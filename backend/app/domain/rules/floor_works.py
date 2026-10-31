"""Works measured by the floor of the room wherever they are planned (owner 2026-10-31: "Zabezpieczenie podłóg" lives in the plan of the floor,
once per room, with the area of the floor -- not on every wall)."""
from app.models.price_item import PriceUnit

FLOOR_MEASURED_CODES = frozenset({"CENNIK_PREP_PROT-01"})


def is_floor_measured(code: str, unit: PriceUnit | str) -> bool:
    value = unit.value if isinstance(unit, PriceUnit) else unit
    return code in FLOOR_MEASURED_CODES and value == PriceUnit.M2.value
