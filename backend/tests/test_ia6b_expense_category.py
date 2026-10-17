"""Invoices and advances IA-6b -- the category of an expense: the rule that makes the parts, the routes, what the database refuses."""
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.domain.rules.payment_totals import CATEGORIES, Entry, summarize
from app.models.project_payment import ExpenseCategory, ProjectPayment
from tests.test_clients import auth_header
from tests.test_ia1_payments_api import TODAY, add, body, listing, owner, project_of
from tests.test_stage16e2_contract import load_migration

DAY = date(2026, 10, 18)


def entry(kind, amount, category=None, archived=False):
    return Entry(id=uuid.uuid4(), kind=kind, amount_gross=Decimal(amount), due_on=None, settles_id=None, is_archived=archived, category=category)


def parts(entries):
    return [(p.category, p.total) for p in summarize(entries, None, DAY).expenses_by_category]


# ------------------------------------------------------------------ the rule

def test_the_words_of_the_rule_are_the_words_of_the_model_and_the_schema():
    from app.schemas.payment import Category

    assert CATEGORIES == tuple(c.value for c in ExpenseCategory)
    assert set(Category.__args__) == set(CATEGORIES)  # type: ignore[attr-defined]


def test_no_expense_gives_no_part():
    assert parts([]) == [] and parts([entry("INVOICE", "100"), entry("PAYMENT", "50")]) == []


def test_each_category_that_has_an_expense_gets_its_sum_in_the_fixed_order():
    got = parts([
        entry("EXPENSE", "10.10", "OTHER"), entry("EXPENSE", "5", "TRANSPORT"), entry("EXPENSE", "100", "MATERIALS"),
        entry("EXPENSE", "0.20", "MATERIALS"), entry("EXPENSE", "7", "TOOLS"),
    ])
    assert got == [("MATERIALS", Decimal("100.20")), ("TOOLS", Decimal("7")), ("TRANSPORT", Decimal("5")), ("OTHER", Decimal("10.10"))]


def test_an_expense_without_a_category_is_the_last_part_and_an_unknown_word_is_one_of_those():
    got = parts([entry("EXPENSE", "3"), entry("EXPENSE", "4", "SERVICES"), entry("EXPENSE", "2", "SURPRISE")])
    assert got == [("SERVICES", Decimal("4")), (None, Decimal("5"))]


def test_archived_expenses_and_other_kinds_are_not_in_any_part():
    got = parts([
        entry("EXPENSE", "50", "TOOLS", archived=True), entry("EXPENSE", "20", "TOOLS"),
        entry("INVOICE", "999", "TOOLS"), entry("PAYMENT", "888", "TOOLS"),
    ])
    assert got == [("TOOLS", Decimal("20"))]


def test_a_category_that_has_only_archived_expenses_is_not_listed():
    assert parts([entry("EXPENSE", "50", "TOOLS", archived=True), entry("EXPENSE", "1", "OTHER")]) == [("OTHER", Decimal("1"))]


def test_the_parts_always_add_up_to_the_expenses_of_the_summary():
    entries = [entry("EXPENSE", "0.10", "TOOLS"), entry("EXPENSE", "0.20"), entry("EXPENSE", "33.33", "MATERIALS"), entry("EXPENSE", "9", "OTHER", archived=True)]
    summary = summarize(entries, None, DAY)
    assert sum((p.total for p in summary.expenses_by_category), Decimal("0")) == summary.expenses == Decimal("33.63")


# ------------------------------------------------------------------ the routes

async def test_an_expense_keeps_its_category_and_an_old_one_has_none(async_client):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    tools = await add(async_client, t, p, kind="EXPENSE", title="Wiertarka", category="TOOLS")
    plain = await add(async_client, t, p, kind="EXPENSE", title="Bez kategorii")
    assert tools["category"] == "TOOLS" and plain["category"] is None
    items = {i["title"]: i["category"] for i in (await listing(async_client, t, p))["items"]}
    assert items == {"Wiertarka": "TOOLS", "Bez kategorii": None}
    invoice = await add(async_client, t, p, kind="INVOICE", title="Faktura")
    assert invoice["category"] is None


@pytest.mark.parametrize("kind", ["INVOICE", "ADVANCE", "PAYMENT"])
async def test_only_an_expense_can_have_a_category(async_client, kind):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    r = await async_client.post(f"/api/projects/{p}/payments", json=body(kind=kind, category="MATERIALS"), headers=auth_header(t))
    assert r.status_code == 422 and r.json()["detail"]["code"] == "PAYMENT_INVALID"
    assert (await listing(async_client, t, p))["total"] == 0


@pytest.mark.parametrize("word", ["materials", "FUEL", "", "MATERIALS "])
async def test_a_word_that_is_not_a_category_is_refused_and_nothing_is_saved(async_client, word):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    r = await async_client.post(f"/api/projects/{p}/payments", json=body(kind="EXPENSE", category=word), headers=auth_header(t))
    assert r.status_code == 422
    assert (await listing(async_client, t, p))["total"] == 0


