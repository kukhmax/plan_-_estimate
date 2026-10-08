"""Stage 14E.2 — `GET /projects/{p}/photos/counts` and the client-declared capture source
(docs/STAGE_14E_PHOTO_UI_CONTRACT.md §3a, §9; owner decision D11 = A).

Photos are created through the real upload endpoint (InMemory storage) or inserted directly for the
non-READY / archived cases; JSON routes are called with httpx over ASGI.
"""

import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.core.config import settings
from app.domain.exceptions import MediaStorageUnavailable
from app.models.photo_asset import PhotoAsset, PhotoAssetStatus, PhotoCaptureSource
from app.models.photo_attachment import PhotoAttachmentContext as C
from tests import test_stage14c5_followup as fu
from tests import test_stage14c5_photos_api as c5
from tests.test_stage14c4_photos_api import call, form, path_for

api = c5.api  # shared fixtures (uploads on, s3 flag, InMemory recording storage)
http = c5.http
upload, row, code = c5.upload, c5.row, c5.code


def counts_url(project) -> str:
    return f"{path_for(project)}/counts"


# 14F.2 added the inspection-evidence maps, 14H.1 the execution-evidence maps and 14H.5 the per-surface inspection map (empty here: these tests photograph only the four 14C contexts).
EMPTY = {"project": 0, "rooms": {}, "surfaces": {}, "openings": {}, "room_totals": {}, "inspections": {}, "findings": {}, "lineages": {}, "questions": {}, "works": {}, "work_surfaces": {}, "inspection_surfaces": {}}


# ---------------------------------------------------------------------------
# counts
# ---------------------------------------------------------------------------


async def test_empty_project_has_zero_counts(api, http):
    r = await http.get(counts_url(api.project))
    assert r.status_code == 200 and r.json() == EMPTY


async def test_counts_group_by_context_and_target(api, http):
    for _ in range(3):
        await upload(api, context="PROJECT")
    for _ in range(2):
        await upload(api, context="ROOM")
    await upload(api, context="SURFACE")
    await upload(api, context="OPENING")
    r = await http.get(counts_url(api.project))
    assert r.status_code == 200
    assert r.json() == {
        "project": 3,
        "rooms": {str(api.room): 2},
        "surfaces": {str(api.surface): 1},
        "openings": {str(api.opening): 1},
        # Stage 14E.6: the room's own 2 + its surface's 1 + its surface's opening's 1
        "room_totals": {str(api.room): 4},
        "inspections": {},
        "findings": {},
        "lineages": {},
        "questions": {},
        "works": {},
        "work_surfaces": {},
        "inspection_surfaces": {},
    }


async def test_targets_without_photos_are_omitted(api, http):
    await upload(api, context="ROOM")
    data = (await http.get(counts_url(api.project))).json()
    assert data["surfaces"] == {} and data["openings"] == {} and data["project"] == 0


async def test_second_attachment_of_the_same_asset_counts_in_its_own_context(api, http):
    made = await upload(api, context="ROOM")
    base = f"/api/projects/{api.project}"
    r = await http.post(f"{base}/photos/{made['asset']['id']}/attachments", json={"context": "PROJECT"})
    assert r.status_code == 201
    data = (await http.get(counts_url(api.project))).json()
    assert data["project"] == 1 and data["rooms"] == {str(api.room): 1}


@pytest.mark.parametrize("status", [PhotoAssetStatus.PENDING, PhotoAssetStatus.FAILED])
async def test_pending_and_failed_assets_are_never_counted(api, http, status):
    await fu.add_photo(api, status=status)
    await fu.add_photo(api, status=status, context=C.ROOM, room=api.room)
    assert (await http.get(counts_url(api.project))).json() == EMPTY


async def test_archived_attachment_and_archived_asset_are_not_counted_and_return_when_restored(api, http):
    a = await upload(api, context="ROOM")
    b = await upload(api, context="ROOM")
    base = f"/api/projects/{api.project}"
    assert (await http.get(counts_url(api.project))).json()["rooms"] == {str(api.room): 2}

    await http.post(f"{base}/photo-attachments/{a['attachment']['id']}/archive")
    assert (await http.get(counts_url(api.project))).json()["rooms"] == {str(api.room): 1}

    await http.post(f"{base}/photos/{b['asset']['id']}/archive")
    assert (await http.get(counts_url(api.project))).json() == EMPTY

    await http.post(f"{base}/photo-attachments/{a['attachment']['id']}/restore")
    await http.post(f"{base}/photos/{b['asset']['id']}/restore")
    assert (await http.get(counts_url(api.project))).json()["rooms"] == {str(api.room): 2}


