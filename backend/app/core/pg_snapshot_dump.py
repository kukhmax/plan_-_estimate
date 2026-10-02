"""Snapshot-bound PostgreSQL dump + READY inventory (Stage 14D.2A).

`docs/STAGE_14D_BACKUP_RESTORE_PLAN.md` §7. One exporter transaction makes
the READY photo-asset inventory and the `pg_dump` output describe the SAME
database state:

1. a dedicated asyncpg connection (never a pooled application connection),
   opened with `idle_in_transaction_session_timeout=0` for its session (it is
   closed afterwards), runs `BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY`;
2. its first statement is `SELECT pg_export_snapshot()`, which fixes the
   transaction snapshot and exports it;
3. the READY inventory is read in that same transaction (same snapshot) and
   reduced to `ready_count` / `ready_set_sha256`;
4. `pg_dump --snapshot=<id>` runs while the exporter transaction is still open;
5. only after `pg_dump` has EXITED is the exporter rolled back and closed.

Lifetime rule (PostgreSQL): an exported snapshot can be imported only until
the exporting transaction ends; a transaction that has already imported it
keeps it afterwards. `pg_dump` imports it in its own setup (and every
parallel worker would import it again), and that moment is not observable
from outside, so the exporter is held until `pg_dump` exits -- never shorter.

`pg_dump` must come from the PostgreSQL toolchain matching the server (in
production: the postgres container, via `docker exec`); its major version is
checked against the server before the snapshot is exported. Its sessions are
tagged with `PGAPPNAME`, so on failure, timeout or cancellation the
server-side backend can be terminated even when the local process is only a
`docker exec` client. The dump is written to `<output>.partial` (mode 0600,
independent of the umask; the final file keeps that mode) and renamed
only after a zero exit status and the plain-format completion marker; a
partial file is never left behind and never treated as a dump.

No credential is logged: the DSN is passed only to asyncpg.
"""

import asyncio
import hashlib
import logging
import os
import re
import secrets
import uuid
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

import asyncpg

from app.domain.services.media_backup_ready_set import ReadyAsset, ReadySetDigest, ready_set_digest

logger = logging.getLogger(__name__)

READY_INVENTORY_SQL = (
    "SELECT id, storage_key_original, storage_key_display, storage_key_thumbnail,"
    " byte_size, display_byte_size, thumbnail_byte_size, sha256"
    " FROM photo_assets WHERE status = 'READY'"
)
DUMP_COMPLETE_MARKER = b"-- PostgreSQL database dump complete"
MARKER_SEARCH_BYTES = 4096
STDERR_TAIL_CHARS = 2000
CLEANUP_TIMEOUT_SECONDS = 15.0
# A plain dump can contain personal / business data: owner read-write only,
# whatever the process umask is.
DUMP_FILE_MODE = 0o600
# The exporter is idle in transaction while pg_dump uses the snapshot; a
# non-zero server default must not end that transaction early.
EXPORTER_SERVER_SETTINGS = {"idle_in_transaction_session_timeout": "0"}

_SNAPSHOT_ID = re.compile(r"^[0-9A-F]+-[0-9A-F]+-[0-9]+$")
_PG_DUMP_VERSION = re.compile(r"\(PostgreSQL\)\s+(\d+)(?:\.(\d+))?")
_TAG = re.compile(r"^[a-z0-9-]{8,48}$")


class SnapshotDumpError(RuntimeError):
    """The snapshot-bound dump did not complete; no dump file was produced."""


class PgDumpFailedError(SnapshotDumpError):
    def __init__(self, message: str, *, returncode: int | None, stderr_tail: str) -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stderr_tail = stderr_tail


class PgDumpTimeoutError(SnapshotDumpError):
    pass


class PgDumpVersionMismatchError(SnapshotDumpError):
    pass


