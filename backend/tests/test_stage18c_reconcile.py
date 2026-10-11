"""Stage 18C -- the preferences, the reminders the events imply, the plan of changes to the queue, and the planned dates against the breaks
(pure functions)."""
import uuid
from dataclasses import replace
from datetime import UTC, date, datetime, time, timedelta

import pytest

from app.domain.calendar import schedule as sched
from app.domain.calendar.events import CalendarEvent, EventKind
from app.domain.calendar.prefs import (
    ALLOWED_TIMEZONES,
    CalendarPrefs,
    in_quiet_hours,
    parse_timezone,
)
from app.domain.calendar.reconcile import (
    QueuedReminder,
    desired_reminders,
    leave_quiet_hours,
    local_instant,
    plan_changes,
)
from app.models.work_execution import WorkExecutionStatus as S

P = uuid.UUID("11111111-1111-1111-1111-111111111111")
PREFS = CalendarPrefs()
NOW = datetime(2026, 10, 12, 6, 0, tzinfo=UTC)


def utc(*args):
    return datetime(*args, tzinfo=UTC)


def timed(at, kind=EventKind.BREAK_END, key="k"):
    return CalendarEvent(kind, key, P, at=at)


def day(on, kind=EventKind.DELIVERY_DEADLINE, key="d"):
    return CalendarEvent(kind, key, P, on=on)


# --- the preferences -----------------------------------------------------------------------------------------------------------


def test_quiet_hours_wrap_midnight_and_an_empty_window_is_never_quiet():
    q = (time(21, 0), time(7, 0))
    assert in_quiet_hours(time(21, 0), *q) and in_quiet_hours(time(23, 59), *q) and in_quiet_hours(time(0, 0), *q) and in_quiet_hours(time(6, 59), *q)
    assert not in_quiet_hours(time(7, 0), *q) and not in_quiet_hours(time(12, 0), *q) and not in_quiet_hours(time(20, 59), *q)
    assert in_quiet_hours(time(13, 0), time(12, 0), time(14, 0)) and not in_quiet_hours(time(14, 0), time(12, 0), time(14, 0))  # a window inside a day
    assert not in_quiet_hours(time(3, 0), time(8, 0), time(8, 0))


def test_the_digest_must_be_outside_the_quiet_hours():
    CalendarPrefs(digest_at=time(8, 0))
    for bad in (time(21, 0), time(23, 0), time(6, 30)):
        with pytest.raises(ValueError):
            CalendarPrefs(digest_at=bad)


def test_the_time_zone_comes_from_the_short_list_only():
    assert "Europe/Warsaw" in ALLOWED_TIMEZONES and parse_timezone("Europe/Warsaw").key == "Europe/Warsaw"
    for bad in ("Mars/Olympus", "", "europe/warsaw", "America/New_York"):
        with pytest.raises(ValueError):
            parse_timezone(bad)
    assert all(parse_timezone(name) for name in ALLOWED_TIMEZONES)  # the system knows every zone of the list


def test_which_kinds_send_follows_the_default_and_the_owners_choice_and_the_master_switch():
    assert PREFS.sends(EventKind.BREAK_END) and not PREFS.sends(EventKind.BREAK_START)
    assert CalendarPrefs(kind_overrides={"BREAK_START": True}).sends(EventKind.BREAK_START)
    assert not CalendarPrefs(kind_overrides={"BREAK_END": False}).sends(EventKind.BREAK_END)
    assert not CalendarPrefs(enabled=False, kind_overrides={"BREAK_END": True}).sends(EventKind.BREAK_END)


# --- the reminders the events imply --------------------------------------------------------------------------------------------


def test_a_timed_event_is_sent_at_its_time_in_the_daytime():
    [item] = desired_reminders([timed(utc(2026, 10, 12, 8, 0))], PREFS)  # 10:00 in Warsaw (CEST)
    assert item.send_at == utc(2026, 10, 12, 8, 0) and item.lead_days == 0


