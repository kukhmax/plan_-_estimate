"""Rules of the protocol of a pressure test (V2-12b): what an entry may be and what is missing before it is issued.

Deterministic and plain: the system is one of five, the medium is water or air, the numbers fit a range. The code decides **nothing** about the result: whether a test is
positive is the owner's word (no norm is applied and none is put in the owner's mouth); it only refuses an entry that is not a number, is out of range, or a photo that is not
one of the object's. As in the protocol of concealed works, a protocol needs **the manometer photographed** (without the picture nobody can later say what the pressure was),
and when the customer did not come it needs **the day he was notified**.
"""
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from app.domain.contracts.answers import TEXT_LIMIT
from app.domain.exceptions import HandoverInvalidError, PressureInvalidError
from app.domain.protocols.handover import (
    BAD_TIME, LONG_TEXT_LIMIT, NOT_AN_OPTION, OUT_OF_RANGE, TOO_LONG, WRONG_TYPE, normalize_attendees,
)

SYSTEMS = ("COLD_WATER", "HOT_WATER", "HEATING", "GAS", "SEWER")
MEDIA = ("WATER", "AIR")
RESULTS = ("POSITIVE", "NEGATIVE")
MAX_PHOTOS = 4
MAX_PRESSURE_BAR = Decimal(100)
MAX_DURATION_MIN = 1440
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
FIELDS = (
    "held_on", "held_time", "customer_absent", "notified_on", "attendees", "system", "section", "medium", "test_pressure_bar",
    "duration_min", "pressure_drop_bar", "photo_ids", "result", "remarks",
)

UNKNOWN_FIELD = "UNKNOWN_FIELD"
UNKNOWN_PHOTO = "UNKNOWN_PHOTO"
TOO_MANY_PHOTOS = "TOO_MANY_PHOTOS"

# what is missing before the protocol can be issued
EXECUTOR_PROFILE_REQUIRED = "EXECUTOR_PROFILE_REQUIRED"
CLIENT_REQUIRED = "CLIENT_REQUIRED"
HELD_ON_REQUIRED = "HELD_ON_REQUIRED"
NOTIFIED_ON_REQUIRED = "NOTIFIED_ON_REQUIRED"
NO_ATTENDEES = "NO_ATTENDEES"
SYSTEM_REQUIRED = "SYSTEM_REQUIRED"
MEDIUM_REQUIRED = "MEDIUM_REQUIRED"
PRESSURE_REQUIRED = "PRESSURE_REQUIRED"
DURATION_REQUIRED = "DURATION_REQUIRED"
DROP_REQUIRED = "DROP_REQUIRED"
PHOTOS_REQUIRED = "PHOTOS_REQUIRED"
RESULT_REQUIRED = "RESULT_REQUIRED"
REMARKS_REQUIRED = "REMARKS_REQUIRED"  # a negative result is explained


@dataclass(frozen=True, slots=True)
class Blocker:
    code: str
    details: dict[str, Any] | None = None


def empty_state() -> dict[str, Any]:
    return {
        "held_on": None, "held_time": None, "customer_absent": False, "notified_on": None, "attendees": [], "system": None, "section": None,
        "medium": None, "test_pressure_bar": None, "duration_min": None, "pressure_drop_bar": None, "photo_ids": [], "result": None, "remarks": None,
    }