async def test_counts_equal_the_visible_list_totals(api, http):
    """The badge number is exactly what the normal list shows for that target."""
    for _ in range(2):
        await upload(api, context="SURFACE")
    await upload(api, context="ROOM")
    shown = (await http.get(path_for(api.project), params={"context": "SURFACE", "surface_id": str(api.surface)}))
    assert len(shown.json()["items"]) == (await http.get(counts_url(api.project))).json()["surfaces"][str(api.surface)]


async def test_other_projects_photos_are_not_counted(api, http):
    await upload(api, context="PROJECT", project=api.project2)
    assert (await http.get(counts_url(api.project))).json() == EMPTY
    assert (await http.get(counts_url(api.project2))).json()["project"] == 1


async def test_foreign_missing_and_unauthenticated(api, http):
    for project in (api.foreign_project, uuid.uuid4()):
        r = await http.get(counts_url(project))
        assert r.status_code == 404 and code(r) == "PROJECT_NOT_FOUND"
    foreign_owner = await http.get(counts_url(api.project), headers={"Authorization": f"Bearer {api.other_token}"})
    assert foreign_owner.status_code == 404 and code(foreign_owner) == "PROJECT_NOT_FOUND"
    anonymous = await http.get(counts_url(api.project), headers={"Authorization": ""})
    assert anonymous.status_code in (401, 403)


async def test_counts_work_with_uploads_disabled_and_do_not_touch_storage(api, http, monkeypatch):
    await upload(api, context="PROJECT")
    monkeypatch.setattr(settings, "PHOTO_UPLOADS_ENABLED", False)
    before = api.storage.keys()
    with fu.captured_sql() as statements:
        r = await http.get(counts_url(api.project))
    assert r.status_code == 200 and r.json()["project"] == 1
    assert api.storage.keys() == before
    assert fu.writes(statements) == []


async def test_counts_use_one_aggregate_query_regardless_of_photo_number(api, http):
    for _ in range(5):
        await upload(api, context="ROOM")
    with fu.captured_sql() as statements:
        await http.get(counts_url(api.project))
    selects = [s for s in statements if s.startswith("SELECT")]
    aggregate = [s for s in selects if "count(" in s.lower() and "photo_attachments" in s]
    assert len(aggregate) == 1 and len(selects) <= 3  # project ownership lookup + one aggregate (+ user lookup)


async def test_counts_route_is_not_swallowed_by_the_asset_detail_route(api, http):
    """`counts` must be matched before `{asset_id}`: a UUID that is not a photo is still a 404 PHOTO_NOT_FOUND."""
    assert (await http.get(counts_url(api.project))).status_code == 200
    r = await http.get(f"{path_for(api.project)}/{uuid.uuid4()}")
    assert r.status_code == 404 and code(r) == "PHOTO_NOT_FOUND"


# ---------------------------------------------------------------------------
# capture source
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("value", ["CAMERA", "GALLERY"])
async def test_declared_source_is_stored_returned_listed_and_in_detail(api, http, value):
    made = await upload(api, context="ROOM", extra=[("source", value)])
    assert made["asset"]["capture_source"] == value
    asset = await row(api.db, PhotoAsset, made["asset"]["id"])
    assert asset.capture_source is PhotoCaptureSource(value)
    listed = (await http.get(path_for(api.project))).json()["items"][0]["asset"]
    assert listed["capture_source"] == value
    detail = (await http.get(f"{path_for(api.project)}/{made['asset']['id']}")).json()["asset"]
    assert detail["capture_source"] == value


async def test_source_is_optional_and_defaults_to_unknown(api, http):
    made = await upload(api, context="ROOM")
    assert made["asset"]["capture_source"] is None
    assert (await row(api.db, PhotoAsset, made["asset"]["id"])).capture_source is None


@pytest.mark.parametrize("bad", ["camera", "Camera", "SCREENSHOT", "", " CAMERA", "CAMERA ", "1"])
async def test_invalid_source_value_is_malformed_and_writes_nothing(api, bad):
    body = form(api, extra=[("source", bad)])
    c = await call(path_for(api.project), token=api.token, body=body)
    assert c.status == 422 and c.json()["detail"]["code"] == "PHOTO_UPLOAD_MALFORMED"
    assert await c5.counts(api.db) == (0, 0)


async def test_duplicate_source_field_is_malformed(api):
    body = form(api, extra=[("source", "CAMERA"), ("source", "GALLERY")])
    c = await call(path_for(api.project), token=api.token, body=body)
    assert c.status == 422 and c.json()["detail"]["code"] == "PHOTO_UPLOAD_MALFORMED"
    assert await c5.counts(api.db) == (0, 0)


