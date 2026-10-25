"""V2-8c -- migration 0074: the journal kind MEASUREMENTS, what the database refuses, a downgrade that never drops a document."""
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from tests.test_stage16e2_contract import load_migration, run

NAME = "0074_measurements_document"
INSERT = (
    "INSERT INTO issued_documents (id, owner_id, project_id, kind, title, number, project_seq, template_version, status, issued_at, created_at, updated_at) "
    "VALUES (:id, 'o', 'p', :kind, 'x', :number, :seq, '1', 'SENT', '2026-10-27', '2026-10-27', '2026-10-27')"
)
OLD_KINDS = ("ESTIMATE", "PHOTO_REPORT", "TECH_CARD", "PRODUCTION_PLAN", "CONTRACT", "HANDOVER_PROTOCOL", "CONCEALED_WORKS_PROTOCOL", "FINAL_PROTOCOL",
             "DECISION_PROTOCOL", "DOWNTIME_NOTICE", "DOWNTIME_PROTOCOL", "SETTLEMENT")


def old_engine():
    """The journal table as 0073 leaves it: the kinds it knew, a row of the oldest kind."""
    engine = create_engine("sqlite://")
    listed = ", ".join(f"'{kind}'" for kind in OLD_KINDS)
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE issued_documents (id CHAR(32) PRIMARY KEY, owner_id CHAR(32) NOT NULL, project_id CHAR(32) NOT NULL, kind VARCHAR(32) NOT NULL, "
            "title VARCHAR(255) NOT NULL, number VARCHAR(64) NOT NULL, project_seq INTEGER NOT NULL, template_version VARCHAR(16) NOT NULL, "
            "status VARCHAR(16) NOT NULL, issued_at DATETIME NOT NULL, created_at DATETIME NOT NULL, updated_at DATETIME NOT NULL, "
            f"CONSTRAINT ck_issued_documents_kind CHECK (kind IN ({listed})))"
        ))
        conn.execute(text(INSERT), {"id": "old", "kind": "SETTLEMENT", "number": "ROZL/1", "seq": 1})
    return engine


def engine_0074():
    engine = old_engine()
    run(engine, NAME, "upgrade")
    return engine


def test_revision_chain_and_length():
    module = load_migration(NAME)
    assert module.revision == NAME and module.down_revision == "0073_client_decline" and len(module.revision) <= 32


def test_the_old_row_is_untouched_and_the_new_kind_is_accepted_and_nothing_else_is():
    engine = engine_0074()
    with engine.begin() as conn:
        conn.execute(text(INSERT), {"id": "new", "kind": "MEASUREMENTS", "number": "OBM/1", "seq": 2})
        assert [tuple(r) for r in conn.execute(text("SELECT id, kind FROM issued_documents ORDER BY id"))] == [("new", "MEASUREMENTS"), ("old", "SETTLEMENT")]
    for bad in ("MEASUREMENT", "OBMIAR", ""):
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(text(INSERT), {"id": f"bad-{bad}", "kind": bad, "number": f"X/{bad}", "seq": 9})


def test_the_check_of_the_migration_is_the_check_of_the_model():
    from app.models.issued_document import IssuedDocument

    module = load_migration(NAME)
    model = next(c for c in IssuedDocument.__table__.constraints if getattr(c, "name", None) == "ck_issued_documents_kind")
    assert " ".join(module.KINDS_NEW.split()) == " ".join(str(model.sqltext).split())


def test_downgrade_refuses_while_a_document_exists():
    engine = engine_0074()
    with engine.begin() as conn:
        conn.execute(text(INSERT), {"id": "new", "kind": "MEASUREMENTS", "number": "OBM/1", "seq": 2})
    with pytest.raises(RuntimeError, match="1 journal row"):
        run(engine, NAME, "downgrade")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM issued_documents")).scalar_one() == 2  # nothing was changed


def test_downgrade_without_documents_narrows_the_check_again_and_loses_no_row():
    engine = engine_0074()
    run(engine, NAME, "downgrade")
    with engine.connect() as conn:
        assert [r[0] for r in conn.execute(text("SELECT id FROM issued_documents"))] == ["old"]
    assert "ck_issued_documents_kind" in {c["name"] for c in inspect(engine).get_check_constraints("issued_documents")}
    with pytest.raises(IntegrityError), engine.begin() as conn:  # the old check does not know the new kind
        conn.execute(text(INSERT), {"id": "n", "kind": "MEASUREMENTS", "number": "OBM/2", "seq": 3})
    run(engine, NAME, "upgrade")  # and up again
    with engine.begin() as conn:
        conn.execute(text(INSERT), {"id": "n", "kind": "MEASUREMENTS", "number": "OBM/2", "seq": 3})