def _text(key: str, value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        raise PressureInvalidError(key, WRONG_TYPE)
    text = " ".join(value.split()) if limit <= TEXT_LIMIT else value.strip()
    if len(text) > limit:
        raise PressureInvalidError(key, TOO_LONG)
    return text or None


def _day(key: str, value: Any) -> date | None:
    if value is not None and not isinstance(value, date):
        raise PressureInvalidError(key, WRONG_TYPE)
    return value


def _bar(key: str, value: Any, *, allow_zero: bool) -> Decimal | None:
    """A pressure in bar: a number with at most two places, above zero (the drop may be zero), at most 100."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise PressureInvalidError(key, WRONG_TYPE)
    try:
        number = Decimal(str(value).replace(",", ".").strip())
    except InvalidOperation:
        raise PressureInvalidError(key, WRONG_TYPE) from None
    if not number.is_finite() or number != number.quantize(Decimal("0.01")):
        raise PressureInvalidError(key, WRONG_TYPE)
    if number < 0 or (number == 0 and not allow_zero) or number > MAX_PRESSURE_BAR:
        raise PressureInvalidError(key, OUT_OF_RANGE)
    return number.quantize(Decimal("0.01"))


def _minutes(key: str, value: Any) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise PressureInvalidError(key, WRONG_TYPE)
    if value < 1 or value > MAX_DURATION_MIN:
        raise PressureInvalidError(key, OUT_OF_RANGE)
    return value


def apply_changes(
    current: dict[str, Any],
    changes: dict[str, Any],
    *,
    photo_ids: set[str],
    people: dict[str, tuple[str, str | None]],
) -> dict[str, Any]:
    """The protocol's data after `changes`, or `PressureInvalidError` (nothing is applied when one change is refused). `photo_ids` are the photos of the object that
    may be chosen as the manometer's."""
    state = {**empty_state(), **{key: (list(value) if isinstance(value, list) else value) for key, value in current.items()}}
    unknown = [key for key in changes if key not in FIELDS]
    if unknown:
        raise PressureInvalidError(unknown[0], UNKNOWN_FIELD)
    for key, value in changes.items():
        if key in ("held_on", "notified_on"):
            state[key] = _day(key, value)
        elif key == "held_time":
            if value is not None and (not isinstance(value, str) or not _TIME.match(value)):
                raise PressureInvalidError(key, BAD_TIME)
            state[key] = value
        elif key == "customer_absent":
            if value is not None and not isinstance(value, bool):
                raise PressureInvalidError(key, WRONG_TYPE)
            state[key] = bool(value)
        elif key == "attendees":
            try:
                state[key] = normalize_attendees(value, people)
            except HandoverInvalidError as exc:
                raise PressureInvalidError(key, exc.reason) from exc
        elif key == "system":
            if value is not None and value not in SYSTEMS:
                raise PressureInvalidError(key, NOT_AN_OPTION)
            state[key] = value
        elif key == "medium":
            if value is not None and value not in MEDIA:
                raise PressureInvalidError(key, NOT_AN_OPTION)
            state[key] = value
        elif key == "result":
            if value is not None and value not in RESULTS:
                raise PressureInvalidError(key, NOT_AN_OPTION)
            state[key] = value
        elif key == "section":
            state[key] = None if value is None else _text(key, value, 200)
        elif key == "remarks":
            state[key] = None if value is None else _text(key, value, LONG_TEXT_LIMIT)
        elif key == "test_pressure_bar":
            state[key] = _bar(key, value, allow_zero=False)
        elif key == "pressure_drop_bar":
            state[key] = _bar(key, value, allow_zero=True)
        elif key == "duration_min":
            state[key] = _minutes(key, value)
        elif key == "photo_ids":
            if value is None:
                value = []
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise PressureInvalidError(key, WRONG_TYPE)
            chosen: list[str] = []
            for photo in value:
                try:
                    photo = str(uuid.UUID(photo))
                except ValueError:
                    raise PressureInvalidError(key, UNKNOWN_PHOTO) from None
                if photo not in photo_ids:
                    raise PressureInvalidError(key, UNKNOWN_PHOTO)
                if photo not in chosen:
                    chosen.append(photo)
            if len(chosen) > MAX_PHOTOS:
                raise PressureInvalidError(key, TOO_MANY_PHOTOS)
            state[key] = chosen
    return state


def evaluate(data: dict[str, Any]) -> list[Blocker]:
    """What must still be done before the protocol can be issued, in the order of doing it."""
    blockers: list[Blocker] = []
    if not data.get("system"):
        blockers.append(Blocker(SYSTEM_REQUIRED))
    if not data.get("medium"):
        blockers.append(Blocker(MEDIUM_REQUIRED))
    if data.get("test_pressure_bar") is None:
        blockers.append(Blocker(PRESSURE_REQUIRED))
    if data.get("duration_min") is None:
        blockers.append(Blocker(DURATION_REQUIRED))
    if data.get("pressure_drop_bar") is None:
        blockers.append(Blocker(DROP_REQUIRED))
    if not data.get("held_on"):
        blockers.append(Blocker(HELD_ON_REQUIRED))
    if data.get("customer_absent"):
        if not data.get("notified_on"):
            blockers.append(Blocker(NOTIFIED_ON_REQUIRED))
    elif not data.get("attendees"):
        blockers.append(Blocker(NO_ATTENDEES))
    if not data.get("photo_ids"):
        blockers.append(Blocker(PHOTOS_REQUIRED))
    if not data.get("result"):
        blockers.append(Blocker(RESULT_REQUIRED))
    elif data["result"] == "NEGATIVE" and not data.get("remarks"):
        blockers.append(Blocker(REMARKS_REQUIRED))
    return blockers
