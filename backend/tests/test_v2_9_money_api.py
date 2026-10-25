"""V2-9 -- the payment schedule, the work hours and the margin over the real routes (HTTP), with the rules of the owner's scope."""
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.payment_stage import PaymentStage, WorkHour
from app.models.project_payment import ProjectPayment
from tests.test_clients import OTHER_USER, VALID_USER, auth_header, get_token
from tests.test_projects import create_project

TODAY = datetime.now(UTC).date()


async def owner(c) -> str:
    return await get_token(c, VALID_USER)


async def project_of(c, token) -> str:
    return (await create_project(c, token))["id"]


def h(token):
    return auth_header(token)


async def agree(c, token, project, amount="40000"):
    r = await c.put(f"/api/projects/{project}/finance", json={"agreed_amount": amount}, headers=h(token))
    assert r.status_code == 200, r.text


async def stage(c, token, project, **over):
    body = {"title": "Zaliczka", "percent": "30", **over}
    r = await c.post(f"/api/projects/{project}/payment-stages", json=body, headers=h(token))
    assert r.status_code == 201, r.text
    return r.json()


async def schedule(c, token, project):
    r = await c.get(f"/api/projects/{project}/payment-stages", headers=h(token))
    assert r.status_code == 200, r.text
    return r.json()


async def pay(c, token, project, kind="PAYMENT", **over):
    body = {"kind": kind, "title": "Wpłata", "amount_gross": "1000.00", "occurred_on": TODAY.isoformat(), **over}
    r = await c.post(f"/api/projects/{project}/payments", json=body, headers=h(token))
    return r


# --- the schedule -----------------------------------------------------------------------------------------------------------------------------------


async def test_a_stage_is_a_share_or_a_fixed_amount_and_the_server_prices_it(async_client):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    await agree(async_client, t, p)
    share = await stage(async_client, t, p, title="Zaliczka", percent="30")
    fixed = await stage(async_client, t, p, title="Odbiór", percent=None, amount="5000", due_on=(TODAY + timedelta(days=30)).isoformat())
    assert (share["amount"], share["percent"], share["amount_fixed"], share["state"], share["remaining"]) == ("12000.00", "30.00", None, "OPEN", "12000.00")
    assert (fixed["amount"], fixed["percent"], fixed["amount_fixed"]) == ("5000.00", None, "5000.00")
    listed = await schedule(async_client, t, p)
    assert [i["title"] for i in listed["items"]] == ["Odbiór", "Zaliczka"]  # the day first, no day last
    assert listed["summary"] == {"agreed": "40000.00", "stages_total": "17000.00", "unpriced": 0, "difference": "23000.00", "received": "0.00", "to_receive": "17000.00"}


@pytest.mark.parametrize("body", [
    {"title": "x"},  # neither
    {"title": "x", "percent": "30", "amount": "100"},  # both
    {"title": "x", "percent": "0"}, {"title": "x", "percent": "101"}, {"title": "x", "amount": "0"}, {"title": "  "}, {"percent": "10"},
    {"title": "x", "percent": "10", "extra": 1},
])
async def test_a_wrong_stage_is_refused(async_client, body):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    r = await async_client.post(f"/api/projects/{p}/payment-stages", json=body, headers=h(t))
    assert r.status_code == 422


async def test_a_blank_title_in_the_service_is_a_stable_code(async_client):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    s = await stage(async_client, t, p)
    r = await async_client.patch(f"/api/projects/{p}/payment-stages/{s['id']}", json={"title": " "}, headers=h(t))
    assert r.status_code == 422  # the schema's minimum or the rule: never saved
    assert (await schedule(async_client, t, p))["items"][0]["title"] == "Zaliczka"


