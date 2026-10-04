"""Restore the encrypted database dump of a sealed run into a scratch PostgreSQL -- Stage 14D.2I.1.

Contract: docs/STAGE_14D_BACKUP_RESTORE_PLAN.md §7 (completeness invariant), §9 (restore chain), §10 (restore
time), §11 (drill), §16.13 (this module).

`restore_database` takes a sealed run (`VerifiedRun`, from `load_prior_run`), the read side of the backup target
and an age identity, and returns a `DbRestoreReport`. Order (cheap and local first, nothing is written before the
guards pass):

    guards     scratch database (name marker, loopback / scratch host, pgpass) and identity file (private, owner
               only, holds an age secret key; it is also one of the manifest's public recipients)
    database   reachable, `current_database()` is the configured one, and EMPTY (a production database never is)
    artifact   `db/<run_id>/plan-estimate.sql.gz.age` downloaded into a private scratch directory; its size and
               SHA-256 equal the manifest's before any decryption
    load       `age --decrypt` -> gunzip (one member, CRC32 / ISIZE checked) -> `psql --single-transaction`
               with ON_ERROR_STOP. The plaintext exists only in pipes: no SQL file is written. psql receives EOF
               -- and therefore COMMITs -- only after age exited 0, the gzip member ended cleanly and the plain
               dump's completion marker was seen; on any failure psql is killed first, so nothing is committed
    checks     `alembic_version` equals the manifest's `alembic_head`; the READY set read from the restored
               database equals the manifest's (`verify_against_ready_set`: the association is proved from the
               restored data, not from the tool that wrote the backup); the PENDING / FAILED counts equal the
               manifest's `skipped`

Failures are machine-readable (`RestoreFailure`) and never carry a value: no host, key, SQL text, row content or
provider message; the report is canonical secret-free JSON. Unexpected exceptions and cancellation propagate after
the child processes were killed (psql first) and the scratch directory removed.

Roles: the plain dump keeps object owners and grants, so a role it names must exist in the scratch server
(create it before the restore; `ROLE_MISSING` names it). Nothing is created or altered outside the restored
database.
"""

import asyncio
import enum
import hashlib
import logging
import os
import re
import shutil
import tempfile
import uuid
import zlib
from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any

import asyncpg

from app.backup.manifest import (
    ManifestInvariantError,
    VerifiedRun,
    canonical_line,
    verify_against_ready_set,
)
from app.backup.pg_connection import PgConnectionConfig
from app.backup.restore_guards import (
    IdentityFileError,
    UnsafeRestoreDatabaseError,
    validate_identity_file,
    validate_restore_database,
)
from app.backup.schema_revision import (
    ExpectedHeadError,
    ObservedRevisionError,
    observed_revision_from_rows,
    resolve_expected_head,
)
from app.backup.snapshot_metadata import (
    ALEMBIC_SQL,
    STATUS_COUNTS_SQL,
    SnapshotMetadataError,
    parse_status_counts,
)
from app.backup.target import (
    DEFAULT_RETRY,
    BackupReader,
    RetryPolicy,
    Sleep,
    file_facts,
    retrying,
)
from app.core.pg_snapshot_dump import (
    DUMP_COMPLETE_MARKER,
    MARKER_SEARCH_BYTES,
    READY_INVENTORY_SQL,
)
from app.domain.exceptions import (
    MediaObjectNotFound,
    MediaStorageError,
    MediaStorageUnavailable,
)
from app.domain.services.media_backup_ready_set import (
    ReadyAsset,
    ReadySetFormatError,
    ready_set_digest,
)

logger = logging.getLogger(__name__)

REPORT_FORMAT = "plan-estimate/db-restore-report/v1"
CHUNK_BYTES = 1024 * 1024
DEFAULT_TIMEOUT_SECONDS = 4 * 3600.0
DEFAULT_MAX_PLAINTEXT_BYTES = 256 * 2**30
TOOL_TIMEOUT_SECONDS = 30.0
CONNECT_TIMEOUT_SECONDS = 30.0
KILL_WAIT_SECONDS = 15.0
STDERR_TAIL_BYTES = 8192
_SCRATCH_PREFIX = "restore-"
_ROLE_MISSING = re.compile(r'role "([A-Za-z0-9_$.-]{1,63})" does not exist')
_AGE_PUBLIC_KEY = re.compile(r"^age1[02-9ac-hj-np-z]{58}$", re.ASCII)

