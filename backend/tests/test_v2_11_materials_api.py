"""V2-11 -- the norms, the calculations of a room, the statement of an object and its addition to an estimate (docs/V2_11_PLAN_RU.md)."""
import uuid
from decimal import Decimal

from app.domain.data.material_norms import NORMS
from app.models.estimate import Estimate, EstimateLine, EstimateStatus, LineOrigin
from app.models.material import MaterialCalc, MaterialNorm
from sqlalchemy import select

from tests.test_area_segments import create_room
from tests.test_clients import OTHER_USER, VALID_USER, auth_header, get_token
from tests.test_projects import create_project

TILE = {"area_m2": "10", "length_cm": "30", "width_cm": "60", "thickness_mm": "8", "joint_mm": "3", "layout": "STRAIGHT", "waterproof": True, "tape_m": "12"}
WALL = {"kind": "WALL", "area_m2": "13", "layers": 2, "height_m": "2.6"}
CEILING = {"kind": "CEILING", "area_m2": "10", "layers": 1, "perimeter_m": "12"}


async def owner(c) -> str:
    return await get_token(c, VALID_USER)


async def world(c, t, rooms=("Łazienka",)):
    project = (await create_project(c, t))["id"]
    return project, [(await create_room(c, t, project, name=name))["id"] for name in rooms]


def calcs_url(project, room, calc=None) -> str:
    base = f"/api/projects/{project}/rooms/{room}/material-calcs"
    return base if calc is None else f"{base}/{calc}"


async def add_calc(c, t, project, room, package="TILE", params=None, title=None):
    params = params if params is not None else (TILE if package == "TILE" else WALL)
    return await c.post(calcs_url(project, room), json={"package": package, "title": title, "params": params}, headers=auth_header(t))


async def norms(c, t) -> dict:
    return {n["code"]: n for n in (await c.get("/api/material-norms", headers=auth_header(t))).json()["items"]}


async def item(c, t, name, unit, category="MATERIAL", price="10.00") -> dict:
    r = await c.post("/api/price-items", json={"category": category, "unit": unit, "display_name": name, "price": price}, headers=auth_header(t))
    assert r.status_code == 201, r.text
    return r.json()


async def link(c, t, code, item_id):
    n = await norms(c, t)
    return await c.patch(f"/api/material-norms/{n[code]['id']}", json={"price_item_id": item_id}, headers=auth_header(t))


async def draft(c, t, project) -> str:
    r = await c.post(f"/api/projects/{project}/estimates/generate", headers=auth_header(t))
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


# ------------------------------------------------------------------ the norms

async def test_the_norms_are_made_from_the_starting_ones_once(async_client, db_session):
    t = await owner(async_client)
    first = (await async_client.get("/api/material-norms", headers=auth_header(t))).json()["items"]
    assert [n["code"] for n in first] == [d.code for d in NORMS] and len(first) == len(NORMS)
    waste = next(n for n in first if n["code"] == "TILE_WASTE_STRAIGHT")
    assert (waste["kind"], waste["value"], waste["default_value"], waste["unit_text"], waste["minimum"], waste["maximum"]) == ("PARAM", "10", "10", "%", "0", "100")
    material = next(n for n in first if n["code"] == "TILE_ADHESIVE")
    assert (material["kind"], material["value"], material["billing_unit"], material["price_item"], material["name"], material["default_name"]) == (
        "MATERIAL", None, "PCS", None, "Klej do płytek (worek)", "Klej do płytek (worek)",
    )
    again = (await async_client.get("/api/material-norms", headers=auth_header(t))).json()["items"]
    assert [n["id"] for n in again] == [n["id"] for n in first]
    assert len((await db_session.execute(select(MaterialNorm))).scalars().all()) == len(NORMS)


async def test_the_norms_of_one_owner_are_not_the_norms_of_another(async_client, db_session):
    t = await owner(async_client)
    other = await get_token(async_client, OTHER_USER)
    mine = await norms(async_client, t)
    theirs = await norms(async_client, other)
    assert not ({n["id"] for n in mine.values()} & {n["id"] for n in theirs.values()})
    r = await async_client.patch(f"/api/material-norms/{mine['TILE_WASTE_STRAIGHT']['id']}", json={"value": "12"}, headers=auth_header(other))
    assert r.status_code == 404


