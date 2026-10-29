"""UX walk A3: lines added from the rooms keep "do ustalenia" after the owner priced their items -- "Uzupełnij ceny z cennika" fills them (never a typed price)."""
from decimal import Decimal

from httpx import AsyncClient

from tests.test_v2_6_vat import _price, _quick, _signed_in, web  # noqa: F401  (the fixture is used by name)


async def _world(client: AsyncClient, db, unpriced_work: bool = False) -> dict:
    headers = await _signed_in(client, db)
    if not unpriced_work:
        await _price(client, headers)
    made = await _quick(client, headers)
    pid, eid = made["project_id"], made["estimate_id"]
    rooms = (await client.get(f"/api/projects/{pid}/rooms", headers=headers)).json()
    rid = (rooms["items"] if isinstance(rooms, dict) else rooms)[0]["id"]
    assert (await client.post("/api/price-items/points-pack", json={}, headers=headers)).status_code in (200, 201)
    found = (await client.get("/api/price-items", params={"search": "Punkt wodny"}, headers=headers)).json()
    water = next(i for i in (found["items"] if isinstance(found, dict) else found) if i["display_name"] == "Punkt wodny")
    made_point = await client.post(f"/api/projects/{pid}/rooms/{rid}/points", json={"price_item_id": water["id"], "quantity": "4"}, headers=headers)
    assert made_point.status_code == 201, made_point.text
    added = await client.post(f"/api/projects/{pid}/estimates/{eid}/add-points", headers=headers)
    assert added.status_code == 200 and added.json()["added"] == 1, added.text
    return {"headers": headers, "url": f"/api/projects/{pid}/estimates/{eid}", "water": water["id"]}


async def test_a_line_from_a_room_gets_the_price_set_later_in_the_price_book(async_client: AsyncClient, db_session, web):  # noqa: F811
    w = await _world(async_client, db_session)
    before = (await async_client.get(w["url"], headers=w["headers"])).json()
    line = next(ln for ln in before["lines"] if ln["description"] == "Punkt wodny")
    assert line["unit_price"] is None
    total_before = Decimal(before["total"])
    assert (await async_client.patch(f"/api/price-items/{w['water']}", json={"price": "120.00"}, headers=w["headers"])).status_code == 200
    done = await async_client.post(f"{w['url']}/fill-prices", headers=w["headers"])
    assert done.status_code == 200, done.text
    assert done.json() == {"filled": 1, "missing": 0, "missing_planned": 0}
    after = (await async_client.get(w["url"], headers=w["headers"])).json()
    line = next(ln for ln in after["lines"] if ln["description"] == "Punkt wodny")
    assert Decimal(line["unit_price"]) == Decimal("120.00") and Decimal(line["amount"]) == Decimal("480.00")
    assert Decimal(after["total"]) == total_before + Decimal("480.00")
    again = (await async_client.post(f"{w['url']}/fill-prices", headers=w["headers"])).json()
    assert again == {"filled": 0, "missing": 0, "missing_planned": 0}


async def test_an_item_still_without_a_price_stays_missing_and_planned_works_are_counted_apart(async_client: AsyncClient, db_session, web):  # noqa: F811
    w = await _world(async_client, db_session, unpriced_work=True)
    done = (await async_client.post(f"{w['url']}/fill-prices", headers=w["headers"])).json()
    assert done["filled"] == 0 and done["missing"] >= 2 and done["missing_planned"] == done["missing"] - 1


async def test_a_price_the_owner_typed_is_never_replaced(async_client: AsyncClient, db_session, web):  # noqa: F811
    w = await _world(async_client, db_session)
    line = next(ln for ln in (await async_client.get(w["url"], headers=w["headers"])).json()["lines"] if ln["description"] == "Punkt wodny")
    typed = await async_client.patch(f"{w['url']}/lines/{line['id']}", json={"unit_price": "99.00"}, headers=w["headers"])
    assert typed.status_code == 200, typed.text
    await async_client.patch(f"/api/price-items/{w['water']}", json={"price": "120.00"}, headers=w["headers"])
    assert (await async_client.post(f"{w['url']}/fill-prices", headers=w["headers"])).json()["filled"] == 0
    line = next(ln for ln in (await async_client.get(w["url"], headers=w["headers"])).json()["lines"] if ln["description"] == "Punkt wodny")
    assert Decimal(line["unit_price"]) == Decimal("99.00")


async def test_only_a_draft_and_only_the_owner(async_client: AsyncClient, db_session, web):  # noqa: F811
    w = await _world(async_client, db_session)
    stranger = await _signed_in(async_client, db_session, email="obcy@example.pl")
    assert (await async_client.post(f"{w['url']}/fill-prices", headers=stranger)).status_code == 404
    assert (await async_client.post(f"{w['url']}/fill-prices")).status_code == 401
    await async_client.patch(f"/api/price-items/{w['water']}", json={"price": "120.00"}, headers=w["headers"])
    await async_client.post(f"{w['url']}/fill-prices", headers=w["headers"])
    assert (await async_client.post(f"{w['url']}/finalize", headers=w["headers"])).status_code == 200
    assert (await async_client.post(f"{w['url']}/fill-prices", headers=w["headers"])).status_code == 422