Connect = Callable[..., Awaitable[Any]]


class RestoreStep(enum.StrEnum):
    GUARDS = "guards"
    DATABASE = "database"
    ARTIFACT = "artifact"
    LOAD = "load"
    CHECKS = "checks"
    DONE = "done"


class RestoreFailure(enum.StrEnum):
    SCRATCH_UNSAFE = "SCRATCH_UNSAFE"  # the target database is not recognisably scratch
    IDENTITY_INVALID = "IDENTITY_INVALID"  # the identity file is unsafe, unreadable or not an age secret key
    IDENTITY_NOT_A_RECIPIENT = "IDENTITY_NOT_A_RECIPIENT"  # its public key is not among the manifest's recipients
    TOOL_UNUSABLE = "TOOL_UNUSABLE"  # age / age-keygen / psql missing or not runnable
    DATABASE_UNREACHABLE = "DATABASE_UNREACHABLE"
    DATABASE_NOT_EMPTY = "DATABASE_NOT_EMPTY"  # a restore target must be empty (the final guard against production)
    DUMP_MISSING = "DUMP_MISSING"
    DUMP_SIZE_MISMATCH = "DUMP_SIZE_MISMATCH"
    DUMP_SHA_MISMATCH = "DUMP_SHA_MISMATCH"
    STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"
    STORAGE_MISCONFIGURED = "STORAGE_MISCONFIGURED"
    DECRYPT_FAILED = "DECRYPT_FAILED"  # age exited non-zero: wrong key, corrupt or truncated ciphertext
    GZIP_INVALID = "GZIP_INVALID"  # not one clean gzip member (CRC32 / ISIZE / truncated / trailing data)
    DUMP_INCOMPLETE = "DUMP_INCOMPLETE"  # the plain dump lacks pg_dump's completion marker
    PLAINTEXT_TOO_LARGE = "PLAINTEXT_TOO_LARGE"
    PSQL_FAILED = "PSQL_FAILED"
    ROLE_MISSING = "ROLE_MISSING"  # the dump names a role the scratch server does not have
    RESTORE_TIMEOUT = "RESTORE_TIMEOUT"
    CHECKS_UNREADABLE = "CHECKS_UNREADABLE"  # the restored database could not be queried as expected
    ALEMBIC_MISMATCH = "ALEMBIC_MISMATCH"
    READY_SET_MISMATCH = "READY_SET_MISMATCH"
    STATUS_COUNTS_MISMATCH = "STATUS_COUNTS_MISMATCH"


@dataclass(frozen=True)
class DbRestoreReport:
    run_id: str
    step: RestoreStep  # the last step started (DONE after success)
    failure: RestoreFailure | None
    missing_role: str | None = None  # a role NAME (not a secret), only with ROLE_MISSING
    encrypted_bytes: int = 0
    plaintext_bytes: int = 0
    plaintext_sha256: str | None = None
    alembic_revision: str | None = None
    matches_repository_head: bool | None = None
    ready_count: int | None = None
    status_counts: dict[str, int] | None = None

    @property
    def ok(self) -> bool:
        return self.failure is None and self.step is RestoreStep.DONE

    def report_bytes(self) -> bytes:
        document: dict[str, object] = {
            "format": REPORT_FORMAT,
            "run_id": self.run_id,
            "ok": self.ok,
            "step": self.step.value,
            "failure": None if self.failure is None else self.failure.value,
            "missing_role": self.missing_role,
            "encrypted_bytes": self.encrypted_bytes,
            "plaintext_bytes": self.plaintext_bytes,
            "plaintext_sha256": self.plaintext_sha256,
            "alembic_revision": self.alembic_revision,
            "matches_repository_head": self.matches_repository_head,
            "ready_count": self.ready_count,
            "status_counts": self.status_counts,
        }
        return canonical_line(document)


# --- command lines (no secret ever appears in argv) --------------------------------------------------------


def age_public_key_argv(age_keygen_path: str, identity: Path) -> list[str]:
    return [age_keygen_path, "-y", str(identity)]


def age_decrypt_argv(age_path: str, identity: Path, artifact: Path) -> list[str]:
    return [age_path, "--decrypt", "-i", str(identity), str(artifact)]


def psql_restore_argv(psql_path: str) -> list[str]:
    """One transaction, stop at the first error, never prompt, read the script from stdin."""
    return [psql_path, "-X", "-q", "-v", "ON_ERROR_STOP=1", "--single-transaction", "--no-password", "-f", "-"]