async def test_a_number_is_changed_checked_and_returned_to_the_starting_one(async_client, db_session):
    t = await owner(async_client)
    n = await norms(async_client, t)
    url = f"/api/material-norms/{n['TILE_WASTE_STRAIGHT']['id']}"
    changed = await async_client.patch(url, json={"value": "12.5"}, headers=auth_header(t))
    assert changed.status_code == 200 and changed.json()["value"] == "12.5" and changed.json()["default_value"] == "10"
    for bad in ("-1", "100.5", "abc"):
        assert (await async_client.patch(url, json={"value": bad}, headers=auth_header(t))).status_code == 422
    assert (await async_client.patch(url, json={"value": "101"}, headers=auth_header(t))).json()["detail"]["code"] == "NORM_OUT_OF_RANGE"
    assert (await async_client.patch(url, json={"name": "x"}, headers=auth_header(t))).json()["detail"]["code"] == "NORM_NOT_A_MATERIAL"
    assert (await async_client.patch(url, json={"nope": 1}, headers=auth_header(t))).status_code == 422
    back = await async_client.patch(url, json={"reset": True}, headers=auth_header(t))
    assert back.json()["value"] == "10"


async def test_a_material_is_renamed_tied_to_an_item_of_its_unit_and_untied(async_client, db_session):
    t = await owner(async_client)
    other = await get_token(async_client, OTHER_USER)
    n = await norms(async_client, t)
    url = f"/api/material-norms/{n['TILE_ADHESIVE']['id']}"
    bag = await item(async_client, t, "Klej Atlas 25 kg", "PCS", price="42.50")
    r = await async_client.patch(url, json={"name": "Klej Atlas", "price_item_id": bag["id"]}, headers=auth_header(t))
    assert r.status_code == 200 and r.json()["name"] == "Klej Atlas" and r.json()["price_item"]["id"] == bag["id"] and r.json()["price_item"]["price"] == "42.50"
    assert (await async_client.patch(url, json={"value": "3"}, headers=auth_header(t))).json()["detail"]["code"] == "NORM_NOT_A_NUMBER"
    area = await item(async_client, t, "Za m2", "M2")
    assert (await async_client.patch(url, json={"price_item_id": area["id"]}, headers=auth_header(t))).json()["detail"]["code"] == "NORM_ITEM_UNIT_MISMATCH"
    foreign = await item(async_client, other, "Cudzy", "PCS")
    assert (await async_client.patch(url, json={"price_item_id": foreign["id"]}, headers=auth_header(t))).json()["detail"]["code"] == "NORM_ITEM_UNKNOWN"
    assert (await async_client.patch(url, json={"price_item_id": str(uuid.uuid4())}, headers=auth_header(t))).json()["detail"]["code"] == "NORM_ITEM_UNKNOWN"
    old = await item(async_client, t, "Stary", "PCS")
    await async_client.post(f"/api/price-items/{old['id']}/archive", headers=auth_header(t))
    assert (await async_client.patch(url, json={"price_item_id": old["id"]}, headers=auth_header(t))).json()["detail"]["code"] == "NORM_ITEM_ARCHIVED"
    untied = await async_client.patch(url, json={"price_item_id": None}, headers=auth_header(t))
    assert untied.json()["price_item"] is None and untied.json()["name"] == "Klej Atlas"
    await async_client.patch(url, json={"price_item_id": bag["id"]}, headers=auth_header(t))
    back = await async_client.patch(url, json={"reset": True}, headers=auth_header(t))
    assert back.json()["name"] == "Klej do płytek (worek)" and back.json()["price_item"] is None


