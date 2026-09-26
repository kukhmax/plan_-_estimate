"""Read-only grouping of openings by type and exact dimensions (Stage 13F-PRE).

Used by the room calculation read model and the project (object) summary to
show which doors / windows / other openings stand behind the aggregate
deduction and reveal figures. Pure presentation grouping: no geometry is
recomputed here.

Grouping key: (opening type, exact width, exact height). Dimensions are
Decimals quantized to the column scale (Numeric(10, 3)), so 0.9 and 0.900 are
one group and binary-float equality is never used. Quantities are summed per
group (Opening.quantity respected). DOOR / WINDOW / OTHER never merge.
Callers pass only openings that are active, on active surfaces of active
rooms.
"""
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal

from app.models.opening import OpeningType

DIMENSION_PRECISION = Decimal("0.001")

_TYPE_ORDER = {OpeningType.DOOR: 0, OpeningType.WINDOW: 1, OpeningType.OTHER: 2}


@dataclass(frozen=True)
class OpeningGroup:
    opening_type: OpeningType
    width: Decimal
    height: Decimal
    quantity: int


def group_openings(
    rows: Iterable[tuple[OpeningType | str, Decimal | str, Decimal | str, int]],
) -> list[OpeningGroup]:
    """Aggregate (type, width, height, quantity) rows into ordered groups:
    DOOR -> WINDOW -> OTHER, then width and height ascending."""
    totals: dict[tuple[OpeningType, Decimal, Decimal], int] = {}
    for opening_type, width, height, quantity in rows:
        key = (
            OpeningType(opening_type),
            Decimal(str(width)).quantize(DIMENSION_PRECISION),
            Decimal(str(height)).quantize(DIMENSION_PRECISION),
        )
        totals[key] = totals.get(key, 0) + int(quantity)
    return [
        OpeningGroup(opening_type=t, width=w, height=h, quantity=q)
        for (t, w, h), q in sorted(
            totals.items(), key=lambda item: (_TYPE_ORDER[item[0][0]], item[0][1], item[0][2])
        )
    ]
