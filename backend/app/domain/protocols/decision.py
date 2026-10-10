"""Rules of the protocol of information and decisions of the customer (Stage 16I.1; annex 9 of the contract).

The contract (`executor_recommendations`) asks for this protocol when the contractor recommends a solution and the customer gives it up
or demands the work done against it. Deterministic and catalogue-driven: an **item** is either a **risk** the application found
(active, `warranty_exclusion_candidate`; its Polish texts are the built-in risk catalogue's) or a recommendation the contractor writes
himself; each item carries the customer's **decision** -- accepts the recommendation (an order follows), gives it up, or insists on the work
against it (and then the contractor says whether he performs it after the protocol or refuses, contract § 17 ust. 3). Nothing here says
what a decision means for the guarantee: that is the contract's (`§ 16 ust. 3 lit. f`), which the page only points at.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from app.domain.exceptions import DecisionInvalidError, HandoverInvalidError
from app.domain.protocols.handover import (
    BAD_TIME, LONG_TEXT_LIMIT, NOT_AN_OPTION, TOO_LONG, WRONG_TYPE, normalize_attendees,
)

DECISIONS = ("ACCEPTED", "DECLINED", "INSISTS")
ACTIONS = ("PERFORM", "REFUSE")  # what the contractor does when the customer insists on the work against the recommendation
FIELDS = ("held_on", "held_time", "attendees", "items", "understood", "signature_refused", "notes")
ITEM_FIELDS = ("risk_id", "room_id", "title", "recommendation", "consequence", "price", "decision", "executor_action", "order_ref", "note")
OWN_TEXTS = {"title": 255, "recommendation": 2000, "consequence": 2000}
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
_MONEY = re.compile(r"^\d{1,9}([.,]\d{1,2})?$")

UNKNOWN_FIELD = "UNKNOWN_FIELD"
UNKNOWN_RISK = "UNKNOWN_RISK"
UNKNOWN_ROOM = "UNKNOWN_ROOM"
BAD_ITEM = "BAD_ITEM"  # a new item needs a risk, or a title, a recommendation and a consequence
BAD_MONEY = "BAD_MONEY"
ITEM_LOCKED = "ITEM_LOCKED"  # the risk of an item is not changed: remove the item and add another

# what is missing before the protocol can be issued
EXECUTOR_PROFILE_REQUIRED = "EXECUTOR_PROFILE_REQUIRED"
CLIENT_REQUIRED = "CLIENT_REQUIRED"
CONTRACT_REQUIRED = "CONTRACT_REQUIRED"
HELD_ON_REQUIRED = "HELD_ON_REQUIRED"
NO_ATTENDEES = "NO_ATTENDEES"
NO_ITEMS = "NO_ITEMS"
ITEM_RISK_GONE = "ITEM_RISK_GONE"  # the risk of an item is no longer active
ITEM_DECISION_REQUIRED = "ITEM_DECISION_REQUIRED"
ITEM_ACTION_REQUIRED = "ITEM_ACTION_REQUIRED"  # the customer insists: the contractor performs or refuses
DECLARATION_REQUIRED = "DECLARATION_REQUIRED"  # the customer did not declare that he understood, and did not refuse to sign
REFUSAL_NOTE_REQUIRED = "REFUSAL_NOTE_REQUIRED"  # a refusal to sign is written down with its circumstances


@dataclass(frozen=True, slots=True)
class Blocker:
    code: str
    details: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class RiskFacts:
    """An active risk of the object that may be put into the protocol (its texts are resolved by the caller from the catalogue)."""

    id: str
    room_id: str
    room_name: str
    severity: str
    title_key: str
    explanation_key: str
    consequence_key: str
    communication_key: str
    blocks_finishing: bool


def empty_state() -> dict[str, Any]:
    return {"held_on": None, "held_time": None, "attendees": [], "items": [], "understood": False, "signature_refused": False, "notes": None}


def _text(key: str, value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        raise DecisionInvalidError(key, WRONG_TYPE)
    text = " ".join(value.split()) if limit <= 500 else value.strip()
    if len(text) > limit:
        raise DecisionInvalidError(key, TOO_LONG)
    return text or None


def _day(key: str, value: Any) -> date | None:
    if value is not None and not isinstance(value, date):
        raise DecisionInvalidError(key, WRONG_TYPE)
    return value


def _uuid(key: str, value: Any) -> str:
    try:
        return str(uuid.UUID(str(value)))
    except ValueError:
        raise DecisionInvalidError(key, WRONG_TYPE) from None


def _money(key: str, value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise DecisionInvalidError(key, WRONG_TYPE)
    raw = str(value).strip()
    if not _MONEY.match(raw):
        raise DecisionInvalidError(key, BAD_MONEY)
    try:
        return f"{Decimal(raw.replace(',', '.')):.2f}"
    except InvalidOperation:  # pragma: no cover - the pattern already guarantees a decimal
        raise DecisionInvalidError(key, BAD_MONEY) from None


def _item(item_id: str, current: dict[str, Any] | None, change: Any, risks: dict[str, RiskFacts], room_ids: set[str]) -> dict[str, Any]:
    if not isinstance(change, dict) or not set(change) <= set(ITEM_FIELDS):
        raise DecisionInvalidError("items", WRONG_TYPE)
    item = dict(current or {})
    if "risk_id" in change:
        risk_id = change["risk_id"]
        if current is not None and risk_id != current.get("risk_id"):
            raise DecisionInvalidError("risk_id", ITEM_LOCKED)
        if risk_id is not None:
            risk_id = _uuid("risk_id", risk_id)
            if risk_id not in risks:
                raise DecisionInvalidError("risk_id", UNKNOWN_RISK)
            item["risk_id"], item["source"] = risk_id, "RISK"
    own = item.get("source") != "RISK"
    for key, value in change.items():
        if key == "risk_id":
            continue
        if key in OWN_TEXTS or key in ("price", "room_id"):
            if not own:  # the texts of a risk are the catalogue's, not the owner's
                raise DecisionInvalidError(key, ITEM_LOCKED)
            item.pop(key, None)
            if key == "room_id":
                if value is not None:
                    room = _uuid(key, value)
                    if room not in room_ids:
                        raise DecisionInvalidError(key, UNKNOWN_ROOM)
                    item[key] = room
            elif key == "price":
                if (price := _money(key, value)) is not None:
                    item[key] = price
            elif value is not None and (text := _text(key, value, OWN_TEXTS[key])):
                item[key] = text
        elif key == "decision":
            if value is not None and value not in DECISIONS:
                raise DecisionInvalidError(key, NOT_AN_OPTION)
            item.pop(key, None)
            if value:
                item[key] = value
        elif key == "executor_action":
            if value is not None and value not in ACTIONS:
                raise DecisionInvalidError(key, NOT_AN_OPTION)
            item.pop(key, None)
            if value:
                item[key] = value
        else:  # order_ref, note
            limit = 64 if key == "order_ref" else 2000
            item.pop(key, None)
            if value is not None and (text := _text(key, value, limit)):
                item[key] = text
    if item.get("decision") != "INSISTS":  # the contractor's answer to a demand exists only with a demand
        item.pop("executor_action", None)
    if item.get("decision") != "ACCEPTED":
        item.pop("order_ref", None)
    if "source" not in item:
        if not (item.get("title") and item.get("recommendation") and item.get("consequence")):
            raise DecisionInvalidError("items", BAD_ITEM)
        item["source"] = "OWN"
    item["id"] = item_id
    return item


def apply_changes(
    current: dict[str, Any],
    changes: dict[str, Any],
    *,
    risks: dict[str, RiskFacts],
    room_ids: set[str],
    people: dict[str, tuple[str, str | None]],
) -> dict[str, Any]:
    """The protocol's data after `changes`, or `DecisionInvalidError` (nothing is applied when one change is refused).

    `items` changes are {item_id: {fields} | None}: a new item is created by sending a `risk_id`, or a title, a recommendation and a
    consequence (the contractor's own recommendation); an existing one is changed by its fields (the risk of an item is not changed);
    null removes it. New items go to the end of the list."""
    state = {**empty_state(), **{k: (list(v) if isinstance(v, list) else v) for k, v in current.items()}}
    state["items"] = [dict(i) for i in current.get("items") or []]
    unknown = [key for key in changes if key not in FIELDS]
    if unknown:
        raise DecisionInvalidError(unknown[0], UNKNOWN_FIELD)
    for key, value in changes.items():
        if key == "held_on":
            state[key] = _day(key, value)
        elif key == "held_time":
            if value is not None and (not isinstance(value, str) or not _TIME.match(value)):
                raise DecisionInvalidError(key, BAD_TIME)
            state[key] = value
        elif key in ("understood", "signature_refused"):
            if value is not None and not isinstance(value, bool):
                raise DecisionInvalidError(key, WRONG_TYPE)
            state[key] = bool(value)
        elif key == "attendees":
            try:
                state[key] = normalize_attendees(value, people)
            except HandoverInvalidError as exc:
                raise DecisionInvalidError(key, exc.reason) from exc
        elif key == "notes":
            state[key] = None if value is None else _text(key, value, LONG_TEXT_LIMIT)
        else:  # items
            if not isinstance(value, dict):
                raise DecisionInvalidError(key, WRONG_TYPE)
            for raw_id, change in value.items():
                item_id = _uuid("items", raw_id)
                index = next((i for i, item in enumerate(state["items"]) if item["id"] == item_id), None)
                if change is None:
                    if index is not None:
                        del state["items"][index]
                    continue
                item = _item(item_id, state["items"][index] if index is not None else None, change, risks, room_ids)
                if index is None:
                    state["items"].append(item)
                else:
                    state["items"][index] = item
    return state


# --- what is missing -----------------------------------------------------------------------------------------------------------------


def evaluate(state: dict[str, Any], risks: dict[str, RiskFacts]) -> list[Blocker]:
    """What must still be done before the protocol can be issued, in the order of doing it."""
    blockers: list[Blocker] = []
    items = state.get("items") or []
    if not state.get("held_on"):
        blockers.append(Blocker(HELD_ON_REQUIRED))
    if not state.get("attendees"):
        blockers.append(Blocker(NO_ATTENDEES))
    if not items:
        blockers.append(Blocker(NO_ITEMS))
    gone = [i["id"] for i in items if i.get("source") == "RISK" and i.get("risk_id") not in risks]
    if gone:
        blockers.append(Blocker(ITEM_RISK_GONE, {"item_ids": gone}))
    undecided = [i["id"] for i in items if not i.get("decision")]
    if undecided:
        blockers.append(Blocker(ITEM_DECISION_REQUIRED, {"item_ids": undecided}))
    unanswered = [i["id"] for i in items if i.get("decision") == "INSISTS" and not i.get("executor_action")]
    if unanswered:
        blockers.append(Blocker(ITEM_ACTION_REQUIRED, {"item_ids": unanswered}))
    if not state.get("understood") and not state.get("signature_refused"):
        blockers.append(Blocker(DECLARATION_REQUIRED))
    if state.get("signature_refused") and not state.get("notes"):
        blockers.append(Blocker(REFUSAL_NOTE_REQUIRED))
    return blockers

