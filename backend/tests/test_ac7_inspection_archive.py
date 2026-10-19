"""Archive cleanup AC-7 -- the archived inspections (Badania podłoża) in the archive, and deleting one for good (HTTP over the real routes).

What matters: the list holds only the archived inspections of rooms and objects in work, of the caller; restoring uses the route of the inspection;
only an ARCHIVED inspection can go; everything that hangs on it goes in ONE transaction (answers, findings, risks, recommended works, its photos and
their files through the ledger) but a file another photo still uses stays; a protocol that is not archived and uses a photo of it as evidence holds it;
the other inspections, the room, the object and another owner are never touched.
"""
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.api import deps
from app.domain.exceptions import MediaStorageUnavailable
from app.domain.services.media_purger import InMemoryMediaPurger
from app.main import app
from app.models.checklist import AnswerType, ChecklistQuestion
from app.models.concealed_works_protocol import ConcealedWorksProtocol
from app.models.inspection import Inspection, InspectionAnswer, InspectionFinding
from app.models.photo_annotation import PhotoAnnotation
from app.models.photo_asset import PhotoAsset
from app.models.photo_attachment import PhotoAttachment
from app.models.purge_ledger import PurgeLedger
from app.models.risk import Risk, RiskSeverity
from app.models.room import Room
from app.models.surface import Surface
from app.models.work_recommendation import (
    WorkRecommendation,
    WorkRecommendationStatus,
    WorkRecommendationTriggerType,
)
from tests import test_stage14c4_photos_api as c4
from tests.test_estimates import _make_room
from tests.test_stage14c5_photos_api import code, row
from tests.test_stage14f2_inspection_photos import upload_ok
from tests.test_work_recommendation_accept import _make_inspection, _make_template

api = c4.api
NOW = datetime.now(UTC)


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


@pytest.fixture
async def w(api):
    """Two inspections of the owner's room: `mine` (an answer, two findings, a risk, a recommended work) and `kept` (an answer), plus an
    inspection of the owner's wall, one of the other object of the owner and one of a foreign owner."""
    db = api.db
    template = await _make_template(db)
    question = ChecklistQuestion(template_id=template.id, position=1, key="q1", text_key="q.one", answer_type=AnswerType.BOOLEAN)
    db.add(question)
    await db.commit()
    mine = await _make_inspection(db, api.room, template.id)
    kept = await _make_inspection(db, api.room, template.id)
    mine_id, kept_id = mine.id, kept.id
    on_wall = Inspection(room_id=api.room, surface_id=api.surface, template_id=template.id, substrate=mine.substrate, status=mine.status, completed_at=NOW)
    db.add(on_wall)
    answer = InspectionAnswer(inspection_id=mine_id, question_id=question.id, value_bool=True)
    db.add_all([answer, InspectionAnswer(inspection_id=kept_id, question_id=question.id, value_bool=False)])
    finding_a = InspectionFinding(inspection_id=mine_id, question_id=question.id, finding_key="CRACK")
    finding_b = InspectionFinding(inspection_id=mine_id, question_id=question.id, finding_key="MOLD")
    risk = Risk(
        room_id=api.room, inspection_id=mine_id, risk_code="R1", rule_code="R1", rule_version=1, severity=RiskSeverity.HIGH, title_key="t",
        explanation_key="e", consequence_key="c", mitigation_key="m", communication_key="k", source_signature=uuid.uuid4().hex, position=0,
    )
    db.add_all([finding_a, finding_b, risk])
    await db.flush()
    recommendation = WorkRecommendation(
        trigger_type=WorkRecommendationTriggerType.RISK_RULE, trigger_code="R1", source_signature=uuid.uuid4().hex, inspection_id=mine_id,
        room_id=api.room, surface_id=None, target_kind="WALL", recommended_work_code="CENNIK_PRIM", status=WorkRecommendationStatus.PENDING,
        is_active=True, risk_id=risk.id,
    )
    other_room = await _make_room(db, api.project2)
    other_object = await _make_inspection(db, other_room.id, template.id)
    foreign = await _make_inspection(db, api.foreign_room, template.id)
    db.add(recommendation)
    await db.commit()
    return SimpleNamespace(
        mine=mine_id, kept=kept_id, on_wall=on_wall.id, other_object=other_object.id, other_room=other_room.id, foreign=foreign.id,
        finding_a=finding_a.id, finding_b=finding_b.id, risk=risk.id, recommendation=recommendation.id, answer=answer.id,
    )


