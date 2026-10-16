"""Archive cleanup AC-3a -- the server side of the ledger: the export file and the mark-done of the owner's report."""
import io
import os
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.backup import purge_ledger as pl
from app.backup.purge_ledger_db import export_entries, mark_backup_done
from app.backup.purge_report import ReportEntry, parse_report, serialize_report
from app.cli import purge_ledger as cli
from app.models.purge_ledger import PurgeLedger

NOW = datetime(2026, 10, 16, 20, 0, tzinfo=UTC)


def ledger_row(n: int, **over) -> PurgeLedger:
    asset = uuid.UUID(int=n)
    base = f"photos/v1/{asset}/"
    values = dict(
        id=uuid.UUID(int=1000 + n), owner_id=uuid.UUID(int=1), project_id=uuid.UUID(int=2), asset_id=asset, kind="PHOTO", storage_name="r2",
        storage_key_original=f"{base}original.jpg", storage_key_display=f"{base}display.jpg", storage_key_thumbnail=f"{base}thumb.jpg", sha256="b" * 64,
        byte_size=10, display_byte_size=5, thumbnail_byte_size=1, purged_at=datetime(2026, 10, 16, 19, n, tzinfo=UTC), storage_state="DONE",
        storage_done_at=NOW, backup_state="PENDING",
    )
    values.update(over)
    return PurgeLedger(**values)


async def add(db, *rows) -> None:
    db.add_all(rows)
    await db.commit()


async def test_the_export_is_a_valid_strict_file_of_all_rows_or_of_the_pending_ones(db_session):
    await add(db_session, ledger_row(1), ledger_row(2, backup_state="DONE", backup_done_at=NOW), ledger_row(3))
    everything = await export_entries(db_session)
    pending = await export_entries(db_session, pending_only=True)
    assert [e.asset_id.int for e in everything] == [1, 2, 3] and [e.asset_id.int for e in pending] == [1, 3]
    parsed = pl.parse_ledger(pl.serialize_ledger(everything, exported_at="2026-10-16T20:00:00Z"))  # what a restore or the purge tool reads
    assert len(parsed.entries) == 3 and parsed.entries[0].sha256 == "b" * 64
    assert parsed.entries[0].purged_at == "2026-10-16T19:01:00Z"


async def test_the_export_holds_no_content_no_owner_and_no_project(db_session):
    await add(db_session, ledger_row(1))
    text = pl.serialize_ledger(await export_entries(db_session), exported_at="2026-10-16T20:00:00Z").decode()
    assert "owner" not in text and "project" not in text


def report(bucket: str, *entries: tuple[int, str]) -> bytes:
    return serialize_report([ReportEntry(uuid.UUID(int=n), outcome, 1) for n, outcome in entries], bucket_kind=bucket, finished_at="2026-10-16T21:00:00Z")


async def states(db) -> dict[int, str]:
    return {row.asset_id.int: row.backup_state for row in (await db.execute(select(PurgeLedger))).scalars()}


async def test_a_production_report_marks_the_rows_whose_copies_are_gone_and_nothing_else(db_session):
    await add(db_session, ledger_row(1), ledger_row(2), ledger_row(3))
    marked = await mark_backup_done(db_session, parse_report(report("prod", (1, "deleted"), (2, "failed"), (3, "already_absent"), (99, "deleted"))), now=NOW)
    assert marked == 2 and await states(db_session) == {1: "DONE", 2: "PENDING", 3: "DONE"}
    row = (await db_session.execute(select(PurgeLedger).where(PurgeLedger.asset_id == uuid.UUID(int=1)))).scalar_one()
    assert row.backup_done_at is not None


async def test_a_rehearsal_in_the_drill_bucket_never_marks_a_production_row(db_session):
    await add(db_session, ledger_row(1))
    assert await mark_backup_done(db_session, parse_report(report("drill", (1, "deleted")))) == 0
    assert await states(db_session) == {1: "PENDING"}


async def test_marking_twice_changes_nothing(db_session):
    await add(db_session, ledger_row(1))
    first = await mark_backup_done(db_session, parse_report(report("prod", (1, "deleted"))), now=NOW)
    second = await mark_backup_done(db_session, parse_report(report("prod", (1, "deleted"))), now=NOW)
    assert (first, second) == (1, 0)


@pytest.fixture
def sessions(db_session, monkeypatch):
    @asynccontextmanager
    async def maker():
        yield db_session

    monkeypatch.setattr(cli, "async_session_maker", maker)


async def test_the_command_writes_the_export_to_a_new_private_file(db_session, sessions, tmp_path):
    await add(db_session, ledger_row(1), ledger_row(2))
    target = tmp_path / "ledger.jsonl"
    out = io.StringIO()
    assert await cli.run(["export", "--out", str(target)], out) == 0
    assert "entries=2" in out.getvalue() and oct(os.stat(target).st_mode & 0o777) == "0o600"
    assert len(pl.parse_ledger(target.read_bytes()).entries) == 2
    assert await cli.run(["export", "--out", str(target)], io.StringIO()) == cli.EXIT_UNUSABLE  # never overwritten
    assert await cli.run(["export", "--out", "relative.jsonl"], io.StringIO()) == cli.EXIT_UNUSABLE


async def test_the_command_prints_the_export_when_no_file_is_named(db_session, sessions):
    await add(db_session, ledger_row(1))
    out = io.StringIO()
    assert await cli.run(["export", "--pending-only"], out) == 0
    assert len(pl.parse_ledger(out.getvalue().encode()).entries) == 1


async def test_mark_done_reads_the_report_and_refuses_anything_else(db_session, sessions, tmp_path):
    await add(db_session, ledger_row(1))
    good, bad = tmp_path / "report.jsonl", tmp_path / "bad.jsonl"
    good.write_bytes(report("prod", (1, "deleted")))
    bad.write_bytes(b'{"format":"other"}\n')
    out = io.StringIO()
    assert await cli.run(["mark-done", "--report", str(good)], out) == 0 and "marked=1" in out.getvalue()
    assert await cli.run(["mark-done", "--report", str(bad)], io.StringIO()) == cli.EXIT_UNUSABLE
    assert await cli.run(["mark-done", "--report", str(tmp_path / "missing")], io.StringIO()) == cli.EXIT_UNUSABLE
    assert await cli.run(["mark-done", "--report", "relative"], io.StringIO()) == cli.EXIT_UNUSABLE
