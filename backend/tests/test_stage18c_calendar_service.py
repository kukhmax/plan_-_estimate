"""Stage 18C -- the calendar service on the database: the queue follows the statuses, the contract, the protocols and the settings."""
import logging
import uuid
from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy import select, update

from app.domain.calendar.working_days import add_working_days
from app.domain.exceptions import (
    CalendarSettingsInvalidError,
    ProjectNotFoundError,
    ReminderInvalidError,
    ReminderNotFoundError,
    ScheduleOccurrenceNotFoundError,
)
from app.domain.services.calendar_service import CalendarService
from app.domain.services.project_service import ProjectService
from app.models.acceptance_protocol import AcceptanceProtocol
from app.models.contract import Contract
from app.models.reminder import Reminder
from app.models.work_execution import SurfaceWorkExecution, WorkExecutionStatus
from app.models.work_plan import SurfacePlannedWork
from tests.test_stage13h_bulk_execution import (
    IP,
    NS,
    C,
    _apply,
    _ctx,
    _plan,
    _preview,
    _wall,
)

pytestmark = pytest.mark.asyncio

SETTINGS = {
    "timezone": "Europe/Warsaw", "enabled": True, "kind_overrides": {}, "quiet_from": time(21, 0), "quiet_to": time(7, 0), "digest_at": time(8, 0),
    "language": None,
}


NAIVE = datetime(2099, 1, 1)  # noqa: DTZ001 - naive on purpose: a reminder needs an aware instant


def today() -> date:
    return datetime.now(UTC).date()


def utc(value: datetime | None) -> datetime | None:
    return value if value is None or value.tzinfo else value.replace(tzinfo=UTC)


async def rows(db, **where) -> list[Reminder]:
    stmt = select(Reminder).execution_options(populate_existing=True).order_by(Reminder.created_at, Reminder.dedupe_key)
    for name, value in where.items():
        stmt = stmt.where(getattr(Reminder, name) == value)
    return list((await db.execute(stmt)).scalars())


async def complete(c, surface, key, expected=NS, status=C):
    return await c.exec.transition(c.project, c.room, surface, c.user, key, status=status, expected_status=expected)


async def scene(client, db, waits=None, items=2):
    c = await _ctx(client, db)
    wall = await _wall(c, "A", 0)
    keys = await _plan(c, wall, [c.p1, c.p2, c.p3][:items], waits=waits if waits is not None else {0: 24, 1: 48})
    c.svc = CalendarService(db)
    return c, wall, keys


# --- the break follows the status of the work ----------------------------------------------------------------------------------------


async def test_completing_a_work_with_a_break_queues_the_reminder_of_its_end(async_client, db_session):
    c, wall, keys = await scene(async_client, db_session)
    await complete(c, wall, keys[0])
    [end] = [r for r in await rows(db_session) if r.kind == "BREAK_END"]
    execution = (await db_session.execute(select(SurfaceWorkExecution))).scalar_one()
    assert end.status == "PENDING" and end.origin == "AUTO" and end.occurrence_key == keys[0]
    assert (end.project_id, end.room_id, end.surface_id, end.owner_id) == (c.project, c.room, wall, c.user)
    assert utc(end.event_at) == utc(execution.completed_at) + timedelta(hours=24)
    assert utc(end.send_at) >= utc(end.event_at) and end.tz == "Europe/Warsaw"
    assert end.title_key == "calendar.event.break_end" and end.params == {"hours": 24} and end.lead_days == 0
    assert not [r for r in await rows(db_session) if r.kind == "BREAK_START"]  # the start is in the calendar, not a message


async def test_a_work_without_a_break_queues_nothing(async_client, db_session):
    c, wall, keys = await scene(async_client, db_session, waits={})
    await complete(c, wall, keys[0])
    assert await rows(db_session) == []


async def test_taking_the_completion_back_cancels_it_and_completing_again_queues_a_new_one(async_client, db_session):
    c, wall, keys = await scene(async_client, db_session)
    await complete(c, wall, keys[0])
    await complete(c, wall, keys[0], expected=C, status=IP)
    assert [r.status for r in await rows(db_session)] == ["CANCELLED"]
    await complete(c, wall, keys[0], expected=IP, status=C)
    assert sorted(r.status for r in await rows(db_session)) == ["CANCELLED", "PENDING"]