def inspection_url(a, inspection, room=None, project=None) -> str:
    return f"/api/projects/{project or a.project}/rooms/{room or a.room}/inspections/{inspection}"


async def archive(http, a, inspection, **kw) -> None:
    assert (await http.post(f"{inspection_url(a, inspection, **kw)}/archive")).status_code == 200


async def count(db, model, *conditions) -> int:
    return (await db.execute(select(func.count()).select_from(model).where(*conditions))).scalar_one()


async def keys_of(db, asset_id) -> set[str]:
    asset = await row(db, PhotoAsset, asset_id)
    return {asset.storage_key_original, asset.storage_key_display, asset.storage_key_thumbnail}


async def listed(http) -> dict:
    response = await http.get("/api/archive/inspections")
    assert response.status_code == 200
    return response.json()


# ------------------------------------------------------------------ the list

async def test_an_inspection_in_work_is_not_in_the_archive_and_an_archived_one_is_with_its_place(api, http, w):
    assert await listed(http) == {"items": [], "total": 0}
    await archive(http, api, w.mine)
    await archive(http, api, w.on_wall)
    found = await listed(http)
    assert found["total"] == 2 and {item["id"] for item in found["items"]} == {str(w.mine), str(w.on_wall)}
    by_id = {item["id"]: item for item in found["items"]}
    room_item, wall_item = by_id[str(w.mine)], by_id[str(w.on_wall)]
    assert room_item["project_id"] == str(api.project) and room_item["room_id"] == str(api.room) and room_item["project_name"] and room_item["room_name"]
    assert room_item["surface_id"] is None and room_item["surface_name"] is None and room_item["surface_type"] is None and room_item["plane"] is None
    assert room_item["status"] == "COMPLETED" and room_item["substrate"] == "CONCRETE" and room_item["completed_at"]
    assert wall_item["surface_id"] == str(api.surface) and wall_item["surface_name"] and wall_item["surface_type"]


async def test_the_list_is_newest_first(api, http, w):
    await archive(http, api, w.mine)
    await archive(http, api, w.kept)
    found = await listed(http)
    created = [item["created_at"] for item in found["items"]]
    assert created == sorted(created, reverse=True) and found["total"] == 2


async def test_a_restored_inspection_leaves_the_archive_and_is_back_in_the_room(api, http, w):
    await archive(http, api, w.mine)
    assert (await http.post(f"{inspection_url(api, w.mine)}/restore")).status_code == 200
    assert await listed(http) == {"items": [], "total": 0}
    in_room = (await http.get(f"/api/projects/{api.project}/rooms/{api.room}/inspections")).json()
    assert str(w.mine) in {item["id"] for item in in_room["items"]}


async def test_an_inspection_of_an_archived_room_or_object_is_not_listed_apart(api, http, w):
    await archive(http, api, w.mine)
    assert (await listed(http))["total"] == 1
    assert (await http.post(f"/api/projects/{api.project}/rooms/{api.room}/archive")).status_code == 200
    assert await listed(http) == {"items": [], "total": 0}
    assert (await http.post(f"/api/projects/{api.project}/rooms/{api.room}/restore")).status_code == 200
    assert (await listed(http))["total"] == 1
    assert (await http.post(f"/api/projects/{api.project}/archive")).status_code == 200
    assert await listed(http) == {"items": [], "total": 0}


async def test_the_list_holds_only_the_inspections_of_the_caller(api, http, w):
    await archive(http, api, w.mine)
    await archive(http, api, w.other_object, room=w.other_room, project=api.project2)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as stranger:
        stranger.headers["Authorization"] = f"Bearer {api.other_token}"
        assert (await stranger.get("/api/archive/inspections")).json() == {"items": [], "total": 0}
        # the stranger archives his own inspection: only he sees it
        assert (await stranger.post(f"{inspection_url(api, w.foreign, room=api.foreign_room, project=api.foreign_project)}/archive")).status_code == 200
        mine_only = (await stranger.get("/api/archive/inspections")).json()
        assert [item["id"] for item in mine_only["items"]] == [str(w.foreign)]
    assert {item["id"] for item in (await listed(http))["items"]} == {str(w.mine), str(w.other_object)}


