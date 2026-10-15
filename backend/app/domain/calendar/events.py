"""The events of the calendar, derived from the data of an object (Stage 18B).

Nothing is stored here and nothing is sent: a function takes the plain facts (dates and states read elsewhere) and returns the events
those facts imply, in a deterministic order. The terms that come from the contract are the terms of its text (a test compares each number
below with the clause it comes from); a term that is already closed by the protocol (the meeting was held) is no event any more.
"""
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta, tzinfo
from enum import StrEnum

from app.domain.calendar import DEFAULT_TIMEZONE
from app.domain.calendar.working_days import add_working_days
from app.domain.rules.work_execution_rules import derive_ready_after
from app.models.work_execution import WorkExecutionStatus

# The terms of the contract template (clauses.json); tests/test_stage18b_calendar_events.py keeps them equal to the clause texts.
ADVANCE_DAYS = 3  # § 6 ust. 1: the advance within 3 days from the conclusion of the contract
REINVITE_WORKING_DAYS = 3  # § 14 ust. 5: the additional term of the second call to the acceptance, not shorter than 3 working days
CONCEALED_NOTICE_WORKING_DAYS = 1  # § 13 ust. 1: the notice of concealed works at least 1 working day ahead
DOWNTIME_REMOVAL_WORKING_DAYS = 1  # § 10 ust. 2: the obstacle not removed by the end of the next working day
CONSUMER_WITHDRAWAL_DAYS = 14  # § 20 ust. 1: a consumer may withdraw within 14 days from the conclusion


class EventKind(StrEnum):
    BREAK_START = "BREAK_START"  # a technological break begins (the work is completed)
    BREAK_END = "BREAK_END"  # the next work may begin
    WORK_START = "WORK_START"  # the first planned work of a room
    WORK_END = "WORK_END"  # the last planned work of a room
    OBJECT_START = "OBJECT_START"  # the start of the works of the contract
    OBJECT_END = "OBJECT_END"  # the end of the works of the contract
    DELIVERY_DEADLINE = "DELIVERY_DEADLINE"  # the date to hand the object over (the end of the works of the contract)
    ACCEPTANCE_TERM = "ACCEPTANCE_TERM"  # the customer should come to the acceptance / to the second call (§ 14)
    CONCEALED_TERM = "CONCEALED_TERM"  # the earliest day of the acceptance of concealed works (§ 13)
    DOWNTIME_TERM = "DOWNTIME_TERM"  # the end of the next working day after the notice / the term set to remove an obstacle (§ 10)
    WITHDRAWAL_END = "WITHDRAWAL_END"  # the end of the consumer's right to withdraw (§ 20)
    PAYMENT_TERM = "PAYMENT_TERM"  # the advance is due (§ 6)
    ADJACENT_WORK = "ADJACENT_WORK"  # another contractor works in the object (the period of the protocol)
    PRICE_VALIDITY_END = "PRICE_VALIDITY_END"  # the unit prices stop to bind (§ 4)
    USER = "USER"  # an own reminder (the Remind button, Stage 18E)


# Which kinds send a message by default (Q1, 2026-10-11); the owner switches the rest on in the settings. The calendar shows all of them.
PUSH_BY_DEFAULT: frozenset[EventKind] = frozenset(
    {EventKind.BREAK_END, EventKind.WORK_START, EventKind.WORK_END, EventKind.OBJECT_START, EventKind.OBJECT_END,
     EventKind.DELIVERY_DEADLINE, EventKind.ACCEPTANCE_TERM, EventKind.CONCEALED_TERM, EventKind.DOWNTIME_TERM, EventKind.USER}
)
# How many days ahead of the day a reminder is also due; zero is the day itself. Only the delivery deadline is announced early.
LEAD_DAYS: Mapping[EventKind, tuple[int, ...]] = {EventKind.DELIVERY_DEADLINE: (7, 3, 1, 0), EventKind.OBJECT_START: (1, 0)}
DEFAULT_LEAD_DAYS: tuple[int, ...] = (0,)


def lead_days(kind: EventKind) -> tuple[int, ...]:
    return LEAD_DAYS.get(kind, DEFAULT_LEAD_DAYS)


@dataclass(frozen=True)
class CalendarEvent:
    """One thing that happens (a day, or an instant). `key` is stable: the same fact always has the same key (the deduplication key)."""

    kind: EventKind
    key: str
    project_id: uuid.UUID
    on: date | None = None  # a day without an hour
    at: datetime | None = None  # an instant (aware)
    ref: str = ""  # what within the kind (e.g. "appearance" / "reinvite")
    room_id: uuid.UUID | None = None
    surface_id: uuid.UUID | None = None
    occurrence_key: uuid.UUID | None = None
    params: dict[str, str | int] = field(default_factory=dict)  # for the text: the title key is `calendar.event.<kind>[.<ref>]`

    def __post_init__(self) -> None:
        if (self.on is None) == (self.at is None):
            raise ValueError("an event has either a day or an instant")
        if self.at is not None and self.at.tzinfo is None:
            raise ValueError("the instant of an event must be aware")

    @property
    def title_key(self) -> str:
        base = f"calendar.event.{self.kind.value.lower()}"
        return f"{base}.{self.ref}" if self.ref else base

    def day(self, tz: tzinfo = DEFAULT_TIMEZONE) -> date:
        """The calendar day of the event in the owner's time zone."""
        return self.on if self.on is not None else self.at.astimezone(tz).date()  # type: ignore[union-attr]


