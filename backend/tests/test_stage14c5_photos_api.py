"""Stage 14C.5 — photo reads, signed links, metadata, archive / restore,
attach-existing and /api/photo-storage (HTTP)
(docs/STAGE_14C_MEDIA_API_CONTRACT.md §11c, §15–§18, §21).

Photos are created through the real 14C.4 upload endpoint (InMemory storage);
JSON routes are called with httpx over ASGI.
"""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.core.config import settings
from app.domain.exceptions import MediaStorageMisconfigured, MediaStorageUnavailable
from app.domain.services.media_storage import DisabledMediaStorage
from app.main import app
from app.models.opening import Opening
from app.models.photo_asset import PhotoAsset, PhotoAssetStatus
from app.models.photo_attachment import PhotoAttachment, PhotoAttachmentContext, PhotoCategory
from app.models.project import Project
from app.models.room import Room
from app.models.surface import Surface
from tests import test_stage14c4_photos_api as c4
from tests.test_stage14b4_photo_asset import raw_asset
from tests.test_stage14b_media_storage import make_s3
from tests.test_stage14c4_photos_api import call, form, image_bytes, path_for

api = c4.api  # shared pytest fixture (settings: uploads on, s3; InMemory recording storage)


@pytest.fixture
async def http(api):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {api.token}"
        yield client


async def upload(a, *, context="ROOM", target=None, upload_id=None, extra=(), project=None, token=None) -> dict:
    if target is None and context != "ROOM":
        target = {"PROJECT": None, "SURFACE": ("surface_id", str(a.surface)),
                  "OPENING": ("opening_id", str(a.opening))}[context]
        if target is None:
            target = ("caption", "")  # no target id for PROJECT
    c = await call(path_for(project or a.project), token=token or a.token,
                   body=form(a, upload_id=upload_id, context=context, target=target, extra=extra))
    assert c.status == 201, c.body
    return c.json()


async def counts(db) -> tuple[int, int]:
    a = (await db.execute(select(func.count()).select_from(PhotoAsset))).scalar_one()
    b = (await db.execute(select(func.count()).select_from(PhotoAttachment))).scalar_one()
    return a, b


async def row(db, model, row_id):
    return await db.get(model, uuid.UUID(str(row_id)), populate_existing=True)


def code(r) -> str:
    return r.json()["detail"]["code"]


def assert_no_leaks(r, *assets: PhotoAsset) -> None:
    raw = r.text
    assert '"sha256"' not in raw and "storage_key" not in raw and "/original." not in raw
    for asset in assets:
        assert asset.sha256 not in raw and asset.storage_key_original not in raw


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


async def test_list_all_contexts_with_thumbnail_only(api, http):
    made = [await upload(api, context=c) for c in ("PROJECT", "ROOM", "SURFACE", "OPENING")]
    r = await http.get(path_for(api.project))
    assert r.status_code == 200
    data = r.json()
    assert [i["attachment"]["id"] for i in data["items"]] == [m["attachment"]["id"] for m in made]
    for item in data["items"]:
        assert set(item) == {"attachment", "asset", "thumbnail_url"}
        assert item["thumbnail_url"].startswith("memory://media/") and "/thumb.jpg" in item["thumbnail_url"]
    assert data["next_cursor"] is None and data["urls_expire_at"]
    assets = [await row(api.db, PhotoAsset, m["asset"]["id"]) for m in made]
    assert_no_leaks(r, *assets)


@pytest.mark.parametrize(
    ("context", "param"),
    [("PROJECT", None), ("ROOM", "room_id"), ("SURFACE", "surface_id"), ("OPENING", "opening_id")],
)
async def test_list_filters_by_context(api, http, context, param):
    target = await upload(api, context=context)
    await upload(api, context="ROOM" if context != "ROOM" else "PROJECT")
    params = {"context": context}
    if param:
        params[param] = str(getattr(api, param.removesuffix("_id")))
    r = await http.get(path_for(api.project), params=params)
    assert r.status_code == 200
    assert [i["attachment"]["id"] for i in r.json()["items"]] == [target["attachment"]["id"]]


async def test_list_category_and_report_filters(api, http):
    hit = await upload(api, extra=[("category", "DEFECT"), ("include_in_report", "true")])
    await upload(api)
    for params in ({"category": "DEFECT"}, {"include_in_report": "true"}):
        r = await http.get(path_for(api.project), params=params)
        assert [i["attachment"]["id"] for i in r.json()["items"]] == [hit["attachment"]["id"]]


