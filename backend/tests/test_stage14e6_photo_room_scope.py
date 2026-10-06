"""Stage 14E.6 — photos of a whole room: `room_totals` in `GET …/photos/counts` and the `in_room_id` list filter.

The owner's model: photos are added on surfaces; the room card (and the room view) show EVERY photo of the room — its own,
those of its surfaces and those of their openings — for viewing and editing. Created through the real upload endpoint
(InMemory storage), second room / surface / opening inserted directly.
"""

import uuid

import pytest

from tests import test_stage14c5_photos_api as c5
from tests.test_stage14c4_photos_api import _make_opening, _make_room, _make_surface, path_for

api = c5.api
http = c5.http
upload, code = c5.upload, c5.code


class Layout:
    """Room 1 (api.room) and a second room of the same project, each with a surface and an opening."""

    def __init__(self, api, room2, surface2, opening2):
        self.api = api
        self.room1, self.surface1, self.opening1 = api.room, api.surface, api.opening
        self.room2, self.surface2, self.opening2 = room2, surface2, opening2


@pytest.fixture
async def layout(api):
    room2 = await _make_room(api.db, api.project, name="Kuchnia")
    surface2 = await _make_surface(api.db, room2.id)
    opening2 = await _make_opening(api.db, surface2.id)
    return Layout(api, room2.id, surface2.id, opening2.id)


async def fill(layout) -> dict[str, list[str]]:
    """Room 1: 1 own + 2 surface + 1 opening = 4. Room 2: 1 + 1 + 1 = 3. Object itself: 1. Returns attachment ids per room."""
    a = layout.api
    made: dict[str, list[str]] = {"r1": [], "r2": [], "project": []}

    async def add(bucket, **kwargs):
        made[bucket].append((await upload(a, **kwargs))["attachment"]["id"])

    await add("r1", context="ROOM", target=("room_id", str(layout.room1)))
    await add("r1", context="SURFACE", target=("surface_id", str(layout.surface1)))
    await add("r1", context="SURFACE", target=("surface_id", str(layout.surface1)))
    await add("r1", context="OPENING", target=("opening_id", str(layout.opening1)))
    await add("r2", context="ROOM", target=("room_id", str(layout.room2)))
    await add("r2", context="SURFACE", target=("surface_id", str(layout.surface2)))
    await add("r2", context="OPENING", target=("opening_id", str(layout.opening2)))
    await add("project", context="PROJECT")
    return made


async def list_ids(http, project, **params) -> list[str]:
    ids: list[str] = []
    cursor = None
    while True:
        r = await http.get(path_for(project), params={**params, "limit": 2, **({"cursor": cursor} if cursor else {})})
        assert r.status_code == 200, r.text
        body = r.json()
        ids.extend(item["attachment"]["id"] for item in body["items"])
        cursor = body["next_cursor"]
        if cursor is None:
            return ids


# ---------------------------------------------------------------------------
# counts.room_totals
# ---------------------------------------------------------------------------


async def test_room_totals_include_surfaces_and_openings_of_the_room(layout, http):
    await fill(layout)
    r = await http.get(f"{path_for(layout.api.project)}/counts")
    assert r.status_code == 200
    body = r.json()
    assert body["room_totals"] == {str(layout.room1): 4, str(layout.room2): 3}
    # the leaf fields keep their meaning
    assert body["rooms"] == {str(layout.room1): 1, str(layout.room2): 1}
    assert body["surfaces"] == {str(layout.surface1): 2, str(layout.surface2): 1}
    assert body["openings"] == {str(layout.opening1): 1, str(layout.opening2): 1}
    assert body["project"] == 1


async def test_room_totals_add_up_to_everything_that_is_not_the_object_itself(layout, http):
    await fill(layout)
    body = (await http.get(f"{path_for(layout.api.project)}/counts")).json()
    leaves = sum(body["rooms"].values()) + sum(body["surfaces"].values()) + sum(body["openings"].values())
    assert sum(body["room_totals"].values()) == leaves


async def test_a_room_without_photos_is_absent_and_an_empty_project_has_none(layout, http):
    body = (await http.get(f"{path_for(layout.api.project)}/counts")).json()
    assert body["room_totals"] == {}
    await upload(layout.api, context="SURFACE", target=("surface_id", str(layout.surface2)))
    body = (await http.get(f"{path_for(layout.api.project)}/counts")).json()
    assert body["room_totals"] == {str(layout.room2): 1}


async def test_archived_attachments_leave_the_room_total_and_come_back_on_restore(layout, http):
    made = await fill(layout)
    base = f"/api/projects/{layout.api.project}"
    target = made["r1"][1]  # a surface photo
    assert (await http.post(f"{base}/photo-attachments/{target}/archive")).status_code == 200
    body = (await http.get(f"{base}/photos/counts")).json()
    assert body["room_totals"][str(layout.room1)] == 3
    assert (await http.post(f"{base}/photo-attachments/{target}/restore")).status_code == 200
    body = (await http.get(f"{base}/photos/counts")).json()
    assert body["room_totals"][str(layout.room1)] == 4


