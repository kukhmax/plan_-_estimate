"""UX walk B8-pre (owner 2026-10-29): the order of the rectangles of a floor / ceiling, like the order of the walls."""
from httpx import AsyncClient

from tests.test_area_segments import (
    OTHER_USER,
    VALID_USER,
    auth_header,
    create_project,
    create_room,
    create_segment,
    get_token,
    segments_url,
)


async def _world(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"], length="4.000", width="3.000")
    return token, project["id"], room["id"]


async def _ids(async_client, token, project, room, plane) -> list[str]:
    items = (await async_client.get(segments_url(project, room), params={"plane": plane}, headers=auth_header(token))).json()["items"]
    return [item["id"] for item in items]


def _reorder(async_client, token, project, room, plane, ids):
    return async_client.post(f"{segments_url(project, room)}/reorder", json={"plane": plane, "segment_ids": ids}, headers=auth_header(token))


async def test_the_rectangles_of_a_plane_take_the_order_the_owner_chose(async_client: AsyncClient):
    token, project, room = await _world(async_client)
    a = (await create_segment(async_client, token, project, room, width="1.000", height="1.000", label="a"))["id"]
    b = (await create_segment(async_client, token, project, room, width="2.000", height="1.000", label="b"))["id"]
    c = (await create_segment(async_client, token, project, room, operation="SUBTRACT", width="0.500", height="0.500", label="c"))["id"]
    assert await _ids(async_client, token, project, room, "FLOOR") == [a, b, c]
    done = await _reorder(async_client, token, project, room, "FLOOR", [c, a, b])
    assert done.status_code == 200, done.text
    assert [item["id"] for item in done.json()["items"] if item["plane"] == "FLOOR"] == [c, a, b]
    assert [item["position"] for item in done.json()["items"] if item["plane"] == "FLOOR"] == [0, 1, 2]
    assert "planes" in done.json() and done.json()["total"] == 3
    assert await _ids(async_client, token, project, room, "FLOOR") == [c, a, b]  # kept


async def test_the_other_plane_and_the_areas_are_not_touched(async_client: AsyncClient):
    token, project, room = await _world(async_client)
    f1 = (await create_segment(async_client, token, project, room, plane="FLOOR", width="1.000", height="1.000"))["id"]
    f2 = (await create_segment(async_client, token, project, room, plane="FLOOR", width="2.000", height="1.000"))["id"]
    c1 = (await create_segment(async_client, token, project, room, plane="CEILING", width="1.000", height="1.000"))["id"]
    c2 = (await create_segment(async_client, token, project, room, plane="CEILING", width="2.000", height="1.000"))["id"]
    before = (await async_client.get(segments_url(project, room), headers=auth_header(token))).json()["planes"]
    assert (await _reorder(async_client, token, project, room, "FLOOR", [f2, f1])).status_code == 200
    after = (await async_client.get(segments_url(project, room), headers=auth_header(token))).json()
    assert after["planes"] == before
    assert await _ids(async_client, token, project, room, "CEILING") == [c1, c2]


async def test_a_list_that_is_not_exactly_the_active_rectangles_of_the_plane_is_refused(async_client: AsyncClient):
    token, project, room = await _world(async_client)
    a = (await create_segment(async_client, token, project, room, width="1.000", height="1.000"))["id"]
    b = (await create_segment(async_client, token, project, room, width="2.000", height="1.000"))["id"]
    c = (await create_segment(async_client, token, project, room, width="3.000", height="1.000"))["id"]
    ceiling = (await create_segment(async_client, token, project, room, plane="CEILING", width="1.000", height="1.000"))["id"]
    for ids in ([b, a], [a, b, c, c], [a, b, ceiling], [a, b, "00000000-0000-0000-0000-000000000000"]):
        refused = await _reorder(async_client, token, project, room, "FLOOR", ids)
        assert refused.status_code in (409, 422), (ids, refused.text)
        assert await _ids(async_client, token, project, room, "FLOOR") == [a, b, c]  # nothing moved
    assert (await _reorder(async_client, token, project, room, "FLOOR", [b, a])).json()["detail"]["code"] == "AREA_REORDER_NOT_CURRENT"
    assert (await _reorder(async_client, token, project, room, "FLOOR", [a, a])).json()["detail"]["code"] == "AREA_REORDER_NEED_TWO"
    await async_client.post(f"{segments_url(project, room)}/{c}/archive", headers=auth_header(token))
    assert (await _reorder(async_client, token, project, room, "FLOOR", [b, a])).status_code == 200  # the archived one is not in the order


async def test_the_copy_of_a_rectangle_goes_to_the_end_until_the_order_is_set(async_client: AsyncClient):
    """The screen duplicates by creating the same rectangle and then puts it behind the original with this route."""
    token, project, room = await _world(async_client)
    a = (await create_segment(async_client, token, project, room, width="1.000", height="1.000", position=0))["id"]
    b = (await create_segment(async_client, token, project, room, width="2.000", height="1.000", position=1))["id"]
    copy = (await create_segment(async_client, token, project, room, width="1.000", height="1.000"))["id"]
    assert await _ids(async_client, token, project, room, "FLOOR") == [a, b, copy]
    assert (await _reorder(async_client, token, project, room, "FLOOR", [a, copy, b])).status_code == 200
    assert await _ids(async_client, token, project, room, "FLOOR") == [a, copy, b]


async def test_only_the_owner_reorders(async_client: AsyncClient):
    token, project, room = await _world(async_client)
    a = (await create_segment(async_client, token, project, room, width="1.000", height="1.000"))["id"]
    b = (await create_segment(async_client, token, project, room, width="2.000", height="1.000"))["id"]
    other = await get_token(async_client, OTHER_USER)
    assert (await _reorder(async_client, other, project, room, "FLOOR", [b, a])).status_code == 404
    assert (await async_client.post(f"{segments_url(project, room)}/reorder", json={"plane": "FLOOR", "segment_ids": [b, a]})).status_code == 401
    assert await _ids(async_client, token, project, room, "FLOOR") == [a, b]
    bad = await async_client.post(f"{segments_url(project, room)}/reorder", json={"plane": "WALL", "segment_ids": [a, b]}, headers=auth_header(token))
    assert bad.status_code == 422
