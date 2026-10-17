"""Invoices and advances (IA-1) -- the settlement records of an object and its agreed amount (HTTP over the real routes)."""
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.estimate import Estimate, EstimateStatus
from app.models.project_payment import ProjectPayment
from tests.test_clients import OTHER_USER, VALID_USER, auth_header, get_token
from tests.test_projects import create_project

TODAY = datetime.now(UTC).date()


async def owner(c) -> str:
    return await get_token(c, VALID_USER)


async def other(c) -> str:
    return await get_token(c, OTHER_USER)


def body(kind="PAYMENT", **over):
    base = {"kind": kind, "title": "Zaliczka na materiały", "amount_gross": "1000.00", "occurred_on": TODAY.isoformat()}
    return {**base, **over}


async def add(c, token, project_id, **over):
    r = await c.post(f"/api/projects/{project_id}/payments", json=body(**over), headers=auth_header(token))
    assert r.status_code == 201, r.text
    return r.json()


async def listing(c, token, project_id, query=""):
    r = await c.get(f"/api/projects/{project_id}/payments{query}", headers=auth_header(token))
    assert r.status_code == 200, r.text
    return r.json()


async def project_of(c, token) -> str:
    return (await create_project(c, token))["id"]


# ------------------------------------------------------------------ creating

async def test_every_kind_can_be_added_with_its_own_fields(async_client):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    invoice = await add(async_client, t, p, kind="INVOICE", title="Prace malarskie", number="FV 12/2026", due_on=(TODAY + timedelta(days=7)).isoformat(),
                        amount_net="813.01", vat_rate="23.00", note="etap 1")
    advance = await add(async_client, t, p, kind="ADVANCE", title="Zaliczka na start", amount_gross="2000")
    payment = await add(async_client, t, p, kind="PAYMENT", title="Wpłata za fakturę", settles_id=invoice["id"], amount_gross="400")
    expense = await add(async_client, t, p, kind="EXPENSE", title="Farba", counterparty="Leroy Merlin", document_kind="RECEIPT", amount_gross="312.40")
    assert (invoice["kind"], invoice["number"], invoice["amount_net"], invoice["vat_rate"]) == ("INVOICE", "FV 12/2026", "813.01", "23.00")
    assert (invoice["state"], invoice["settled"], invoice["remaining"]) == ("OPEN", "0.00", "1000.00")  # as it was when it was added
    assert advance["amount_gross"] == "2000.00" and advance["state"] is None
    assert payment["settles_id"] == invoice["id"]
    assert (expense["counterparty"], expense["document_kind"]) == ("Leroy Merlin", "RECEIPT") and expense["is_archived"] is False


@pytest.mark.parametrize(
    "kind, extra",
    [
        ("ADVANCE", {"due_on": "2026-12-01"}),  # only an invoice has a due date
        ("EXPENSE", {"due_on": "2026-12-01"}),
        ("INVOICE", {"counterparty": "Sklep"}),  # only an expense has a shop
        ("PAYMENT", {"document_kind": "RECEIPT"}),
        ("EXPENSE", {"settles_id": str(uuid.uuid4())}),  # only money in settles
        ("INVOICE", {"settles_id": str(uuid.uuid4())}),
        ("PAYMENT", {"amount_net": "2000.00", "amount_gross": "1000.00"}),  # the net is not above the gross
    ],
)
async def test_a_field_of_another_kind_is_refused(async_client, kind, extra):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    r = await async_client.post(f"/api/projects/{p}/payments", json=body(kind, **extra), headers=auth_header(t))
    assert r.status_code == 422 and r.json()["detail"]["code"] == "PAYMENT_INVALID"
    assert (await listing(async_client, t, p))["total"] == 0


@pytest.mark.parametrize(
    "over",
    [{"amount_gross": "0"}, {"amount_gross": "-5"}, {"amount_gross": "10.005"}, {"amount_gross": "1234567890123.00"}, {"title": ""}, {"title": "x" * 501},
     {"vat_rate": "101"}, {"kind": "SALE"}, {"surprise": 1}, {"id": str(uuid.UUID(int=1))}],
)
async def test_an_invalid_body_is_refused_before_anything_is_written(async_client, over):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    r = await async_client.post(f"/api/projects/{p}/payments", json=body(**over), headers=auth_header(t))
    assert r.status_code == 422
    assert (await listing(async_client, t, p))["total"] == 0


async def test_a_blank_title_of_spaces_is_refused(async_client):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    r = await async_client.post(f"/api/projects/{p}/payments", json=body(title="   "), headers=auth_header(t))
    assert r.status_code == 422 and r.json()["detail"]["code"] == "PAYMENT_INVALID"


