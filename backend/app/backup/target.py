"""Backup target port, verified create-only puts and run publication (Stage 14D.2F).

Contract: docs/STAGE_14D_BACKUP_RESTORE_PLAN.md §5 (layout), §6 / §16.9 (manifest,
COMPLETE.json), §8 (provenance), §10 (post-copy verification), §15 (failure /
resume). The target is the independent Oracle Object Storage bucket; this module
is provider-neutral, `app.backup.oci_target` is the OCI adapter.

The write port is deliberately tiny and has no way to destroy or alter data:

    put_new(key, source, content_type) -> CREATED | EXISTS   (create-only)
    head(key)                          -> TargetObject | None
    download_to(key, path)             -> writes a new local file

No delete, no overwrite, no multipart, no list. This mirrors the IAM the
uploader principal holds (`OBJECT_CREATE` + read / inspect only, 14D.3 §6.2).

`put_verified` is the only way this module writes an object: local SHA-256 and
size, create-only put, HEAD size, full re-download and SHA-256 comparison
(plan §10 "Post-copy"). An object that already exists is accepted only when its
downloaded bytes equal the local bytes (an idempotent retry of an ambiguous
put); different bytes raise `MediaObjectConflict` and nothing is overwritten.
Transient failures are retried with bounded exponential backoff; every other
failure is final.

`publish_run` writes one backup run in the only safe order: encrypted database
dump, then `manifest.jsonl`, then `COMPLETE.json` last, and only after the
manifest was fully validated locally. A run that stops anywhere before the
COMPLETE.json upload is incomplete by definition (plan §6) and is never cleaned
up by deleting -- there is no delete path.

Errors name keys' roles and counts, never contents or credentials.
"""

import asyncio
import enum
import hashlib
import logging
import os
import shutil
import tempfile
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Protocol, TypeVar, runtime_checkable

from app.backup.manifest import (
    ManifestHeader,
    ManifestObject,
    build_complete,
    build_manifest,
    complete_key,
    manifest_key,
    verify_run,
)
from app.domain.exceptions import (
    MediaObjectConflict,
    MediaObjectNotFound,
    MediaStorageUnavailable,
)
from app.domain.services.media_storage import validate_object_key

logger = logging.getLogger(__name__)

CHUNK_BYTES = 1024 * 1024
CONTENT_TYPE_DUMP = "application/octet-stream"
CONTENT_TYPE_MANIFEST = "application/x-ndjson"
CONTENT_TYPE_COMPLETE = "application/json"
_SCRATCH_PREFIX = "backup-target-"

T = TypeVar("T")


class BackupTargetError(RuntimeError):
    """Base class for failures that are not storage-provider errors."""


class SourceIntegrityError(BackupTargetError):
    """The local source does not match what the caller expected (size / SHA-256)."""


class TargetVerificationError(BackupTargetError):
    """An object written in this call does not verify (missing, wrong size or SHA-256)."""


class PutOutcome(enum.StrEnum):
    CREATED = "created"
    EXISTS = "exists"


@dataclass(frozen=True)
class TargetObject:
    size: int
    etag: str | None = None  # opaque, diagnostic only (plan §8)


@runtime_checkable
class BackupTarget(Protocol):
    async def put_new(self, key: str, source: Path, content_type: str) -> PutOutcome:
        """Create `key` from the local file `source`. Never overwrites: an existing key
        returns EXISTS and is left untouched."""
        ...

    async def head(self, key: str) -> TargetObject | None:
        """Object facts, or None when the key does not exist."""
        ...

    async def download_to(self, key: str, path: Path) -> None:
        """Write the object to the NEW local file `path` (MediaObjectNotFound if absent)."""
        ...


# --- bounded retries -----------------------------------------------------------------------------


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 4
    base_delay: float = 1.0
    factor: float = 2.0
    max_delay: float = 20.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1 or self.base_delay < 0 or self.factor < 1 or self.max_delay < 0:
            raise ValueError("invalid retry policy")

    def delay(self, attempt: int) -> float:
        """Seconds to wait after failed attempt number `attempt` (1-based)."""
        return min(self.max_delay, self.base_delay * self.factor ** (attempt - 1))


DEFAULT_RETRY = RetryPolicy()
Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], datetime]


def utc_now() -> datetime:
    return datetime.now(UTC)


async def _retrying(operation: Callable[[], Awaitable[T]], retry: RetryPolicy, sleep: Sleep, what: str) -> T:
    """Retry only transient storage failures; everything else propagates at once."""
    attempt = 1
    while True:
        try:
            return await operation()
        except MediaStorageUnavailable as exc:
            if attempt >= retry.max_attempts:
                raise
            logger.warning("backup target %s failed (attempt %d, code=%s); retrying", what, attempt, exc.error_code)
            await sleep(retry.delay(attempt))
            attempt += 1


# --- local file facts ----------------------------------------------------------------------------


def file_facts(path: Path) -> tuple[int, str]:
    """(size, SHA-256) of a local file, streamed."""
    digest = hashlib.sha256()
    size = 0
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_BYTES), b""):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


# --- verified create-only put ---------------------------------------------------------------------


