"""Stage 14C.5 owner follow-up: cursor guarantee (unsigned, cannot widen
predicates), keyset exactness, archive-view overlap, archived detail,
/api/photo-storage gate and quota boundaries, presign-failure write safety,
attach-to-archived-asset visibility, PATCH idempotency at SQL level."""

import base64
import json
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import event

from app.api.v1.endpoints import photos as photos_endpoint
from app.core.config import settings
from app.domain.exceptions import MediaStorageError, MediaStorageUnavailable
from app.domain.services.media_storage import DisabledMediaStorage
from app.domain.services.photo_query_service import PhotoListFilters, decode_cursor, encode_cursor
from app.models.photo_asset import PhotoAsset, PhotoAssetStatus
from app.models.photo_attachment import PhotoAttachment, PhotoAttachmentContext, PhotoCategory
from tests import test_stage14c5_photos_api as c5
from tests.conftest import test_engine
from tests.test_stage14b4_photo_asset import raw_asset
from tests.test_stage14c4_photos_api import path_for

api = c5.api  # shared fixtures
http = c5.http
upload, row, code = c5.upload, c5.row, c5.code
C = PhotoAttachmentContext
T0 = datetime(2026, 3, 1, 12, 0, 0, 123456, tzinfo=UTC)


@contextmanager
def captured_sql():
    statements: list[str] = []

    def before(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.strip().split()[0].upper() + " " + statement)

    event.listen(test_engine.sync_engine, "before_cursor_execute", before)
    try:
        yield statements
    finally:
        event.remove(test_engine.sync_engine, "before_cursor_execute", before)


def writes(statements: list[str]) -> list[str]:
    return [s for s in statements if s.split()[0] in {"INSERT", "UPDATE", "DELETE"}]


async def add_photo(a, *, owner=None, project=None, status=PhotoAssetStatus.READY, context=C.PROJECT, room=None,
                    position=0, uploaded_at=T0, att_archived=False, asset_archived=False,
                    category=PhotoCategory.GENERAL):
    asset = raw_asset(SimpleNamespace(id=owner or a.me), SimpleNamespace(id=project or a.project), status=status,
                      uploaded_at=uploaded_at, archived_at=T0 if asset_archived else None)
    a.db.add(asset)
    await a.db.flush()
    att = PhotoAttachment(asset_id=asset.id, project_id=project or a.project, context=context, room_id=room,
                          category=category, position=position, archived_at=T0 if att_archived else None)
    a.db.add(att)
    await a.db.commit()
    return asset, att


def ids(resp) -> list[str]:
    return [i["attachment"]["id"] for i in resp.json()["items"]]


