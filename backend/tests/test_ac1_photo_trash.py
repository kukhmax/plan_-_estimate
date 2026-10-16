"""Archive cleanup AC-1 -- the trash of archived photos (HTTP over the real photo routes, in-memory storage).

Nothing is deleted: the trash is a state of the archive. The files stay, an active photo cannot be trashed, the archive view
no longer shows what is in the trash, the trash view shows only that, and "restore" works from the trash too.
"""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.photo_asset import PhotoAsset
from app.models.photo_attachment import PhotoAttachment
from tests import test_stage14c4_photos_api as c4
from tests.test_stage14c4_photos_api import path_for
from tests.test_stage14c5_photos_api import code, row, upload

api = c4.api


@pytest.fixture
async def http(api):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {api.token}"
        yield client


def base_of(a) -> str:
    return f"/api/projects/{a.project}"


async def ids(http, a, **params) -> list[str]:
    response = await http.get(path_for(a.project), params=params)
    assert response.status_code == 200, response.text
    return [item["attachment"]["id"] for item in response.json()["items"]]


async def test_an_active_photo_cannot_be_trashed(api, http):
    made = await upload(api)
    att_id = made["attachment"]["id"]
    response = await http.post(f"{base_of(api)}/photo-attachments/{att_id}/trash")
    assert response.status_code == 409 and code(response) == "PHOTO_ATTACHMENT_NOT_ARCHIVED"
    assert (await row(api.db, PhotoAttachment, att_id)).trashed_at is None
    assert await ids(http, api) == [att_id]


async def test_trash_moves_an_archived_photo_between_the_views_and_deletes_nothing(api, http):
    made = await upload(api)
    base = base_of(api)
    att_id, asset_id = made["attachment"]["id"], made["asset"]["id"]
    keys_before = api.storage.keys()
    await http.post(f"{base}/photo-attachments/{att_id}/archive")
    assert await ids(http, api, archived="true") == [att_id] and await ids(http, api, trashed="true") == []

    first = (await http.post(f"{base}/photo-attachments/{att_id}/trash")).json()
    again = (await http.post(f"{base}/photo-attachments/{att_id}/trash")).json()
    assert first["trashed_at"] and first["trashed_at"] == again["trashed_at"] and first["archived_at"]
    assert await ids(http, api) == []
    assert await ids(http, api, archived="true") == []  # the archive view leaves the trash out
    assert await ids(http, api, trashed="true") == [att_id]

    # nothing was deleted: the row, the asset and every object stay
    assert api.storage.keys() == keys_before
    asset = await row(api.db, PhotoAsset, asset_id)
    assert asset.archived_at is None and (await row(api.db, PhotoAttachment, att_id)).trashed_at is not None


async def test_untrash_returns_the_photo_to_the_archive_and_is_idempotent(api, http):
    made = await upload(api)
    base, att_id = base_of(api), made["attachment"]["id"]
    await http.post(f"{base}/photo-attachments/{att_id}/archive")
    await http.post(f"{base}/photo-attachments/{att_id}/trash")
    out = (await http.post(f"{base}/photo-attachments/{att_id}/untrash")).json()
    assert out["trashed_at"] is None and out["archived_at"] is not None
    assert (await http.post(f"{base}/photo-attachments/{att_id}/untrash")).json()["trashed_at"] is None
    assert await ids(http, api, archived="true") == [att_id] and await ids(http, api, trashed="true") == []


async def test_restore_from_the_trash_goes_straight_to_the_active_photos(api, http):
    made = await upload(api)
    base, att_id = base_of(api), made["attachment"]["id"]
    await http.post(f"{base}/photo-attachments/{att_id}/archive")
    await http.post(f"{base}/photo-attachments/{att_id}/trash")
    restored = (await http.post(f"{base}/photo-attachments/{att_id}/restore")).json()
    assert restored["archived_at"] is None and restored["trashed_at"] is None
    assert await ids(http, api) == [att_id] and await ids(http, api, trashed="true") == []


async def test_archive_of_a_trashed_photo_keeps_it_in_the_trash(api, http):
    made = await upload(api)
    base, att_id = base_of(api), made["attachment"]["id"]
    await http.post(f"{base}/photo-attachments/{att_id}/archive")
    await http.post(f"{base}/photo-attachments/{att_id}/trash")
    again = (await http.post(f"{base}/photo-attachments/{att_id}/archive")).json()
    assert again["trashed_at"] is not None


async def test_the_views_archived_and_trashed_are_exclusive(api, http):
    response = await http.get(path_for(api.project), params={"archived": "true", "trashed": "true"})
    assert response.status_code == 422 and code(response) == "PHOTO_ATTACHMENT_INVALID"


async def test_other_attachments_of_the_same_photo_are_not_touched(api, http):
    made = await upload(api)
    base = base_of(api)
    asset_id, att_id = made["asset"]["id"], made["attachment"]["id"]
    other = (await http.post(f"{base}/photos/{asset_id}/attachments", json={"context": "PROJECT"})).json()
    await http.post(f"{base}/photo-attachments/{att_id}/archive")
    await http.post(f"{base}/photo-attachments/{att_id}/trash")
    assert (await row(api.db, PhotoAttachment, other["id"])).trashed_at is None
    assert await ids(http, api) == [other["id"]]


async def test_a_photo_of_another_owner_or_project_is_not_found(api, http):
    made = await upload(api)
    att_id = made["attachment"]["id"]
    for path in (f"/api/projects/{uuid.uuid4()}/photo-attachments/{att_id}/trash",
                 f"{base_of(api)}/photo-attachments/{uuid.uuid4()}/trash",
                 f"{base_of(api)}/photo-attachments/{uuid.uuid4()}/untrash"):
        response = await http.post(path)
        assert response.status_code == 404, path
