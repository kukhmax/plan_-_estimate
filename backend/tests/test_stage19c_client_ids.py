"""Stage 19C -- an id chosen by the phone: creating under it is allowed and safely repeatable; anything else on that id is a conflict."""
import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient

from tests.test_wall_generation import OWNER_USER, FOREIGN_USER, auth_header, create_project, get_token

ROOM = {"name": "Salon", "length": "5.000", "width": "4.000", "height": "2.700"}


def uid() -> str:
    return str(uuid.uuid4())


async def _setup(async_client: AsyncClient):
    token = await get_token(async_client, OWNER_USER)
    return token, await create_project(async_client, token)


def rooms(project) -> str:
    return f"/api/projects/{project['id']}/rooms"


async def _room(async_client, token, project, **extra):
    response = await async_client.post(rooms(project), json={**ROOM, **extra}, headers=auth_header(token))
    assert response.status_code == 201, response.text
    return response.json()


async def _wall(async_client, token, project, room_id, **extra):
    payload = {"name": "Wall 1", "surface_type": "WALL", "width": "4.000", "height": "2.700", "position": 0, **extra}
    response = await async_client.post(f"{rooms(project)}/{room_id}/surfaces", json=payload, headers=auth_header(token))
    assert response.status_code == 201, response.text
    return response.json()


# --- the id itself ------------------------------------------------------------------------------------------------------------------

async def test_a_room_is_created_under_the_id_of_the_phone(async_client: AsyncClient) -> None:
    token, project = await _setup(async_client)
    room_id = uid()

    room = await _room(async_client, token, project, id=room_id)

    assert room["id"] == room_id
    again = await async_client.get(f"{rooms(project)}/{room_id}", headers=auth_header(token))
    assert again.status_code == 200 and again.json()["name"] == "Salon"


async def test_without_an_id_the_server_still_chooses_one(async_client: AsyncClient) -> None:
    token, project = await _setup(async_client)
    room = await _room(async_client, token, project)
    assert uuid.UUID(room["id"]).version == 4


@pytest.mark.parametrize("bad", ["not-a-uuid", "00000000-0000-0000-0000-000000000000", str(uuid.uuid1()), 5])
async def test_an_id_that_is_not_a_random_uuid_is_refused(async_client: AsyncClient, bad) -> None:
    token, project = await _setup(async_client)
    response = await async_client.post(rooms(project), json={**ROOM, "id": bad}, headers=auth_header(token))
    assert response.status_code == 422


# --- a repeat of the same request ----------------------------------------------------------------------------------------------------

async def test_the_same_request_again_returns_the_same_room_and_makes_no_second_one(async_client: AsyncClient) -> None:
    token, project = await _setup(async_client)
    room_id = uid()
    first = await _room(async_client, token, project, id=room_id)

    second = await _room(async_client, token, project, id=room_id)

    assert second["id"] == first["id"] and second["calculations"] == first["calculations"]
    listed = (await async_client.get(rooms(project), headers=auth_header(token))).json()
    assert [r["id"] for r in listed["items"]] == [room_id]


async def test_a_repeat_does_not_make_a_second_pair_of_floor_and_ceiling(async_client: AsyncClient) -> None:
    token, project = await _setup(async_client)
    room_id = uid()
    await _room(async_client, token, project, id=room_id)
    await _room(async_client, token, project, id=room_id)

    surfaces = (await async_client.get(f"{rooms(project)}/{room_id}/surfaces", headers=auth_header(token))).json()["items"]

    assert sorted(s["surface_type"] for s in surfaces) == ["CEILING", "FLOOR"]


async def test_a_wall_a_rectangle_and_a_note_repeat_safely(async_client: AsyncClient) -> None:
    token, project = await _setup(async_client)
    room = await _room(async_client, token, project)
    wall_id, seg_id, note_id = uid(), uid(), uid()

    for _ in range(2):
        wall = await _wall(async_client, token, project, room["id"], id=wall_id)
        assert wall["id"] == wall_id
        seg = await async_client.post(
            f"{rooms(project)}/{room['id']}/area-segments",
            json={"id": seg_id, "plane": "FLOOR", "operation": "ADD", "width": "1.500", "height": "2.000"},
            headers=auth_header(token),
        )
        assert seg.status_code == 201 and seg.json()["id"] == seg_id
        note = await async_client.post(f"/api/projects/{project['id']}/notes", json={"id": note_id, "body": "  Zadzwonić  "}, headers=auth_header(token))
        assert note.status_code == 201 and note.json()["id"] == note_id and note.json()["body"] == "Zadzwonić"

    walls = [s for s in (await async_client.get(f"{rooms(project)}/{room['id']}/surfaces", headers=auth_header(token))).json()["items"] if s["surface_type"] == "WALL"]
    assert [w["id"] for w in walls] == [wall_id]
    segments = (await async_client.get(f"{rooms(project)}/{room['id']}/area-segments", headers=auth_header(token))).json()["items"]
    assert [s["id"] for s in segments] == [seg_id]
    notes = (await async_client.get(f"/api/projects/{project['id']}/notes", headers=auth_header(token))).json()["items"]
    assert [n["id"] for n in notes] == [note_id]


