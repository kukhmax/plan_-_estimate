"""Upload one promoted local run to the independent backup target -- Stage 14D.2J.2.

Contract: docs/STAGE_14D_BACKUP_RESTORE_PLAN.md §5-§9, §15, §16.16.

`db-dump` leaves `encrypted/<run_id>/` (artifact, sidecars, local evidence). This module is what the uploader
container does with it, in the only order that keeps the §7 invariant:

    local     the run's files are read through the data root (no symlinks, private, bounded) and bound together:
              the READY file must hash to the evidence's `ready_set_sha256`, the recipients must be as many as
              the evidence says, the artifact is checked against the evidence by `publish_run`
    prior     the previous published run (named, or the newest `evidence/*.published.json` older than this run)
              is loaded and its seal verified, so unchanged objects inherit their SHA-256 provenance
    sync      `sync_media`: every READY object is brought into the target (create-only) or proved present
    publish   `publish_run`: dump, manifest, then COMPLETE.json last
    evidence  `evidence/<run_id>.published.json` (counts only) so the next run finds its prior without listing

Any step that does not succeed ends the upload with one machine-readable failure; nothing later runs. A failed
upload leaves the target without COMPLETE.json for that run (never a half-sealed run) and the local files
untouched; the same upload can be repeated, because every write is create-only or verified-identical.
"""

import asyncio
import enum
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.backup import manifest as mf
from app.backup.media_sync import (
    MediaSource,
    PriorRunError,
    load_prior_run,
    sync_media,
)
from app.backup.run_id import validate_run_id
from app.backup.run_sidecars import (
    MAX_SIDECAR_BYTES,
    READY_ASSETS_NAME,
    RECIPIENTS_NAME,
    SidecarError,
    parse_ready_assets,
    parse_recipients,
)
from app.backup.target import (
    DEFAULT_RETRY,
    BackupReader,
    BackupTarget,
    BackupTargetError,
    Clock,
    RetryPolicy,
    Sleep,
    file_facts,
    publish_run,
    utc_now,
)
from app.backup.workspace import (
    LOCAL_EVIDENCE_NAME,
    PUBLISHED_EVIDENCE_SUFFIX,
    BackupDataRoot,
    EvidenceWriteError,
    RunFileMissingError,
    WorkspaceError,
)
from app.core.db_dump_encryption import ENCRYPTED_DUMP_NAME
from app.domain.exceptions import MediaStorageError
from app.domain.services.media_backup_ready_set import ready_set_digest

logger = logging.getLogger(__name__)

REPORT_FORMAT = "plan-estimate/upload-report/v1"
PUBLISHED_FORMAT = "plan-estimate/published-run/v1"
LOCAL_RUN_FORMAT = "plan-estimate/local-db-backup/v1"
MAX_EVIDENCE_BYTES = 1024 * 1024


class UploadStep(enum.StrEnum):
    LOCAL = "local"
    TARGET = "target"
    PRIOR = "prior"
    SYNC = "sync"
    PUBLISH = "publish"
    EVIDENCE = "evidence"
    DONE = "done"


class UploadFailure(enum.StrEnum):
    ALREADY_PUBLISHED = "ALREADY_PUBLISHED"  # this run has published evidence: nothing to do
    RUN_MISSING = "RUN_MISSING"  # no such promoted run, or one of its files is missing
    RUN_UNSAFE = "RUN_UNSAFE"  # a path of the run is a symlink, not private, or not a regular file
    RUN_INVALID = "RUN_INVALID"  # a file of the run is malformed or does not agree with the evidence
    PRIOR_UNUSABLE = "PRIOR_UNUSABLE"  # the prior run is missing, not sealed, inconsistent or from another bucket
    PRIOR_UNAVAILABLE = "PRIOR_UNAVAILABLE"  # the prior run could not be read (target unavailable / misconfigured)
    TARGET_RUN_CONFLICT = "TARGET_RUN_CONFLICT"  # the target holds a run with this id that is not this local run
    TARGET_UNAVAILABLE = "TARGET_UNAVAILABLE"  # the target could not be read to look for this run
    SYNC_INCOMPLETE = "SYNC_INCOMPLETE"  # media sync did not admit every object (see the embedded sync report)
    PUBLISH_FAILED = "PUBLISH_FAILED"  # dump / manifest / seal could not be written and verified
    EVIDENCE_NOT_WRITTEN = "EVIDENCE_NOT_WRITTEN"  # the run IS sealed in the target, local evidence is missing