@pytest.mark.parametrize(
    ("params", "status", "expected_code"),
    [
        ({"context": "WORK"}, 422, "PHOTO_CONTEXT_NOT_SUPPORTED"),
        ({"context": "ROOM"}, 422, "PHOTO_ATTACHMENT_INVALID"),
        ({"room_id": str(uuid.uuid4())}, 422, "PHOTO_ATTACHMENT_INVALID"),
        ({"context": "ROOM", "room_id": "FOREIGN"}, 404, "ROOM_NOT_FOUND"),
        ({"context": "ROOM", "room_id": str(uuid.uuid4())}, 404, "ROOM_NOT_FOUND"),
        ({"cursor": "%%bad%%"}, 422, "PHOTO_CURSOR_INVALID"),
    ],
    ids=["inspection", "room-no-id", "id-no-context", "foreign-room", "missing-room", "bad-cursor"],
)
async def test_list_filter_errors(api, http, params, status, expected_code):
    if params.get("room_id") == "FOREIGN":
        params = {**params, "room_id": str(api.foreign_room)}
    r = await http.get(path_for(api.project), params=params)
    assert r.status_code == status and code(r) == expected_code


@pytest.mark.parametrize("params", [{"limit": "101"}, {"limit": "0"}, {"context": "GALLERY"}, {"archived": "maybe"}])
async def test_list_query_type_errors_are_422(api, http, params):
    r = await http.get(path_for(api.project), params=params)
    assert r.status_code == 422


async def test_foreign_or_missing_project_is_404(api, http):
    for project in (api.foreign_project, uuid.uuid4()):
        r = await http.get(path_for(project))
        assert r.status_code == 404 and code(r) == "PROJECT_NOT_FOUND"


async def seed(a, n: int, *, positions=None) -> list[uuid.UUID]:
    """n READY assets with one PROJECT attachment each, inserted directly."""
    me = SimpleNamespace(id=a.me)
    project = SimpleNamespace(id=a.project)
    out = []
    for i in range(n):
        asset = raw_asset(me, project, status=PhotoAssetStatus.READY,
                          uploaded_at=datetime(2026, 1, 1, 0, i % 7, tzinfo=UTC))
        a.db.add(asset)
        await a.db.flush()
        att = PhotoAttachment(asset_id=asset.id, project_id=a.project, context=PhotoAttachmentContext.PROJECT,
                              category=PhotoCategory.GENERAL, position=(positions or [0] * n)[i])
        a.db.add(att)
        out.append(att)
    await a.db.commit()
    return [att.id for att in out]


async def test_default_limit_30_and_max_100(api, http):
    await seed(api, 101)
    first = await http.get(path_for(api.project))
    assert len(first.json()["items"]) == 30 and first.json()["next_cursor"]
    hundred = await http.get(path_for(api.project), params={"limit": 100})
    assert len(hundred.json()["items"]) == 100 and hundred.json()["next_cursor"]


async def test_pages_traverse_without_gaps_or_duplicates(api, http):
    await seed(api, 23, positions=[i % 3 for i in range(23)])
    full_page = (await http.get(path_for(api.project), params={"limit": 100})).json()
    full = [i["attachment"]["id"] for i in full_page["items"]]
    seen, cursor = [], None
    while True:
        params = {"limit": 5, **({"cursor": cursor} if cursor else {})}
        data = (await http.get(path_for(api.project), params=params)).json()
        seen += [i["attachment"]["id"] for i in data["items"]]
        cursor = data["next_cursor"]
        if not cursor:
            break
    assert seen == full and len(set(seen)) == 23


async def test_cursor_from_one_filter_set_is_rejected_for_another(api, http):
    await seed(api, 3)
    cursor = (await http.get(path_for(api.project), params={"limit": 1})).json()["next_cursor"]
    for params in ({"archived": "true"}, {"category": "BEFORE"}, {"context": "PROJECT"}):
        r = await http.get(path_for(api.project), params={**params, "cursor": cursor})
        assert r.status_code == 422 and code(r) == "PHOTO_CURSOR_INVALID"
    r = await http.get(path_for(api.project2), params={"cursor": cursor})
    assert r.status_code == 422 and code(r) == "PHOTO_CURSOR_INVALID"
    corrupted = cursor[:-2] + ("A" if cursor[-2] != "A" else "B") + cursor[-1]  # breaks the encoding (malformed)
    r = await http.get(path_for(api.project), params={"cursor": corrupted})
    assert r.status_code == 422 and code(r) == "PHOTO_CURSOR_INVALID"


async def test_position_is_the_first_sort_key(api, http):
    a = await upload(api)
    b = await upload(api)
    assert (await http.patch(f"/api/projects/{api.project}/photo-attachments/{a['attachment']['id']}",
                             json={"position": 5})).status_code == 200
    ordered = [i["attachment"]["id"] for i in (await http.get(path_for(api.project))).json()["items"]]
    assert ordered == [b["attachment"]["id"], a["attachment"]["id"]]