async def test_replay_ignores_a_different_source(api, http):
    """C16: a replay of a READY upload never changes metadata; the first declaration wins."""
    upload_id = str(uuid.uuid4())
    first = await upload(api, upload_id=upload_id, extra=[("source", "CAMERA")])
    c = await call(path_for(api.project), token=api.token,
                   body=form(api, upload_id=upload_id, extra=[("source", "GALLERY")]))
    assert c.status == 200
    assert c.json()["asset"]["capture_source"] == "CAMERA" == first["asset"]["capture_source"]
    assert (await row(api.db, PhotoAsset, upload_id)).capture_source is PhotoCaptureSource.CAMERA


async def test_replay_without_source_does_not_clear_it(api):
    upload_id = str(uuid.uuid4())
    await upload(api, upload_id=upload_id, extra=[("source", "GALLERY")])
    c = await call(path_for(api.project), token=api.token, body=form(api, upload_id=upload_id))
    assert c.status == 200 and c.json()["asset"]["capture_source"] == "GALLERY"


async def test_resume_of_a_failed_upload_keeps_the_first_declaration(api):
    """A storage failure leaves a FAILED asset that already carries the declared source; the resumed request
    (same upload id and bytes, a different declared source) finalizes it WITHOUT changing the source."""
    upload_id = str(uuid.uuid4())
    api.storage.put_faults["/display.jpg"] = MediaStorageUnavailable("storage down")
    failed = await call(path_for(api.project), token=api.token,
                        body=form(api, upload_id=upload_id, extra=[("source", "CAMERA")]))
    assert failed.status == 503 and failed.json()["detail"]["code"] == "PHOTO_STORAGE_UNAVAILABLE"
    asset = await row(api.db, PhotoAsset, upload_id)
    assert asset.status is PhotoAssetStatus.FAILED and asset.capture_source is PhotoCaptureSource.CAMERA

    api.storage.put_faults.clear()
    resumed = await call(path_for(api.project), token=api.token,
                         body=form(api, upload_id=upload_id, extra=[("source", "GALLERY")]))
    assert resumed.status == 201, resumed.body
    assert resumed.json()["asset"]["capture_source"] == "CAMERA"
    asset = await row(api.db, PhotoAsset, upload_id)
    assert asset.status is PhotoAssetStatus.READY and asset.capture_source is PhotoCaptureSource.CAMERA


# ---------------------------------------------------------------------------
# database constraint
# ---------------------------------------------------------------------------


async def test_check_constraint_rejects_unknown_values_at_the_database_level(api):
    asset = c5.raw_asset(SimpleNamespace(id=api.me), SimpleNamespace(id=api.project), status=PhotoAssetStatus.READY)
    api.db.add(asset)
    await api.db.commit()
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        await api.db.execute(
            text("UPDATE photo_assets SET capture_source = 'SCREENSHOT' WHERE id = :id"),
            {"id": asset.id.hex},
        )
    await api.db.rollback()


# ---------------------------------------------------------------------------
# migration 0033 (rendered PostgreSQL DDL; the real upgrade / downgrade runs on a scratch PostgreSQL 16)
# ---------------------------------------------------------------------------


def _offline_sql(*args: str) -> str:
    import os
    import subprocess
    import sys
    from pathlib import Path

    backend = Path(__file__).resolve().parents[1]
    env = dict(os.environ, DATABASE_URL="postgresql+asyncpg://offline:offline@localhost:1/offline")
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args, "--sql"], cwd=backend, env=env, capture_output=True, text=True, check=True
    ).stdout


def test_migration_0033_adds_one_nullable_column_and_one_check_only():
    up = _offline_sql("upgrade", "0032_photo_attachments:0033_photo_capture_source")
    assert "ALTER TABLE photo_assets ADD COLUMN capture_source VARCHAR(16)" in up
    assert "NOT NULL" not in up.split("ADD COLUMN capture_source")[1].split(";")[0]  # nullable, no default
    assert "DEFAULT" not in up.split("ADD COLUMN capture_source")[1].split(";")[0]
    assert (
        "ALTER TABLE photo_assets ADD CONSTRAINT ck_photo_assets_capture_source "
        "CHECK (capture_source IS NULL OR capture_source IN ('CAMERA', 'GALLERY'))"
    ) in up
    assert "CREATE TYPE" not in up and "CREATE TABLE" not in up and "CREATE INDEX" not in up
    assert "UPDATE " not in up.replace("UPDATE alembic_version", "")  # no backfill of existing rows
    assert up.count("ALTER TABLE") == 2  # the column and the constraint, nothing else


def test_migration_0033_downgrade_is_a_plain_drop_and_leaves_no_type():
    down = _offline_sql("downgrade", "0033_photo_capture_source:0032_photo_attachments")
    assert "ALTER TABLE photo_assets DROP CONSTRAINT ck_photo_assets_capture_source" in down
    assert "ALTER TABLE photo_assets DROP COLUMN capture_source" in down
    assert "DROP TYPE" not in down and "DROP TABLE" not in down
