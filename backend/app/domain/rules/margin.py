"""The margin of an object (V2-9): what was agreed, less what was spent, less the owner's own work. Pure function, no database.

The base is the agreed amount, else the total of the estimate that was offered as its hint; the amounts are taken **as recorded** (no VAT is taken out or put in).
The work is the hours of the owner's log times the hourly rate of the profile; without a rate the work is not priced and the margin is the one **before** labour,
with the money for an hour of work shown instead.
"""
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
TENTH = Decimal("0.1")
ZERO = Decimal("0.00")
AGREED, ESTIMATE = "AGREED", "ESTIMATE"


@dataclass(frozen=True, slots=True)
class Margin:
    basis: Decimal | None
    basis_source: str | None  # AGREED | ESTIMATE | None (nothing to count from)
    expenses: Decimal
    hours: Decimal
    hourly_rate: Decimal | None
    labor_cost: Decimal | None  # hours x rate; None without a rate
    labor_included: bool  # whether `margin` is after the work (a rate is set) or before it
    margin: Decimal | None  # None without a basis
    percent: Decimal | None  # of the basis, one place
    per_hour: Decimal | None  # (basis - expenses) / hours: what an hour of the work brought, before labour; None without hours or a basis


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def compute(agreed: Decimal | None, estimate_total: Decimal | None, expenses: Decimal, hours: Decimal, hourly_rate: Decimal | None) -> Margin:
    if agreed is not None:
        basis, source = agreed, AGREED
    elif estimate_total is not None:
        basis, source = estimate_total, ESTIMATE
    else:
        basis, source = None, None
    labor = None if hourly_rate is None else _money(hours * hourly_rate)
    if basis is None:
        return Margin(None, None, expenses, hours, hourly_rate, labor, labor is not None, None, None, None)
    before_labor = basis - expenses
    margin = _money(before_labor - (labor or ZERO))
    return Margin(
        basis=basis,
        basis_source=source,
        expenses=expenses,
        hours=hours,
        hourly_rate=hourly_rate,
        labor_cost=labor,
        labor_included=labor is not None,
        margin=margin,
        percent=(margin * Decimal(100) / basis).quantize(TENTH, rounding=ROUND_HALF_UP) if basis > 0 else None,
        per_hour=_money(before_labor / hours) if hours > 0 else None,
    )
