"""Archive cleanup AC-5b -- deleting an archived object for good (HTTP over the real routes, in-memory storage and purger).

What matters: only an archived object can go; an issued / signed document holds it; everything below it goes in ONE transaction (and nothing when
it fails), the files of its photos leave the storage through the ledger, a failure of the storage after the rows are gone loses nothing and a
retry finishes it; another object and another owner are never touched.
"""
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, func, select

from app.api import deps
from app.domain.exceptions import MediaStorageUnavailable
from app.domain.services.media_purger import InMemoryMediaPurger
from app.main import app
from app.models.acceptance_protocol import AcceptanceProtocol
from app.models.concealed_works_protocol import ConcealedWorksProtocol
from app.models.contract import Contract
from app.models.decision_protocol import DecisionProtocol
from app.models.downtime_episode import DowntimeEpisode
from app.models.handover_protocol import HandoverProtocol
from app.models.opening import Opening
from app.models.photo_annotation import PhotoAnnotation
from app.models.photo_asset import PhotoAsset
from app.models.photo_attachment import PhotoAttachment
from app.models.project import Project
from app.models.project_payment import ProjectFinance, ProjectPayment
from app.models.purge_ledger import PurgeLedger
from app.models.reminder import Reminder
from app.models.room import Room
from app.models.surface import Surface
from tests import test_stage14c4_photos_api as c4
from tests.test_stage14c5_photos_api import code, row, upload

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


def base_of(a, project=None) -> str:
    return f"/api/projects/{project or a.project}"


async def archive(http, a, project=None) -> None:
    assert (await http.post(f"{base_of(a, project)}/archive")).status_code == 200


async def count(db, model, *conditions) -> int:
    return (await db.execute(select(func.count()).select_from(model).where(*conditions))).scalar_one()


async def keys_of(db, asset_id) -> set[str]:
    asset = await row(db, PhotoAsset, asset_id)
    return {asset.storage_key_original, asset.storage_key_display, asset.storage_key_thumbnail}


# ------------------------------------------------------------------ the archive is the only way in

async def test_an_object_in_work_cannot_be_deleted(api, http, purger):
    made = await upload(api)
    keys = set(api.storage.keys())
    preview = (await http.get(f"{base_of(api)}/purge-preview")).json()
    assert preview["archived"] is False and preview["can_purge"] is False
    refused = await http.post(f"{base_of(api)}/purge")
    assert refused.status_code == 409 and code(refused) == "PROJECT_NOT_ARCHIVED"
    assert await row(api.db, Project, api.project) is not None and await row(api.db, PhotoAsset, made["asset"]["id"]) is not None
    assert set(api.storage.keys()) == keys and purger.deleted == [] and await count(api.db, PurgeLedger) == 0


# ------------------------------------------------------------------ preview

async def test_the_preview_counts_everything_that_would_go_and_changes_nothing(api, http, purger):
    first, second = await upload(api), await upload(api)
    await http.post(f"{base_of(api)}/photo-attachments/{first['attachment']['id']}/annotations", json={"x": 0.1, "y": 0.2})
    api.db.add(Contract(owner_id=api.me, project_id=api.project, version=1, status="DRAFT", answers={}, questionnaire_version=1))
    api.db.add(ConcealedWorksProtocol(owner_id=api.me, project_id=api.project, sequence=1, status="DRAFT", photo_ids=[]))
    await api.db.commit()
    await archive(http, api)
    a1, a2 = await row(api.db, PhotoAsset, first["asset"]["id"]), await row(api.db, PhotoAsset, second["asset"]["id"])
    size = sum(a.byte_size + a.display_byte_size + a.thumbnail_byte_size for a in (a1, a2))

    preview = (await http.get(f"{base_of(api)}/purge-preview")).json()
    assert preview["project_id"] == str(api.project) and preview["archived"] is True and preview["can_purge"] is True
    assert (preview["rooms"], preview["surfaces"], preview["openings"], preview["inspections"], preview["estimates"]) == (1, 1, 1, 0, 0)
    assert (preview["documents"], preview["sent_documents"]) == (2, 0)
    assert (preview["photos"], preview["photo_files"], preview["bytes"], preview["annotations"]) == (2, 2, size, 1)
    assert preview["may_be_in_backups"] is True and preview["blockers"] == []
    # nothing was changed
    assert await row(api.db, Project, api.project) is not None and await count(api.db, PhotoAsset) == 2 and purger.deleted == []


