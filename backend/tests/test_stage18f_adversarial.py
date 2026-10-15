"""Stage 18F -- the adversarial check of the calendar: summer and winter time in every zone, the edges of a day and of the quiet hours, damaged data,
two passes meeting on one fact, a term moved after it was announced, an archived surface, the master switch, a flood of own reminders."""
import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import update

from app.domain.calendar import events as ev
from app.domain.calendar.events import CalendarEvent, EventKind
from app.domain.calendar.prefs import ALLOWED_TIMEZONES, CalendarPrefs, parse_timezone
from app.domain.calendar.reconcile import (
    desired_reminders,
    leave_quiet_hours,
    local_instant,
)
from app.domain.calendar.working_days import add_working_days
from app.domain.exceptions import ReminderInvalidError
from app.domain.services import calendar_service as svc_module
from app.domain.services.calendar_dispatcher import CalendarDispatcher
from app.domain.services.calendar_service import CalendarService
from app.models.contract import Contract
from app.models.reminder import Reminder
from app.models.surface import Surface
from tests.conftest import TestingSessionLocal
from tests.test_stage18c_calendar_service import complete, rows, scene, today
from tests.test_stage18d_dispatcher import FakeSender, owner, reminder

P = uuid.UUID("11111111-1111-1111-1111-111111111111")


def prefs_for(zone: str, **kw) -> CalendarPrefs:
    return CalendarPrefs(tz=parse_timezone(zone), tz_name=zone, **kw)


# --- summer and winter time -------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("zone", ALLOWED_TIMEZONES)
def test_the_morning_digest_is_at_the_same_wall_clock_hour_on_every_day_of_two_years_in_every_zone(zone):
    prefs = prefs_for(zone)
    tz = ZoneInfo(zone)
    day = date(2026, 1, 1)
    while day < date(2028, 1, 1):
        items = desired_reminders([CalendarEvent(EventKind.DELIVERY_DEADLINE, "k", P, on=day)], prefs)
        assert [i.lead_days for i in items] == [7, 3, 1, 0]
        sends = [i.send_at for i in items]
        assert sends == sorted(sends) and len(set(sends)) == 4  # strictly ahead, in order
        for item in items:
            local = item.send_at.astimezone(tz)
            assert (local.date(), local.hour, local.minute) == (day - timedelta(days=item.lead_days), 8, 0), (zone, day, item.lead_days)
        day += timedelta(days=1)


@pytest.mark.parametrize("zone", ALLOWED_TIMEZONES)
def test_a_timed_event_in_the_quiet_hours_waits_for_the_end_of_them_and_never_goes_back_in_time(zone):
    prefs = prefs_for(zone)
    tz = ZoneInfo(zone)
    start = datetime(2026, 1, 1, tzinfo=UTC)
    for hour in range(0, 24 * 365 * 2, 5):  # every five hours for two years: across every change of the clock
        instant = start + timedelta(hours=hour, minutes=17)
        moved = leave_quiet_hours(instant, prefs)
        assert moved >= instant and moved - instant < timedelta(hours=13)
        local = moved.astimezone(tz)
        if moved != instant:
            assert (local.hour, local.minute) == (7, 0), (zone, instant)
        else:
            assert not (local.hour >= 21 or local.hour < 7), (zone, instant)


def test_a_time_that_does_not_exist_or_happens_twice_does_not_break_anything():
    # Warsaw: 29 March 2026 02:00 -> 03:00 (02:30 does not exist); 25 October 2026 03:00 -> 02:00 (02:30 happens twice)
    prefs = prefs_for("Europe/Warsaw", quiet_from=time(22, 0), quiet_to=time(2, 30), digest_at=time(12, 0))
    spring = leave_quiet_hours(datetime(2026, 3, 28, 23, 30, tzinfo=UTC), prefs)  # 00:30 local on the 29th, before the gap
    autumn = leave_quiet_hours(datetime(2026, 10, 24, 23, 30, tzinfo=UTC), prefs)  # 01:30 local on the 25th
    assert datetime(2026, 3, 28, 23, 30, tzinfo=UTC) <= spring <= datetime(2026, 3, 29, 3, 0, tzinfo=UTC)
    assert datetime(2026, 10, 24, 23, 30, tzinfo=UTC) <= autumn <= datetime(2026, 10, 25, 3, 0, tzinfo=UTC)
    assert local_instant(date(2026, 3, 29), time(2, 30), prefs.tz).tzinfo is not None  # no exception, an instant