def craft(payload: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()


# ---------------------------------------------------------------------------
# 1. Cursor: unsigned, but a crafted valid tuple cannot widen any predicate
# ---------------------------------------------------------------------------


async def test_crafted_valid_cursor_only_moves_inside_the_authorized_filtered_set(api, http):
    _, v1 = await add_photo(api, uploaded_at=T0)
    _, v2 = await add_photo(api, uploaded_at=T0 + timedelta(minutes=1))
    _, v3 = await add_photo(api, uploaded_at=T0 + timedelta(minutes=2))
    # Everything below must stay invisible to the PROJECT / normal-view query.
    await add_photo(api, uploaded_at=T0 - timedelta(days=1), att_archived=True)       # archived attachment
    await add_photo(api, uploaded_at=T0 - timedelta(days=1), asset_archived=True)     # archived asset
    await add_photo(api, uploaded_at=T0 - timedelta(days=1), status=PhotoAssetStatus.PENDING)
    await add_photo(api, uploaded_at=T0 - timedelta(days=1), status=PhotoAssetStatus.FAILED)
    await add_photo(api, uploaded_at=T0 - timedelta(days=1), context=C.ROOM, room=api.room)  # other context
    await add_photo(api, uploaded_at=T0 - timedelta(days=1), project=api.project2)           # other project
    await add_photo(api, uploaded_at=T0 - timedelta(days=1), owner=api.other, project=api.foreign_project)
    authorized = [str(v1.id), str(v2.id), str(v3.id)]
    params = {"context": "PROJECT"}
    first = await http.get(path_for(api.project), params={**params, "limit": 1})
    assert ids(first) == authorized[:1]
    real = json.loads(base64.urlsafe_b64decode(first.json()["next_cursor"] + "=="))
    fingerprint = real["f"]
    # The fingerprint is a plain hash of non-secret values: a client can recompute it.
    me, project = SimpleNamespace(id=api.me), SimpleNamespace(id=api.project)
    assert PhotoListFilters(context=C.PROJECT).fingerprint(me.id, project.id) == fingerprint
    crafted_tuples = [
        {"p": 0, "u": "1970-01-01T00:00:00", "i": str(uuid.UUID(int=0))},          # before everything
        {"p": 0, "u": (T0 - timedelta(days=1)).isoformat(), "i": str(uuid.UUID(int=0))},
        {"p": 0, "u": T0.isoformat(), "i": str(uuid.UUID(int=0))},                  # inside a real boundary
    ]
    for tup in crafted_tuples:
        r = await http.get(path_for(api.project), params={**params, "limit": 100,
                                                           "cursor": craft({"v": 1, **tup, "f": fingerprint})})
        assert r.status_code == 200  # accepted: a valid continuation tuple, NOT detected as tampering
        assert set(ids(r)) <= set(authorized)  # never escapes owner / project / context / view / READY
        assert ids(r) == authorized  # all three start after the crafted point
    after_all = craft({"v": 1, "p": 10**9, "u": T0.isoformat(), "i": str(uuid.UUID(int=0)), "f": fingerprint})
    assert ids(await http.get(path_for(api.project), params={**params, "cursor": after_all})) == []
    # Reusing the same crafted tuple under another view / filter is rejected (fingerprint binding).
    archive_view = await http.get(path_for(api.project), params={"context": "PROJECT", "archived": "true",
                                                                  "cursor": craft({"v": 1, **crafted_tuples[0],
                                                                                   "f": fingerprint})})
    assert archive_view.status_code == 422 and code(archive_view) == "PHOTO_CURSOR_INVALID"


async def test_crafted_cursor_in_archive_view_cannot_reach_active_or_hidden_rows(api, http):
    await add_photo(api)  # active: never in the archive view
    await add_photo(api, status=PhotoAssetStatus.PENDING, att_archived=True)
    _, archived = await add_photo(api, att_archived=True, uploaded_at=T0 + timedelta(minutes=1))
    fp = PhotoListFilters(archived=True).fingerprint(api.me, api.project)
    cursor = craft({"v": 1, "p": 0, "u": "1970-01-01T00:00:00", "i": str(uuid.UUID(int=0)), "f": fp})
    r = await http.get(path_for(api.project), params={"archived": "true", "cursor": cursor})
    assert ids(r) == [str(archived.id)]


# ---------------------------------------------------------------------------
# 2. Keyset exactness
# ---------------------------------------------------------------------------


async def test_keyset_exact_across_ties_and_page_boundaries(api, http):
    rows = []
    # 7 rows sharing position 0 AND uploaded_at (tie broken by id only), 3 sharing position 0 with later
    # uploaded_at values, 4 at position 1 sharing one uploaded_at, all with microsecond timestamps.
    for _ in range(7):
        rows.append(await add_photo(api, position=0, uploaded_at=T0))
    for k in range(3):
        rows.append(await add_photo(api, position=0, uploaded_at=T0 + timedelta(microseconds=k + 1)))
    for _ in range(4):
        rows.append(await add_photo(api, position=1, uploaded_at=T0 - timedelta(days=5)))
    expected = [str(att.id) for asset, att in sorted(rows, key=lambda r: (r[1].position, r[0].uploaded_at,
                                                                           r[1].id))]
    pages, cursor = [], None
    while True:
        params = {"limit": 3, **({"cursor": cursor} if cursor else {})}
        r = await http.get(path_for(api.project), params=params)
        pages.append(ids(r))
        cursor = r.json()["next_cursor"]
        if not cursor:
            break
    assert len(pages) >= 5  # boundaries fall inside the 7-way (position, uploaded_at) tie
    flat = [i for page in pages for i in page]
    assert flat == expected and len(set(flat)) == len(rows)


@pytest.mark.parametrize(
    "value",
    [datetime(2026, 3, 1, 12, 0, 0, 123456, tzinfo=UTC),
     datetime(2026, 3, 1, 14, 0, 0, 1, tzinfo=timezone(timedelta(hours=2))),
     datetime(2026, 3, 1, 12, 0, 0, 999999)],
    ids=["utc", "offset", "naive-sqlite"],
)
def test_cursor_round_trips_uploaded_at_exactly(value):
    att = SimpleNamespace(position=3, id=uuid.uuid4())
    asset = SimpleNamespace(uploaded_at=value)
    decoded = decode_cursor(encode_cursor(att, asset, "f" * 32), "f" * 32)
    assert decoded.uploaded_at == value and decoded.uploaded_at.utcoffset() == value.utcoffset()
    assert (decoded.position, decoded.attachment_id) == (3, att.id)


# ---------------------------------------------------------------------------
# 3. Archive-view overlap matrix
# ---------------------------------------------------------------------------


async def test_archive_overlap_matrix(api, http):
    made = await upload(api, context="PROJECT")
    base = f"/api/projects/{api.project}"
    att, asset = made["attachment"]["id"], made["asset"]["id"]

    async def views():
        normal = ids(await http.get(path_for(api.project)))
        archive = ids(await http.get(path_for(api.project), params={"archived": "true"}))
        return normal.count(att), archive.count(att), len(normal), len(archive)

    await http.post(f"{base}/photo-attachments/{att}/archive")
    await http.post(f"{base}/photos/{asset}/archive")
    assert await views() == (0, 1, 0, 1)  # both archived: once, not duplicated
    await http.post(f"{base}/photo-attachments/{att}/restore")  # A: attachment only
    assert await views() == (0, 1, 0, 1)
    assert (await row(api.db, PhotoAsset, asset)).archived_at is not None  # no cascade
    await http.post(f"{base}/photo-attachments/{att}/archive")  # B: re-archive attachment, restore asset
    await http.post(f"{base}/photos/{asset}/restore")
    assert await views() == (0, 1, 0, 1)
    assert (await row(api.db, PhotoAttachment, att)).archived_at is not None  # no cascade
    await http.post(f"{base}/photo-attachments/{att}/restore")  # C: both restored
    assert await views() == (1, 0, 1, 0)


# ---------------------------------------------------------------------------
# 4. Detail of an archived READY asset
# ---------------------------------------------------------------------------


async def test_archived_asset_detail_lists_every_attachment_once(api, http):
    made = await upload(api)
    base = f"/api/projects/{api.project}"
    asset = made["asset"]["id"]
    second = (await http.post(f"{base}/photos/{asset}/attachments", json={"context": "PROJECT"})).json()
    third = (await http.post(f"{base}/photos/{asset}/attachments",
                             json={"context": "SURFACE", "surface_id": str(api.surface)})).json()
    await http.post(f"{base}/photo-attachments/{second['id']}/archive")
    archived_asset = (await http.post(f"{base}/photos/{asset}/archive")).json()
    first_read = (await http.get(f"{base}/photos/{asset}")).json()
    second_read = (await http.get(f"{base}/photos/{asset}")).json()
    order = [a["id"] for a in first_read["attachments"]]
    assert order == [made["attachment"]["id"], second["id"], third["id"]]
    assert order == [a["id"] for a in second_read["attachments"]]
    assert len(set(order)) == 3
    states = {a["id"]: a["archived_at"] is not None for a in first_read["attachments"]}
    assert states == {made["attachment"]["id"]: False, second["id"]: True, third["id"]: False}
    assert first_read["asset"]["archived_at"] == archived_asset["archived_at"]
    assert first_read["thumbnail_url"] and first_read["display_url"] and first_read["urls_expire_at"]
    api.runtime.storage = DisabledMediaStorage()
    disabled = (await http.get(f"{base}/photos/{asset}")).json()
    assert (disabled["thumbnail_url"], disabled["display_url"], disabled["urls_expire_at"]) == (None, None, None)
    assert [a["id"] for a in disabled["attachments"]] == order


# ---------------------------------------------------------------------------
# 5–6. /api/photo-storage: effective gate and quota boundaries
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("enabled", "backend", "expected_uploads", "expected_media"),
    [(False, "disabled", False, False), (True, "disabled", False, False),
     (False, "s3", False, True), (True, "s3", True, True)],
)
async def test_photo_storage_effective_gate_truth_table(api, http, monkeypatch, enabled, backend,
                                                        expected_uploads, expected_media):
    monkeypatch.setattr(settings, "PHOTO_UPLOADS_ENABLED", enabled)
    monkeypatch.setattr(settings, "MEDIA_STORAGE_BACKEND", backend)

    def no_storage():
        raise AssertionError("the status endpoint must not touch storage")

    monkeypatch.setattr(api.runtime, "storage", SimpleNamespace(presign_get=no_storage, head_object=no_storage))
    data = (await http.get("/api/photo-storage")).json()
    assert (data["uploads_enabled"], data["media_available"]) == (expected_uploads, expected_media)
    # The status agrees with the real upload gate.
    gate = await c5.call(path_for(api.project), token=api.token, body=c5.form(api))
    assert (gate.status != 503 or gate.json()["detail"]["code"] != "PHOTO_UPLOADS_DISABLED") == expected_uploads


