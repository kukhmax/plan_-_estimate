"""Verify a sealed backup run in the target -- Stage 14D.2H.

Contract: docs/STAGE_14D_BACKUP_RESTORE_PLAN.md §6 (manifest, COMPLETE.json), §9 (encrypted chain), §10
(integrity model), §16.12 (this module).

`verify_run_in_target` proves, from the stored bytes alone, that a run in the backup target is what its
COMPLETE.json says it is. It needs no secret and no database: a private age identity and a scratch PostgreSQL
are restore concerns (14D.2I), where the dump is decrypted and the READY-set digest is recomputed from the
restored database.

    seal       `runs/<run_id>/COMPLETE.json` and `manifest.jsonl` exist and `verify_run` accepts them (the
               seal records the manifest's SHA-256; counts and digests agree; the run id is the one asked for)
    recipients (optional) every public age recipient the caller expects is among the manifest's recipients
    dump       `db/<run_id>/plan-estimate.sql.gz.age` exists with the recorded size; FULL also re-hashes it
    objects    every object line of the manifest exists with the recorded size; FULL also downloads it and
               compares its SHA-256 with the manifest. Never trusts provenance: `inherited:<run>` lines are
               checked like any other when FULL is requested.

QUICK reads two small documents and one HEAD per object; FULL reads every byte. Ordinary operation is one
object at a time. Every problem is a machine-readable code tied to an asset id and role (or to the run),
never a key, hash or provider message, so the report can be stored and shown. A misconfigured store or a
streak of unavailable-store failures aborts the run of checks (`AbortReason`). Unexpected exceptions propagate.

The module only reads: `BackupReader` has `head` and `download_to`, nothing that writes, overwrites or deletes.
"""

import asyncio
import enum
import logging
import shutil
import tempfile
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import TypeVar

from app.backup.manifest import (
    DOWNLOADED,
    ManifestError,
    ManifestObject,
    Role,
    VerifiedRun,
    canonical_line,
    complete_key,
    format_timestamp,
    manifest_key,
    verify_run,
)
from app.backup.run_id import validate_run_id
from app.backup.target import (
    DEFAULT_RETRY,
    BackupReader,
    Clock,
    RetryPolicy,
    Sleep,
    file_facts,
    retrying,
    utc_now,
)
from app.core.db_dump_encryption import parse_age_recipients
from app.domain.exceptions import (
    MediaObjectNotFound,
    MediaStorageError,
    MediaStorageUnavailable,
)

logger = logging.getLogger(__name__)

REPORT_FORMAT = "plan-estimate/verify-report/v1"
MAX_CONSECUTIVE_UNAVAILABLE = 5
MAX_LISTED_PROBLEMS = 200
_SCRATCH_PREFIX = "verify-"

T = TypeVar("T")


class VerifyMode(enum.StrEnum):
    QUICK = "quick"  # seal, dump size, object existence and size
    FULL = "full"  # additionally SHA-256 of the dump and of every object


class RunProblem(enum.StrEnum):
    SEAL_MISSING = "SEAL_MISSING"  # no COMPLETE.json: the run is incomplete by definition (plan §6)
    MANIFEST_MISSING = "MANIFEST_MISSING"
    SEAL_INVALID = "SEAL_INVALID"  # the seal does not match the manifest, or the manifest is inconsistent
    RECIPIENTS_MISMATCH = "RECIPIENTS_MISMATCH"  # an expected public recipient is not among the manifest's
    DUMP_MISSING = "DUMP_MISSING"
    DUMP_SIZE_MISMATCH = "DUMP_SIZE_MISMATCH"
    DUMP_SHA_MISMATCH = "DUMP_SHA_MISMATCH"


class ObjectProblemCode(enum.StrEnum):
    MISSING_OBJECT = "MISSING_OBJECT"
    SIZE_MISMATCH = "SIZE_MISMATCH"
    SHA_MISMATCH = "SHA_MISMATCH"
    UNAVAILABLE = "UNAVAILABLE"  # transient failure persisted through all retries


class AbortReason(enum.StrEnum):
    STORAGE_MISCONFIGURED = "STORAGE_MISCONFIGURED"
    STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"


@dataclass(frozen=True)
class ObjectProblem:
    asset_id: str
    role: Role
    code: ObjectProblemCode

    def to_dict(self) -> dict[str, str]:
        return {"asset_id": self.asset_id, "role": self.role.value, "code": self.code.value}


@dataclass(frozen=True)
class VerifyCounts:
    objects_total: int = 0
    size_checked: int = 0
    sha_checked: int = 0
    bytes_hashed: int = 0
    inherited_lines: int = 0  # object lines whose SHA-256 the manifest inherited (informational)
    downloaded_lines: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "objects_total": self.objects_total,
            "size_checked": self.size_checked,
            "sha_checked": self.sha_checked,
            "bytes_hashed": self.bytes_hashed,
            "inherited_lines": self.inherited_lines,
            "downloaded_lines": self.downloaded_lines,
        }


