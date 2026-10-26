"""The checklist of the electrician and of the plumber (V2-14; docs/V2_14_PLAN_RU.md): the typical positions of a room, the checks of what a craftsman writes.

Pure rules, no database and no web framework. The typical positions are fixed here, never in a screen: each has a key (the screens name it in their language), a unit (pieces or
metres of a route) and an upper limit. A craftsman may add positions of his own (a name, a quantity, a unit, a note); everything he writes is cleaned and bounded here.
"""
import hashlib
import json
import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from app.domain.rules.trades import ELECTRIC, PLUMBING

TRADES = (ELECTRIC, PLUMBING)
PCS = "PCS"
LM = "LM"
UNITS = (PCS, LM)
MAX_NOTE = 200
MAX_NAME = 80
MAX_OWN_PER_ROOM = 30
MAX_TYPICAL_NOTE = MAX_NOTE
MAX_COMMENT = 1000
MAX_PIECES = Decimal(500)
MAX_METRES = Decimal(5000)


class TradeChecklistError(Exception):
    """A rule of the checklist is broken; `code` is the machine word the screens translate, `field` the entry it concerns."""

    def __init__(self, code: str, message: str = "", field: str | None = None) -> None:
        super().__init__(message or code)
        self.code = code
        self.field = field


@dataclass(frozen=True, slots=True)
class Position:
    key: str
    unit: str


# In the order of a walk through a room.
POSITIONS: dict[str, tuple[Position, ...]] = {
    ELECTRIC: (
        Position("SOCKET", PCS),
        Position("SWITCH", PCS),
        Position("LIGHT_POINT", PCS),
        Position("CIRCUIT", PCS),
        Position("CABLE_ROUTE", LM),
    ),
    PLUMBING: (
        Position("WATER_POINT", PCS),
        Position("DRAIN_POINT", PCS),
        Position("MANIFOLD_OUT", PCS),
        Position("PIPE_ROUTE", LM),
    ),
}


def positions_of(trade: str) -> tuple[Position, ...]:
    if trade not in POSITIONS:
        raise TradeChecklistError("UNKNOWN_TRADE", f"no checklist for {trade!r}", "trade")
    return POSITIONS[trade]


def clean_trade(value: str | None) -> str:
    if value not in TRADES:
        raise TradeChecklistError("UNKNOWN_TRADE", "the link is for the electrician or the plumber", "trade")
    return str(value)


def clean_quantity(unit: str, value: object) -> Decimal | None:
    """None (blank) = not answered; zero is an answer ("none needed"). Pieces are whole numbers, metres have at most two decimals."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise TradeChecklistError("QUANTITY_INVALID", "write a number", "quantity")
    try:
        number = Decimal(str(value).strip().replace(",", "."))
    except Exception:  # noqa: BLE001 -- any unreadable text is the same refusal
        raise TradeChecklistError("QUANTITY_INVALID", "write a number", "quantity") from None
    if not number.is_finite() or number < 0:
        raise TradeChecklistError("QUANTITY_INVALID", "the quantity cannot be negative", "quantity")
    if unit == PCS:
        if number != number.to_integral_value():
            raise TradeChecklistError("QUANTITY_NOT_WHOLE", "pieces are counted whole", "quantity")
        if number > MAX_PIECES:
            raise TradeChecklistError("QUANTITY_TOO_BIG", f"at most {MAX_PIECES} pieces", "quantity")
        return number.quantize(Decimal("0.01"))
    metres = number.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if metres != number:
        raise TradeChecklistError("QUANTITY_TOO_PRECISE", "metres with at most two decimals", "quantity")
    if metres > MAX_METRES:
        raise TradeChecklistError("QUANTITY_TOO_BIG", f"at most {MAX_METRES} metres", "quantity")
    return metres


def clean_note(value: str | None) -> str | None:
    text = re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]", " ", value or "")).strip()
    if not text:
        return None
    if len(text) > MAX_NOTE:
        raise TradeChecklistError("NOTE_TOO_LONG", f"at most {MAX_NOTE} characters", "note")
    return text


def clean_own_name(value: str | None) -> str:
    text = re.sub(r"\s+", " ", re.sub(r"[\x00-\x1f\x7f]", " ", value or "")).strip()
    if not text:
        raise TradeChecklistError("NAME_REQUIRED", "write the name of the position", "name")
    if len(text) > MAX_NAME:
        raise TradeChecklistError("NAME_TOO_LONG", f"at most {MAX_NAME} characters", "name")
    return text


def clean_owner_note(value: str | None) -> str | None:
    """The owner's word to the craftsman: line breaks kept (at most two in a row), at most 1000 characters; blank = none."""
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", " ", (value or "").replace("\r\n", "\n")).strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    if not text:
        return None
    if len(text) > MAX_COMMENT:
        raise TradeChecklistError("COMMENT_TOO_LONG", f"at most {MAX_COMMENT} characters", "note")
    return text


@dataclass(frozen=True, slots=True)
class TypicalAnswer:
    key: str
    unit: str
    quantity: Decimal | None
    note: str | None


@dataclass(frozen=True, slots=True)
class OwnAnswer:
    name: str
    unit: str
    quantity: Decimal
    note: str | None


def clean_room_answers(
    trade: str, typical: list[dict[str, Any]] | None, own: list[dict[str, Any]] | None
) -> tuple[list[TypicalAnswer], list[OwnAnswer]]:
    """What a craftsman wrote for one room, cleaned. Typical: only the keys of his checklist, each once; a row with neither a quantity nor a note is not an answer and is dropped.
    Own: a name, a quantity (required), a unit; at most 30 per room. Raises `TradeChecklistError` for the first wrong entry."""
    known = {p.key: p for p in positions_of(trade)}
    clean_typical: list[TypicalAnswer] = []
    seen: set[str] = set()
    for row in typical or []:
        key = str(row.get("key", ""))
        if key not in known:
            raise TradeChecklistError("UNKNOWN_POSITION", f"{key!r} is not on this checklist", "key")
        if key in seen:
            raise TradeChecklistError("DUPLICATE_POSITION", f"{key} is given twice", "key")
        seen.add(key)
        unit = known[key].unit
        quantity = clean_quantity(unit, row.get("quantity"))
        note = clean_note(row.get("note"))
        if quantity is None and note is None:
            continue
        clean_typical.append(TypicalAnswer(key, unit, quantity, note))
    rows = own or []
    if len(rows) > MAX_OWN_PER_ROOM:
        raise TradeChecklistError("TOO_MANY_OWN", f"at most {MAX_OWN_PER_ROOM} own positions per room", "own")
    clean_own: list[OwnAnswer] = []
    for row in rows:
        unit = row.get("unit")
        if unit not in UNITS:
            raise TradeChecklistError("UNIT_INVALID", "pieces or metres", "unit")
        quantity = clean_quantity(str(unit), row.get("quantity"))
        if quantity is None:
            raise TradeChecklistError("QUANTITY_REQUIRED", "write the quantity", "quantity")
        clean_own.append(OwnAnswer(clean_own_name(row.get("name")), str(unit), quantity, clean_note(row.get("note"))))
    return clean_typical, clean_own


def answers_hash(rows: list[tuple[str, str, str, str, str]]) -> str:
    """What the craftsman sent: (room, key or name, unit, quantity, note) of every answer, in a fixed order. Any change changes the hash."""
    text = json.dumps(sorted(rows), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