def _plus_days(day: date, count: int) -> date | None:
    """`day` plus calendar days; None when the result is not a date (a typo of the year must not stop the calendar)."""
    try:
        return day + timedelta(days=count)
    except OverflowError:
        return None


def _plus_working_days(day: date, count: int) -> date | None:
    try:
        return add_working_days(day, count)
    except (OverflowError, ValueError):
        return None


def _key(kind: EventKind, project_id: uuid.UUID, *parts: object) -> str:
    return ":".join([kind.value, str(project_id), *[str(p) for p in parts if p not in (None, "")]])


def sort_events(events: Iterable[CalendarEvent], tz: tzinfo = DEFAULT_TIMEZONE) -> list[CalendarEvent]:
    """Chronological order; an all-day event goes before the timed ones of its day; ties by kind and key (deterministic)."""
    floor = datetime.min.replace(tzinfo=UTC)
    return sorted(events, key=lambda e: (e.day(tz), e.at or floor, e.kind.value, e.key))


# --- technological breaks (Stage 13) -------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class BreakInput:
    project_id: uuid.UUID
    occurrence_key: uuid.UUID
    status: WorkExecutionStatus
    completed_at: datetime | None
    wait_after_hours: int | None
    room_id: uuid.UUID | None = None
    surface_id: uuid.UUID | None = None


def break_events(inputs: Iterable[BreakInput]) -> list[CalendarEvent]:
    """The start and the end of the technological break of every completed work that has a break (the end is `ready_after`)."""
    events: list[CalendarEvent] = []
    for item in inputs:
        ready_after = derive_ready_after(item.status, item.completed_at, item.wait_after_hours)
        if ready_after is None or not item.wait_after_hours or item.completed_at is None:
            continue
        common = {"project_id": item.project_id, "room_id": item.room_id, "surface_id": item.surface_id, "occurrence_key": item.occurrence_key}
        events.append(CalendarEvent(EventKind.BREAK_START, _key(EventKind.BREAK_START, item.project_id, item.occurrence_key),
                                    at=item.completed_at, params={"hours": item.wait_after_hours}, **common))  # type: ignore[arg-type]
        events.append(CalendarEvent(EventKind.BREAK_END, _key(EventKind.BREAK_END, item.project_id, item.occurrence_key),
                                    at=ready_after, params={"hours": item.wait_after_hours}, **common))  # type: ignore[arg-type]
    return events


# --- the planned dates of works (Q12) -----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class PlannedWork:
    project_id: uuid.UUID
    occurrence_key: uuid.UUID
    planned_date: date
    room_id: uuid.UUID | None = None


def schedule_events(planned: Iterable[PlannedWork]) -> list[CalendarEvent]:
    """The first and the last planned day of every room (the end only when it is a later day than the start)."""
    by_room: dict[tuple[uuid.UUID, uuid.UUID | None], list[date]] = {}
    for work in planned:
        by_room.setdefault((work.project_id, work.room_id), []).append(work.planned_date)
    events: list[CalendarEvent] = []
    for (project_id, room_id), dates in by_room.items():
        first, last = min(dates), max(dates)
        events.append(CalendarEvent(EventKind.WORK_START, _key(EventKind.WORK_START, project_id, room_id), project_id, on=first, room_id=room_id))
        if last > first:
            events.append(CalendarEvent(EventKind.WORK_END, _key(EventKind.WORK_END, project_id, room_id), project_id, on=last, room_id=room_id))
    return events


# --- the contract --------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class ContractDates:
    project_id: uuid.UUID
    signed_on: date | None = None
    work_start_date: date | None = None
    work_end_date: date | None = None
    price_validity_days: int | None = None
    consumer: bool = False  # the customer is a consumer (a private person): the right of withdrawal of § 20 may apply