async def test_a_payment_settles_only_an_invoice_of_the_same_object(async_client):
    t = await owner(async_client)
    p, q = await project_of(async_client, t), await project_of(async_client, t)
    foreign_invoice = await add(async_client, t, q, kind="INVOICE", title="Inna")
    expense = await add(async_client, t, p, kind="EXPENSE", title="Farba")
    for target in (foreign_invoice["id"], expense["id"], str(uuid.uuid4())):
        r = await async_client.post(f"/api/projects/{p}/payments", json=body("PAYMENT", settles_id=target), headers=auth_header(t))
        assert r.status_code == 422 and r.json()["detail"]["code"] == "PAYMENT_INVALID"


async def test_a_repeated_create_with_the_same_id_is_safe_and_another_content_is_a_conflict(async_client):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    new_id = str(uuid.uuid4())
    first = await add(async_client, t, p, id=new_id)
    again = await add(async_client, t, p, id=new_id)  # the phone sent it again
    assert first["id"] == again["id"] == new_id and (await listing(async_client, t, p))["total"] == 1
    clash = await async_client.post(f"/api/projects/{p}/payments", json=body(id=new_id, amount_gross="1.00"), headers=auth_header(t))
    assert clash.status_code == 409 and clash.json()["detail"]["code"] == "CLIENT_ID_CONFLICT"
    q = await project_of(async_client, t)  # the same id on another object is a conflict too
    elsewhere = await async_client.post(f"/api/projects/{q}/payments", json=body(id=new_id), headers=auth_header(t))
    assert elsewhere.status_code == 409


# ------------------------------------------------------------------ reading: the list, the states, the summary

async def test_the_summary_and_the_state_of_an_invoice_follow_the_payments_tied_to_it(async_client):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    late = await add(async_client, t, p, kind="INVOICE", title="Spóźniona", amount_gross="1000", due_on=(TODAY - timedelta(days=2)).isoformat())
    soon = await add(async_client, t, p, kind="INVOICE", title="Wkrótce", amount_gross="500", due_on=(TODAY + timedelta(days=9)).isoformat())
    paid = await add(async_client, t, p, kind="INVOICE", title="Zapłacona", amount_gross="200")
    await add(async_client, t, p, kind="PAYMENT", title="Część", amount_gross="100", settles_id=soon["id"])
    await add(async_client, t, p, kind="PAYMENT", title="Całość", amount_gross="200", settles_id=paid["id"])
    await add(async_client, t, p, kind="ADVANCE", title="Zaliczka", amount_gross="700")
    await add(async_client, t, p, kind="EXPENSE", title="Płytki", amount_gross="250.50")
    await async_client.put(f"/api/projects/{p}/finance", json={"agreed_amount": "5000"}, headers=auth_header(t))

    data = await listing(async_client, t, p)
    states = {item["title"]: (item["state"], item["settled"], item["remaining"]) for item in data["items"] if item["kind"] == "INVOICE"}
    assert states == {"Spóźniona": ("OVERDUE", "0.00", "1000.00"), "Wkrótce": ("PARTIAL", "100.00", "400.00"), "Zapłacona": ("PAID", "200.00", "0.00")}
    s = {name: Decimal(value) for name, value in data["summary"].items() if value is not None}
    assert (s["invoiced"], s["received"], s["expenses"]) == (Decimal("1700"), Decimal("1000"), Decimal("250.50"))
    assert (s["to_receive"], s["result"], s["invoiced_unpaid"]) == (Decimal("4000"), Decimal("749.50"), Decimal("1400"))
    assert Decimal(data["agreed_amount"]) == 5000
    # without an agreed amount there is nothing "left to receive"
    await async_client.put(f"/api/projects/{p}/finance", json={"agreed_amount": None}, headers=auth_header(t))
    assert (await listing(async_client, t, p))["summary"]["to_receive"] is None


async def test_the_list_is_newest_first_filterable_and_hides_the_archived_unless_asked(async_client):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    old = await add(async_client, t, p, kind="EXPENSE", title="Stary", occurred_on=(TODAY - timedelta(days=30)).isoformat())
    new = await add(async_client, t, p, kind="EXPENSE", title="Nowy")
    await add(async_client, t, p, kind="ADVANCE", title="Zaliczka")
    assert [i["id"] for i in (await listing(async_client, t, p, "?kind=EXPENSE"))["items"]] == [new["id"], old["id"]]
    assert (await listing(async_client, t, p, "?kind=INVOICE"))["total"] == 0
    await async_client.post(f"/api/projects/{p}/payments/{old['id']}/archive", headers=auth_header(t))
    assert [i["id"] for i in (await listing(async_client, t, p, "?kind=EXPENSE"))["items"]] == [new["id"]]
    assert len((await listing(async_client, t, p, "?kind=EXPENSE&include_archived=true"))["items"]) == 2
    assert (await async_client.get(f"/api/projects/{p}/payments?kind=NOPE", headers=auth_header(t))).status_code == 422