async def test_changing_a_stage_swaps_percent_and_amount_and_can_clear_the_day(async_client):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    await agree(async_client, t, p, "10000")
    s = await stage(async_client, t, p, due_on=TODAY.isoformat())
    r = await async_client.patch(f"/api/projects/{p}/payment-stages/{s['id']}", json={"amount": "2500", "due_on": None, "title": "Po gładziach"}, headers=h(t))
    assert r.status_code == 200, r.text
    changed = r.json()
    assert (changed["title"], changed["percent"], changed["amount_fixed"], changed["amount"], changed["due_on"]) == ("Po gładziach", None, "2500.00", "2500.00", None)
    back = (await async_client.patch(f"/api/projects/{p}/payment-stages/{s['id']}", json={"percent": "50"}, headers=h(t))).json()
    assert (back["percent"], back["amount_fixed"], back["amount"]) == ("50.00", None, "5000.00")
    assert (await async_client.patch(f"/api/projects/{p}/payment-stages/{s['id']}", json={"percent": "50", "amount": "1"}, headers=h(t))).status_code == 422


async def test_shares_follow_the_agreed_amount_and_wait_without_it(async_client):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    await stage(async_client, t, p)
    waiting = await schedule(async_client, t, p)
    assert waiting["items"][0]["amount"] is None and waiting["summary"]["unpriced"] == 1 and waiting["summary"]["to_receive"] is None
    await agree(async_client, t, p, "1000")
    assert (await schedule(async_client, t, p))["items"][0]["amount"] == "300.00"
    await agree(async_client, t, p, "2000")
    assert (await schedule(async_client, t, p))["items"][0]["amount"] == "600.00"


async def test_money_received_for_a_stage_moves_its_state(async_client):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    await agree(async_client, t, p, "1000")
    s = await stage(async_client, t, p, percent="50")
    first = await pay(async_client, t, p, kind="ADVANCE", amount_gross="200", stage_id=s["id"])
    assert first.status_code == 201 and first.json()["stage_id"] == s["id"]
    item = (await schedule(async_client, t, p))["items"][0]
    assert (item["state"], item["received"], item["remaining"]) == ("PARTIAL", "200.00", "300.00")
    second = await pay(async_client, t, p, amount_gross="300", stage_id=s["id"])
    assert (await schedule(async_client, t, p))["items"][0]["state"] == "PAID"
    archived = await async_client.post(f"/api/projects/{p}/payments/{second.json()['id']}/archive", headers=h(t))
    assert archived.status_code == 200
    assert (await schedule(async_client, t, p))["items"][0]["state"] == "PARTIAL"  # an archived record does not count


async def test_a_stage_is_for_money_in_of_the_same_object_only(async_client):
    t = await owner(async_client)
    p, q = await project_of(async_client, t), await project_of(async_client, t)
    s = await stage(async_client, t, p)
    for kind in ("EXPENSE", "INVOICE"):
        r = await pay(async_client, t, p, kind=kind, stage_id=s["id"])
        assert (r.status_code, r.json()["detail"]["code"]) == (422, "PAYMENT_INVALID")
    elsewhere = await pay(async_client, t, q, stage_id=s["id"])
    assert elsewhere.status_code == 422
    none = await pay(async_client, t, p, stage_id=str(uuid.uuid4()))
    assert none.status_code == 422
    ok = (await pay(async_client, t, p)).json()
    moved = await async_client.patch(f"/api/projects/{p}/payments/{ok['id']}", json={"stage_id": s["id"]}, headers=h(t))
    assert moved.status_code == 200 and moved.json()["stage_id"] == s["id"]
    cleared = await async_client.patch(f"/api/projects/{p}/payments/{ok['id']}", json={"stage_id": None}, headers=h(t))
    assert cleared.json()["stage_id"] is None


async def test_receiving_books_the_rest_in_one_step_and_only_once(async_client):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    await agree(async_client, t, p, "1000")
    s = await stage(async_client, t, p, title="Po gładziach", percent="40")
    await pay(async_client, t, p, amount_gross="100", stage_id=s["id"])
    r = await async_client.post(f"/api/projects/{p}/payment-stages/{s['id']}/receive", headers=h(t))
    assert r.status_code == 201, r.text
    booked = r.json()
    assert (booked["kind"], booked["title"], booked["amount_gross"], booked["occurred_on"], booked["stage_id"]) == ("PAYMENT", "Po gładziach", "300.00", TODAY.isoformat(), s["id"])
    assert (await schedule(async_client, t, p))["items"][0]["state"] == "PAID"
    again = await async_client.post(f"/api/projects/{p}/payment-stages/{s['id']}/receive", headers=h(t))
    assert (again.status_code, again.json()["detail"]["code"]) == (422, "STAGE_NOTHING_LEFT")


