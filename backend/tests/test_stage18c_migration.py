"""Stage 18C -- migration 0054: the three tables, what the database itself refuses, and a downgrade that never drops the owner's data."""
import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from app.models.calendar_settings import CalendarSettings
from app.models.reminder import Reminder
from app.models.work_schedule import WorkSchedule
from tests.test_stage16e2_contract import contract_engine, load_migration, run

NAME = "0054_calendar_reminders"

REMINDER = (
    "INSERT INTO reminders (id, owner_id, project_id, origin, kind, ref, title, title_key, params, event_on, event_at, lead_days, send_at, tz, "
    "close_on_status, status, dedupe_key, attempts, created_at, updated_at) VALUES (:id, 'u1', :project, :origin, 'BREAK_END', '', :title, :title_key, '{}', "
    ":event_on, :event_at, :lead, '2026-10-12 08:00:00', 'Europe/Warsaw', :close, :status, :dedupe, :attempts, '2026-10-11', '2026-10-11')"
)
GOOD = {"id": "r1", "project": "p1", "origin": "AUTO", "title": None, "title_key": "calendar.event.break_end", "event_on": None, "event_at": None,
        "lead": 0, "close": None, "status": "PENDING", "dedupe": "k1", "attempts": 0}
SCHEDULE = "INSERT INTO work_schedule (id, owner_id, project_id, occurrence_key, planned_date, created_at, updated_at) VALUES (:id, 'u1', 'p1', :key, '2026-10-12', '2026-10-11', '2026-10-11')"
SETTINGS = ("INSERT INTO calendar_settings (id, owner_id, timezone, enabled, kind_overrides, quiet_from, quiet_to, digest_at, language, created_at, updated_at) "
            "VALUES (:id, :owner, 'Europe/Warsaw', 1, '{}', '21:00:00', '07:00:00', '08:00:00', :language, '2026-10-11', '2026-10-11')")


def engine_0054():
    engine = contract_engine()
    run(engine, NAME, "upgrade")
    return engine


def test_revision_chain_and_length():
    module = load_migration(NAME)
    assert module.revision == NAME and module.down_revision == "0053_downtime_episodes" and len(module.revision) <= 32


def test_the_tables_have_the_columns_of_the_models():
    inspector = inspect(engine_0054())
    for table, model in (("work_schedule", WorkSchedule), ("reminders", Reminder), ("calendar_settings", CalendarSettings)):
        assert {c["name"] for c in inspector.get_columns(table)} == {c.name for c in model.__table__.columns}, table
    assert {i["name"] for i in inspector.get_indexes("reminders")} >= {"ix_reminders_due", "ix_reminders_owner_project", "ix_reminders_occurrence"}


def test_the_database_refuses_what_the_service_never_writes():
    engine = engine_0054()
    with engine.begin() as conn:
        conn.execute(text(REMINDER), GOOD)
        conn.execute(text(REMINDER), {**GOOD, "id": "r2", "origin": "USER", "title": "Zadzwonić", "title_key": None, "dedupe": "k2", "project": None})
        conn.execute(text(REMINDER), {**GOOD, "id": "r3", "dedupe": "k3", "event_on": "2026-10-12", "close": "COMPLETED"})
    for bad in (
        {"id": "b1", "dedupe": "b1", "status": "WAITING"},
        {"id": "b2", "dedupe": "b2", "origin": "OTHER"},
        {"id": "b3", "dedupe": "b3", "origin": "USER", "title": None, "title_key": None},  # an own reminder without words
        {"id": "b4", "dedupe": "b4", "title_key": None},  # a derived one without its text key
        {"id": "b5", "dedupe": "b5", "event_on": "2026-10-12", "event_at": "2026-10-12 08:00:00"},
        {"id": "b6", "dedupe": "b6", "close": "NOT_STARTED"},
        {"id": "b7", "dedupe": "b7", "attempts": -1},
        {"id": "b8", "dedupe": "b8", "lead": -1},
        {"id": "b9", "dedupe": "k1"},  # the same fact twice for one owner
    ):
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(text(REMINDER), {**GOOD, **bad})


def test_one_planned_date_per_work_and_one_settings_row_per_owner_in_a_known_language():
    engine = engine_0054()
    with engine.begin() as conn:
        conn.execute(text(SCHEDULE), {"id": "s1", "key": "k1"})
        conn.execute(text(SETTINGS), {"id": "c1", "owner": "u1", "language": "pl"})
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text(SCHEDULE), {"id": "s2", "key": "k1"})
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text(SETTINGS), {"id": "c2", "owner": "u1", "language": None})
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id) VALUES ('u2')"))
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text(SETTINGS), {"id": "c3", "owner": "u2", "language": "de"})


def test_deleting_an_object_or_an_owner_takes_the_calendar_with_it():
    engine = engine_0054()
    with engine.begin() as conn:
        conn.execute(text(REMINDER), GOOD)
        conn.execute(text(SCHEDULE), {"id": "s1", "key": "k1"})
        conn.execute(text(SETTINGS), {"id": "c1", "owner": "u1", "language": None})
        conn.execute(text("DELETE FROM projects WHERE id = 'p1'"))
        assert conn.execute(text("SELECT count(*) FROM reminders")).scalar_one() == 0
        assert conn.execute(text("SELECT count(*) FROM work_schedule")).scalar_one() == 0
        assert conn.execute(text("SELECT count(*) FROM calendar_settings")).scalar_one() == 1
        conn.execute(text("DELETE FROM users WHERE id = 'u1'"))
        assert conn.execute(text("SELECT count(*) FROM calendar_settings")).scalar_one() == 0


def test_downgrade_refuses_while_a_planned_date_or_an_own_reminder_exists_and_then_works():
    engine = engine_0054()
    with engine.begin() as conn:
        conn.execute(text(SCHEDULE), {"id": "s1", "key": "k1"})
    with pytest.raises(RuntimeError, match="1 planned date"):
        run(engine, NAME, "downgrade")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM work_schedule"))
        conn.execute(text(REMINDER), {**GOOD, "id": "r2", "origin": "USER", "title": "Zadzwonić", "title_key": None, "dedupe": "k2"})
    with pytest.raises(RuntimeError, match="1 own reminder"):
        run(engine, NAME, "downgrade")
    with engine.begin() as conn:  # the derived queue and the settings are not the owner's data: they are rebuilt
        conn.execute(text("DELETE FROM reminders WHERE origin = 'USER'"))
        conn.execute(text(REMINDER), GOOD)
        conn.execute(text(SETTINGS), {"id": "c1", "owner": "u1", "language": None})
    run(engine, NAME, "downgrade")
    names = inspect(engine).get_table_names()
    assert not {"work_schedule", "reminders", "calendar_settings"} & set(names) and "issued_documents" in names
    run(engine, NAME, "upgrade")
