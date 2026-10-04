"""Media sync: copy the READY set from the source store (R2) into the backup target (Oracle) -- Stage 14D.2G.

Contract: docs/STAGE_14D_BACKUP_RESTORE_PLAN.md §5 (layout, copy unit), §8 (SHA-256 provenance),
§10 (backup-time and post-copy verification), §15 (failure / resume), §16.11 (this module).

The input is the READY set of the run's database snapshot (`ReadyAsset`, 14D.2A). Every asset needs
exactly three objects in the target -- original, display, thumbnail -- under the same immutable keys
as the source. Objects are handled one at a time, strictly sequentially:

    target object missing   download the source object into a private scratch directory, check size
                            (all roles) and SHA-256 (originals, against the database row), then
                            `put_verified` (create-only put, HEAD, full re-download, SHA-256) ->
                            action `copied`, provenance `downloaded`
    target object present   admitted only per §8:
                              * `inherited:<run_id>` -- the prior run is sealed (`VerifiedRun`), lists
                                this key with the same size and trusted SHA-256, the object exists with
                                that size (and, for originals, the recorded SHA-256 equals the database
                                row). Nothing is downloaded.
                              * otherwise (no prior run, `--deep`, key / size not recorded, ...) the
                                target object is downloaded and its SHA-256 recomputed, AND the source
                                object is downloaded and compared: the target is write-once, so a
                                same-size but different object would otherwise be locked into the
                                backup for good. A difference is `TARGET_CONFLICT`; nothing is ever
                                overwritten.

Failures are per object (`ObjectFailure`, a machine-readable code, never a key, hash or provider
message). The run goes on so the report is complete (§15) but `MediaSyncResult.complete` is False, and
`objects_for_publication()` refuses to hand out objects, so a manifest / COMPLETE.json can never be
built from a partial copy. A misconfigured store (permission, bucket) or a streak of unavailable-store
failures aborts the run at once (`AbortReason`). Unexpected exceptions (programming errors, a full
scratch disk) are not translated: they propagate and the run has no seal.

This module has no delete, overwrite or multipart path; it can only create objects through
`BackupTarget.put_new`. Scratch files live in a fresh 0700 directory per object and are always removed.
"""

import asyncio
import enum
import logging
import os
import shutil
import tempfile
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Protocol, TypeVar

from app.backup.manifest import (
    DOWNLOADED,
    Action,
    ManifestError,
    ManifestObject,
    ProvenanceKind,
    Role,
    VerifiedRun,
    canonical_line,
    complete_key,
    decide_provenance,
    expected_content_type,
    format_timestamp,
    manifest_key,
    verify_run,
)
from app.backup.run_id import validate_run_id
from app.backup.target import (
    DEFAULT_RETRY,
    BackupReader,
    BackupTarget,
    Clock,
    RetryPolicy,
    Sleep,
    TargetObject,
    TargetVerificationError,
    file_facts,
    put_verified,
    retrying,
    utc_now,
)
from app.domain.exceptions import (
    MediaObjectConflict,
    MediaObjectNotFound,
    MediaStorageError,
    MediaStorageUnavailable,
)
from app.domain.photos.keys import PHOTO_KEY_PREFIX
from app.domain.services.media_backup_ready_set import ReadyAsset

logger = logging.getLogger(__name__)

REPORT_FORMAT = "plan-estimate/media-sync-report/v1"
MAX_CONSECUTIVE_UNAVAILABLE = 5
_SCRATCH_PREFIX = "media-sync-"

T = TypeVar("T")


class MediaSyncError(RuntimeError):
    """Base class of media sync errors. Messages never contain keys, hashes or provider text."""


class MediaSyncIncomplete(MediaSyncError):
    """Objects were requested for publication from a run that is not complete."""


class PriorRunError(MediaSyncError):
    """The named prior run cannot be used (missing, not sealed, inconsistent, or from another bucket)."""

    def __init__(self, message: str, *, missing: bool = False) -> None:
        super().__init__(message)
        self.missing = missing  # True: COMPLETE.json or the manifest does not exist at all


