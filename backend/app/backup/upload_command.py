"""`python -m app.backup upload` (Stage 14D.2J.2) -- the uploader container's command.

    python -m app.backup upload --environment drill|production [--run-id ID] [--prior auto|none|ID]
                                [--deep] [--scratch-dir DIR] [--allow-production]

It takes `run.lock` (so it never overlaps a `db-dump`), picks the run (the newest promoted run without
`evidence/<run_id>.published.json`, or `--run-id`), builds the R2 source and the Oracle target from the environment and
calls `upload_run`. Output is a short structured summary: no environment, keys, hashes, paths or provider text.

Environment (names only here; values never printed):
    MEDIA_S3_ENDPOINT_URL MEDIA_S3_BUCKET [MEDIA_S3_REGION=auto] MEDIA_S3_ACCESS_KEY_ID MEDIA_S3_SECRET_ACCESS_KEY
    [MEDIA_STORAGE_NAME=r2-primary]      the READY-media source (the same names the application uses; read-only is enough)
    BACKUP_OCI_NAMESPACE BACKUP_OCI_BUCKET [BACKUP_OCI_REGION=eu-frankfurt-1]
                                         the Oracle target (instance principal; create-only IAM, plan §12)
    BACKUP_TOOL_COMMIT                   40-hex commit of the image, recorded in the manifest
    BACKUP_SCRATCH_DIR                   default for --scratch-dir (else /tmp)

`--environment` is mandatory and checked against the bucket names: a drill upload needs two drill buckets, a production
upload two non-drill buckets and `--allow-production` (production uploads stay off until the owner enables them).

Exit codes:
    0  published (or an already sealed run adopted)
    1  upload failed (see step / failure; failure evidence written when possible)
    2  usage error (argparse)
    3  lock held (a db-dump or another upload is running; nothing touched)
    5  configuration / guard / data root failure (nothing uploaded)
    6  interrupted (SIGTERM / SIGINT); nothing is sealed unless a later step finished
    8  nothing to upload: no such run, or it already has published evidence
    9  the local run is unusable (unsafe path, malformed file, or files that disagree with the evidence)
   10  the run IS sealed in the target but its local evidence could not be written -- repeat the same command
"""

import argparse
import asyncio
import re
import shutil
import signal
import tempfile
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TextIO

from app.backup.db_dump_command import (
    EXIT_FAILED,
    EXIT_INTERRUPTED,
    EXIT_LOCK_HELD,
    EXIT_PREFLIGHT,
    EXIT_SUCCESS,
    run_cancellable,
)
from app.backup.layout import CONTAINER_DATA_ROOT
from app.backup.media_sync import MediaSource
from app.backup.run_id import RunIdError, validate_run_id
from app.backup.target import BackupTarget, utc_now
from app.backup.upload_run import (
    UploadFailure,
    UploadReport,
    upload_run,
    utc_compact,
)
from app.backup.workspace import (
    UPLOAD_FAILED_EVIDENCE,
    BackupDataRoot,
    LockHeldError,
    RunLock,
    WorkspaceError,
)
from app.domain.exceptions import MediaStorageError
from app.domain.services.media_backup_ready_set import (
    ReadySetFormatError,  # noqa: F401  (re-exported error family)
)

EXIT_NOTHING_TO_UPLOAD = 8
EXIT_RUN_UNUSABLE = 9
EXIT_SEALED_WITHOUT_EVIDENCE = 10

DEFAULT_OCI_REGION = "eu-frankfurt-1"
DEFAULT_SCRATCH = "/tmp"
_ENDPOINT = re.compile(r"^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?/?$")
_BUCKET = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_NAMESPACE = re.compile(r"^[A-Za-z0-9]{1,64}$")
_REGION = re.compile(r"^[a-z]{2}-[a-z]+-[0-9]$")
_STORAGE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


class UploadConfigError(ValueError):
    """The environment or the arguments are unusable. The message names settings only, never values."""


@dataclass(frozen=True)
class UploadSettings:
    environment: str
    source_endpoint: str
    source_bucket: str
    source_region: str
    source_name: str
    target_namespace: str
    target_bucket: str
    target_region: str
    tool_commit: str


def check_environment(environment: str, source_bucket: str, target_bucket: str, *, allow_production: bool) -> None:
    """The drill / production guard on bucket names (names are the only thing a typo can swap)."""
    if source_bucket == target_bucket:
        raise UploadConfigError("the source bucket and the target bucket must differ")
    drill = ("drill" in source_bucket, "drill" in target_bucket)
    if environment == "drill":
        if not all(drill):
            raise UploadConfigError("--environment drill requires drill buckets for both the source and the target")
    elif environment == "production":
        if any(drill):
            raise UploadConfigError("--environment production refuses drill buckets")
        if not allow_production:
            raise UploadConfigError("production uploads are not enabled (--allow-production is required)")
    else:
        raise UploadConfigError("--environment must be drill or production")