async def test_the_preview_of_an_object_without_photos_has_nothing_in_the_backups(api, http, purger):
    await archive(http, api)
    preview = (await http.get(f"{base_of(api)}/purge-preview")).json()
    assert (preview["photos"], preview["photo_files"], preview["bytes"]) == (0, 0, 0) and preview["may_be_in_backups"] is False


# ------------------------------------------------------------------ the deletion

async def test_the_deletion_removes_the_object_everything_below_it_and_the_files_and_leaves_a_ledger(api, http, purger):
    first, second = await upload(api), await upload(api)
    await http.post(f"{base_of(api)}/photo-attachments/{first['attachment']['id']}/annotations", json={"x": 0.5, "y": 0.5})
    mine = (await keys_of(api.db, first["asset"]["id"])) | (await keys_of(api.db, second["asset"]["id"]))
    # an object of the same owner with a photo of its own: it must stay whole
    kept = await upload(api, context="PROJECT", project=api.project2)
    kept_keys = await keys_of(api.db, kept["asset"]["id"])
    api.db.add(Contract(owner_id=api.me, project_id=api.project, version=1, status="DRAFT", answers={}, questionnaire_version=1))
    await api.db.commit()
    await archive(http, api)

    result = await http.post(f"{base_of(api)}/purge")
    assert result.status_code == 200 and result.json() == {"purged": True, "photo_files": 2, "storage_pending": 0}

    assert await row(api.db, Project, api.project) is None
    assert await count(api.db, Room, Room.project_id == api.project) == 0 and await count(api.db, Contract, Contract.project_id == api.project) == 0
    assert await count(api.db, Room, Room.id == api.room) == 0 and await count(api.db, Surface, Surface.id == api.surface) == 0
    assert await count(api.db, Opening, Opening.id == api.opening) == 0
    assert await count(api.db, PhotoAsset, PhotoAsset.project_id == api.project) == 0 and await count(api.db, PhotoAnnotation) == 0
    assert set(purger.deleted) == mine and not (mine & set(api.storage.keys()))
    ledger = list((await api.db.execute(select(PurgeLedger).order_by(PurgeLedger.asset_id))).scalars())
    assert len(ledger) == 2 and {l.project_id for l in ledger} == {api.project} and {l.owner_id for l in ledger} == {api.me}
    assert all(l.storage_state == "DONE" and l.backup_state == "PENDING" and l.kind == "PHOTO" for l in ledger)
    assert {k for l in ledger for k in l.keys()} == mine
    # the other object is whole
    assert await row(api.db, Project, api.project2) is not None and await row(api.db, PhotoAsset, kept["asset"]["id"]) is not None
    assert kept_keys <= set(api.storage.keys())
    status = (await http.get("/api/photo-purge/status")).json()
    assert status["storage_pending"] == 0 and status["backup_pending"] == 2


async def test_an_object_without_photos_is_deleted_without_a_ledger(api, http, purger):
    await archive(http, api)
    result = await http.post(f"{base_of(api)}/purge")
    assert result.json() == {"purged": True, "photo_files": 0, "storage_pending": 0}
    assert await row(api.db, Project, api.project) is None and await count(api.db, PurgeLedger) == 0 and purger.deleted == []
    assert (await http.post(f"{base_of(api)}/purge")).status_code == 404  # already gone


async def test_a_failure_of_the_storage_after_the_rows_are_gone_loses_nothing_and_a_retry_finishes_it(api, http, purger):
    made = await upload(api)
    mine = await keys_of(api.db, made["asset"]["id"])
    await archive(http, api)
    purger.fault = MediaStorageUnavailable("storage down")

    result = await http.post(f"{base_of(api)}/purge")
    assert result.status_code == 200 and result.json() == {"purged": True, "photo_files": 1, "storage_pending": 1}
    assert await row(api.db, Project, api.project) is None and await count(api.db, PhotoAsset) == 0
    assert mine <= set(api.storage.keys())  # the objects are still there, the ledger remembers them
    ledger = (await api.db.execute(select(PurgeLedger))).scalar_one()
    assert ledger.storage_state == "PENDING" and ledger.project_id == api.project

    purger.fault = None
    assert (await http.post("/api/photo-purge/retry")).json()["storage_pending"] == 0
    assert not (mine & set(api.storage.keys()))
    await api.db.refresh(ledger)
    assert ledger.storage_state == "DONE"