# ------------------------------------------------------------------ changing, archiving

async def test_a_record_can_be_changed_and_a_field_cleared_but_not_its_kind(async_client):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    row = await add(async_client, t, p, kind="EXPENSE", title="Farba", number="P/1", counterparty="Castorama", amount_gross="100")
    r = await async_client.patch(f"/api/projects/{p}/payments/{row['id']}", json={"title": "Farba biała", "amount_gross": "120.50", "number": None}, headers=auth_header(t))
    assert r.status_code == 200
    changed = r.json()
    assert (changed["title"], changed["amount_gross"], changed["number"], changed["counterparty"]) == ("Farba biała", "120.50", None, "Castorama")
    for bad in ({"kind": "INVOICE"}, {"title": None}, {"amount_gross": None}, {"occurred_on": None}, {"due_on": "2026-12-01"}, {"amount_net": "999999.00"}):
        refused = await async_client.patch(f"/api/projects/{p}/payments/{row['id']}", json=bad, headers=auth_header(t))
        assert refused.status_code == 422, bad
    assert (await listing(async_client, t, p))["items"][0]["title"] == "Farba biała"


async def test_a_payment_can_be_tied_to_an_invoice_and_untied(async_client):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    invoice = await add(async_client, t, p, kind="INVOICE", title="FV", amount_gross="1000")
    pay = await add(async_client, t, p, kind="PAYMENT", title="Wpłata", amount_gross="1000")
    state = lambda data: [i for i in data["items"] if i["id"] == invoice["id"]][0]["state"]  # noqa: E731
    assert state(await listing(async_client, t, p)) == "OPEN"
    await async_client.patch(f"/api/projects/{p}/payments/{pay['id']}", json={"settles_id": invoice["id"]}, headers=auth_header(t))
    assert state(await listing(async_client, t, p)) == "PAID"
    await async_client.patch(f"/api/projects/{p}/payments/{pay['id']}", json={"settles_id": None}, headers=auth_header(t))
    assert state(await listing(async_client, t, p)) == "OPEN"


async def test_archiving_takes_a_record_out_of_the_totals_and_restoring_brings_it_back(async_client):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    invoice = await add(async_client, t, p, kind="INVOICE", title="FV", amount_gross="1000")
    pay = await add(async_client, t, p, kind="PAYMENT", title="Wpłata", amount_gross="1000", settles_id=invoice["id"])
    summary = lambda: listing(async_client, t, p)  # noqa: E731
    assert (await summary())["summary"]["received"] == "1000.00"
    archived = (await async_client.post(f"/api/projects/{p}/payments/{pay['id']}/archive", headers=auth_header(t))).json()
    assert archived["is_archived"] is True
    data = await summary()
    assert data["summary"]["received"] == "0.00" and [i for i in data["items"] if i["id"] == invoice["id"]][0]["state"] == "OPEN"
    restored = (await async_client.post(f"/api/projects/{p}/payments/{pay['id']}/restore", headers=auth_header(t))).json()
    assert restored["is_archived"] is False and (await summary())["summary"]["received"] == "1000.00"


# ------------------------------------------------------------------ the agreed amount and its hint from the estimate

async def test_the_agreed_amount_is_set_cleared_and_must_be_positive(async_client):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    first = (await async_client.get(f"/api/projects/{p}/finance", headers=auth_header(t))).json()
    assert first == {"agreed_amount": None, "currency": "PLN", "suggestion": None}
    put = await async_client.put(f"/api/projects/{p}/finance", json={"agreed_amount": "40000"}, headers=auth_header(t))
    assert put.status_code == 200 and put.json()["agreed_amount"] == "40000.00"
    assert (await async_client.put(f"/api/projects/{p}/finance", json={"agreed_amount": "41500.50"}, headers=auth_header(t))).json()["agreed_amount"] == "41500.50"
    assert (await async_client.put(f"/api/projects/{p}/finance", json={"agreed_amount": None}, headers=auth_header(t))).json()["agreed_amount"] is None
    for bad in ({"agreed_amount": "0"}, {"agreed_amount": "-1"}, {"agreed_amount": "1.005"}, {"currency": "EUR"}):
        assert (await async_client.put(f"/api/projects/{p}/finance", json=bad, headers=auth_header(t))).status_code == 422