@dataclass(frozen=True)
class PgDumpCommand:
    """How to invoke the server-matching `pg_dump` (plain SQL format).

    `prefix` runs the tool where it lives, e.g. `("docker", "exec", "-i",
    "plan_estimate_postgres")`; empty means a local binary. The connection
    uses the tool's own environment (container socket), never a password in
    argv."""

    prefix: tuple[str, ...]
    username: str
    dbname: str
    lock_wait_timeout_ms: int | None = None

    def version_argv(self) -> list[str]:
        return [*self.prefix, "pg_dump", "--version"]

    def dump_argv(self, snapshot_id: str, application_name: str) -> list[str]:
        if not _SNAPSHOT_ID.match(snapshot_id):
            raise SnapshotDumpError("refusing an unexpected snapshot identifier")
        if not _TAG.match(application_name):
            raise SnapshotDumpError("refusing an unexpected application name")
        argv = [
            *self.prefix,
            "env",
            f"PGAPPNAME={application_name}",
            "pg_dump",
            "--format=plain",
            "--no-password",
            f"--snapshot={snapshot_id}",
            f"--username={self.username}",
            f"--dbname={self.dbname}",
        ]
        if self.lock_wait_timeout_ms is not None:
            argv.append(f"--lock-wait-timeout={int(self.lock_wait_timeout_ms)}")
        return argv


@dataclass(frozen=True)
class SnapshotDumpResult:
    snapshot_id: str
    ready: ReadySetDigest
    server_major_version: int
    dump_path: Path
    dump_size: int
    dump_sha256: str


def parse_pg_dump_major(version_output: str) -> int:
    match = _PG_DUMP_VERSION.search(version_output)
    if match is None:
        raise PgDumpVersionMismatchError("cannot parse the pg_dump version")
    return int(match.group(1))


def _tail(stderr: bytes) -> str:
    return stderr.decode("utf-8", errors="replace")[-STDERR_TAIL_CHARS:]