@pytest.mark.parametrize(
    ("warning", "cap", "state"),
    [(1231, 2000, "OK"), (1230, 2000, "WARNING"), (1, 1230, "FULL"), (1, 1229, "FULL")],
    ids=["below-warning", "at-warning", "at-cap", "over-cap"],
)
async def test_photo_storage_quota_boundaries(api, http, monkeypatch, warning, cap, state):
    me, project = SimpleNamespace(id=api.me), SimpleNamespace(id=api.project)
    sizes = dict(byte_size=1000, display_byte_size=200, thumbnail_byte_size=30)  # 1230
    api.db.add(raw_asset(me, project, status=PhotoAssetStatus.READY, **sizes))
    api.db.add(raw_asset(SimpleNamespace(id=api.other), SimpleNamespace(id=api.foreign_project),
                         status=PhotoAssetStatus.READY, **sizes))  # another owner: excluded
    await api.db.commit()
    monkeypatch.setattr(settings, "PHOTO_STORAGE_WARNING_BYTES", warning)
    monkeypatch.setattr(settings, "PHOTO_STORAGE_SOFT_CAP_BYTES", cap)
    calls = {"usage": 0, "state": 0}
    real_usage, real_state = photos_endpoint.logical_usage_bytes, photos_endpoint.storage_state

    async def spy_usage(*a, **k):
        calls["usage"] += 1
        return await real_usage(*a, **k)

    def spy_state(*a, **k):
        calls["state"] += 1
        return real_state(*a, **k)

    monkeypatch.setattr(photos_endpoint, "logical_usage_bytes", spy_usage)
    monkeypatch.setattr(photos_endpoint, "storage_state", spy_state)
    data = (await http.get("/api/photo-storage")).json()
    assert (data["used_bytes"], data["state"]) == (1230, state)
    assert calls == {"usage": 1, "state": 1}  # the canonical 14C.3 quota functions, not a copy