class FailureCode(enum.StrEnum):
    MISSING_SOURCE = "MISSING_SOURCE"  # READY in the database, absent in the source store: evidence loss
    SOURCE_SIZE_MISMATCH = "SOURCE_SIZE_MISMATCH"  # source bytes differ in size from the database row
    SOURCE_SHA_MISMATCH = "SOURCE_SHA_MISMATCH"  # source original differs from the database SHA-256
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"  # transient source failure persisted through all retries
    TARGET_CONFLICT = "TARGET_CONFLICT"  # the target already holds different bytes (never overwritten)
    TARGET_VERIFICATION_FAILED = "TARGET_VERIFICATION_FAILED"  # post-copy check failed
    TARGET_UNAVAILABLE = "TARGET_UNAVAILABLE"  # transient target failure persisted through all retries
    SOURCE_LISTING_FAILED = "SOURCE_LISTING_FAILED"  # source_keys / orphan_candidates could not be established


class AbortReason(enum.StrEnum):
    SOURCE_MISCONFIGURED = "SOURCE_MISCONFIGURED"
    TARGET_MISCONFIGURED = "TARGET_MISCONFIGURED"
    STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"  # too many consecutive unavailable-store failures


_UNAVAILABLE_CODES = frozenset({FailureCode.SOURCE_UNAVAILABLE, FailureCode.TARGET_UNAVAILABLE})


class MediaSource(Protocol):
    """What the sync needs from the source store. `S3MediaStorage` and `InMemoryMediaStorage` provide it."""

    async def download_to(self, key: str, path: Path) -> None: ...

    def iter_keys(self, prefix: str) -> AsyncIterator[str]: ...


@dataclass(frozen=True)
class ObjectFailure:
    asset_id: str | None  # None only for a failure that is not about one asset (the source listing)
    role: Role | None
    code: FailureCode

    def to_dict(self) -> dict[str, str | None]:
        return {
            "asset_id": self.asset_id,
            "role": None if self.role is None else self.role.value,
            "code": self.code.value,
        }


@dataclass(frozen=True)
class SyncCounts:
    copied: int = 0  # created in the target by this run
    inherited: int = 0  # present, provenance inherited from the prior run (nothing downloaded)
    verified_present: int = 0  # present, SHA-256 established by download (and compared with the source)
    failed: int = 0
    bytes_copied: int = 0
    objects_required: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "copied": self.copied,
            "inherited": self.inherited,
            "verified_present": self.verified_present,
            "failed": self.failed,
            "bytes_copied": self.bytes_copied,
            "objects_required": self.objects_required,
        }


@dataclass(frozen=True)
class MediaSyncResult:
    run_id: str
    objects: tuple[ManifestObject, ...]  # admitted and verified, ordered by key
    failures: tuple[ObjectFailure, ...]
    counts: SyncCounts
    source_keys: int
    orphan_candidates: int
    aborted: AbortReason | None

    @property
    def complete(self) -> bool:
        return self.aborted is None and not self.failures and len(self.objects) == self.counts.objects_required

    def objects_for_publication(self) -> tuple[ManifestObject, ...]:
        """The object lines for `publish_run`; refused unless every required object was admitted."""
        if not self.complete:
            raise MediaSyncIncomplete("the media sync is not complete; no manifest may be built from it")
        return self.objects

    def report_bytes(self) -> bytes:
        """Canonical, secret-free error report (one JSON line). Safe to store next to the run's evidence."""
        document: dict[str, object] = {
            "format": REPORT_FORMAT,
            "run_id": self.run_id,
            "complete": self.complete,
            "aborted": None if self.aborted is None else self.aborted.value,
            "counts": self.counts.to_dict(),
            "source_keys": self.source_keys,
            "orphan_candidates": self.orphan_candidates,
            "failures": [failure.to_dict() for failure in self.failures],
        }
        return canonical_line(document)


# --- internals ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Required:
    asset_id: str
    role: Role
    key: str
    size: int
    expected_sha256: str | None  # the database SHA-256 (originals only)
    content_type: str


class _ObjectFailed(Exception):
    def __init__(self, code: FailureCode) -> None:
        super().__init__(code.value)
        self.code = code


