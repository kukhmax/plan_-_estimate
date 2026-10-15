"""The calendar preferences of the owner as the pure functions see them (Stage 18C): the zone, the kinds that send, the quiet hours."""
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import time, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.domain.calendar import DEFAULT_TIMEZONE
from app.domain.calendar.events import PUSH_BY_DEFAULT, EventKind

# The short list of the settings (Q15); the owner works in Poland, the others are for the border regions and the neighbours.
ALLOWED_TIMEZONES: tuple[str, ...] = (
    "Europe/Warsaw", "Europe/Berlin", "Europe/Prague", "Europe/Vilnius", "Europe/Kyiv", "Europe/London", "UTC",
)


def parse_timezone(name: str) -> ZoneInfo:
    if name not in ALLOWED_TIMEZONES:
        raise ValueError(f"the time zone {name!r} is not in the list of the settings")
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as error:  # the list names a zone the system does not know: a deployment problem, not the owner's
        raise ValueError(f"the time zone {name!r} is unknown to the system") from error


def in_quiet_hours(at: time, quiet_from: time, quiet_to: time) -> bool:
    """Is the time of the day inside the quiet window (it may wrap midnight: 21:00-07:00); a window with equal ends is empty."""
    if quiet_from == quiet_to:
        return False
    if quiet_from < quiet_to:
        return quiet_from <= at < quiet_to
    return at >= quiet_from or at < quiet_to


@dataclass(frozen=True)
class CalendarPrefs:
    enabled: bool = True
    tz: tzinfo = DEFAULT_TIMEZONE
    tz_name: str = "Europe/Warsaw"
    kind_overrides: Mapping[str, bool] = field(default_factory=dict)
    quiet_from: time = time(21, 0)
    quiet_to: time = time(7, 0)
    digest_at: time = time(8, 0)
    language: str | None = None  # the language of the messages; None: the language of the owner's Telegram

    def __post_init__(self) -> None:
        if in_quiet_hours(self.digest_at, self.quiet_from, self.quiet_to):
            raise ValueError("the digest time must be outside the quiet hours")

    def sends(self, kind: EventKind) -> bool:
        """Does an event of this kind send a message: the owner's choice, otherwise the default of the kind."""
        if not self.enabled:
            return False
        override = self.kind_overrides.get(kind.value)
        return override if override is not None else kind in PUSH_BY_DEFAULT