async def test_the_second_reconciliation_changes_nothing(async_client, db_session):
    c, wall, keys = await scene(async_client, db_session)
    await complete(c, wall, keys[0])
    before = [(r.id, r.status, r.send_at) for r in await rows(db_session)]
    plan = await c.svc.reconcile_project(c.user, c.project)
    assert plan.empty and [(r.id, r.status, r.send_at) for r in await rows(db_session)] == before


async def test_a_changed_break_moves_the_reminder_to_the_new_end(async_client, db_session):
    c, wall, keys = await scene(async_client, db_session)
    await complete(c, wall, keys[0])
    await db_session.execute(update(SurfacePlannedWork).where(SurfacePlannedWork.occurrence_key == keys[0]).values(wait_after_hours=48))
    await db_session.commit()
    await c.svc.reconcile_project(c.user, c.project)
    await db_session.commit()
    by_status = {r.status: r for r in await rows(db_session)}
    execution = (await db_session.execute(select(SurfaceWorkExecution))).scalar_one()
    assert set(by_status) == {"CANCELLED", "PENDING"} and utc(by_status["PENDING"].event_at) == utc(execution.completed_at) + timedelta(hours=48)


async def test_a_sent_reminder_is_history_even_when_the_break_changes_later(async_client, db_session):
    c, wall, keys = await scene(async_client, db_session)
    await complete(c, wall, keys[0])
    await db_session.execute(update(Reminder).values(status="SENT"))
    await db_session.execute(update(SurfacePlannedWork).where(SurfacePlannedWork.occurrence_key == keys[0]).values(wait_after_hours=72))
    await db_session.commit()
    await c.svc.reconcile_project(c.user, c.project)
    await db_session.commit()
    assert sorted(r.status for r in await rows(db_session)) == ["PENDING", "SENT"]  # the sent one stays; the new fact is a new row


async def test_marking_many_walls_at_once_queues_each_break(async_client, db_session):
    c = await _ctx(async_client, db_session)
    a, b, d = await _wall(c, "A", 0), await _wall(c, "B", 1), await _wall(c, "D", 2)
    await _plan(c, a, [c.p1, c.p2], [C, NS], waits={0: 24})
    await _plan(c, b, [c.p1, c.p2], [NS, NS], waits={0: 24})
    await _plan(c, d, [c.p1, c.p2], [NS, NS], waits={0: 12})
    assert {r.surface_id for r in await rows(db_session)} == {a}
    preview = await _preview(c, a)
    applied = await _apply(c, a, preview.json()["expected_source"])
    assert applied.status_code == 200, applied.text
    assert {r.surface_id for r in await rows(db_session, status="PENDING", kind="BREAK_END")} == {a, b, d}


async def test_a_fault_in_the_calendar_never_blocks_marking_a_work_done(async_client, db_session, monkeypatch, caplog):
    c, wall, keys = await scene(async_client, db_session)

    async def broken(self, owner_id, project_id, **kwargs):
        raise RuntimeError("the calendar is broken")

    monkeypatch.setattr(CalendarService, "reconcile_project", broken)
    with caplog.at_level(logging.ERROR):
        view = await complete(c, wall, keys[0])
    assert view.status == WorkExecutionStatus.COMPLETED
    assert (await db_session.execute(select(SurfaceWorkExecution.status))).scalar_one() == WorkExecutionStatus.COMPLETED
    assert "calendar reconciliation after a status change failed" in caplog.text  # not silent


# --- own reminders that wait for a status -----------------------------------------------------------------------------------------


async def own(c, key, close_on, hours=5):
    return await c.svc.create_reminder(
        c.user, title="Zadzwonić do klienta", send_at=datetime.now(UTC) + timedelta(hours=hours), project_id=c.project, occurrence_key=key,
        close_on_status=close_on,
    )


