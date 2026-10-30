"""VAT of an estimate (V2-6; docs/V2_6_PLAN_RU.md): the mode, the allowed rates and the totals.

The prices of the owner's price book are NET (netto) by default: the lines of an estimate add up to the net total, and the VAT is added on top. An estimate
may instead say its prices already INCLUDE the VAT (`vat_included`, only with a rate): then the lines add up to the gross and the VAT is taken out of it. Exempt ("zw.")
sells without VAT: the net total is the whole. The VAT is counted once, on the net total, and rounded half up to the grosz (the way the VAT of a document is
counted per rate). Nothing here changes the lines or the net total.
"""
from decimal import ROUND_HALF_UP, Decimal

EXEMPT = "EXEMPT"
RATE = "RATE"
MODES = (EXEMPT, RATE)
RATES = (8, 23)  # the two standard rates the screens offer first
MAX_RATE = 100  # an own rate (owner 2026-10-30, "свой вариант VAT"): a whole percent from 0 to 100
CENT = Decimal("0.01")


class VatError(ValueError):
    """The mode and the rate do not belong together (a rate without the mode RATE, the mode RATE without a rate from 0 to 100, an unknown mode)."""


def validate_vat(mode: str | None, rate: int | None) -> tuple[str | None, int | None]:
    """The canonical pair: (None, None) = not set, (EXEMPT, None), or (RATE, a whole percent 0..100: 8 and 23 are the usual ones, any other is the owner's own)."""
    if mode is None:
        if rate is not None:
            raise VatError("a rate needs the mode RATE")
        return None, None
    if mode == EXEMPT:
        if rate is not None:
            raise VatError("an exempt sale has no rate")
        return EXEMPT, None
    if mode == RATE:
        if isinstance(rate, bool) or not isinstance(rate, int) or not 0 <= rate <= MAX_RATE:
            raise VatError(f"the rate must be a whole percent from 0 to {MAX_RATE}")
        return RATE, rate
    raise VatError(f"unknown VAT mode: {mode}")


def vat_split(
    lines_total: Decimal | None, mode: str | None, rate: int | None, included: bool = False
) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    """(net, VAT, gross) of the sum of the lines.

    Prices net (the default): the sum IS the net total and the VAT is added on top. Prices that already include the VAT (owner 2026-10-27,
    "вычесть НДС из сметы"; only with a rate): the sum IS the gross total, the net is gross x 100 / (100 + rate) rounded half up to the grosz
    and the VAT is the rest, so net + VAT is exactly the gross. Not set: (sum, None, None); exempt: (sum, None, sum).
    """
    if lines_total is None:
        return None, None, None
    if mode is None:
        return lines_total, None, None
    if mode == EXEMPT:
        return lines_total, None, lines_total
    if mode == RATE and rate is not None:
        if included:
            net = (lines_total * Decimal(100) / Decimal(100 + rate)).quantize(CENT, rounding=ROUND_HALF_UP)
            return net, lines_total - net, lines_total
        vat = (lines_total * rate / Decimal(100)).quantize(CENT, rounding=ROUND_HALF_UP)
        return lines_total, vat, lines_total + vat
    return lines_total, None, None


def vat_totals(net: Decimal | None, mode: str | None, rate: int | None, included: bool = False) -> tuple[Decimal | None, Decimal | None]:
    """(the VAT amount, the gross total) of the sum of the lines -- see `vat_split`. Not set or no total: (None, None); exempt: (None, sum)."""
    if net is None or mode is None:
        return None, None
    _, vat, gross = vat_split(net, mode, rate, included)
    return vat, gross