async def test_the_tile_is_tied_to_an_item_in_square_metres(async_client, db_session):
    t = await owner(async_client)
    per_m2 = await item(async_client, t, "Gres 30x60", "M2", price="89.00")
    assert (await link(async_client, t, "TILE_TILES", per_m2["id"])).status_code == 200
    bag = await item(async_client, t, "Worek", "PCS")
    assert (await link(async_client, t, "TILE_TILES", bag["id"])).json()["detail"]["code"] == "NORM_ITEM_UNIT_MISMATCH"


# ------------------------------------------------------------------ the calculations of a room

async def test_a_tile_calculation_is_made_listed_changed_and_deleted(async_client, db_session):
    t = await owner(async_client)
    project, [room] = await world(async_client, t)
    made = await add_calc(async_client, t, project, room, title="  Podłoga łazienki ")
    assert made.status_code == 201, made.text
    body = made.json()
    assert body["package"] == "TILE" and body["title"] == "Podłoga łazienki" and body["room_id"] == room
    by = {m["code"]: m for m in body["materials"]}
    assert by["TILE_TILES"]["quantity"] == "11.00" and by["TILE_TILES"]["pieces"] == 62 and by["TILE_TILES"]["billing_unit"] == "M2" and by["TILE_TILES"]["billing_quantity"] == "11.00"
    assert (by["TILE_ADHESIVE"]["quantity"], by["TILE_ADHESIVE"]["unit_text"], by["TILE_ADHESIVE"]["pack_size"], by["TILE_ADHESIVE"]["packs"]) == ("50.00", "kg", "25", 2)
    assert by["TILE_ADHESIVE"]["billing_unit"] == "PCS" and by["TILE_ADHESIVE"]["billing_quantity"] == "2.00" and by["TILE_ADHESIVE"]["name"] == "Klej do płytek (worek)"
    assert by["TILE_GROUT"]["quantity"] == "2.21" and by["TILE_GROUT"]["packs"] == 1
    assert by["TILE_WATERPROOF"]["packs"] == 2 and by["TILE_WATERPROOF_TAPE"]["packs"] == 2 and by["TILE_SPACERS"]["packs"] == 1
    listed = (await async_client.get(calcs_url(project, room), headers=auth_header(t))).json()["items"]
    assert [c["id"] for c in listed] == [body["id"]]
    changed = await async_client.patch(calcs_url(project, room, body["id"]), json={"title": None, "params": {**TILE, "area_m2": "20", "waterproof": False, "tape_m": None}}, headers=auth_header(t))
    assert changed.status_code == 200 and changed.json()["title"] is None
    by2 = {m["code"]: m for m in changed.json()["materials"]}
    assert by2["TILE_TILES"]["quantity"] == "22.00" and "TILE_WATERPROOF" not in by2
    assert (await async_client.delete(calcs_url(project, room, body["id"]), headers=auth_header(t))).status_code == 204
    assert (await async_client.delete(calcs_url(project, room, body["id"]), headers=auth_header(t))).status_code == 404


async def test_a_drywall_wall_and_ceiling(async_client, db_session):
    t = await owner(async_client)
    project, [room] = await world(async_client, t)
    wall = (await add_calc(async_client, t, project, room, "DRYWALL", WALL)).json()
    by = {m["code"]: m for m in wall["materials"]}
    assert by["GK_SHEETS"]["packs"] == 10 and by["GK_UD"]["packs"] == 4 and by["GK_CD"]["packs"] == 9 and "GK_HANGERS" not in by
    ceiling = (await add_calc(async_client, t, project, room, "DRYWALL", CEILING)).json()
    by = {m["code"]: m for m in ceiling["materials"]}
    assert by["GK_SHEETS"]["packs"] == 4 and by["GK_HANGERS"]["packs"] == 15 and by["GK_UD"]["packs"] == 5


