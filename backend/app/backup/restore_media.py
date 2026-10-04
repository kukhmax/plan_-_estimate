"""Restore the media objects of a sealed run into a destination bucket -- Stage 14D.2I.2.

Contract: docs/STAGE_14D_BACKUP_RESTORE_PLAN.md §10 ("Restore time"), §11 steps 4-5 (drill), §12 (isolation), §16.14.

`restore_media` copies every object line of a sealed run (`VerifiedRun`) from the backup target into a destination
bucket (the drill-restore bucket in a drill) and proves each copy. It runs after the database restore (14D.2I.1),
whose READY set it requires: restore time is where "originals = DB, sizes = DB" is checked.

    guards      the destination is not a forbidden / source / backup bucket and, unless a real restore is
                explicitly allowed, a drill bucket; the manifest describes exactly the READY set read from the
                restored database (`verify_against_ready_set`); the destination holds NO object under `photos/v1/`
                that is not part of the run (a production bucket always does; a fresh or half-restored bucket never)
    per object  strictly one at a time, in canonical (key) order:
                  absent   download from the backup -> size and SHA-256 must equal the manifest's -> create-only
                           put (identical re-put is a no-op, anything else is a conflict) -> HEAD size and full
                           re-download, SHA-256 compared with the manifest
                  present  the same size AND, by download, the same SHA-256 -> `already_present` (a resumed run);
                           anything else is `DESTINATION_CONFLICT` and the object is never touched

Nothing is ever overwritten or deleted: the destination interface has no such verb and an existing object is only
read. Problems are collected per object (machine-readable code, asset id and role -- never a key, hash or provider
message); a misconfigured store or a streak of unavailable-store failures aborts the run. Unexpected exceptions and
cancellation propagate after the scratch files are removed. The report is canonical secret-free JSON.

Whether the restored bucket and database agree is then checked by the existing `scripts/media_integrity_check.py
--verify-sha256 --strict` (plan §10, §11 step 5), run by the operator against the restored database and bucket.
"""

import asyncio
import enum
import logging
import shutil
import tempfile
from collections.abc import Awaitable, Callable, Collection, Iterable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import TypeVar

from app.backup.manifest import (
    ManifestInvariantError,
    ManifestObject,
    Role,
    VerifiedRun,
    canonical_line,
    verify_against_ready_set,
)
from app.backup.restore_guards import (
    UnsafeRestoreMediaTargetError,
    validate_restore_media_target,
)
from app.backup.target import (
    DEFAULT_RETRY,
    BackupReader,
    RetryPolicy,
    Sleep,
    file_facts,
    retrying,
)
from app.domain.exceptions import (
    MediaObjectConflict,
    MediaObjectNotFound,
    MediaStorageError,
    MediaStorageUnavailable,
)
from app.domain.photos.keys import PHOTO_KEY_PREFIX
from app.domain.services.media_backup_ready_set import ReadyAsset
from app.domain.services.media_storage import MediaStorageAdmin

logger = logging.getLogger(__name__)

REPORT_FORMAT = "plan-estimate/media-restore-report/v1"
MAX_CONSECUTIVE_UNAVAILABLE = 5
MAX_LISTED_PROBLEMS = 200
_SCRATCH_PREFIX = "media-restore-"

T = TypeVar("T")


class Preflight(enum.StrEnum):
    DESTINATION_UNSAFE = "DESTINATION_UNSAFE"  # forbidden / source / backup bucket, or not a drill bucket
    MANIFEST_DB_MISMATCH = "MANIFEST_DB_MISMATCH"  # the manifest does not describe the restored database's READY set
    FOREIGN_OBJECTS_PRESENT = "FOREIGN_OBJECTS_PRESENT"  # the destination holds objects that are not part of the run
    LISTING_FAILED = "LISTING_FAILED"
    STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"
    STORAGE_MISCONFIGURED = "STORAGE_MISCONFIGURED"


