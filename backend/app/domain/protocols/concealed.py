"""Rules of the protocol of acceptance of concealed works (Stage 16G): what an entry may be and what is missing before it is issued.

Deterministic and catalogue-driven: the kind of work is one of the catalogue's (`concealed_work_kinds.json`), the surface is one of
the object's, the evidence is the photos of the category HIDDEN_WORK that belong to that surface. Two rules protect both sides: a
protocol needs **photos** (without them nobody can later say what was covered), and when the customer did not come the protocol
needs **the day he was notified** (contract § 13 ust. 3: a one-sided protocol with photos, the work goes on). The code decides nothing
about the work itself: the result is the owner's word.
"""

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.domain.contracts.answers import TEXT_LIMIT
from app.domain.contracts.catalog import ContractCatalog
from app.domain.exceptions import ConcealedInvalidError, HandoverInvalidError
from app.domain.protocols.handover import (
    BAD_TIME, LONG_TEXT_LIMIT, NOT_AN_OPTION, TOO_LONG, WRONG_TYPE, normalize_attendees,
)

RESULTS = ("ACCEPTED", "WITH_REMARKS")
COVER_CONSENTS = ("GIVEN", "WITHHELD")
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
FIELDS = (
    "held_on", "held_time", "customer_absent", "notified_on", "attendees", "surface_id", "work_kind", "work_note", "material",
    "batch", "photo_ids", "result", "remarks", "cover_consent",
)

UNKNOWN_FIELD = "UNKNOWN_FIELD"
UNKNOWN_SURFACE = "UNKNOWN_SURFACE"
UNKNOWN_PHOTO = "UNKNOWN_PHOTO"

# what is missing before the protocol can be issued
EXECUTOR_PROFILE_REQUIRED = "EXECUTOR_PROFILE_REQUIRED"
CLIENT_REQUIRED = "CLIENT_REQUIRED"
CONTRACT_REQUIRED = "CONTRACT_REQUIRED"
SURFACE_REQUIRED = "SURFACE_REQUIRED"
WORK_KIND_REQUIRED = "WORK_KIND_REQUIRED"
WORK_NOTE_REQUIRED = "WORK_NOTE_REQUIRED"  # the kind "other" is described in words
HELD_ON_REQUIRED = "HELD_ON_REQUIRED"
NOTIFIED_ON_REQUIRED = "NOTIFIED_ON_REQUIRED"  # the customer did not come: when was he told
NO_ATTENDEES = "NO_ATTENDEES"
PHOTOS_REQUIRED = "PHOTOS_REQUIRED"
RESULT_REQUIRED = "RESULT_REQUIRED"
REMARKS_REQUIRED = "REMARKS_REQUIRED"
COVER_CONSENT_REQUIRED = "COVER_CONSENT_REQUIRED"


@dataclass(frozen=True, slots=True)
class Blocker:
    code: str
    details: dict[str, Any] | None = None


def empty_state() -> dict[str, Any]:
    return {
        "held_on": None, "held_time": None, "customer_absent": False, "notified_on": None, "attendees": [], "surface_id": None,
        "work_kind": None, "work_note": None, "material": None, "batch": None, "photo_ids": [], "result": None, "remarks": None,
        "cover_consent": None,
    }


