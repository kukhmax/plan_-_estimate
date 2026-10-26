"""The packages of professions ("trades") of an owner (V2-13; docs/V2_13_PLAN_RU.md).

An owner who does only tile does not want the price categories of the electrician in the price book, the works of the plumber in the plan of a wall or the package of the
drywall in the materials of a room. Each trade names what belongs to it: the categories of the price book (and so the works that come from them, the points and routes of a
room) and the packages of the materials of a room. What belongs to no trade (the universal points and routes, materials, other) is always there.

Nothing is DELETED or blocked by a trade being off: it only hides what is offered for a new choice; the rows that already exist (an estimate's line, a calculation, a point) stay
visible. NULL in the database = "never chosen" = every trade on, so nothing disappears for anybody after the release and a new owner starts with everything.
"""
from collections.abc import Iterable
from dataclasses import dataclass

FINISHING = "FINISHING"
DRYWALL = "DRYWALL"
MICROCEMENT = "MICROCEMENT"
TILE = "TILE"
ELECTRIC = "ELECTRIC"
PLUMBING = "PLUMBING"


@dataclass(frozen=True, slots=True)
class Trade:
    key: str
    price_categories: tuple[str, ...]
    material_packages: tuple[str, ...] = ()


# In the order the owner reads them (microcement stands before the tile, V2-13 decision of 2026-11-02).
TRADES: tuple[Trade, ...] = (
    Trade(FINISHING, ("PREPARATION", "SKIM_COAT", "PLASTER", "PAINTING", "GLASS_FIBER", "DECORATIVE", "REVEAL")),
    Trade(DRYWALL, ("DRYWALL",), ("DRYWALL",)),
    Trade(MICROCEMENT, ("MICROCEMENT",)),
    Trade(TILE, ("TILE",), ("TILE",)),
    Trade(ELECTRIC, ("ELECTRICAL",), ("ELECTRIC",)),
    Trade(PLUMBING, ("PLUMBING",), ("PLUMBING",)),
)
TRADE_KEYS: tuple[str, ...] = tuple(t.key for t in TRADES)
# The categories that belong to no trade: always offered.
ALWAYS_CATEGORIES: tuple[str, ...] = ("POINTS_ROUTES", "MATERIAL", "OTHER")


class TradesError(ValueError):
    """The chosen trades are not a list of known trades. `reason` is a stable code, `key` the offending entry (when there is one)."""

    def __init__(self, reason: str, key: str | None = None) -> None:
        super().__init__(f"trades: {reason}" + (f" ({key!r})" if key is not None else ""))
        self.reason = reason
        self.key = key


def validate_enabled(keys: Iterable[object]) -> tuple[str, ...]:
    """The canonical choice: known trades only, each once, in the order of `TRADES`. An empty choice is allowed (only the universal things are offered)."""
    seen: set[str] = set()
    for key in keys:
        if not isinstance(key, str):
            raise TradesError("WRONG_TYPE")
        if key not in TRADE_KEYS:
            raise TradesError("UNKNOWN_TRADE", key)
        seen.add(key)
    return tuple(k for k in TRADE_KEYS if k in seen)


def enabled_of(stored: object) -> tuple[str, ...]:
    """What an owner has on: the stored choice, or every trade while none was ever made (NULL). A stored value that is not a list of known trades (a trade removed in a later
    release) counts only for the ones still known."""
    if stored is None:
        return TRADE_KEYS
    if not isinstance(stored, list):
        return TRADE_KEYS
    return tuple(k for k in TRADE_KEYS if k in stored)