class _Abort(Exception):
    def __init__(self, reason: AbortReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


def required_objects(assets: Iterable[ReadyAsset]) -> list[_Required]:
    """The three objects of every asset in canonical order; refuses anything the 14B layout does not allow.

    A key carries its asset id and a role-specific name, so unique assets and valid keys make every key unique."""
    required: list[_Required] = []
    seen_assets: set[str] = set()
    for asset in sorted(assets, key=lambda item: str(item.asset_id)):
        asset_id = str(asset.asset_id)
        if asset_id in seen_assets:
            raise MediaSyncError("the READY set lists an asset twice")
        seen_assets.add(asset_id)
        for role, key, size, sha in (
            (Role.ORIGINAL, asset.key_original, asset.byte_size, asset.sha256),
            (Role.DISPLAY, asset.key_display, asset.display_byte_size, None),
            (Role.THUMBNAIL, asset.key_thumbnail, asset.thumbnail_byte_size, None),
        ):
            try:
                content_type = expected_content_type(role, asset_id, key)
            except ManifestError:
                raise MediaSyncError("an asset has a key that is not valid for its role") from None
            required.append(_Required(asset_id, role, key, size, sha, content_type))
    return required


class _Scratch:
    """A private per-object scratch directory, always removed."""

    def __init__(self, parent: Path) -> None:
        self._dir = Path(tempfile.mkdtemp(prefix=_SCRATCH_PREFIX, dir=parent))

    def path(self, name: str) -> Path:
        return self._dir / name  # never created here: stores write new files (the target adapter creates exclusively)

    def close(self) -> None:
        shutil.rmtree(self._dir, ignore_errors=True)
        if self._dir.exists():  # pragma: no cover - a leftover would hold object bytes
            raise MediaSyncError("the scratch directory could not be removed")


class _Syncer:
    def __init__(
        self,
        source: MediaSource,
        target: BackupTarget,
        *,
        prior: VerifiedRun | None,
        deep: bool,
        scratch_dir: Path,
        retry: RetryPolicy,
        sleep: Sleep,
        clock: Clock,
    ) -> None:
        self.source = source
        self.target = target
        self.prior = prior
        self.deep = deep
        self.scratch_dir = scratch_dir
        self.retry = retry
        self.sleep = sleep
        self.clock = clock

    # -- store calls, translated to failure codes -------------------------------------------------

    async def _source_call(self, operation: Callable[[], Awaitable[T]], what: str) -> T:
        try:
            return await retrying(operation, self.retry, self.sleep, what)
        except MediaObjectNotFound:
            raise _ObjectFailed(FailureCode.MISSING_SOURCE) from None
        except MediaStorageUnavailable:
            raise _ObjectFailed(FailureCode.SOURCE_UNAVAILABLE) from None
        except MediaStorageError:
            raise _Abort(AbortReason.SOURCE_MISCONFIGURED) from None

    async def _target_call(self, operation: Callable[[], Awaitable[T]], what: str) -> T:
        try:
            return await retrying(operation, self.retry, self.sleep, what)
        except MediaObjectConflict:
            raise _ObjectFailed(FailureCode.TARGET_CONFLICT) from None
        except (MediaObjectNotFound, TargetVerificationError):
            raise _ObjectFailed(FailureCode.TARGET_VERIFICATION_FAILED) from None
        except MediaStorageUnavailable:
            raise _ObjectFailed(FailureCode.TARGET_UNAVAILABLE) from None
        except MediaStorageError:
            raise _Abort(AbortReason.TARGET_MISCONFIGURED) from None

    # -- one object ---------------------------------------------------------------------------------

    async def admit(self, req: _Required) -> tuple[ManifestObject, Action, int]:
        """Admit one required object. Returns the manifest line, how it was admitted and the bytes copied."""
        head = await self._target_call(lambda: self.target.head(req.key), "head")
        decision = decide_provenance(
            self.prior,
            key=req.key,
            expected_size=req.size,
            expected_sha256=req.expected_sha256,
            target_size=None if head is None else head.size,
            deep=self.deep,
        )
        if head is not None and decision.kind is ProvenanceKind.INHERIT and decision.sha256 is not None:
            line = self._line(req, Action.ALREADY_PRESENT, decision.sha256, decision.provenance, head.etag)
            return line, Action.ALREADY_PRESENT, 0
        if head is not None and head.size != req.size:
            raise _ObjectFailed(FailureCode.TARGET_CONFLICT)  # refused on size alone: nothing is downloaded
        scratch = _Scratch(self.scratch_dir)
        try:
            source_sha = await self._fetch_source(req, scratch)
            if head is None:
                return await self._copy(req, scratch, source_sha)
            return await self._verify_present(req, head, scratch, source_sha)
        finally:
            scratch.close()

    async def _fetch_source(self, req: _Required, scratch: _Scratch) -> str:
        """Download the source object, check size (and the original's SHA-256 against the database)."""
        path = scratch.path("source")
        await self._source_call(lambda: self.source.download_to(req.key, path), "source download")
        size, sha = file_facts(path)
        if size != req.size:
            raise _ObjectFailed(FailureCode.SOURCE_SIZE_MISMATCH)
        if req.expected_sha256 is not None and sha != req.expected_sha256:
            raise _ObjectFailed(FailureCode.SOURCE_SHA_MISMATCH)
        return sha

    async def _copy(self, req: _Required, scratch: _Scratch, source_sha: str) -> tuple[ManifestObject, Action, int]:
        path = scratch.path("source")
        stored = await self._target_call(
            lambda: put_verified(
                self.target,
                key=req.key,
                source=path,
                content_type=req.content_type,
                scratch_dir=self.scratch_dir,
                expected_sha256=source_sha,
                expected_size=req.size,
                retry=self.retry,
                sleep=self.sleep,
            ),
            "put",
        )
        if stored.created:
            return self._line(req, Action.COPIED, stored.sha256, DOWNLOADED, stored.etag), Action.COPIED, req.size
        # Created by an earlier, ambiguous attempt of this tool: its bytes were just proved identical.
        return self._line(req, Action.ALREADY_PRESENT, stored.sha256, DOWNLOADED, stored.etag), Action.ALREADY_PRESENT, 0

    async def _verify_present(
        self, req: _Required, head: TargetObject, scratch: _Scratch, source_sha: str
    ) -> tuple[ManifestObject, Action, int]:
        path = scratch.path("target")
        await self._target_call(lambda: self.target.download_to(req.key, path), "target download")
        size, target_sha = file_facts(path)
        if size != req.size or target_sha != source_sha:
            raise _ObjectFailed(FailureCode.TARGET_CONFLICT)
        return self._line(req, Action.ALREADY_PRESENT, target_sha, DOWNLOADED, head.etag), Action.ALREADY_PRESENT, 0

    def _line(self, req: _Required, action: Action, sha256: str, provenance: str, etag: str | None) -> ManifestObject:
        return ManifestObject(
            asset_id=req.asset_id,
            role=req.role,
            key=req.key,
            size=req.size,
            sha256=sha256,
            content_type=req.content_type,
            action=action,
            sha_provenance=provenance,
            verified_at=format_timestamp(self.clock()),
            target_etag=etag,
        )

    # -- source listing -------------------------------------------------------------------------------

    async def count_listing(self, required_keys: frozenset[str]) -> tuple[int, int]:
        """(keys under the photo prefix, keys that are not part of the required set)."""

        async def count() -> tuple[int, int]:
            total = orphans = 0
            async for key in self.source.iter_keys(PHOTO_KEY_PREFIX):
                total += 1
                if key not in required_keys:
                    orphans += 1
            return total, orphans

        return await self._source_call(count, "source listing")


async def sync_media(
    source: MediaSource,
    target: BackupTarget,
    *,
    assets: Iterable[ReadyAsset],
    run_id: str,
    target_bucket: str,
    scratch_dir: Path,
    prior: VerifiedRun | None = None,
    deep: bool = False,
    retry: RetryPolicy = DEFAULT_RETRY,
    sleep: Sleep | None = None,
    clock: Clock = utc_now,
    max_consecutive_unavailable: int = MAX_CONSECUTIVE_UNAVAILABLE,
) -> MediaSyncResult:
    """Bring every object of the READY set into the target and report exactly what happened."""
    validate_run_id(run_id)
    if max_consecutive_unavailable < 1:
        raise ValueError("max_consecutive_unavailable must be at least 1")
    if prior is not None:
        if prior.run_id >= run_id:
            raise PriorRunError("the prior run is not earlier than this run")
        if prior.manifest.header.target.bucket != target_bucket:
            raise PriorRunError("the prior run was written to a different bucket")
    required = required_objects(assets)
    syncer = _Syncer(
        source,
        target,
        prior=prior,
        deep=deep,
        scratch_dir=scratch_dir,
        retry=retry,
        sleep=asyncio.sleep if sleep is None else sleep,
        clock=clock,
    )

    admitted: list[ManifestObject] = []
    failures: list[ObjectFailure] = []
    copied = inherited = verified_present = bytes_copied = 0
    streak = 0
    aborted: AbortReason | None = None
    for req in required:
        try:
            line, action, copied_bytes = await syncer.admit(req)
        except _ObjectFailed as failed:
            failures.append(ObjectFailure(req.asset_id, req.role, failed.code))
            streak = streak + 1 if failed.code in _UNAVAILABLE_CODES else 0
            if streak >= max_consecutive_unavailable:
                aborted = AbortReason.STORAGE_UNAVAILABLE
                break
            continue
        except _Abort as abort:
            aborted = abort.reason
            break
        streak = 0
        admitted.append(line)
        if action is Action.COPIED:
            copied += 1
            bytes_copied += copied_bytes
        elif line.sha_provenance == DOWNLOADED:
            verified_present += 1
        else:
            inherited += 1

    source_keys = orphan_candidates = 0
    if aborted is None:
        try:
            source_keys, orphan_candidates = await syncer.count_listing(frozenset(req.key for req in required))
        except _ObjectFailed as failed:
            failures.append(ObjectFailure(None, None, FailureCode.SOURCE_LISTING_FAILED))
            logger.warning("source listing failed (%s)", failed.code.value)
        except _Abort as abort:
            aborted = abort.reason
    counts = SyncCounts(
        copied=copied,
        inherited=inherited,
        verified_present=verified_present,
        failed=len(failures),
        bytes_copied=bytes_copied,
        objects_required=len(required),
    )
    logger.info(
        "media sync finished: required=%d copied=%d inherited=%d verified_present=%d failed=%d aborted=%s",
        len(required),
        copied,
        inherited,
        verified_present,
        len(failures),
        aborted,
    )
    return MediaSyncResult(
        run_id=run_id,
        objects=tuple(sorted(admitted, key=lambda obj: obj.key)),
        failures=tuple(failures),
        counts=counts,
        source_keys=source_keys,
        orphan_candidates=orphan_candidates,
        aborted=aborted,
    )


# --- prior run -------------------------------------------------------------------------------------


async def load_prior_run(
    target: BackupReader,
    run_id: str,
    *,
    scratch_dir: Path,
    retry: RetryPolicy = DEFAULT_RETRY,
    sleep: Sleep | None = None,
) -> VerifiedRun:
    """Download `runs/<run_id>/COMPLETE.json` and `manifest.jsonl` and verify the seal (plan §8.2.1-2).

    A run that is missing, unsealed or inconsistent is an error, never a silent "no prior run":
    the operator named it, so the difference must be visible (the caller may fall back to
    `prior=None` or `deep=True` on purpose)."""
    pause: Sleep = asyncio.sleep if sleep is None else sleep
    scratch = Path(tempfile.mkdtemp(prefix=_SCRATCH_PREFIX, dir=scratch_dir))
    try:
        blobs: list[bytes] = []
        for key in (complete_key(run_id), manifest_key(run_id)):
            path = scratch / f"blob{len(blobs)}"
            try:
                await retrying(partial(target.download_to, key, path), retry, pause, "prior run")
            except MediaObjectNotFound:
                raise PriorRunError("the prior run is missing or has no COMPLETE.json", missing=True) from None
            blobs.append(path.read_bytes())
            os.unlink(path)
        try:
            return verify_run(blobs[0], blobs[1])
        except ManifestError:
            raise PriorRunError("the prior run is not a consistent, sealed run") from None
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