def test_an_event_in_the_quiet_hours_waits_for_the_morning():
    [late] = desired_reminders([timed(utc(2026, 10, 12, 20, 30))], PREFS)  # 22:30 -> 07:00 of the next day = 05:00 UTC
    [early] = desired_reminders([timed(utc(2026, 10, 12, 3, 0))], PREFS)  # 05:00 -> 07:00 the same day
    [edge] = desired_reminders([timed(utc(2026, 10, 12, 19, 0))], PREFS)  # 21:00 sharp is already quiet
    assert late.send_at == utc(2026, 10, 13, 5, 0) and early.send_at == utc(2026, 10, 12, 5, 0) and edge.send_at == utc(2026, 10, 13, 5, 0)
    assert leave_quiet_hours(utc(2026, 10, 12, 18, 59), PREFS) == utc(2026, 10, 12, 18, 59)  # 20:59 is not


def test_winter_time_is_one_hour_not_two():
    [item] = desired_reminders([timed(utc(2026, 12, 10, 20, 30))], PREFS)  # CET: 21:30 -> quiet -> 07:00 next day = 06:00 UTC
    assert item.send_at == utc(2026, 12, 11, 6, 0)
    assert local_instant(date(2026, 12, 11), time(8, 0), PREFS.tz) == utc(2026, 12, 11, 7, 0)


def test_the_delivery_deadline_is_announced_a_week_three_days_a_day_ahead_and_on_the_day_in_the_morning_digest():
    items = desired_reminders([day(date(2026, 11, 20))], PREFS)
    assert [(i.lead_days, i.send_at) for i in items] == [
        (7, utc(2026, 11, 13, 7, 0)), (3, utc(2026, 11, 17, 7, 0)), (1, utc(2026, 11, 19, 7, 0)), (0, utc(2026, 11, 20, 7, 0)),
    ]  # 08:00 in Warsaw (CET)
    assert len({i.dedupe_key for i in items}) == 4


def test_the_digest_time_of_the_owner_is_used():
    [item] = desired_reminders([day(date(2026, 10, 20), EventKind.ACCEPTANCE_TERM)], CalendarPrefs(digest_at=time(9, 30)))
    assert item.send_at == utc(2026, 10, 20, 7, 30)  # 09:30 CEST


def test_a_kind_that_does_not_send_gives_nothing_until_the_owner_switches_it_on():
    event = day(date(2026, 10, 20), EventKind.PAYMENT_TERM)
    assert desired_reminders([event], PREFS) == []
    assert len(desired_reminders([event], CalendarPrefs(kind_overrides={"PAYMENT_TERM": True}))) == 1
    assert desired_reminders([timed(utc(2026, 10, 12, 8, 0))], CalendarPrefs(enabled=False)) == []


def test_the_key_names_the_fact_and_the_instant_so_a_moved_fact_is_a_new_key():
    a = desired_reminders([timed(utc(2026, 10, 12, 8, 0))], PREFS)[0].dedupe_key
    b = desired_reminders([timed(utc(2026, 10, 12, 9, 0))], PREFS)[0].dedupe_key
    same = desired_reminders([timed(utc(2026, 10, 12, 8, 0))], PREFS)[0].dedupe_key
    assert a == same != b
    assert len(a) < 255


# --- the plan of changes -------------------------------------------------------------------------------------------------------


def queue_of(items, status="PENDING"):
    return {i.dedupe_key: QueuedReminder(status, i.send_at) for i in items}


def test_a_new_fact_is_inserted_and_one_whose_time_has_passed_is_not():
    ahead = desired_reminders([timed(utc(2026, 10, 12, 8, 0), key="a")], PREFS)
    past = desired_reminders([timed(utc(2026, 10, 12, 5, 0), key="b")], PREFS)  # 07:00 local, before NOW (06:00 UTC = 08:00 local)
    plan = plan_changes(ahead + past, {}, NOW)
    assert [i.dedupe_key for i in plan.insert] == [ahead[0].dedupe_key] and not plan.retime and not plan.cancel and not plan.revive


def test_an_unchanged_object_gives_an_empty_plan():
    desired = desired_reminders([timed(utc(2026, 10, 12, 8, 0), key="a"), day(date(2026, 11, 20))], PREFS)
    assert plan_changes(desired, queue_of(desired), NOW).empty


