"""Archive cleanup AC-2 -- deleting a photo from the trash for good (HTTP over the real routes, in-memory storage and purger).

What matters: only a trashed photo can go; the file set is removed only with the LAST use of the file and only that photo's three objects;
the ledger records it; a failure of the storage after the rows are gone loses nothing and a retry finishes it; a protocol that points to
the photo blocks it; nothing of another owner is reachable.
"""
import uuid
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.api import deps
from app.domain.exceptions import MediaStorageUnavailable
from app.domain.services.media_purger import InMemoryMediaPurger
from app.main import app
from app.models.acceptance_protocol import AcceptanceProtocol
from app.models.concealed_works_protocol import ConcealedWorksProtocol
from app.models.downtime_episode import DowntimeEpisode
from app.models.photo_annotation import PhotoAnnotation
from app.models.photo_asset import PhotoAsset
from app.models.photo_attachment import PhotoAttachment
from app.models.purge_ledger import PurgeLedger
from tests import test_stage14c4_photos_api as c4
from tests.test_stage14c5_photos_api import code, row, upload

api = c4.api


@pytest.fixture
async def http(api):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {api.token}"
        yield client


@pytest.fixture
def purger(api):
    instance = InMemoryMediaPurger(api.storage)
    app.dependency_overrides[deps.get_media_purger] = lambda: instance
    return instance


def base_of(a) -> str:
    return f"/api/projects/{a.project}"


async def trash(http, a, made) -> str:
    att_id = made["attachment"]["id"]
    assert (await http.post(f"{base_of(a)}/photo-attachments/{att_id}/archive")).status_code == 200
    assert (await http.post(f"{base_of(a)}/photo-attachments/{att_id}/trash")).status_code == 200
    return att_id


async def count(db, model) -> int:
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


async def test_only_a_photo_in_the_trash_can_be_deleted_for_good(api, http, purger):
    made = await upload(api)
    att_id = made["attachment"]["id"]
    keys = set(api.storage.keys())
    refused = await http.post(f"{base_of(api)}/photo-attachments/{att_id}/purge")
    assert refused.status_code == 409 and code(refused) == "PHOTO_PURGE_NOT_TRASHED"
    await http.post(f"{base_of(api)}/photo-attachments/{att_id}/archive")  # archived is still not the trash
    refused = await http.post(f"{base_of(api)}/photo-attachments/{att_id}/purge")
    assert refused.status_code == 409 and code(refused) == "PHOTO_PURGE_NOT_TRASHED"
    assert set(api.storage.keys()) == keys and purger.deleted == [] and await count(api.db, PurgeLedger) == 0
    assert await row(api.db, PhotoAttachment, att_id) is not None


async def test_the_last_use_of_a_photo_removes_its_rows_its_three_objects_and_leaves_a_ledger_row(api, http, purger):
    first, second = await upload(api), await upload(api)
    att_id, asset_id = first["attachment"]["id"], first["asset"]["id"]
    marker = await http.post(f"{base_of(api)}/photo-attachments/{att_id}/annotations", json={"x": 0.5, "y": 0.5})
    assert marker.status_code == 201
    asset = await row(api.db, PhotoAsset, asset_id)
    mine = {asset.storage_key_original, asset.storage_key_display, asset.storage_key_thumbnail}
    others = set(api.storage.keys()) - mine
    assert len(mine) == 3 and others
    await trash(http, api, first)

    result = await http.post(f"{base_of(api)}/photo-attachments/{att_id}/purge")
    assert result.status_code == 200 and result.json() == {"purged": True, "deleted_files": True, "storage_pending": False}

    assert set(purger.deleted) == mine
    assert set(api.storage.keys()) == others  # the other photo is untouched
    assert await row(api.db, PhotoAttachment, att_id) is None and await row(api.db, PhotoAsset, asset_id) is None
    assert await count(api.db, PhotoAnnotation) == 0
    ledger = (await api.db.execute(select(PurgeLedger))).scalar_one()
    assert ledger.asset_id == uuid.UUID(asset_id) and ledger.owner_id == api.me and ledger.project_id == api.project
    assert {ledger.storage_key_original, ledger.storage_key_display, ledger.storage_key_thumbnail} == mine
    assert ledger.sha256 == asset.sha256 and ledger.storage_state == "DONE" and ledger.storage_done_at is not None
    assert ledger.backup_state == "PENDING" and ledger.backup_done_at is None
    assert await row(api.db, PhotoAsset, second["asset"]["id"]) is not None
    assert (await http.post(f"{base_of(api)}/photo-attachments/{att_id}/purge")).status_code == 404  # already gone