async def test_an_own_reminder_closes_when_the_work_reaches_the_status_it_waited_for(async_client, db_session):
    c, wall, keys = await scene(async_client, db_session, waits={})
    waits_start, waits_done, free = await own(c, keys[0], "IN_PROGRESS"), await own(c, keys[0], "COMPLETED"), await own(c, keys[0], None)
    await complete(c, wall, keys[0], status=IP)
    status = {r.id: r.status for r in await rows(db_session)}
    assert (status[waits_start.id], status[waits_done.id], status[free.id]) == ("DONE", "PENDING", "PENDING")
    await complete(c, wall, keys[0], expected=IP, status=C)
    status = {r.id: r.status for r in await rows(db_session)}
    assert (status[waits_done.id], status[free.id]) == ("DONE", "PENDING")  # an own time without a condition stays


async def test_completing_at_once_closes_both_kinds_of_waiting_reminders(async_client, db_session):
    c, wall, keys = await scene(async_client, db_session, waits={})
    a, b = await own(c, keys[0], "IN_PROGRESS"), await own(c, keys[0], "COMPLETED")
    await complete(c, wall, keys[0])  # NOT_STARTED -> COMPLETED
    assert {r.status for r in await rows(db_session, origin="USER")} == {"DONE"} and {a.id, b.id} == {r.id for r in await rows(db_session, origin="USER")}


async def test_an_own_reminder_is_checked_and_belongs_to_the_owner(async_client, db_session):
    c, _, _ = await scene(async_client, db_session)
    future = datetime.now(UTC) + timedelta(hours=3)
    for bad, code in (({"title": "  "}, "TITLE_REQUIRED"), ({"title": "x" * 121}, "TITLE_TOO_LONG"), ({"send_at": datetime.now(UTC) - timedelta(minutes=1)}, "IN_THE_PAST"),
                      ({"send_at": NAIVE}, "IN_THE_PAST"), ({"close_on_status": "NOT_STARTED"}, "CLOSE_STATUS_INVALID")):
        with pytest.raises(ReminderInvalidError) as error:
            await c.svc.create_reminder(c.user, **{"title": "ok", "send_at": future, **bad})
        assert error.value.code == code
    stranger = uuid.uuid4()
    with pytest.raises(ProjectNotFoundError):
        await c.svc.create_reminder(stranger, title="x", send_at=future, project_id=c.project)
    mine = await c.svc.create_reminder(c.user, title=" Odebrać klucze ", send_at=future)
    assert mine.title == "Odebrać klucze" and mine.project_id is None and mine.origin == "USER" and mine.status == "PENDING"
    with pytest.raises(ReminderNotFoundError):
        await c.svc.cancel_reminder(stranger, mine.id)
    assert (await c.svc.cancel_reminder(c.user, mine.id)).status == "CANCELLED"
    assert (await c.svc.cancel_reminder(c.user, mine.id)).status == "CANCELLED"  # twice is the same
    assert await c.svc.reminders_of(stranger) == []


# --- the object, the settings ------------------------------------------------------------------------------------------------------


async def test_archiving_an_object_cancels_its_reminders_and_restoring_brings_back_the_derived_ones_only(async_client, db_session):
    c, wall, keys = await scene(async_client, db_session)
    await complete(c, wall, keys[0])
    mine = await own(c, None, None)
    await ProjectService(db_session).archive_project(c.project, c.user)
    assert {r.status for r in await rows(db_session)} == {"CANCELLED"}
    await ProjectService(db_session).restore_project(c.project, c.user)
    status = {r.origin: r.status for r in await rows(db_session)}
    assert status == {"AUTO": "PENDING", "USER": "CANCELLED"}  # the owner's own reminder is not revived behind their back
    assert mine.id in {r.id for r in await rows(db_session, origin="USER")}


async def test_the_settings_are_saved_and_switch_the_queue(async_client, db_session):
    c, wall, keys = await scene(async_client, db_session)
    await c.svc.save_settings(c.user, **{**SETTINGS, "timezone": "Europe/Berlin", "language": "ru"})
    await complete(c, wall, keys[0])
    [end] = await rows(db_session, kind="BREAK_END")
    assert end.tz == "Europe/Berlin" and (await c.svc.settings_row(c.user)).language == "ru"
    await c.svc.save_settings(c.user, **{**SETTINGS, "enabled": False})
    assert [r.status for r in await rows(db_session)] == ["CANCELLED"]
    await c.svc.save_settings(c.user, **SETTINGS)
    assert [r.status for r in await rows(db_session)] == ["PENDING"]  # the same fact comes back, the same row


