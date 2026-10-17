"""Archive cleanup AC-3a -- the photos of the archive and the trash across all objects (HTTP, in-memory storage).

One list for the owner's archive page: what is in the archive, what is in the trash, with the object and the place of every photo,
the totals of both views, and nothing of another owner.
"""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from tests import test_stage14c4_photos_api as c4
from tests.test_stage14c5_photos_api import upload

api = c4.api


@pytest.fixture
async def http(api):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {api.token}"
        yield client


def base_of(a) -> str:
    return f"/api/projects/{a.project}"


async def archive(http, **params):
    response = await http.get("/api/photos/archive", params=params)
    assert response.status_code == 200, response.text
    return response.json()


async def test_an_empty_archive_is_empty_with_zero_totals(api, http):
    body = await archive(http)
    assert body["items"] == [] and body["archived_total"] == 0 and body["trashed_total"] == 0
    assert body["urls_expire_at"] is None


async def test_an_active_photo_is_in_neither_view(api, http):
    await upload(api)
    for view in ("archived", "trashed"):
        assert (await archive(http, view=view))["items"] == []


async def test_an_archived_photo_is_listed_with_its_object_and_place(api, http):
    made = await upload(api, context="SURFACE")
    att_id = made["attachment"]["id"]
    await http.post(f"{base_of(api)}/photo-attachments/{att_id}/archive")

    body = await archive(http)
    assert [item["attachment"]["id"] for item in body["items"]] == [att_id]
    item = body["items"][0]
    assert item["project_id"] == str(api.project) and item["project_name"]
    assert item["place"]["surface_name"] and item["place"]["surface_type"] and item["place"]["room_name"]
    assert item["thumbnail_url"] and item["asset"]["id"] == made["asset"]["id"]
    assert (body["archived_total"], body["trashed_total"]) == (1, 0)
    assert body["urls_expire_at"] is not None


async def test_an_opening_photo_names_the_opening_its_wall_and_its_room(api, http):
    made = await upload(api, context="OPENING")
    await http.post(f"{base_of(api)}/photo-attachments/{made['attachment']['id']}/archive")
    place = (await archive(http))["items"][0]["place"]
    assert place["opening_type"] and place["surface_name"] and place["room_name"]


async def test_a_project_photo_has_no_place(api, http):
    made = await upload(api, context="PROJECT")
    await http.post(f"{base_of(api)}/photo-attachments/{made['attachment']['id']}/archive")
    place = (await archive(http))["items"][0]["place"]
    assert place == {
        "room_name": None, "surface_name": None, "surface_type": None, "opening_type": None, "opening_name": None,
        "payment_title": None, "payment_kind": None,
    }


async def test_the_trash_view_lists_only_the_trash_and_the_archive_view_leaves_it_out(api, http):
    first = await upload(api, context="SURFACE")
    second = await upload(api, context="ROOM")
    base = base_of(api)
    for made in (first, second):
        await http.post(f"{base}/photo-attachments/{made['attachment']['id']}/archive")
    await http.post(f"{base}/photo-attachments/{second['attachment']['id']}/trash")

    archived = await archive(http, view="archived")
    trashed = await archive(http, view="trashed")
    assert [i["attachment"]["id"] for i in archived["items"]] == [first["attachment"]["id"]]
    assert [i["attachment"]["id"] for i in trashed["items"]] == [second["attachment"]["id"]]
    # the totals of both views come with each answer
    assert (archived["archived_total"], archived["trashed_total"]) == (1, 1)
    assert (trashed["archived_total"], trashed["trashed_total"]) == (1, 1)


async def test_a_photo_leaves_the_list_when_it_is_restored(api, http):
    made = await upload(api)
    base, att_id = base_of(api), made["attachment"]["id"]
    await http.post(f"{base}/photo-attachments/{att_id}/archive")
    assert len((await archive(http))["items"]) == 1
    await http.post(f"{base}/photo-attachments/{att_id}/restore")
    body = await archive(http)
    assert body["items"] == [] and body["archived_total"] == 0


async def test_an_archived_asset_shows_all_its_attachments_like_the_object_list(api, http):
    made = await upload(api)
    await http.post(f"{base_of(api)}/photos/{made['asset']['id']}/archive")
    body = await archive(http)
    assert [i["asset"]["id"] for i in body["items"]] == [made["asset"]["id"]]


async def test_the_limit_cuts_the_list_but_the_totals_stay_whole(api, http):
    base = base_of(api)
    for _ in range(3):
        made = await upload(api, context="PROJECT")
        await http.post(f"{base}/photo-attachments/{made['attachment']['id']}/archive")
    body = await archive(http, limit=2)
    assert len(body["items"]) == 2 and body["archived_total"] == 3


@pytest.mark.parametrize("bad", [{"limit": 0}, {"limit": 101}, {"view": "all"}])
async def test_invalid_parameters_are_rejected(api, http, bad):
    response = await http.get("/api/photos/archive", params=bad)
    assert response.status_code == 422


async def test_another_owners_photos_are_never_listed(api, http):
    foreign = await upload(api, context="PROJECT", project=api.foreign_project, token=api.other_token, extra=())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as other:
        other.headers["Authorization"] = f"Bearer {api.other_token}"
        await other.post(
            f"/api/projects/{api.foreign_project}/photo-attachments/{foreign['attachment']['id']}/archive"
        )
        mine = await other.get("/api/photos/archive")
        assert [i["attachment"]["id"] for i in mine.json()["items"]] == [foreign["attachment"]["id"]]
    body = await archive(http)
    assert body["items"] == [] and body["archived_total"] == 0


async def test_the_list_needs_a_signed_in_user(api):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anonymous:
        response = await anonymous.get("/api/photos/archive")
    assert response.status_code in (401, 403)
