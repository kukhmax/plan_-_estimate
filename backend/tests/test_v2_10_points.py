"""V2-10 -- the points and routes of a room: the list, the rules of a row, the typical items, the addition to an estimate (docs/V2_10_PLAN_RU.md)."""
import uuid
from decimal import Decimal

import pytest
from app.domain.data.points_pack import POINTS_PACK
from app.models.estimate import EstimateLine, LineOrigin
from app.models.price_item import PriceCategory, PriceItem, PriceUnit
from app.models.room_point import RoomPoint
from sqlalchemy import select

from tests.test_area_segments import create_room
from tests.test_clients import OTHER_USER, VALID_USER, auth_header, get_token
from tests.test_projects import create_project


async def owner(c) -> str:
    return await get_token(c, VALID_USER)


async def item(c, token, name="Gniazdko", unit="PCS", category="ELECTRICAL", price="45.00", **extra) -> dict:
    body = {"category": category, "unit": unit, "display_name": name, "price": price, **extra}
    r = await c.post("/api/price-items", json=body, headers=auth_header(token))
    assert r.status_code == 201, r.text
    return r.json()


async def world(c, token, rooms=("Łazienka",)):
    project = (await create_project(c, token))["id"]
    ids = [(await create_room(c, token, project, name=name))["id"] for name in rooms]
    return project, ids


def points_url(project, room, point=None) -> str:
    base = f"/api/projects/{project}/rooms/{room}/points"
    return base if point is None else f"{base}/{point}"


async def add(c, token, project, room, item_id, quantity="4", **extra):
    return await c.post(points_url(project, room), json={"price_item_id": item_id, "quantity": quantity, **extra}, headers=auth_header(token))


async def draft(c, token, project) -> str:
    r = await c.post(f"/api/projects/{project}/estimates/generate", headers=auth_header(token))
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


# ------------------------------------------------------------------ the categories and the typical items

def test_the_four_categories_are_known():
    assert {"ELECTRICAL", "PLUMBING", "TILE", "POINTS_ROUTES"} <= {c.value for c in PriceCategory}


def test_the_pack_has_twelve_rows_with_unique_names_and_the_right_units():
    assert len(POINTS_PACK) == 12 and len({(p.display_name, p.category) for p in POINTS_PACK}) == 12
    for entry in POINTS_PACK:
        assert entry.unit in (PriceUnit.PCS, PriceUnit.LM) or entry.category is PriceCategory.TILE
    assert {p.category for p in POINTS_PACK} == {PriceCategory.ELECTRICAL, PriceCategory.PLUMBING, PriceCategory.TILE, PriceCategory.POINTS_ROUTES}


async def test_a_custom_item_may_have_a_new_category(async_client, db_session):
    t = await owner(async_client)
    for category in ("ELECTRICAL", "PLUMBING", "TILE", "POINTS_ROUTES"):
        made = await item(async_client, t, name=f"x {category}", category=category)
        assert made["category"] == category
    listed = (await async_client.get("/api/price-items", params={"category": "PLUMBING"}, headers=auth_header(t))).json()
    assert [i["category"] for i in listed["items"]] == ["PLUMBING"]


async def test_the_pack_makes_the_rows_without_prices_and_twice_makes_nothing_new(async_client, db_session):
    t = await owner(async_client)
    first = await async_client.post("/api/price-items/points-pack", headers=auth_header(t))
    assert first.status_code == 200 and first.json() == {"created": 12, "existing": 0}
    made = (await db_session.execute(select(PriceItem).where(PriceItem.code.like("CUSTOM_%")))).scalars().all()
    assert len(made) == 12 and all(row.price is None and row.display_name for row in made)
    assert {(row.display_name, row.category) for row in made} == {(p.display_name, p.category) for p in POINTS_PACK}
    again = await async_client.post("/api/price-items/points-pack", headers=auth_header(t))
    assert again.json() == {"created": 0, "existing": 12}
    # a row the owner renamed is made again (the pack names what the owner has not changed); one archived is still "had"
    other = await get_token(async_client, OTHER_USER)
    assert (await async_client.post("/api/price-items/points-pack", headers=auth_header(other))).json() == {"created": 12, "existing": 0}


# ------------------------------------------------------------------ the list of a room