async def test_the_list_needs_a_signed_in_user(api):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anonymous:
        assert (await anonymous.get("/api/archive/inspections")).status_code in (401, 403)


# ------------------------------------------------------------------ the archive is the only way in

async def test_an_inspection_in_work_cannot_be_deleted(api, http, w, purger):
    made = await upload_ok(api, context="INSPECTION", target=("inspection_id", str(w.mine)))
    url = inspection_url(api, w.mine)
    preview = (await http.get(f"{url}/purge-preview")).json()
    assert preview["kind"] == "INSPECTION" and preview["archived"] is False and preview["can_purge"] is False
    refused = await http.post(f"{url}/purge")
    assert refused.status_code == 409 and code(refused) == "STRUCTURE_NOT_ARCHIVED"
    assert await row(api.db, Inspection, w.mine) is not None and await row(api.db, PhotoAsset, made["asset"]["id"]) is not None
    assert purger.deleted == []


# ------------------------------------------------------------------ the preview

async def test_the_preview_counts_what_would_go_and_changes_nothing(api, http, w, purger):
    on_inspection = await upload_ok(api, context="INSPECTION", target=("inspection_id", str(w.mine)))
    on_finding = await upload_ok(api, context="FINDING", target=("finding_id", str(w.finding_a)))
    await http.post(f"/api/projects/{api.project}/photo-attachments/{on_inspection['attachment']['id']}/annotations", json={"x": 0.1, "y": 0.2})
    await archive(http, api, w.mine)
    assets = [await row(api.db, PhotoAsset, m["asset"]["id"]) for m in (on_inspection, on_finding)]
    size = sum(a.byte_size + a.display_byte_size + a.thumbnail_byte_size for a in assets)

    preview = (await http.get(f"{inspection_url(api, w.mine)}/purge-preview")).json()
    assert preview["kind"] == "INSPECTION" and preview["target_id"] == str(w.mine) and preview["archived"] and preview["can_purge"]
    assert (preview["surfaces"], preview["openings"], preview["inspections"]) == (0, 0, 1)
    assert (preview["answers"], preview["findings"], preview["risks"], preview["recommendations"]) == (1, 2, 1, 1)
    assert (preview["photos"], preview["photo_files"], preview["bytes"], preview["annotations"]) == (2, 2, size, 1)
    assert preview["estimate_lines"] == 0 and preview["may_be_in_backups"] is True and preview["blockers"] == []
    assert await row(api.db, Inspection, w.mine) is not None and await count(api.db, PhotoAsset) == 2 and purger.deleted == []


# ------------------------------------------------------------------ the deletion

async def test_the_deletion_removes_the_inspection_with_everything_that_hangs_on_it_and_keeps_the_rest(api, http, w, purger):
    on_inspection = await upload_ok(api, context="INSPECTION", target=("inspection_id", str(w.mine)))
    on_finding = await upload_ok(api, context="FINDING", target=("finding_id", str(w.finding_b)))
    mine = (await keys_of(api.db, on_inspection["asset"]["id"])) | (await keys_of(api.db, on_finding["asset"]["id"]))
    kept_photo = await upload_ok(api, context="INSPECTION", target=("inspection_id", str(w.kept)))
    room_photo = await upload_ok(api, context="ROOM")
    kept_keys = (await keys_of(api.db, kept_photo["asset"]["id"])) | (await keys_of(api.db, room_photo["asset"]["id"]))
    await archive(http, api, w.mine)

    result = await http.post(f"{inspection_url(api, w.mine)}/purge")
    assert result.status_code == 200 and result.json() == {"purged": True, "photo_files": 2, "storage_pending": 0}
    assert await row(api.db, Inspection, w.mine) is None
    assert await count(api.db, InspectionAnswer, InspectionAnswer.inspection_id == w.mine) == 0
    assert await count(api.db, InspectionFinding, InspectionFinding.inspection_id == w.mine) == 0
    assert await row(api.db, Risk, w.risk) is None and await row(api.db, WorkRecommendation, w.recommendation) is None
    assert await count(api.db, PhotoAttachment, PhotoAttachment.inspection_id == w.mine) == 0
    assert set(purger.deleted) == mine and not (mine & set(api.storage.keys()))
    ledger = list((await api.db.execute(select(PurgeLedger))).scalars())
    assert len(ledger) == 2 and {l.project_id for l in ledger} == {api.project} and all(l.storage_state == "DONE" and l.backup_state == "PENDING" for l in ledger)
    # the other inspection of the room (with its answer and photo), the room, the wall and the photo of the room stay whole
    assert await row(api.db, Inspection, w.kept) is not None and await count(api.db, InspectionAnswer, InspectionAnswer.inspection_id == w.kept) == 1
    assert await row(api.db, Room, api.room) is not None and await row(api.db, Surface, api.surface) is not None
    assert await row(api.db, PhotoAsset, kept_photo["asset"]["id"]) is not None and await row(api.db, PhotoAsset, room_photo["asset"]["id"]) is not None
    assert kept_keys <= set(api.storage.keys())
    assert await row(api.db, Inspection, w.other_object) is not None and await row(api.db, Inspection, w.foreign) is not None
    assert (await http.post(f"{inspection_url(api, w.mine)}/purge")).status_code == 404  # already gone
    assert await listed(http) == {"items": [], "total": 0}