async def test_the_hint_is_the_total_of_the_accepted_estimate_else_of_the_final_one(async_client, db_session):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    from sqlalchemy import select

    from app.models.project import Project

    project = (await db_session.execute(select(Project).where(Project.id == uuid.UUID(p)))).scalar_one()
    owner_id, project_id = project.owner_id, project.id

    async def estimate(version, status, total):
        db_session.add(Estimate(owner_id=owner_id, project_id=project_id, version=version, status=status, total=total, currency="PLN"))
        await db_session.commit()

    hint = lambda: async_client.get(f"/api/projects/{p}/finance", headers=auth_header(t))  # noqa: E731
    await estimate(1, EstimateStatus.DRAFT, Decimal("99999.00"))  # a draft is not a hint
    assert (await hint()).json()["suggestion"] is None
    await estimate(2, EstimateStatus.FINAL, Decimal("39000.00"))
    got = (await hint()).json()["suggestion"]
    assert (got["amount"], got["estimate_version"], got["status"]) == ("39000.00", 2, "FINAL")
    await estimate(3, EstimateStatus.ACCEPTED, Decimal("38420.00"))
    await estimate(4, EstimateStatus.FINAL, Decimal("45000.00"))  # newer, but the accepted one wins
    got = (await hint()).json()["suggestion"]
    assert (got["amount"], got["estimate_version"], got["status"]) == ("38420.00", 3, "ACCEPTED")
    # the hint never becomes the agreed amount by itself
    assert (await hint()).json()["agreed_amount"] is None


# ------------------------------------------------------------------ owners

async def test_nothing_of_another_owner_is_reachable(async_client):
    t, stranger = await owner(async_client), await other(async_client)
    p = await project_of(async_client, t)
    row = await add(async_client, t, p)
    mine = {"headers": auth_header(stranger)}
    for method, url, payload in (
        ("get", f"/api/projects/{p}/payments", None), ("post", f"/api/projects/{p}/payments", body()),
        ("patch", f"/api/projects/{p}/payments/{row['id']}", {"title": "x"}), ("post", f"/api/projects/{p}/payments/{row['id']}/archive", None),
        ("post", f"/api/projects/{p}/payments/{row['id']}/restore", None), ("get", f"/api/projects/{p}/finance", None),
        ("put", f"/api/projects/{p}/finance", {"agreed_amount": "1"}),
    ):
        kwargs = dict(mine, **({"json": payload} if payload is not None else {}))
        assert (await getattr(async_client, method)(url, **kwargs)).status_code == 404, (method, url)
    assert (await listing(async_client, t, p))["total"] == 1
    # a record of mine is not reachable through another object of mine
    q = await project_of(async_client, t)
    assert (await async_client.patch(f"/api/projects/{q}/payments/{row['id']}", json={"title": "x"}, headers=auth_header(t))).status_code == 404


async def test_every_route_needs_a_signed_in_user(async_client):
    p = uuid.uuid4()
    for method, url in (("get", f"/api/projects/{p}/payments"), ("post", f"/api/projects/{p}/payments"), ("get", f"/api/projects/{p}/finance"), ("put", f"/api/projects/{p}/finance")):
        assert (await getattr(async_client, method)(url)).status_code in (401, 403)


# ------------------------------------------------------------------ the database repeats the rules

@pytest.mark.parametrize(
    "bad",
    [
        {"kind": "SALE"}, {"amount_gross": Decimal("0")}, {"amount_net": Decimal("-1")}, {"vat_rate": Decimal("101")}, {"title": "  "},
        {"document_kind": "RECEIPT"}, {"counterparty": "Sklep"}, {"due_on": date(2026, 12, 1), "kind": "EXPENSE"}, {"document_kind": "OTHER", "kind": "EXPENSE"},
    ],
)
async def test_the_database_refuses_what_the_service_refuses(async_client, db_session, bad):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    from sqlalchemy import select

    from app.models.project import Project

    project = (await db_session.execute(select(Project).where(Project.id == uuid.UUID(p)))).scalar_one()
    base = {"owner_id": project.owner_id, "project_id": project.id, "kind": "INVOICE", "title": "x", "amount_gross": Decimal("1"), "occurred_on": TODAY}
    db_session.add(ProjectPayment(**{**base, **bad}))
    with pytest.raises(IntegrityError):
        await db_session.flush()
    await db_session.rollback()


async def test_deleting_the_object_takes_its_records_and_agreed_amount_with_it(async_client, db_session):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    await add(async_client, t, p)
    await async_client.put(f"/api/projects/{p}/finance", json={"agreed_amount": "1000"}, headers=auth_header(t))
    from sqlalchemy import delete, func, select

    from app.models.project import Project
    from app.models.project_payment import ProjectFinance

    await db_session.execute(delete(Project).where(Project.id == uuid.UUID(p)))
    await db_session.commit()
    assert (await db_session.execute(select(func.count()).select_from(ProjectPayment))).scalar_one() == 0
    assert (await db_session.execute(select(func.count()).select_from(ProjectFinance))).scalar_one() == 0