def _tool_env() -> dict[str, str]:
    return {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C"}


# --- subprocess helpers ----------------------------------------------------------------------------------------


async def _drain(stream: asyncio.StreamReader | None) -> bytes:
    """Read a pipe to EOF keeping only the last STDERR_TAIL_BYTES (a diagnostic only, never reported)."""
    tail = b""
    if stream is None:
        return tail
    while True:
        chunk = await stream.read(65536)
        if not chunk:
            return tail
        tail = (tail + chunk)[-STDERR_TAIL_BYTES:]


async def _discard(stream: asyncio.StreamReader) -> bytes:
    """Read a pipe to EOF and throw the bytes away (it only exists to let the pipe transport close)."""
    while await stream.read(65536):
        pass
    return b""


async def _kill(proc: asyncio.subprocess.Process | None) -> None:
    if proc is None or proc.returncode is not None:
        return
    try:
        proc.kill()
    except ProcessLookupError:
        return
    try:
        await asyncio.wait_for(proc.wait(), KILL_WAIT_SECONDS)
    except TimeoutError:
        logger.warning("a child process did not exit after SIGKILL within %.0f s", KILL_WAIT_SECONDS)


async def _public_key_of(age_keygen_path: str, identity: Path) -> str | None:
    """The public key of the identity, None when the tool refuses it. FileNotFoundError / PermissionError propagate."""
    proc = await asyncio.create_subprocess_exec(
        *age_public_key_argv(age_keygen_path, identity),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
        env=_tool_env(),
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), TOOL_TIMEOUT_SECONDS)
    except BaseException:
        await _kill(proc)
        raise
    lines = [line.strip() for line in stdout.decode("ascii", "replace").splitlines() if line.strip()]
    if proc.returncode != 0 or len(lines) != 1 or not _AGE_PUBLIC_KEY.match(lines[0]):
        return None
    return lines[0]


@dataclass(frozen=True)
class _Load:
    failure: RestoreFailure | None
    missing_role: str | None = None
    plaintext_bytes: int = 0
    plaintext_sha256: str | None = None


class _Decoder:
    """Incremental gunzip with a bounded output per call; a single clean member is the only accepted input."""

    def __init__(self) -> None:
        self._decompressor = zlib.decompressobj(wbits=16 + zlib.MAX_WBITS)
        self.failure: RestoreFailure | None = None

    def feed(self, data: bytes) -> list[bytes]:
        pieces: list[bytes] = []
        while True:
            if self._decompressor.eof:
                if data:  # anything after the end of the member
                    self.failure = RestoreFailure.GZIP_INVALID
                return pieces
            try:
                out = self._decompressor.decompress(data, CHUNK_BYTES)
            except zlib.error:
                self.failure = RestoreFailure.GZIP_INVALID
                return pieces
            data = self._decompressor.unconsumed_tail
            if out:
                pieces.append(out)
            if self._decompressor.unused_data:
                self.failure = RestoreFailure.GZIP_INVALID
                return pieces
            if not out and not data:
                return pieces

    def finish(self) -> list[bytes]:
        pieces: list[bytes] = []
        try:
            out = self._decompressor.flush()
        except zlib.error:
            self.failure = RestoreFailure.GZIP_INVALID
            return pieces
        if out:
            pieces.append(out)
        if not self._decompressor.eof:
            self.failure = RestoreFailure.GZIP_INVALID  # truncated: no trailer
        return pieces


