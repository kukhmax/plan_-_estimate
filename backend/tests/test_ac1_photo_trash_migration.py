"""Archive cleanup AC-1 -- migration 0056: the trash column on photo_attachments, what the database refuses, and a lossless downgrade."""
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from tests.test_stage16e2_contract import load_migration, run

NAME = "0056_photo_trash"
INSERT = "INSERT INTO photo_attachments (id, project_id, archived_at, trashed_at) VALUES (:id, 'p1', :archived, :trashed)"


def engine_0056():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        # only the columns this migration touches or the check names (the full table is rebuilt by the real chain)
        conn.execute(text("CREATE TABLE photo_attachments (id CHAR(32) PRIMARY KEY, project_id CHAR(32) NOT NULL, archived_at DATETIME)"))
        conn.execute(text("INSERT INTO photo_attachments (id, project_id, archived_at) VALUES ('old-active', 'p1', NULL), ('old-archived', 'p1', '2026-10-01')"))
    run(engine, NAME, "upgrade")
    return engine


def test_revision_chain_and_length():
    module = load_migration(NAME)
    assert module.revision == NAME and module.down_revision == "0055_project_notes" and len(module.revision) <= 32


def test_existing_rows_are_untouched_and_the_column_and_index_exist():
    engine = engine_0056()
    inspector = inspect(engine)
    assert "trashed_at" in {c["name"] for c in inspector.get_columns("photo_attachments")}
    assert "ix_photo_attachments_project_trashed" in {i["name"] for i in inspector.get_indexes("photo_attachments")}
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, archived_at, trashed_at FROM photo_attachments ORDER BY id")).all()
    assert [(r[0], r[1] is not None, r[2]) for r in rows] == [("old-active", False, None), ("old-archived", True, None)]


def test_the_database_keeps_the_trash_a_state_of_the_archive():
    engine = engine_0056()
    with engine.begin() as conn:
        conn.execute(text(INSERT), {"id": "ok-trashed", "archived": "2026-10-01", "trashed": "2026-10-02"})
        conn.execute(text(INSERT), {"id": "ok-archived", "archived": "2026-10-01", "trashed": None})
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text(INSERT), {"id": "bad", "archived": None, "trashed": "2026-10-02"})


def test_downgrade_loses_only_the_mark_never_a_row():
    engine = engine_0056()
    with engine.begin() as conn:
        conn.execute(text(INSERT), {"id": "t", "archived": "2026-10-01", "trashed": "2026-10-02"})
    run(engine, NAME, "downgrade")
    inspector = inspect(engine)
    assert "trashed_at" not in {c["name"] for c in inspector.get_columns("photo_attachments")}
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, archived_at FROM photo_attachments ORDER BY id")).all()
    assert [r[0] for r in rows] == ["old-active", "old-archived", "t"] and rows[2][1] is not None