# ---------------------------------------------------------------------------
# Hidden statuses, corrupted rows, archived parents
# ---------------------------------------------------------------------------


async def hidden_asset(a, status: PhotoAssetStatus) -> tuple[PhotoAsset, PhotoAttachment]:
    asset = raw_asset(SimpleNamespace(id=a.me), SimpleNamespace(id=a.project), status=status)
    a.db.add(asset)
    await a.db.flush()
    att = PhotoAttachment(asset_id=asset.id, project_id=a.project, context=PhotoAttachmentContext.PROJECT,
                          category=PhotoCategory.GENERAL)
    a.db.add(att)
    await a.db.commit()
    return asset, att


@pytest.mark.parametrize("status", [PhotoAssetStatus.PENDING, PhotoAssetStatus.FAILED])
async def test_pending_and_failed_are_invisible_everywhere(api, http, status):
    asset, att = await hidden_asset(api, status)
    base = f"/api/projects/{api.project}"
    assert (await http.get(path_for(api.project))).json()["items"] == []
    assert (await http.get(path_for(api.project), params={"archived": "true"})).json()["items"] == []
    responses = [
        (await http.get(f"{base}/photos/{asset.id}"), "PHOTO_NOT_FOUND"),
        (await http.post(f"{base}/photos/{asset.id}/archive"), "PHOTO_NOT_FOUND"),
        (await http.post(f"{base}/photos/{asset.id}/restore"), "PHOTO_NOT_FOUND"),
        (await http.post(f"{base}/photos/{asset.id}/attachments", json={"context": "ROOM", "room_id": str(api.room)}),
         "PHOTO_NOT_FOUND"),
        (await http.patch(f"{base}/photo-attachments/{att.id}", json={"caption": "x"}), "PHOTO_ATTACHMENT_NOT_FOUND"),
        (await http.post(f"{base}/photo-attachments/{att.id}/archive"), "PHOTO_ATTACHMENT_NOT_FOUND"),
        (await http.post(f"{base}/photo-attachments/{att.id}/restore"), "PHOTO_ATTACHMENT_NOT_FOUND"),
    ]
    for r, expected in responses:
        assert r.status_code == 404 and code(r) == expected
    db_asset = await row(api.db, PhotoAsset, asset.id)
    assert db_asset.status is status and db_asset.archived_at is None


async def test_corrupted_cross_project_attachment_is_invisible(api, http):
    made = await upload(api)
    rogue = PhotoAttachment(asset_id=uuid.UUID(made["asset"]["id"]), project_id=api.project2,
                            context=PhotoAttachmentContext.PROJECT, category=PhotoCategory.GENERAL)
    api.db.add(rogue)
    await api.db.commit()
    base2 = f"/api/projects/{api.project2}"
    assert (await http.get(path_for(api.project2))).json()["items"] == []
    assert (await http.get(f"{base2}/photos/{made['asset']['id']}")).status_code == 404
    r = await http.patch(f"{base2}/photo-attachments/{rogue.id}", json={"caption": "x"})
    assert r.status_code == 404 and code(r) == "PHOTO_ATTACHMENT_NOT_FOUND"
    detail = (await http.get(f"/api/projects/{api.project}/photos/{made['asset']['id']}")).json()
    assert [a["id"] for a in detail["attachments"]] == [made["attachment"]["id"]]


async def test_foreign_and_random_ids_give_identical_404s(api, http):
    foreign = await upload(api, context="PROJECT", project=api.foreign_project, token=api.other_token,
                           target=("caption", ""))
    base = f"/api/projects/{api.project}"
    for asset_id in (foreign["asset"]["id"], str(uuid.uuid4())):
        r = await http.get(f"{base}/photos/{asset_id}")
        assert r.status_code == 404 and r.json() == {"detail": {"code": "PHOTO_NOT_FOUND",
                                                                 "message": "Photo not found"}}
    for att_id in (foreign["attachment"]["id"], str(uuid.uuid4())):
        r = await http.patch(f"{base}/photo-attachments/{att_id}", json={"caption": "x"})
        assert r.status_code == 404 and code(r) == "PHOTO_ATTACHMENT_NOT_FOUND"
    r = await http.get(f"/api/projects/{api.foreign_project}/photos/{foreign['asset']['id']}")
    assert r.status_code == 404 and code(r) == "PROJECT_NOT_FOUND"


