"""Invoices and advances IA-6b -- migration 0061: the column, the checks, the rows it leaves alone, a downgrade that never drops a written category."""
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from tests.test_stage16e2_contract import load_migration, run

NAME = "0061_expense_category"
INSERT = (
    "INSERT INTO project_payments (id, kind, title, amount_gross, occurred_on, is_archived, category) "
    "VALUES (:id, :kind, 'x', 1, '2026-10-18', 0, :category)"
)


def old_engine():
    """The table as 0060 leaves it (the columns this migration cares about) with an old expense and an old invoice."""
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE project_payments (id CHAR(32) PRIMARY KEY, kind VARCHAR(16) NOT NULL, title VARCHAR(500) NOT NULL, amount_gross NUMERIC(12, 2) NOT NULL, "
            "occurred_on DATE NOT NULL, is_archived BOOLEAN NOT NULL DEFAULT 0, "
            "CONSTRAINT ck_project_payments_kind CHECK (kind IN ('INVOICE', 'ADVANCE', 'PAYMENT', 'EXPENSE')))"
        ))
        conn.execute(text("INSERT INTO project_payments (id, kind, title, amount_gross, occurred_on) VALUES ('old-expense', 'EXPENSE', 'x', 5, '2026-10-01')"))
        conn.execute(text("INSERT INTO project_payments (id, kind, title, amount_gross, occurred_on) VALUES ('old-invoice', 'INVOICE', 'x', 5, '2026-10-01')"))
    return engine


def engine_0061():
    engine = old_engine()
    run(engine, NAME, "upgrade")
    return engine


def test_revision_chain_and_length():
    module = load_migration(NAME)
    assert module.revision == NAME and module.down_revision == "0060_settlement_document" and len(module.revision) <= 32


def test_old_rows_are_untouched_and_have_no_category():
    engine = engine_0061()
    with engine.connect() as conn:
        rows = [tuple(r) for r in conn.execute(text("SELECT id, kind, category FROM project_payments ORDER BY id"))]
    assert rows == [("old-expense", "EXPENSE", None), ("old-invoice", "INVOICE", None)]
    assert "category" in {c["name"] for c in inspect(engine).get_columns("project_payments")}


def test_a_known_category_is_accepted_on_an_expense_only():
    engine = engine_0061()
    with engine.begin() as conn:
        for number, name in enumerate(("MATERIALS", "TOOLS", "TRANSPORT", "SERVICES", "OTHER")):
            conn.execute(text(INSERT), {"id": f"e{number}", "kind": "EXPENSE", "category": name})
        conn.execute(text(INSERT), {"id": "n", "kind": "EXPENSE", "category": None})
        conn.execute(text(INSERT), {"id": "i", "kind": "INVOICE", "category": None})
    for number, (kind, category) in enumerate([("EXPENSE", "FUEL"), ("EXPENSE", "materials"), ("INVOICE", "MATERIALS"), ("ADVANCE", "OTHER"), ("PAYMENT", "TOOLS")]):
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(text(INSERT), {"id": f"bad{number}", "kind": kind, "category": category})


def test_downgrade_refuses_while_a_category_is_written_and_changes_nothing():
    engine = engine_0061()
    with engine.begin() as conn:
        conn.execute(text(INSERT), {"id": "e", "kind": "EXPENSE", "category": "TOOLS"})
    with pytest.raises(RuntimeError, match="1 expense"):
        run(engine, NAME, "downgrade")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT category FROM project_payments WHERE id = 'e'")).scalar_one() == "TOOLS"


def test_downgrade_without_a_written_category_drops_the_column_and_loses_no_row_and_up_again_works():
    engine = engine_0061()
    run(engine, NAME, "downgrade")
    assert "category" not in {c["name"] for c in inspect(engine).get_columns("project_payments")}
    assert {c["name"] for c in inspect(engine).get_check_constraints("project_payments")} == {"ck_project_payments_kind"}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM project_payments")).scalar_one() == 2
    run(engine, NAME, "upgrade")
    with engine.begin() as conn:
        conn.execute(text(INSERT), {"id": "again", "kind": "EXPENSE", "category": "OTHER"})