async def test_a_photo_that_appears_meanwhile_stops_the_deletion_and_nothing_is_lost(api, http, purger):
    first = await upload(api)
    first_keys = await keys_of(api.db, first["asset"]["id"])
    await archive(http, api)
    template = await row(api.db, PhotoAsset, first["asset"]["id"])
    fired: list[bool] = []

    def add_a_photo_before_the_object_is_deleted(state):
        # the first DELETE of the photo markers is the first statement of the transaction: a new photo row lands in it
        if state.is_delete and not fired and getattr(state.statement.table, "name", "") == "photo_annotations":
            fired.append(True)
            clone = {c.name: getattr(template, c.name) for c in PhotoAsset.__table__.columns}
            clone.update(id=uuid.uuid4(), storage_key_original="k/o-new", storage_key_display="k/d-new", storage_key_thumbnail="k/t-new", sha256="f" * 64)
            state.session.add(PhotoAsset(**clone))

    event.listen(api.db.sync_session, "do_orm_execute", add_a_photo_before_the_object_is_deleted)
    try:
        result = await http.post(f"{base_of(api)}/purge")
    finally:
        event.remove(api.db.sync_session, "do_orm_execute", add_a_photo_before_the_object_is_deleted)
    assert fired and result.status_code == 409 and code(result) == "PROJECT_PURGE_CONFLICT"
    # all or nothing: the object, its photo, its files and the markers are all still here, and no ledger row was written
    assert await row(api.db, Project, api.project) is not None and await row(api.db, PhotoAsset, first["asset"]["id"]) is not None
    assert await row(api.db, PhotoAttachment, first["attachment"]["id"]) is not None
    assert await count(api.db, PurgeLedger) == 0 and purger.deleted == [] and first_keys <= set(api.storage.keys())


# ------------------------------------------------------------------ the documents that hold an object

FROZEN = {"issued_at": NOW, "snapshot": {}, "document_html": "<p>x</p>"}
HOLDERS = [
    # (model, status, extra columns, holds)
    (Contract, "DRAFT", {}, False),
    (Contract, "ARCHIVED", {}, False),
    (Contract, "ISSUED", dict(FROZEN), True),
    (Contract, "SIGNED", {**FROZEN, "signed_on": date(2026, 10, 1)}, True),
    (HandoverProtocol, "DRAFT", {}, False),
    (HandoverProtocol, "ARCHIVED", {}, False),
    (HandoverProtocol, "ISSUED", dict(FROZEN), True),
    (ConcealedWorksProtocol, "DRAFT", {}, False),
    (ConcealedWorksProtocol, "ARCHIVED", {}, False),
    (ConcealedWorksProtocol, "ISSUED", dict(FROZEN), True),
    (DecisionProtocol, "ARCHIVED", {}, False),
    (DecisionProtocol, "ISSUED", dict(FROZEN), True),
    (AcceptanceProtocol, "DRAFT", {}, False),
    (AcceptanceProtocol, "ISSUED", dict(FROZEN), True),
    (DowntimeEpisode, "DRAFT", {}, False),
    (DowntimeEpisode, "ARCHIVED", {}, False),
    (DowntimeEpisode, "NOTICED", {"notice_issued_at": NOW, "notice_snapshot": {}, "notice_html": "<p>x</p>"}, True),
]