async def test_the_owner_may_switch_a_kind_off_and_the_break_reminder_goes(async_client, db_session):
    c, wall, keys = await scene(async_client, db_session)
    await complete(c, wall, keys[0])
    await c.svc.save_settings(c.user, **{**SETTINGS, "kind_overrides": {"BREAK_END": False}})
    assert [r.status for r in await rows(db_session)] == ["CANCELLED"]


@pytest.mark.parametrize(
    ("change", "code"),
    [({"timezone": "Mars/Olympus"}, "TIMEZONE_UNKNOWN"), ({"language": "de"}, "LANGUAGE_UNKNOWN"), ({"kind_overrides": {"NOPE": True}}, "KIND_UNKNOWN"),
     ({"kind_overrides": {"BREAK_END": "yes"}}, "KIND_UNKNOWN"), ({"digest_at": time(22, 0)}, "DIGEST_IN_QUIET_HOURS")],
)
async def test_wrong_settings_are_refused_with_a_code_and_nothing_is_saved(async_client, db_session, change, code):
    c, _, _ = await scene(async_client, db_session)
    with pytest.raises(CalendarSettingsInvalidError) as error:
        await c.svc.save_settings(c.user, **{**SETTINGS, **change})
    assert error.value.code == code and await c.svc.settings_row(c.user) is None


async def test_nothing_of_another_owner_is_reachable(async_client, db_session):
    c, _, keys = await scene(async_client, db_session)
    stranger = uuid.uuid4()
    for call in (c.svc.reconcile_project(stranger, c.project), c.svc.events_for_project(stranger, c.project), c.svc.planned_dates(stranger, c.project),
                 c.svc.schedule_warnings(stranger, c.project), c.svc.set_planned_date(stranger, c.project, keys[0], date(2030, 1, 7))):
        with pytest.raises(ProjectNotFoundError):
            await call


# --- the dates of the contract and of the protocols -----------------------------------------------------------------------------------


async def test_the_dates_of_a_signed_contract_and_an_acceptance_become_reminders_and_a_held_acceptance_takes_its_term_away(async_client, db_session):
    c, _, _ = await scene(async_client, db_session)
    now_day = today()
    start, end = now_day + timedelta(days=10), now_day + timedelta(days=40)
    db_session.add(Contract(
        owner_id=c.user, project_id=c.project, version=1, status="SIGNED", questionnaire_version=1, issued_at=datetime.now(UTC), snapshot={},
        document_html="<p/>", signed_on=now_day,
        answers={"work_start_date": start.isoformat(), "work_end_date": end.isoformat(), "customer_appearance_days": 3, "price_validity_days": 30},
    ))
    notified = now_day + timedelta(days=1)
    acceptance = AcceptanceProtocol(owner_id=c.user, project_id=c.project, sequence=1, status="DRAFT", notified_on=notified)
    db_session.add(acceptance)
    await db_session.commit()
    await c.svc.reconcile_project(c.user, c.project)
    await db_session.commit()
    got = {(r.kind, r.ref, r.lead_days): r for r in await rows(db_session)}
    assert {(k, lead) for k, _, lead in got if k == "DELIVERY_DEADLINE"} == {("DELIVERY_DEADLINE", n) for n in (7, 3, 1, 0)}
    assert got[("DELIVERY_DEADLINE", "", 0)].event_on == end and got[("OBJECT_END", "", 0)].event_on == end and got[("OBJECT_START", "", 0)].event_on == start
    assert got[("ACCEPTANCE_TERM", "appearance", 0)].event_on == add_working_days(notified, 3)
    assert not [k for k in got if k[0] in ("PAYMENT_TERM", "PRICE_VALIDITY_END", "WITHDRAWAL_END")]  # off by default
    await db_session.execute(update(AcceptanceProtocol).values(held_on=now_day))
    await db_session.commit()
    await c.svc.reconcile_project(c.user, c.project)
    await db_session.commit()
    assert {r.status for r in await rows(db_session, kind="ACCEPTANCE_TERM")} == {"CANCELLED"}


# --- the planned dates ---------------------------------------------------------------------------------------------------------------