@pytest.mark.parametrize("parent", ["project", "room", "surface", "opening"])
async def test_archived_parents_do_not_block_photo_operations(api, http, parent):
    made = await upload(api, context="OPENING")
    model, key = {"project": (Project, api.project), "room": (Room, api.room),
                  "surface": (Surface, api.surface), "opening": (Opening, api.opening)}[parent]
    obj = await api.db.get(model, key)
    obj.is_archived = True
    await api.db.commit()
    base = f"/api/projects/{api.project}"
    asset_id, att_id = made["asset"]["id"], made["attachment"]["id"]
    listed = await http.get(path_for(api.project), params={"context": "OPENING", "opening_id": str(api.opening)})
    assert [i["attachment"]["id"] for i in listed.json()["items"]] == [att_id]
    assert (await http.get(f"{base}/photos/{asset_id}")).status_code == 200
    assert (await http.patch(f"{base}/photo-attachments/{att_id}", json={"caption": "c"})).status_code == 200
    assert (await http.post(f"{base}/photos/{asset_id}/attachments",
                            json={"context": "SURFACE", "surface_id": str(api.surface)})).status_code == 201
    assert (await http.post(f"{base}/photo-attachments/{att_id}/archive")).status_code == 200
    assert (await http.post(f"{base}/photo-attachments/{att_id}/restore")).status_code == 200
    assert (await http.post(f"{base}/photos/{asset_id}/archive")).status_code == 200
    assert (await http.post(f"{base}/photos/{asset_id}/restore")).status_code == 200


# ---------------------------------------------------------------------------
# Detail and signed URLs
# ---------------------------------------------------------------------------


async def test_detail_returns_asset_all_attachments_and_both_urls(api, http, monkeypatch):
    monkeypatch.setattr(settings, "PHOTO_SIGNED_URL_TTL_SECONDS", 90)
    made = await upload(api)
    base = f"/api/projects/{api.project}"
    extra = (await http.post(f"{base}/photos/{made['asset']['id']}/attachments",
                             json={"context": "PROJECT"})).json()
    await http.post(f"{base}/photo-attachments/{extra['id']}/archive")
    r = await http.get(f"{base}/photos/{made['asset']['id']}")
    data = r.json()
    assert set(data) == {"asset", "attachments", "thumbnail_url", "display_url", "urls_expire_at"}
    assert [(a["id"], a["archived_at"] is not None) for a in data["attachments"]] == [
        (made["attachment"]["id"], False), (extra["id"], True)]
    assert data["thumbnail_url"].endswith("/thumb.jpg?expires=90")
    assert data["display_url"].endswith("/display.jpg?expires=90")
    assert_no_leaks(r, await row(api.db, PhotoAsset, made["asset"]["id"]))


async def test_disabled_storage_returns_metadata_with_null_urls(api, http):
    made = await upload(api)
    api.runtime.storage = DisabledMediaStorage()
    listed = (await http.get(path_for(api.project))).json()
    assert listed["items"][0]["thumbnail_url"] is None and listed["urls_expire_at"] is None
    detail = (await http.get(f"/api/projects/{api.project}/photos/{made['asset']['id']}")).json()
    assert (detail["thumbnail_url"], detail["display_url"], detail["urls_expire_at"]) == (None, None, None)
    assert detail["asset"]["id"] == made["asset"]["id"]


@pytest.mark.parametrize(
    ("error", "status", "expected_code"),
    [(MediaStorageUnavailable("dns failure 10.9.9.9"), 503, "PHOTO_STORAGE_UNAVAILABLE"),
     (MediaStorageMisconfigured("bad key AKIASECRET"), 500, "PHOTO_STORAGE_ERROR")],
)
async def test_presign_failure_on_reads_changes_nothing(api, http, monkeypatch, error, status, expected_code):
    made = await upload(api)
    before = await row(api.db, PhotoAsset, made["asset"]["id"])
    snapshot = (before.status, before.archived_at, before.updated_at)

    async def failing(key, ttl):
        raise error

    monkeypatch.setattr(api.storage, "presign_get", failing)
    for url in (path_for(api.project), f"/api/projects/{api.project}/photos/{made['asset']['id']}"):
        r = await http.get(url)
        assert r.status_code == status and code(r) == expected_code
        assert "10.9.9.9" not in r.text and "AKIASECRET" not in r.text and "retry-after" not in r.headers
    after = await row(api.db, PhotoAsset, made["asset"]["id"])
    assert (after.status, after.archived_at, after.updated_at) == snapshot
    assert await counts(api.db) == (1, 1) and len(api.storage.keys()) == 3


async def test_s3_presign_carries_the_response_overrides():
    storage, stub = make_s3()
    with stub:
        url = await storage.presign_get("photos/v1/x/thumb.jpg", 300)
    query = parse_qs(urlparse(url).query)
    assert query["response-cache-control"] == ["private, max-age=300"]
    assert query["response-content-disposition"] == ["inline"]
    stub.assert_no_pending_responses()  # local signing, no request