@dataclass(frozen=True)
class LocalRun:
    """What the upload takes from `local-run.json` (validated again by the manifest types when used)."""

    run_id: str
    started_at: str
    dumped_at: str
    alembic_head: str
    ready_count: int
    ready_set_sha256: str
    artifact_sha256: str
    artifact_size: int
    recipient_count: int
    pending: int
    failed: int


class LocalRunError(ValueError):
    """`local-run.json` is not a complete run evidence document. The message names no value."""


def _section(document: dict[str, Any], name: str) -> dict[str, Any]:
    value = document.get(name)
    if not isinstance(value, dict):
        raise LocalRunError(f"{name} is missing")
    return value


def _field(section: dict[str, Any], name: str) -> Any:
    if name not in section:
        raise LocalRunError(f"{name} is missing")
    return section[name]


def parse_local_run(data: bytes, run_id: str) -> LocalRun:
    try:
        document = json.loads(data)
    except (ValueError, UnicodeDecodeError):
        raise LocalRunError("the run evidence is not JSON") from None
    if not isinstance(document, dict):
        raise LocalRunError("the run evidence is not an object")
    if document.get("format") != LOCAL_RUN_FORMAT or document.get("status") != "complete":
        raise LocalRunError("the run evidence is not a complete local backup")
    if document.get("run_id") != run_id:
        raise LocalRunError("the run evidence belongs to another run")
    database, snapshot, artifact = (_section(document, name) for name in ("database", "snapshot", "artifact"))
    counts = _field(database, "photo_asset_status_counts")
    if not isinstance(counts, dict):
        raise LocalRunError("photo_asset_status_counts is missing")
    if _field(database, "alembic_revision") != _field(database, "expected_alembic_head"):
        raise LocalRunError("the run was taken at an unexpected schema revision")
    if _field(artifact, "name") != ENCRYPTED_DUMP_NAME or _field(artifact, "encryption") != "age":
        raise LocalRunError("the artifact is not the encrypted dump")
    return LocalRun(
        run_id=run_id,
        started_at=_field(document, "started_at"),
        dumped_at=_field(document, "dump_completed_at"),
        alembic_head=_field(database, "expected_alembic_head"),
        ready_count=_field(snapshot, "ready_count"),
        ready_set_sha256=_field(snapshot, "ready_set_sha256"),
        artifact_sha256=_field(artifact, "sha256"),
        artifact_size=_field(artifact, "size"),
        recipient_count=_field(artifact, "recipient_count"),
        pending=_field(counts, "PENDING"),
        failed=_field(counts, "FAILED"),
    )


@dataclass(frozen=True)
class UploadReport:
    run_id: str
    step: UploadStep  # the last step started (DONE after success)
    failure: UploadFailure | None
    sync_report: bytes | None = None  # the sync's own canonical report, when the sync ran
    objects: int | None = None
    ready_assets: int | None = None
    prior_run_id: str | None = None
    adopted: bool = False  # the run was already sealed in the target; only the local evidence was written

    @property
    def ok(self) -> bool:
        return self.step is UploadStep.DONE and self.failure is None

    @property
    def published(self) -> bool:
        """The run is sealed in the target (also true when only the local evidence failed)."""
        return self.ok or self.failure is UploadFailure.EVIDENCE_NOT_WRITTEN

    def report_bytes(self) -> bytes:
        document: dict[str, object] = {
            "format": REPORT_FORMAT,
            "run_id": self.run_id,
            "ok": self.ok,
            "published": self.published,
            "adopted": self.adopted,
            "step": self.step.value,
            "failure": None if self.failure is None else self.failure.value,
            "prior_run_id": self.prior_run_id,
            "objects": self.objects,
            "ready_assets": self.ready_assets,
            "sync": None if self.sync_report is None else json.loads(self.sync_report),
        }
        return mf.canonical_line(document)


