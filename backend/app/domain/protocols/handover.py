"""Rules of the protocol of handing over the premises (Stage 16F.1): what an entry may be, what decision it allows, what is missing.

Deterministic and catalogue-driven, like the answers of the contract: the requirements are the catalogue of the premises
(`premises_requirements.json`, the same list as annex 4 of the contract), a state is one of four words, a measured value must fit
the kind of its requirement. Nothing is judged by the code except one rule that protects the contractor and the customer alike: a
room may be marked **handed over** only when every requirement is met (or does not apply); with an unmet or conditional requirement
the decision is *handed over conditionally* (the risk is then written in the protocol, contract § 8 ust. 4 and § 17) or *not handed
over*. The numbers themselves are the owner's (contract annex 4); the protocol only records what was found.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.domain.contracts.answers import TEXT_LIMIT, _requirement_value
from app.domain.contracts.catalog import ContractCatalog
from app.domain.exceptions import ContractAnswerInvalidError, HandoverInvalidError

STATES = ("YES", "NO", "CONDITIONAL", "NOT_APPLICABLE")
DECISIONS = ("HANDED_OVER", "CONDITIONAL", "NOT_HANDED_OVER")
LONG_TEXT_LIMIT = 4000
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

# reasons the screen has a sentence for
WRONG_TYPE = "WRONG_TYPE"
NOT_AN_OPTION = "NOT_AN_OPTION"
TOO_LONG = "TOO_LONG"
BAD_TIME = "BAD_TIME"
UNKNOWN_ROOM = "UNKNOWN_ROOM"
UNKNOWN_REQUIREMENT = "UNKNOWN_REQUIREMENT"
UNKNOWN_PERSON = "UNKNOWN_PERSON"
OUT_OF_RANGE = "OUT_OF_RANGE"

# what is missing before the protocol can be issued
EXECUTOR_PROFILE_REQUIRED = "EXECUTOR_PROFILE_REQUIRED"
CLIENT_REQUIRED = "CLIENT_REQUIRED"
CONTRACT_REQUIRED = "CONTRACT_REQUIRED"  # the requirements are the contract's: there is nothing to hand over against without one
HELD_ON_REQUIRED = "HELD_ON_REQUIRED"
NO_ATTENDEES = "NO_ATTENDEES"
NO_ROOMS = "NO_ROOMS"
REQUIREMENTS_MISSING = "REQUIREMENTS_MISSING"
DECISION_MISSING = "DECISION_MISSING"
DECISION_TOO_FAVOURABLE = "DECISION_TOO_FAVOURABLE"


@dataclass(frozen=True, slots=True)
class Blocker:
    code: str
    details: dict[str, Any] | None = None


def _text(key: str, value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        raise HandoverInvalidError(key, WRONG_TYPE)
    text = " ".join(value.split()) if limit == TEXT_LIMIT else value.strip()
    if len(text) > limit:
        raise HandoverInvalidError(key, TOO_LONG)
    return text or None


def suggested_decision(requirements: dict[str, Any], catalog: ContractCatalog) -> str | None:
    """The best decision the findings allow, or None while a requirement is still unanswered."""
    states = [(requirements.get(r.key) or {}).get("state") for r in catalog.requirements.items]
    if any(s is None for s in states):
        return None
    if "NO" in states:
        return "NOT_HANDED_OVER"
    if "CONDITIONAL" in states:
        return "CONDITIONAL"
    return "HANDED_OVER"


def _allowed(decision: str, suggested: str | None) -> bool:
    """A decision may be as strict as the findings or stricter; with an unmet requirement a conditional start is the owner's choice."""
    if suggested is None or decision == "NOT_HANDED_OVER":
        return True
    if decision == "CONDITIONAL":
        return True
    return suggested == "HANDED_OVER"


def _requirement_entry(key: str, entry: Any, requirement: Any) -> dict[str, Any]:
    if not isinstance(entry, dict) or not set(entry) <= {"state", "value", "note"}:
        raise HandoverInvalidError(key, WRONG_TYPE)
    result: dict[str, Any] = {}
    if "state" in entry:
        if entry["state"] not in STATES:
            raise HandoverInvalidError(key, NOT_AN_OPTION)
        result["state"] = entry["state"]
    if "value" in entry:
        if entry["value"] is None:
            result["value"] = None  # cleared: the merge drops it
        elif requirement.value_kind == "YES_NO":
            raise HandoverInvalidError(key, WRONG_TYPE)  # a yes / no requirement is its state, there is no number to measure
        else:
            try:
                result["value"] = _requirement_value(key, requirement, entry["value"])
            except ContractAnswerInvalidError as exc:
                raise HandoverInvalidError(key, exc.reason) from exc
    if "note" in entry:
        result["note"] = None if entry["note"] is None else _text(key, entry["note"], TEXT_LIMIT)  # None / blank: cleared
    return result


