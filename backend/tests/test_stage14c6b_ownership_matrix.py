"""Stage 14C.6B — consolidated ownership / information-leak matrix over every
media route (contract §14, §16, §11c). Table-driven: each row is one probe
with its expected status and error code. Every error response must be the
fixed envelope and contain no storage key, sha256, original URL, provider
text or another owner's data."""

import base64
import json
import uuid
from types import SimpleNamespace

import pytest

from app.models.photo_asset import PhotoAsset, PhotoAssetStatus
from app.models.photo_attachment import PhotoAttachment, PhotoAttachmentContext, PhotoCategory
from tests import test_stage14c5_photos_api as c5
from tests.test_stage14b4_photo_asset import raw_asset

api, http = c5.api, c5.http


async def hidden(a, status, *, owner=None, project=None) -> tuple[uuid.UUID, uuid.UUID]:
    asset = raw_asset(SimpleNamespace(id=owner or a.me), SimpleNamespace(id=project or a.project), status=status)
    a.db.add(asset)
    await a.db.flush()
    att = PhotoAttachment(asset_id=asset.id, project_id=project or a.project, context=PhotoAttachmentContext.PROJECT,
                          category=PhotoCategory.GENERAL)
    a.db.add(att)
    await a.db.commit()
    return asset.id, att.id


@pytest.fixture
async def world(api, http):
    own = await c5.upload(api)
    other_project = await c5.upload(api, context="PROJECT", project=api.project2, target=("caption", ""))
    foreign = await c5.upload(api, context="PROJECT", project=api.foreign_project, token=api.other_token,
                              target=("caption", ""))
    pending = await hidden(api, PhotoAssetStatus.PENDING)
    failed = await hidden(api, PhotoAssetStatus.FAILED)
    archived = await c5.upload(api, context="PROJECT", target=("caption", ""))
    await http.post(f"/api/projects/{api.project}/photos/{archived['asset']['id']}/archive")
    # corrupted: attachment row in project2 pointing at an asset of project
    rogue = PhotoAttachment(asset_id=uuid.UUID(own["asset"]["id"]), project_id=api.project2,
                            context=PhotoAttachmentContext.PROJECT, category=PhotoCategory.GENERAL)
    api.db.add(rogue)
    await api.db.commit()
    rogue_id = rogue.id  # capture now: later upload calls roll back the shared test session (F3)
    other_cursor_seed = [await c5.upload(api, context="PROJECT", project=api.foreign_project, token=api.other_token,
                                         target=("caption", "")) for _ in range(2)]
    return SimpleNamespace(own=own, other_project=other_project, foreign=foreign, pending=pending, failed=failed,
                           archived=archived, rogue=rogue_id, other_cursor_seed=other_cursor_seed)


def every_secret(db_assets: list[PhotoAsset]) -> list[str]:
    out = []
    for asset in db_assets:
        out += [asset.sha256, asset.storage_key_original, asset.storage_key_display, asset.storage_key_thumbnail]
    return out


ATT = "photo-attachments"