async def test_a_share_without_an_agreed_amount_cannot_be_received(async_client):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    s = await stage(async_client, t, p)
    r = await async_client.post(f"/api/projects/{p}/payment-stages/{s['id']}/receive", headers=h(t))
    assert (r.status_code, r.json()["detail"]["code"]) == (422, "STAGE_AMOUNT_UNKNOWN")


async def test_deleting_a_stage_keeps_the_money(async_client, db_session):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    await agree(async_client, t, p, "1000")
    s = await stage(async_client, t, p)
    paid = (await pay(async_client, t, p, amount_gross="250", stage_id=s["id"])).json()
    assert (await async_client.delete(f"/api/projects/{p}/payment-stages/{s['id']}", headers=h(t))).status_code == 204
    assert (await schedule(async_client, t, p))["items"] == []
    db_session.expire_all()
    row = (await db_session.execute(select(ProjectPayment).where(ProjectPayment.id == uuid.UUID(paid["id"])))).scalar_one()
    assert row.stage_id is None and str(row.amount_gross) == "250.00" and row.is_archived is False
    assert (await async_client.delete(f"/api/projects/{p}/payment-stages/{s['id']}", headers=h(t))).status_code == 404


async def test_another_owner_sees_nothing_and_changes_nothing(async_client, db_session):
    t, o = await owner(async_client), await get_token(async_client, OTHER_USER)
    p = await project_of(async_client, t)
    s = await stage(async_client, t, p)
    (await async_client.post(f"/api/projects/{p}/work-hours", json={"worked_on": TODAY.isoformat(), "hours": "3"}, headers=h(t))).raise_for_status()
    own = await project_of(async_client, o)
    probes = [
        ("get", f"/api/projects/{p}/payment-stages", None), ("post", f"/api/projects/{p}/payment-stages", {"title": "x", "percent": "1"}),
        ("patch", f"/api/projects/{p}/payment-stages/{s['id']}", {"title": "y"}), ("delete", f"/api/projects/{p}/payment-stages/{s['id']}", None),
        ("post", f"/api/projects/{p}/payment-stages/{s['id']}/receive", None), ("get", f"/api/projects/{p}/work-hours", None),
        ("post", f"/api/projects/{p}/work-hours", {"worked_on": TODAY.isoformat(), "hours": "1"}), ("get", f"/api/projects/{p}/margin", None),
        ("patch", f"/api/projects/{own}/payment-stages/{s['id']}", {"title": "y"}),  # the stage of another object is not found under mine either
    ]
    for method, url, body in probes:
        r = await getattr(async_client, method)(url, headers=h(o), **({"json": body} if body is not None else {}))
        assert r.status_code == 404, (method, url, r.status_code)
    db_session.expire_all()
    assert (await db_session.execute(select(PaymentStage))).scalar_one().title == "Zaliczka"
    assert len((await db_session.execute(select(WorkHour))).scalars().all()) == 1


async def test_the_routes_need_a_token(async_client):
    pid = uuid.uuid4()
    for method, url in (("get", f"/api/projects/{pid}/payment-stages"), ("post", f"/api/projects/{pid}/payment-stages"), ("get", f"/api/projects/{pid}/work-hours"),
                        ("post", f"/api/projects/{pid}/work-hours"), ("get", f"/api/projects/{pid}/margin")):
        assert (await getattr(async_client, method)(url)).status_code == 401, url


# --- the hours --------------------------------------------------------------------------------------------------------------------------------------


