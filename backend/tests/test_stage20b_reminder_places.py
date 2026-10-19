"""Stage 20B finding F1 -- the room and the surface of a reminder must belong to the reminder's own object (the message names them)."""
import pytest

from tests.stage20_world import build_world

ROUTE = "/api/calendar/reminders"


@pytest.fixture
async def world(async_client, db_session):
    return await build_world(async_client, db_session, telegram_id=20010)


async def remind(client, world, **body):
    payload = {"preset": "TOMORROW", "title": "Zadzwonić"} | body
    return await client.post(ROUTE, headers=world.token, json=payload)


async def test_a_reminder_may_name_a_room_and_a_surface_of_its_own_object(async_client, world):
    response = await remind(async_client, world, project_id=world.first("project_id"), room_id=world.first("room_id"), surface_id=world.first("surface_id"))
    assert response.status_code == 201, response.text
    assert response.json()["room_id"] == world.first("room_id")


async def test_a_room_of_another_object_of_the_same_owner_is_refused(async_client, world):
    second = await async_client.post("/api/projects", headers=world.token, json={"name": "Drugi", "address": "ul. C 3", "city": "Łódź", "postal_code": "90-001"})
    response = await remind(async_client, world, project_id=second.json()["id"], room_id=world.first("room_id"))
    assert response.status_code == 422 and response.json()["detail"]["code"] == "ROOM_NOT_IN_PROJECT"


async def test_a_room_without_an_object_is_refused(async_client, world):
    response = await remind(async_client, world, room_id=world.first("room_id"))
    assert response.status_code == 422 and response.json()["detail"]["code"] == "ROOM_NOT_IN_PROJECT"


async def test_a_surface_that_is_not_in_the_room_is_refused(async_client, world):
    pid = world.first("project_id")
    other_room = (await async_client.post(f"/api/projects/{pid}/rooms", headers=world.token, json={"name": "Kuchnia"})).json()
    response = await remind(async_client, world, project_id=pid, room_id=other_room["id"], surface_id=world.first("surface_id"))
    assert response.status_code == 422 and response.json()["detail"]["code"] == "SURFACE_NOT_IN_ROOM"


async def test_a_surface_without_a_room_is_refused(async_client, world):
    response = await remind(async_client, world, project_id=world.first("project_id"), surface_id=world.first("surface_id"))
    assert response.status_code == 422 and response.json()["detail"]["code"] == "SURFACE_NOT_IN_ROOM"


async def test_nothing_is_stored_by_a_refused_reminder(async_client, world):
    await remind(async_client, world, project_id=world.first("project_id"), room_id="00000000-0000-4000-8000-000000000000")
    listed = (await async_client.get(ROUTE, headers=world.token)).json()
    assert all(r["room_id"] != "00000000-0000-4000-8000-000000000000" for r in listed["items"])