class S3PresignStorage(c4.RecordingStorage):
    """Recording InMemory storage whose presign is the real S3 adapter (local signing)."""

    def __init__(self) -> None:
        super().__init__()
        self.s3, self.stub = make_s3()

    async def presign_get(self, key, ttl_seconds):
        return await self.s3.presign_get(key, ttl_seconds)


@pytest.mark.parametrize("ttl", [120, 300])
async def test_upload_list_and_detail_urls_carry_overrides(api, http, monkeypatch, ttl):
    monkeypatch.setattr(settings, "PHOTO_SIGNED_URL_TTL_SECONDS", ttl)
    api.runtime.storage = api.storage = S3PresignStorage()
    made = await upload(api)
    detail = (await http.get(f"/api/projects/{api.project}/photos/{made['asset']['id']}")).json()
    listed = (await http.get(path_for(api.project))).json()
    urls = [made["thumbnail_url"], made["display_url"], detail["thumbnail_url"], detail["display_url"],
            listed["items"][0]["thumbnail_url"]]
    for url in urls:
        query = parse_qs(urlparse(url).query)
        assert query["response-cache-control"] == [f"private, max-age={ttl}"], url
        assert query["response-content-disposition"] == ["inline"]
        assert query["X-Amz-Expires"] == [str(ttl)]
        assert "/original." not in url


# ---------------------------------------------------------------------------
# PATCH metadata
# ---------------------------------------------------------------------------


def patch_url(a, att_id) -> str:
    return f"/api/projects/{a.project}/photo-attachments/{att_id}"


async def test_patch_each_field_and_omitted_fields_unchanged(api, http):
    made = await upload(api, extra=[("caption", "start"), ("category", "BEFORE")])
    att_id = made["attachment"]["id"]
    r = await http.patch(patch_url(api, att_id), json={"include_in_report": True})
    a = r.json()
    assert (a["caption"], a["category"], a["include_in_report"], a["position"]) == ("start", "BEFORE", True, 0)
    a = (await http.patch(patch_url(api, att_id), json={"category": "AFTER", "position": 4})).json()
    assert (a["caption"], a["category"], a["position"]) == ("start", "AFTER", 4)
    a = (await http.patch(patch_url(api, att_id), json={"caption": "  nowy opis  "})).json()
    assert a["caption"] == "nowy opis"
    assert (await http.patch(patch_url(api, att_id), json={"caption": "   "})).json()["caption"] is None
    assert (await http.patch(patch_url(api, att_id), json={"caption": "x"})).json()["caption"] == "x"
    assert (await http.patch(patch_url(api, att_id), json={"caption": None})).json()["caption"] is None
    assert (await http.patch(patch_url(api, att_id), json={"caption": "c" * 1000})).status_code == 200
    padded = (await http.patch(patch_url(api, att_id), json={"caption": "  " + "d" * 1000 + "  "})).json()
    assert padded["caption"] == "d" * 1000


@pytest.mark.parametrize(
    ("body", "status", "expected_code"),
    [
        ({"caption": "c" * 1001}, 422, "PHOTO_ATTACHMENT_INVALID"),
        ({"category": None}, 422, None),
        ({"category": "SELFIE"}, 422, None),
        ({"include_in_report": None}, 422, None),
        ({"include_in_report": "true"}, 422, None),
        ({"position": None}, 422, None),
        ({"position": -1}, 422, "PHOTO_ATTACHMENT_INVALID"),
        ({"position": True}, 422, None),
        ({"position": 1.5}, 422, None),
        ({"asset_id": str(uuid.uuid4())}, 422, None),
        ({"project_id": str(uuid.uuid4())}, 422, None),
        ({"owner_id": str(uuid.uuid4())}, 422, None),
        ({"context": "PROJECT"}, 422, None),
        ({"room_id": str(uuid.uuid4())}, 422, None),
        ({"upload_id": str(uuid.uuid4())}, 422, None),
        ({"storage_key_display": "x"}, 422, None),
        ({"sha256": "ab" * 32}, 422, None),
        ({"width": 1}, 422, None),
        ({"archived_at": None}, 422, None),
    ],
)
async def test_patch_rejections_leave_the_row_unchanged(api, http, body, status, expected_code):
    made = await upload(api, extra=[("caption", "keep")])
    att_id = made["attachment"]["id"]
    before = await row(api.db, PhotoAttachment, att_id)
    snapshot = (before.caption, before.category, before.include_in_report, before.position, before.context,
                before.room_id, before.updated_at)
    r = await http.patch(patch_url(api, att_id), json=body)
    assert r.status_code == status
    if expected_code:
        assert code(r) == expected_code
    after = await row(api.db, PhotoAttachment, att_id)
    assert (after.caption, after.category, after.include_in_report, after.position, after.context,
            after.room_id, after.updated_at) == snapshot


