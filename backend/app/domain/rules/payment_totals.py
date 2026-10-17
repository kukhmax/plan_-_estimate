"""The totals and the state of the invoices of an object (invoices and advances, IA-1) -- pure functions, no database, no framework.

What the contractor sees in the summary is made here and only here (the interface formats, it never adds): what was invoiced, what was taken
from the client, what was spent, what is left to receive of the agreed amount, and for every invoice how much of it the payments tied to it
have settled. Archived records count for nothing. Money is `Decimal`; nothing is rounded (the amounts are already two places).
"""
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

INVOICE = "INVOICE"
MONEY_IN = ("ADVANCE", "PAYMENT")
EXPENSE = "EXPENSE"

ZERO = Decimal("0.00")  # every sum starts from two places, so an empty total is "0.00" and not "0"

PAID = "PAID"
PARTIAL = "PARTIAL"
OVERDUE = "OVERDUE"
OPEN = "OPEN"


@dataclass(frozen=True, slots=True)
class Entry:
    id: object
    kind: str
    amount_gross: Decimal
    due_on: date | None
    settles_id: object | None
    is_archived: bool


@dataclass(frozen=True, slots=True)
class InvoiceStanding:
    settled: Decimal  # taken from the client by the payments tied to this invoice
    remaining: Decimal  # what is still to be paid (never below zero)
    state: str  # PAID | PARTIAL | OVERDUE | OPEN


@dataclass(frozen=True, slots=True)
class Summary:
    invoiced: Decimal
    received: Decimal
    expenses: Decimal
    invoiced_unpaid: Decimal  # the unpaid rest of the invoices that payments are tied to (payments tied to nothing settle nothing)
    to_receive: Decimal | None  # the agreed amount less what was received; None without an agreed amount
    result: Decimal  # received less expenses: a cash result, not a profit in the accounting sense


def invoice_standings(entries: Iterable[Entry], today: date) -> dict[object, InvoiceStanding]:
    """The state of every invoice, archived ones included (their payments still count against them, archived payments do not)."""
    entries = list(entries)
    settled: dict[object, Decimal] = {}
    for entry in entries:
        if entry.kind in MONEY_IN and not entry.is_archived and entry.settles_id is not None:
            settled[entry.settles_id] = settled.get(entry.settles_id, ZERO) + entry.amount_gross
    standings: dict[object, InvoiceStanding] = {}
    for entry in entries:
        if entry.kind != INVOICE:
            continue
        done = settled.get(entry.id, ZERO)
        remaining = max(entry.amount_gross - done, ZERO)
        if done >= entry.amount_gross:
            state = PAID
        elif entry.due_on is not None and today > entry.due_on:
            state = OVERDUE
        elif done > 0:
            state = PARTIAL
        else:
            state = OPEN
        standings[entry.id] = InvoiceStanding(settled=done, remaining=remaining, state=state)
    return standings


def summarize(entries: Iterable[Entry], agreed: Decimal | None, today: date) -> Summary:
    entries = list(entries)
    live = [entry for entry in entries if not entry.is_archived]
    zero = ZERO
    invoiced = sum((e.amount_gross for e in live if e.kind == INVOICE), zero)
    received = sum((e.amount_gross for e in live if e.kind in MONEY_IN), zero)
    expenses = sum((e.amount_gross for e in live if e.kind == EXPENSE), zero)
    standings = invoice_standings(entries, today)
    unpaid = sum((standings[e.id].remaining for e in live if e.kind == INVOICE), zero)
    return Summary(
        invoiced=invoiced,
        received=received,
        expenses=expenses,
        invoiced_unpaid=unpaid,
        to_receive=None if agreed is None else agreed - received,
        result=received - expenses,
    )