class ObjectProblemCode(enum.StrEnum):
    MISSING_BACKUP_OBJECT = "MISSING_BACKUP_OBJECT"  # the manifest lists it, the backup target does not have it
    BACKUP_SIZE_MISMATCH = "BACKUP_SIZE_MISMATCH"
    BACKUP_SHA_MISMATCH = "BACKUP_SHA_MISMATCH"
    BACKUP_UNAVAILABLE = "BACKUP_UNAVAILABLE"
    DESTINATION_CONFLICT = "DESTINATION_CONFLICT"  # the destination holds other bytes under the key (never overwritten)
    DESTINATION_VERIFICATION_FAILED = "DESTINATION_VERIFICATION_FAILED"  # post-copy size / SHA-256 check failed
    DESTINATION_UNAVAILABLE = "DESTINATION_UNAVAILABLE"


class AbortReason(enum.StrEnum):
    BACKUP_MISCONFIGURED = "BACKUP_MISCONFIGURED"
    DESTINATION_MISCONFIGURED = "DESTINATION_MISCONFIGURED"
    STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"


_UNAVAILABLE = frozenset({ObjectProblemCode.BACKUP_UNAVAILABLE, ObjectProblemCode.DESTINATION_UNAVAILABLE})


@dataclass(frozen=True)
class ObjectProblem:
    asset_id: str
    role: Role
    code: ObjectProblemCode

    def to_dict(self) -> dict[str, str]:
        return {"asset_id": self.asset_id, "role": self.role.value, "code": self.code.value}


@dataclass(frozen=True)
class RestoreCounts:
    objects_total: int = 0
    restored: int = 0  # created in the destination by this run
    already_present: int = 0  # found with the right size and SHA-256 (a resumed run)
    failed: int = 0
    bytes_restored: int = 0
    foreign_objects: int = 0  # reported with FOREIGN_OBJECTS_PRESENT

    def to_dict(self) -> dict[str, int]:
        return {
            "objects_total": self.objects_total,
            "restored": self.restored,
            "already_present": self.already_present,
            "failed": self.failed,
            "bytes_restored": self.bytes_restored,
            "foreign_objects": self.foreign_objects,
        }


@dataclass(frozen=True)
class MediaRestoreReport:
    run_id: str
    preflight: Preflight | None
    object_problems: tuple[ObjectProblem, ...]
    aborted: AbortReason | None
    counts: RestoreCounts

    @property
    def ok(self) -> bool:
        return (
            self.preflight is None
            and not self.object_problems
            and self.aborted is None
            and self.counts.restored + self.counts.already_present == self.counts.objects_total
        )

    def report_bytes(self) -> bytes:
        """Canonical, secret-free one-line JSON; at most MAX_LISTED_PROBLEMS problems are listed, the totals cover all."""
        totals: dict[str, int] = {}
        for problem in self.object_problems:
            totals[problem.code.value] = totals.get(problem.code.value, 0) + 1
        listed = self.object_problems[:MAX_LISTED_PROBLEMS]
        document: dict[str, object] = {
            "format": REPORT_FORMAT,
            "run_id": self.run_id,
            "ok": self.ok,
            "preflight": None if self.preflight is None else self.preflight.value,
            "aborted": None if self.aborted is None else self.aborted.value,
            "counts": self.counts.to_dict(),
            "object_problem_totals": dict(sorted(totals.items())),
            "object_problems": [problem.to_dict() for problem in listed],
            "object_problems_omitted": len(self.object_problems) - len(listed),
        }
        return canonical_line(document)


class _Problem(Exception):
    def __init__(self, code: ObjectProblemCode) -> None:
        super().__init__(code.value)
        self.code = code