async def test_patch_same_values_is_idempotent_without_update(api, http):
    made = await upload(api, extra=[("caption", "same"), ("category", "DEFECT")])
    att_id = made["attachment"]["id"]
    body = {"caption": "same", "category": "DEFECT", "include_in_report": False, "position": 0}
    first = (await http.patch(patch_url(api, att_id), json=body)).json()
    second = (await http.patch(patch_url(api, att_id), json=body)).json()
    assert first["updated_at"] == second["updated_at"] == made["attachment"]["updated_at"]
    changed = (await http.patch(patch_url(api, att_id), json={"position": 2})).json()
    assert changed["updated_at"] != made["attachment"]["updated_at"]


async def test_patch_allowed_on_archived_attachment_and_archived_asset(api, http):
    made = await upload(api)
    base = f"/api/projects/{api.project}"
    att_id, asset_id = made["attachment"]["id"], made["asset"]["id"]
    await http.post(f"{base}/photo-attachments/{att_id}/archive")
    await http.post(f"{base}/photos/{asset_id}/archive")
    r = await http.patch(patch_url(api, att_id), json={"caption": "w archiwum"})
    assert r.status_code == 200 and r.json()["caption"] == "w archiwum" and r.json()["archived_at"]


async def test_patch_foreign_project_is_404(api, http):
    made = await upload(api)
    r = await http.patch(f"/api/projects/{api.foreign_project}/photo-attachments/{made['attachment']['id']}",
                         json={"caption": "x"})
    assert r.status_code == 404 and code(r) == "PROJECT_NOT_FOUND"


# ---------------------------------------------------------------------------
# Attachment archive / restore
# ---------------------------------------------------------------------------


async def test_attachment_archive_restore_idempotent_and_isolated(api, http):
    made = await upload(api)
    base = f"/api/projects/{api.project}"
    asset_id, att_id = made["asset"]["id"], made["attachment"]["id"]
    other = (await http.post(f"{base}/photos/{asset_id}/attachments", json={"context": "PROJECT"})).json()
    keys_before = api.storage.keys()
    first = (await http.post(f"{base}/photo-attachments/{att_id}/archive")).json()
    again = (await http.post(f"{base}/photo-attachments/{att_id}/archive")).json()
    assert first["archived_at"] and first["archived_at"] == again["archived_at"]
    normal = [i["attachment"]["id"] for i in (await http.get(path_for(api.project))).json()["items"]]
    archive_view = [i["attachment"]["id"] for i in
                    (await http.get(path_for(api.project), params={"archived": "true"})).json()["items"]]
    assert normal == [other["id"]] and archive_view == [att_id]
    asset = await row(api.db, PhotoAsset, asset_id)
    assert asset.archived_at is None and asset.status is PhotoAssetStatus.READY
    assert (await row(api.db, PhotoAttachment, other["id"])).archived_at is None
    assert first["include_in_report"] == made["attachment"]["include_in_report"]
    restored = (await http.post(f"{base}/photo-attachments/{att_id}/restore")).json()
    assert restored["archived_at"] is None
    assert (await http.post(f"{base}/photo-attachments/{att_id}/restore")).json()["archived_at"] is None
    assert api.storage.keys() == keys_before and api.storage.puts.count(asset.storage_key_original) == 1


async def test_attachment_restore_conflicts_with_equivalent_active(api, http):
    made = await upload(api)
    base = f"/api/projects/{api.project}"
    asset_id, att_id = made["asset"]["id"], made["attachment"]["id"]
    await http.post(f"{base}/photo-attachments/{att_id}/archive")
    replacement = await http.post(f"{base}/photos/{asset_id}/attachments", json={"context": "ROOM",
                                                                               "room_id": str(api.room)})
    assert replacement.status_code == 201
    r = await http.post(f"{base}/photo-attachments/{att_id}/restore")
    assert r.status_code == 409 and code(r) == "PHOTO_ATTACHMENT_DUPLICATE"
    assert (await row(api.db, PhotoAttachment, att_id)).archived_at is not None


# ---------------------------------------------------------------------------
# Asset archive / restore
# ---------------------------------------------------------------------------