async def test_the_data_of_a_calculation_are_checked(async_client, db_session):
    t = await owner(async_client)
    project, [room] = await world(async_client, t)
    for package, params in (
        ("TILE", {**TILE, "area_m2": "0"}), ("TILE", {**TILE, "length_cm": "-3"}), ("TILE", {**TILE, "layout": "SPIRAL"}), ("TILE", {**TILE, "nope": 1}),
        ("TILE", {"area_m2": "5"}), ("DRYWALL", {**WALL, "height_m": None}), ("DRYWALL", {**CEILING, "perimeter_m": None}), ("DRYWALL", {**WALL, "layers": 3}),
        ("DRYWALL", {"kind": "FLOOR", "area_m2": "5"}),
    ):
        r = await add_calc(async_client, t, project, room, package, params)
        assert r.status_code == 422, (package, params)
    assert (await async_client.post(calcs_url(project, room), json={"package": "OTHER", "params": {}}, headers=auth_header(t))).status_code == 422
    assert (await db_session.execute(select(MaterialCalc))).scalars().all() == []
    made = (await add_calc(async_client, t, project, room)).json()
    bad = await async_client.patch(calcs_url(project, room, made["id"]), json={"params": {"area_m2": "5"}}, headers=auth_header(t))
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "CALC_INVALID"
    assert (await async_client.patch(calcs_url(project, room, made["id"]), json={"params": {**WALL}}, headers=auth_header(t))).status_code == 422  # a drywall into a tile


async def test_the_title_is_one_of_the_encrypted_columns():
    from app.core.encrypted_text import EncryptedText

    assert isinstance(MaterialCalc.__table__.c.title.type, EncryptedText)


async def test_a_changed_norm_is_seen_at_once(async_client, db_session):
    t = await owner(async_client)
    project, [room] = await world(async_client, t)
    made = (await add_calc(async_client, t, project, room)).json()
    n = await norms(async_client, t)
    await async_client.patch(f"/api/material-norms/{n['TILE_WASTE_STRAIGHT']['id']}", json={"value": "20"}, headers=auth_header(t))
    shown = (await async_client.get(calcs_url(project, room), headers=auth_header(t))).json()["items"][0]
    assert {m["code"]: m for m in shown["materials"]}["TILE_TILES"]["quantity"] == "12.00" and made["id"] == shown["id"]


async def test_nothing_of_another_owner_or_another_object_is_reachable(async_client, db_session):
    t = await owner(async_client)
    other = await get_token(async_client, OTHER_USER)
    project, [room] = await world(async_client, t)
    project2, [room2] = await world(async_client, t, ("Kuchnia",))
    made = (await add_calc(async_client, t, project, room)).json()
    for method, url, kwargs in (
        ("get", calcs_url(project, room), {}),
        ("post", calcs_url(project, room), {"json": {"package": "TILE", "params": TILE}}),
        ("patch", calcs_url(project, room, made["id"]), {"json": {"title": "x"}}),
        ("delete", calcs_url(project, room, made["id"]), {}),
        ("get", f"/api/projects/{project}/materials", {}),
    ):
        assert (await getattr(async_client, method)(url, headers=auth_header(other), **kwargs)).status_code == 404, (method, url)
    assert (await async_client.get(calcs_url(project, room2), headers=auth_header(t))).status_code == 404  # a room of another object is not this room
    assert (await async_client.patch(calcs_url(project2, room2, made["id"]), json={"title": "x"}, headers=auth_header(t))).status_code == 404


# ------------------------------------------------------------------ the statement and the estimate

async def test_the_statement_sums_the_calculations_and_makes_the_packs_once(async_client, db_session):
    t = await owner(async_client)
    project, [bath, kitchen] = await world(async_client, t, ("Łazienka", "Kuchnia"))
    small = {**TILE, "area_m2": "6", "waterproof": False, "tape_m": None}
    await add_calc(async_client, t, project, bath, "TILE", small, "Podłoga")
    await add_calc(async_client, t, project, kitchen, "TILE", small, "Fartuch")
    await add_calc(async_client, t, project, kitchen, "DRYWALL", WALL)
    s = (await async_client.get(f"/api/projects/{project}/materials", headers=auth_header(t))).json()
    assert [(c["room_name"], c["title"], c["package"]) for c in s["calcs"]] == [("Łazienka", "Podłoga", "TILE"), ("Kuchnia", "Fartuch", "TILE"), ("Kuchnia", None, "DRYWALL")]
    by = {x["code"]: x for x in s["totals"]}
    assert by["TILE_ADHESIVE"]["quantity"] == "60.00" and by["TILE_ADHESIVE"]["packs"] == 3 and by["TILE_ADHESIVE"]["billing_quantity"] == "3.00"  # 30 + 30 kg over 25 kg bags: not 2 + 2
    assert by["TILE_TILES"]["quantity"] == "13.20" and by["TILE_TILES"]["pieces"] == 74 and by["TILE_TILES"]["packs"] is None
    assert by["GK_SHEETS"]["package"] == "DRYWALL" and by["GK_SHEETS"]["packs"] == 10
    assert s["amount"] is None and s["unpriced"] == len(s["totals"])  # no price anywhere
    assert (await async_client.get(f"/api/projects/{uuid.uuid4()}/materials", headers=auth_header(t))).status_code == 404


