"""Stage 14D.2A — exporter SQL / configuration contract (no PostgreSQL).

A recording stand-in for the asyncpg connection checks what
`snapshot_bound_dump` emits and in which order: the session settings the
dedicated exporter connection is opened with (idle_in_transaction_session_timeout
disabled), the transaction start, the snapshot export as the first statement
of the transaction, the fail-closed checks of the observed settings, and the
rollback / close on every path. Real PostgreSQL semantics are proven in
test_stage14d2a_postgres.py.
"""

import uuid
from pathlib import Path

import pytest

from app.core import pg_snapshot_dump as mod
from app.core.pg_snapshot_dump import PgDumpCommand, PgDumpFailedError, SnapshotDumpError, snapshot_bound_dump

SNAPSHOT = "00000003-0000001B-1"


class FakeConn:
    def __init__(self, settings=("repeatable read", "on", "0"), rows=()):
        self.log: list[str] = []
        self.settings = settings
        self.rows = list(rows)
        self.in_tx = False
        self.closed = False

    async def fetchval(self, sql):
        self.log.append(sql)
        if sql == "SHOW server_version_num":
            return "160015"
        if sql == "SELECT pg_export_snapshot()":
            assert self.in_tx, "snapshot exported outside the transaction"
            return SNAPSHOT
        raise AssertionError(sql)

    async def fetchrow(self, sql):
        self.log.append(sql)
        return self.settings

    async def fetch(self, sql, *args):
        self.log.append(sql)
        return self.rows if sql == mod.READY_INVENTORY_SQL else []

    async def execute(self, sql):
        self.log.append(sql)
        if sql.startswith("BEGIN"):
            self.in_tx = True
        elif sql == "ROLLBACK":
            self.in_tx = False

    def is_in_transaction(self):
        return self.in_tx

    async def close(self):
        self.log.append("<close>")
        self.closed = True

    def terminate(self):
        self.log.append("<terminate>")
        self.closed = True


@pytest.fixture
def harness(monkeypatch):
    state = {"conn": FakeConn(), "connect_kwargs": None, "dump_argv": None, "dump_error": None}

    async def fake_connect(dsn, **kwargs):
        state["connect_kwargs"] = kwargs
        return state["conn"]

    async def fake_major(command, timeout_seconds=30.0):
        return 16

    async def fake_run(argv, output_path, timeout_seconds):
        state["dump_argv"] = list(argv)
        state["conn"].log.append("<pg_dump>")
        assert state["conn"].in_tx, "pg_dump ran after the exporter transaction ended"
        if state["dump_error"] is not None:
            raise state["dump_error"]
        Path(output_path).write_bytes(b"-- dump\n" + mod.DUMP_COMPLETE_MARKER + b"\n")

    monkeypatch.setattr(mod.asyncpg, "connect", fake_connect)
    monkeypatch.setattr(mod, "pg_dump_major_version", fake_major)
    monkeypatch.setattr(mod, "run_dump_process", fake_run)
    return state


CMD = PgDumpCommand(prefix=("docker", "exec", "-i", "pe-scratch-x"), username="pe", dbname="pe_scratch_test_x")


async def test_exporter_session_disables_idle_in_transaction_timeout(harness, tmp_path):
    await snapshot_bound_dump("postgresql://u@127.0.0.1/db", CMD, tmp_path / "d.sql", session_tag="pe-snapshot-ut")
    settings = harness["connect_kwargs"]["server_settings"]
    assert settings["idle_in_transaction_session_timeout"] == "0"
    assert settings["application_name"] == "pe-snapshot-ut-exp"
    assert mod.EXPORTER_SERVER_SETTINGS == {"idle_in_transaction_session_timeout": "0"}


async def test_statement_order_and_release_after_pg_dump(harness, tmp_path):
    result = await snapshot_bound_dump("dsn", CMD, tmp_path / "d.sql", session_tag="pe-snapshot-ut")
    log = harness["conn"].log
    begin = log.index("BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY")
    assert log[:begin] == ["SHOW server_version_num"]  # nothing runs inside the transaction before the export
    assert log[begin + 1] == "SELECT pg_export_snapshot()"
    check = log[begin + 2]
    assert "transaction_isolation" in check and "transaction_read_only" in check
    assert "idle_in_transaction_session_timeout" in check
    assert log[begin + 3] == mod.READY_INVENTORY_SQL
    assert log[begin + 4] == "<pg_dump>"
    assert log.index("ROLLBACK") > log.index("<pg_dump>") and log[-1] == "<close>"
    assert f"--snapshot={SNAPSHOT}" in harness["dump_argv"]
    assert "PGAPPNAME=pe-snapshot-ut-dump" in harness["dump_argv"]
    assert result.snapshot_id == SNAPSHOT and result.ready.ready_count == 0


@pytest.mark.parametrize(
    "settings",
    [
        ("repeatable read", "on", "30000"),  # a non-zero inherited timeout must never be accepted silently
        ("repeatable read", "on", "1min"),
        ("read committed", "on", "0"),
        ("repeatable read", "off", "0"),
    ],
)
async def test_observed_settings_fail_closed_before_any_read_or_dump(harness, tmp_path, settings):
    harness["conn"] = FakeConn(settings=settings)
    with pytest.raises(SnapshotDumpError):
        await snapshot_bound_dump("dsn", CMD, tmp_path / "d.sql", session_tag="pe-snapshot-ut")
    log = harness["conn"].log
    assert mod.READY_INVENTORY_SQL not in log and "<pg_dump>" not in log
    assert log[-2:] == ["ROLLBACK", "<close>"] and harness["conn"].closed
    assert not (tmp_path / "d.sql").exists()


async def test_dump_failure_terminates_tagged_backend_then_rolls_back(harness, tmp_path):
    harness["dump_error"] = PgDumpFailedError("boom", returncode=1, stderr_tail="")
    with pytest.raises(PgDumpFailedError):
        await snapshot_bound_dump("dsn", CMD, tmp_path / "d.sql", session_tag="pe-snapshot-ut")
    log = harness["conn"].log
    terminate = next(i for i, sql in enumerate(log) if "pg_terminate_backend" in sql)
    assert log.index("<pg_dump>") < terminate < log.index("ROLLBACK") < log.index("<close>")


async def test_inventory_rows_feed_the_ready_digest(harness, tmp_path):
    asset_id = uuid.uuid4()
    base = f"photos/v1/{asset_id}/"
    harness["conn"] = FakeConn(rows=[{
        "id": asset_id, "storage_key_original": base + "original.jpg", "storage_key_display": base + "display.jpg",
        "storage_key_thumbnail": base + "thumb.jpg", "byte_size": 3, "display_byte_size": 2,
        "thumbnail_byte_size": 1, "sha256": "a" * 64,
    }])
    result = await snapshot_bound_dump("dsn", CMD, tmp_path / "d.sql", session_tag="pe-snapshot-ut")
    assert result.ready.ready_count == 1 and len(result.ready.ready_set_sha256) == 64
