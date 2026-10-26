"""V2-9a -- migration 0076: the journal kind PAYMENT_SCHEDULE, what the database refuses, a downgrade that never drops a document."""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from tests.test_stage16e2_contract import load_migration, run

NAME = "0076_payment_schedule_doc"
INSERT = (
    "INSERT INTO issued_documents (id, owner_id, project_id, kind, title, number, project_seq, template_version, status, issued_at, created_at, updated_at) "
    "VALUES (:id, 'o', 'p', :kind, 'x', :number, :seq, '1', 'SENT', '2026-10-28', '2026-10-28', '2026-10-28')"
)
OLD_KINDS = ("ESTIMATE", "PHOTO_REPORT", "TECH_CARD", "PRODUCTION_PLAN", "CONTRACT", "HANDOVER_PROTOCOL", "CONCEALED_WORKS_PROTOCOL", "FINAL_PROTOCOL",
             "DECISION_PROTOCOL", "DOWNTIME_NOTICE", "DOWNTIME_PROTOCOL", "SETTLEMENT", "MEASUREMENTS")


def old_engine():
    """The journal table as 0075 leaves it: the kinds it knew, a row of the newest of them."""
    engine = create_engine("sqlite://")
    listed = ", ".join(f"'{kind}'" for kind in OLD_KINDS)
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE issued_documents (id CHAR(32) PRIMARY KEY, owner_id CHAR(32) NOT NULL, project_id CHAR(32) NOT NULL, kind VARCHAR(32) NOT NULL, "
            "title VARCHAR(255) NOT NULL, number VARCHAR(64) NOT NULL, project_seq INTEGER NOT NULL, template_version VARCHAR(16) NOT NULL, "
            "status VARCHAR(16) NOT NULL, issued_at DATETIME NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, "
            f"CONSTRAINT ck_issued_documents_kind CHECK (kind IN ({listed})))"
        ))
        conn.execute(text(INSERT), {"id": "old", "kind": "MEASUREMENTS", "number": "OBM/1", "seq": 1})
    return engine


def engine_0076():
    engine = old_engine()
    run(engine, NAME, "upgrade")
    return engine


def test_revision_chain_and_length():
    module = load_migration(NAME)
    assert module.revision == NAME and module.down_revision == "0075_payment_schedule" and len(module.revision) <= 32


def test_the_old_row_is_untouched_and_the_new_kind_is_accepted_and_nothing_else_is():
    engine = engine_0076()
    with engine.begin() as conn:
        conn.execute(text(INSERT), {"id": "new", "kind": "PAYMENT_SCHEDULE", "number": "HPL/1", "seq": 2})
        assert [tuple(r) for r in conn.execute(text("SELECT id, kind FROM issued_documents ORDER BY id"))] == [("new", "PAYMENT_SCHEDULE"), ("old", "MEASUREMENTS")]
    for bad in ("PAYMENT", "HARMONOGRAM", ""):
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(text(INSERT), {"id": f"bad-{bad}", "kind": bad, "number": f"X/{bad}", "seq": 9})


def test_the_check_of_the_migration_is_the_check_of_the_model():
    from app.models.issued_document import IssuedDocument

    module = load_migration(NAME)
    latest = load_migration("0082_pressure_tests")  # the model follows the newest widening; the steps between are chained
    map_ = load_migration("0081_installation_map_doc")
    model = next(c for c in IssuedDocument.__table__.constraints if getattr(c, "name", None) == "ck_issued_documents_kind")
    assert " ".join(latest.KINDS_NEW.split()) == " ".join(str(model.sqltext).split())
    assert " ".join(latest.KINDS_OLD.split()) == " ".join(map_.KINDS_NEW.split())
    assert " ".join(module.KINDS_NEW.split()) == " ".join(map_.KINDS_OLD.split())


def test_the_downgrade_refuses_while_a_schedule_is_in_the_journal_and_then_restores_the_old_check():
    engine = engine_0076()
    with engine.begin() as conn:
        conn.execute(text(INSERT), {"id": "new", "kind": "PAYMENT_SCHEDULE", "number": "HPL/1", "seq": 2})
    with pytest.raises(RuntimeError, match="never dropped silently"):
        run(engine, NAME, "downgrade")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM issued_documents WHERE kind = 'PAYMENT_SCHEDULE'"))
    run(engine, NAME, "downgrade")
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text(INSERT), {"id": "again", "kind": "PAYMENT_SCHEDULE", "number": "HPL/2", "seq": 3})
    with engine.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM issued_documents")).scalar_one() == 1
    run(engine, NAME, "upgrade")  # and up again