async def test_the_statement_prices_the_materials_that_are_tied_to_an_item(async_client, db_session):
    t = await owner(async_client)
    project, [room] = await world(async_client, t)
    await add_calc(async_client, t, project, room, "TILE", {**TILE, "waterproof": False, "tape_m": None})
    await link(async_client, t, "TILE_TILES", (await item(async_client, t, "Gres", "M2", price="89.00"))["id"])
    await link(async_client, t, "TILE_ADHESIVE", (await item(async_client, t, "Klej", "PCS", price="42.50"))["id"])
    await link(async_client, t, "TILE_GROUT", (await item(async_client, t, "Fuga", "PCS", price=None))["id"])  # an item without a price
    s = (await async_client.get(f"/api/projects/{project}/materials", headers=auth_header(t))).json()
    by = {x["code"]: x for x in s["totals"]}
    assert (by["TILE_TILES"]["unit_price"], by["TILE_TILES"]["amount"]) == ("89.00", "979.00")  # 11.00 m2
    assert (by["TILE_ADHESIVE"]["unit_price"], by["TILE_ADHESIVE"]["amount"]) == ("42.50", "85.00")  # 2 bags
    assert by["TILE_GROUT"]["unit_price"] is None and by["TILE_GROUT"]["amount"] is None and by["TILE_GROUT"]["price_item_id"] is not None
    assert s["amount"] == "1064.00" and s["unpriced"] == 2  # the grout and the spacers


async def test_the_materials_become_the_lines_of_a_draft_estimate(async_client, db_session):
    t = await owner(async_client)
    project, [room] = await world(async_client, t)
    await add_calc(async_client, t, project, room, "TILE", {**TILE, "waterproof": False, "tape_m": None})
    await link(async_client, t, "TILE_TILES", (await item(async_client, t, "Gres 30x60", "M2", price="89.00"))["id"])
    await link(async_client, t, "TILE_ADHESIVE", (await item(async_client, t, "Klej Atlas", "PCS", price="42.50"))["id"])
    estimate = await draft(async_client, t, project)
    url = f"/api/projects/{project}/estimates/{estimate}/add-materials"
    r = await async_client.post(url, headers=auth_header(t))
    assert r.status_code == 200 and r.json() == {"added": 4, "already": 0, "skipped": []}
    lines = (await db_session.execute(select(EstimateLine).where(EstimateLine.estimate_id == uuid.UUID(estimate)).order_by(EstimateLine.position))).scalars().all()
    assert [ln.description for ln in lines][0] == "Gres 30x60"  # the order of the statement: the tile first
    by = {ln.description: ln for ln in lines}
    assert by["Gres 30x60"].quantity == Decimal("11.00") and by["Gres 30x60"].amount == Decimal("979.00")
    assert by["Klej Atlas"].unit.value == "PCS" and by["Klej Atlas"].quantity == Decimal(2) and by["Klej Atlas"].amount == Decimal("85.00")
    free = by["Fuga (worek)"]  # not tied: the name of the norm, no price
    assert free.unit_price is None and free.amount is None and free.price_item_id is None and free.scope.value == "MATERIAL" and free.quantity == Decimal(1)
    assert {ln.origin for ln in lines} == {LineOrigin.MANUAL} and all(ln.room_id is None for ln in lines)
    shown = (await async_client.get(f"/api/projects/{project}/estimates/{estimate}", headers=auth_header(t))).json()
    assert shown["total"] == "1064.00"
    again = await async_client.post(url, headers=auth_header(t))
    assert again.json() == {"added": 0, "already": 4, "skipped": []}


