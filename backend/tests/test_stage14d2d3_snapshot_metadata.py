"""Stage 14D.2D.3 — same-snapshot metadata reader (recording fake asyncpg connection).

Proves the SQL / state-machine contract (REPEATABLE READ READ ONLY, snapshot
import as the first statement, validated id, rollback + close on every path,
strict parsing). It does NOT prove real PostgreSQL snapshot behaviour; that is
the opt-in real PostgreSQL proof (14D.2D.4).
"""

import asyncio

import pytest

from app.backup.schema_revision import ObservedRevisionError
from app.backup.snapshot_metadata import (
    ALEMBIC_SQL,
    DATABASE_SQL,
    STATUS_COUNTS_SQL,
    TRANSACTION_SQL,
    SnapshotMetadataError,
    parse_status_counts,
    read_snapshot_metadata,
    set_snapshot_sql,
)

SNAPSHOT = "00000003-0000001B-1"
TAG = "pe-snapshot-0123456789ab"
DSN = "postgresql://pe_backup@postgres:5432/plan_estimate?sslmode=disable&passfile=%2Frun%2Fsecrets%2Fpgpass"


class FakeConnection:
    def __init__(self, *, alembic=(("0032_photo_attachments",),), statuses=(("READY", 3), ("PENDING", 1)),
                 database=("plan_estimate", "16.15", "160015"), transaction=("repeatable read", "on"),
                 fail_on: str | None = None, hang_on: str | None = None) -> None:
        self.statements: list[str] = []
        self.in_tx = False
        self.closed = False
        self.terminated = False
        self.results = {ALEMBIC_SQL: list(alembic), STATUS_COUNTS_SQL: list(statuses)}
        self.rows = {DATABASE_SQL: database, TRANSACTION_SQL: transaction}
        self.fail_on = fail_on
        self.hang_on = hang_on

    async def _step(self, sql: str) -> None:
        self.statements.append(sql)
        if self.hang_on and sql.startswith(self.hang_on):
            await asyncio.sleep(3600)
        if self.fail_on and sql.startswith(self.fail_on):
            raise RuntimeError("server error with secret-ish text: password=hunter2")

    async def execute(self, sql: str) -> None:
        await self._step(sql)
        if sql.startswith("BEGIN"):
            self.in_tx = True
        if sql == "ROLLBACK":
            self.in_tx = False

    async def fetch(self, sql: str):
        await self._step(sql)
        return self.results[sql]

    async def fetchrow(self, sql: str):
        await self._step(sql)
        return self.rows[sql]

    def is_in_transaction(self) -> bool:
        return self.in_tx

    async def close(self) -> None:
        self.closed = True

    def terminate(self) -> None:
        self.terminated = True


def connector(conn: FakeConnection, seen: dict):
    async def connect(dsn, **kwargs):
        seen["dsn"] = dsn
        seen["kwargs"] = kwargs
        return conn

    return connect


async def test_imports_the_snapshot_first_and_reads_metadata():
    conn, seen = FakeConnection(), {}
    meta = await read_snapshot_metadata(DSN, SNAPSHOT, TAG, connect=connector(conn, seen))
    assert conn.statements == [
        "BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY",
        f"SET TRANSACTION SNAPSHOT '{SNAPSHOT}'",
        TRANSACTION_SQL,
        ALEMBIC_SQL,
        STATUS_COUNTS_SQL,
        DATABASE_SQL,
        "ROLLBACK",
    ]
    assert conn.closed and not conn.in_tx
    assert seen["dsn"] == DSN and seen["kwargs"] == {"server_settings": {"application_name": f"{TAG}-meta"}}
    assert meta.alembic_revision == "0032_photo_attachments"
    assert meta.photo_asset_status_counts == {"FAILED": 0, "PENDING": 1, "READY": 3}
    assert (meta.database_name, meta.server_version, meta.server_version_num) == ("plan_estimate", "16.15", 160015)


@pytest.mark.parametrize(
    "snapshot_id",
    ["", "00000003-0000001b-1", "1-2-3'; DROP TABLE x; --", "1-2-3 ", "x' OR '1'='1", "00000003-0000001B-1\n"],
)
async def test_invalid_snapshot_id_is_refused_before_connecting(snapshot_id):
    seen: dict = {}
    with pytest.raises(SnapshotMetadataError):
        await read_snapshot_metadata(DSN, snapshot_id, TAG, connect=connector(FakeConnection(), seen))
    assert seen == {}


def test_set_snapshot_sql_only_contains_the_validated_id():
    assert set_snapshot_sql(SNAPSHOT) == "SET TRANSACTION SNAPSHOT '00000003-0000001B-1'"


