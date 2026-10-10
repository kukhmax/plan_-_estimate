"""Rules of the notice and the protocol of downtime on the customer's side (Stage 16I.3; annex 8 of the contract, `downtime`, § 10).

Two documents of one episode. The **notice** says at once, in a documentary form, what stops the work (a cause from the catalogue), in
which rooms, with photos, and what the contractor needs and until when (`§ 10 ust. 2`). If the obstacle stays, the **protocol** confirms
the **days** on which the contractor was ready and could not work: every day is after the notice, a working day (Monday to Friday; the
calendar of public holidays is not kept here), and says whether other work could be done that day -- such a day is no downtime day and is
not paid for. The sum for readiness is **derived** from the frozen contract: the rate per day, the cap as a percentage of the estimated
remuneration; nothing is typed, nothing is invented -- a rate or a cap the contract leaves empty stays empty.
"""

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from app.domain.contracts.catalog import ContractCatalog
from app.domain.exceptions import DowntimeInvalidError, HandoverInvalidError
from app.domain.protocols.handover import BAD_TIME, LONG_TEXT_LIMIT, TOO_LONG, WRONG_TYPE, normalize_attendees

NOTICE_FIELDS = ("cause_key", "cause_note", "room_ids", "noticed_on", "noticed_time", "notice_channel", "photo_ids", "need_text", "need_by")
PROTOCOL_FIELDS = ("days", "held_on", "held_time", "attendees", "signature_refused", "deadline_note", "notes")
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

UNKNOWN_FIELD = "UNKNOWN_FIELD"
UNKNOWN_CAUSE = "UNKNOWN_CAUSE"
UNKNOWN_ROOM = "UNKNOWN_ROOM"
UNKNOWN_PHOTO = "UNKNOWN_PHOTO"
NOTICE_FROZEN = "NOTICE_FROZEN"  # the notice is issued: its entries are not changed any more
NOT_NOTICED_YET = "NOT_NOTICED_YET"  # the days are confirmed only after the notice
BAD_DAY = "BAD_DAY"  # not a date, not after the day of the notice, or not a working day (Saturday, Sunday)

# what is missing before the notice can be issued
EXECUTOR_PROFILE_REQUIRED = "EXECUTOR_PROFILE_REQUIRED"
CLIENT_REQUIRED = "CLIENT_REQUIRED"
CONTRACT_REQUIRED = "CONTRACT_REQUIRED"
CAUSE_REQUIRED = "CAUSE_REQUIRED"
CAUSE_NOTE_REQUIRED = "CAUSE_NOTE_REQUIRED"  # the cause "other" is described
NOTICED_ON_REQUIRED = "NOTICED_ON_REQUIRED"
NEED_REQUIRED = "NEED_REQUIRED"  # what the contractor needs from the customer
PHOTOS_REQUIRED = "PHOTOS_REQUIRED"  # the notice goes with photos (§ 10 ust. 2)
# ... and before the protocol can be issued
DAYS_REQUIRED = "DAYS_REQUIRED"
HELD_ON_REQUIRED = "HELD_ON_REQUIRED"
DAY_AFTER_PROTOCOL = "DAY_AFTER_PROTOCOL"  # a day of downtime later than the day of the protocol
NO_ATTENDEES = "NO_ATTENDEES"
REFUSAL_NOTE_REQUIRED = "REFUSAL_NOTE_REQUIRED"


@dataclass(frozen=True, slots=True)
class Blocker:
    code: str
    details: dict[str, Any] | None = None


def empty_state() -> dict[str, Any]:
    return {
        "cause_key": None, "cause_note": None, "room_ids": [], "noticed_on": None, "noticed_time": None, "notice_channel": None, "photo_ids": [],
        "need_text": None, "need_by": None, "days": [], "held_on": None, "held_time": None, "attendees": [], "signature_refused": False,
        "deadline_note": None, "notes": None,
    }


def _text(key: str, value: Any, limit: int) -> str | None:
    if not isinstance(value, str):
        raise DowntimeInvalidError(key, WRONG_TYPE)
    text = " ".join(value.split()) if limit <= 500 else value.strip()
    if len(text) > limit:
        raise DowntimeInvalidError(key, TOO_LONG)
    return text or None


def _day(key: str, value: Any) -> date | None:
    if value is not None and not isinstance(value, date):
        raise DowntimeInvalidError(key, WRONG_TYPE)
    return value