@dataclass(frozen=True)
class VerifiedPut:
    key: str
    size: int
    sha256: str
    created: bool  # True: this call created the object; False: it already held identical bytes
    etag: str | None  # opaque, diagnostic only


async def put_verified(
    target: BackupTarget,
    *,
    key: str,
    source: Path,
    content_type: str,
    scratch_dir: Path,
    expected_sha256: str | None = None,
    expected_size: int | None = None,
    retry: RetryPolicy = DEFAULT_RETRY,
    sleep: Sleep = asyncio.sleep,
) -> VerifiedPut:
    """Create `key` from `source`, then prove by full re-download that the target holds exactly these bytes."""
    validate_object_key(key)
    size, sha256 = await asyncio.to_thread(file_facts, source)
    if size == 0:
        raise SourceIntegrityError("the local source is empty")
    if expected_size is not None and size != expected_size:
        raise SourceIntegrityError("the local source size differs from the expected size")
    if expected_sha256 is not None and sha256 != expected_sha256:
        raise SourceIntegrityError("the local source SHA-256 differs from the expected SHA-256")

    outcome = await _retrying(lambda: target.put_new(key, source, content_type), retry, sleep, "put")
    created = outcome is PutOutcome.CREATED

    facts = await _retrying(lambda: target.head(key), retry, sleep, "head")
    if facts is None:
        raise TargetVerificationError("the object is not visible in the target after the put")
    if facts.size != size:
        if created:
            raise TargetVerificationError("the stored size differs from the local size")
        raise MediaObjectConflict("the target key already holds different content")

    stored_sha256 = await _download_sha256(target, key, size, scratch_dir, retry, sleep)
    if stored_sha256 != sha256:
        if created:
            raise TargetVerificationError("the stored bytes differ from the local bytes")
        raise MediaObjectConflict("the target key already holds different content")
    return VerifiedPut(key=key, size=size, sha256=sha256, created=created, etag=facts.etag)


async def _download_sha256(
    target: BackupTarget, key: str, expected_size: int, scratch_dir: Path, retry: RetryPolicy, sleep: Sleep
) -> str:
    """Download into a private temp directory, hash, always clean up."""
    workdir = Path(await asyncio.to_thread(tempfile.mkdtemp, prefix=_SCRATCH_PREFIX, dir=scratch_dir))  # mode 0700
    try:
        path = workdir / "object"

        async def fetch() -> None:
            if path.exists():  # a failed attempt may have left a partial file
                path.unlink()
            await target.download_to(key, path)

        await _retrying(fetch, retry, sleep, "download")
        size, sha256 = await asyncio.to_thread(file_facts, path)
        if size != expected_size:
            raise TargetVerificationError("the downloaded size differs from the expected size")
        return sha256
    finally:
        await asyncio.to_thread(shutil.rmtree, workdir, True)