@pytest.mark.parametrize("tag", ["short", "UPPER-case-tag", "tag with space", "x" * 41, "pe-snap;drop"])
async def test_invalid_session_tag_is_refused_before_connecting(tag):
    seen: dict = {}
    with pytest.raises(SnapshotMetadataError):
        await read_snapshot_metadata(DSN, SNAPSHOT, tag, connect=connector(FakeConnection(), seen))
    assert seen == {}


@pytest.mark.parametrize("fail_on", ["SET TRANSACTION SNAPSHOT", ALEMBIC_SQL, STATUS_COUNTS_SQL, DATABASE_SQL])
async def test_rollback_and_close_on_query_failure(fail_on):
    conn = FakeConnection(fail_on=fail_on)
    with pytest.raises(RuntimeError):
        await read_snapshot_metadata(DSN, SNAPSHOT, TAG, connect=connector(conn, {}))
    assert conn.statements[-1] == "ROLLBACK" and conn.closed and not conn.in_tx


async def test_metadata_reads_never_precede_the_snapshot_import():
    conn = FakeConnection(fail_on="SET TRANSACTION SNAPSHOT")
    with pytest.raises(RuntimeError):
        await read_snapshot_metadata(DSN, SNAPSHOT, TAG, connect=connector(conn, {}))
    assert ALEMBIC_SQL not in conn.statements and STATUS_COUNTS_SQL not in conn.statements


async def test_wrong_transaction_mode_is_refused():
    conn = FakeConnection(transaction=("read committed", "off"))
    with pytest.raises(SnapshotMetadataError):
        await read_snapshot_metadata(DSN, SNAPSHOT, TAG, connect=connector(conn, {}))
    assert ALEMBIC_SQL not in conn.statements and conn.closed


async def test_timeout_cleans_up():
    conn = FakeConnection(hang_on=ALEMBIC_SQL)
    with pytest.raises(TimeoutError):
        await read_snapshot_metadata(DSN, SNAPSHOT, TAG, connect=connector(conn, {}), timeout_seconds=0.2)
    assert conn.statements[-1] == "ROLLBACK" and conn.closed


async def test_cancellation_cleans_up():
    conn = FakeConnection(hang_on=ALEMBIC_SQL)
    task = asyncio.create_task(read_snapshot_metadata(DSN, SNAPSHOT, TAG, connect=connector(conn, {})))
    for _ in range(100):
        if ALEMBIC_SQL in conn.statements:
            break
        await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert conn.closed and not conn.in_tx


@pytest.mark.parametrize("alembic", [(), (("0031_a",), ("0032_b",)), ((None,),), (("bad id",),), (("x" * 33,),)])
async def test_alembic_version_must_be_exactly_one_valid_row(alembic):
    conn = FakeConnection(alembic=alembic)
    with pytest.raises(ObservedRevisionError):
        await read_snapshot_metadata(DSN, SNAPSHOT, TAG, connect=connector(conn, {}))
    assert conn.closed


@pytest.mark.parametrize(
    "statuses",
    [
        (("DELETED", 1),),
        (("ready", 1),),
        ((None, 1),),
        (("READY", 1), ("READY", 2)),
        (("READY", -1),),
        (("READY", True),),
        (("READY", "3"),),
        (("READY", 1.0),),
    ],
)
def test_status_counts_are_canonical_only(statuses):
    with pytest.raises(SnapshotMetadataError):
        parse_status_counts(list(statuses))


def test_absent_statuses_count_zero():
    assert parse_status_counts([]) == {"FAILED": 0, "PENDING": 0, "READY": 0}


@pytest.mark.parametrize(
    "database",
    [
        ("plan estimate", "16.15", "160015"),
        ("plan_estimate", "sixteen", "160015"),
        ("plan_estimate", "16.15", "16x"),
        ("plan_estimate", "16.15", "99999"),
        ("plan_estimate", "16.15", "１６００１５"),
        ("plan_estimate", "16.15", 160015),
        (None, "16.15", "160015"),
    ],
)
async def test_database_metadata_is_validated(database):
    conn = FakeConnection(database=database)
    with pytest.raises(SnapshotMetadataError):
        await read_snapshot_metadata(DSN, SNAPSHOT, TAG, connect=connector(conn, {}))


async def test_errors_never_echo_server_text():
    conn = FakeConnection(statuses=(("password=hunter2", 1),))
    with pytest.raises(SnapshotMetadataError) as exc:
        await read_snapshot_metadata(DSN, SNAPSHOT, TAG, connect=connector(conn, {}))
    assert "hunter2" not in str(exc.value)