async def test_asset_archive_restore_is_independent_of_attachments(api, http):
    made = await upload(api)
    base = f"/api/projects/{api.project}"
    asset_id, first_att = made["asset"]["id"], made["attachment"]["id"]
    second = (await http.post(f"{base}/photos/{asset_id}/attachments", json={"context": "PROJECT"})).json()
    await http.post(f"{base}/photo-attachments/{second['id']}/archive")
    keys_before = api.storage.keys()
    archived = (await http.post(f"{base}/photos/{asset_id}/archive")).json()
    assert archived["archived_at"] and archived["status"] == "READY"
    assert (await http.post(f"{base}/photos/{asset_id}/archive")).json()["archived_at"] == archived["archived_at"]
    # no cascade: attachment states exactly as before
    assert (await row(api.db, PhotoAttachment, first_att)).archived_at is None
    assert (await row(api.db, PhotoAttachment, second["id"])).archived_at is not None
    assert (await http.get(path_for(api.project))).json()["items"] == []
    archive_view = [i["attachment"]["id"] for i in
                    (await http.get(path_for(api.project), params={"archived": "true"})).json()["items"]]
    assert sorted(archive_view) == sorted([first_att, second["id"]])
    detail = (await http.get(f"{base}/photos/{asset_id}")).json()
    assert detail["asset"]["archived_at"] and detail["thumbnail_url"] and detail["display_url"]
    restored = (await http.post(f"{base}/photos/{asset_id}/restore")).json()
    assert restored["archived_at"] is None
    assert (await http.post(f"{base}/photos/{asset_id}/restore")).json()["archived_at"] is None
    assert (await row(api.db, PhotoAttachment, first_att)).archived_at is None
    assert (await row(api.db, PhotoAttachment, second["id"])).archived_at is not None  # still archived
    assert [i["attachment"]["id"] for i in (await http.get(path_for(api.project))).json()["items"]] == [first_att]
    assert api.storage.keys() == keys_before


async def test_replay_while_archived_stays_archived(api, http):
    upload_id = str(uuid.uuid4())
    made = await upload(api, upload_id=upload_id)
    base = f"/api/projects/{api.project}"
    await http.post(f"{base}/photo-attachments/{made['attachment']['id']}/archive")
    await http.post(f"{base}/photos/{made['asset']['id']}/archive")
    api.storage.puts.clear()
    replay = await call(path_for(api.project), token=api.token, body=form(api, upload_id=upload_id))
    assert replay.status == 200
    data = replay.json()
    assert data["asset"]["archived_at"] and data["attachment"]["archived_at"]
    assert data["thumbnail_url"] and data["display_url"]
    assert api.storage.puts == [] and await counts(api.db) == (1, 1)
    assert (await http.get(path_for(api.project))).json()["items"] == []


# ---------------------------------------------------------------------------
# Attach existing
# ---------------------------------------------------------------------------


async def test_attach_existing_creates_only_a_db_row(api, http, monkeypatch):
    made = await upload(api)
    monkeypatch.setattr(settings, "PHOTO_UPLOADS_ENABLED", False)  # attach is DB-only
    api.storage.puts.clear()
    base = f"/api/projects/{api.project}/photos/{made['asset']['id']}/attachments"
    r = await http.post(base, json={"context": "SURFACE", "surface_id": str(api.surface), "category": "DEFECT",
                                    "caption": " rysa ", "include_in_report": True})
    assert r.status_code == 201
    att = r.json()
    assert (att["context"], att["surface_id"], att["category"], att["caption"], att["include_in_report"],
            att["position"]) == ("SURFACE", str(api.surface), "DEFECT", "rysa", True, 0)
    assert api.storage.puts == [] and api.storage.heads == [] and await counts(api.db) == (1, 2)
    dup = await http.post(base, json={"context": "SURFACE", "surface_id": str(api.surface)})
    assert dup.status_code == 409 and code(dup) == "PHOTO_ATTACHMENT_DUPLICATE"


@pytest.mark.parametrize(
    ("body_fn", "status", "expected_code"),
    [
        (lambda a: {"context": "ROOM", "room_id": str(a.foreign_room)}, 404, "ROOM_NOT_FOUND"),
        (lambda a: {"context": "WORK"}, 422, "PHOTO_CONTEXT_NOT_SUPPORTED"),
        (lambda a: {"context": "ROOM"}, 422, "PHOTO_ATTACHMENT_INVALID"),
        (lambda a: {"context": "PROJECT", "position": 3}, 422, None),
        (lambda a: {"context": "PROJECT", "asset_id": str(uuid.uuid4())}, 422, None),
        (lambda a: {"context": "PROJECT", "include_in_report": "yes"}, 422, None),
    ],
    ids=["foreign-target", "inspection", "missing-target", "position-not-allowed", "extra-field", "bad-bool"],
)
async def test_attach_existing_rejections(api, http, body_fn, status, expected_code):
    made = await upload(api)
    r = await http.post(f"/api/projects/{api.project}/photos/{made['asset']['id']}/attachments", json=body_fn(api))
    assert r.status_code == status
    if expected_code:
        assert code(r) == expected_code
    assert await counts(api.db) == (1, 1)