async def test_an_inspection_without_photos_goes_and_writes_no_ledger(api, http, w, purger):
    await archive(http, api, w.kept)
    assert (await http.post(f"{inspection_url(api, w.kept)}/purge")).json() == {"purged": True, "photo_files": 0, "storage_pending": 0}
    assert await row(api.db, Inspection, w.kept) is None and await count(api.db, PurgeLedger) == 0 and purger.deleted == []


async def test_a_file_that_another_photo_still_uses_stays(api, http, w, purger):
    made = await upload_ok(api, context="INSPECTION", target=("inspection_id", str(w.mine)))
    second = (await http.post(f"/api/projects/{api.project}/photos/{made['asset']['id']}/attachments", json={"context": "PROJECT"})).json()
    await archive(http, api, w.mine)
    preview = (await http.get(f"{inspection_url(api, w.mine)}/purge-preview")).json()
    assert (preview["photos"], preview["photo_files"], preview["bytes"]) == (1, 0, 0)
    assert (await http.post(f"{inspection_url(api, w.mine)}/purge")).json() == {"purged": True, "photo_files": 0, "storage_pending": 0}
    assert await row(api.db, PhotoAttachment, made["attachment"]["id"]) is None
    assert await row(api.db, PhotoAttachment, second["id"]) is not None and await row(api.db, PhotoAsset, made["asset"]["id"]) is not None
    assert purger.deleted == [] and await count(api.db, PurgeLedger) == 0


async def test_the_markers_of_its_photos_go_with_them(api, http, w, purger):
    made = await upload_ok(api, context="INSPECTION", target=("inspection_id", str(w.mine)))
    await http.post(f"/api/projects/{api.project}/photo-attachments/{made['attachment']['id']}/annotations", json={"x": 0.3, "y": 0.4})
    assert await count(api.db, PhotoAnnotation) == 1
    await archive(http, api, w.mine)
    assert (await http.post(f"{inspection_url(api, w.mine)}/purge")).status_code == 200
    assert await count(api.db, PhotoAnnotation) == 0


# ------------------------------------------------------------------ the protocols that hold it

@pytest.mark.parametrize("status, holds", [("DRAFT", True), ("ISSUED", True), ("ARCHIVED", False)])
async def test_a_protocol_that_uses_a_photo_of_the_inspection_as_evidence_holds_it(api, http, w, purger, status, holds):
    made = await upload_ok(api, context="INSPECTION", target=("inspection_id", str(w.mine)))
    frozen = {"issued_at": NOW, "snapshot": {}, "document_html": "<p>x</p>"} if status == "ISSUED" else {}
    api.db.add(ConcealedWorksProtocol(owner_id=api.me, project_id=api.project, sequence=1, status=status, photo_ids=[made["attachment"]["id"]], **frozen))
    await api.db.commit()
    await archive(http, api, w.mine)
    preview = (await http.get(f"{inspection_url(api, w.mine)}/purge-preview")).json()
    assert preview["can_purge"] is (not holds) and bool(preview["blockers"]) is holds
    result = await http.post(f"{inspection_url(api, w.mine)}/purge")
    if holds:
        assert result.status_code == 409 and code(result) == "STRUCTURE_PURGE_BLOCKED" and result.json()["detail"]["blockers"][0]["protocol_id"]
        assert await row(api.db, Inspection, w.mine) is not None and await row(api.db, PhotoAttachment, made["attachment"]["id"]) is not None
        assert purger.deleted == [] and await count(api.db, PurgeLedger) == 0
    else:
        assert result.status_code == 200 and await row(api.db, Inspection, w.mine) is None


