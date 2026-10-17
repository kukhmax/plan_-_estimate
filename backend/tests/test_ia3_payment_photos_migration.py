"""Invoices and advances IA-3 -- migration 0059: the context PAYMENT on photo_attachments, what the database refuses, and a downgrade that never drops a receipt."""
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.models.photo_attachment import CONTEXT_TARGETS_CHECK
from tests.test_stage16e2_contract import load_migration, run

NAME = "0059_payment_photos"
INSERT = (
    "INSERT INTO photo_attachments (id, asset_id, project_id, context, room_id, surface_id, payment_id, category, include_in_report, position, created_at, updated_at) "
    "VALUES (:id, :asset, 'p1', :context, :room, :surface, :payment, 'GENERAL', 0, 0, '2026-10-17', '2026-10-17')"
)
ROW = {"id": "x", "asset": "a1", "context": "PROJECT", "room": None, "surface": None, "payment": None}


def old_engine():
    """The table as the chain left it before this migration (0032 + 0056), with one old row of the room context."""
    engine = create_engine("sqlite://")
    with engine.begin() as conn:  # the tables the foreign keys point at: reflecting the table for the rebuild needs them
        for table in ("photo_assets", "projects", "rooms", "surfaces", "openings", "inspections", "checklist_questions", "inspection_findings", "price_items", "project_payments"):
            conn.execute(text(f"CREATE TABLE {table} (id CHAR(32) PRIMARY KEY)"))
    run(engine, "0032_photo_attachments", "upgrade")
    run(engine, "0056_photo_trash", "upgrade")
    old = (
        "INSERT INTO photo_attachments (id, asset_id, project_id, context, room_id, category, include_in_report, position, created_at, updated_at) "
        "VALUES (:id, :asset, 'p1', :context, :room, 'GENERAL', 0, 0, '2026-10-17', '2026-10-17')"
    )
    with engine.begin() as conn:
        conn.execute(text(old), {"id": "old-room", "asset": "a1", "context": "ROOM", "room": "r1"})
        conn.execute(text(old), {"id": "old-project", "asset": "a2", "context": "PROJECT", "room": None})
    return engine


def engine_0059():
    engine = old_engine()
    run(engine, NAME, "upgrade")
    return engine


def test_revision_chain_and_length():
    module = load_migration(NAME)
    assert module.revision == NAME and module.down_revision == "0058_project_payments" and len(module.revision) <= 32


def test_the_check_of_the_migration_is_the_check_of_the_model_and_the_old_one_is_the_old_one():
    module = load_migration(NAME)
    assert module.NEW_CHECK == CONTEXT_TARGETS_CHECK
    assert module.OLD_CHECK == load_migration("0032_photo_attachments").CONTEXT_TARGETS_CHECK


def test_the_column_and_the_indexes_exist_and_the_old_rows_are_untouched():
    engine = engine_0059()
    inspector = inspect(engine)
    assert "payment_id" in {c["name"] for c in inspector.get_columns("photo_attachments")}
    indexes = {i["name"]: i for i in inspector.get_indexes("photo_attachments")}
    assert "ix_photo_attachments_payment_id" in indexes
    assert indexes["uq_photo_att_payment_active"]["unique"] and indexes["uq_photo_att_payment_active"]["column_names"] == ["asset_id", "payment_id"]
    fks = [fk for fk in inspector.get_foreign_keys("photo_attachments") if fk["constrained_columns"] == ["payment_id"]]
    assert [(fk["referred_table"], fk["options"].get("ondelete")) for fk in fks] == [("project_payments", "RESTRICT")]
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, context, payment_id FROM photo_attachments ORDER BY id")).all()
    assert [tuple(r) for r in rows] == [("old-project", "PROJECT", None), ("old-room", "ROOM", None)]


def test_the_database_accepts_a_receipt_and_refuses_every_wrong_shape():
    engine = engine_0059()
    with engine.begin() as conn:
        conn.execute(text(INSERT), {**ROW, "id": "ok", "asset": "a3", "context": "PAYMENT", "payment": "pay1"})
        conn.execute(text(INSERT), {**ROW, "id": "ok-room", "asset": "a4", "context": "ROOM", "room": "r1"})  # the old branches still hold
    for bad in (
        {"id": "b1", "context": "PAYMENT"},                                      # a receipt of nothing
        {"id": "b2", "context": "PAYMENT", "payment": "pay1", "room": "r1"},    # a record and a room
        {"id": "b3", "context": "PAYMENT", "payment": "pay1", "surface": "s1"},
        {"id": "b4", "context": "ROOM", "room": "r1", "payment": "pay1"},       # a room photo with a record
        {"id": "b5", "context": "PROJECT", "payment": "pay1"},
        {"id": "b6", "context": "SURFACE", "surface": "s1", "payment": "pay1"},
    ):
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(text(INSERT), {**ROW, "asset": "a9", **bad})


def test_one_active_receipt_of_a_file_per_record():
    engine = engine_0059()
    receipt = {**ROW, "asset": "a3", "context": "PAYMENT", "payment": "pay1"}
    with engine.begin() as conn:
        conn.execute(text(INSERT), {**receipt, "id": "first"})
        conn.execute(text(INSERT), {**receipt, "id": "other-record", "payment": "pay2"})
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text(INSERT), {**receipt, "id": "again"})
    with engine.begin() as conn:  # an archived one does not count
        conn.execute(text("UPDATE photo_attachments SET archived_at = '2026-10-17' WHERE id = 'first'"))
        conn.execute(text(INSERT), {**receipt, "id": "again"})


def test_downgrade_refuses_while_a_receipt_exists():
    engine = engine_0059()
    with engine.begin() as conn:
        conn.execute(text(INSERT), {**ROW, "id": "r", "asset": "a3", "context": "PAYMENT", "payment": "pay1"})
    with pytest.raises(RuntimeError, match="1 photo"):
        run(engine, NAME, "downgrade")
    assert "payment_id" in {c["name"] for c in inspect(engine).get_columns("photo_attachments")}  # nothing was changed


def test_downgrade_without_receipts_restores_the_old_table_and_loses_no_row():
    engine = engine_0059()
    run(engine, NAME, "downgrade")
    inspector = inspect(engine)
    assert "payment_id" not in {c["name"] for c in inspector.get_columns("photo_attachments")}
    names = {i["name"] for i in inspector.get_indexes("photo_attachments")}
    assert not {"ix_photo_attachments_payment_id", "uq_photo_att_payment_active"} & names
    with engine.connect() as conn:
        assert [r[0] for r in conn.execute(text("SELECT id FROM photo_attachments ORDER BY id"))] == ["old-project", "old-room"]
    with pytest.raises((IntegrityError, OperationalError)), engine.begin() as conn:  # the old check does not know the new context
        conn.execute(text("INSERT INTO photo_attachments (id, asset_id, project_id, context, category, include_in_report, position, created_at, updated_at) "
                          "VALUES ('n', 'a5', 'p1', 'PAYMENT', 'GENERAL', 0, 0, '2026-10-17', '2026-10-17')"))
    run(engine, NAME, "upgrade")  # and up again
    assert "payment_id" in {c["name"] for c in inspect(engine).get_columns("photo_attachments")}