async def put_bytes_verified(
    target: BackupTarget,
    *,
    key: str,
    data: bytes,
    content_type: str,
    scratch_dir: Path,
    retry: RetryPolicy = DEFAULT_RETRY,
    sleep: Sleep = asyncio.sleep,
) -> VerifiedPut:
    """`put_verified` for small in-memory documents (manifest, COMPLETE.json)."""
    workdir = Path(await asyncio.to_thread(tempfile.mkdtemp, prefix=_SCRATCH_PREFIX, dir=scratch_dir))
    try:
        source = workdir / "document"
        fd = os.open(source, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        return await put_verified(
            target,
            key=key,
            source=source,
            content_type=content_type,
            scratch_dir=scratch_dir,
            expected_sha256=hashlib.sha256(data).hexdigest(),
            expected_size=len(data),
            retry=retry,
            sleep=sleep,
        )
    finally:
        await asyncio.to_thread(shutil.rmtree, workdir, True)


# --- run publication ------------------------------------------------------------------------------


@dataclass(frozen=True)
class PublishedRun:
    run_id: str
    dump_key: str
    manifest_key: str
    manifest_sha256: str
    complete_key: str
    complete_sha256: str
    objects: int
    ready_assets: int


async def publish_run(
    target: BackupTarget,
    *,
    header: ManifestHeader,
    objects: Iterable[ManifestObject],
    dump_path: Path,
    source_keys: int,
    orphan_candidates: int,
    scratch_dir: Path,
    skipped_pending: int = 0,
    skipped_failed: int = 0,
    retry: RetryPolicy = DEFAULT_RETRY,
    sleep: Sleep = asyncio.sleep,
    clock: Clock = utc_now,
) -> PublishedRun:
    """Write one complete run: dump, manifest, COMPLETE.json last.

    `objects` are the media object lines already admitted and verified in the target
    (14D.2G). Everything that can be validated locally is validated before the first
    byte is written: the dump against the header, the manifest against the plan §7
    invariants. A failure after that leaves at most an incomplete run (no COMPLETE.json).
    """
    size, sha256 = await asyncio.to_thread(file_facts, dump_path)
    if size != header.db_dump.encrypted_size or sha256 != header.db_dump.encrypted_sha256:
        raise SourceIntegrityError("the encrypted dump does not match the manifest header")
    manifest = build_manifest(
        header,
        objects,
        skipped_pending=skipped_pending,
        skipped_failed=skipped_failed,
        source_keys=source_keys,
        orphan_candidates=orphan_candidates,
    )
    manifest_bytes = manifest.to_bytes()

    await put_verified(
        target,
        key=header.db_dump.key,
        source=dump_path,
        content_type=CONTENT_TYPE_DUMP,
        scratch_dir=scratch_dir,
        expected_sha256=header.db_dump.encrypted_sha256,
        expected_size=header.db_dump.encrypted_size,
        retry=retry,
        sleep=sleep,
    )
    stored_manifest = await put_bytes_verified(
        target,
        key=manifest_key(header.run_id),
        data=manifest_bytes,
        content_type=CONTENT_TYPE_MANIFEST,
        scratch_dir=scratch_dir,
        retry=retry,
        sleep=sleep,
    )
    await _require_objects_present(target, manifest.objects, retry, sleep)
    complete = build_complete(manifest, clock())
    complete_bytes = complete.to_bytes()
    verify_run(complete_bytes, manifest_bytes)  # the seal matches the manifest that was just stored
    stored_complete = await put_bytes_verified(
        target,
        key=complete_key(header.run_id),
        data=complete_bytes,
        content_type=CONTENT_TYPE_COMPLETE,
        scratch_dir=scratch_dir,
        retry=retry,
        sleep=sleep,
    )
    return PublishedRun(
        run_id=header.run_id,
        dump_key=header.db_dump.key,
        manifest_key=stored_manifest.key,
        manifest_sha256=stored_manifest.sha256,
        complete_key=stored_complete.key,
        complete_sha256=stored_complete.sha256,
        objects=manifest.summary.objects,
        ready_assets=manifest.summary.ready_assets,
    )


async def _require_objects_present(
    target: BackupTarget, objects: tuple[ManifestObject, ...], retry: RetryPolicy, sleep: Sleep
) -> None:
    """Defence in depth before sealing: every object line must exist in the target with its recorded size.
    (The SHA-256 of each was established when the object was admitted, plan section 8.)"""
    for obj in objects:
        facts = await _retrying(partial(target.head, obj.key), retry, sleep, "head")
        if facts is None:
            raise TargetVerificationError("an object listed in the manifest is missing from the target")
        if facts.size != obj.size:
            raise TargetVerificationError("an object listed in the manifest has a different size in the target")


# --- in-memory test double -------------------------------------------------------------------------


@dataclass
class Fault:
    """Injected failure for one call. `apply_effect=True` performs the operation first and
    then raises: the ambiguous 'it was stored but the response was lost' case. `after` lets
    that many calls of the operation succeed first."""

    error: Exception
    apply_effect: bool = False
    after: int = 0


class InMemoryBackupTarget:
    """Test double with the real contract: create-only, no delete, no overwrite. Not for production."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.content_types: dict[str, str] = {}
        self.calls: list[tuple[str, str]] = []
        self._faults: dict[str, list[Fault]] = {"put_new": [], "head": [], "download_to": []}
        self.corrupt_on_store: set[str] = set()
        self.hide_after_put: set[str] = set()

    def inject(
        self, operation: str, error: Exception, *, times: int = 1, apply_effect: bool = False, after: int = 0
    ) -> None:
        # `after` delays the whole batch once: only its first fault carries it.
        self._faults[operation].extend(Fault(error, apply_effect, after if n == 0 else 0) for n in range(times))

    def _next_fault(self, operation: str) -> Fault | None:
        queue = self._faults[operation]
        if not queue:
            return None
        if queue[0].after > 0:
            queue[0].after -= 1
            return None
        return queue.pop(0)

    def _store(self, key: str, data: bytes, content_type: str) -> PutOutcome:
        if key in self.objects:
            return PutOutcome.EXISTS
        stored = bytes([data[0] ^ 0xFF]) + data[1:] if key in self.corrupt_on_store and data else data
        self.objects[key] = stored
        self.content_types[key] = content_type
        return PutOutcome.CREATED

    async def put_new(self, key: str, source: Path, content_type: str) -> PutOutcome:
        validate_object_key(key)
        self.calls.append(("put_new", key))
        fault = self._next_fault("put_new")
        if fault is not None and not fault.apply_effect:
            raise fault.error
        outcome = self._store(key, Path(source).read_bytes(), content_type)
        if fault is not None:
            raise fault.error
        return outcome

    async def head(self, key: str) -> TargetObject | None:
        validate_object_key(key)
        self.calls.append(("head", key))
        fault = self._next_fault("head")
        if fault is not None:
            raise fault.error
        if key in self.hide_after_put or key not in self.objects:
            return None
        return TargetObject(size=len(self.objects[key]), etag=f'"{hashlib.md5(self.objects[key]).hexdigest()}"')

    async def download_to(self, key: str, path: Path) -> None:
        validate_object_key(key)
        self.calls.append(("download_to", key))
        fault = self._next_fault("download_to")
        if fault is not None:
            raise fault.error
        if key not in self.objects:
            raise MediaObjectNotFound("object not found")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(self.objects[key])