def apply_changes(
    current: dict[str, Any],
    changes: dict[str, Any],
    *,
    room_ids: set[str],
    people: dict[str, tuple[str, str | None]],
    catalog: ContractCatalog,
) -> dict[str, Any]:
    """The protocol's data after `changes`, or `HandoverInvalidError` (nothing is applied when one change is refused).

    `current` and the result: {"held_on", "held_time", "attendees", "rooms", "meters", "notes"}. `people` maps the id of an active
    person of the object to (name, role). A change that is None clears the field / the entry."""
    state = {key: (dict(value) if isinstance(value, dict) else list(value) if isinstance(value, list) else value) for key, value in current.items()}
    state["rooms"] = {rid: {**room, "requirements": dict(room.get("requirements") or {})} for rid, room in (current.get("rooms") or {}).items()}
    requirements = {r.key: r for r in catalog.requirements.items}
    for key, value in changes.items():
        if key == "held_on":
            if value is not None and not isinstance(value, date):
                raise HandoverInvalidError(key, WRONG_TYPE)
            state[key] = value
        elif key == "held_time":
            if value is not None and (not isinstance(value, str) or not _TIME.match(value)):
                raise HandoverInvalidError(key, BAD_TIME)
            state[key] = value
        elif key in ("meters", "notes"):
            state[key] = None if value is None else _text(key, value, LONG_TEXT_LIMIT)
        elif key == "attendees":
            state[key] = _attendees(value, people)
        elif key == "rooms":
            if not isinstance(value, dict):
                raise HandoverInvalidError(key, WRONG_TYPE)
            for room_id, room_change in value.items():
                if room_id not in room_ids:
                    raise HandoverInvalidError("rooms", UNKNOWN_ROOM)
                if room_change is None:
                    state["rooms"].pop(room_id, None)
                    continue
                state["rooms"][room_id] = _room(room_id, state["rooms"].get(room_id, {"requirements": {}}), room_change, requirements)
        else:
            raise HandoverInvalidError(key, UNKNOWN_REQUIREMENT)
    return state


def _attendees(value: Any, people: dict[str, tuple[str, str | None]]) -> list[dict[str, Any]]:
    """A list of {"person_id"} (a person of the register, copied by name) or {"name", "role"} (somebody who is not in it)."""
    if not isinstance(value, list):
        raise HandoverInvalidError("attendees", WRONG_TYPE)
    result: list[dict[str, Any]] = []
    for entry in value:
        if not isinstance(entry, dict) or not set(entry) <= {"person_id", "name", "role"}:
            raise HandoverInvalidError("attendees", WRONG_TYPE)
        if entry.get("person_id") is not None:
            try:
                person = str(uuid.UUID(str(entry["person_id"])))
            except ValueError:
                raise HandoverInvalidError("attendees", WRONG_TYPE) from None
            if person not in people:
                raise HandoverInvalidError("attendees", UNKNOWN_PERSON)
            if any(a["person_id"] == person for a in result):
                continue
            name, role = people[person]
            result.append({"person_id": person, "name": name, "role": role})
        else:
            name = _text("attendees", entry.get("name", ""), TEXT_LIMIT) if "name" in entry else None
            if not name:
                raise HandoverInvalidError("attendees", WRONG_TYPE)
            role = _text("attendees", entry["role"], TEXT_LIMIT) if entry.get("role") is not None else None
            result.append({"person_id": None, "name": name, "role": role})
    return result


normalize_attendees = _attendees  # the list of people present is the same in every protocol


def _room(room_id: str, room: dict[str, Any], change: Any, requirements: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(change, dict) or not set(change) <= {"requirements", "damages", "decision"}:
        raise HandoverInvalidError("rooms", WRONG_TYPE)
    result = {**room, "requirements": dict(room.get("requirements") or {})}
    for key, value in change.items():
        if key == "damages":
            damages = None if value is None else _text("damages", value, LONG_TEXT_LIMIT)
            result.pop("damages", None)
            if damages:
                result["damages"] = damages
        elif key == "decision":
            if value is None:
                result.pop("decision", None)
            elif value not in DECISIONS:
                raise HandoverInvalidError("decision", NOT_AN_OPTION)
            else:
                result["decision"] = value
        else:  # requirements
            if not isinstance(value, dict):
                raise HandoverInvalidError("requirements", WRONG_TYPE)
            for requirement_key, entry in value.items():
                if requirement_key not in requirements:
                    raise HandoverInvalidError("requirements", UNKNOWN_REQUIREMENT)
                if entry is None:
                    result["requirements"].pop(requirement_key, None)
                    continue
                merged = {**result["requirements"].get(requirement_key, {}), **_requirement_entry(requirement_key, entry, requirements[requirement_key])}
                result["requirements"][requirement_key] = {k: v for k, v in merged.items() if v is not None}  # None clears a field
    return result


def evaluate(data: dict[str, Any], catalog: ContractCatalog) -> list[Blocker]:
    """What must still be done before the protocol can be issued, in the order of doing it."""
    blockers: list[Blocker] = []
    if not data.get("held_on"):
        blockers.append(Blocker(HELD_ON_REQUIRED))
    if not data.get("attendees"):
        blockers.append(Blocker(NO_ATTENDEES))
    rooms = data.get("rooms") or {}
    if not rooms:
        blockers.append(Blocker(NO_ROOMS))
        return blockers
    unanswered, undecided, too_favourable = [], [], []
    for room_id, room in rooms.items():
        answered = room.get("requirements") or {}
        missing = [r.key for r in catalog.requirements.items if not (answered.get(r.key) or {}).get("state")]
        if missing:
            unanswered.append({"room_id": room_id, "keys": missing})
        decision = room.get("decision")
        if decision is None:
            undecided.append(room_id)
        elif not _allowed(decision, suggested_decision(answered, catalog)):
            too_favourable.append(room_id)
    if unanswered:
        blockers.append(Blocker(REQUIREMENTS_MISSING, {"rooms": unanswered}))
    if undecided:
        blockers.append(Blocker(DECISION_MISSING, {"room_ids": undecided}))
    if too_favourable:
        blockers.append(Blocker(DECISION_TOO_FAVOURABLE, {"room_ids": too_favourable}))
    return blockers