async def test_hours_are_logged_summed_changed_and_deleted(async_client):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    a = await async_client.post(f"/api/projects/{p}/work-hours", json={"worked_on": TODAY.isoformat(), "hours": "7.5", "note": " gładź salon "}, headers=h(t))
    assert a.status_code == 201, a.text
    assert (a.json()["hours"], a.json()["note"]) == ("7.50", "gładź salon")
    b = await async_client.post(f"/api/projects/{p}/work-hours", json={"worked_on": (TODAY - timedelta(days=1)).isoformat(), "hours": "4.25"}, headers=h(t))
    listed = (await async_client.get(f"/api/projects/{p}/work-hours", headers=h(t))).json()
    assert [i["hours"] for i in listed["items"]] == ["7.50", "4.25"] and listed["total_hours"] == "11.75" and listed["hourly_rate"] is None
    changed = await async_client.patch(f"/api/projects/{p}/work-hours/{b.json()['id']}", json={"hours": "5", "note": None}, headers=h(t))
    assert (changed.json()["hours"], changed.json()["note"]) == ("5.00", None)
    assert (await async_client.delete(f"/api/projects/{p}/work-hours/{a.json()['id']}", headers=h(t))).status_code == 204
    assert (await async_client.get(f"/api/projects/{p}/work-hours", headers=h(t))).json()["total_hours"] == "5.00"
    assert (await async_client.delete(f"/api/projects/{p}/work-hours/{a.json()['id']}", headers=h(t))).status_code == 404


@pytest.mark.parametrize("hours", ["0", "-1", "24.01", "abc", "1.005"])
async def test_wrong_hours_are_refused(async_client, hours):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    r = await async_client.post(f"/api/projects/{p}/work-hours", json={"worked_on": TODAY.isoformat(), "hours": hours}, headers=h(t))
    assert r.status_code == 422


# --- the rate and the margin ------------------------------------------------------------------------------------------------------------------------


async def profile(c, token, **extra):
    return await c.put("/api/executor-profile", json={"name": "Jan Kowalski Wykończenia", **extra}, headers=h(token))


async def test_the_hourly_rate_is_kept_cleared_and_validated(async_client):
    t = await owner(async_client)
    assert (await profile(async_client, t, hourly_rate="90")).status_code == 200
    got = (await async_client.get("/api/executor-profile", headers=h(t))).json()["profile"]
    assert got["hourly_rate"] == "90.00"
    assert (await profile(async_client, t)).status_code == 200  # omitted: the rate stays (an older screen never clears it)
    assert (await async_client.get("/api/executor-profile", headers=h(t))).json()["profile"]["hourly_rate"] == "90.00"
    assert (await profile(async_client, t, hourly_rate=None)).status_code == 200  # given as null: cleared
    assert (await async_client.get("/api/executor-profile", headers=h(t))).json()["profile"]["hourly_rate"] is None
    for bad in ("0", "-5", "abc"):
        assert (await profile(async_client, t, hourly_rate=bad)).status_code == 422


async def test_the_margin_is_counted_on_the_server_from_what_the_screens_show(async_client):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    empty = (await async_client.get(f"/api/projects/{p}/margin", headers=h(t))).json()
    assert (empty["basis"], empty["margin"], empty["expenses"], empty["hours"]) == (None, None, "0.00", "0.00")
    await agree(async_client, t, p, "10000")
    (await pay(async_client, t, p, kind="EXPENSE", title="Farba", amount_gross="1500.50")).raise_for_status()
    (await pay(async_client, t, p, kind="EXPENSE", title="Stare", amount_gross="999")).raise_for_status()
    old = (await async_client.get(f"/api/projects/{p}/payments", headers=h(t))).json()["items"][0]["id"]
    (await async_client.post(f"/api/projects/{p}/payments/{old}/archive", headers=h(t))).raise_for_status()
    for hours in ("24", "16", "20"):
        (await async_client.post(f"/api/projects/{p}/work-hours", json={"worked_on": TODAY.isoformat(), "hours": hours}, headers=h(t))).raise_for_status()
    before = (await async_client.get(f"/api/projects/{p}/margin", headers=h(t))).json()
    assert (before["basis"], before["basis_source"], before["expenses"], before["hours"], before["labor_included"]) == ("10000.00", "AGREED", "1500.50", "60.00", False)
    await profile(async_client, t, hourly_rate="80")
    after = (await async_client.get(f"/api/projects/{p}/margin", headers=h(t))).json()
    assert (after["labor_cost"], after["labor_included"], after["hourly_rate"]) == ("4800.00", True, "80.00")
    assert (after["margin"], after["percent"], after["per_hour"]) == ("3699.50", "37.00", "141.66")
    # the work log shows the rate too
    assert (await async_client.get(f"/api/projects/{p}/work-hours", headers=h(t))).json()["hourly_rate"] == "80.00"
