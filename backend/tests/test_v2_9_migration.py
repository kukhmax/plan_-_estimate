"""V2-9 -- migration 0075: the stages, the hours, the stage of a payment and the hourly rate; what the database refuses; a downgrade that never drops the owner's input."""
import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from tests.test_stage16e2_contract import load_migration, run

NAME = "0075_payment_schedule"
NOW = "2026-10-28 10:00:00"


def old_engine():
    """The tables 0074 leaves that this migration touches, with a payment of each kind and a profile."""
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.execute(text("CREATE TABLE users (id CHAR(32) PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE projects (id CHAR(32) PRIMARY KEY)"))
        conn.execute(text(
            "CREATE TABLE project_payments (id CHAR(32) PRIMARY KEY, owner_id CHAR(32) NOT NULL, project_id CHAR(32) NOT NULL, kind VARCHAR(16) NOT NULL, "
            "title TEXT NOT NULL, amount_gross NUMERIC(12,2) NOT NULL, occurred_on DATE NOT NULL, "
            "CONSTRAINT ck_project_payments_kind CHECK (kind IN ('INVOICE', 'ADVANCE', 'PAYMENT', 'EXPENSE')))"
        ))
        conn.execute(text("CREATE TABLE executor_profiles (id CHAR(32) PRIMARY KEY, owner_id CHAR(32) NOT NULL, name VARCHAR(255) NOT NULL)"))
        conn.execute(text("INSERT INTO users (id) VALUES ('u1')"))
        conn.execute(text("INSERT INTO projects (id) VALUES ('p1')"))
        conn.execute(text("INSERT INTO executor_profiles (id, owner_id, name) VALUES ('e1', 'u1', 'Jan')"))
        for pid, kind in (("a", "ADVANCE"), ("i", "INVOICE"), ("x", "EXPENSE")):
            conn.execute(text("INSERT INTO project_payments VALUES (:id, 'u1', 'p1', :kind, 't', 10, '2026-10-01')"), {"id": pid, "kind": kind})
    return engine


def engine_0075():
    engine = old_engine()
    run(engine, NAME, "upgrade")
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
    return engine


def stage(conn, sid="s1", percent="30", amount=None, project="p1"):
    conn.execute(
        text("INSERT INTO payment_stages (id, owner_id, project_id, position, title, percent, amount, created_at, updated_at) VALUES (:id, 'u1', :p, 0, 't', :pc, :am, :n, :n)"),
        {"id": sid, "p": project, "pc": percent, "am": amount, "n": NOW},
    )


def test_revision_chain_and_length():
    module = load_migration(NAME)
    assert module.revision == NAME and module.down_revision == "0074_measurements_document" and len(module.revision) <= 32


def test_upgrade_adds_the_tables_and_the_columns_and_leaves_every_row():
    engine = engine_0075()
    names = inspect(engine)
    assert {"payment_stages", "work_hours"} <= set(names.get_table_names())
    assert "stage_id" in {c["name"] for c in names.get_columns("project_payments")} and "hourly_rate" in {c["name"] for c in names.get_columns("executor_profiles")}
    with engine.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM project_payments")).scalar_one() == 3
        assert conn.execute(text("SELECT hourly_rate FROM executor_profiles")).scalar_one() is None
        assert conn.execute(text("SELECT count(*) FROM project_payments WHERE stage_id IS NOT NULL")).scalar_one() == 0


@pytest.mark.parametrize("percent, amount", [(None, None), ("30", "100"), ("0", None), ("100.01", None), (None, "0")])
def test_a_stage_is_a_percent_or_an_amount_in_range_and_nothing_else(percent, amount):
    engine = engine_0075()
    with pytest.raises(IntegrityError), engine.begin() as conn:
        stage(conn, percent=percent, amount=amount)


def test_a_good_stage_is_accepted_and_an_unknown_object_is_not():
    engine = engine_0075()
    with engine.begin() as conn:
        stage(conn, "s1", "30"), stage(conn, "s2", None, "1500.50")
        assert conn.execute(text("SELECT count(*) FROM payment_stages")).scalar_one() == 2
    with pytest.raises(IntegrityError), engine.begin() as conn:
        stage(conn, "s3", "10", project="nope")


def test_only_an_advance_or_a_payment_can_have_a_stage_and_deleting_the_stage_keeps_the_money():
    engine = engine_0075()
    with engine.begin() as conn:
        stage(conn)
        conn.execute(text("UPDATE project_payments SET stage_id = 's1' WHERE id = 'a'"))
    for kind_id in ("i", "x"):
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(text("UPDATE project_payments SET stage_id = 's1' WHERE id = :id"), {"id": kind_id})
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text("UPDATE project_payments SET stage_id = 'nope' WHERE id = 'a'"))
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.execute(text("DELETE FROM payment_stages WHERE id = 's1'"))
        assert [tuple(r) for r in conn.execute(text("SELECT id, stage_id FROM project_payments WHERE id = 'a'"))] == [("a", None)]


@pytest.mark.parametrize("hours", ["0", "-1", "24.5"])
def test_hours_are_between_zero_and_a_day(hours):
    engine = engine_0075()
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text("INSERT INTO work_hours VALUES ('h', 'u1', 'p1', '2026-10-28', :h, NULL, :n, :n)"), {"h": hours, "n": NOW})
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO work_hours VALUES ('h', 'u1', 'p1', '2026-10-28', 24, NULL, :n, :n)"), {"n": NOW})


def test_the_rate_is_positive_or_empty():
    engine = engine_0075()
    with engine.begin() as conn:
        conn.execute(text("UPDATE executor_profiles SET hourly_rate = 85.5"))
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text("UPDATE executor_profiles SET hourly_rate = 0"))


def test_the_things_of_an_object_go_with_it():
    engine = engine_0075()
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        stage(conn)
        conn.execute(text("INSERT INTO work_hours VALUES ('h', 'u1', 'p1', '2026-10-28', 3, NULL, :n, :n)"), {"n": NOW})
        conn.execute(text("DELETE FROM project_payments"))
        conn.execute(text("DELETE FROM projects WHERE id = 'p1'"))
        assert conn.execute(text("SELECT count(*) FROM payment_stages")).scalar_one() == 0 and conn.execute(text("SELECT count(*) FROM work_hours")).scalar_one() == 0


def test_the_downgrade_refuses_while_the_owners_input_exists_and_then_restores_the_old_shape():
    engine = engine_0075()
    with engine.begin() as conn:
        stage(conn)
    with pytest.raises(RuntimeError, match="never dropped silently"):
        run(engine, NAME, "downgrade")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM payment_stages"))
    run(engine, NAME, "downgrade")
    names = inspect(engine)
    assert not ({"payment_stages", "work_hours"} & set(names.get_table_names()))
    assert "stage_id" not in {c["name"] for c in names.get_columns("project_payments")} and "hourly_rate" not in {c["name"] for c in names.get_columns("executor_profiles")}
    with engine.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM project_payments")).scalar_one() == 3
    run(engine, NAME, "upgrade")  # and up again


def test_the_model_is_what_the_migration_makes():
    from app.models.payment_stage import PaymentStage, WorkHour

    engine = engine_0075()
    names = inspect(engine)
    for model in (PaymentStage, WorkHour):
        assert {c["name"] for c in names.get_columns(model.__tablename__)} == {c.name for c in model.__table__.columns}
        migration_checks = {c["name"] for c in names.get_check_constraints(model.__tablename__)}
        assert migration_checks == {c.name for c in model.__table__.constraints if getattr(c, "name", None) and c.__class__.__name__ == "CheckConstraint"}