def published_evidence_bytes(report: UploadReport, published_at: datetime) -> bytes:
    document: dict[str, object] = {
        "format": PUBLISHED_FORMAT,
        "run_id": report.run_id,
        "published_at": mf.format_timestamp(published_at),
        "objects": report.objects,
        "ready_assets": report.ready_assets,
        "prior_run_id": report.prior_run_id,
    }
    return mf.canonical_line(document)


async def upload_run(
    data_root: BackupDataRoot,
    run_id: str,
    *,
    source: MediaSource,
    target: BackupTarget,
    reader: BackupReader,
    source_name: str,
    source_bucket: str,
    target_bucket: str,
    tool_commit: str,
    scratch_dir: Path,
    prior: str | None = "auto",
    deep: bool = False,
    retry: RetryPolicy = DEFAULT_RETRY,
    sleep: Sleep | None = None,
    clock: Clock = utc_now,
) -> UploadReport:
    """Upload the promoted run `run_id` (module docstring). `prior`: "auto" = newest published run older than this
    one (none if there is none), a run id = that run, None = no prior (every object is downloaded and compared)."""
    validate_run_id(run_id)

    def failed(step: UploadStep, failure: UploadFailure, **extra: Any) -> UploadReport:
        logger.info("upload stopped: run=%s step=%s failure=%s", run_id, step.value, failure.value)
        return UploadReport(run_id, step, failure, **extra)

    # -- local ----------------------------------------------------------------------------------------------
    if run_id in data_root.published_run_ids():
        return failed(UploadStep.LOCAL, UploadFailure.ALREADY_PUBLISHED)
    try:
        local = parse_local_run(data_root.read_promoted_file(run_id, LOCAL_EVIDENCE_NAME, max_bytes=MAX_EVIDENCE_BYTES), run_id)
        assets = parse_ready_assets(data_root.read_promoted_file(run_id, READY_ASSETS_NAME, max_bytes=MAX_SIDECAR_BYTES))
        recipients = parse_recipients(data_root.read_promoted_file(run_id, RECIPIENTS_NAME, max_bytes=MAX_SIDECAR_BYTES))
        dump_path = data_root.verified_promoted_path(run_id, ENCRYPTED_DUMP_NAME)
    except RunFileMissingError:
        return failed(UploadStep.LOCAL, UploadFailure.RUN_MISSING)
    except WorkspaceError:
        return failed(UploadStep.LOCAL, UploadFailure.RUN_UNSAFE)
    except (LocalRunError, SidecarError):
        return failed(UploadStep.LOCAL, UploadFailure.RUN_INVALID)
    digest = ready_set_digest(assets)
    if digest.ready_set_sha256 != local.ready_set_sha256 or digest.ready_count != local.ready_count:
        return failed(UploadStep.LOCAL, UploadFailure.RUN_INVALID)
    if len(recipients) != local.recipient_count:
        return failed(UploadStep.LOCAL, UploadFailure.RUN_INVALID)
    try:
        header = mf.ManifestHeader(
            run_id=run_id,
            started_at=local.started_at,
            tool_commit=tool_commit,
            source=mf.SourceInfo(source_name, source_bucket),
            target=mf.TargetInfo(target_bucket),
            db_dump=mf.DbDumpInfo(
                key=mf.db_dump_key(run_id),
                recipients=recipients,
                encrypted_sha256=local.artifact_sha256,
                encrypted_size=local.artifact_size,
                alembic_head=local.alembic_head,
                dumped_at=local.dumped_at,
            ),
            snapshot=mf.SnapshotInfo(local.ready_count, local.ready_set_sha256),
        )
    except mf.ManifestError:
        return failed(UploadStep.LOCAL, UploadFailure.RUN_INVALID)

    size, sha256 = await asyncio.to_thread(file_facts, dump_path)
    if size != local.artifact_size or sha256 != local.artifact_sha256:
        return failed(UploadStep.LOCAL, UploadFailure.RUN_INVALID)

    # -- target: is this very run already sealed there? (an upload that sealed it but could not write its
    #    local evidence is finished by writing the evidence, never by publishing a second, different manifest) --
    try:
        existing = await load_prior_run(reader, run_id, scratch_dir=scratch_dir, retry=retry, sleep=sleep)
    except PriorRunError as exc:
        if not exc.missing:
            return failed(UploadStep.TARGET, UploadFailure.TARGET_RUN_CONFLICT)
    except (MediaStorageError, BackupTargetError):
        return failed(UploadStep.TARGET, UploadFailure.TARGET_UNAVAILABLE)
    else:
        sealed = existing.manifest.header
        if (
            sealed.snapshot != header.snapshot
            or sealed.db_dump != header.db_dump
            or sealed.source != header.source
            or sealed.target != header.target
        ):
            return failed(UploadStep.TARGET, UploadFailure.TARGET_RUN_CONFLICT)
        summary = existing.manifest.summary
        report = UploadReport(
            run_id, UploadStep.DONE, None, None, summary.objects, summary.ready_assets, None, adopted=True
        )
        try:
            data_root.write_upload_evidence(run_id, PUBLISHED_EVIDENCE_SUFFIX, published_evidence_bytes(report, clock()))
        except EvidenceWriteError:
            return failed(
                UploadStep.EVIDENCE,
                UploadFailure.EVIDENCE_NOT_WRITTEN,
                objects=summary.objects,
                ready_assets=summary.ready_assets,
                adopted=True,
            )
        return report

    # -- prior ----------------------------------------------------------------------------------------------
    prior_id: str | None
    if prior == "auto":
        older = [published for published in data_root.published_run_ids() if published < run_id]
        prior_id = older[-1] if older else None
    else:
        prior_id = None if prior is None else validate_run_id(prior)
    verified: mf.VerifiedRun | None = None
    if prior_id is not None:
        try:
            verified = await load_prior_run(reader, prior_id, scratch_dir=scratch_dir, retry=retry, sleep=sleep)
        except PriorRunError:
            return failed(UploadStep.PRIOR, UploadFailure.PRIOR_UNUSABLE, prior_run_id=prior_id)
        except (MediaStorageError, BackupTargetError):
            return failed(UploadStep.PRIOR, UploadFailure.PRIOR_UNAVAILABLE, prior_run_id=prior_id)

    # -- sync -----------------------------------------------------------------------------------------------
    try:
        result = await sync_media(
            source,
            target,
            assets=assets,
            run_id=run_id,
            target_bucket=target_bucket,
            scratch_dir=scratch_dir,
            prior=verified,
            deep=deep,
            retry=retry,
            sleep=sleep,
            clock=clock,
        )
    except PriorRunError:
        return failed(UploadStep.PRIOR, UploadFailure.PRIOR_UNUSABLE, prior_run_id=prior_id)
    if not result.complete:
        return failed(UploadStep.SYNC, UploadFailure.SYNC_INCOMPLETE, sync_report=result.report_bytes(), prior_run_id=prior_id)

    # -- publish --------------------------------------------------------------------------------------------
    try:
        published = await publish_run(
            target,
            header=header,
            objects=result.objects_for_publication(),
            dump_path=dump_path,
            source_keys=result.source_keys,
            orphan_candidates=result.orphan_candidates,
            scratch_dir=scratch_dir,
            skipped_pending=local.pending,
            skipped_failed=local.failed,
            retry=retry,
            sleep=asyncio.sleep if sleep is None else sleep,
            clock=clock,
        )
    except (BackupTargetError, MediaStorageError):
        return failed(UploadStep.PUBLISH, UploadFailure.PUBLISH_FAILED, sync_report=result.report_bytes(), prior_run_id=prior_id)

    report = UploadReport(
        run_id, UploadStep.DONE, None, result.report_bytes(), published.objects, published.ready_assets, prior_id
    )

    # -- evidence -------------------------------------------------------------------------------------------
    try:
        data_root.write_upload_evidence(run_id, PUBLISHED_EVIDENCE_SUFFIX, published_evidence_bytes(report, clock()))
    except EvidenceWriteError:
        return UploadReport(
            run_id,
            UploadStep.EVIDENCE,
            UploadFailure.EVIDENCE_NOT_WRITTEN,
            result.report_bytes(),
            published.objects,
            published.ready_assets,
            prior_id,
        )
    return report


def utc_compact(moment: datetime) -> str:
    """`YYYYMMDDTHHMMSSZ`, the suffix of `.upload-failed-<UTC>.json` evidence names."""
    return moment.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