async def test_a_file_that_has_another_use_stays_until_its_last_use_is_deleted(api, http, purger):
    made = await upload(api)
    base, asset_id, first_id = base_of(api), made["asset"]["id"], made["attachment"]["id"]
    second_id = (await http.post(f"{base}/photos/{asset_id}/attachments", json={"context": "PROJECT"})).json()["id"]
    await trash(http, api, made)
    preview = (await http.get(f"{base}/photo-attachments/{first_id}/purge-preview")).json()
    assert preview["deletes_files"] is False and preview["files"] == 0 and preview["bytes"] == 0 and preview["other_attachments"] == 1

    result = (await http.post(f"{base}/photo-attachments/{first_id}/purge")).json()
    assert result == {"purged": True, "deleted_files": False, "storage_pending": False}
    assert purger.deleted == [] and await row(api.db, PhotoAsset, asset_id) is not None and await count(api.db, PurgeLedger) == 0
    assert await row(api.db, PhotoAttachment, second_id) is not None

    await http.post(f"{base}/photo-attachments/{second_id}/archive")
    await http.post(f"{base}/photo-attachments/{second_id}/trash")
    result = (await http.post(f"{base}/photo-attachments/{second_id}/purge")).json()
    assert result["deleted_files"] is True and len(purger.deleted) == 3 and await row(api.db, PhotoAsset, asset_id) is None


async def test_the_preview_counts_what_would_go_and_changes_nothing(api, http, purger):
    made = await upload(api)
    base, att_id = base_of(api), made["attachment"]["id"]
    await http.post(f"{base}/photo-attachments/{att_id}/annotations", json={"x": 0.1, "y": 0.2})
    await http.post(f"{base}/photo-attachments/{att_id}/annotations", json={"x": 0.3, "y": 0.4})
    asset = await row(api.db, PhotoAsset, made["asset"]["id"])
    before = await http.get(f"{base}/photo-attachments/{att_id}/purge-preview")
    assert before.json()["trashed"] is False and before.json()["can_purge"] is False
    await trash(http, api, made)
    preview = (await http.get(f"{base}/photo-attachments/{att_id}/purge-preview")).json()
    assert preview == {
        "attachment_id": att_id, "trashed": True, "can_purge": True, "annotations": 2, "other_attachments": 0, "deletes_files": True, "files": 3,
        "bytes": asset.byte_size + asset.display_byte_size + asset.thumbnail_byte_size, "may_be_in_backups": True, "blockers": [],
    }
    assert purger.deleted == [] and await row(api.db, PhotoAttachment, att_id) is not None and await count(api.db, PhotoAnnotation) == 2


NOW = datetime.now(UTC)
# what the database demands of an issued / noticed protocol (the frozen document)
FROZEN = {
    ConcealedWorksProtocol: {"ISSUED": {"issued_at": NOW, "snapshot": {}, "document_html": "<p>x</p>"}},
    AcceptanceProtocol: {"ISSUED": {"issued_at": NOW, "snapshot": {}, "document_html": "<p>x</p>"}},
    DowntimeEpisode: {"NOTICED": {"notice_issued_at": NOW, "notice_snapshot": {}, "notice_html": "<p>x</p>"}},
}
CASES = [(model, status, status != "ARCHIVED") for model, statuses in (
    (ConcealedWorksProtocol, ("DRAFT", "ISSUED", "ARCHIVED")), (AcceptanceProtocol, ("DRAFT", "ISSUED", "ARCHIVED")), (DowntimeEpisode, ("DRAFT", "NOTICED", "ARCHIVED")),
) for status in statuses]


@pytest.mark.parametrize("model, status, blocks", CASES, ids=[f"{m.__name__}-{s}" for m, s, _ in CASES])
async def test_a_protocol_that_points_to_the_photo_protects_it(api, http, purger, model, status, blocks):
    kwargs = FROZEN[model].get(status, {})
    made = await upload(api)
    att_id = made["attachment"]["id"]
    if model is AcceptanceProtocol:
        extra = {"surfaces": {str(uuid.uuid4()): {"assessed": True, "remarks": {"r1": {"id": "r1", "photo_ids": [att_id]}}}}}
    else:
        extra = {"photo_ids": [att_id]}
    api.db.add(model(owner_id=api.me, project_id=api.project, sequence=1, status=status, **extra, **kwargs))
    await api.db.commit()
    await trash(http, api, made)

    preview = (await http.get(f"{base_of(api)}/photo-attachments/{att_id}/purge-preview")).json()
    assert preview["can_purge"] is (not blocks) and bool(preview["blockers"]) is blocks
    result = await http.post(f"{base_of(api)}/photo-attachments/{att_id}/purge")
    if blocks:
        assert result.status_code == 409 and code(result) == "PHOTO_PURGE_BLOCKED"
        assert result.json()["detail"]["blockers"][0]["status"] == status
        assert await row(api.db, PhotoAttachment, att_id) is not None and purger.deleted == []
    else:
        assert result.status_code == 200