async def _load(
    *,
    age_path: str,
    psql_path: str,
    identity: Path,
    artifact: Path,
    libpq_env: dict[str, str],
    timeout_seconds: float,
    max_plaintext_bytes: int,
) -> _Load:
    """age -> gunzip -> psql, with the commit gate described in the module docstring."""
    age: asyncio.subprocess.Process | None = None
    psql: asyncio.subprocess.Process | None = None
    tasks: list[asyncio.Task[bytes]] = []
    digest = hashlib.sha256()
    total = 0
    tail = bytearray()
    failure: RestoreFailure | None = None
    try:
        try:
            age = await asyncio.create_subprocess_exec(
                *age_decrypt_argv(age_path, identity, artifact),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=_tool_env(),
            )
            psql = await asyncio.create_subprocess_exec(
                *psql_restore_argv(psql_path),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
                env={**_tool_env(), **libpq_env},
            )
        except (FileNotFoundError, PermissionError):
            return _Load(RestoreFailure.TOOL_UNUSABLE)
        assert age.stdout is not None and psql.stdin is not None
        psql_err = asyncio.ensure_future(_drain(psql.stderr))
        tasks.append(psql_err)
        tasks.append(asyncio.ensure_future(_drain(age.stderr)))
        decoder = _Decoder()
        psql_died = False

        async def feed_psql(pieces: list[bytes]) -> bool:
            """Forward plaintext to psql. False when it can take no more (it exited / closed the pipe)."""
            nonlocal total
            for piece in pieces:
                total += len(piece)
                if total > max_plaintext_bytes:
                    return False
                digest.update(piece)
                tail.extend(piece)
                del tail[:-MARKER_SEARCH_BYTES]
                if psql is None or psql.stdin is None or psql.returncode is not None:
                    return False
                try:
                    psql.stdin.write(piece)
                    await psql.stdin.drain()
                except (BrokenPipeError, ConnectionResetError):
                    return False
            return True

        async with asyncio.timeout(timeout_seconds):
            while True:
                chunk = await age.stdout.read(CHUNK_BYTES)
                if not chunk:
                    break
                alive = await feed_psql(decoder.feed(chunk))
                if decoder.failure is not None:
                    failure = decoder.failure
                    break
                if total > max_plaintext_bytes:
                    failure = RestoreFailure.PLAINTEXT_TOO_LARGE
                    break
                if not alive:
                    psql_died = True
                    break
            if failure is None and not psql_died and await age.wait() != 0:
                # age ended with an error (wrong key, tampered or truncated ciphertext): that is the root cause,
                # whatever the gzip layer makes of the short or empty stream it was left with.
                failure = RestoreFailure.DECRYPT_FAILED
            if failure is None and not psql_died:
                alive = await feed_psql(decoder.finish())
                if decoder.failure is not None:
                    failure = decoder.failure
                elif total > max_plaintext_bytes:
                    failure = RestoreFailure.PLAINTEXT_TOO_LARGE
                elif not alive:
                    psql_died = True
            if failure is None and not psql_died and DUMP_COMPLETE_MARKER not in bytes(tail):
                failure = RestoreFailure.DUMP_INCOMPLETE
            if failure is None and not psql_died:
                # Every gate passed: only now does psql see EOF, run COMMIT and exit.
                psql.stdin.close()
                await psql.wait()
                if psql.returncode != 0:
                    psql_died = True
            if psql_died:
                await _kill(psql)  # it has exited or is about to; never let it see EOF after a failure
                await _kill(age)
                return _psql_failure(await psql_err, total)
    except TimeoutError:
        return _Load(RestoreFailure.RESTORE_TIMEOUT, plaintext_bytes=total)
    finally:
        # psql first (defensive): it never gets EOF here, and a killed psql can no longer COMMIT.
        await asyncio.shield(_kill(psql))
        await asyncio.shield(_kill(age))
        # Read the dead processes' pipes to EOF so that every transport is closed before the loop can end.
        drains = list(tasks)
        if age is not None and age.stdout is not None:
            drains.append(asyncio.ensure_future(_discard(age.stdout)))
        if drains:
            _, pending = await asyncio.wait(drains, timeout=KILL_WAIT_SECONDS)
            for task in pending:
                task.cancel()
            await asyncio.gather(*drains, return_exceptions=True)
    if failure is not None:
        return _Load(failure, plaintext_bytes=total)
    return _Load(None, plaintext_bytes=total, plaintext_sha256=digest.hexdigest())


def _psql_failure(stderr_tail: bytes, total: int) -> _Load:
    """Classify psql's failure from its diagnostic tail without ever returning the tail itself."""
    match = _ROLE_MISSING.search(stderr_tail.decode("utf-8", "replace"))
    if match is not None:
        return _Load(RestoreFailure.ROLE_MISSING, missing_role=match.group(1), plaintext_bytes=total)
    return _Load(RestoreFailure.PSQL_FAILED, plaintext_bytes=total)


# --- database queries -----------------------------------------------------------------------------------------------

CURRENT_DATABASE_SQL = "SELECT current_database()"
USER_RELATIONS_SQL = (
    "SELECT count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace"
    " WHERE n.nspname NOT IN ('pg_catalog', 'information_schema', 'pg_toast')"
    " AND n.nspname NOT LIKE 'pg_temp_%' AND c.relkind IN ('r', 'p', 'v', 'm', 'S', 'f')"
)