class _Abort(Exception):
    def __init__(self, reason: AbortReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


class _Restorer:
    def __init__(
        self,
        reader: BackupReader,
        destination: MediaStorageAdmin,
        *,
        scratch_dir: Path,
        verify_destination: bool,
        retry: RetryPolicy,
        sleep: Sleep,
    ) -> None:
        self.reader = reader
        self.destination = destination
        self.scratch_dir = scratch_dir
        self.verify_destination = verify_destination
        self.retry = retry
        self.sleep = sleep

    async def _backup(self, operation: Callable[[], Awaitable[T]], what: str) -> T:
        try:
            return await retrying(operation, self.retry, self.sleep, what)
        except MediaObjectNotFound:
            raise _Problem(ObjectProblemCode.MISSING_BACKUP_OBJECT) from None
        except MediaStorageUnavailable:
            raise _Problem(ObjectProblemCode.BACKUP_UNAVAILABLE) from None
        except MediaStorageError:
            raise _Abort(AbortReason.BACKUP_MISCONFIGURED) from None

    async def _destination(self, operation: Callable[[], Awaitable[T]], what: str) -> T:
        try:
            return await retrying(operation, self.retry, self.sleep, what)
        except MediaObjectConflict:
            raise _Problem(ObjectProblemCode.DESTINATION_CONFLICT) from None
        except MediaObjectNotFound:
            raise _Problem(ObjectProblemCode.DESTINATION_VERIFICATION_FAILED) from None
        except MediaStorageUnavailable:
            raise _Problem(ObjectProblemCode.DESTINATION_UNAVAILABLE) from None
        except MediaStorageError:
            raise _Abort(AbortReason.DESTINATION_MISCONFIGURED) from None

    async def _destination_facts(self, key: str, workdir: Path, name: str) -> tuple[int, str]:
        path = workdir / name
        await self._destination(partial(self.destination.download_to, key, path), "destination download")
        return await asyncio.to_thread(file_facts, path)

    async def restore_one(self, obj: ManifestObject) -> int:
        """Restore one object; returns the bytes created in the destination (0 if it was already there)."""
        head = await self._destination(partial(self.destination.head_object, obj.key), "destination head")
        workdir = Path(tempfile.mkdtemp(prefix=_SCRATCH_PREFIX, dir=self.scratch_dir))
        try:
            if head is not None:
                if head.size != obj.size:
                    raise _Problem(ObjectProblemCode.DESTINATION_CONFLICT)
                size, sha256 = await self._destination_facts(obj.key, workdir, "existing")
                if size != obj.size or sha256 != obj.sha256:
                    raise _Problem(ObjectProblemCode.DESTINATION_CONFLICT)
                return 0
            source = workdir / "backup"
            await self._backup(partial(self.reader.download_to, obj.key, source), "backup download")
            size, sha256 = await asyncio.to_thread(file_facts, source)
            if size != obj.size:
                raise _Problem(ObjectProblemCode.BACKUP_SIZE_MISMATCH)
            if sha256 != obj.sha256:
                raise _Problem(ObjectProblemCode.BACKUP_SHA_MISMATCH)
            await self._destination(partial(self.destination.put_object, obj.key, source, obj.content_type), "put")
            stored = await self._destination(partial(self.destination.head_object, obj.key), "destination head")
            if stored is None or stored.size != obj.size:
                raise _Problem(ObjectProblemCode.DESTINATION_VERIFICATION_FAILED)
            if self.verify_destination:
                size, sha256 = await self._destination_facts(obj.key, workdir, "stored")
                if size != obj.size or sha256 != obj.sha256:
                    raise _Problem(ObjectProblemCode.DESTINATION_VERIFICATION_FAILED)
            return obj.size
        finally:
            shutil.rmtree(workdir, ignore_errors=True)


async def restore_media(
    reader: BackupReader,
    run: VerifiedRun,
    destination: MediaStorageAdmin,
    *,
    destination_bucket: str,
    forbidden_buckets: Collection[str],
    ready_assets: Iterable[ReadyAsset],
    scratch_dir: Path,
    allow_non_drill: bool = False,
    allow_foreign_objects: bool = False,
    verify_destination: bool = True,
    retry: RetryPolicy = DEFAULT_RETRY,
    sleep: Sleep | None = None,
    max_consecutive_unavailable: int = MAX_CONSECUTIVE_UNAVAILABLE,
) -> MediaRestoreReport:
    """Restore every object of `run` into `destination` and report exactly what happened (module docstring).

    `ready_assets` is the READY set read from the RESTORED database (14D.2I.1); `destination_bucket` is the name of
    the bucket `destination` writes to (the adapter cannot be asked, so the caller states it and the guard checks it).
    """
    if max_consecutive_unavailable < 1:
        raise ValueError("max_consecutive_unavailable must be at least 1")
    header = run.manifest.header
    objects = tuple(sorted(run.manifest.objects, key=lambda obj: obj.key))
    total = RestoreCounts(objects_total=len(objects))

    def stopped(preflight: Preflight, **counts: int) -> MediaRestoreReport:
        logger.info("media restore stopped: run=%s preflight=%s", run.run_id, preflight.value)
        return MediaRestoreReport(run.run_id, preflight, (), None, RestoreCounts(objects_total=len(objects), **counts))

    # -- guards ---------------------------------------------------------------------------------------------
    try:
        validate_restore_media_target(
            destination_bucket,
            forbidden_buckets={*forbidden_buckets, header.source.bucket, header.target.bucket},
            allow_non_drill=allow_non_drill,
        )
    except UnsafeRestoreMediaTargetError:
        return stopped(Preflight.DESTINATION_UNSAFE)
    try:
        verify_against_ready_set(run.manifest, ready_assets)
    except ManifestInvariantError:
        return stopped(Preflight.MANIFEST_DB_MISMATCH)

    pause: Sleep = asyncio.sleep if sleep is None else sleep
    restorer = _Restorer(
        reader, destination, scratch_dir=scratch_dir, verify_destination=verify_destination, retry=retry, sleep=pause
    )
    wanted = frozenset(obj.key for obj in objects)

    async def foreign_objects() -> int:
        count = 0
        async for key in destination.iter_keys(PHOTO_KEY_PREFIX):
            if key not in wanted:
                count += 1
        return count

    try:
        foreign = await retrying(foreign_objects, retry, pause, "destination listing")
    except MediaStorageUnavailable:
        return stopped(Preflight.STORAGE_UNAVAILABLE)
    except MediaStorageError:
        return stopped(Preflight.STORAGE_MISCONFIGURED)
    if foreign and not allow_foreign_objects:
        return stopped(Preflight.FOREIGN_OBJECTS_PRESENT, foreign_objects=foreign)

    # -- objects --------------------------------------------------------------------------------------------
    problems: list[ObjectProblem] = []
    restored = present = bytes_restored = streak = 0
    aborted: AbortReason | None = None
    for obj in objects:
        try:
            created = await restorer.restore_one(obj)
        except _Problem as problem:
            problems.append(ObjectProblem(obj.asset_id, obj.role, problem.code))
            streak = streak + 1 if problem.code in _UNAVAILABLE else 0
            if streak >= max_consecutive_unavailable:
                aborted = AbortReason.STORAGE_UNAVAILABLE
                break
            continue
        except _Abort as abort:
            aborted = abort.reason
            break
        streak = 0
        if created:
            restored += 1
            bytes_restored += created
        else:
            present += 1
    counts = RestoreCounts(
        objects_total=total.objects_total,
        restored=restored,
        already_present=present,
        failed=len(problems),
        bytes_restored=bytes_restored,
        foreign_objects=foreign,
    )
    logger.info(
        "media restore finished: run=%s objects=%d restored=%d present=%d failed=%d aborted=%s",
        run.run_id,
        len(objects),
        restored,
        present,
        len(problems),
        aborted,
    )
    return MediaRestoreReport(run.run_id, None, tuple(problems), aborted, counts)
