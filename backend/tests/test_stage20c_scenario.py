"""Stage 20C -- the end-to-end scenario of one object, through the HTTP API: the figures are worked out by hand and the API must give the same."""
from decimal import ROUND_HALF_UP, Decimal

import pytest
from sqlalchemy import text

from tests.test_stage15f2_api import use_issuer  # noqa: F401
from tests.test_stage15f2_issuing import Delivery, issuer
from tests.stage20_world import (
    DOOR_H,
    DOOR_W,
    FLOOR_PRICE,
    HEIGHT,
    LENGTH,
    WALL_PRICE,
    WIDTH,
    build_world,
)

D = Decimal


def money(value) -> Decimal:
    return D(value).quantize(D("0.01"), rounding=ROUND_HALF_UP)


@pytest.fixture
async def world(async_client, db_session):
    return await build_world(async_client, db_session)


async def get(client, world, path):
    response = await client.get(path, headers=world.token)
    assert response.status_code == 200, f"{path} -> {response.status_code} {response.text[:300]}"
    return response.json()


async def test_the_areas_are_the_ones_worked_out_by_hand(async_client, world):
    pid, rid = world.first("project_id"), world.first("room_id")
    surfaces = (await get(async_client, world, f"/api/projects/{pid}/rooms/{rid}/surfaces"))["items"]
    walls = {s["name"]: s for s in surfaces if s["surface_type"] == "WALL"}
    gross = [LENGTH * HEIGHT, WIDTH * HEIGHT, LENGTH * HEIGHT, WIDTH * HEIGHT]
    assert [D(w["gross_area"]) for w in walls.values()] == gross
    door = DOOR_W * DOOR_H
    assert D(walls["Wall 1"]["deduction_area"]) == door and D(walls["Wall 1"]["net_area"]) == gross[0] - door
    assert all(D(walls[n]["deduction_area"]) == 0 for n in ("Wall 2", "Wall 3", "Wall 4"))

    summary = await get(async_client, world, f"/api/projects/{pid}/summary")
    assert D(summary["total_wall_area"]) == sum(gross) == D("35")
    assert D(summary["net_wall_area"]) == sum(gross) - door == D("33.11")
    assert D(summary["ceiling_area"]) == LENGTH * WIDTH == D("12")
    assert D(summary["floor_area"]) == LENGTH * WIDTH + 1  # the niche of 1 x 1 m added to the floor
    reveal_length = DOOR_H + DOOR_H + DOOR_W  # left, right, top (the bottom is not a reveal)
    assert D(summary["reveal_total_length"]) == reveal_length == D("5.1")
    assert D(summary["reveal_total_area"]) == reveal_length * D("0.2") == D("1.02")


async def test_the_estimate_is_the_sum_of_its_lines_and_equals_the_hand_calculation(async_client, world):
    pid, eid = world.first("project_id"), world.first("estimate_id")
    estimate = await get(async_client, world, f"/api/projects/{pid}/estimates/{eid}")
    expected_walls = (LENGTH * HEIGHT - DOOR_W * DOOR_H + WIDTH * HEIGHT + LENGTH * HEIGHT + WIDTH * HEIGHT) * WALL_PRICE
    expected_floor = (LENGTH * WIDTH + 1) * FLOOR_PRICE
    manual = D("50.00")
    assert expected_walls == D("662.20") and expected_floor == D("455.00")
    lines = estimate["lines"]
    assert sum(money(D(l["quantity"]) * D(l["unit_price"])) for l in lines) == D(estimate["total"]) == money(expected_walls + expected_floor + manual)
    assert estimate["status"] == "DRAFT" and estimate["version"] == 1
    assert isinstance(estimate["total"], str) and estimate["total"].count(".") == 1  # a decimal text, never a float
    assert any(l["description"] == "Dojazd" and D(l["unit_price"]) == manual for l in lines)


async def test_finalizing_makes_an_estimate_that_later_changes_do_not_touch(async_client, world):
    pid, eid = world.first("project_id"), world.first("estimate_id")
    before = await get(async_client, world, f"/api/projects/{pid}/estimates/{eid}")
    finalized = await async_client.post(f"/api/projects/{pid}/estimates/{eid}/finalize", headers=world.token)
    assert finalized.status_code == 200, finalized.text
    assert finalized.json()["status"] == "FINAL" and finalized.json()["total"] == before["total"]
    line = before["lines"][0]
    refused = await async_client.patch(f"/api/projects/{pid}/estimates/{eid}/lines/{line['id']}", headers=world.token, json={"quantity": "999"})
    assert refused.status_code in (409, 422), refused.text
    # a price of the price book changes: the finalized estimate does not
    item = world.first("price_item_id")
    changed = await async_client.patch(f"/api/price-items/{item}", headers=world.token, json={"price": "99.00"})
    assert changed.status_code == 200
    again = await get(async_client, world, f"/api/projects/{pid}/estimates/{eid}")
    assert again["total"] == before["total"] and again["status"] == "FINAL"
    # the next revision is a fresh DRAFT of the next version
    second = await async_client.post(f"/api/projects/{pid}/estimates/generate", headers=world.token)
    assert second.status_code == 200 and second.json()["version"] == 2 and second.json()["status"] == "DRAFT"
    assert D(second.json()["total"]) != D(before["total"])  # it follows the new price; the manual line is not carried
    listed = await get(async_client, world, f"/api/projects/{pid}/estimates")
    assert {e["version"] for e in listed["items"]} == {1, 2}