def test_the_working_days_do_not_know_the_clock():
    # the same dates whatever the zone or the night of the change: a term is counted in days
    assert add_working_days(date(2026, 3, 27), 1) == date(2026, 3, 30) and add_working_days(date(2026, 10, 23), 1) == date(2026, 10, 26)


def test_the_day_of_an_instant_flips_at_local_midnight_not_at_utc_midnight():
    event = CalendarEvent(EventKind.BREAK_END, "k", P, at=datetime(2026, 10, 12, 21, 59, 59, 999999, tzinfo=UTC))  # 23:59:59.999999 CEST
    after = CalendarEvent(EventKind.BREAK_END, "k", P, at=datetime(2026, 10, 12, 22, 0, tzinfo=UTC))  # 00:00:00 CEST
    assert (event.day(), after.day()) == (date(2026, 10, 12), date(2026, 10, 13))
    winter = CalendarEvent(EventKind.BREAK_END, "k", P, at=datetime(2026, 12, 12, 23, 0, tzinfo=UTC))  # 00:00 CET
    assert winter.day() == date(2026, 12, 13)


def test_the_edges_of_the_quiet_hours_are_exact():
    prefs = prefs_for("Europe/Warsaw")  # 21:00-07:00
    edge = lambda local: datetime.combine(date(2026, 10, 12), local, tzinfo=ZoneInfo("Europe/Warsaw")).astimezone(UTC)
    assert leave_quiet_hours(edge(time(20, 59, 59, 999999)), prefs) == edge(time(20, 59, 59, 999999))
    assert leave_quiet_hours(edge(time(21, 0)), prefs) == datetime(2026, 10, 13, 7, 0, tzinfo=ZoneInfo("Europe/Warsaw")).astimezone(UTC)
    assert leave_quiet_hours(edge(time(6, 59, 59, 999999)), prefs) == edge(time(7, 0))
    assert leave_quiet_hours(edge(time(7, 0)), prefs) == edge(time(7, 0))


# --- damaged data ------------------------------------------------------------------------------------------------------------------------


def test_a_date_at_the_end_of_time_or_a_huge_term_is_dropped_not_fatal():
    end = date.max  # 31 December 9999: every term after it is not a date
    assert ev.contract_events(ev.ContractDates(P, signed_on=end, price_validity_days=365, consumer=True)) == []  # all three terms overflow
    assert ev.acceptance_events(ev.AcceptanceDates(P, 365, notified_on=end, renotified_on=end)) == []
    assert ev.concealed_events([ev.ConcealedDates(P, "a", notified_on=end)]) == []
    assert ev.downtime_events(ev.DowntimeDates(P, noticed_on=end, need_by=end))[0].ref == "need_by"  # the term that is a date stays
    near = ev.contract_events(ev.ContractDates(P, signed_on=date(9999, 12, 20), consumer=True))
    assert {e.kind for e in near} == {EventKind.PAYMENT_TERM}  # the advance (3 days) still fits, the 14 days of withdrawal do not: what fits is kept


async def test_garbage_in_the_answers_of_a_contract_does_not_stop_the_calendar(async_client, db_session):
    c, wall, keys = await scene(async_client, db_session)
    db_session.add(Contract(
        owner_id=c.user, project_id=c.project, version=1, status="DRAFT", questionnaire_version=1,
        answers={"work_start_date": "2026-13-45", "work_end_date": 20261012, "price_validity_days": 10**12, "customer_appearance_days": "three", "payment_due_days": -5},
    ))
    await db_session.commit()
    await complete(c, wall, keys[0])
    events = await c.svc.events_for_project(c.user, c.project)
    assert {e.kind.value for e in events} == {"BREAK_START", "BREAK_END"}  # the works are still in the calendar, the garbage gives nothing
    assert (await c.svc.agenda(c.user)).items  # and the screen opens
    assert await c.svc.schedule_warnings(c.user, c.project) == []


# --- two passes on one fact (the real race of eight passes was shown on PostgreSQL: a shared SQLite connection cannot model it), a term that moves ---------------------------------------------------------------------------------------------


async def test_a_fact_another_pass_queued_a_moment_ago_is_not_an_error(async_client, db_session):
    c, wall, keys = await scene(async_client, db_session)
    await complete(c, wall, keys[0])
    [existing] = [r for r in await rows(db_session) if r.kind == "BREAK_END"]
    prefs = await c.svc.prefs(c.user)
    event = ev.CalendarEvent(EventKind.BREAK_END, existing.dedupe_key.split("|")[0], c.project, at=existing.event_at.replace(tzinfo=UTC), occurrence_key=keys[0])
    [again] = desired_reminders([event], prefs)
    assert again.dedupe_key == existing.dedupe_key
    await c.svc._insert_new(c.user, [again], prefs)  # the same key, a second time: nothing happens
    await db_session.commit()
    assert len([r for r in await rows(db_session) if r.kind == "BREAK_END"]) == 1