async def test_photo_storage_counts_every_reserved_status_and_archived(api, http):
    me, project = SimpleNamespace(id=api.me), SimpleNamespace(id=api.project)
    sizes = dict(byte_size=1000, display_byte_size=200, thumbnail_byte_size=30)
    for status in PhotoAssetStatus:
        api.db.add(raw_asset(me, project, status=status, **sizes))
    api.db.add(raw_asset(me, project, status=PhotoAssetStatus.READY, archived_at=T0, **sizes))
    await api.db.commit()
    assert (await http.get("/api/photo-storage")).json()["used_bytes"] == 4 * 1230


# ---------------------------------------------------------------------------
# 7–8. Presign: overrides and write safety on failure
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("error", "status"),
    [(MediaStorageUnavailable("x"), 503), (MediaStorageError("generic provider failure"), 500)],
    ids=["unavailable", "generic"],
)
async def test_presign_failure_emits_no_write_statement(api, http, monkeypatch, error, status):
    made = await upload(api, extra=[("caption", "opis"), ("category", "DEFECT")])
    base = f"/api/projects/{api.project}"
    await http.post(f"{base}/photo-attachments/{made['attachment']['id']}/archive")
    asset_before = await row(api.db, PhotoAsset, made["asset"]["id"])
    att_before = await row(api.db, PhotoAttachment, made["attachment"]["id"])
    snap = lambda a, t: (a.status, a.archived_at, a.updated_at, t.archived_at, t.caption, t.category,  # noqa: E731
                         t.include_in_report, t.position, t.updated_at)
    before = snap(asset_before, att_before)

    async def failing(key, ttl):
        raise error

    monkeypatch.setattr(api.storage, "presign_get", failing)
    with captured_sql() as statements:
        reads = ((path_for(api.project), {"archived": "true"}), (f"{base}/photos/{made['asset']['id']}", {}))
        for url, params in reads:
            r = await http.get(url, params=params)
            assert r.status_code == status and "generic provider failure" not in r.text
    assert writes(statements) == [] and any(s.startswith("SELECT") for s in statements)
    after = snap(await row(api.db, PhotoAsset, made["asset"]["id"]),
                 await row(api.db, PhotoAttachment, made["attachment"]["id"]))
    assert after == before


