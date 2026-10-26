"""V2-12 -- the packages "Elektryka" and "Hydraulika" through the API: the calculations, the norms, the routes of a room, the statement and the estimate (docs/V2_12_PLAN_RU.md)."""
import uuid
from decimal import Decimal

from app.domain.data.material_norms import NORMS
from app.models.estimate import EstimateLine
from app.models.material import MaterialCalc
from sqlalchemy import select

from tests.test_clients import OTHER_USER, auth_header, get_token
from tests.test_v2_11_materials_api import add_calc, calcs_url, draft, item, link, norms, owner, world

ELECTRIC = {"sockets": 4, "switches": 2, "lights": 3, "circuits": 2}
PLUMBING = {"water_points": 3, "drain_points": 2, "manifold_outlets": 4}


async def point(c, t, project, room, item_id, quantity):
    r = await c.post(f"/api/projects/{project}/rooms/{room}/points", json={"price_item_id": item_id, "quantity": quantity}, headers=auth_header(t))
    assert r.status_code == 201, r.text


async def test_the_norms_of_the_new_packages_are_made_and_changed_like_the_others(async_client, db_session):
    t = await owner(async_client)
    n = await norms(async_client, t)
    assert len(n) == len(NORMS)
    assert {v["package"] for v in n.values()} == {"TILE", "DRYWALL", "ELECTRIC", "PLUMBING"}
    assert n["ELEC_CABLE_M_SOCKET"]["value"] == "6" and n["PL_PIPE_M_POINT"]["value"] == "4"
    r = await async_client.patch(f"/api/material-norms/{n['ELEC_CABLE_M_SOCKET']['id']}", json={"value": "8"}, headers=auth_header(t))
    assert r.status_code == 200 and r.json()["value"] == "8"
    r = await async_client.patch(f"/api/material-norms/{n['ELEC_CABLE_WASTE']['id']}", json={"value": "101"}, headers=auth_header(t))
    assert r.status_code == 422 and r.json()["detail"]["code"] == "NORM_OUT_OF_RANGE"
    socket = await item(async_client, t, "Gniazdo Simon", "PCS", price="12.00")
    assert (await link(async_client, t, "ELEC_SOCKETS", socket["id"])).status_code == 200
    per_m = await item(async_client, t, "Rura", "LM")
    assert (await link(async_client, t, "PL_PIPE", per_m["id"])).json()["detail"]["code"] == "NORM_ITEM_UNIT_MISMATCH"


async def test_an_electrical_calculation_is_made_listed_changed_and_deleted(async_client, db_session):
    t = await owner(async_client)
    project, [room] = await world(async_client, t)
    r = await add_calc(async_client, t, project, room, "ELECTRIC", ELECTRIC, title="Salon")
    assert r.status_code == 201, r.text
    made = r.json()
    by = {m["code"]: m for m in made["materials"]}
    assert made["package"] == "ELECTRIC" and made["title"] == "Salon"
    assert by["ELEC_CABLE"]["quantity"] == "51.70" and by["ELEC_CABLE"]["packs"] == 1 and by["ELEC_CABLE"]["billing_quantity"] == "1.00" and by["ELEC_CABLE"]["pack_size"] == "100"
    assert by["ELEC_CONDUIT"]["packs"] == 2 and by["ELEC_TERMINALS"]["packs"] == 1 and by["ELEC_SOCKETS"]["billing_quantity"] == "4.00"
    assert by["ELEC_SOCKETS"]["name"] == "Gniazdo"
    changed = await async_client.patch(calcs_url(project, room, made["id"]), json={"params": {**ELECTRIC, "route_m": "30"}}, headers=auth_header(t))
    assert changed.status_code == 200 and {m["code"]: m for m in changed.json()["materials"]}["ELEC_CABLE"]["quantity"] == "33.00"
    listed = (await async_client.get(calcs_url(project, room), headers=auth_header(t))).json()["items"]
    assert [c["id"] for c in listed] == [made["id"]]
    assert (await async_client.delete(calcs_url(project, room, made["id"]), headers=auth_header(t))).status_code == 204


async def test_a_plumbing_calculation(async_client, db_session):
    t = await owner(async_client)
    project, [room] = await world(async_client, t)
    r = await add_calc(async_client, t, project, room, "PLUMBING", PLUMBING)
    assert r.status_code == 201, r.text
    by = {m["code"]: m for m in r.json()["materials"]}
    assert by["PL_PIPE"]["quantity"] == "13.20" and by["PL_PIPE"]["packs"] == 1
    assert by["PL_DRAIN_PIPE"]["quantity"] == "4.00" and by["PL_DRAIN_PIPE"]["packs"] == 2 and by["PL_MANIFOLD"]["billing_quantity"] == "4.00"


async def test_a_changed_norm_of_the_new_packages_is_seen_at_once(async_client, db_session):
    t = await owner(async_client)
    project, [room] = await world(async_client, t)
    made = (await add_calc(async_client, t, project, room, "ELECTRIC", {"sockets": 10})).json()
    n = await norms(async_client, t)
    await async_client.patch(f"/api/material-norms/{n['ELEC_CABLE_M_SOCKET']['id']}", json={"value": "10"}, headers=auth_header(t))
    listed = (await async_client.get(calcs_url(project, room), headers=auth_header(t))).json()["items"]
    assert {m["code"]: m for m in listed[0]["materials"]}["ELEC_CABLE"]["quantity"] == "110.00" and listed[0]["id"] == made["id"]  # 10 * 10 * 1.1