def test_applying_a_plan_and_planning_again_changes_nothing():
    desired = desired_reminders([timed(utc(2026, 10, 12, 8, 0), key="a"), day(date(2026, 11, 20))], PREFS)
    queue: dict[str, QueuedReminder] = {}
    first = plan_changes(desired, queue, NOW)
    queue.update({i.dedupe_key: QueuedReminder("PENDING", i.send_at) for i in first.insert})
    assert len(first.insert) == 5 and plan_changes(desired, queue, NOW).empty


def test_a_gone_fact_cancels_its_pending_row_but_never_a_sent_one():
    old = desired_reminders([timed(utc(2026, 10, 12, 8, 0), key="a"), timed(utc(2026, 10, 12, 9, 0), key="b")], PREFS)
    queue = {old[0].dedupe_key: QueuedReminder("PENDING", old[0].send_at), old[1].dedupe_key: QueuedReminder("SENT", old[1].send_at)}
    plan = plan_changes([], queue, NOW)
    assert plan.cancel == [old[0].dedupe_key]


@pytest.mark.parametrize("status", ["SENT", "SENDING", "FAILED", "MISSED", "DONE", "SKIPPED"])
def test_a_row_that_is_history_is_never_touched(status):
    item = desired_reminders([timed(utc(2026, 10, 12, 8, 0))], PREFS)[0]
    moved = replace(item, send_at=item.send_at + timedelta(hours=1))
    assert plan_changes([moved], {item.dedupe_key: QueuedReminder(status, item.send_at)}, NOW).empty
    assert plan_changes([], {item.dedupe_key: QueuedReminder(status, item.send_at)}, NOW).empty


def test_a_changed_zone_or_quiet_hour_moves_the_pending_row():
    event = timed(utc(2026, 10, 12, 20, 30))
    before = desired_reminders([event], PREFS)
    after = desired_reminders([event], CalendarPrefs(quiet_from=time(23, 0)))  # 22:30 is no longer quiet
    plan = plan_changes(after, queue_of(before), NOW)
    assert [i.send_at for i in plan.retime] == [utc(2026, 10, 12, 20, 30)] and not plan.insert and not plan.cancel


def test_a_cancelled_row_whose_fact_is_back_is_revived_only_if_still_ahead():
    item = desired_reminders([timed(utc(2026, 10, 12, 8, 0))], PREFS)[0]
    queue = {item.dedupe_key: QueuedReminder("CANCELLED", item.send_at)}
    assert [i.dedupe_key for i in plan_changes([item], queue, NOW).revive] == [item.dedupe_key]
    assert plan_changes([item], queue, utc(2026, 10, 12, 9, 0)).empty


# --- the planned dates against the breaks ---------------------------------------------------------------------------------------


def step(position, *, wait=None, status=S.NOT_STARTED, completed_at=None, planned=None):
    return sched.WorkStep(uuid.uuid4(), position, wait, status, completed_at, planned)


@pytest.mark.parametrize(("hours", "days"), [(None, 0), (0, 0), (1, 1), (8, 1), (24, 1), (25, 2), (48, 2), (49, 3)])
def test_a_break_counts_in_whole_days_rounded_up(hours, days):
    assert sched.break_days(hours) == days


def test_the_earliest_start_after_a_planned_work_adds_its_break():
    monday = date(2026, 10, 12)
    assert sched.earliest_start(step(0, planned=monday)) == monday  # no break: the same day
    assert sched.earliest_start(step(0, wait=24, planned=monday)) == date(2026, 10, 13)
    assert sched.earliest_start(step(0, wait=30, planned=monday)) == date(2026, 10, 14)
    assert sched.earliest_start(step(0, wait=24)) is None  # nothing known


def test_the_earliest_start_after_a_completed_work_is_its_real_ready_time_in_warsaw():
    done = step(0, wait=48, status=S.COMPLETED, completed_at=utc(2026, 10, 12, 10, 0), planned=date(2026, 10, 1))  # the plan is history
    assert sched.earliest_start(done) == date(2026, 10, 14)
    late = step(0, wait=0, status=S.COMPLETED, completed_at=utc(2026, 10, 12, 22, 30))  # 00:30 of the 13th in Warsaw
    assert sched.earliest_start(late) == date(2026, 10, 13)


