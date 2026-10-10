"""Rules of the protocol of acceptance of the work (Stage 16H.1): what an entry may be, what result it gives, what is missing.

The algorithm of the plan (section 5), deterministic and catalogue-driven. The **result is never typed**: a surface is *not accepted*
when some of its planned works are not completed (the execution of Stage 13) or when it has a **significant** remark; it is *accepted
with remarks* when it has only **removable** ones (each with its deadline); otherwise it is *accepted*. The whole follows from its
surfaces in the same way, and the protocol is *final* when its rooms are all the rooms that have planned works, otherwise *partial*.
The classes of the remarks are the catalogue's (`defect_classes.json`), the conditions of the assessment follow from the class of
each surface (`evaluation_conditions.json`); nothing here invents a number. Geometry and measurements are not part of this step: the
catalogue of tolerances has no approved value yet.
"""

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from app.domain.contracts.catalog import ContractCatalog
from app.domain.exceptions import AcceptanceInvalidError, HandoverInvalidError
from app.domain.protocols.handover import (
    BAD_TIME, LONG_TEXT_LIMIT, NOT_AN_OPTION, TOO_LONG, WRONG_TYPE, normalize_attendees,
)

ACCEPTED, WITH_REMARKS, NOT_ACCEPTED = "ACCEPTED", "ACCEPTED_WITH_REMARKS", "NOT_ACCEPTED"
CLASSES = ("REMOVABLE", "SIGNIFICANT")
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_MONEY = re.compile(r"^\d{1,9}([.,]\d{1,2})?$")
FIELDS = (
    "held_on", "held_time", "customer_absent", "notified_on", "renotified_on", "attendees", "room_ids", "conditions_note",
    "instrument_keys", "surfaces", "batches", "instructions_given", "amount_due", "amount_retained", "notes",
)
REMARK_FIELDS = ("place", "description", "classification", "deadline", "photo_ids")

UNKNOWN_FIELD = "UNKNOWN_FIELD"
UNKNOWN_ROOM = "UNKNOWN_ROOM"
UNKNOWN_SURFACE = "UNKNOWN_SURFACE"
UNKNOWN_INSTRUMENT = "UNKNOWN_INSTRUMENT"
UNKNOWN_PHOTO = "UNKNOWN_PHOTO"
BAD_REMARK = "BAD_REMARK"  # a remark without a place, a description or a class, or a removable one without its deadline
BAD_MONEY = "BAD_MONEY"

# what is missing before the protocol can be issued
EXECUTOR_PROFILE_REQUIRED = "EXECUTOR_PROFILE_REQUIRED"
CLIENT_REQUIRED = "CLIENT_REQUIRED"
CONTRACT_REQUIRED = "CONTRACT_REQUIRED"
SCOPE_REQUIRED = "SCOPE_REQUIRED"  # no room chosen, or the chosen rooms have no planned works
HELD_ON_REQUIRED = "HELD_ON_REQUIRED"
NOTIFIED_ON_REQUIRED = "NOTIFIED_ON_REQUIRED"
RENOTIFIED_ON_REQUIRED = "RENOTIFIED_ON_REQUIRED"
NOTIFICATION_ORDER = "NOTIFICATION_ORDER"  # the second call must come after the first, and the acceptance after the second
NO_ATTENDEES = "NO_ATTENDEES"
CONDITIONS_NOTE_REQUIRED = "CONDITIONS_NOTE_REQUIRED"  # a surface whose standard needs conditions agreed before the work
SURFACE_NOT_ASSESSED = "SURFACE_NOT_ASSESSED"


@dataclass(frozen=True, slots=True)
class Blocker:
    code: str
    details: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class WorkLine:
    name: str
    status: str  # NOT_STARTED / IN_PROGRESS / COMPLETED


@dataclass(frozen=True, slots=True)
class SurfaceFacts:
    """What the application already knows about a surface that may be accepted."""

    id: str
    name: str
    room_id: str
    room_name: str
    surface_type: str
    quality_target: str | None
    works: tuple[WorkLine, ...]

    @property
    def incomplete(self) -> tuple[WorkLine, ...]:
        return tuple(w for w in self.works if w.status != "COMPLETED")