async def test_an_opening_repeat_is_not_counted_against_the_wall_twice(async_client: AsyncClient) -> None:
    token, project = await _setup(async_client)
    room = await _room(async_client, token, project)
    wall = await _wall(async_client, token, project, room["id"], width="1.000", height="2.200")  # gross 2.200
    opening_id = uid()
    url = f"{rooms(project)}/{room['id']}/surfaces/{wall['id']}/openings"
    body = {"id": opening_id, "opening_type": "DOOR", "width": "0.900", "height": "2.000"}  # 1.800 of 2.200

    first = await async_client.post(url, json=body, headers=auth_header(token))
    second = await async_client.post(url, json=body, headers=auth_header(token))  # a second 1.800 would exceed the wall

    assert first.status_code == 201 and second.status_code == 201
    assert second.json()["id"] == opening_id
    listed = (await async_client.get(url, headers=auth_header(token))).json()
    assert listed["total"] == 1


# --- a conflict ----------------------------------------------------------------------------------------------------------------------

async def test_the_same_id_with_other_content_is_a_conflict_with_a_code(async_client: AsyncClient) -> None:
    token, project = await _setup(async_client)
    room_id = uid()
    await _room(async_client, token, project, id=room_id)

    response = await async_client.post(rooms(project), json={**ROOM, "id": room_id, "name": "Inny"}, headers=auth_header(token))

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "CLIENT_ID_CONFLICT"
    room = (await async_client.get(f"{rooms(project)}/{room_id}", headers=auth_header(token))).json()
    assert room["name"] == "Salon"  # nothing was changed


async def test_the_same_id_with_other_content_is_a_conflict_for_a_wall_too(async_client: AsyncClient) -> None:
    token, project = await _setup(async_client)
    room = await _room(async_client, token, project)
    wall_id = uid()
    await _wall(async_client, token, project, room["id"], id=wall_id)
    response = await async_client.post(
        f"{rooms(project)}/{room['id']}/surfaces",
        json={"id": wall_id, "name": "Wall 1", "surface_type": "WALL", "width": "3.000", "height": "2.700", "position": 0},
        headers=auth_header(token),
    )
    assert response.status_code == 409 and response.json()["detail"]["code"] == "CLIENT_ID_CONFLICT"


async def test_ids_only_have_to_be_free_in_their_own_table(async_client: AsyncClient) -> None:
    token, project = await _setup(async_client)
    room = await _room(async_client, token, project)
    # a wall may carry the id of a room: they are different kinds of record, UUIDv4 makes it a matter of theory
    wall = await _wall(async_client, token, project, room["id"], id=room["id"])
    assert wall["id"] == room["id"]


async def test_another_owner_cannot_take_over_or_probe_an_id(async_client: AsyncClient) -> None:
    token, project = await _setup(async_client)
    room_id = uid()
    await _room(async_client, token, project, id=room_id)
    foreign = await get_token(async_client, FOREIGN_USER)
    other_project = await create_project(async_client, foreign)

    response = await async_client.post(rooms(other_project), json={**ROOM, "id": room_id}, headers=auth_header(foreign))

    assert response.status_code == 409  # taken; and nothing of the first owner is returned
    assert "Salon" not in response.text
    assert (await async_client.get(f"{rooms(project)}/{room_id}", headers=auth_header(token))).json()["project_id"] == project["id"]


async def test_the_same_id_under_another_parent_is_a_conflict(async_client: AsyncClient) -> None:
    token, project = await _setup(async_client)
    other_project = await create_project(async_client, token)
    room_id = uid()
    await _room(async_client, token, project, id=room_id)

    response = await async_client.post(rooms(other_project), json={**ROOM, "id": room_id}, headers=auth_header(token))

    assert response.status_code == 409


async def test_ids_of_a_failed_request_stay_free(async_client: AsyncClient) -> None:
    token, project = await _setup(async_client)
    room = await _room(async_client, token, project)
    wall = await _wall(async_client, token, project, room["id"], width="1.000", height="1.000")  # gross 1.000
    url = f"{rooms(project)}/{room['id']}/surfaces/{wall['id']}/openings"
    opening_id = uid()
    too_big = {"id": opening_id, "opening_type": "DOOR", "width": "2.000", "height": "2.000"}
    assert (await async_client.post(url, json=too_big, headers=auth_header(token))).status_code == 422

    ok = await async_client.post(url, json={**too_big, "width": "0.500", "height": "0.500"}, headers=auth_header(token))

    assert ok.status_code == 201 and ok.json()["id"] == opening_id


def test_the_decimal_of_a_repeat_is_compared_by_value() -> None:
    from app.domain.services.client_ids import _same

    assert _same(Decimal("2.700"), Decimal("2.7")) and _same(Decimal("2.700"), 2.7) and not _same(Decimal("2.7"), Decimal("2.8"))
    assert _same(None, None) and not _same(None, "x")