async def test_a_category_can_be_set_changed_and_cleared_and_never_on_another_kind(async_client):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    expense = await add(async_client, t, p, kind="EXPENSE", title="Farba")
    invoice = await add(async_client, t, p, kind="INVOICE", title="Faktura")
    url = lambda row: f"/api/projects/{p}/payments/{row['id']}"
    for value in ("MATERIALS", "SERVICES", None):
        r = await async_client.patch(url(expense), json={"category": value}, headers=auth_header(t))
        assert r.status_code == 200 and r.json()["category"] == value, r.text
    bad = await async_client.patch(url(invoice), json={"category": "OTHER"}, headers=auth_header(t))
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "PAYMENT_INVALID"
    # a change of something else leaves the category as it was
    await async_client.patch(url(expense), json={"category": "TOOLS"}, headers=auth_header(t))
    r = await async_client.patch(url(expense), json={"title": "Farba biała"}, headers=auth_header(t))
    assert r.json()["category"] == "TOOLS"


async def test_the_summary_lists_the_parts_as_two_place_strings_and_follows_archive_and_restore(async_client):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    await add(async_client, t, p, kind="EXPENSE", title="Płytki", amount_gross="250.5", category="MATERIALS")
    transport = await add(async_client, t, p, kind="EXPENSE", title="Dostawa", amount_gross="80", category="TRANSPORT")
    await add(async_client, t, p, kind="EXPENSE", title="Stary wydatek", amount_gross="5")
    summary = (await listing(async_client, t, p))["summary"]
    assert summary["expenses"] == "335.50"
    assert summary["expenses_by_category"] == [
        {"category": "MATERIALS", "total": "250.50"}, {"category": "TRANSPORT", "total": "80.00"}, {"category": None, "total": "5.00"},
    ]
    await async_client.post(f"/api/projects/{p}/payments/{transport['id']}/archive", headers=auth_header(t))
    again = (await listing(async_client, t, p))["summary"]
    assert [x["category"] for x in again["expenses_by_category"]] == ["MATERIALS", None] and again["expenses"] == "255.50"
    await async_client.post(f"/api/projects/{p}/payments/{transport['id']}/restore", headers=auth_header(t))
    assert [x["category"] for x in (await listing(async_client, t, p))["summary"]["expenses_by_category"]] == ["MATERIALS", "TRANSPORT", None]


async def test_an_object_without_expenses_has_an_empty_list_of_parts(async_client):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    assert (await listing(async_client, t, p))["summary"]["expenses_by_category"] == []


async def test_sending_the_same_expense_again_is_safe_and_with_another_category_it_is_a_conflict(async_client):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    same = body(kind="EXPENSE", category="TOOLS", id=str(uuid.uuid4()))
    first = await async_client.post(f"/api/projects/{p}/payments", json=same, headers=auth_header(t))
    second = await async_client.post(f"/api/projects/{p}/payments", json=same, headers=auth_header(t))
    assert first.status_code == 201 and second.status_code == 201 and first.json()["id"] == second.json()["id"]
    other = await async_client.post(f"/api/projects/{p}/payments", json={**same, "category": "OTHER"}, headers=auth_header(t))
    assert other.status_code == 409
    assert (await listing(async_client, t, p))["total"] == 1


async def test_the_category_of_another_owners_expense_is_not_reachable(async_client):
    from tests.test_ia1_payments_api import other

    t, stranger = await owner(async_client), await other(async_client)
    p = await project_of(async_client, t)
    row = await add(async_client, t, p, kind="EXPENSE", title="Farba", category="MATERIALS")
    r = await async_client.patch(f"/api/projects/{p}/payments/{row['id']}", json={"category": "OTHER"}, headers=auth_header(stranger))
    assert r.status_code == 404
    assert (await listing(async_client, t, p))["items"][0]["category"] == "MATERIALS"


# ------------------------------------------------------------------ the database repeats the rules

@pytest.mark.parametrize(("kind", "category"), [("EXPENSE", "FUEL"), ("EXPENSE", ""), ("INVOICE", "MATERIALS"), ("PAYMENT", "OTHER")])
async def test_the_database_refuses_a_wrong_category_even_when_the_service_is_bypassed(async_client, db_session, kind, category):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    row = (await async_client.post(f"/api/projects/{p}/payments", json=body(kind="EXPENSE"), headers=auth_header(t))).json()
    from sqlalchemy import select

    seed = (await db_session.execute(select(ProjectPayment).where(ProjectPayment.id == uuid.UUID(row["id"])))).scalar_one()
    db_session.add(ProjectPayment(
        owner_id=seed.owner_id, project_id=seed.project_id, kind=kind, title="x", amount_gross=Decimal("1"), occurred_on=TODAY, category=category,
    ))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


def test_the_checks_of_the_migration_are_the_checks_of_the_model():
    module = load_migration("0061_expense_category")
    model = {c.name: " ".join(str(c.sqltext).split()) for c in ProjectPayment.__table__.constraints if (getattr(c, "name", None) or "").startswith("ck_project_payments_category")}
    assert model == {
        "ck_project_payments_category": " ".join(module.CHECK_VALUES.split()),
        "ck_project_payments_category_only_expense": " ".join(module.CHECK_ONLY_EXPENSE.split()),
    }