def empty_state() -> dict[str, Any]:
    return {
        "held_on": None, "held_time": None, "customer_absent": False, "notified_on": None, "renotified_on": None, "attendees": [],
        "room_ids": [], "conditions_note": None, "instrument_keys": [], "surfaces": {}, "batches": None, "instructions_given": False,
        "amount_due": None, "amount_retained": None, "notes": None,
    }


# --- the derived result --------------------------------------------------------------------------------------------------------


def surface_result(facts: SurfaceFacts, entry: dict[str, Any] | None) -> str:
    """Not accepted: unfinished works or a significant remark. With remarks: only removable ones. Otherwise accepted."""
    classes = [r["classification"] for r in ((entry or {}).get("remarks") or {}).values()]
    if facts.incomplete or "SIGNIFICANT" in classes:
        return NOT_ACCEPTED
    return WITH_REMARKS if classes else ACCEPTED


def ordered_remarks(entry: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The remarks of a surface in the order they were written. They are kept as a JSON object, whose keys PostgreSQL stores in its own
    order, so every remark carries its `position`."""
    return sorted(((entry or {}).get("remarks") or {}).values(), key=lambda r: (r.get("position", 0), r["id"]))


def overall_result(results: list[str]) -> str | None:
    if not results:
        return None
    if NOT_ACCEPTED in results:
        return NOT_ACCEPTED
    return WITH_REMARKS if WITH_REMARKS in results else ACCEPTED


def surfaces_in_scope(state: dict[str, Any], facts: dict[str, SurfaceFacts]) -> list[SurfaceFacts]:
    """The surfaces with planned works of the chosen rooms, in the order of the object."""
    rooms = set(state.get("room_ids") or [])
    return [f for f in facts.values() if f.room_id in rooms and f.works]


def scope_kind(state: dict[str, Any], facts: dict[str, SurfaceFacts]) -> str | None:
    """FINAL when the rooms in scope are every room that has planned works, otherwise PARTIAL; None while there is no scope."""
    planned_rooms = {f.room_id for f in facts.values() if f.works}
    chosen = set(state.get("room_ids") or []) & planned_rooms
    if not chosen:
        return None
    return "FINAL" if chosen == planned_rooms else "PARTIAL"


def conditions(state: dict[str, Any], facts: dict[str, SurfaceFacts], catalog: ContractCatalog) -> list[dict[str, Any]]:
    """The conditions of the visual assessment of each standard that is in scope (the catalogue's), in the catalogue's order."""
    present = {f.quality_target for f in surfaces_in_scope(state, facts) if f.quality_target}
    return [
        {"key": c.key, "lighting": c.lighting, "requires_agreement": c.requires_agreement, "text_pl": c.text_pl}
        for c in catalog.evaluation.items if c.key in present
    ]


# --- entries -----------------------------------------------------------------------------------------------------------------------


def _text(key: str, value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        raise AcceptanceInvalidError(key, WRONG_TYPE)
    text = " ".join(value.split()) if limit <= 500 else value.strip()
    if len(text) > limit:
        raise AcceptanceInvalidError(key, TOO_LONG)
    return text or None


def _day(key: str, value: Any) -> date | None:
    if value is not None and not isinstance(value, date):
        raise AcceptanceInvalidError(key, WRONG_TYPE)
    return value


def _money(key: str, value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise AcceptanceInvalidError(key, WRONG_TYPE)
    raw = str(value).strip()
    if not _MONEY.match(raw):
        raise AcceptanceInvalidError(key, BAD_MONEY)
    try:
        return f"{Decimal(raw.replace(',', '.')):.2f}"
    except InvalidOperation:  # pragma: no cover - the pattern already guarantees a decimal
        raise AcceptanceInvalidError(key, BAD_MONEY) from None


def _uuid(key: str, value: Any) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except ValueError:
        raise AcceptanceInvalidError(key, WRONG_TYPE) from None


def _remark(remark_id: str, current: dict[str, Any] | None, change: dict[str, Any], photos: set[str]) -> dict[str, Any]:
    if not isinstance(change, dict) or not set(change) <= set(REMARK_FIELDS):
        raise AcceptanceInvalidError("remarks", WRONG_TYPE)
    remark = dict(current or {})
    for key, value in change.items():
        if key in ("place", "description"):
            text = None if value is None else _text(key, value, 255 if key == "place" else 2000)
            remark.pop(key, None)
            if text:
                remark[key] = text
        elif key == "classification":
            if value is not None and value not in CLASSES:
                raise AcceptanceInvalidError("classification", NOT_AN_OPTION)
            remark.pop(key, None)
            if value:
                remark[key] = value
        elif key == "deadline":
            day = _day("deadline", value)
            remark.pop(key, None)
            if day:
                remark[key] = day.isoformat()
        else:  # photo_ids
            chosen: list[str] = []
            for photo in value or []:
                if not isinstance(photo, str):
                    raise AcceptanceInvalidError("photo_ids", WRONG_TYPE)
                if photo not in photos:
                    raise AcceptanceInvalidError("photo_ids", UNKNOWN_PHOTO)
                if photo not in chosen:
                    chosen.append(photo)
            remark["photo_ids"] = chosen
    if not (remark.get("place") and remark.get("description") and remark.get("classification")):
        raise AcceptanceInvalidError("remarks", BAD_REMARK)
    if remark["classification"] == "REMOVABLE" and not remark.get("deadline"):
        raise AcceptanceInvalidError("deadline", BAD_REMARK)  # every removable defect has its deadline (plan, step 6)
    remark.setdefault("photo_ids", [])
    remark["id"] = remark_id
    return remark


def apply_changes(
    current: dict[str, Any],
    changes: dict[str, Any],
    *,
    room_ids: set[str],
    surface_ids: set[str],
    defect_photos_of: Callable[[str], set[str]],
    people: dict[str, tuple[str, str | None]],
    catalog: ContractCatalog,
) -> dict[str, Any]:
    """The protocol's data after `changes`, or `AcceptanceInvalidError` (nothing is applied when one change is refused).

    `surfaces` changes are {surface_id: {"assessed": bool, "remarks": {remark_id: {fields} | None}} | None}; a remark is created or
    changed by sending its fields (a new one needs a place, a description and a class, a removable one a deadline) and removed with
    null."""
    state = {**empty_state(), **{k: (list(v) if isinstance(v, list) else v) for k, v in current.items()}}
    state["surfaces"] = {sid: {**entry, "remarks": {rid: dict(r) for rid, r in (entry.get("remarks") or {}).items()}} for sid, entry in (current.get("surfaces") or {}).items()}
    unknown = [key for key in changes if key not in FIELDS]
    if unknown:
        raise AcceptanceInvalidError(unknown[0], UNKNOWN_FIELD)
    instruments = {i.key for i in catalog.instruments.items}
    for key, value in changes.items():
        if key in ("held_on", "notified_on", "renotified_on"):
            state[key] = _day(key, value)
        elif key == "held_time":
            if value is not None and (not isinstance(value, str) or not _TIME.match(value)):
                raise AcceptanceInvalidError(key, BAD_TIME)
            state[key] = value
        elif key in ("customer_absent", "instructions_given"):
            if value is not None and not isinstance(value, bool):
                raise AcceptanceInvalidError(key, WRONG_TYPE)
            state[key] = bool(value)
        elif key == "attendees":
            try:
                state[key] = normalize_attendees(value, people)
            except HandoverInvalidError as exc:
                raise AcceptanceInvalidError(key, exc.reason) from exc
        elif key == "room_ids":
            if value is None:
                value = []
            if not isinstance(value, list):
                raise AcceptanceInvalidError(key, WRONG_TYPE)
            chosen: list[str] = []
            for room in value:
                room = _uuid(key, room)
                if room not in room_ids:
                    raise AcceptanceInvalidError(key, UNKNOWN_ROOM)
                if room not in chosen:
                    chosen.append(room)
            state[key] = chosen
        elif key == "instrument_keys":
            if value is None:
                value = []
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                raise AcceptanceInvalidError(key, WRONG_TYPE)
            if any(v not in instruments for v in value):
                raise AcceptanceInvalidError(key, UNKNOWN_INSTRUMENT)
            state[key] = list(dict.fromkeys(value))
        elif key in ("conditions_note", "batches", "notes"):
            state[key] = None if value is None else _text(key, value, LONG_TEXT_LIMIT)
        elif key in ("amount_due", "amount_retained"):
            state[key] = _money(key, value)
        else:  # surfaces
            if not isinstance(value, dict):
                raise AcceptanceInvalidError(key, WRONG_TYPE)
            for surface, entry in value.items():
                surface = _uuid("surfaces", surface)
                if surface not in surface_ids:
                    raise AcceptanceInvalidError("surfaces", UNKNOWN_SURFACE)
                if entry is None:
                    state["surfaces"].pop(surface, None)
                    continue
                if not isinstance(entry, dict) or not set(entry) <= {"assessed", "remarks"}:
                    raise AcceptanceInvalidError("surfaces", WRONG_TYPE)
                target = state["surfaces"].setdefault(surface, {"assessed": False, "remarks": {}})
                if "assessed" in entry:
                    if entry["assessed"] is not None and not isinstance(entry["assessed"], bool):
                        raise AcceptanceInvalidError("assessed", WRONG_TYPE)
                    target["assessed"] = bool(entry["assessed"])
                for remark_id, remark in (entry.get("remarks") or {}).items():
                    remark_id = _uuid("remarks", remark_id)
                    if remark is None:
                        target["remarks"].pop(remark_id, None)
                    else:
                        known = target["remarks"].get(remark_id)
                        changed = _remark(remark_id, known, remark, defect_photos_of(surface))
                        if known is None:  # a new remark goes to the end; PostgreSQL does not keep the order of the keys of a JSON object
                            changed["position"] = 1 + max((r.get("position", 0) for r in target["remarks"].values()), default=0)
                        target["remarks"][remark_id] = changed
    return state


# --- what is missing -----------------------------------------------------------------------------------------------------------------


def evaluate(state: dict[str, Any], facts: dict[str, SurfaceFacts], catalog: ContractCatalog) -> list[Blocker]:
    """What must still be done before the protocol can be issued, in the order of doing it."""
    blockers: list[Blocker] = []
    scope = surfaces_in_scope(state, facts)
    if not scope:
        blockers.append(Blocker(SCOPE_REQUIRED))
    if not state.get("held_on"):
        blockers.append(Blocker(HELD_ON_REQUIRED))
    if state.get("customer_absent"):
        # the customer did not come: he was called, and called again with an additional term (contract § 14 ust. 5)
        if not state.get("notified_on"):
            blockers.append(Blocker(NOTIFIED_ON_REQUIRED))
        if not state.get("renotified_on"):
            blockers.append(Blocker(RENOTIFIED_ON_REQUIRED))
        first, second, held = state.get("notified_on"), state.get("renotified_on"), state.get("held_on")
        if (first and second and second <= first) or (second and held and held < second):
            blockers.append(Blocker(NOTIFICATION_ORDER))
    elif not state.get("attendees"):
        blockers.append(Blocker(NO_ATTENDEES))
    if any(c["requires_agreement"] for c in conditions(state, facts, catalog)) and not state.get("conditions_note"):
        blockers.append(Blocker(CONDITIONS_NOTE_REQUIRED))
    unassessed = [f.id for f in scope if not (state.get("surfaces", {}).get(f.id) or {}).get("assessed")]
    if unassessed:
        blockers.append(Blocker(SURFACE_NOT_ASSESSED, {"surface_ids": unassessed}))
    return blockers