async def test_a_deadline_moved_after_a_week_ahead_notice_was_sent_keeps_the_history_and_announces_the_new_date(async_client, db_session):
    c, _, _ = await scene(async_client, db_session)
    first, second = today() + timedelta(days=30), today() + timedelta(days=45)
    contract = Contract(owner_id=c.user, project_id=c.project, version=1, status="DRAFT", questionnaire_version=1, answers={"work_end_date": first.isoformat()})
    db_session.add(contract)
    await db_session.commit()
    await c.svc.reconcile_project(c.user, c.project)
    await db_session.commit()
    deadline = {r.lead_days: r for r in await rows(db_session, kind="DELIVERY_DEADLINE")}
    assert set(deadline) == {7, 3, 1, 0}
    await db_session.execute(update(Reminder).where(Reminder.id == deadline[7].id).values(status="SENT"))  # the notice a week ahead went out
    contract.answers = {"work_end_date": second.isoformat()}
    await db_session.commit()
    await c.svc.reconcile_project(c.user, c.project)
    await db_session.commit()
    after = await rows(db_session, kind="DELIVERY_DEADLINE")
    by = lambda status, day: sorted(r.lead_days for r in after if r.status == status and r.event_on == day)
    assert by("SENT", first) == [7] and by("CANCELLED", first) == [0, 1, 3]  # what was sent stays; what was not is withdrawn
    assert by("PENDING", second) == [0, 1, 3, 7]  # the new date is announced in full


async def test_a_surface_that_is_archived_takes_its_break_reminder_with_it_and_a_restored_one_brings_it_back(async_client, db_session):
    c, wall, keys = await scene(async_client, db_session)
    await complete(c, wall, keys[0])
    assert [r.status for r in await rows(db_session, kind="BREAK_END")] == ["PENDING"]
    await db_session.execute(update(Surface).where(Surface.id == wall).values(is_archived=True))
    await db_session.commit()
    await c.svc.reconcile_project(c.user, c.project)
    await db_session.commit()
    assert [r.status for r in await rows(db_session, kind="BREAK_END")] == ["CANCELLED"]
    await db_session.execute(update(Surface).where(Surface.id == wall).values(is_archived=False))
    await db_session.commit()
    await c.svc.reconcile_project(c.user, c.project)
    await db_session.commit()
    assert [r.status for r in await rows(db_session, kind="BREAK_END")] == ["PENDING"]  # the same fact: the same row, alive again


async def test_a_full_cycle_over_every_source_twice_changes_nothing_the_second_time(async_client, db_session):
    c, wall, keys = await scene(async_client, db_session)
    await complete(c, wall, keys[0])
    await c.svc.set_planned_date(c.user, c.project, keys[1], today() + timedelta(days=9))
    db_session.add(Contract(owner_id=c.user, project_id=c.project, version=1, status="DRAFT", questionnaire_version=1,
                            answers={"work_start_date": (today() + timedelta(days=5)).isoformat(), "work_end_date": (today() + timedelta(days=40)).isoformat()}))
    await db_session.commit()
    dispatcher = CalendarDispatcher(TestingSessionLocal, FakeSender())
    await dispatcher.reconcile_all()
    first = sorted((r.dedupe_key, r.status, r.send_at) for r in await rows(db_session))
    await dispatcher.reconcile_all()
    await dispatcher.reconcile_all()
    assert sorted((r.dedupe_key, r.status, r.send_at) for r in await rows(db_session)) == first and len(first) >= 8


# --- the master switch, a flood -----------------------------------------------------------------------------------------------------------


async def test_with_the_messages_switched_off_nothing_goes_not_even_the_owners_own_and_it_goes_when_they_are_back(db_session):
    now = datetime(2026, 10, 12, 8, 0, tzinfo=UTC)
    u, p, *_ = await owner(db_session, 900091)
    await CalendarService(db_session).save_settings(
        u.id, timezone="Europe/Warsaw", enabled=False, kind_overrides={}, quiet_from=time(21, 0), quiet_to=time(7, 0), digest_at=time(8, 0), language=None, now=now,
    )
    db_session.add(reminder(u, p, None, None, origin="USER", kind="USER", title="own", params={}, send_at=now - timedelta(minutes=1)))
    await db_session.commit()
    sender = FakeSender()
    dispatcher = CalendarDispatcher(TestingSessionLocal, sender)
    report = await dispatcher.tick(now)
    assert (report.deferred_off, report.claimed, sender.calls) == (1, 0, [])
    await CalendarService(db_session).save_settings(
        u.id, timezone="Europe/Warsaw", enabled=True, kind_overrides={}, quiet_from=time(21, 0), quiet_to=time(7, 0), digest_at=time(8, 0), language=None, now=now,
    )
    await dispatcher.tick(now + timedelta(minutes=2))
    assert [c[1] for c in sender.calls] == ["🔔 own\nKowalski"]