def _text(key: str, value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        raise ConcealedInvalidError(key, WRONG_TYPE)
    text = " ".join(value.split()) if limit <= TEXT_LIMIT else value.strip()
    if len(text) > limit:
        raise ConcealedInvalidError(key, TOO_LONG)
    return text or None


def _day(key: str, value: Any) -> date | None:
    if value is not None and not isinstance(value, date):
        raise ConcealedInvalidError(key, WRONG_TYPE)
    return value


def apply_changes(
    current: dict[str, Any],
    changes: dict[str, Any],
    *,
    surface_ids: set[str],
    photos_of: Callable[[str], set[str]],
    people: dict[str, tuple[str, str | None]],
    catalog: ContractCatalog,
) -> dict[str, Any]:
    """The protocol's data after `changes`, or `ConcealedInvalidError` (nothing is applied when one change is refused).
    `photos_of(surface)` are the ids of the evidence photos that exist for a surface; changing the surface drops the chosen photos
    (they belong to the old one) unless new ones are chosen in the same change."""
    state = {**empty_state(), **{key: (list(value) if isinstance(value, list) else value) for key, value in current.items()}}
    unknown = [key for key in changes if key not in FIELDS]
    if unknown:
        raise ConcealedInvalidError(unknown[0], UNKNOWN_FIELD)
    kinds = {k.key for k in catalog.work_kinds.items}
    if "surface_id" in changes:
        value = changes["surface_id"]
        if value is None:
            surface = None
        else:
            try:
                surface = str(uuid.UUID(str(value)))
            except ValueError:
                raise ConcealedInvalidError("surface_id", WRONG_TYPE) from None
            if surface not in surface_ids:
                raise ConcealedInvalidError("surface_id", UNKNOWN_SURFACE)
        if surface != state["surface_id"]:
            state["photo_ids"] = []
        state["surface_id"] = surface
    for key, value in changes.items():
        if key == "surface_id":
            continue
        if key in ("held_on", "notified_on"):
            state[key] = _day(key, value)
        elif key == "held_time":
            if value is not None and (not isinstance(value, str) or not _TIME.match(value)):
                raise ConcealedInvalidError(key, BAD_TIME)
            state[key] = value
        elif key == "customer_absent":
            if value is not None and not isinstance(value, bool):
                raise ConcealedInvalidError(key, WRONG_TYPE)
            state[key] = bool(value)
        elif key == "attendees":
            try:
                state[key] = normalize_attendees(value, people)
            except HandoverInvalidError as exc:
                raise ConcealedInvalidError(key, exc.reason) from exc
        elif key == "work_kind":
            if value is not None and (not isinstance(value, str) or value not in kinds):
                raise ConcealedInvalidError(key, NOT_AN_OPTION)
            state[key] = value
        elif key in ("work_note", "remarks"):
            state[key] = None if value is None else _text(key, value, LONG_TEXT_LIMIT)
        elif key == "material":
            state[key] = None if value is None else _text(key, value, 500)
        elif key == "batch":
            state[key] = None if value is None else _text(key, value, 255)
        elif key == "photo_ids":
            if value is None:
                value = []
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise ConcealedInvalidError(key, WRONG_TYPE)
            allowed = photos_of(state["surface_id"]) if state["surface_id"] else set()
            chosen: list[str] = []
            for photo in value:
                if photo not in allowed:
                    raise ConcealedInvalidError(key, UNKNOWN_PHOTO)
                if photo not in chosen:
                    chosen.append(photo)
            state[key] = chosen
        elif key == "result":
            if value is not None and value not in RESULTS:
                raise ConcealedInvalidError(key, NOT_AN_OPTION)
            state[key] = value
        elif key == "cover_consent":
            if value is not None and value not in COVER_CONSENTS:
                raise ConcealedInvalidError(key, NOT_AN_OPTION)
            state[key] = value
    return state


def evaluate(data: dict[str, Any]) -> list[Blocker]:
    """What must still be done before the protocol can be issued, in the order of doing it."""
    blockers: list[Blocker] = []
    if not data.get("surface_id"):
        blockers.append(Blocker(SURFACE_REQUIRED))
    if not data.get("work_kind"):
        blockers.append(Blocker(WORK_KIND_REQUIRED))
    elif data["work_kind"] == "other" and not data.get("work_note"):
        blockers.append(Blocker(WORK_NOTE_REQUIRED))
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
    elif data["result"] == "WITH_REMARKS" and not data.get("remarks"):
        blockers.append(Blocker(REMARKS_REQUIRED))
    if not data.get("customer_absent") and not data.get("cover_consent"):
        blockers.append(Blocker(COVER_CONSENT_REQUIRED))
    return blockers