async def test_a_point_is_made_listed_changed_and_deleted(async_client, db_session):
    t = await owner(async_client)
    project, [room] = await world(async_client, t)
    socket = await item(async_client, t)
    made = await add(async_client, t, project, room, socket["id"], "12", note="  przy oknie ")
    assert made.status_code == 201, made.text
    body = made.json()
    assert (body["quantity"], body["note"], body["room_id"]) == ("12.00", "przy oknie", room)
    assert body["item"]["id"] == socket["id"] and body["item"]["unit"] == "PCS" and body["item"]["price"] == "45.00"
    chase = await item(async_client, t, "Bruzda", "LM", "ELECTRICAL", "18.50")
    await add(async_client, t, project, room, chase["id"], "7.5")
    listed = (await async_client.get(points_url(project, room), headers=auth_header(t))).json()["items"]
    assert [(r["item"]["display_name"], r["quantity"]) for r in listed] == [("Gniazdko", "12.00"), ("Bruzda", "7.50")]  # the order of entry
    changed = await async_client.patch(points_url(project, room, body["id"]), json={"quantity": "10", "note": None}, headers=auth_header(t))
    assert changed.status_code == 200 and changed.json()["quantity"] == "10.00" and changed.json()["note"] is None
    swapped = await async_client.patch(points_url(project, room, body["id"]), json={"price_item_id": chase["id"]}, headers=auth_header(t))
    assert swapped.status_code == 200 and swapped.json()["item"]["unit"] == "LM"
    assert (await async_client.delete(points_url(project, room, body["id"]), headers=auth_header(t))).status_code == 204
    assert len((await async_client.get(points_url(project, room), headers=auth_header(t))).json()["items"]) == 1
    assert (await async_client.delete(points_url(project, room, body["id"]), headers=auth_header(t))).status_code == 404


def test_the_note_is_one_of_the_encrypted_columns():
    from app.core.encrypted_text import EncryptedText

    assert isinstance(RoomPoint.__table__.c.note.type, EncryptedText)


@pytest.mark.parametrize("quantity", ["0", "-1", "1.234", "abc", "100000000000"])
async def test_a_quantity_must_be_positive_with_at_most_two_places(async_client, db_session, quantity):
    t = await owner(async_client)
    project, [room] = await world(async_client, t)
    r = await add(async_client, t, project, room, (await item(async_client, t))["id"], quantity)
    assert r.status_code == 422
    assert (await db_session.execute(select(RoomPoint))).scalars().all() == []


async def test_only_a_live_item_of_the_owner_in_pieces_or_metres_can_be_a_row(async_client, db_session):
    t = await owner(async_client)
    other = await get_token(async_client, OTHER_USER)
    project, [room] = await world(async_client, t)
    area = await item(async_client, t, "Układanie", "M2", "TILE")
    r = await add(async_client, t, project, room, area["id"])
    assert r.status_code == 422 and r.json()["detail"]["code"] == "POINT_UNIT_INVALID"
    foreign = await item(async_client, other, "Cudze")
    r = await add(async_client, t, project, room, foreign["id"])
    assert r.status_code == 422 and r.json()["detail"]["code"] == "POINT_ITEM_UNKNOWN"
    r = await add(async_client, t, project, room, str(uuid.uuid4()))
    assert r.json()["detail"]["code"] == "POINT_ITEM_UNKNOWN"
    old = await item(async_client, t, "Stare")
    assert (await async_client.post(f"/api/price-items/{old['id']}/archive", headers=auth_header(t))).status_code == 200
    r = await add(async_client, t, project, room, old["id"])
    assert r.json()["detail"]["code"] == "POINT_ITEM_ARCHIVED"
    assert (await db_session.execute(select(RoomPoint))).scalars().all() == []


async def test_a_change_obeys_the_same_rules(async_client, db_session):
    t = await owner(async_client)
    project, [room] = await world(async_client, t)
    made = (await add(async_client, t, project, room, (await item(async_client, t))["id"])).json()
    area = await item(async_client, t, "Fugowanie", "M2", "TILE")
    r = await async_client.patch(points_url(project, room, made["id"]), json={"price_item_id": area["id"]}, headers=auth_header(t))
    assert r.status_code == 422 and r.json()["detail"]["code"] == "POINT_UNIT_INVALID"
    assert (await async_client.patch(points_url(project, room, made["id"]), json={"quantity": "0"}, headers=auth_header(t))).status_code == 422
    assert (await async_client.patch(points_url(project, room, made["id"]), json={"nope": 1}, headers=auth_header(t))).status_code == 422