async def test_the_switch_does_not_save_a_reminder_that_is_a_day_late(db_session):
    now = datetime(2026, 10, 12, 8, 0, tzinfo=UTC)
    u, p, *_ = await owner(db_session, 900092)
    await CalendarService(db_session).save_settings(
        u.id, timezone="Europe/Warsaw", enabled=False, kind_overrides={}, quiet_from=time(21, 0), quiet_to=time(7, 0), digest_at=time(8, 0), language=None, now=now,
    )
    db_session.add(reminder(u, p, None, None, origin="USER", kind="USER", title="old", params={}, send_at=now - timedelta(hours=30)))
    await db_session.commit()
    report = await CalendarDispatcher(TestingSessionLocal, FakeSender()).tick(now)
    assert report.missed == 1 and [r.status for r in await rows(db_session)] == ["MISSED"]


async def test_the_own_reminders_of_one_owner_are_limited_and_the_others_are_not_affected(async_client, db_session, monkeypatch):
    c, _, _ = await scene(async_client, db_session)
    monkeypatch.setattr(svc_module, "MAX_OWN_PENDING", 3)
    soon = datetime.now(UTC) + timedelta(hours=2)
    for n in range(3):
        await c.svc.create_reminder(c.user, title=f"r{n}", send_at=soon)
    with pytest.raises(ReminderInvalidError) as caught:
        await c.svc.create_reminder(c.user, title="one too many", send_at=soon)
    assert caught.value.code == "TOO_MANY"
    first = (await rows(db_session, origin="USER"))[0]
    await c.svc.cancel_reminder(c.user, first.id)
    await c.svc.create_reminder(c.user, title="room again", send_at=soon)  # a cancelled one frees a place


async def test_many_reminders_that_must_wait_do_not_hide_the_one_behind_them(db_session, monkeypatch):
    from app.domain.services import calendar_dispatcher as cd

    monkeypatch.setattr(cd, "CLAIM_LIMIT", 5)  # a page of five; thirty automatic reminders wait for the morning in front of one own reminder
    night = datetime(2026, 10, 12, 23, 30, tzinfo=UTC)  # 01:30 in Warsaw: the quiet hours
    u, p, r, s = await owner(db_session, 900093)
    db_session.add_all([reminder(u, p, r, s, send_at=night - timedelta(minutes=60 - n)) for n in range(30)])
    db_session.add(reminder(u, p, None, None, origin="USER", kind="USER", title="own", params={}, send_at=night - timedelta(minutes=1)))
    await db_session.commit()
    sender = FakeSender()
    report = await CalendarDispatcher(TestingSessionLocal, sender).tick(night)
    assert report.deferred_quiet == 30 and [c[1] for c in sender.calls] == ["🔔 own\nKowalski"]
    morning = await CalendarDispatcher(TestingSessionLocal, FakeSender()).tick(night + timedelta(hours=6))
    assert morning.claimed == 30 and {x.status for x in await rows(db_session) if x.origin == "AUTO"} == {"SENT"}  # and they go when the quiet ends


async def test_a_queue_longer_than_a_pass_is_finished_by_the_next_pass_and_nothing_is_taken_twice(db_session, monkeypatch):
    from app.domain.services import calendar_dispatcher as cd

    monkeypatch.setattr(cd, "CLAIM_LIMIT", 4)
    monkeypatch.setattr(cd, "MAX_PAGES", 2)  # a pass reads eight rows at most
    now = datetime(2026, 10, 12, 8, 0, tzinfo=UTC)
    u, p, *_ = await owner(db_session, 900094)
    db_session.add_all([reminder(u, p, None, None, origin="USER", kind="USER", title=f"n{n:02d}", params={}, send_at=now - timedelta(minutes=30 - n)) for n in range(20)])
    await db_session.commit()
    sender = FakeSender()
    dispatcher = CalendarDispatcher(TestingSessionLocal, sender)
    claimed = [(await dispatcher.tick(now)).claimed for _ in range(4)]
    assert claimed == [8, 8, 4, 0] and len(sender.calls) == 20 and len({c[1] for c in sender.calls}) == 20
