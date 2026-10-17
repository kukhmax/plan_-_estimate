"""Invoices and advances (IA-1) -- the totals and the state of an invoice (pure rule, no database)."""
import uuid
from datetime import date, timedelta
from decimal import Decimal

from app.domain.rules.payment_totals import (
    OPEN,
    OVERDUE,
    PAID,
    PARTIAL,
    Entry,
    invoice_standings,
    summarize,
)

TODAY = date(2026, 10, 17)


def entry(kind, amount, *, due=None, settles=None, archived=False, id=None):
    return Entry(id=id or uuid.uuid4(), kind=kind, amount_gross=Decimal(amount), due_on=due, settles_id=settles, is_archived=archived)


def test_nothing_gives_zero_and_no_amount_left_to_receive():
    s = summarize([], None, TODAY)
    assert (s.invoiced, s.received, s.expenses, s.invoiced_unpaid, s.result) == (0, 0, 0, 0, 0) and s.to_receive is None


def test_the_totals_add_each_kind_and_leave_out_the_archived():
    s = summarize(
        [entry("INVOICE", "1000.50"), entry("INVOICE", "99", archived=True), entry("ADVANCE", "300"), entry("PAYMENT", "200.25"),
         entry("PAYMENT", "50", archived=True), entry("EXPENSE", "120.10"), entry("EXPENSE", "5", archived=True)],
        Decimal("5000"), TODAY,
    )
    assert (s.invoiced, s.received, s.expenses) == (Decimal("1000.50"), Decimal("500.25"), Decimal("120.10"))
    assert s.to_receive == Decimal("4499.75") and s.result == Decimal("380.15")


def test_the_money_is_exact_decimal_not_float():
    s = summarize([entry("PAYMENT", "0.10"), entry("PAYMENT", "0.20")], Decimal("1"), TODAY)
    assert s.received == Decimal("0.30") and s.to_receive == Decimal("0.70")


def test_more_received_than_agreed_is_a_negative_rest_not_hidden():
    assert summarize([entry("PAYMENT", "120")], Decimal("100"), TODAY).to_receive == Decimal("-20")


def test_an_invoice_is_open_partial_paid_or_overdue():
    invoice = entry("INVOICE", "1000", due=TODAY + timedelta(days=3))
    standings = lambda *others: invoice_standings([invoice, *others], TODAY)[invoice.id]
    assert standings().state == OPEN and standings().remaining == 1000
    part = standings(entry("PAYMENT", "400", settles=invoice.id))
    assert (part.state, part.settled, part.remaining) == (PARTIAL, Decimal("400"), Decimal("600"))
    assert standings(entry("PAYMENT", "400", settles=invoice.id), entry("ADVANCE", "600", settles=invoice.id)).state == PAID


def test_overdue_needs_a_passed_due_date_and_an_unpaid_rest_and_paid_wins():
    past = entry("INVOICE", "1000", due=TODAY - timedelta(days=1))
    assert invoice_standings([past], TODAY)[past.id].state == OVERDUE
    assert invoice_standings([past, entry("PAYMENT", "10", settles=past.id)], TODAY)[past.id].state == OVERDUE  # partly paid but late
    assert invoice_standings([past, entry("PAYMENT", "1000", settles=past.id)], TODAY)[past.id].state == PAID
    today_due = entry("INVOICE", "1000", due=TODAY)
    assert invoice_standings([today_due], TODAY)[today_due.id].state == OPEN  # the due day itself is not late
    no_due = entry("INVOICE", "1000")
    assert invoice_standings([no_due], TODAY - timedelta(days=999))[no_due.id].state == OPEN


def test_an_archived_payment_settles_nothing_and_an_overpaid_invoice_has_no_negative_rest():
    invoice = entry("INVOICE", "100")
    gone = entry("PAYMENT", "100", settles=invoice.id, archived=True)
    assert invoice_standings([invoice, gone], TODAY)[invoice.id].state == OPEN
    over = invoice_standings([invoice, entry("PAYMENT", "150", settles=invoice.id)], TODAY)[invoice.id]
    assert (over.state, over.remaining) == (PAID, Decimal("0"))


def test_a_payment_tied_to_no_invoice_counts_as_received_but_settles_nothing():
    invoice = entry("INVOICE", "500")
    s = summarize([invoice, entry("PAYMENT", "500")], None, TODAY)
    assert s.received == 500 and s.invoiced_unpaid == 500


def test_the_unpaid_rest_adds_the_live_invoices_only():
    a, b, gone = entry("INVOICE", "300"), entry("INVOICE", "700"), entry("INVOICE", "900", archived=True)
    s = summarize([a, b, gone, entry("PAYMENT", "100", settles=a.id)], None, TODAY)
    assert s.invoiced_unpaid == Decimal("900")  # 200 + 700, the archived one left out
