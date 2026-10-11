"""Reconciliation of the reminders with the events (Stage 18C): what should be queued, and what changes in the queue.

Two pure steps. `desired_reminders` turns the events of an object and the owner's preferences into the reminders that should exist, each
with a deduplication key that names the fact *and the instant it is scheduled for*; `plan_changes` compares them with what is queued and
says what to insert, to move and to cancel. The same input gives the same plan, an unchanged object gives an empty plan, a moved fact
is a new key (the old row is cancelled, a row already sent is never touched). The database part is in `services/calendar_service.py`.
"""
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo

from app.domain.calendar.events import CalendarEvent, lead_days
from app.domain.calendar.prefs import CalendarPrefs, in_quiet_hours


@dataclass(frozen=True)
class DesiredReminder:
    dedupe_key: str
    event: CalendarEvent
    lead_days: int
    send_at: datetime  # UTC


@dataclass(frozen=True)
class QueuedReminder:
    """What the reconciliation needs to know about a row already in the queue."""

    status: str
    send_at: datetime


@dataclass(frozen=True)
class ReconcilePlan:
    insert: list[DesiredReminder]
    retime: list[DesiredReminder]  # a pending row whose send time changed (the zone or the quiet hours were changed)
    revive: list[DesiredReminder]  # a cancelled row whose fact is back (the same fact, the same instant)
    cancel: list[str]  # dedupe keys of pending rows whose fact is gone

    @property
    def empty(self) -> bool:
        return not (self.insert or self.retime or self.revive or self.cancel)


def local_instant(day: date, at: time, tz: tzinfo) -> datetime:
    """The UTC instant of a wall-clock time on a day in the owner's zone."""
    return datetime.combine(day, at, tzinfo=tz).astimezone(UTC)


def leave_quiet_hours(instant: datetime, prefs: CalendarPrefs) -> datetime:
    """An instant inside the quiet hours moves to the end of them (07:00 of the same or the next morning); outside it stays."""
    local = instant.astimezone(prefs.tz)
    if not in_quiet_hours(local.time(), prefs.quiet_from, prefs.quiet_to):
        return instant
    day = local.date() if local.time() < prefs.quiet_to else local.date() + timedelta(days=1)
    return local_instant(day, prefs.quiet_to, prefs.tz)


def _key(event: CalendarEvent, lead: int) -> str:
    instant = event.at.astimezone(UTC).isoformat() if event.at is not None else None
    return f"{event.key}|{instant or event.on}|{lead}"


def desired_reminders(events: Iterable[CalendarEvent], prefs: CalendarPrefs) -> list[DesiredReminder]:
    """The automatic reminders the events imply: a timed event is sent at its time (not in the quiet hours); a day is announced in the
    digest of that morning and, for the kinds that are announced early, of the mornings before it."""
    found: list[DesiredReminder] = []
    for event in events:
        if not prefs.sends(event.kind):
            continue
        if event.at is not None:
            found.append(DesiredReminder(_key(event, 0), event, 0, leave_quiet_hours(event.at, prefs)))
            continue
        assert event.on is not None  # an event has a day or an instant (checked when it is made)
        for lead in lead_days(event.kind):
            send = local_instant(event.on - timedelta(days=lead), prefs.digest_at, prefs.tz)
            found.append(DesiredReminder(_key(event, lead), event, lead, send))
    return found


def plan_changes(desired: Iterable[DesiredReminder], queued: Mapping[str, QueuedReminder], now: datetime) -> ReconcilePlan:
    """Insert what is new and still ahead, move the pending rows whose time changed, bring back a cancelled row whose fact is back,
    cancel the pending rows whose fact is gone.

    A row that is neither pending nor cancelled (sent, failed, missed, done) is history and is never touched; a fact whose time has already
    passed and that was never queued is not queued now (the calendar shows it, a late message would only be noise).
    """
    wanted = {item.dedupe_key: item for item in desired}
    insert = [item for key, item in wanted.items() if key not in queued and item.send_at > now]
    retime = [item for key, item in wanted.items() if key in queued and queued[key].status == "PENDING" and queued[key].send_at != item.send_at]
    revive = [item for key, item in wanted.items() if key in queued and queued[key].status == "CANCELLED" and item.send_at > now]
    cancel = [key for key, row in queued.items() if row.status == "PENDING" and key not in wanted]
    return ReconcilePlan(insert=insert, retime=retime, revive=revive, cancel=cancel)
