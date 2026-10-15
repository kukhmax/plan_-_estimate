"""What the calendar screen shows (Stage 18E): plain types, and the presets of the "Remind" button as pure functions.

The agenda is a list by day: the events derived from the data, the owner's own reminders, and the works of the plan that have a date; the
works whose date has passed and that are not done are listed apart (overdue). The time of a preset ("tomorrow morning", "the day before")
is computed here, in the owner's zone, not in the screen: the application keeps no rule of time in React.
"""
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta

from app.domain.calendar.events import EventKind
from app.domain.calendar.prefs import CalendarPrefs
from app.domain.calendar.reconcile import local_instant
from app.models.work_execution import WorkExecutionStatus

PRESET_BREAK_END = "BREAK_END"  # when the break of a completed work ends
PRESET_WORK_DAY = "WORK_DAY"  # the morning of the planned day of a work
PRESET_DAY_BEFORE = "DAY_BEFORE"  # the evening before the planned day
PRESET_IN_1H = "IN_1H"
PRESET_IN_3H = "IN_3H"
PRESET_TOMORROW = "TOMORROW"  # tomorrow morning
PRESET_CUSTOM = "CUSTOM"  # an instant the owner chose
PRESETS = (PRESET_BREAK_END, PRESET_WORK_DAY, PRESET_DAY_BEFORE, PRESET_IN_1H, PRESET_IN_3H, PRESET_TOMORROW, PRESET_CUSTOM)
EVENING = time(18, 0)  # "the day before" is announced at six in the evening
# What each preset waits for: a preset about the start of a work is pointless once the work has started.
CLOSE_ON = {PRESET_WORK_DAY: WorkExecutionStatus.IN_PROGRESS.value, PRESET_DAY_BEFORE: WorkExecutionStatus.IN_PROGRESS.value}
NEEDS_WORK = (PRESET_BREAK_END, PRESET_WORK_DAY, PRESET_DAY_BEFORE)


class PresetUnavailableError(Exception):
    """The preset cannot be made for this work: `code` is WORK_REQUIRED, NO_PLANNED_DATE, NO_BREAK, CUSTOM_TIME_REQUIRED or UNKNOWN_PRESET."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def preset_instant(
    preset: str, prefs: CalendarPrefs, now: datetime, *, planned_date: date | None = None, ready_after: datetime | None = None,
    custom: datetime | None = None,
) -> datetime:
    """The instant (UTC) a preset means. Raises `PresetUnavailableError` when the data it needs is missing."""
    if preset not in PRESETS:
        raise PresetUnavailableError("UNKNOWN_PRESET")
    if preset == PRESET_IN_1H:
        return now + timedelta(hours=1)
    if preset == PRESET_IN_3H:
        return now + timedelta(hours=3)
    if preset == PRESET_TOMORROW:
        return local_instant(now.astimezone(prefs.tz).date() + timedelta(days=1), prefs.digest_at, prefs.tz)
    if preset == PRESET_CUSTOM:
        if custom is None or custom.tzinfo is None:
            raise PresetUnavailableError("CUSTOM_TIME_REQUIRED")
        return custom.astimezone(UTC)
    if preset == PRESET_BREAK_END:
        if ready_after is None:
            raise PresetUnavailableError("NO_BREAK")
        return ready_after
    if planned_date is None:
        raise PresetUnavailableError("NO_PLANNED_DATE")
    if preset == PRESET_WORK_DAY:
        return local_instant(planned_date, prefs.digest_at, prefs.tz)
    return local_instant(planned_date - timedelta(days=1), EVENING, prefs.tz)  # PRESET_DAY_BEFORE


@dataclass(frozen=True)
class AgendaItem:
    """One line of the agenda."""

    source: str  # EVENT (derived) or REMINDER (the owner's own)
    kind: str  # an EventKind value
    key: str  # stable: the key of the event, or the id of the reminder
    day: date  # the day in the owner's zone
    on: date | None = None
    at: datetime | None = None
    ref: str = ""
    title_key: str | None = None
    title: str | None = None  # the owner's own words (REMINDER)
    params: dict[str, str | int] = field(default_factory=dict)
    sends: bool = False  # does this line send a message (the kind is on in the settings)
    reminder_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    project_name: str | None = None
    room_id: uuid.UUID | None = None
    room_name: str | None = None
    surface_id: uuid.UUID | None = None
    surface_name: str | None = None
    occurrence_key: uuid.UUID | None = None

    @property
    def is_user(self) -> bool:
        return self.kind == EventKind.USER.value


@dataclass(frozen=True)
class AgendaWork:
    """A work of the plan with its date and state: the line of the "Today" list and of the overdue list."""

    occurrence_key: uuid.UUID
    planned_date: date
    status: WorkExecutionStatus
    wait_after_hours: int | None
    project_id: uuid.UUID
    project_name: str
    room_id: uuid.UUID
    room_name: str
    surface_id: uuid.UUID
    surface_name: str
    work_name_key: str | None
    work_display_name: str | None
    ready_after: datetime | None = None


@dataclass(frozen=True)
class Agenda:
    today: date
    start: date
    end: date
    items: list[AgendaItem]
    works: list[AgendaWork]  # planned in the period, not done
    overdue: list[AgendaWork]  # planned before today, not done