async def test_a_planned_date_queues_the_start_of_the_room_and_clearing_it_cancels(async_client, db_session):
    c, _, keys = await scene(async_client, db_session)
    day = today() + timedelta(days=20)
    await c.svc.set_planned_date(c.user, c.project, keys[0], day, note="po schnięciu")
    assert await c.svc.planned_dates(c.user, c.project) == {keys[0]: day}
    [start] = await rows(db_session, kind="WORK_START")
    assert start.event_on == day and start.room_id == c.room and start.status == "PENDING"
    assert utc(start.send_at).astimezone(CalendarService.prefs_of(None).tz).time() == time(8, 0)  # the morning digest
    await c.svc.set_planned_date(c.user, c.project, keys[0], day + timedelta(days=1))  # the same row of the schedule, moved
    assert sorted(r.status for r in await rows(db_session, kind="WORK_START")) == ["CANCELLED", "PENDING"]
    await c.svc.set_planned_date(c.user, c.project, keys[0], None)
    assert await c.svc.planned_dates(c.user, c.project) == {} and {r.status for r in await rows(db_session, kind="WORK_START")} == {"CANCELLED"}
    with pytest.raises(ScheduleOccurrenceNotFoundError):
        await c.svc.set_planned_date(c.user, c.project, uuid.uuid4(), day)


async def test_a_date_before_the_end_of_the_break_is_a_warning_and_the_proposal_follows_the_breaks(async_client, db_session):
    c, _, keys = await scene(async_client, db_session)
    monday = today() + timedelta(days=(7 - today().weekday()) % 7 or 7)  # the next Monday
    await c.svc.set_planned_date(c.user, c.project, keys[0], monday)
    await c.svc.set_planned_date(c.user, c.project, keys[1], monday)  # the first work has a break of 24 h
    [warning] = await c.svc.schedule_warnings(c.user, c.project)
    assert (warning.occurrence_key, warning.code, warning.date) == (keys[1], "BEFORE_BREAK_END", monday + timedelta(days=1))
    assert await c.svc.suggest_dates(c.user, c.project, monday) == {keys[0]: monday, keys[1]: monday + timedelta(days=1)}
    assert await c.svc.suggest_dates(c.user, c.project, monday, room_id=uuid.uuid4()) == {}  # another room has no works
    assert await c.svc.planned_dates(c.user, c.project) == {keys[0]: monday, keys[1]: monday}  # the proposal saved nothing


async def test_the_dates_outside_the_contract_are_warned_about(async_client, db_session):
    c, _, keys = await scene(async_client, db_session)
    now_day = today()
    db_session.add(Contract(
        owner_id=c.user, project_id=c.project, version=1, status="DRAFT", questionnaire_version=1,
        answers={"work_start_date": (now_day + timedelta(days=10)).isoformat(), "work_end_date": (now_day + timedelta(days=20)).isoformat()},
    ))
    await db_session.commit()
    await c.svc.set_planned_date(c.user, c.project, keys[0], now_day + timedelta(days=5))
    await c.svc.set_planned_date(c.user, c.project, keys[1], now_day + timedelta(days=30))
    codes = {(w.occurrence_key, w.code) for w in await c.svc.schedule_warnings(c.user, c.project)}
    assert {(keys[0], "BEFORE_CONTRACT_START"), (keys[1], "AFTER_CONTRACT_END")} <= codes


async def test_the_dates_come_from_the_signed_contract_not_from_a_newer_draft_or_an_archived_version(async_client, db_session):
    c, _, _ = await scene(async_client, db_session)
    now_day = today()
    signed_end, draft_end, old_end = now_day + timedelta(days=30), now_day + timedelta(days=50), now_day + timedelta(days=70)

    def contract(version, status, end):
        return Contract(
            owner_id=c.user, project_id=c.project, version=version, status=status, questionnaire_version=1, answers={"work_end_date": end.isoformat()},
            **({"issued_at": datetime.now(UTC), "snapshot": {}, "document_html": "<p/>"} if status != "DRAFT" else {}), **({"signed_on": now_day} if status == "SIGNED" else {}),
        )

    db_session.add_all([contract(1, "ARCHIVED", old_end), contract(2, "SIGNED", signed_end), contract(3, "DRAFT", draft_end)])
    await db_session.commit()
    ends = {e.on for e in await c.svc.events_for_project(c.user, c.project) if e.kind.value == "OBJECT_END"}
    assert ends == {signed_end}