def _time(key: str, value: Any) -> str | None:
    if value is not None and (not isinstance(value, str) or not _TIME.match(value)):
        raise DowntimeInvalidError(key, BAD_TIME)
    return value


def _uuids(key: str, value: Any, known: set[str], reason: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise DowntimeInvalidError(key, WRONG_TYPE)
    chosen: list[str] = []
    for raw in value:
        try:
            item = str(uuid.UUID(str(raw)))
        except ValueError:
            raise DowntimeInvalidError(key, WRONG_TYPE) from None
        if item not in known:
            raise DowntimeInvalidError(key, reason)
        if item not in chosen:
            chosen.append(item)
    return chosen


def _day_entry(day: date, current: dict[str, Any] | None, change: Any, noticed_on: date | None) -> dict[str, Any]:
    if not isinstance(change, dict) or not set(change) <= {"other_work", "note"}:
        raise DowntimeInvalidError("days", WRONG_TYPE)
    if noticed_on is None or day <= noticed_on or day.weekday() >= 5:
        raise DowntimeInvalidError("days", BAD_DAY)
    entry = dict(current or {"date": day.isoformat(), "other_work": False})
    if "other_work" in change:
        if change["other_work"] is not None and not isinstance(change["other_work"], bool):
            raise DowntimeInvalidError("other_work", WRONG_TYPE)
        entry["other_work"] = bool(change["other_work"])
    if "note" in change:
        entry.pop("note", None)
        if change["note"] is not None and (note := _text("note", change["note"], 500)):
            entry["note"] = note
    return entry


def apply_changes(
    current: dict[str, Any],
    changes: dict[str, Any],
    *,
    status: str,
    room_ids: set[str],
    photos_of: Callable[[list[str]], set[str]],
    people: dict[str, tuple[str, str | None]],
    catalog: ContractCatalog,
) -> dict[str, Any]:
    """The episode's data after `changes`, or `DowntimeInvalidError` (nothing is applied when one change is refused).

    While the episode is a DRAFT only the notice's entries change, once it is NOTICED only the protocol's. `days` changes are
    {"2026-10-14": {"other_work": bool, "note": text} | None}: a day is created or changed by sending its fields and removed with null."""
    state = {**empty_state(), **{k: (list(v) if isinstance(v, list) else v) for k, v in current.items()}}
    state["days"] = [dict(d) for d in current.get("days") or []]
    for key in changes:
        if key not in NOTICE_FIELDS and key not in PROTOCOL_FIELDS:
            raise DowntimeInvalidError(key, UNKNOWN_FIELD)
        if key in NOTICE_FIELDS and status != "DRAFT":
            raise DowntimeInvalidError(key, NOTICE_FROZEN)
        if key in PROTOCOL_FIELDS and status != "NOTICED":
            raise DowntimeInvalidError(key, NOT_NOTICED_YET)
    causes = {c.key for c in catalog.downtime_causes.items}
    for key, value in changes.items():
        if key == "cause_key":
            if value is not None and value not in causes:
                raise DowntimeInvalidError(key, UNKNOWN_CAUSE)
            state[key] = value
        elif key in ("cause_note", "need_text", "deadline_note", "notes"):
            state[key] = None if value is None else _text(key, value, LONG_TEXT_LIMIT)
        elif key == "notice_channel":
            state[key] = None if value is None else _text(key, value, 255)
        elif key == "room_ids":
            state[key] = _uuids(key, value, room_ids, UNKNOWN_ROOM)
        elif key == "photo_ids":
            state[key] = None  # settled below, against the rooms as they will be
            state["_photos"] = value
        elif key in ("noticed_on", "need_by", "held_on"):
            state[key] = _day(key, value)
        elif key in ("noticed_time", "held_time"):
            state[key] = _time(key, value)
        elif key == "signature_refused":
            if value is not None and not isinstance(value, bool):
                raise DowntimeInvalidError(key, WRONG_TYPE)
            state[key] = bool(value)
        elif key == "attendees":
            try:
                state[key] = normalize_attendees(value, people)
            except HandoverInvalidError as exc:
                raise DowntimeInvalidError(key, exc.reason) from exc
        else:  # days
            if not isinstance(value, dict):
                raise DowntimeInvalidError(key, WRONG_TYPE)
            for raw_day, change in value.items():
                try:
                    day = date.fromisoformat(raw_day)
                except (TypeError, ValueError):
                    raise DowntimeInvalidError(key, BAD_DAY) from None
                index = next((i for i, d in enumerate(state["days"]) if d["date"] == day.isoformat()), None)
                if change is None:
                    if index is not None:
                        del state["days"][index]
                    continue
                entry = _day_entry(day, state["days"][index] if index is not None else None, change, state["noticed_on"])
                if index is None:
                    state["days"].append(entry)
                else:
                    state["days"][index] = entry
            state["days"].sort(key=lambda d: d["date"])
    # the photos are those of the rooms as they will be: changing the rooms drops the photos that no longer belong
    if status == "DRAFT":
        allowed = photos_of(state["room_ids"])
        if "_photos" in state:
            state["photo_ids"] = _uuids("photo_ids", state.pop("_photos"), allowed, UNKNOWN_PHOTO)
        else:
            state["photo_ids"] = [p for p in current.get("photo_ids") or [] if p in allowed]
    else:  # the notice is issued: its photos stay as they were
        state.pop("_photos", None)
        state["photo_ids"] = list(current.get("photo_ids") or [])
    return state


# --- what is missing -----------------------------------------------------------------------------------------------------------------


def evaluate_notice(state: dict[str, Any]) -> list[Blocker]:
    """What must still be done before the notice can be issued, in the order of doing it."""
    blockers: list[Blocker] = []
    if not state.get("cause_key"):
        blockers.append(Blocker(CAUSE_REQUIRED))
    elif state["cause_key"] == "other" and not state.get("cause_note"):
        blockers.append(Blocker(CAUSE_NOTE_REQUIRED))
    if not state.get("noticed_on"):
        blockers.append(Blocker(NOTICED_ON_REQUIRED))
    if not state.get("need_text"):
        blockers.append(Blocker(NEED_REQUIRED))
    if not state.get("photo_ids"):
        blockers.append(Blocker(PHOTOS_REQUIRED))
    return blockers


def evaluate_protocol(state: dict[str, Any]) -> list[Blocker]:
    """What must still be done before the protocol can be issued, in the order of doing it."""
    blockers: list[Blocker] = []
    days = state.get("days") or []
    if not days:
        blockers.append(Blocker(DAYS_REQUIRED))
    if not state.get("held_on"):
        blockers.append(Blocker(HELD_ON_REQUIRED))
    else:
        late = [d["date"] for d in days if date.fromisoformat(d["date"]) > state["held_on"]]
        if late:
            blockers.append(Blocker(DAY_AFTER_PROTOCOL, {"days": late}))
    if not state.get("attendees"):
        blockers.append(Blocker(NO_ATTENDEES))
    if state.get("signature_refused") and not state.get("notes"):
        blockers.append(Blocker(REFUSAL_NOTE_REQUIRED))
    return blockers


# --- the sum for readiness --------------------------------------------------------------------------------------------------------------


def _decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool) or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", "."))
    except InvalidOperation:
        return None


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def settlement(days: list[dict[str, Any]], contract_snapshot: dict[str, Any] | None) -> dict[str, Any]:
    """The days and the sum for readiness, from the frozen contract: `chargeable` are the days without other work; the sum is the rate
    per day times them, **not more than** the cap (a percentage of the estimated remuneration). A rate, a cap or a total the contract
    does not hold leaves the matching value empty; the limit of days (the contract's own) only says whether the downtime has run past it."""
    answers = (contract_snapshot or {}).get("answers") or {}
    estimate = (contract_snapshot or {}).get("estimate") or {}
    chargeable = sum(1 for d in days if not d.get("other_work"))
    rate = _decimal(answers.get("downtime_rate_per_day"))
    cap_percent, total = _decimal(answers.get("downtime_cap_percent")), _decimal(estimate.get("total"))
    cap = _money(total * cap_percent / Decimal(100)) if cap_percent is not None and total is not None else None
    amount = _money(rate * chargeable) if rate is not None else None
    payable = amount if amount is None or cap is None else min(amount, cap)
    limit = answers.get("downtime_days_limit")
    limit_days = int(limit) if isinstance(limit, (int, float)) and not isinstance(limit, bool) else None
    return {
        "listed": len(days), "chargeable": chargeable, "rate": rate, "amount": amount, "cap": cap, "capped": amount is not None and cap is not None and amount > cap,
        "payable": payable, "limit_days": limit_days, "limit_exceeded": limit_days is not None and len(days) > limit_days,
    }