async def test_nothing_of_another_owner_or_another_object_is_reachable(async_client, db_session):
    t = await owner(async_client)
    other = await get_token(async_client, OTHER_USER)
    project, [room] = await world(async_client, t)
    project2, [room2] = await world(async_client, t, ("Kuchnia",))
    made = (await add(async_client, t, project, room, (await item(async_client, t))["id"])).json()
    for method, url, kwargs in (
        ("get", points_url(project, room), {}),
        ("post", points_url(project, room), {"json": {"price_item_id": str(uuid.uuid4()), "quantity": "1"}}),
        ("patch", points_url(project, room, made["id"]), {"json": {"quantity": "2"}}),
        ("delete", points_url(project, room, made["id"]), {}),
        ("get", f"/api/projects/{project}/room-points/summary", {}),
    ):
        assert (await getattr(async_client, method)(url, headers=auth_header(other), **kwargs)).status_code == 404, (method, url)
    # a room of another object of the same owner is not this room
    assert (await async_client.get(points_url(project, room2), headers=auth_header(t))).status_code == 404
    assert (await async_client.patch(points_url(project2, room2, made["id"]), json={"quantity": "2"}, headers=auth_header(t))).status_code == 404


async def test_the_counts_by_room(async_client, db_session):
    t = await owner(async_client)
    project, [bath, kitchen] = await world(async_client, t, ("Łazienka", "Kuchnia"))
    socket = await item(async_client, t)
    for _ in range(3):
        await add(async_client, t, project, bath, socket["id"])
    counts = (await async_client.get(f"/api/projects/{project}/room-points/summary", headers=auth_header(t))).json()["items"]
    assert counts == [{"room_id": bath, "count": 3}] and kitchen not in {c["room_id"] for c in counts}


async def test_the_rows_go_with_their_room_and_object(async_client, db_session):
    t = await owner(async_client)
    project, [room] = await world(async_client, t)
    await add(async_client, t, project, room, (await item(async_client, t))["id"])
    assert len((await db_session.execute(select(RoomPoint))).scalars().all()) == 1


# ------------------------------------------------------------------ the estimate

async def test_the_rows_become_the_lines_of_a_draft_estimate_with_the_price_of_that_moment(async_client, db_session):
    t = await owner(async_client)
    project, [bath, kitchen] = await world(async_client, t, ("Łazienka", "Kuchnia"))
    socket = await item(async_client, t, "Gniazdko", "PCS", "ELECTRICAL", "45.00")
    chase = await item(async_client, t, "Bruzda", "LM", "ELECTRICAL", "18.50")
    unpriced = await item(async_client, t, "Punkt wodny", "PCS", "PLUMBING", None)
    await add(async_client, t, project, bath, socket["id"], "12")
    await add(async_client, t, project, bath, chase["id"], "7.5")
    await add(async_client, t, project, kitchen, unpriced["id"], "2")
    estimate = await draft(async_client, t, project)
    r = await async_client.post(f"/api/projects/{project}/estimates/{estimate}/add-points", headers=auth_header(t))
    assert r.status_code == 200 and r.json() == {"added": 3, "already": 0, "skipped": []}
    lines = (await db_session.execute(select(EstimateLine).where(EstimateLine.estimate_id == uuid.UUID(estimate)).order_by(EstimateLine.position))).scalars().all()
    assert [(ln.description, ln.unit.value, ln.quantity, ln.unit_price, ln.amount) for ln in lines] == [
        ("Gniazdko", "PCS", Decimal("12.000"), Decimal("45.00"), Decimal("540.00")),
        ("Bruzda", "LM", Decimal("7.500"), Decimal("18.50"), Decimal("138.75")),
        ("Punkt wodny", "PCS", Decimal("2.000"), None, None),
    ]
    assert {ln.origin for ln in lines} == {LineOrigin.MANUAL} and [str(ln.room_id) for ln in lines] == [bath, bath, kitchen]
    shown = (await async_client.get(f"/api/projects/{project}/estimates/{estimate}", headers=auth_header(t))).json()
    assert shown["total"] == "678.75" and [ln["room_name"] for ln in shown["lines"]] == ["Łazienka", "Łazienka", "Kuchnia"]
    # a later change of the price book does not touch the snapshot
    await async_client.patch(f"/api/price-items/{socket['id']}", json={"price": "99.00"}, headers=auth_header(t))
    again = (await async_client.get(f"/api/projects/{project}/estimates/{estimate}", headers=auth_header(t))).json()
    assert again["total"] == "678.75"