def rows(a, w) -> list[tuple[str, str, str, dict | None, int, str | None]]:
    p, p2, fp = a.project, a.project2, a.foreign_project
    own_asset, own_att = w.own["asset"]["id"], w.own["attachment"]["id"]
    foreign_asset, foreign_att = w.foreign["asset"]["id"], w.foreign["attachment"]["id"]
    rnd = str(uuid.uuid4())
    pend_asset, pend_att = map(str, w.pending)
    fail_asset, fail_att = map(str, w.failed)
    return [
        # (label, method, url, json body, status, code)
        ("random project list", "GET", f"/api/projects/{rnd}/photos", None, 404, "PROJECT_NOT_FOUND"),
        ("foreign project list", "GET", f"/api/projects/{fp}/photos", None, 404, "PROJECT_NOT_FOUND"),
        ("foreign project detail", "GET", f"/api/projects/{fp}/photos/{foreign_asset}", None, 404, "PROJECT_NOT_FOUND"),
        ("own asset, wrong project", "GET", f"/api/projects/{p2}/photos/{own_asset}", None, 404, "PHOTO_NOT_FOUND"),
        ("foreign asset in own project", "GET", f"/api/projects/{p}/photos/{foreign_asset}", None, 404,
         "PHOTO_NOT_FOUND"),
        ("random asset", "GET", f"/api/projects/{p}/photos/{rnd}", None, 404, "PHOTO_NOT_FOUND"),
        ("pending asset detail", "GET", f"/api/projects/{p}/photos/{pend_asset}", None, 404, "PHOTO_NOT_FOUND"),
        ("failed asset detail", "GET", f"/api/projects/{p}/photos/{fail_asset}", None, 404, "PHOTO_NOT_FOUND"),
        ("pending asset archive", "POST", f"/api/projects/{p}/photos/{pend_asset}/archive", None, 404,
         "PHOTO_NOT_FOUND"),
        ("failed asset restore", "POST", f"/api/projects/{p}/photos/{fail_asset}/restore", None, 404,
         "PHOTO_NOT_FOUND"),
        ("pending attach", "POST", f"/api/projects/{p}/photos/{pend_asset}/attachments", {"context": "PROJECT"}, 404,
         "PHOTO_NOT_FOUND"),
        ("foreign asset attach", "POST", f"/api/projects/{p}/photos/{foreign_asset}/attachments",
         {"context": "PROJECT"}, 404, "PHOTO_NOT_FOUND"),
        ("own attachment, wrong project", "PATCH", f"/api/projects/{p2}/{ATT}/{own_att}", {"caption": "x"}, 404,
         "PHOTO_ATTACHMENT_NOT_FOUND"),
        ("foreign attachment", "PATCH", f"/api/projects/{p}/{ATT}/{foreign_att}", {"caption": "x"}, 404,
         "PHOTO_ATTACHMENT_NOT_FOUND"),
        ("random attachment archive", "POST", f"/api/projects/{p}/{ATT}/{rnd}/archive", None, 404,
         "PHOTO_ATTACHMENT_NOT_FOUND"),
        ("pending attachment restore", "POST", f"/api/projects/{p}/{ATT}/{pend_att}/restore", None, 404,
         "PHOTO_ATTACHMENT_NOT_FOUND"),
        ("failed attachment patch", "PATCH", f"/api/projects/{p}/{ATT}/{fail_att}", {"caption": "x"}, 404,
         "PHOTO_ATTACHMENT_NOT_FOUND"),
        ("corrupted cross-project attachment", "PATCH", f"/api/projects/{p2}/{ATT}/{w.rogue}", {"caption": "x"}, 404,
         "PHOTO_ATTACHMENT_NOT_FOUND"),
        ("foreign room target (list)", "GET", f"/api/projects/{p}/photos?context=ROOM&room_id={a.foreign_room}", None,
         404, "ROOM_NOT_FOUND"),
        ("foreign room target (attach)", "POST", f"/api/projects/{p}/photos/{own_asset}/attachments",
         {"context": "ROOM", "room_id": str(a.foreign_room)}, 404, "ROOM_NOT_FOUND"),
        ("random surface target", "POST", f"/api/projects/{p}/photos/{own_asset}/attachments",
         {"context": "SURFACE", "surface_id": rnd}, 404, "SURFACE_NOT_FOUND"),
        ("random opening target", "GET", f"/api/projects/{p}/photos?context=OPENING&opening_id={rnd}", None, 404,
         "OPENING_NOT_FOUND"),
        ("WORK without its ids (list)", "GET", f"/api/projects/{p}/photos?context=WORK", None, 422,
         "PHOTO_ATTACHMENT_INVALID"),
        ("WORK without its ids (attach)", "POST", f"/api/projects/{p}/photos/{own_asset}/attachments",
         {"context": "WORK"}, 422, "PHOTO_ATTACHMENT_INVALID"),
        ("malformed project uuid", "GET", "/api/projects/not-a-uuid/photos", None, 422, None),
        ("malformed asset uuid", "GET", f"/api/projects/{p}/photos/not-a-uuid", None, 422, None),
        ("malformed attachment uuid", "POST", f"/api/projects/{p}/{ATT}/not-a-uuid/archive", None, 422, None),
    ]