async def test_attach_foreign_asset_is_404_and_archived_asset_allowed(api, http):
    foreign = await upload(api, context="PROJECT", project=api.foreign_project, token=api.other_token,
                           target=("caption", ""))
    r = await http.post(f"/api/projects/{api.project}/photos/{foreign['asset']['id']}/attachments",
                        json={"context": "PROJECT"})
    assert r.status_code == 404 and code(r) == "PHOTO_NOT_FOUND"
    mine = await upload(api)
    base = f"/api/projects/{api.project}/photos/{mine['asset']['id']}"
    await http.post(f"{base}/archive")
    assert (await http.post(f"{base}/attachments", json={"context": "PROJECT"})).status_code == 201


# ---------------------------------------------------------------------------
# /api/photo-storage
# ---------------------------------------------------------------------------


async def test_photo_storage_requires_auth(api):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anonymous:
        assert (await anonymous.get("/api/photo-storage")).status_code == 401


async def test_photo_storage_uses_logical_accounting_without_storage_calls(api, http, monkeypatch):
    made = await upload(api)
    me, project = SimpleNamespace(id=api.me), SimpleNamespace(id=api.project)
    extras = [raw_asset(me, project, status=s, byte_size=1000, display_byte_size=200, thumbnail_byte_size=30)
              for s in (PhotoAssetStatus.PENDING, PhotoAssetStatus.FAILED)]
    extras.append(raw_asset(me, project, status=PhotoAssetStatus.READY, byte_size=1000, display_byte_size=200,
                            thumbnail_byte_size=30, archived_at=datetime(2026, 1, 1, tzinfo=UTC)))
    other = raw_asset(SimpleNamespace(id=api.other), SimpleNamespace(id=api.foreign_project),
                      status=PhotoAssetStatus.READY, byte_size=10**9)
    api.db.add_all([*extras, other])
    await api.db.commit()
    first = await row(api.db, PhotoAsset, made["asset"]["id"])
    expected = first.byte_size + first.display_byte_size + first.thumbnail_byte_size + 3 * 1230
    api.storage.puts.clear()
    api.storage.heads.clear()
    calls = []

    async def no_presign(*a):
        calls.append(a)
        raise AssertionError("no storage call expected")

    monkeypatch.setattr(api.storage, "presign_get", no_presign)
    data = (await http.get("/api/photo-storage")).json()
    assert data == {"uploads_enabled": True, "media_available": True, "used_bytes": expected,
                    "warning_bytes": settings.PHOTO_STORAGE_WARNING_BYTES,
                    "soft_cap_bytes": settings.PHOTO_STORAGE_SOFT_CAP_BYTES, "state": "OK"}
    assert calls == [] and api.storage.puts == [] and api.storage.heads == []


@pytest.mark.parametrize(
    ("warning", "cap", "state"), [(10**12, 2 * 10**12, "OK"), (1, 10**12, "WARNING"), (1, 2, "FULL")]
)
async def test_photo_storage_states(api, http, monkeypatch, warning, cap, state):
    await upload(api)
    monkeypatch.setattr(settings, "PHOTO_STORAGE_WARNING_BYTES", warning)
    monkeypatch.setattr(settings, "PHOTO_STORAGE_SOFT_CAP_BYTES", cap)
    assert (await http.get("/api/photo-storage")).json()["state"] == state


@pytest.mark.parametrize(
    ("enabled", "backend", "uploads", "media"),
    [(True, "s3", True, True), (False, "s3", False, True), (False, "disabled", False, False)],
)
async def test_photo_storage_flags(api, http, monkeypatch, enabled, backend, uploads, media):
    monkeypatch.setattr(settings, "PHOTO_UPLOADS_ENABLED", enabled)
    monkeypatch.setattr(settings, "MEDIA_STORAGE_BACKEND", backend)
    data = (await http.get("/api/photo-storage")).json()
    assert (data["uploads_enabled"], data["media_available"], data["used_bytes"]) == (uploads, media, 0)


def test_only_the_project_photo_counts_route_exists():
    # Counts were deferred in 14C (C14) and added in Stage 14E.2: exactly one route, read-only.
    paths = app.openapi()["paths"]
    assert [p for p in paths if "count" in p] == ["/api/projects/{project_id}/photos/counts"]
    assert list(paths["/api/projects/{project_id}/photos/counts"]) == ["get"]
    assert image_bytes  # imported helper kept in use
