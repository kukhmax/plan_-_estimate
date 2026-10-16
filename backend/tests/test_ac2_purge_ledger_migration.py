"""Archive cleanup AC-2 -- migration 0057: the ledger table, what the database refuses, and a downgrade that never drops the ledger."""
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.models.purge_ledger import PurgeLedger
from tests.test_stage16e2_contract import load_migration, run

NAME = "0057_purge_ledger"
ROW = (
    "INSERT INTO purge_ledger (id, owner_id, project_id, asset_id, kind, storage_name, storage_key_original, storage_key_display, "
    "storage_key_thumbnail, sha256, byte_size, display_byte_size, thumbnail_byte_size, purged_at, storage_state, storage_done_at, backup_state, backup_done_at) "
    "VALUES (:id, 'o', 'p', :asset, :kind, 'r2', 'k/o', 'k/d', 'k/t', :sha, 1, 1, 1, '2026-10-16', :sstate, :sdone, :bstate, :bdone)"
)
GOOD = {"id": "l1", "asset": "a1", "kind": "PHOTO", "sha": "0" * 64, "sstate": "PENDING", "sdone": None, "bstate": "PENDING", "bdone": None}


def engine_0057():
    engine = create_engine("sqlite://")
    run(engine, NAME, "upgrade")
    return engine


def test_revision_chain_and_length():
    module = load_migration(NAME)
    assert module.revision == NAME and module.down_revision == "0056_photo_trash" and len(module.revision) <= 32


def test_the_table_has_the_columns_of_the_model_and_no_foreign_key():
    inspector = inspect(engine_0057())
    assert {c["name"] for c in inspector.get_columns("purge_ledger")} == {c.name for c in PurgeLedger.__table__.columns}
    assert inspector.get_foreign_keys("purge_ledger") == []  # the obligation to clean the backups outlives every other row
    assert {i["name"] for i in inspector.get_indexes("purge_ledger")} >= {"ix_purge_ledger_owner_states", "uq_purge_ledger_asset"}


def test_the_database_refuses_what_the_service_never_writes():
    engine = engine_0057()
    with engine.begin() as conn:
        conn.execute(text(ROW), GOOD)
        conn.execute(text(ROW), {**GOOD, "id": "l2", "asset": "a2", "sstate": "DONE", "sdone": "2026-10-16", "bstate": "DONE", "bdone": "2026-10-17"})
    for bad in (
        {"id": "b1", "asset": "a3", "kind": "ROOM"},
        {"id": "b2", "asset": "a4", "sstate": "WAITING"},
        {"id": "b3", "asset": "a5", "bstate": "WAITING"},
        {"id": "b4", "asset": "a6", "sstate": "DONE", "sdone": None},
        {"id": "b5", "asset": "a7", "bstate": "DONE", "bdone": None},
        {"id": "b6", "asset": "a1"},  # one ledger row per file set
    ):
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(text(ROW), {**GOOD, **bad})


def test_the_downgrade_refuses_while_the_ledger_has_rows_and_works_when_it_is_empty():
    engine = engine_0057()
    run(engine, NAME, "downgrade")
    assert "purge_ledger" not in inspect(engine).get_table_names()
    run(engine, NAME, "upgrade")
    with engine.begin() as conn:
        conn.execute(text(ROW), GOOD)
    with pytest.raises(RuntimeError, match="ledger row"):
        run(engine, NAME, "downgrade")
    assert "purge_ledger" in inspect(engine).get_table_names()