async def _connect(connect: Connect, config: PgConnectionConfig) -> Any:
    return await connect(config.asyncpg_dsn(), timeout=CONNECT_TIMEOUT_SECONDS)


async def _close(conn: Any) -> None:
    try:
        await asyncio.wait_for(conn.close(), KILL_WAIT_SECONDS)
    except Exception as exc:  # noqa: BLE001 - closing must not mask the outcome; the connection is dropped hard
        logger.warning("restore connection close failed: %s", type(exc).__name__)
        conn.terminate()


def _ready_asset(row: Any) -> ReadyAsset:
    rid, key_o, key_d, key_t, size_o, size_d, size_t, sha256 = tuple(row)
    return ReadyAsset(
        asset_id=uuid.UUID(str(rid)),
        key_original=key_o,
        key_display=key_d,
        key_thumbnail=key_t,
        byte_size=size_o,
        display_byte_size=size_d,
        thumbnail_byte_size=size_t,
        sha256=sha256,
    )


async def restore_database(
    reader: BackupReader,
    run: VerifiedRun,
    *,
    database: PgConnectionConfig,
    identity_file: Path,
    scratch_dir: Path,
    allowed_hosts: Collection[str] = (),
    age_path: str = "age",
    age_keygen_path: str = "age-keygen",
    psql_path: str = "psql",
    connect: Connect = asyncpg.connect,
    retry: RetryPolicy = DEFAULT_RETRY,
    sleep: Sleep | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_plaintext_bytes: int = DEFAULT_MAX_PLAINTEXT_BYTES,
    repository_head: Callable[[], str] = resolve_expected_head,
) -> DbRestoreReport:
    """Restore the run's database dump into the scratch database and prove the result (module docstring)."""
    run_id = run.run_id
    header = run.manifest.header
    dump = header.db_dump
    pause: Sleep = asyncio.sleep if sleep is None else sleep

    def fail(step: RestoreStep, failure: RestoreFailure, **fields: Any) -> DbRestoreReport:
        logger.info("db restore stopped: run=%s step=%s failure=%s", run_id, step.value, failure.value)
        return DbRestoreReport(run_id, step, failure, **fields)

    # -- guards ---------------------------------------------------------------------------------------------
    try:
        validate_restore_database(database, allowed_hosts=allowed_hosts)
    except UnsafeRestoreDatabaseError:
        return fail(RestoreStep.GUARDS, RestoreFailure.SCRATCH_UNSAFE)
    try:
        validate_identity_file(identity_file)
    except IdentityFileError:
        return fail(RestoreStep.GUARDS, RestoreFailure.IDENTITY_INVALID)
    try:
        public_key = await _public_key_of(age_keygen_path, identity_file)
    except (FileNotFoundError, PermissionError):
        return fail(RestoreStep.GUARDS, RestoreFailure.TOOL_UNUSABLE)
    except TimeoutError:
        return fail(RestoreStep.GUARDS, RestoreFailure.TOOL_UNUSABLE)
    if public_key is None:
        return fail(RestoreStep.GUARDS, RestoreFailure.IDENTITY_INVALID)
    if public_key not in dump.recipients:
        return fail(RestoreStep.GUARDS, RestoreFailure.IDENTITY_NOT_A_RECIPIENT)

    # -- database preflight -------------------------------------------------------------------------------------
    try:
        conn = await _connect(connect, database)
    except (OSError, asyncpg.PostgresError, TimeoutError):
        return fail(RestoreStep.DATABASE, RestoreFailure.DATABASE_UNREACHABLE)
    try:
        current = await conn.fetchval(CURRENT_DATABASE_SQL)
        relations = await conn.fetchval(USER_RELATIONS_SQL)
    except (OSError, asyncpg.PostgresError, TimeoutError):
        return fail(RestoreStep.DATABASE, RestoreFailure.DATABASE_UNREACHABLE)
    finally:
        await _close(conn)
    if current != database.database:
        return fail(RestoreStep.DATABASE, RestoreFailure.SCRATCH_UNSAFE)
    if relations != 0:
        return fail(RestoreStep.DATABASE, RestoreFailure.DATABASE_NOT_EMPTY)

    # -- artifact -----------------------------------------------------------------------------------------------
    workdir = Path(tempfile.mkdtemp(prefix=_SCRATCH_PREFIX, dir=scratch_dir))
    try:
        artifact = workdir / "artifact.age"
        try:
            await retrying(partial(reader.download_to, dump.key, artifact), retry, pause, "dump")
        except MediaObjectNotFound:
            return fail(RestoreStep.ARTIFACT, RestoreFailure.DUMP_MISSING)
        except MediaStorageUnavailable:
            return fail(RestoreStep.ARTIFACT, RestoreFailure.STORAGE_UNAVAILABLE)
        except MediaStorageError:
            return fail(RestoreStep.ARTIFACT, RestoreFailure.STORAGE_MISCONFIGURED)
        size, sha256 = await asyncio.to_thread(file_facts, artifact)
        if size != dump.encrypted_size:
            return fail(RestoreStep.ARTIFACT, RestoreFailure.DUMP_SIZE_MISMATCH, encrypted_bytes=size)
        if sha256 != dump.encrypted_sha256:
            return fail(RestoreStep.ARTIFACT, RestoreFailure.DUMP_SHA_MISMATCH, encrypted_bytes=size)

        # -- load -----------------------------------------------------------------------------------------------
        loaded = await _load(
            age_path=age_path,
            psql_path=psql_path,
            identity=identity_file,
            artifact=artifact,
            libpq_env=database.libpq_env(),
            timeout_seconds=timeout_seconds,
            max_plaintext_bytes=max_plaintext_bytes,
        )
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    if loaded.failure is not None:
        return fail(
            RestoreStep.LOAD,
            loaded.failure,
            missing_role=loaded.missing_role,
            encrypted_bytes=size,
            plaintext_bytes=loaded.plaintext_bytes,
        )

    # -- checks -------------------------------------------------------------------------------------------------
    common: dict[str, Any] = {
        "encrypted_bytes": size,
        "plaintext_bytes": loaded.plaintext_bytes,
        "plaintext_sha256": loaded.plaintext_sha256,
    }
    try:
        conn = await _connect(connect, database)
    except (OSError, asyncpg.PostgresError, TimeoutError):
        return fail(RestoreStep.CHECKS, RestoreFailure.CHECKS_UNREADABLE, **common)
    try:
        await conn.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
        alembic_rows = await conn.fetch(ALEMBIC_SQL)
        ready_rows = await conn.fetch(READY_INVENTORY_SQL)
        status_rows = await conn.fetch(STATUS_COUNTS_SQL)
    except (OSError, asyncpg.PostgresError, TimeoutError):
        return fail(RestoreStep.CHECKS, RestoreFailure.CHECKS_UNREADABLE, **common)
    finally:
        await _close(conn)

    try:
        revision = observed_revision_from_rows([tuple(row) for row in alembic_rows])
    except ObservedRevisionError:
        return fail(RestoreStep.CHECKS, RestoreFailure.ALEMBIC_MISMATCH, **common)
    if revision != dump.alembic_head:
        return fail(RestoreStep.CHECKS, RestoreFailure.ALEMBIC_MISMATCH, alembic_revision=revision, **common)
    try:
        repo_head: str | None = repository_head()
    except ExpectedHeadError:
        repo_head = None
    matches = None if repo_head is None else repo_head == revision
    common.update(alembic_revision=revision, matches_repository_head=matches)

    try:
        assets = [_ready_asset(row) for row in ready_rows]
        digest = ready_set_digest(assets)
        verify_against_ready_set(run.manifest, assets)
    except (ReadySetFormatError, ManifestInvariantError, ValueError, TypeError):
        return fail(RestoreStep.CHECKS, RestoreFailure.READY_SET_MISMATCH, **common)
    common["ready_count"] = digest.ready_count

    try:
        counts = parse_status_counts([(row[0], row[1]) for row in status_rows])
    except SnapshotMetadataError:
        return fail(RestoreStep.CHECKS, RestoreFailure.STATUS_COUNTS_MISMATCH, **common)
    common["status_counts"] = counts
    summary = run.manifest.summary
    if (
        counts["READY"] != header.snapshot.ready_count
        or counts["PENDING"] != summary.skipped_pending
        or counts["FAILED"] != summary.skipped_failed
    ):
        return fail(RestoreStep.CHECKS, RestoreFailure.STATUS_COUNTS_MISMATCH, **common)
    return DbRestoreReport(run_id, RestoreStep.DONE, None, **common)