def settings_from_env(env: Mapping[str, str], environment: str, *, allow_production: bool) -> UploadSettings:
    def value(name: str, default: str = "") -> str:
        return env.get(name, default).strip()

    def required(name: str, pattern: re.Pattern[str]) -> str:
        found = value(name)
        if not found:
            raise UploadConfigError(f"{name} is required")
        if not pattern.fullmatch(found):
            raise UploadConfigError(f"{name} is not a valid value")
        return found

    for name in ("MEDIA_S3_ACCESS_KEY_ID", "MEDIA_S3_SECRET_ACCESS_KEY"):
        if not value(name):
            raise UploadConfigError(f"{name} is required")
    settings = UploadSettings(
        environment=environment,
        source_endpoint=required("MEDIA_S3_ENDPOINT_URL", _ENDPOINT),
        source_bucket=required("MEDIA_S3_BUCKET", _BUCKET),
        source_region=value("MEDIA_S3_REGION", "auto") or "auto",
        source_name=value("MEDIA_STORAGE_NAME", "r2-primary") or "r2-primary",
        target_namespace=required("BACKUP_OCI_NAMESPACE", _NAMESPACE),
        target_bucket=required("BACKUP_OCI_BUCKET", _BUCKET),
        target_region=value("BACKUP_OCI_REGION", DEFAULT_OCI_REGION),
        tool_commit=required("BACKUP_TOOL_COMMIT", _COMMIT),
    )
    if not _STORAGE_NAME.fullmatch(settings.source_name):
        raise UploadConfigError("MEDIA_STORAGE_NAME is not a valid value")
    if not _REGION.fullmatch(settings.target_region):
        raise UploadConfigError("BACKUP_OCI_REGION is not a valid value")
    check_environment(environment, settings.source_bucket, settings.target_bucket, allow_production=allow_production)
    return settings


@dataclass
class UploadDependencies:
    """Injection seams: the defaults build the real R2 source and Oracle target (imported lazily)."""

    make_source: Callable[[UploadSettings, Mapping[str, str]], MediaSource]
    make_target: Callable[[UploadSettings], BackupTarget]
    clock: Callable[[], datetime] = utc_now


def _real_source(settings: UploadSettings, env: Mapping[str, str]) -> MediaSource:
    from app.core.s3_media_storage import S3MediaStorage

    return S3MediaStorage(
        endpoint_url=settings.source_endpoint,
        bucket=settings.source_bucket,
        region=settings.source_region,
        access_key_id=env["MEDIA_S3_ACCESS_KEY_ID"].strip(),
        secret_access_key=env["MEDIA_S3_SECRET_ACCESS_KEY"].strip(),
    )


def _real_target(settings: UploadSettings) -> BackupTarget:
    from app.backup.oci_target import OciBackupTarget

    return OciBackupTarget.from_instance_principal(
        namespace=settings.target_namespace, bucket=settings.target_bucket, region=settings.target_region
    )


DEFAULT_DEPENDENCIES = UploadDependencies(make_source=_real_source, make_target=_real_target)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.backup upload", description="Upload one promoted run")
    parser.add_argument("--environment", required=True, choices=("drill", "production"))
    parser.add_argument("--run-id", default=None, help="a promoted run (default: the newest without published evidence)")
    parser.add_argument("--prior", default="auto", help="auto (newest published run), none, or a run id")
    parser.add_argument("--deep", action="store_true", help="download and compare every object again")
    parser.add_argument("--scratch-dir", default=None, help="private scratch directory (default BACKUP_SCRATCH_DIR or /tmp)")
    parser.add_argument("--allow-production", action="store_true", help="required for --environment production")
    return parser


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    return build_parser().parse_args(list(argv))


def select_run(data_root: BackupDataRoot, requested: str | None) -> str | None:
    if requested is not None:
        return validate_run_id(requested)
    published = set(data_root.published_run_ids())
    pending = [run for run in data_root.promoted_run_ids() if run not in published]
    return pending[-1] if pending else None


def exit_code_for(report: UploadReport) -> int:
    if report.ok:
        return EXIT_SUCCESS
    failure = report.failure
    if failure in (UploadFailure.ALREADY_PUBLISHED, UploadFailure.RUN_MISSING):
        return EXIT_NOTHING_TO_UPLOAD
    if failure in (UploadFailure.RUN_UNSAFE, UploadFailure.RUN_INVALID):
        return EXIT_RUN_UNUSABLE
    if failure is UploadFailure.EVIDENCE_NOT_WRITTEN:
        return EXIT_SEALED_WITHOUT_EVIDENCE
    return EXIT_FAILED


