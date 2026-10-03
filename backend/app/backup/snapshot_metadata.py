"""Same-snapshot database metadata (Stage 14D.2D.3, owner decision D4).

Called from the 14D.2A `after_export` hook while the exporter transaction is
still open. A SECOND connection imports the exported snapshot -- the same
PostgreSQL mechanism pg_dump uses -- so everything read here belongs to
exactly the database state that the READY inventory and the dump describe:

    BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY
    SET TRANSACTION SNAPSHOT '<strictly validated id>'   -- first statement
    SELECT version_num FROM alembic_version              -- exactly one row
    SELECT status::text, count(*) FROM photo_assets GROUP BY status
    SELECT current_database(), server_version, server_version_num
    ROLLBACK; close

`SET TRANSACTION SNAPSHOT` takes no bind parameter, so the id is accepted
only if it matches the strict 14D.2D.1 pattern (hex / digits / dashes); no
other text is ever interpolated. Every returned value is validated before it
can reach evidence. The connection uses the same passfile DSN as the
exporter; no password is handled here.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import asyncpg

from app.backup.evidence import (
    PHOTO_ASSET_STATUSES,
    EvidenceError,
    validate_database_name,
    validate_server_version,
    validate_server_version_num,
    validate_session_tag,
    validate_snapshot_id,
    validate_status_counts,
)
from app.backup.schema_revision import observed_revision_from_rows

logger = logging.getLogger(__name__)

METADATA_TIMEOUT_SECONDS = 60.0
CLEANUP_TIMEOUT_SECONDS = 15.0
ALEMBIC_SQL = "SELECT version_num FROM alembic_version"
STATUS_COUNTS_SQL = "SELECT status::text AS status, count(*) AS n FROM photo_assets GROUP BY status"
DATABASE_SQL = (
    "SELECT current_database() AS name, current_setting('server_version') AS version,"
    " current_setting('server_version_num') AS version_num"
)
TRANSACTION_SQL = (
    "SELECT current_setting('transaction_isolation') AS isolation,"
    " current_setting('transaction_read_only') AS read_only"
)

Connect = Callable[..., Awaitable[Any]]


class SnapshotMetadataError(RuntimeError):
    """Same-snapshot metadata could not be read or is invalid. Messages name
    the item, never a value."""


@dataclass(frozen=True)
class SnapshotMetadata:
    database_name: str
    server_version: str
    server_version_num: int
    alembic_revision: str
    photo_asset_status_counts: dict[str, int]


def set_snapshot_sql(snapshot_id: str) -> str:
    """The only interpolated statement; the id is strictly validated first."""
    try:
        validated = validate_snapshot_id(snapshot_id)
    except EvidenceError:
        raise SnapshotMetadataError("refusing an invalid exported snapshot id") from None
    return f"SET TRANSACTION SNAPSHOT '{validated}'"


def parse_status_counts(rows: list[tuple[object, object]]) -> dict[str, int]:
    """Canonical statuses only (FAILED / PENDING / READY), each at most once,
    non-negative integers; absent statuses count 0."""
    counts = dict.fromkeys(PHOTO_ASSET_STATUSES, 0)
    seen: set[str] = set()
    for status, count in rows:
        if not isinstance(status, str) or status not in counts:
            raise SnapshotMetadataError("photo_assets contains an unknown status")
        if status in seen:
            raise SnapshotMetadataError("photo_assets status counts are ambiguous")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise SnapshotMetadataError("photo_assets status count is not a non-negative integer")
        seen.add(status)
        counts[status] = count
    try:
        return validate_status_counts(counts)
    except EvidenceError:
        raise SnapshotMetadataError("photo_assets status counts are invalid") from None


def parse_database_row(name: object, version: object, version_num: object) -> tuple[str, str, int]:
    """`server_version_num` arrives as text (current_setting); only plain ASCII digits are accepted."""
    if not isinstance(version_num, str) or not version_num.isascii() or not version_num.isdigit():
        raise SnapshotMetadataError("database / server metadata is invalid")
    try:
        return (
            validate_database_name(name),
            validate_server_version(version),
            validate_server_version_num(int(version_num)),
        )
    except EvidenceError:
        raise SnapshotMetadataError("database / server metadata is invalid") from None


async def _cleanup(conn: Any) -> None:
    try:
        async with asyncio.timeout(CLEANUP_TIMEOUT_SECONDS):
            if conn.is_in_transaction():
                await conn.execute("ROLLBACK")
            await conn.close()
    except Exception as exc:  # noqa: BLE001 - cleanup must not mask the original outcome; logged, hard-closed
        logger.warning("snapshot metadata connection cleanup failed: %s", type(exc).__name__)
        conn.terminate()


async def read_snapshot_metadata(
    dsn: str,
    snapshot_id: str,
    session_tag: str,
    *,
    connect: Connect = asyncpg.connect,
    timeout_seconds: float = METADATA_TIMEOUT_SECONDS,
) -> SnapshotMetadata:
    """Import `snapshot_id` on a dedicated connection and read the metadata
    that must belong to the backup snapshot."""
    statement = set_snapshot_sql(snapshot_id)
    try:
        tag = validate_session_tag(session_tag)
    except EvidenceError:
        raise SnapshotMetadataError("refusing an invalid session tag") from None
    conn = await connect(dsn, server_settings={"application_name": f"{tag}-meta"})
    try:
        async with asyncio.timeout(timeout_seconds):
            await conn.execute("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
            await conn.execute(statement)
            isolation, read_only = await conn.fetchrow(TRANSACTION_SQL)
            if isolation != "repeatable read" or read_only != "on":
                raise SnapshotMetadataError("metadata transaction is not REPEATABLE READ READ ONLY")
            alembic_rows = await conn.fetch(ALEMBIC_SQL)
            status_rows = await conn.fetch(STATUS_COUNTS_SQL)
            database_row = await conn.fetchrow(DATABASE_SQL)
    finally:
        await asyncio.shield(_cleanup(conn))

    # ObservedRevisionError (0 / >1 rows, malformed id) propagates with its own error code.
    revision = observed_revision_from_rows([tuple(row) for row in alembic_rows])
    counts = parse_status_counts([(row[0], row[1]) for row in status_rows])
    if database_row is None:
        raise SnapshotMetadataError("database metadata row is missing")
    name, version, version_num = parse_database_row(database_row[0], database_row[1], database_row[2])
    return SnapshotMetadata(
        database_name=name,
        server_version=version,
        server_version_num=version_num,
        alembic_revision=revision,
        photo_asset_status_counts=counts,
    )