def contract_events(contract: ContractDates) -> list[CalendarEvent]:
    pid = contract.project_id
    events: list[CalendarEvent] = []
    if contract.work_start_date:
        events.append(CalendarEvent(EventKind.OBJECT_START, _key(EventKind.OBJECT_START, pid), pid, on=contract.work_start_date))
    if contract.work_end_date:
        events.append(CalendarEvent(EventKind.OBJECT_END, _key(EventKind.OBJECT_END, pid), pid, on=contract.work_end_date))
        events.append(CalendarEvent(EventKind.DELIVERY_DEADLINE, _key(EventKind.DELIVERY_DEADLINE, pid), pid, on=contract.work_end_date))
    if contract.signed_on:
        advance = _plus_days(contract.signed_on, ADVANCE_DAYS)
        if advance:
            events.append(CalendarEvent(EventKind.PAYMENT_TERM, _key(EventKind.PAYMENT_TERM, pid, "advance"), pid, ref="advance", on=advance))
        validity = _plus_days(contract.signed_on, contract.price_validity_days) if contract.price_validity_days else None
        if validity:
            events.append(CalendarEvent(EventKind.PRICE_VALIDITY_END, _key(EventKind.PRICE_VALIDITY_END, pid), pid, on=validity))
        withdrawal = _plus_days(contract.signed_on, CONSUMER_WITHDRAWAL_DAYS) if contract.consumer else None
        if withdrawal:
            events.append(CalendarEvent(EventKind.WITHDRAWAL_END, _key(EventKind.WITHDRAWAL_END, pid), pid, on=withdrawal))
    return events


# --- the protocols -------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class AcceptanceDates:
    project_id: uuid.UUID
    appearance_days: int | None  # the contract's answer: working days for the customer to come (§ 14 ust. 2)
    notified_on: date | None = None
    renotified_on: date | None = None
    held_on: date | None = None


def acceptance_events(acceptance: AcceptanceDates) -> list[CalendarEvent]:
    """The day by which the customer should come to the acceptance, and by which to the second call; none once the acceptance was held."""
    pid = acceptance.project_id
    if acceptance.held_on:
        return []
    events: list[CalendarEvent] = []
    appearance = _plus_working_days(acceptance.notified_on, acceptance.appearance_days) if acceptance.notified_on and acceptance.appearance_days else None
    if appearance:
        events.append(CalendarEvent(EventKind.ACCEPTANCE_TERM, _key(EventKind.ACCEPTANCE_TERM, pid, "appearance"), pid, ref="appearance", on=appearance))
    reinvite = _plus_working_days(acceptance.renotified_on, REINVITE_WORKING_DAYS) if acceptance.renotified_on else None
    if reinvite:
        events.append(CalendarEvent(EventKind.ACCEPTANCE_TERM, _key(EventKind.ACCEPTANCE_TERM, pid, "reinvite"), pid, ref="reinvite", on=reinvite))
    return events


@dataclass(frozen=True)
class ConcealedDates:
    project_id: uuid.UUID
    ref: str  # which concealed work (the id of the record in the protocol)
    notified_on: date | None = None
    held_on: date | None = None


def concealed_events(items: Iterable[ConcealedDates]) -> list[CalendarEvent]:
    """The earliest day the contractor may cover the work: the notice plus the working day of § 13 ust. 1; none once it was accepted."""
    events: list[CalendarEvent] = []
    for item in items:
        term = _plus_working_days(item.notified_on, CONCEALED_NOTICE_WORKING_DAYS) if item.notified_on and not item.held_on else None
        if term:
            events.append(CalendarEvent(EventKind.CONCEALED_TERM, _key(EventKind.CONCEALED_TERM, item.project_id, item.ref), item.project_id,
                                        ref="notice", on=term, params={"concealed": item.ref}))
    return events


@dataclass(frozen=True)
class DowntimeDates:
    project_id: uuid.UUID
    noticed_on: date | None = None
    need_by: date | None = None
    held_on: date | None = None


def downtime_events(downtime: DowntimeDates) -> list[CalendarEvent]:
    """The end of the next working day after the notice (from then every working day is a day of the downtime), and the term the
    contractor set to remove the obstacle; none once the downtime protocol was held."""
    pid = downtime.project_id
    if downtime.held_on:
        return []
    events: list[CalendarEvent] = []
    next_day = _plus_working_days(downtime.noticed_on, DOWNTIME_REMOVAL_WORKING_DAYS) if downtime.noticed_on else None
    if next_day:
        events.append(CalendarEvent(EventKind.DOWNTIME_TERM, _key(EventKind.DOWNTIME_TERM, pid, "notice"), pid, ref="notice", on=next_day))
    if downtime.need_by:
        events.append(CalendarEvent(EventKind.DOWNTIME_TERM, _key(EventKind.DOWNTIME_TERM, pid, "need_by"), pid, ref="need_by", on=downtime.need_by))
    return events


@dataclass(frozen=True)
class AdjacentPeriod:
    project_id: uuid.UUID
    ref: str
    period_from: date | None = None
    period_to: date | None = None


def adjacent_events(periods: Iterable[AdjacentPeriod]) -> list[CalendarEvent]:
    events: list[CalendarEvent] = []
    for item in periods:
        for part, day in (("from", item.period_from), ("to", item.period_to)):
            if day:
                events.append(CalendarEvent(EventKind.ADJACENT_WORK, _key(EventKind.ADJACENT_WORK, item.project_id, item.ref, part), item.project_id,
                                            ref=part, on=day, params={"adjacent": item.ref}))
    return events
