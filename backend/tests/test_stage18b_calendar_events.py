"""Stage 18B -- the events derived from the data of an object (pure functions, no database)."""
import random
import re
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.domain.calendar import events as ev
from app.domain.calendar.events import (
    AcceptanceDates,
    AdjacentPeriod,
    BreakInput,
    CalendarEvent,
    ConcealedDates,
    ContractDates,
    DowntimeDates,
    EventKind,
    PlannedWork,
    acceptance_events,
    adjacent_events,
    break_events,
    concealed_events,
    contract_events,
    downtime_events,
    lead_days,
    schedule_events,
    sort_events,
)
from app.domain.contracts.clauses import load_clause_catalog
from app.domain.rules.work_execution_rules import derive_ready_after
from app.models.work_execution import WorkExecutionStatus as S

P = uuid.UUID("11111111-1111-1111-1111-111111111111")


def kinds(events):
    return [(e.kind, e.ref, e.on or e.at) for e in events]


# --- technological breaks ------------------------------------------------------------------------------------------------------


def test_a_completed_work_with_a_break_gives_its_start_and_its_end():
    done = datetime(2026, 10, 12, 10, 0, tzinfo=UTC)
    key = uuid.uuid4()
    events = break_events([BreakInput(P, key, S.COMPLETED, done, 48)])
    assert [(e.kind, e.at) for e in events] == [(EventKind.BREAK_START, done), (EventKind.BREAK_END, datetime(2026, 10, 14, 10, 0, tzinfo=UTC))]
    assert events[1].at == derive_ready_after(S.COMPLETED, done, 48)  # the one truth of Stage 13 (D-H12)
    assert all(e.occurrence_key == key and e.params == {"hours": 48} for e in events)


@pytest.mark.parametrize(
    ("status", "completed_at", "hours"),
    [(S.IN_PROGRESS, datetime(2026, 10, 12, tzinfo=UTC), 24), (S.NOT_STARTED, None, 24), (S.COMPLETED, datetime(2026, 10, 12, tzinfo=UTC), None),
     (S.COMPLETED, datetime(2026, 10, 12, tzinfo=UTC), 0)],
)
def test_no_break_event_without_a_completed_work_and_a_break(status, completed_at, hours):
    assert break_events([BreakInput(P, uuid.uuid4(), status, completed_at, hours)]) == []


def test_the_keys_are_stable_and_distinct():
    a, b = uuid.uuid4(), uuid.uuid4()
    inputs = [BreakInput(P, a, S.COMPLETED, datetime(2026, 10, 12, tzinfo=UTC), 24), BreakInput(P, b, S.COMPLETED, datetime(2026, 10, 12, tzinfo=UTC), 24)]
    first, second = break_events(inputs), break_events(inputs)
    assert [e.key for e in first] == [e.key for e in second]
    assert len({e.key for e in first}) == 4


# --- planned dates -------------------------------------------------------------------------------------------------------------


def test_a_room_has_the_first_and_the_last_planned_day():
    room, other = uuid.uuid4(), uuid.uuid4()
    planned = [PlannedWork(P, uuid.uuid4(), date(2026, 10, 14), room), PlannedWork(P, uuid.uuid4(), date(2026, 10, 12), room),
               PlannedWork(P, uuid.uuid4(), date(2026, 10, 20), room), PlannedWork(P, uuid.uuid4(), date(2026, 10, 13), other)]
    events = {(e.kind, e.room_id): e.on for e in schedule_events(planned)}
    assert events == {(EventKind.WORK_START, room): date(2026, 10, 12), (EventKind.WORK_END, room): date(2026, 10, 20),
                      (EventKind.WORK_START, other): date(2026, 10, 13)}  # one day: no end event


# --- the contract --------------------------------------------------------------------------------------------------------------


def test_the_dates_of_the_contract():
    contract = ContractDates(P, signed_on=date(2026, 10, 1), work_start_date=date(2026, 10, 12), work_end_date=date(2026, 11, 20),
                             price_validity_days=30, consumer=True)
    got = {(e.kind, e.ref): e.on for e in contract_events(contract)}
    assert got == {
        (EventKind.OBJECT_START, ""): date(2026, 10, 12), (EventKind.OBJECT_END, ""): date(2026, 11, 20),
        (EventKind.DELIVERY_DEADLINE, ""): date(2026, 11, 20),
        (EventKind.PAYMENT_TERM, "advance"): date(2026, 10, 4),  # three calendar days from the conclusion, a Sunday as it falls
        (EventKind.PRICE_VALIDITY_END, ""): date(2026, 10, 31),
        (EventKind.WITHDRAWAL_END, ""): date(2026, 10, 15),
    }


