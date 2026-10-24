"""VAT of an estimate (V2-6; docs/V2_6_PLAN_RU.md): the mode, the allowed rates and the totals.

The prices of the owner's price book are NET (netto): the lines of an estimate add up to the net total, and the VAT is added on top. Exempt ("zw.")
sells without VAT: the net total is the whole. The VAT is counted once, on the net total, and rounded half up to the grosz (the way the VAT of a document is
counted per rate). Nothing here changes the lines or the net total.
"""
from decimal import ROUND_HALF_UP, Decimal

EXEMPT = "EXEMPT"
RATE = "RATE"
MODES = (EXEMPT, RATE)
RATES = (8, 23)
CENT = Decimal("0.01")


class VatError(ValueError):
    """The mode and the rate do not belong together (a rate without the mode RATE, the mode RATE without an allowed rate, an unknown mode)."""


def validate_vat(mode: str | None, rate: int | None) -> tuple[str | None, int | None]:
    """The canonical pair: (None, None) = not set, (EXEMPT, None), or (RATE, 8 | 23)."""
    if mode is None:
        if rate is not None:
            raise VatError("a rate needs the mode RATE")
        return None, None
    if mode == EXEMPT:
        if rate is not None:
            raise VatError("an exempt sale has no rate")
        return EXEMPT, None
    if mode == RATE:
        if rate not in RATES:
            raise VatError(f"the rate must be one of {RATES}")
        return RATE, rate
    raise VatError(f"unknown VAT mode: {mode}")


def vat_totals(net: Decimal | None, mode: str | None, rate: int | None) -> tuple[Decimal | None, Decimal | None]:
    """(the VAT amount, the gross total). Not set or no net total: (None, None); exempt: (None, net); a rate: (net x rate, net + VAT)."""
    if net is None or mode is None:
        return None, None
    if mode == EXEMPT:
        return None, net
    if mode == RATE and rate is not None:
        vat = (net * rate / Decimal(100)).quantize(CENT, rounding=ROUND_HALF_UP)
        return vat, net + vat
    return None, None