async def test_only_this_users_rooms_are_counted(layout, http):
    await fill(layout)
    other = await _make_room(layout.api.db, layout.api.foreign_project)
    body = (await http.get(f"{path_for(layout.api.project)}/counts")).json()
    assert str(other.id) not in body["room_totals"]


# ---------------------------------------------------------------------------
# list ?in_room_id=
# ---------------------------------------------------------------------------


async def test_in_room_lists_the_room_its_surfaces_and_their_openings_and_nothing_else(layout, http):
    made = await fill(layout)
    assert sorted(await list_ids(http, layout.api.project, in_room_id=str(layout.room1))) == sorted(made["r1"])
    assert sorted(await list_ids(http, layout.api.project, in_room_id=str(layout.room2))) == sorted(made["r2"])


async def test_in_room_matches_the_count_of_the_same_room(layout, http):
    await fill(layout)
    totals = (await http.get(f"{path_for(layout.api.project)}/counts")).json()["room_totals"]
    for room in (layout.room1, layout.room2):
        assert len(await list_ids(http, layout.api.project, in_room_id=str(room))) == totals[str(room)]


async def test_in_room_in_the_archive_view_shows_only_that_rooms_archived_photos(layout, http):
    made = await fill(layout)
    base = f"/api/projects/{layout.api.project}"
    for attachment in (made["r1"][0], made["r2"][0]):
        assert (await http.post(f"{base}/photo-attachments/{attachment}/archive")).status_code == 200
    assert await list_ids(http, layout.api.project, in_room_id=str(layout.room1), archived="true") == [made["r1"][0]]
    assert len(await list_ids(http, layout.api.project, in_room_id=str(layout.room1))) == 3


async def test_in_room_combines_with_category_and_the_report_flag(layout, http):
    made = await fill(layout)
    base = f"/api/projects/{layout.api.project}"
    marked = made["r1"][2]
    assert (await http.patch(f"{base}/photo-attachments/{marked}", json={"category": "DEFECT", "include_in_report": True})).status_code == 200
    assert await list_ids(http, layout.api.project, in_room_id=str(layout.room1), category="DEFECT") == [marked]
    assert await list_ids(http, layout.api.project, in_room_id=str(layout.room1), include_in_report="true") == [marked]


@pytest.mark.parametrize(
    "extra",
    [{"context": "ROOM"}, {"room_id": "R"}, {"surface_id": "S"}, {"opening_id": "O"}],
    ids=["context", "room_id", "surface_id", "opening_id"],
)
async def test_in_room_cannot_be_combined_with_a_single_target_filter(layout, http, extra):
    params = {k: ({"R": str(layout.room1), "S": str(layout.surface1), "O": str(layout.opening1)}.get(v, v)) for k, v in extra.items()}
    r = await http.get(path_for(layout.api.project), params={"in_room_id": str(layout.room1), **params})
    assert r.status_code == 422
    assert code(r) in {"PHOTO_ATTACHMENT_INVALID", "PHOTO_UPLOAD_MALFORMED"}


async def test_in_room_of_a_foreign_missing_or_other_projects_room_is_404(layout, http):
    foreign_room = layout.api.foreign_room
    other_project_room = await _make_room(layout.api.db, layout.api.project2)
    for room in (foreign_room, uuid.uuid4(), other_project_room.id):
        r = await http.get(path_for(layout.api.project), params={"in_room_id": str(room)})
        assert r.status_code == 404, (room, r.text)
        assert code(r) == "ROOM_NOT_FOUND"


async def test_in_room_of_a_foreign_project_is_404(layout, http):
    r = await http.get(path_for(layout.api.foreign_project), params={"in_room_id": str(layout.room1)})
    assert r.status_code == 404
    assert code(r) == "PROJECT_NOT_FOUND"


async def test_a_cursor_belongs_to_its_room_filter(layout, http):
    await fill(layout)
    first = await http.get(path_for(layout.api.project), params={"in_room_id": str(layout.room1), "limit": 1})
    cursor = first.json()["next_cursor"]
    assert cursor
    for params in ({"in_room_id": str(layout.room2)}, {}, {"context": "SURFACE", "surface_id": str(layout.surface1)}):
        r = await http.get(path_for(layout.api.project), params={**params, "limit": 1, "cursor": cursor})
        assert r.status_code == 422, params
        assert code(r) == "PHOTO_CURSOR_INVALID"


async def test_the_room_list_gives_thumbnail_urls_and_no_internal_fields(layout, http):
    await fill(layout)
    r = await http.get(path_for(layout.api.project), params={"in_room_id": str(layout.room1)})
    assert r.status_code == 200
    c5.assert_no_leaks(r)
    assert all(item["thumbnail_url"] for item in r.json()["items"])