async def test_a_second_addition_adds_nothing_and_a_new_row_is_added_alone(async_client, db_session):
    t = await owner(async_client)
    project, [room] = await world(async_client, t)
    socket = await item(async_client, t)
    await add(async_client, t, project, room, socket["id"], "3")
    estimate = await draft(async_client, t, project)
    url = f"/api/projects/{project}/estimates/{estimate}/add-points"
    assert (await async_client.post(url, headers=auth_header(t))).json()["added"] == 1
    assert (await async_client.post(url, headers=auth_header(t))).json() == {"added": 0, "already": 1, "skipped": []}
    await add(async_client, t, project, room, socket["id"], "5")
    assert (await async_client.post(url, headers=auth_header(t))).json() == {"added": 1, "already": 1, "skipped": []}
    lines = (await db_session.execute(select(EstimateLine).where(EstimateLine.estimate_id == uuid.UUID(estimate)))).scalars().all()
    assert len(lines) == 2


async def test_the_line_the_owner_deleted_comes_back_only_by_asking_again(async_client, db_session):
    t = await owner(async_client)
    project, [room] = await world(async_client, t)
    await add(async_client, t, project, room, (await item(async_client, t))["id"], "3")
    estimate = await draft(async_client, t, project)
    url = f"/api/projects/{project}/estimates/{estimate}/add-points"
    await async_client.post(url, headers=auth_header(t))
    line = (await db_session.execute(select(EstimateLine))).scalar_one()
    assert (await async_client.delete(f"/api/projects/{project}/estimates/{estimate}/lines/{line.id}", headers=auth_header(t))).status_code in (200, 204)
    assert (await async_client.post(url, headers=auth_header(t))).json()["added"] == 1


async def test_a_row_whose_item_has_gone_is_skipped_and_named(async_client, db_session):
    t = await owner(async_client)
    project, [room] = await world(async_client, t)
    socket = await item(async_client, t)
    gone = await item(async_client, t, "Stare")
    bad = (await add(async_client, t, project, room, gone["id"])).json()
    await add(async_client, t, project, room, socket["id"])
    assert (await async_client.post(f"/api/price-items/{gone['id']}/archive", headers=auth_header(t))).status_code == 200
    estimate = await draft(async_client, t, project)
    r = await async_client.post(f"/api/projects/{project}/estimates/{estimate}/add-points", headers=auth_header(t))
    assert r.json() == {"added": 1, "already": 0, "skipped": [{"point_id": bad["id"], "code": "POINT_ITEM_ARCHIVED"}]}
    # the unit of an item changed to an area: the row is skipped with its own code
    other = await item(async_client, t, "Zmienione")
    changed = (await add(async_client, t, project, room, other["id"])).json()
    patched = await async_client.patch(f"/api/price-items/{other['id']}", json={"unit": "M2"}, headers=auth_header(t))
    assert patched.status_code == 200, patched.text
    r = await async_client.post(f"/api/projects/{project}/estimates/{estimate}/add-points", headers=auth_header(t))
    assert {"point_id": changed["id"], "code": "POINT_UNIT_INVALID"} in r.json()["skipped"]


async def test_only_a_draft_of_the_owner_takes_the_rows(async_client, db_session):
    t = await owner(async_client)
    other = await get_token(async_client, OTHER_USER)
    project, [room] = await world(async_client, t)
    await add(async_client, t, project, room, (await item(async_client, t))["id"])
    estimate = await draft(async_client, t, project)
    url = f"/api/projects/{project}/estimates/{estimate}/add-points"
    assert (await async_client.post(url, headers=auth_header(other))).status_code == 404
    assert (await async_client.post(f"/api/projects/{project}/estimates/{uuid.uuid4()}/add-points", headers=auth_header(t))).status_code == 404
    fin = await async_client.post(f"/api/projects/{project}/estimates/{estimate}/finalize", headers=auth_header(t))
    assert fin.status_code == 200, fin.text
    r = await async_client.post(url, headers=auth_header(t))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "ESTIMATE_NOT_DRAFT"


async def test_the_regeneration_of_the_plan_keeps_the_lines_of_the_rows(async_client, db_session):
    t = await owner(async_client)
    project, [room] = await world(async_client, t)
    await add(async_client, t, project, room, (await item(async_client, t))["id"], "3")
    estimate = await draft(async_client, t, project)
    await async_client.post(f"/api/projects/{project}/estimates/{estimate}/add-points", headers=auth_header(t))
    r = await async_client.post(f"/api/projects/{project}/estimates/{estimate}/regenerate", headers=auth_header(t))
    assert r.status_code == 200, r.text
    lines = (await db_session.execute(select(EstimateLine).execution_options(populate_existing=True))).scalars().all()
    assert [ln.description for ln in lines] == ["Gniazdko"] and lines[0].origin == LineOrigin.MANUAL
    assert (await async_client.post(f"/api/projects/{project}/estimates/{estimate}/add-points", headers=auth_header(t))).json() == {"added": 0, "already": 1, "skipped": []}
