"""Stage 16C: the journal of issued documents accepts the technological card (migration 0041)."""
import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

BACKEND = Path(__file__).resolve().parents[1]
VERSIONS = BACKEND / "alembic" / "versions"

INSERT = (
    "INSERT INTO issued_documents (id, owner_id, project_id, kind, title, number, project_seq, template_version, status, issued_at) "
    "VALUES (:id, 'u1', 'p1', :kind, 't', :number, :seq, '1', 'SENT', '2026-10-09')"
)


def load(name: str):
    spec = importlib.util.spec_from_file_location(name, VERSIONS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(engine, name: str, direction: str):
    module = load(name)
    with engine.begin() as conn:
        module.op = Operations(MigrationContext.configure(conn))
        getattr(module, direction)()


def journal_engine():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id CHAR(32) PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE projects (id CHAR(32) PRIMARY KEY)"))
        conn.execute(text("INSERT INTO users (id) VALUES ('u1')"))
        conn.execute(text("INSERT INTO projects (id) VALUES ('p1')"))
    run(engine, "0038_issued_documents", "upgrade")
    return engine


def test_revision_chain():
    module = load("0041_issued_documents_tech_card")
    assert module.revision == "0041_issued_documents_tech_card" and module.down_revision == "0040_project_representatives"


def test_before_the_migration_the_database_refuses_a_card_after_it_accepts_it():
    engine = journal_engine()
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text(INSERT), {"id": "a", "kind": "TECH_CARD", "number": "KART/1", "seq": 1})
    run(engine, "0041_issued_documents_tech_card", "upgrade")
    with engine.begin() as conn:
        conn.execute(text(INSERT), {"id": "a", "kind": "TECH_CARD", "number": "KART/1", "seq": 1})
        conn.execute(text(INSERT), {"id": "b", "kind": "ESTIMATE", "number": "KOSZ/1", "seq": 2})
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text(INSERT), {"id": "c", "kind": "CONTRACT", "number": "UMOWA/1", "seq": 3})


def test_the_migration_keeps_the_other_rules_of_the_journal():
    engine = journal_engine()
    run(engine, "0041_issued_documents_tech_card", "upgrade")
    insp = inspect(engine)
    assert {c["name"] for c in insp.get_check_constraints("issued_documents")} == {
        "ck_issued_documents_kind", "ck_issued_documents_status", "ck_issued_documents_seq_positive", "ck_issued_documents_number_not_empty"}
    assert {c["name"] for c in insp.get_unique_constraints("issued_documents")} == {
        "uq_issued_documents_owner_number", "uq_issued_documents_project_seq"}
    assert [i["name"] for i in insp.get_indexes("issued_documents")] == ["ix_issued_documents_project_issued"]


def test_downgrade_narrows_the_check_and_refuses_to_lose_a_card():
    engine = journal_engine()
    run(engine, "0041_issued_documents_tech_card", "upgrade")
    with engine.begin() as conn:
        conn.execute(text(INSERT), {"id": "a", "kind": "TECH_CARD", "number": "KART/1", "seq": 1})
        conn.execute(text(INSERT), {"id": "b", "kind": "PHOTO_REPORT", "number": "FOTO/1", "seq": 2})
    with pytest.raises(RuntimeError, match="1 technological card"):
        run(engine, "0041_issued_documents_tech_card", "downgrade")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM issued_documents WHERE kind = 'TECH_CARD'"))
    run(engine, "0041_issued_documents_tech_card", "downgrade")
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text(INSERT), {"id": "c", "kind": "TECH_CARD", "number": "KART/2", "seq": 3})
    with engine.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM issued_documents")).scalar_one() == 1  # the photo report survived