@dataclass(frozen=True)
class VerifyReport:
    run_id: str
    mode: VerifyMode
    verified_at: str
    run_problems: tuple[RunProblem, ...]
    object_problems: tuple[ObjectProblem, ...]
    aborted: AbortReason | None
    counts: VerifyCounts
    dump_checked: str  # "none" | "size" | "sha256"

    @property
    def ok(self) -> bool:
        return not self.run_problems and not self.object_problems and self.aborted is None

    def report_bytes(self) -> bytes:
        """Canonical, secret-free one-line JSON. At most MAX_LISTED_PROBLEMS object problems are listed; the
        per-code totals always cover all of them."""
        totals: dict[str, int] = {}
        for problem in self.object_problems:
            totals[problem.code.value] = totals.get(problem.code.value, 0) + 1
        listed = self.object_problems[:MAX_LISTED_PROBLEMS]
        document: dict[str, object] = {
            "format": REPORT_FORMAT,
            "run_id": self.run_id,
            "mode": self.mode.value,
            "verified_at": self.verified_at,
            "ok": self.ok,
            "aborted": None if self.aborted is None else self.aborted.value,
            "run_problems": [problem.value for problem in self.run_problems],
            "dump_checked": self.dump_checked,
            "counts": self.counts.to_dict(),
            "object_problem_totals": dict(sorted(totals.items())),
            "object_problems": [problem.to_dict() for problem in listed],
            "object_problems_omitted": len(self.object_problems) - len(listed),
        }
        return canonical_line(document)


