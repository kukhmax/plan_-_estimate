"""V2-9 -- the payment schedule and the margin: the pure rules (no database)."""
import uuid
from datetime import date, timedelta
from decimal import Decimal

from app.domain.rules import margin as margin_rules
from app.domain.rules import payment_schedule as sched

TODAY = date(2026, 10, 28)
D = Decimal


def stage(*, percent=None, amount=None, due=None, position=0):
    return sched.StageEntry(id=uuid.uuid4(), position=position, percent=D(percent) if percent else None, amount=D(amount) if amount else None, due_on=due)


def got(stage_entry, amount, archived=False):
    return sched.Received(stage_id=stage_entry.id, amount_gross=D(amount), is_archived=archived)


# --- the amount of a stage --------------------------------------------------------------------------------------------------------


def test_a_share_follows_the_agreed_amount_rounded_half_up_and_a_fixed_amount_is_itself():
    assert sched.stage_amount(D("30"), None, D("40000")) == D("12000.00")
    assert sched.stage_amount(D("33.33"), None, D("100.05")) == D("33.35")  # 33.3466.. -> 33.35
    assert sched.stage_amount(D("12.5"), None, D("0.10")) == D("0.01")  # 0.0125 half up -> 0.01
    assert sched.stage_amount(None, D("1500"), D("40000")) == D("1500.00") and sched.stage_amount(None, D("1500"), None) == D("1500.00")


def test_a_share_without_an_agreed_amount_has_no_amount():
    assert sched.stage_amount(D("30"), None, None) is None


# --- the state --------------------------------------------------------------------------------------------------------------------


AGREED = D("1000")


def state_of(entry, money, agreed=AGREED, today=TODAY):
    return sched.standings([entry], money, agreed, today)[entry.id]


def test_open_partial_paid_and_overdue():
    s = stage(percent="50", due=TODAY + timedelta(days=3))
    assert state_of(s, []).state == sched.OPEN and state_of(s, []).remaining == D("500.00")
    part = state_of(s, [got(s, "200")])
    assert (part.state, part.received, part.remaining) == (sched.PARTIAL, D("200"), D("300.00"))
    assert state_of(s, [got(s, "200"), got(s, "300")]).state == sched.PAID
    late = stage(amount="500", due=TODAY - timedelta(days=1))
    assert state_of(late, []).state == sched.OVERDUE and state_of(late, [got(late, "100")]).state == sched.OVERDUE  # partly paid but late
    assert state_of(late, [got(late, "500")]).state == sched.PAID  # paid wins over late


def test_more_than_the_stage_is_paid_and_never_a_negative_rest():
    s = stage(amount="500")
    standing = state_of(s, [got(s, "700")])
    assert (standing.state, standing.received, standing.remaining) == (sched.PAID, D("700"), D("0.00"))


def test_archived_money_and_money_of_another_stage_do_not_count():
    a, b = stage(amount="500"), stage(amount="500")
    found = sched.standings([a, b], [got(a, "100"), got(a, "400", archived=True), got(b, "50")], D("1000"), TODAY)
    assert found[a.id].received == D("100") and found[b.id].received == D("50")


def test_a_share_without_an_agreed_amount_is_open_or_late_and_never_paid():
    s = stage(percent="30", due=TODAY - timedelta(days=2))
    standing = state_of(s, [got(s, "9999")], agreed=None)
    assert (standing.amount, standing.remaining, standing.state) == (None, None, sched.OVERDUE)
    open_one = stage(percent="30")
    assert state_of(open_one, [], agreed=None).state == sched.OPEN
    assert state_of(open_one, [got(open_one, "10")], agreed=None).state == sched.PARTIAL  # something came, the amount is still unknown


# --- the order and the check against the agreed amount -------------------------------------------------------------------------------


def test_the_order_is_the_due_day_then_the_order_of_entry_and_no_day_is_last():
    late, early, none_a, none_b = stage(amount="1", due=date(2026, 12, 1), position=0), stage(amount="1", due=date(2026, 11, 1), position=1), stage(amount="1", position=2), stage(amount="1", position=3)
    assert [s.id for s in sched.ordered([none_b, late, none_a, early])] == [early.id, late.id, none_a.id, none_b.id]


def test_the_summary_checks_the_stages_against_the_agreed_amount():
    a, b = stage(percent="30"), stage(amount="20000")
    found = sched.standings([a, b], [got(a, "5000")], D("40000"), TODAY)
    summary = sched.summarize([a, b], found, D("40000"))
    assert (summary.stages_total, summary.difference, summary.unpriced) == (D("32000.00"), D("8000.00"), 0)  # 8000 not yet scheduled
    assert (summary.received, summary.to_receive) == (D("5000"), D("27000.00"))
    over = sched.summarize([b], sched.standings([b], [], D("15000"), TODAY), D("15000"))
    assert over.difference == D("-5000.00")


def test_without_an_agreed_amount_shares_are_unpriced_and_the_rest_is_unknown():
    a, b = stage(percent="30"), stage(amount="1000")
    summary = sched.summarize([a, b], sched.standings([a, b], [], None, TODAY), None)
    assert (summary.stages_total, summary.unpriced, summary.difference, summary.to_receive) == (D("1000.00"), 1, None, None)


def test_an_empty_schedule_is_all_zero():
    summary = sched.summarize([], {}, D("100"))
    assert (summary.stages_total, summary.received, summary.to_receive, summary.difference) == (D("0"), D("0"), D("0"), D("100"))


# --- the margin -------------------------------------------------------------------------------------------------------------------------------


def test_the_margin_is_the_agreed_amount_less_expenses_less_the_work():
    m = margin_rules.compute(D("40000"), D("38000"), D("12000.50"), D("120"), D("100"))
    assert (m.basis, m.basis_source, m.labor_cost, m.labor_included) == (D("40000"), "AGREED", D("12000.00"), True)
    assert m.margin == D("15999.50") and m.percent == D("40.0") and m.per_hour == D("233.33")


def test_the_estimate_is_the_basis_only_without_an_agreed_amount():
    m = margin_rules.compute(None, D("38000"), D("8000"), D("0"), None)
    assert (m.basis, m.basis_source, m.margin) == (D("38000"), "ESTIMATE", D("30000.00"))


def test_without_a_rate_the_margin_is_before_labour_and_the_hour_is_shown_instead():
    m = margin_rules.compute(D("10000"), None, D("2000"), D("40"), None)
    assert (m.labor_cost, m.labor_included, m.margin, m.per_hour, m.percent) == (None, False, D("8000.00"), D("200.00"), D("80.0"))


def test_no_hours_no_per_hour_and_a_rate_with_no_hours_costs_nothing():
    m = margin_rules.compute(D("1000"), None, D("100"), D("0"), D("90"))
    assert (m.per_hour, m.labor_cost, m.labor_included, m.margin) == (None, D("0.00"), True, D("900.00"))


def test_without_any_basis_there_is_no_margin():
    m = margin_rules.compute(None, None, D("500"), D("10"), D("100"))
    assert (m.basis, m.basis_source, m.margin, m.percent, m.per_hour) == (None, None, None, None, None) and m.labor_cost == D("1000.00")


def test_a_loss_is_a_negative_margin_not_hidden():
    m = margin_rules.compute(D("1000"), None, D("900"), D("10"), D("50"))
    assert m.margin == D("-400.00") and m.percent == D("-40.0")
