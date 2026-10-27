"""Carrying the answers of a craftsman over into the rooms (V2-14a; docs/V2_14A_PLAN_RU.md): which typical position becomes which row of "Punkty i trasy" and which number of a
calculation of materials. Pure rules, no database: the service reads the rows and writes what these functions decide.

The rows made here carry `source = TRADE_LINK`. A second carrying over updates exactly those rows (and removes the ones the craftsman no longer asks for); a row the owner typed is never
touched, even when it names the same item of the Price Book.
"""
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.domain.rules.trade_checklist import TradeChecklistError
from app.domain.rules.trades import ELECTRIC, PLUMBING

SOURCE = "TRADE_LINK"
NOTE_LIMIT = 500  # the limit of the note of a row of "Punkty i trasy"
CENT = Decimal("0.01")

# The item of the Price Book a typical position is looked for by (the typical items of "Punkty i trasy", `domain/data/points_pack.py`): the choice of the owner replaces it.
# "Obwody" and "Wyjścia z rozdzielacza" are not points of the price book: they go to the materials only.
POINT_ITEM_NAME: dict[str, str] = {
    "SOCKET": "Punkt elektryczny - gniazdko / włącznik",
    "SWITCH": "Punkt elektryczny - gniazdko / włącznik",
    "LIGHT_POINT": "Punkt oświetleniowy",
    "CABLE_ROUTE": "Ułożenie przewodu elektrycznego",
    "WATER_POINT": "Punkt wodny",
    "DRAIN_POINT": "Punkt kanalizacyjny",
    "PIPE_ROUTE": "Trasa rurowa",
}

# The number of the calculation of materials (`schemas/material.py`) each typical position fills.
MATERIAL_PARAM: dict[str, dict[str, str]] = {
    ELECTRIC: {"SOCKET": "sockets", "SWITCH": "switches", "LIGHT_POINT": "lights", "CIRCUIT": "circuits", "CABLE_ROUTE": "route_m"},
    PLUMBING: {"WATER_POINT": "water_points", "DRAIN_POINT": "drain_points", "MANIFOLD_OUT": "manifold_outlets", "PIPE_ROUTE": "pipe_m"},
}

NEW, CHANGE, SAME, REMOVE = "NEW", "CHANGE", "SAME", "REMOVE"


def package_of(trade: str) -> str:
    if trade not in MATERIAL_PARAM:
        raise TradeChecklistError("UNKNOWN_TRADE", "the link is for the electrician or the plumber", "trade")
    return trade  # the package of materials has the name of the trade


def default_item_name(key: str) -> str | None:
    return POINT_ITEM_NAME.get(key)


@dataclass(frozen=True, slots=True)
class Answer:
    quantity: Decimal | None
    note: str | None


@dataclass(frozen=True, slots=True)
class Wanted:
    item_id: uuid.UUID
    quantity: Decimal
    note: str | None


@dataclass(frozen=True, slots=True)
class ExistingRow:
    id: uuid.UUID
    item_id: uuid.UUID
    quantity: Decimal
    note: str | None


@dataclass(frozen=True, slots=True)
class RowAction:
    kind: str  # NEW | CHANGE | SAME | REMOVE
    item_id: uuid.UUID
    quantity: Decimal  # what the row will say (REMOVE: what it said)
    note: str | None
    row_id: uuid.UUID | None = None  # CHANGE / SAME / REMOVE: the row of an earlier carrying over
    was_quantity: Decimal | None = None  # CHANGE: what the row said before
    keys: tuple[str, ...] = ()


def _q(value: Decimal) -> Decimal:
    return Decimal(value).quantize(CENT)


def wanted_rows(typical: dict[str, Answer], mapping: dict[str, uuid.UUID | None], order: tuple[str, ...]) -> list[Wanted]:
    """The rows one room should have: the answers with a quantity above zero, the positions of one price item added together (`order` keeps the walk through a room)."""
    sums: dict[uuid.UUID, Decimal] = {}
    notes: dict[uuid.UUID, list[str]] = {}
    for key in order:
        answer = typical.get(key)
        item_id = mapping.get(key)
        if answer is None or item_id is None or answer.quantity is None or answer.quantity <= 0:
            continue
        sums[item_id] = sums.get(item_id, Decimal(0)) + answer.quantity
        if answer.note and answer.note not in notes.setdefault(item_id, []):
            notes[item_id].append(answer.note)
    return [Wanted(item_id, _q(total), " · ".join(notes.get(item_id, []))[:NOTE_LIMIT] or None) for item_id, total in sums.items()]


def plan_rows(wanted: list[Wanted], existing: list[ExistingRow], scope: set[uuid.UUID]) -> list[RowAction]:
    """What carrying over does to the rows of one room. `existing`: the rows an earlier carrying over made; `scope`: the items this trade's choice names (a row of another item, which
    belongs to the other craftsman, is left alone)."""
    actions: list[RowAction] = []
    taken: set[uuid.UUID] = set()
    for want in wanted:
        match = next((row for row in existing if row.item_id == want.item_id and row.id not in taken), None)
        if match is None:
            actions.append(RowAction(NEW, want.item_id, want.quantity, want.note))
            continue
        taken.add(match.id)
        same = _q(match.quantity) == want.quantity and (match.note or None) == want.note
        actions.append(RowAction(SAME if same else CHANGE, want.item_id, want.quantity, want.note, match.id, None if same else _q(match.quantity)))
    for row in existing:
        if row.id not in taken and row.item_id in scope:
            actions.append(RowAction(REMOVE, row.item_id, _q(row.quantity), row.note, row.id))
    return actions


def material_numbers(trade: str, typical: dict[str, Answer]) -> dict[str, Any] | None:
    """The numbers of the calculation of materials a room's answers give (only those above zero); None when there is nothing to count. Pieces are whole numbers, the route is metres."""
    out: dict[str, Any] = {}
    for key, param in MATERIAL_PARAM[package_of(trade)].items():
        answer = typical.get(key)
        if answer is None or answer.quantity is None or answer.quantity <= 0:
            continue
        out[param] = _q(answer.quantity) if param in ("route_m", "pipe_m") else int(answer.quantity)
    return out or None


def same_numbers(stored: dict[str, Any], wanted: dict[str, Any]) -> bool:
    def norm(values: dict[str, Any]) -> dict[str, Decimal]:
        return {k: Decimal(str(v)) for k, v in values.items() if v is not None and Decimal(str(v)) != 0}

    return norm(stored) == norm(wanted)