def test_the_right_of_withdrawal_is_only_a_consumers_and_nothing_without_dates():
    base = {"signed_on": date(2026, 10, 1)}
    assert EventKind.WITHDRAWAL_END not in {e.kind for e in contract_events(ContractDates(P, consumer=False, **base))}
    assert contract_events(ContractDates(P)) == []
    assert {e.kind for e in contract_events(ContractDates(P, work_end_date=date(2026, 11, 20)))} == {EventKind.OBJECT_END, EventKind.DELIVERY_DEADLINE}


# --- the protocols -------------------------------------------------------------------------------------------------------------


def test_the_acceptance_terms_count_working_days_and_stop_when_it_was_held():
    got = {e.ref: e.on for e in acceptance_events(AcceptanceDates(P, 3, notified_on=date(2026, 10, 5), renotified_on=date(2026, 10, 9)))}
    assert got == {"appearance": date(2026, 10, 8), "reinvite": date(2026, 10, 14)}  # Mon + 3 = Thu; Fri + 3 = Wed
    over_a_holiday = acceptance_events(AcceptanceDates(P, 3, notified_on=date(2026, 11, 9)))
    assert over_a_holiday[0].on == date(2026, 11, 13)  # 11 November is a day off
    assert acceptance_events(AcceptanceDates(P, 3, notified_on=date(2026, 10, 5), renotified_on=date(2026, 10, 9), held_on=date(2026, 10, 10))) == []
    assert acceptance_events(AcceptanceDates(P, None, notified_on=date(2026, 10, 5))) == []  # the contract does not say how many days


def test_concealed_works_may_be_covered_after_the_working_day_of_the_notice():
    items = [ConcealedDates(P, "a", notified_on=date(2026, 10, 9)), ConcealedDates(P, "b", notified_on=date(2026, 10, 9), held_on=date(2026, 10, 12)),
             ConcealedDates(P, "c")]
    events = concealed_events(items)
    assert [(e.params["concealed"], e.on) for e in events] == [("a", date(2026, 10, 12))]  # Friday -> Monday; b was accepted; c has no notice


def test_downtime_terms():
    events = downtime_events(DowntimeDates(P, noticed_on=date(2026, 10, 9), need_by=date(2026, 10, 16)))
    assert {e.ref: e.on for e in events} == {"notice": date(2026, 10, 12), "need_by": date(2026, 10, 16)}
    assert downtime_events(DowntimeDates(P, noticed_on=date(2026, 10, 9), held_on=date(2026, 10, 13))) == []


def test_adjacent_works_give_their_period():
    events = adjacent_events([AdjacentPeriod(P, "x", date(2026, 10, 14), date(2026, 10, 18)), AdjacentPeriod(P, "y", None, date(2026, 10, 20))])
    assert [(e.params["adjacent"], e.ref, e.on) for e in events] == [("x", "from", date(2026, 10, 14)), ("x", "to", date(2026, 10, 18)), ("y", "to", date(2026, 10, 20))]


# --- the event itself, the order, the defaults ------------------------------------------------------------------------------------


def test_an_event_has_either_a_day_or_an_aware_instant():
    with pytest.raises(ValueError):
        CalendarEvent(EventKind.USER, "k", P)
    with pytest.raises(ValueError):
        CalendarEvent(EventKind.USER, "k", P, on=date(2026, 10, 12), at=datetime(2026, 10, 12, tzinfo=UTC))
    with pytest.raises(ValueError):
        CalendarEvent(EventKind.USER, "k", P, at=datetime(2026, 10, 12))  # noqa: DTZ001 - naive on purpose


def test_the_day_of_an_instant_is_the_day_in_warsaw():
    summer = CalendarEvent(EventKind.BREAK_END, "k", P, at=datetime(2026, 10, 10, 22, 30, tzinfo=UTC))  # CEST, +2
    winter = CalendarEvent(EventKind.BREAK_END, "k", P, at=datetime(2026, 12, 10, 23, 30, tzinfo=UTC))  # CET, +1
    assert summer.day() == date(2026, 10, 11) and winter.day() == date(2026, 12, 11)