class _Abort(Exception):
    def __init__(self, reason: AbortReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


class _Verifier:
    def __init__(self, reader: BackupReader, mode: VerifyMode, scratch_dir: Path, retry: RetryPolicy, sleep: Sleep) -> None:
        self.reader = reader
        self.mode = mode
        self.scratch_dir = scratch_dir
        self.retry = retry
        self.sleep = sleep

    async def call(self, operation: Callable[[], Awaitable[T]], what: str) -> T:
        """Retry transient failures; a persistent one is `MediaStorageUnavailable`, a configuration one aborts."""
        try:
            return await retrying(operation, self.retry, self.sleep, what)
        except (MediaObjectNotFound, MediaStorageUnavailable):
            raise
        except MediaStorageError:
            raise _Abort(AbortReason.STORAGE_MISCONFIGURED) from None

    async def read_document(self, key: str) -> bytes | None:
        """The bytes of a small document, None when it does not exist."""
        workdir = Path(tempfile.mkdtemp(prefix=_SCRATCH_PREFIX, dir=self.scratch_dir))
        try:
            path = workdir / "document"
            try:
                await self.call(partial(self.reader.download_to, key, path), "document")
            except MediaObjectNotFound:
                return None
            except MediaStorageUnavailable:
                raise _Abort(AbortReason.STORAGE_UNAVAILABLE) from None
            return path.read_bytes()
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    async def hash_object(self, key: str) -> tuple[int, str] | None:
        """(size, SHA-256) of the stored object, None if it does not exist. Unavailable propagates."""
        workdir = Path(tempfile.mkdtemp(prefix=_SCRATCH_PREFIX, dir=self.scratch_dir))
        try:
            path = workdir / "object"
            try:
                await self.call(partial(self.reader.download_to, key, path), "download")
            except MediaObjectNotFound:
                return None
            return await asyncio.to_thread(file_facts, path)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    async def check_object(self, obj: ManifestObject) -> tuple[ObjectProblemCode | None, int]:
        """(problem or None, bytes hashed)."""
        try:
            head = await self.call(partial(self.reader.head, obj.key), "head")
            if head is None:
                return ObjectProblemCode.MISSING_OBJECT, 0
            if head.size != obj.size:
                return ObjectProblemCode.SIZE_MISMATCH, 0
            if self.mode is VerifyMode.QUICK:
                return None, 0
            facts = await self.hash_object(obj.key)
        except MediaStorageUnavailable:
            return ObjectProblemCode.UNAVAILABLE, 0
        if facts is None:
            return ObjectProblemCode.MISSING_OBJECT, 0
        size, sha256 = facts
        if size != obj.size:
            return ObjectProblemCode.SIZE_MISMATCH, 0
        if sha256 != obj.sha256:
            return ObjectProblemCode.SHA_MISMATCH, size
        return None, size

    async def check_dump(self, run: VerifiedRun) -> tuple[RunProblem | None, str]:
        """(problem or None, how far the dump was checked)."""
        dump = run.manifest.header.db_dump
        try:
            head = await self.call(partial(self.reader.head, dump.key), "head dump")
            if head is None:
                return RunProblem.DUMP_MISSING, "none"
            if head.size != dump.encrypted_size:
                return RunProblem.DUMP_SIZE_MISMATCH, "size"
            if self.mode is VerifyMode.QUICK:
                return None, "size"
            facts = await self.hash_object(dump.key)
        except MediaStorageUnavailable:
            raise _Abort(AbortReason.STORAGE_UNAVAILABLE) from None
        if facts is None:
            return RunProblem.DUMP_MISSING, "none"
        size, sha256 = facts
        if size != dump.encrypted_size:
            return RunProblem.DUMP_SIZE_MISMATCH, "size"
        if sha256 != dump.encrypted_sha256:
            return RunProblem.DUMP_SHA_MISMATCH, "sha256"
        return None, "sha256"


async def verify_run_in_target(
    reader: BackupReader,
    run_id: str,
    *,
    scratch_dir: Path,
    mode: VerifyMode = VerifyMode.FULL,
    expected_recipients: Iterable[str] = (),
    retry: RetryPolicy = DEFAULT_RETRY,
    sleep: Sleep | None = None,
    clock: Clock = utc_now,
    max_consecutive_unavailable: int = MAX_CONSECUTIVE_UNAVAILABLE,
) -> VerifyReport:
    """Check one run in the backup target and report exactly what was found."""
    validate_run_id(run_id)
    if max_consecutive_unavailable < 1:
        raise ValueError("max_consecutive_unavailable must be at least 1")
    expected = tuple(expected_recipients)
    wanted = parse_age_recipients(expected) if expected else ()
    verifier = _Verifier(reader, mode, scratch_dir, retry, asyncio.sleep if sleep is None else sleep)
    verified_at = format_timestamp(clock())

    def report(
        problems: list[RunProblem],
        objects: list[ObjectProblem],
        aborted: AbortReason | None,
        counts: VerifyCounts,
        dump_checked: str,
    ) -> VerifyReport:
        return VerifyReport(run_id, mode, verified_at, tuple(problems), tuple(objects), aborted, counts, dump_checked)

    # -- seal ---------------------------------------------------------------------------------------
    try:
        complete_bytes = await verifier.read_document(complete_key(run_id))
        if complete_bytes is None:
            return report([RunProblem.SEAL_MISSING], [], None, VerifyCounts(), "none")
        manifest_bytes = await verifier.read_document(manifest_key(run_id))
        if manifest_bytes is None:
            return report([RunProblem.MANIFEST_MISSING], [], None, VerifyCounts(), "none")
    except _Abort as abort:
        return report([], [], abort.reason, VerifyCounts(), "none")
    try:
        run = verify_run(complete_bytes, manifest_bytes)
    except ManifestError:
        return report([RunProblem.SEAL_INVALID], [], None, VerifyCounts(), "none")
    if run.run_id != run_id:
        return report([RunProblem.SEAL_INVALID], [], None, VerifyCounts(), "none")

    problems: list[RunProblem] = []
    if wanted and not set(wanted) <= set(run.manifest.header.db_dump.recipients):
        problems.append(RunProblem.RECIPIENTS_MISMATCH)

    objects = run.manifest.objects
    inherited = sum(1 for obj in objects if obj.sha_provenance != DOWNLOADED)
    base = VerifyCounts(objects_total=len(objects), inherited_lines=inherited, downloaded_lines=len(objects) - inherited)

    # -- dump ---------------------------------------------------------------------------------------
    try:
        dump_problem, dump_checked = await verifier.check_dump(run)
    except _Abort as abort:
        return report(problems, [], abort.reason, base, "none")
    if dump_problem is not None:
        problems.append(dump_problem)

    # -- objects ------------------------------------------------------------------------------------
    found: list[ObjectProblem] = []
    size_checked = sha_checked = bytes_hashed = streak = 0
    aborted: AbortReason | None = None
    for obj in objects:
        try:
            code, hashed = await verifier.check_object(obj)
        except _Abort as abort:
            aborted = abort.reason
            break
        if code is not None:
            found.append(ObjectProblem(obj.asset_id, obj.role, code))
        if code is ObjectProblemCode.UNAVAILABLE:
            streak += 1
            if streak >= max_consecutive_unavailable:
                aborted = AbortReason.STORAGE_UNAVAILABLE
                break
            continue
        streak = 0
        if code is not ObjectProblemCode.MISSING_OBJECT:
            size_checked += 1
        if mode is VerifyMode.FULL and code in (None, ObjectProblemCode.SHA_MISMATCH):
            sha_checked += 1
            bytes_hashed += hashed
    counts = VerifyCounts(
        objects_total=len(objects),
        size_checked=size_checked,
        sha_checked=sha_checked,
        bytes_hashed=bytes_hashed,
        inherited_lines=inherited,
        downloaded_lines=len(objects) - inherited,
    )
    result = report(problems, found, aborted, counts, dump_checked)
    logger.info(
        "verify finished: run=%s mode=%s objects=%d problems=%d run_problems=%d aborted=%s",
        run_id,
        mode.value,
        len(objects),
        len(found),
        len(problems),
        aborted,
    )
    return result