def test_a_date_before_the_end_of_the_break_is_a_warning_and_on_it_is_not():
    first = step(0, wait=24, planned=date(2026, 10, 12))
    early = step(1, planned=date(2026, 10, 12))
    exact = step(1, planned=date(2026, 10, 13))
    assert [(w.occurrence_key, w.code, w.date) for w in sched.check_schedule([first, early])] == [(early.occurrence_key, sched.BEFORE_BREAK_END, date(2026, 10, 13))]
    assert sched.check_schedule([first, exact]) == []
    assert sched.check_schedule([early, first]) == sched.check_schedule([first, early])  # the order of the list does not matter, the position does


def test_a_completed_work_is_history_and_a_work_without_a_date_is_not_checked():
    first = step(0, wait=24, planned=date(2026, 10, 12))
    done_early = step(1, status=S.COMPLETED, completed_at=utc(2026, 10, 12, 8, 0), planned=date(2026, 10, 12))
    assert sched.check_schedule([first, done_early]) == []
    assert sched.check_schedule([first, step(1)]) == []


def test_the_dates_are_checked_against_the_window_of_the_contract():
    a, b, c = step(0, planned=date(2026, 10, 1)), step(1, planned=date(2026, 10, 15)), step(2, planned=date(2026, 12, 1))
    got = {(w.occurrence_key, w.code) for w in sched.check_schedule([a, b, c], (date(2026, 10, 12), date(2026, 11, 20)))}
    assert got == {(a.occurrence_key, sched.BEFORE_CONTRACT_START), (c.occurrence_key, sched.AFTER_CONTRACT_END)}
    assert sched.check_schedule([a, b, c], (None, None)) == []


def test_the_proposal_follows_the_order_and_the_breaks_on_working_days():
    first, second, third = step(0, wait=24), step(1, wait=24), step(2)
    got = sched.suggest_dates({uuid.uuid4(): [third, first, second]}, date(2026, 10, 9))  # a Friday
    assert got == {first.occurrence_key: date(2026, 10, 9), second.occurrence_key: date(2026, 10, 12), third.occurrence_key: date(2026, 10, 13)}


def test_the_proposal_skips_a_public_holiday_and_starts_a_weekend_on_monday():
    first, second = step(0, wait=24), step(1)
    got = sched.suggest_dates({uuid.uuid4(): [first, second]}, date(2026, 11, 10))  # Tuesday; the 11th is a holiday
    assert got == {first.occurrence_key: date(2026, 11, 10), second.occurrence_key: date(2026, 11, 12)}
    assert sched.suggest_dates({uuid.uuid4(): [first]}, date(2026, 10, 10)) == {first.occurrence_key: date(2026, 10, 12)}


def test_the_proposal_continues_after_a_completed_work_by_its_real_break_and_leaves_it_alone():
    done = step(0, wait=48, status=S.COMPLETED, completed_at=utc(2026, 10, 12, 10, 0))
    next_ = step(1)
    got = sched.suggest_dates({uuid.uuid4(): [done, next_]}, date(2026, 10, 12))
    assert got == {next_.occurrence_key: date(2026, 10, 14)}  # the completed work gets no date


def test_the_surfaces_are_independent_and_the_proposal_never_names_a_day_off():
    a1, a2, b1 = step(0, wait=72), step(1), step(0)
    got = sched.suggest_dates({uuid.uuid4(): [a1, a2], uuid.uuid4(): [b1]}, date(2026, 10, 12))
    assert got[a1.occurrence_key] == got[b1.occurrence_key] == date(2026, 10, 12) and got[a2.occurrence_key] == date(2026, 10, 15)
    from app.domain.calendar.working_days import is_working_day
    start = date(2025, 12, 15)
    for offset in range(120):
        for date_ in sched.suggest_dates({uuid.uuid4(): [step(0, wait=24), step(1, wait=48), step(2)]}, start + timedelta(days=offset)).values():
            assert is_working_day(date_)
