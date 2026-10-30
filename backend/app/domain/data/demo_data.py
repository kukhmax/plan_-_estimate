"""Demo data of an account (V2-2; docs/V2_2_PLAN_RU.md): one object "DEMO · Mieszkanie 50 m²" with five rooms and demo prices.

Prices: the MINIMUM of the approved market window when the row has one, otherwise an invented round value (`INVENTED_PRICES`).
The values are demo values only: the command that applies them never overwrites a price the owner has set.
"""
from dataclasses import dataclass
from decimal import Decimal

from app.domain.data.price_book_seed import (
    build_approved_market_references,
    build_approved_price_book_items,
)

DEMO_CLIENT_MARK = "[DEMO]"
DEMO_PROJECT_PREFIX = "DEMO · "
DEMO_PROJECT_NAME = "DEMO · Mieszkanie 50 m²"


@dataclass(frozen=True)
class DemoRoom:
    name: str
    length: Decimal
    width: Decimal
    height: Decimal = Decimal("2.600")


# 18.72 + 13.60 + 8.96 + 4.80 + 4.80 = 50.88 m² of floor
DEMO_ROOMS: tuple[DemoRoom, ...] = (
    DemoRoom("Salon", Decimal("5.200"), Decimal("3.600")),
    DemoRoom("Sypialnia", Decimal("4.000"), Decimal("3.400")),
    DemoRoom("Kuchnia", Decimal("3.200"), Decimal("2.800")),
    DemoRoom("Łazienka", Decimal("2.400"), Decimal("2.000")),
    DemoRoom("Przedpokój", Decimal("3.000"), Decimal("1.600")),
)

# the rows without market data (the "own price" rows): invented, round, PLN per the unit of the row
INVENTED_PRICES: dict[str, str] = {
    "CENNIK_PREP_PROT-01": "3",
    "CENNIK_PREP_FLEECE-01": "15",
    "CENNIK_PREP_DEGR-01": "4",
    "CENNIK_PREP_CLEAN-01": "3",
    "CENNIK_PRIM_ADH-01": "9",
    "CENNIK_PRIM_HIGH-01": "12",
    "CENNIK_SKIM_LOCAL-01": "25",
    "CENNIK_GK_SCREW-01": "6",
    "CENNIK_GF_FLIZ_L-01": "12",
    "CENNIK_GF_FLIZ_M-01": "22",
    "CENNIK_PAINT_MASK-01": "5",
    "CENNIK_PAINT_MULTI-01": "30",
    "CENNIK_MC_WALL_L-01": "150",
    "CENNIK_MC_FLOOR_L-01": "170",
    "CENNIK_MC_STAIRS-01": "450",
    "CENNIK_DEC_VEN_MAR-01": "180",
    "CENNIK_SKIM_ADD-01": "10",
    "CENNIK_GK_JOINT_Q1-01": "8",
    "CENNIK_GK_JOINT_Q2-01": "12",
    "CENNIK_PREP_CONC-01": "12",
    "CENNIK_SKIM_LEVEL-01": "20",
    # the floor works (2026-10-30): invented round demo values, like the rows above
    "CENNIK_FLOOR_CM-01": "50",
    "CENNIK_FLOOR_PRIM-01": "5",
    "CENNIK_FLOOR_PRIM_EPOXY-01": "35",
    "CENNIK_FLOOR_CONTACT-01": "8",
    "CENNIK_FLOOR_LEVEL-01": "25",
    "CENNIK_FLOOR_GRIND-01": "15",
    "CENNIK_FLOOR_CRACK-01": "30",
    "CENNIK_FLOOR_HOLLOW-01": "60",
    "CENNIK_FLOOR_JOINT-01": "15",
    "CENNIK_FLOOR_WATERPROOF-01": "30",
    "CENNIK_FLOOR_TILE_REMOVE-01": "25",
    "CENNIK_FLOOR_BOARD_FIX-01": "15",
    "CENNIK_FLOOR_OSB-01": "45",
    "CENNIK_FLOOR_VAPOUR-01": "3",
}


def demo_prices() -> dict[str, Decimal]:
    """Code -> demo price (2 places) for every approved row: the minimum of its market window, else the invented value."""
    references = build_approved_market_references()
    prices: dict[str, Decimal] = {}
    for seed in build_approved_price_book_items():
        reference = references.get(seed.code)
        raw = reference.market_min if reference is not None else INVENTED_PRICES[seed.code]
        prices[seed.code] = Decimal(raw).quantize(Decimal("0.01"))
    return prices