# ---------------------------------------------------------------------------
# 9. Attach existing to an archived READY asset
# ---------------------------------------------------------------------------


async def test_attach_to_archived_asset_visibility(api, http, monkeypatch):
    made = await upload(api)
    base = f"/api/projects/{api.project}"
    asset = made["asset"]["id"]
    await http.post(f"{base}/photos/{asset}/archive")
    monkeypatch.setattr(settings, "PHOTO_UPLOADS_ENABLED", False)
    api.storage.puts.clear()
    api.storage.heads.clear()
    new = await http.post(f"{base}/photos/{asset}/attachments", json={"context": "SURFACE",
                                                                      "surface_id": str(api.surface)})
    assert new.status_code == 201 and new.json()["archived_at"] is None
    new_id = new.json()["id"]
    assert new_id not in ids(await http.get(path_for(api.project)))
    archive_ids = ids(await http.get(path_for(api.project), params={"archived": "true"}))
    assert archive_ids.count(new_id) == 1
    await http.post(f"{base}/photos/{asset}/restore")
    normal = ids(await http.get(path_for(api.project)))
    assert normal.count(new_id) == 1 and normal.count(made["attachment"]["id"]) == 1
    assert api.storage.puts == [] and api.storage.heads == []


# ---------------------------------------------------------------------------
# 10. PATCH idempotency at SQL level
# ---------------------------------------------------------------------------


async def test_patch_same_values_emits_no_update_statement(api, http):
    made = await upload(api, extra=[("caption", "same"), ("category", "DEFECT")])
    url = f"/api/projects/{api.project}/photo-attachments/{made['attachment']['id']}"
    body = {"caption": "  same  ", "category": "DEFECT", "include_in_report": False, "position": 0}
    with captured_sql() as statements:
        r = await http.patch(url, json=body)
    assert r.status_code == 200 and writes(statements) == []
    with captured_sql() as statements:
        r = await http.patch(url, json={"position": 7})
    updates = writes(statements)
    assert r.status_code == 200 and len(updates) == 1 and updates[0].startswith("UPDATE UPDATE photo_attachments")