def test_the_title_key_names_the_kind_and_the_part():
    assert CalendarEvent(EventKind.ACCEPTANCE_TERM, "k", P, on=date(2026, 10, 12), ref="reinvite").title_key == "calendar.event.acceptance_term.reinvite"
    assert CalendarEvent(EventKind.BREAK_END, "k", P, at=datetime(2026, 10, 12, tzinfo=UTC)).title_key == "calendar.event.break_end"


def test_the_order_is_chronological_all_day_first_and_independent_of_the_input_order():
    events = [
        CalendarEvent(EventKind.BREAK_END, "b", P, at=datetime(2026, 10, 12, 8, 0, tzinfo=UTC)),  # 10:00 in Warsaw
        CalendarEvent(EventKind.OBJECT_START, "a", P, on=date(2026, 10, 12)),
        CalendarEvent(EventKind.BREAK_START, "c", P, at=datetime(2026, 10, 11, 21, 0, tzinfo=UTC)),  # 23:00 on the 11th in Warsaw
        CalendarEvent(EventKind.BREAK_END, "d", P, at=datetime(2026, 10, 12, 7, 0, tzinfo=UTC)),
        CalendarEvent(EventKind.DELIVERY_DEADLINE, "e", P, on=date(2026, 10, 12)),
    ]
    expected = [e.key for e in sort_events(events)]
    assert expected == ["c", "e", "a", "d", "b"]  # the 11th; then the 12th: the all-day by kind, then the timed
    for seed in range(20):
        shuffled = events[:]
        random.Random(seed).shuffle(shuffled)
        assert [e.key for e in sort_events(shuffled)] == expected


def test_which_kinds_send_a_message_by_default_and_how_early():
    assert EventKind.BREAK_END in ev.PUSH_BY_DEFAULT and EventKind.USER in ev.PUSH_BY_DEFAULT
    for off in (EventKind.BREAK_START, EventKind.WITHDRAWAL_END, EventKind.PAYMENT_TERM, EventKind.ADJACENT_WORK, EventKind.PRICE_VALIDITY_END):
        assert off not in ev.PUSH_BY_DEFAULT
    assert lead_days(EventKind.DELIVERY_DEADLINE) == (7, 3, 1, 0) and lead_days(EventKind.BREAK_END) == (0,)


# --- the numbers are the numbers of the contract -------------------------------------------------------------------------------


def clause_text(section: str, n: int) -> str:
    catalog = load_clause_catalog()
    section_ = next(s for s in catalog.sections if s.key == section)
    return " ".join(v.text_pl for c in section_.clauses if c.n == n for v in c.variants)


def test_the_terms_in_the_code_are_the_terms_of_the_contract_template():
    """If the template changes a term, this fails and the calendar is changed with it (one truth, not two)."""
    assert re.search(rf"w terminie {ev.ADVANCE_DAYS} dni od zawarcia Umowy", clause_text("advance_and_payments", 1))
    assert re.search(rf"nie krótszy niż {ev.REINVITE_WORKING_DAYS} Dni robocze", clause_text("acceptance", 5))
    assert re.search(rf"co najmniej {ev.CONCEALED_NOTICE_WORKING_DAYS} Dnia roboczego", clause_text("concealed_works", 1))
    assert "do końca następnego Dnia roboczego" in clause_text("downtime", 2) and ev.DOWNTIME_REMOVAL_WORKING_DAYS == 1
    assert re.search(rf"w terminie {ev.CONSUMER_WITHDRAWAL_DAYS} dni od jej zawarcia", clause_text("consumer_withdrawal", 1))
    assert "od poniedziałku do piątku z wyłączeniem dni ustawowo wolnych" in clause_text("definitions", 10)


def test_the_package_is_pure_no_web_no_database_no_clock():
    for path in Path(ev.__file__).parent.glob("*.py"):
        source = path.read_text(encoding="utf-8")
        for forbidden in ("fastapi", "sqlalchemy", "httpx", "AsyncSession", ".now(", "utcnow", "today()"):
            assert forbidden not in source, (path.name, forbidden)
