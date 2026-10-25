"""The payment schedule of an object (V2-9): what each stage is worth, what was received for it, where it stands. Pure functions, no database.

A stage names its share of the agreed amount in percent **or** a fixed amount. Money received for a stage is an advance or a payment ("Od klienta") that
names the stage; archived records never count. Every amount is `Decimal` rounded half up to two places; nothing is rounded twice.
"""
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

ZERO = Decimal("0.00")
CENT = Decimal("0.01")
PAID, PARTIAL, OVERDUE, OPEN = "PAID", "PARTIAL", "OVERDUE", "OPEN"


@dataclass(frozen=True, slots=True)
class StageEntry:
    id: object
    position: int
    percent: Decimal | None
    amount: Decimal | None
    due_on: date | None


@dataclass(frozen=True, slots=True)
class Received:
    """One advance or payment that names a stage; `archived` ones are left out by the caller or ignored here."""

    stage_id: object
    amount_gross: Decimal
    is_archived: bool = False


@dataclass(frozen=True, slots=True)
class StageStanding:
    amount: Decimal | None  # None: a share of an agreed amount that is not set yet
    received: Decimal
    remaining: Decimal | None  # never below zero; None together with `amount`
    state: str  # PAID | PARTIAL | OVERDUE | OPEN


@dataclass(frozen=True, slots=True)
class ScheduleSummary:
    agreed: Decimal | None
    stages_total: Decimal  # the stages whose amount is known
    unpriced: int  # the stages that wait for an agreed amount
    difference: Decimal | None  # agreed less stages_total: positive = not yet scheduled, negative = scheduled above the agreed amount; None without an agreed amount
    received: Decimal  # received for the stages (all of it, even above the amount of a stage)
    to_receive: Decimal | None  # the sum of what is still due at the stages; None while some stage has no amount


def stage_amount(percent: Decimal | None, amount: Decimal | None, agreed: Decimal | None) -> Decimal | None:
    """The fixed amount, else the share of the agreed amount; None while a share has no agreed amount to follow."""
    if amount is not None:
        return amount.quantize(CENT, rounding=ROUND_HALF_UP)
    if percent is None or agreed is None:
        return None
    return (agreed * percent / Decimal(100)).quantize(CENT, rounding=ROUND_HALF_UP)


def ordered(stages: Iterable[StageEntry]) -> list[StageEntry]:
    """By the due day (no day: last), then in the order of entry."""
    return sorted(stages, key=lambda s: (s.due_on is None, s.due_on or date.max, s.position, str(s.id)))


def standings(stages: Iterable[StageEntry], money: Iterable[Received], agreed: Decimal | None, today: date) -> dict[object, StageStanding]:
    got: dict[object, Decimal] = {}
    for item in money:
        if not item.is_archived and item.stage_id is not None:
            got[item.stage_id] = got.get(item.stage_id, ZERO) + item.amount_gross
    result: dict[object, StageStanding] = {}
    for stage in stages:
        amount = stage_amount(stage.percent, stage.amount, agreed)
        received = got.get(stage.id, ZERO)
        remaining = None if amount is None else max(amount - received, ZERO)
        if amount is not None and received >= amount:
            state = PAID
        elif stage.due_on is not None and today > stage.due_on:
            state = OVERDUE
        elif received > 0:
            state = PARTIAL
        else:
            state = OPEN
        result[stage.id] = StageStanding(amount=amount, received=received, remaining=remaining, state=state)
    return result


def summarize(stages: Iterable[StageEntry], found: dict[object, StageStanding], agreed: Decimal | None) -> ScheduleSummary:
    stages = list(stages)
    known = [found[s.id].amount for s in stages if found[s.id].amount is not None]
    total = sum(known, ZERO)
    unpriced = len(stages) - len(known)
    remaining = [found[s.id].remaining for s in stages if found[s.id].remaining is not None]
    return ScheduleSummary(
        agreed=agreed,
        stages_total=total,
        unpriced=unpriced,
        difference=None if agreed is None else agreed - total,
        received=sum((found[s.id].received for s in stages), ZERO),
        to_receive=None if unpriced else sum(remaining, ZERO),
    )