async def test_a_new_material_is_added_alone_and_a_deleted_line_comes_back_by_asking(async_client, db_session):
    t = await owner(async_client)
    project, [room] = await world(async_client, t)
    await add_calc(async_client, t, project, room, "TILE", {**TILE, "waterproof": False, "tape_m": None})
    estimate = await draft(async_client, t, project)
    url = f"/api/projects/{project}/estimates/{estimate}/add-materials"
    assert (await async_client.post(url, headers=auth_header(t))).json()["added"] == 4
    await add_calc(async_client, t, project, room, "DRYWALL", WALL)
    r = await async_client.post(url, headers=auth_header(t))
    assert r.json()["already"] == 4 and r.json()["added"] == 6  # sheets, UD, CD, screws, filler, tape
    line = (await db_session.execute(select(EstimateLine).where(EstimateLine.description == "Fuga (worek)"))).scalar_one()
    assert (await async_client.delete(f"/api/projects/{project}/estimates/{estimate}/lines/{line.id}", headers=auth_header(t))).status_code in (200, 204)
    assert (await async_client.post(url, headers=auth_header(t))).json()["added"] == 1


async def test_a_material_whose_item_has_gone_is_skipped_and_named(async_client, db_session):
    t = await owner(async_client)
    project, [room] = await world(async_client, t)
    await add_calc(async_client, t, project, room, "TILE", {**TILE, "waterproof": False, "tape_m": None})
    bag = await item(async_client, t, "Klej", "PCS", price="42.50")
    await link(async_client, t, "TILE_ADHESIVE", bag["id"])
    await async_client.post(f"/api/price-items/{bag['id']}/archive", headers=auth_header(t))
    estimate = await draft(async_client, t, project)
    r = await async_client.post(f"/api/projects/{project}/estimates/{estimate}/add-materials", headers=auth_header(t))
    assert r.json() == {"added": 3, "already": 0, "skipped": ["TILE_ADHESIVE"]}


async def test_only_a_draft_of_the_owner_takes_the_materials(async_client, db_session):
    t = await owner(async_client)
    other = await get_token(async_client, OTHER_USER)
    project, [room] = await world(async_client, t)
    await add_calc(async_client, t, project, room)
    estimate = await draft(async_client, t, project)
    url = f"/api/projects/{project}/estimates/{estimate}/add-materials"
    assert (await async_client.post(url, headers=auth_header(other))).status_code == 404
    assert (await async_client.post(f"/api/projects/{project}/estimates/{uuid.uuid4()}/add-materials", headers=auth_header(t))).status_code == 404
    await async_client.post(url, headers=auth_header(t))
    row = (await db_session.execute(select(Estimate).where(Estimate.id == uuid.UUID(estimate)))).scalar_one()
    row.status = EstimateStatus.FINAL  # finalizing wants every line priced; the state is what is under test
    await db_session.commit()
    r = await async_client.post(url, headers=auth_header(t))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "ESTIMATE_NOT_DRAFT"


async def test_the_regeneration_of_the_plan_keeps_the_lines_of_the_materials(async_client, db_session):
    t = await owner(async_client)
    project, [room] = await world(async_client, t)
    await add_calc(async_client, t, project, room, "TILE", {**TILE, "waterproof": False, "tape_m": None})
    estimate = await draft(async_client, t, project)
    await async_client.post(f"/api/projects/{project}/estimates/{estimate}/add-materials", headers=auth_header(t))
    r = await async_client.post(f"/api/projects/{project}/estimates/{estimate}/regenerate", headers=auth_header(t))
    assert r.status_code == 200, r.text
    lines = (await db_session.execute(select(EstimateLine).execution_options(populate_existing=True))).scalars().all()
    assert len(lines) == 4 and {ln.origin for ln in lines} == {LineOrigin.MANUAL}