async def test_ownership_and_leak_matrix(api, http, world):
    db_assets = list((await api.db.execute(PhotoAsset.__table__.select())).all())
    secrets = []
    for r in db_assets:
        secrets += [r.sha256, r.storage_key_original, r.storage_key_display, r.storage_key_thumbnail]
    failures = []
    for label, method, url, body, status, code in rows(api, world):
        resp = await http.request(method, url, json=body)
        if resp.status_code != status:
            failures.append(f"{label}: {resp.status_code} != {status} ({resp.text[:120]})")
            continue
        detail = resp.json().get("detail")
        if code is not None and detail != {"code": code, "message": detail.get("message")}:
            failures.append(f"{label}: detail {detail}")
        text = resp.text
        for secret in secrets:
            if secret in text:
                failures.append(f"{label}: leaked internal value")
        if "/original." in text or "Traceback" in text or "botocore" in text:
            failures.append(f"{label}: leaked internals")
    assert failures == []


async def test_identical_404_bodies_for_existing_and_missing(api, http, world):
    p = api.project
    pairs = [
        (f"/api/projects/{p}/photos/{world.foreign['asset']['id']}", f"/api/projects/{p}/photos/{uuid.uuid4()}"),
        (f"/api/projects/{p}/photos/{world.pending[0]}", f"/api/projects/{p}/photos/{uuid.uuid4()}"),
        (f"/api/projects/{api.foreign_project}/photos", f"/api/projects/{uuid.uuid4()}/photos"),
    ]
    for existing, missing in pairs:
        a, b = await http.get(existing), await http.get(missing)
        assert (a.status_code, a.content) == (b.status_code, b.content)


async def test_archived_items_are_visible_only_to_their_owner(api, http, world):
    archived_id = world.archived["asset"]["id"]
    async with c5.AsyncClient(transport=c5.ASGITransport(app=c5.app), base_url="http://t") as other:
        other.headers["Authorization"] = f"Bearer {api.other_token}"
        r = await other.get(f"/api/projects/{api.project}/photos/{archived_id}")
        assert r.status_code == 404 and r.json()["detail"]["code"] == "PROJECT_NOT_FOUND"
    own = await http.get(f"/api/projects/{api.project}/photos/{archived_id}")
    assert own.status_code == 200 and own.json()["asset"]["archived_at"]


async def test_cursors_from_another_owner_project_or_view_are_rejected(api, http, world):
    async with c5.AsyncClient(transport=c5.ASGITransport(app=c5.app), base_url="http://t") as other:
        other.headers["Authorization"] = f"Bearer {api.other_token}"
        foreign_cursor = (await other.get(f"/api/projects/{api.foreign_project}/photos",
                                          params={"limit": 1})).json()["next_cursor"]
    assert foreign_cursor
    # forged: another owner's fingerprint replayed on my project
    r = await http.get(f"/api/projects/{api.project}/photos", params={"cursor": foreign_cursor})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "PHOTO_CURSOR_INVALID"
    await c5.upload(api, context="PROJECT", target=("caption", ""))  # 2 visible items -> a next cursor exists
    own_cursor = (await http.get(f"/api/projects/{api.project}/photos", params={"limit": 1})).json()["next_cursor"]
    assert own_cursor
    for params in ({"cursor": own_cursor, "archived": "true"},):
        r = await http.get(f"/api/projects/{api.project}/photos", params=params)
        assert r.status_code == 422
    r = await http.get(f"/api/projects/{api.project2}/photos", params={"cursor": own_cursor})
    assert r.status_code == 422
    decoded = json.loads(base64.urlsafe_b64decode(own_cursor + "=="))
    assert set(decoded) == {"v", "p", "u", "i", "f"}  # no owner/project ids embedded in clear


async def test_photo_storage_never_reveals_another_owners_usage(api, http, world):
    mine = (await http.get("/api/photo-storage")).json()["used_bytes"]
    me = [r for r in (await api.db.execute(PhotoAsset.__table__.select())).all() if r.owner_id == api.me]
    assert mine == sum(r.byte_size + r.display_byte_size + r.thumbnail_byte_size for r in me)
    others = [r for r in (await api.db.execute(PhotoAsset.__table__.select())).all() if r.owner_id == api.other]
    assert others  # the other owner has usage, and none of it is counted above
    assert every_secret  # helper kept for clarity