async def test_an_estimate_becomes_a_real_pdf_sent_to_the_owner(async_client, world, use_issuer):
    pid, eid = world.first("project_id"), world.first("estimate_id")
    sender = Delivery()
    use_issuer(issuer(delivery=sender))
    response = await async_client.post(f"/api/projects/{pid}/estimates/{eid}/preview-pdf", headers=world.token)
    assert response.status_code == 200, response.text[:300]
    assert response.json()["sent"] is True and response.json()["pages"] >= 1
    assert len(sender.sent) == 1 and sender.sent[0]["pdf"].startswith(b"%PDF")


async def test_the_documents_of_the_object_open_as_drafts_with_their_blockers_named(async_client, world):
    pid = world.first("project_id")
    contract = await get(async_client, world, f"/api/projects/{pid}/contracts/{world.first('contract_id')}")
    assert contract["status"] == "DRAFT" and contract["missing_required"]
    gate = await get(async_client, world, f"/api/projects/{pid}/contracts/{world.first('contract_id')}/gate")
    assert gate["blockers"] if "blockers" in gate else gate
    handover = await get(async_client, world, f"/api/projects/{pid}/handovers/{world.first('handover_id')}")
    assert handover["status"] == "DRAFT" and handover["blockers"]
    # a blocked document is refused and takes no number
    refused = await async_client.post(f"/api/projects/{pid}/contracts/{world.first('contract_id')}/issue", headers=world.token)
    assert refused.status_code in (409, 422) and refused.status_code < 500


async def test_the_object_goes_to_the_archive_and_is_deleted_for_good_with_nothing_left_behind(async_client, db_session, world):
    pid = world.first("project_id")
    h = world.token
    assert (await async_client.post(f"/api/projects/{pid}/archive", headers=h)).status_code == 200
    preview = await async_client.get(f"/api/projects/{pid}/purge-preview", headers=h)
    assert preview.status_code == 200, preview.text
    purged = await async_client.post(f"/api/projects/{pid}/purge", headers=h)
    assert purged.status_code == 200, purged.text[:300]
    assert (await async_client.get(f"/api/projects/{pid}", headers=h)).status_code == 404
    # no table keeps a row of the deleted object (the journal of sent documents is deleted by the owner through its own route)
    tables = (await db_session.execute(text("SELECT name FROM sqlite_master WHERE type = 'table'"))).scalars().all()
    leftovers = {}
    for table in tables:
        columns = [r[1] for r in (await db_session.execute(text(f"PRAGMA table_info({table})"))).all()]
        if "project_id" in columns:
            count = (await db_session.execute(text(f"SELECT count(*) FROM {table} WHERE project_id = :p"), {"p": pid.replace('-', '')})).scalar_one()
            count += (await db_session.execute(text(f"SELECT count(*) FROM {table} WHERE project_id = :p"), {"p": pid})).scalar_one()
            if count:
                leftovers[table] = count
    # the ledger of deleted photo files (backup cleaning) holds no names, and the journal of sent documents is the owner's own record
    assert set(leftovers) <= {"purge_ledger", "issued_documents"}, leftovers
    # the client stays: it is a different record
    assert (await async_client.get(f"/api/clients/{world.first('client_id')}", headers=h)).status_code == 200


SEALED = (
    ("clients", "first_name"), ("clients", "last_name"), ("clients", "phone"), ("clients", "email"), ("clients", "notes"),
    ("projects", "name"), ("projects", "address"), ("project_representatives", "name"), ("project_notes", "body"), ("project_payments", "title"),
)


async def test_with_the_encryption_on_the_database_holds_no_plain_personal_data(async_client, db_session, encryption_on):
    world = await build_world(async_client, db_session, telegram_id=20002)
    for table, column in SEALED:
        values = (await db_session.execute(text(f"SELECT {column} FROM {table}"))).scalars().all()
        assert values, (table, column)
        assert all(str(v).startswith("enc1:") for v in values if v is not None), (table, column)
    # and the application still shows the people their own words
    pid = world.first("project_id")
    project = await get(async_client, world, f"/api/projects/{pid}")
    assert project["name"] == "Mieszkanie Nowaków" and project["address"] == "ul. Długa 5/12"
    client_row = await get(async_client, world, f"/api/clients/{world.first('client_id')}")
    assert client_row["last_name"] == "Nowak" and client_row["notes"] == "Klucze u sąsiada"