async def test_the_data_of_the_new_calculations_are_checked(async_client, db_session):
    t = await owner(async_client)
    project, [room] = await world(async_client, t)
    for package, params in (
        ("ELECTRIC", {}), ("ELECTRIC", {"sockets": -1}), ("ELECTRIC", {"sockets": 501}), ("ELECTRIC", {"circuits": 101, "sockets": 1}), ("ELECTRIC", {"sockets": 1, "route_m": "0"}),
        ("ELECTRIC", {"sockets": 1, "nope": 1}), ("ELECTRIC", {"sockets": "x"}),
        ("PLUMBING", {}), ("PLUMBING", {"water_points": -2}), ("PLUMBING", {"manifold_outlets": 51}), ("PLUMBING", {"water_points": 1, "pipe_m": "-1"}),
        ("PLUMBING", {**PLUMBING, "sockets": 1}),
    ):
        r = await add_calc(async_client, t, project, room, package, params)
        assert r.status_code == 422, (package, params)
    assert (await db_session.execute(select(MaterialCalc))).scalars().all() == []
    assert (await add_calc(async_client, t, project, room, "ELECTRIC", {"route_m": "12"})).status_code == 201  # a route alone is enough
    assert (await add_calc(async_client, t, project, room, "ELECTRIC", {"circuits": 1})).status_code == 201
    made = (await add_calc(async_client, t, project, room, "PLUMBING", {"pipe_m": "5"})).json()
    bad = await async_client.patch(calcs_url(project, room, made["id"]), json={"params": ELECTRIC}, headers=auth_header(t))
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "CALC_INVALID"  # an electrical data into a plumbing calculation


async def test_the_routes_of_a_room_are_summed_by_trade(async_client, db_session):
    t = await owner(async_client)
    other = await get_token(async_client, OTHER_USER)
    project, [room, empty] = await world(async_client, t, ("Kuchnia", "Hol"))
    cable = await item(async_client, t, "Kabel", "LM", category="ELECTRICAL")
    chase = await item(async_client, t, "Bruzda", "LM", category="ELECTRICAL")
    pipe = await item(async_client, t, "Rura", "LM", category="PLUMBING")
    socket = await item(async_client, t, "Gniazdo", "PCS", category="ELECTRICAL")
    universal = await item(async_client, t, "Trasa", "LM", category="POINTS_ROUTES")
    for item_row, quantity in ((cable, "12.50"), (chase, "7"), (pipe, "9.25"), (socket, "4"), (universal, "30")):
        await point(async_client, t, project, room, item_row["id"], quantity)
    url = f"/api/projects/{project}/rooms/{room}/route-totals"
    assert (await async_client.get(url, headers=auth_header(t))).json() == {"electrical_m": "19.50", "plumbing_m": "9.25"}  # points in pieces and the universal routes are not counted
    assert (await async_client.get(f"/api/projects/{project}/rooms/{empty}/route-totals", headers=auth_header(t))).json() == {"electrical_m": "0.00", "plumbing_m": "0.00"}
    assert (await async_client.get(url, headers=auth_header(other))).status_code == 404
    assert (await async_client.get(f"/api/projects/{project}/rooms/{uuid.uuid4()}/route-totals", headers=auth_header(t))).status_code == 404


async def test_the_statement_and_the_estimate_take_the_new_materials(async_client, db_session):
    t = await owner(async_client)
    project, [room, second] = await world(async_client, t, ("Salon", "Sypialnia"))
    await add_calc(async_client, t, project, room, "ELECTRIC", ELECTRIC)
    await add_calc(async_client, t, project, second, "ELECTRIC", {"sockets": 4})
    await add_calc(async_client, t, project, room, "PLUMBING", {"water_points": 1})
    await link(async_client, t, "ELEC_SOCKETS", (await item(async_client, t, "Gniazdo Simon", "PCS", price="12.00"))["id"])
    s = (await async_client.get(f"/api/projects/{project}/materials", headers=auth_header(t))).json()
    totals = {x["code"]: x for x in s["totals"]}
    assert totals["ELEC_SOCKETS"]["package"] == "ELECTRIC" and totals["ELEC_SOCKETS"]["billing_quantity"] == "8.00" and totals["ELEC_SOCKETS"]["amount"] == "96.00"
    assert totals["ELEC_TERMINALS"]["quantity"] == "39.00" and totals["ELEC_TERMINALS"]["packs"] == 1  # 27 + 12 in one pack of 50
    assert totals["PL_PIPE"]["package"] == "PLUMBING" and len(s["calcs"]) == 3
    estimate = await draft(async_client, t, project)
    url = f"/api/projects/{project}/estimates/{estimate}/add-materials"
    first = (await async_client.post(url, headers=auth_header(t))).json()
    assert first["added"] == len(s["totals"]) and first["already"] == 0
    lines = {ln.description: ln for ln in (await db_session.execute(select(EstimateLine).where(EstimateLine.estimate_id == uuid.UUID(estimate)))).scalars()}
    assert lines["Gniazdo Simon"].quantity == Decimal(8) and lines["Gniazdo Simon"].amount == Decimal("96.00")
    assert lines["Rura wodna (kręg)"].unit_price is None
    assert (await async_client.post(url, headers=auth_header(t))).json()["added"] == 0