async def _reap(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is None:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        await proc.wait()


async def pg_dump_major_version(command: PgDumpCommand, timeout_seconds: float = 30.0) -> int:
    proc = await asyncio.create_subprocess_exec(
        *command.version_argv(),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        async with asyncio.timeout(timeout_seconds):
            stdout, stderr = await proc.communicate()
    except BaseException:
        await asyncio.shield(_reap(proc))
        raise
    if proc.returncode != 0:
        raise PgDumpFailedError("pg_dump --version failed", returncode=proc.returncode, stderr_tail=_tail(stderr))
    return parse_pg_dump_major(stdout.decode("utf-8", errors="replace"))


def _open_private_exclusive(path: Path) -> BinaryIO:
    """Create `path` exclusively with mode 0600 regardless of the umask
    (O_EXCL keeps the refuse-to-overwrite semantics; fchmod corrects any bit
    the umask removed). The file is never visible with a wider mode."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, DUMP_FILE_MODE)
    try:
        os.fchmod(fd, DUMP_FILE_MODE)
        return os.fdopen(fd, "wb")
    except BaseException:
        os.close(fd)
        raise


async def run_dump_process(argv: Sequence[str], output_path: Path, timeout_seconds: float) -> None:
    """Run `argv` with stdout into `<output>.partial`; rename to `output_path`
    only on exit status 0 and a present completion marker. On any failure,
    timeout or cancellation the child is killed and reaped and the partial
    file removed before the exception propagates."""
    output_path = Path(output_path)
    partial = output_path.with_name(output_path.name + ".partial")
    if output_path.exists() or partial.exists():
        raise SnapshotDumpError("refusing to overwrite an existing dump file")
    proc: asyncio.subprocess.Process | None = None
    try:
        with _open_private_exclusive(partial) as out:
            proc = await asyncio.create_subprocess_exec(
                *argv, stdin=asyncio.subprocess.DEVNULL, stdout=out, stderr=asyncio.subprocess.PIPE
            )
            try:
                async with asyncio.timeout(timeout_seconds):
                    _, stderr = await proc.communicate()
            except TimeoutError:
                raise PgDumpTimeoutError(f"pg_dump did not finish within {timeout_seconds} s") from None
        if proc.returncode != 0:
            raise PgDumpFailedError(
                f"pg_dump exited with status {proc.returncode}", returncode=proc.returncode, stderr_tail=_tail(stderr)
            )
        size = partial.stat().st_size
        with open(partial, "rb") as fh:
            fh.seek(max(0, size - MARKER_SEARCH_BYTES))
            tail = fh.read()
        if size == 0 or DUMP_COMPLETE_MARKER not in tail:
            raise PgDumpFailedError("pg_dump output lacks the completion marker", returncode=0, stderr_tail="")
        os.replace(partial, output_path)
    except BaseException:
        if proc is not None:
            await asyncio.shield(_reap(proc))
        partial.unlink(missing_ok=True)
        raise


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def _terminate_tagged(conn: asyncpg.Connection, application_name: str) -> None:
    """Terminate server backends of the tagged pg_dump (a killed `docker exec`
    client does not stop the process inside the container)."""
    await conn.fetch(
        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
        " WHERE application_name = $1 AND pid <> pg_backend_pid()",
        application_name,
    )


async def _cleanup(conn: asyncpg.Connection, dump_app: str | None) -> None:
    try:
        async with asyncio.timeout(CLEANUP_TIMEOUT_SECONDS):
            if dump_app is not None:
                await _terminate_tagged(conn, dump_app)
            if conn.is_in_transaction():
                await conn.execute("ROLLBACK")
            await conn.close()
    except Exception as exc:  # cleanup must not mask the original outcome; logged, then hard-closed
        logger.warning("snapshot exporter cleanup failed: %s", type(exc).__name__)
        conn.terminate()


async def snapshot_bound_dump(
    dsn: str,
    command: PgDumpCommand,
    output_path: Path,
    *,
    timeout_seconds: float = 3600.0,
    session_tag: str | None = None,
    after_export: Callable[[str], Awaitable[None]] | None = None,
) -> SnapshotDumpResult:
    """Export one snapshot, read the READY set from it, dump it with
    `pg_dump --snapshot`, then release the exporter. `after_export` is an
    observation seam (tests use it to commit concurrent changes between the
    export and the reads); it receives the snapshot id."""
    tag = session_tag or f"pe-snapshot-{secrets.token_hex(6)}"
    if not _TAG.match(tag) or len(tag) > 40:
        raise SnapshotDumpError("invalid session tag")
    exporter_app, dump_app = f"{tag}-exp", f"{tag}-dump"
    output_path = Path(output_path)
    if output_path.exists():
        raise SnapshotDumpError("refusing to overwrite an existing dump file")

    conn = await asyncpg.connect(
        dsn, server_settings={"application_name": exporter_app, **EXPORTER_SERVER_SETTINGS}
    )
    dump_started = False
    try:
        server_major = int(await conn.fetchval("SHOW server_version_num")) // 10000
        tool_major = await pg_dump_major_version(command)
        if tool_major != server_major:
            raise PgDumpVersionMismatchError(
                f"pg_dump major version {tool_major} does not match server major version {server_major}"
            )

        await conn.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
        snapshot_id = await conn.fetchval("SELECT pg_export_snapshot()")
        isolation, read_only, idle_timeout = await conn.fetchrow(
            "SELECT current_setting('transaction_isolation'), current_setting('transaction_read_only'),"
            " current_setting('idle_in_transaction_session_timeout')"
        )
        if isolation != "repeatable read" or read_only != "on":
            raise SnapshotDumpError("exporter transaction is not REPEATABLE READ READ ONLY")
        if idle_timeout != "0":
            raise SnapshotDumpError("exporter idle_in_transaction_session_timeout is not disabled")
        if after_export is not None:
            await after_export(snapshot_id)

        rows = await conn.fetch(READY_INVENTORY_SQL)
        ready = ready_set_digest(
            ReadyAsset(
                asset_id=uuid.UUID(str(row["id"])),
                key_original=row["storage_key_original"],
                key_display=row["storage_key_display"],
                key_thumbnail=row["storage_key_thumbnail"],
                byte_size=row["byte_size"],
                display_byte_size=row["display_byte_size"],
                thumbnail_byte_size=row["thumbnail_byte_size"],
                sha256=row["sha256"],
            )
            for row in rows
        )

        dump_started = True
        await run_dump_process(command.dump_argv(snapshot_id, dump_app), output_path, timeout_seconds)
        # pg_dump has exited: every import of the snapshot is over, the
        # exporter may now end (in finally).
        return SnapshotDumpResult(
            snapshot_id=snapshot_id,
            ready=ready,
            server_major_version=server_major,
            dump_path=output_path,
            dump_size=output_path.stat().st_size,
            dump_sha256=_file_sha256(output_path),
        )
    finally:
        await asyncio.shield(_cleanup(conn, dump_app if dump_started else None))
