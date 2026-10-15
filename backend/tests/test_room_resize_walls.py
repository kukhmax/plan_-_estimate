"""Room size correction: the walls generated from the room follow the new size; hand-shaped walls stay untouched."""
from decimal import Decimal

from httpx import AsyncClient

from tests.test_wall_generation import (
    OWNER_USER,
    auth_header,
    create_opening,
    create_project,
    create_room,
    create_wall,
    generate_url,
    get_token,
    walls_url,
)


async def _room(async_client: AsyncClient, token: str, *, generate: bool = True) -> tuple[dict, dict]:
    project = await create_project(async_client, token)
    room = await create_room(
        async_client, token, project["id"], {"name": "Salon", "length": "3.730", "width": "2.320", "height": "2.680"}
    )
    if generate:
        response = await async_client.post(generate_url(project["id"], room["id"]), headers=auth_header(token))
        assert response.status_code == 200, response.text
    return project, room


async def _patch(async_client: AsyncClient, token: str, project: dict, room: dict, payload: dict):
    return await async_client.patch(
        f"/api/projects/{project['id']}/rooms/{room['id']}", json=payload, headers=auth_header(token)
    )


async def _walls(async_client: AsyncClient, token: str, project: dict, room: dict) -> list[dict]:
    response = await async_client.get(walls_url(project["id"], room["id"]), headers=auth_header(token))
    assert response.status_code == 200, response.text
    return [item for item in response.json()["items"] if item["surface_type"] == "WALL"]


async def test_generated_walls_follow_the_corrected_room_size_keeping_their_ids(async_client: AsyncClient) -> None:
    token = await get_token(async_client, OWNER_USER)
    project, room = await _room(async_client, token)
    before = await _walls(async_client, token, project, room)

    response = await _patch(async_client, token, project, room, {"length": "4.000", "width": "3.000", "height": "2.500"})

    assert response.status_code == 200, response.text
    after = await _walls(async_client, token, project, room)
    assert [w["id"] for w in after] == [w["id"] for w in before]
    assert [Decimal(w["width"]) for w in after] == [Decimal(x) for x in ("4.000", "3.000", "4.000", "3.000")]
    assert all(Decimal(w["height"]) == Decimal("2.500") for w in after)
    assert [Decimal(w["gross_area"]) for w in after] == [Decimal(x) for x in ("10.000", "7.500", "10.000", "7.500")]


async def test_a_single_corrected_dimension_updates_only_what_it_touches(async_client: AsyncClient) -> None:
    token = await get_token(async_client, OWNER_USER)
    project, room = await _room(async_client, token)

    response = await _patch(async_client, token, project, room, {"width": "2.000"})

    assert response.status_code == 200, response.text
    walls = await _walls(async_client, token, project, room)
    assert [Decimal(w["width"]) for w in walls] == [Decimal(x) for x in ("3.730", "2.000", "3.730", "2.000")]
    assert all(Decimal(w["height"]) == Decimal("2.680") for w in walls)


async def test_the_floor_base_area_follows_the_new_room_size(async_client: AsyncClient) -> None:
    token = await get_token(async_client, OWNER_USER)
    project, room = await _room(async_client, token)

    await _patch(async_client, token, project, room, {"length": "4.000", "width": "3.000"})

    response = await async_client.get(
        f"/api/projects/{project['id']}/rooms/{room['id']}", headers=auth_header(token)
    )
    assert Decimal(response.json()["calculations"]["floor_area"]) == Decimal("12.000")


async def test_hand_shaped_walls_are_never_touched(async_client: AsyncClient) -> None:
    token = await get_token(async_client, OWNER_USER)
    project, room = await _room(async_client, token, generate=False)
    for index, (name, width) in enumerate((("A", "3.730"), ("B", "2.320"), ("C", "3.730"), ("D", "2.000"))):
        await create_wall(async_client, token, project["id"], room["id"], name=name, width=width, height="2.680", position=index)

    response = await _patch(async_client, token, project, room, {"length": "5.000", "height": "3.000"})

    assert response.status_code == 200, response.text
    walls = await _walls(async_client, token, project, room)
    assert [Decimal(w["width"]) for w in walls] == [Decimal(x) for x in ("3.730", "2.320", "3.730", "2.000")]
    assert all(Decimal(w["height"]) == Decimal("2.680") for w in walls)


async def test_a_room_without_walls_just_changes_its_size(async_client: AsyncClient) -> None:
    token = await get_token(async_client, OWNER_USER)
    project, room = await _room(async_client, token, generate=False)

    response = await _patch(async_client, token, project, room, {"length": "5.000"})

    assert response.status_code == 200, response.text
    assert Decimal(response.json()["length"]) == Decimal("5.000")
    assert await _walls(async_client, token, project, room) == []


async def test_changing_only_the_name_leaves_the_walls_alone(async_client: AsyncClient) -> None:
    token = await get_token(async_client, OWNER_USER)
    project, room = await _room(async_client, token)
    before = await _walls(async_client, token, project, room)

    response = await _patch(async_client, token, project, room, {"name": "Sypialnia"})

    assert response.status_code == 200, response.text
    assert await _walls(async_client, token, project, room) == before


async def test_walls_edited_by_hand_after_generation_no_longer_follow_the_room(async_client: AsyncClient) -> None:
    token = await get_token(async_client, OWNER_USER)
    project, room = await _room(async_client, token)
    first = (await _walls(async_client, token, project, room))[0]
    edit = await async_client.patch(
        f"/api/projects/{project['id']}/rooms/{room['id']}/surfaces/{first['id']}",
        json={"width": "1.000"},
        headers=auth_header(token),
    )
    assert edit.status_code == 200, edit.text

    response = await _patch(async_client, token, project, room, {"length": "6.000"})

    assert response.status_code == 200, response.text
    widths = [Decimal(w["width"]) for w in await _walls(async_client, token, project, room)]
    assert widths == [Decimal(x) for x in ("1.000", "2.320", "3.730", "2.320")]


async def test_openings_that_no_longer_fit_stop_the_change_and_save_nothing(async_client: AsyncClient) -> None:
    token = await get_token(async_client, OWNER_USER)
    project, room = await _room(async_client, token)
    wall = (await _walls(async_client, token, project, room))[1]  # 2.320 x 2.680 = 6.218
    await create_opening(
        async_client, token, project["id"], room["id"], wall["id"], opening_type="DOOR", width="0.900", height="2.000"
    )

    response = await _patch(async_client, token, project, room, {"width": "0.500", "name": "Nowa"})

    assert response.status_code == 422, response.text
    assert "smaller than its openings" in response.json()["detail"]
    current = await async_client.get(f"/api/projects/{project['id']}/rooms/{room['id']}", headers=auth_header(token))
    assert Decimal(current.json()["width"]) == Decimal("2.320")
    assert current.json()["name"] == "Salon"
    widths = [Decimal(w["width"]) for w in await _walls(async_client, token, project, room)]
    assert widths == [Decimal(x) for x in ("3.730", "2.320", "3.730", "2.320")]


async def test_a_foreign_owner_cannot_resize_and_the_walls_stay(async_client: AsyncClient) -> None:
    token = await get_token(async_client, OWNER_USER)
    project, room = await _room(async_client, token)
    foreign = await get_token(
        async_client, {"id": 123123123, "username": "stranger", "first_name": "S", "last_name": "T", "language_code": "pl"}
    )

    response = await _patch(async_client, foreign, project, room, {"length": "9.000"})

    assert response.status_code == 404
    assert Decimal((await _walls(async_client, token, project, room))[0]["width"]) == Decimal("3.730")