async def test_a_protocol_that_uses_a_photo_of_another_inspection_does_not_hold_this_one(api, http, w, purger):
    other = await upload_ok(api, context="INSPECTION", target=("inspection_id", str(w.kept)))
    api.db.add(ConcealedWorksProtocol(owner_id=api.me, project_id=api.project, sequence=1, status="DRAFT", photo_ids=[other["attachment"]["id"]]))
    await api.db.commit()
    await archive(http, api, w.mine)
    assert (await http.post(f"{inspection_url(api, w.mine)}/purge")).status_code == 200


# ------------------------------------------------------------------ failures

async def test_a_failure_of_the_storage_after_the_rows_are_gone_loses_nothing_and_a_retry_finishes_it(api, http, w, purger):
    made = await upload_ok(api, context="INSPECTION", target=("inspection_id", str(w.mine)))
    mine = await keys_of(api.db, made["asset"]["id"])
    await archive(http, api, w.mine)
    purger.fault = MediaStorageUnavailable("storage down")
    result = await http.post(f"{inspection_url(api, w.mine)}/purge")
    assert result.status_code == 200 and result.json() == {"purged": True, "photo_files": 1, "storage_pending": 1}
    assert await row(api.db, Inspection, w.mine) is None and mine <= set(api.storage.keys())
    assert (await api.db.execute(select(PurgeLedger))).scalar_one().storage_state == "PENDING"
    purger.fault = None
    assert (await http.post("/api/photo-purge/retry")).json()["storage_pending"] == 0
    assert not (mine & set(api.storage.keys()))


# ------------------------------------------------------------------ owners and addresses

async def test_nothing_of_another_owner_is_reachable(api, http, w, purger):
    await archive(http, api, w.mine)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as stranger:
        stranger.headers["Authorization"] = f"Bearer {api.other_token}"
        for method, suffix in (("get", "purge-preview"), ("post", "purge")):
            assert (await getattr(stranger, method)(f"{inspection_url(api, w.mine)}/{suffix}")).status_code == 404
    assert await row(api.db, Inspection, w.mine) is not None
    # my own token cannot reach the foreign inspection, nor an inspection through another room or object
    foreign = inspection_url(api, w.foreign, room=api.foreign_room, project=api.foreign_project)
    assert (await http.get(f"{foreign}/purge-preview")).status_code == 404 and (await http.post(f"{foreign}/purge")).status_code == 404
    assert (await http.post(f"{inspection_url(api, w.mine, room=w.other_room)}/purge")).status_code == 404
    assert (await http.post(f"{inspection_url(api, w.mine, project=api.project2)}/purge")).status_code == 404
    assert (await http.post(f"{inspection_url(api, uuid.uuid4())}/purge")).status_code == 404
    assert await row(api.db, Inspection, w.foreign) is not None and await row(api.db, Inspection, w.mine) is not None


async def test_an_inspection_is_reachable_only_through_its_own_room(api, http, w, purger):
    # another room of the SAME object: the address names a room the inspection does not belong to
    neighbour = (await _make_room(api.db, api.project, name="Kuchnia")).id
    made = await upload_ok(api, context="INSPECTION", target=("inspection_id", str(w.mine)))
    await archive(http, api, w.mine)
    wrong = inspection_url(api, w.mine, room=neighbour)
    assert (await http.get(f"{wrong}/purge-preview")).status_code == 404
    assert (await http.post(f"{wrong}/purge")).status_code == 404
    assert await row(api.db, Inspection, w.mine) is not None and await row(api.db, PhotoAttachment, made["attachment"]["id"]) is not None
    assert purger.deleted == [] and await count(api.db, PurgeLedger) == 0


async def test_the_deletion_needs_a_signed_in_user(api, w, purger):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anonymous:
        for method, suffix in (("get", "purge-preview"), ("post", "purge")):
            assert (await getattr(anonymous, method)(f"{inspection_url(api, w.mine)}/{suffix}")).status_code in (401, 403)
