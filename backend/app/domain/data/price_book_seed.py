"""Technical seed definitions for the editable Price Book (Stage 9B).

These rows are deliberately NOT market data. Their only purpose is to prove
lazy per-owner seed materialization: obvious placeholder prices (1.11 / 2.22 /
3.33 / 4.44) make them impossible to mistake for researched Kraków market
prices. The sourced Kraków catalog is an execution sub-stage 9E concern and is
explicitly not added here.
"""
from dataclasses import dataclass

from app.models.price_item import PriceCategory, PriceScope, PriceUnit


@dataclass(frozen=True)
class PriceItemSeed:
    code: str
    category: PriceCategory
    unit: PriceUnit
    price: str
    price_scope: PriceScope = PriceScope.LABOR
    name_key: str | None = None


def _seed(
    code: str,
    category: PriceCategory,
    unit: PriceUnit,
    price: str,
    name_key: str,
) -> PriceItemSeed:
    return PriceItemSeed(
        code=code,
        category=category,
        unit=unit,
        price=price,
        name_key=name_key,
    )


def build_technical_baseline_price_items() -> list[PriceItemSeed]:
    """Return the small Stage 9B technical seed set.

    Placeholder, non-market prices so the seed set can never be read as a real
    regional catalog; stable CENNIK_* codes per the 9A contract.
    """
    return [
        _seed(
            "CENNIK_PREP_GENERIC_M2",
            PriceCategory.PREPARATION,
            PriceUnit.M2,
            "1.11",
            "pricebook.seed.prep_generic_m2",
        ),
        _seed(
            "CENNIK_PAINT_GENERIC_M2",
            PriceCategory.PAINTING,
            PriceUnit.M2,
            "2.22",
            "pricebook.seed.paint_generic_m2",
        ),
        _seed(
            "CENNIK_REVEAL_GENERIC_M2",
            PriceCategory.REVEAL,
            PriceUnit.M2,
            "3.33",
            "pricebook.seed.reveal_generic_m2",
        ),
        _seed(
            "CENNIK_REVEAL_GENERIC_LM",
            PriceCategory.REVEAL,
            PriceUnit.LM,
            "4.44",
            "pricebook.seed.reveal_generic_lm",
        ),
    ]