def _print_report(report: UploadReport, out: TextIO) -> None:
    if report.ok:
        how = "adopted" if report.adopted else "published"
        print(
            f"upload complete: run_id={report.run_id} {how} objects={report.objects} ready_assets={report.ready_assets}"
            f" prior={report.prior_run_id or '-'}",
            file=out,
        )
        return
    failure = report.failure.value if report.failure else "-"
    print(f"upload failed: run_id={report.run_id} step={report.step.value} failure={failure}", file=out)
    if report.failure is UploadFailure.EVIDENCE_NOT_WRITTEN:
        print("the run IS sealed in the target; repeat the same command to record it locally", file=out)


def _record_failure(data_root: BackupDataRoot, report: UploadReport, moment: datetime, out: TextIO) -> None:
    """Best effort: evidence/<run_id>.upload-failed-<UTC>.json. Never replaces the failure being reported."""
    if report.failure in (UploadFailure.ALREADY_PUBLISHED, None):
        return
    suffix = f".upload-failed-{utc_compact(moment)}.json"
    assert UPLOAD_FAILED_EVIDENCE.match(suffix)
    try:
        data_root.write_upload_evidence(report.run_id, suffix, report.report_bytes())
    except WorkspaceError as exc:
        print(f"failure evidence could not be written ({type(exc).__name__})", file=out)


def run_upload(
    env: Mapping[str, str],
    argv: Sequence[str],
    out: TextIO,
    *,
    data_root: Path = CONTAINER_DATA_ROOT,
    deps: UploadDependencies | None = None,
    signals: tuple[int, ...] = (signal.SIGTERM, signal.SIGINT),
) -> int:
    args = parse_args(argv)
    deps = deps or DEFAULT_DEPENDENCIES
    try:
        settings = settings_from_env(env, args.environment, allow_production=args.allow_production)
        prior = args.prior
        if prior != "auto":
            prior = None if prior == "none" else validate_run_id(prior)
        requested = None if args.run_id is None else validate_run_id(args.run_id)
    except (UploadConfigError, RunIdError) as exc:
        print(f"upload preflight failed: {exc}", file=out)
        return EXIT_PREFLIGHT

    root = BackupDataRoot(data_root)
    try:
        lock = RunLock.acquire(root)
    except LockHeldError:
        print("upload not started: another backup run holds run.lock", file=out)
        return EXIT_LOCK_HELD
    except WorkspaceError as exc:
        print(f"upload preflight failed: the data root is unusable ({type(exc).__name__})", file=out)
        return EXIT_PREFLIGHT
    with lock:
        try:
            run_id = select_run(root, requested)
        except WorkspaceError as exc:
            print(f"upload preflight failed: the data root is unusable ({type(exc).__name__})", file=out)
            return EXIT_PREFLIGHT
        if run_id is None:
            print("nothing to upload: every promoted run already has published evidence", file=out)
            return EXIT_NOTHING_TO_UPLOAD
        try:
            source = deps.make_source(settings, env)
            target = deps.make_target(settings)
        except MediaStorageError as exc:
            print(f"upload preflight failed: the storage clients cannot be built ({type(exc).__name__})", file=out)
            return EXIT_PREFLIGHT
        scratch_parent = Path(args.scratch_dir or env.get("BACKUP_SCRATCH_DIR") or DEFAULT_SCRATCH)
        try:
            scratch = Path(tempfile.mkdtemp(prefix="pe-upload-", dir=scratch_parent))
        except OSError as exc:
            print(f"upload preflight failed: the scratch directory is unusable ({type(exc).__name__})", file=out)
            return EXIT_PREFLIGHT
        try:
            try:
                report = asyncio.run(
                    run_cancellable(
                        lambda: upload_run(
                            root,
                            run_id,
                            source=source,
                            target=target,
                            reader=target,
                            source_name=settings.source_name,
                            source_bucket=settings.source_bucket,
                            target_bucket=settings.target_bucket,
                            tool_commit=settings.tool_commit,
                            scratch_dir=scratch,
                            prior=prior,
                            deep=args.deep,
                            clock=deps.clock,
                        ),
                        signals,
                    )
                )
            except asyncio.CancelledError:
                print("upload interrupted: nothing is sealed unless the run was already published", file=out)
                return EXIT_INTERRUPTED
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        _print_report(report, out)
        if not report.ok:
            _record_failure(root, report, deps.clock(), out)
        return exit_code_for(report)