async def test_a_protocol_that_names_another_photo_does_not_block(api, http, purger):
    made, other = await upload(api), await upload(api)
    api.db.add(ConcealedWorksProtocol(owner_id=api.me, project_id=api.project, sequence=1, status="ISSUED", photo_ids=[other["attachment"]["id"]], **FROZEN[ConcealedWorksProtocol]["ISSUED"]))
    await api.db.commit()
    await trash(http, api, made)
    assert (await http.post(f"{base_of(api)}/photo-attachments/{made['attachment']['id']}/purge")).status_code == 200


async def test_a_storage_failure_after_the_rows_are_gone_loses_nothing_and_a_retry_finishes_it(api, http, purger):
    made = await upload(api)
    base, att_id, asset_id = base_of(api), made["attachment"]["id"], made["asset"]["id"]
    asset = await row(api.db, PhotoAsset, asset_id)
    mine = {asset.storage_key_original, asset.storage_key_display, asset.storage_key_thumbnail}
    await trash(http, api, made)
    purger.fault = MediaStorageUnavailable("storage down")

    result = await http.post(f"{base}/photo-attachments/{att_id}/purge")
    assert result.status_code == 200 and result.json() == {"purged": True, "deleted_files": True, "storage_pending": True}
    assert await row(api.db, PhotoAttachment, att_id) is None and await row(api.db, PhotoAsset, asset_id) is None
    assert mine <= set(api.storage.keys())  # the objects are still there
    ledger = (await api.db.execute(select(PurgeLedger))).scalar_one()
    assert ledger.storage_state == "PENDING" and ledger.storage_done_at is None
    status = (await http.get("/api/photo-purge/status")).json()
    assert status["storage_pending"] == 1 and status["backup_pending"] == 1 and status["last_purged_at"]

    retried = (await http.post("/api/photo-purge/retry")).json()
    assert retried["storage_pending"] == 0 and retried["backup_pending"] == 1
    assert not (mine & set(api.storage.keys()))
    await api.db.refresh(ledger)
    assert ledger.storage_state == "DONE" and ledger.storage_done_at is not None


async def test_the_next_purge_first_finishes_the_one_left_half_done(api, http, purger):
    first, second = await upload(api), await upload(api)
    a1 = await row(api.db, PhotoAsset, first["asset"]["id"])
    k1 = {a1.storage_key_original, a1.storage_key_display, a1.storage_key_thumbnail}
    base = base_of(api)
    await trash(http, api, first)
    purger.fault = MediaStorageUnavailable("down")
    assert (await http.post(f"{base}/photo-attachments/{first['attachment']['id']}/purge")).json()["storage_pending"] is True
    await trash(http, api, second)
    assert (await http.post(f"{base}/photo-attachments/{second['attachment']['id']}/purge")).json()["storage_pending"] is False
    assert not (k1 & set(api.storage.keys()))
    assert (await http.get("/api/photo-purge/status")).json()["storage_pending"] == 0


async def test_nothing_of_another_owner_is_reachable(api, http, purger):
    made = await upload(api)
    att_id = made["attachment"]["id"]
    await trash(http, api, made)
    keys = set(api.storage.keys())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as stranger:
        stranger.headers["Authorization"] = f"Bearer {api.other_token}"
        for method, path in (("get", f"{base_of(api)}/photo-attachments/{att_id}/purge-preview"), ("post", f"{base_of(api)}/photo-attachments/{att_id}/purge")):
            assert (await getattr(stranger, method)(path)).status_code == 404
        # the ledger and the status are per owner
        assert (await stranger.get("/api/photo-purge/status")).json()["storage_pending"] == 0
    assert set(api.storage.keys()) == keys and await row(api.db, PhotoAttachment, att_id) is not None
    assert (await http.post(f"/api/projects/{api.foreign_project}/photo-attachments/{att_id}/purge")).status_code == 404


async def test_the_storage_usage_drops_by_what_was_deleted(api, http, purger):
    made = await upload(api)
    before = (await http.get("/api/photo-storage")).json()["used_bytes"]
    asset = await row(api.db, PhotoAsset, made["asset"]["id"])
    await trash(http, api, made)
    await http.post(f"{base_of(api)}/photo-attachments/{made['attachment']['id']}/purge")
    after = (await http.get("/api/photo-storage")).json()["used_bytes"]
    assert before - after == asset.byte_size + asset.display_byte_size + asset.thumbnail_byte_size


async def test_the_status_of_a_clean_owner_is_zero(api, http, purger):
    assert (await http.get("/api/photo-purge/status")).json() == {"storage_pending": 0, "backup_pending": 0, "last_purged_at": None}
    assert (await http.post("/api/photo-purge/retry")).json()["storage_pending"] == 0