@pytest.mark.parametrize("model, status, extra, holds", HOLDERS, ids=[f"{m.__name__}-{s}" for m, s, _, _ in HOLDERS])
async def test_an_issued_or_signed_document_holds_the_object_and_a_draft_or_archived_one_does_not(api, http, purger, model, status, extra, holds):
    made = await upload(api)
    if model is Contract:
        columns = {"version": 1, "answers": {}, "questionnaire_version": 1}
    elif model is AcceptanceProtocol:
        columns = {"sequence": 1, "surfaces": {}}
    else:
        columns = {"sequence": 1}
    api.db.add(model(owner_id=api.me, project_id=api.project, status=status, **columns, **extra))
    await api.db.commit()
    await archive(http, api)

    preview = (await http.get(f"{base_of(api)}/purge-preview")).json()
    assert preview["can_purge"] is (not holds) and bool(preview["blockers"]) is holds
    result = await http.post(f"{base_of(api)}/purge")
    if holds:
        assert result.status_code == 409 and code(result) == "PROJECT_PURGE_BLOCKED"
        blocker = result.json()["detail"]["blockers"][0]
        assert blocker["status"] == status and blocker["protocol_id"]
        assert await row(api.db, Project, api.project) is not None and await row(api.db, PhotoAsset, made["asset"]["id"]) is not None
        assert purger.deleted == [] and await count(api.db, PurgeLedger) == 0
    else:
        assert result.status_code == 200 and await row(api.db, Project, api.project) is None


async def test_the_documents_of_another_object_do_not_hold_this_one(api, http, purger):
    api.db.add(Contract(owner_id=api.me, project_id=api.project2, version=1, status="SIGNED", answers={}, questionnaire_version=1, signed_on=date(2026, 10, 1), **FROZEN))
    await api.db.commit()
    await archive(http, api)
    assert (await http.post(f"{base_of(api)}/purge")).status_code == 200
    assert await row(api.db, Project, api.project2) is not None


# ------------------------------------------------------------------ owners

async def test_nothing_of_another_owner_is_reachable(api, http, purger):
    await archive(http, api)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as stranger:
        stranger.headers["Authorization"] = f"Bearer {api.other_token}"
        assert (await stranger.get(f"{base_of(api)}/purge-preview")).status_code == 404
        assert (await stranger.post(f"{base_of(api)}/purge")).status_code == 404
    assert await row(api.db, Project, api.project) is not None
    # my own token cannot reach the other owner's object either
    assert (await http.get(f"{base_of(api, api.foreign_project)}/purge-preview")).status_code == 404
    assert (await http.post(f"{base_of(api, api.foreign_project)}/purge")).status_code == 404
    assert await row(api.db, Project, api.foreign_project) is not None
    assert (await http.get(f"{base_of(api, uuid.uuid4())}/purge-preview")).status_code == 404


async def test_the_deletion_needs_a_signed_in_user(api, purger):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anonymous:
        assert (await anonymous.get(f"{base_of(api)}/purge-preview")).status_code in (401, 403)
        assert (await anonymous.post(f"{base_of(api)}/purge")).status_code in (401, 403)


async def test_the_settlement_records_are_counted_in_the_preview_and_go_with_the_object(api, http, purger):
    for kind in ("INVOICE", "ADVANCE", "EXPENSE"):
        api.db.add(ProjectPayment(owner_id=api.me, project_id=api.project, kind=kind, title="x", amount_gross=10, occurred_on=NOW.date(), is_archived=(kind == "EXPENSE")))
    api.db.add(ProjectFinance(project_id=api.project, owner_id=api.me, agreed_amount=1000))
    await api.db.commit()
    await archive(http, api)
    preview = (await http.get(f"{base_of(api)}/purge-preview")).json()
    assert preview["payments"] == 3 and preview["can_purge"] is True  # the archived one counts, and nothing holds the object
    assert (await http.post(f"{base_of(api)}/purge")).status_code == 200
    assert await count(api.db, ProjectPayment) == 0 and await count(api.db, ProjectFinance) == 0


async def test_the_reminders_of_an_invoice_go_with_the_object(api, http, purger):
    from app.domain.services.calendar_service import CalendarService

    api.db.add(ProjectPayment(owner_id=api.me, project_id=api.project, kind="INVOICE", title="FV", amount_gross=10, occurred_on=NOW.date(), due_on=NOW.date() + timedelta(days=10)))
    await api.db.commit()
    await CalendarService(api.db).reconcile_owner(api.me)
    await api.db.commit()
    assert await count(api.db, Reminder) == 2  # IA-5: 3 days ahead and the day itself
    await archive(http, api)  # archiving an object cancels its reminders; they are rows still
    assert (await http.post(f"{base_of(api)}/purge")).status_code == 200
    assert await count(api.db, Reminder) == 0 and await count(api.db, ProjectPayment) == 0
