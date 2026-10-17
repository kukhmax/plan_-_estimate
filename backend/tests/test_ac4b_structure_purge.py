"""Archive cleanup AC-4b -- deleting an archived room or an archived surface for good (HTTP over the real routes, in-memory storage and purger).

What matters: only an archived room / surface can go; a document that is not archived and still points to it (or to one of its photos) holds it;
everything below it goes in ONE transaction and its photos' files through the ledger, but a file another photo still uses stays; the waiting
reminders about it are cancelled; a failure of the storage loses nothing; another room, object and owner are never touched.
"""
import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, func, select

from app.api import deps
from app.domain.exceptions import MediaStorageUnavailable
from app.domain.services.media_purger import InMemoryMediaPurger
from app.main import app
from app.models.acceptance_protocol import AcceptanceProtocol
from app.models.adjacent_work import AdjacentWork
from app.models.concealed_works_protocol import ConcealedWorksProtocol
from app.models.downtime_episode import DowntimeEpisode
from app.models.estimate import Estimate, EstimateLine, EstimateStatus, LineOrigin, QuantitySource
from app.models.opening import Opening
from app.models.photo_annotation import PhotoAnnotation
from app.models.photo_asset import PhotoAsset
from app.models.photo_attachment import PhotoAttachment
from app.models.price_item import PriceScope, PriceUnit
from app.models.purge_ledger import PurgeLedger
from app.models.reminder import Reminder
from app.models.room import Room
from app.models.surface import Surface
from tests import test_stage14c4_photos_api as c4
from tests.test_estimates import _make_opening, _make_room, _make_surface
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


def room_url(a, room=None) -> str:
    return f"/api/projects/{a.project}/rooms/{room or a.room}"


def surface_url(a, surface=None, room=None) -> str:
    return f"{room_url(a, room)}/surfaces/{surface or a.surface}"


async def archive(http, url) -> None:
    assert (await http.post(f"{url}/archive")).status_code == 200


async def count(db, model, *conditions) -> int:
    return (await db.execute(select(func.count()).select_from(model).where(*conditions))).scalar_one()


async def keys_of(db, asset_id) -> set[str]:
    asset = await row(db, PhotoAsset, asset_id)
    return {asset.storage_key_original, asset.storage_key_display, asset.storage_key_thumbnail}


# ------------------------------------------------------------------ the archive is the only way in

async def test_a_room_or_surface_in_work_cannot_be_deleted(api, http, purger):
    made = await upload(api, context="SURFACE")
    keys = set(api.storage.keys())
    for url in (room_url(api), surface_url(api)):
        preview = (await http.get(f"{url}/purge-preview")).json()
        assert preview["archived"] is False and preview["can_purge"] is False
        refused = await http.post(f"{url}/purge")
        assert refused.status_code == 409 and code(refused) == "STRUCTURE_NOT_ARCHIVED"
    assert await row(api.db, Room, api.room) is not None and await row(api.db, Surface, api.surface) is not None
    assert await row(api.db, PhotoAsset, made["asset"]["id"]) is not None and set(api.storage.keys()) == keys and purger.deleted == []


# ------------------------------------------------------------------ rooms

async def test_the_room_preview_counts_what_would_go_and_changes_nothing(api, http, purger):
    room_photo, surface_photo, opening_photo = await upload(api), await upload(api, context="SURFACE"), await upload(api, context="OPENING")
    await http.post(f"/api/projects/{api.project}/photo-attachments/{room_photo['attachment']['id']}/annotations", json={"x": 0.1, "y": 0.2})
    estimate = Estimate(owner_id=api.me, project_id=api.project, version=1, status=EstimateStatus.DRAFT, currency="PLN")
    api.db.add(estimate)
    await api.db.flush()
    api.db.add(EstimateLine(
        estimate_id=estimate.id, origin=LineOrigin.MANUAL, position=1, description="x", unit=PriceUnit.M2, scope=PriceScope.LABOR, currency="PLN",
        quantity=Decimal("1"), quantity_source=QuantitySource.MANUAL, quantity_overridden=False, price_override=False, surface_id=api.surface, room_id=api.room,
    ))
    await api.db.commit()
    await archive(http, room_url(api))
    assets = [await row(api.db, PhotoAsset, m["asset"]["id"]) for m in (room_photo, surface_photo, opening_photo)]
    size = sum(a.byte_size + a.display_byte_size + a.thumbnail_byte_size for a in assets)

    preview = (await http.get(f"{room_url(api)}/purge-preview")).json()
    assert preview["kind"] == "ROOM" and preview["target_id"] == str(api.room) and preview["archived"] and preview["can_purge"]
    assert (preview["surfaces"], preview["openings"], preview["inspections"]) == (1, 1, 0)
    assert (preview["photos"], preview["photo_files"], preview["bytes"], preview["annotations"]) == (3, 3, size, 1)
    assert preview["estimate_lines"] == 1 and preview["may_be_in_backups"] is True and preview["blockers"] == []
    assert await row(api.db, Room, api.room) is not None and await count(api.db, PhotoAsset) == 3 and purger.deleted == []


async def test_the_deletion_of_a_room_removes_everything_below_it_and_its_files_and_keeps_the_other_room(api, http, purger):
    a, b, c = await upload(api), await upload(api, context="SURFACE"), await upload(api, context="OPENING")
    mine = set().union(*[await keys_of(api.db, m["asset"]["id"]) for m in (a, b, c)])
    # another room of the same object, with its own photo: it must stay whole
    other_room = await _make_room(api.db, api.project, name="Kuchnia")
    other_room_id = other_room.id
    other_surface_id = (await _make_surface(api.db, other_room_id)).id
    kept = await upload(api, context="ROOM", target=("room_id", str(other_room_id)))
    kept_keys = await keys_of(api.db, kept["asset"]["id"])
    await archive(http, room_url(api))

    result = await http.post(f"{room_url(api)}/purge")
    assert result.status_code == 200 and result.json() == {"purged": True, "photo_files": 3, "storage_pending": 0}
    assert await row(api.db, Room, api.room) is None and await row(api.db, Surface, api.surface) is None and await row(api.db, Opening, api.opening) is None
    assert set(purger.deleted) == mine and not (mine & set(api.storage.keys()))
    ledger = list((await api.db.execute(select(PurgeLedger))).scalars())
    assert len(ledger) == 3 and {l.project_id for l in ledger} == {api.project} and all(l.storage_state == "DONE" and l.backup_state == "PENDING" for l in ledger)
    assert await row(api.db, Room, other_room_id) is not None and await row(api.db, Surface, other_surface_id) is not None
    assert await row(api.db, PhotoAsset, kept["asset"]["id"]) is not None and kept_keys <= set(api.storage.keys())
    assert (await http.post(f"{room_url(api)}/purge")).status_code == 404  # already gone


async def test_a_file_that_another_photo_still_uses_stays(api, http, purger):
    made = await upload(api)  # the room photo
    second = (await http.post(f"/api/projects/{api.project}/photos/{made['asset']['id']}/attachments", json={"context": "PROJECT"})).json()
    await archive(http, room_url(api))
    preview = (await http.get(f"{room_url(api)}/purge-preview")).json()
    assert (preview["photos"], preview["photo_files"], preview["bytes"]) == (1, 0, 0)
    assert (await http.post(f"{room_url(api)}/purge")).json() == {"purged": True, "photo_files": 0, "storage_pending": 0}
    assert await row(api.db, PhotoAttachment, made["attachment"]["id"]) is None  # the use in the room is gone
    assert await row(api.db, PhotoAttachment, second["id"]) is not None and await row(api.db, PhotoAsset, made["asset"]["id"]) is not None
    assert purger.deleted == [] and await count(api.db, PurgeLedger) == 0


async def test_the_deletion_of_a_surface_removes_it_its_openings_and_photos_but_not_the_room(api, http, purger):
    on_surface, on_opening = await upload(api, context="SURFACE"), await upload(api, context="OPENING")
    in_room = await upload(api)  # the room's own photo stays
    mine = (await keys_of(api.db, on_surface["asset"]["id"])) | (await keys_of(api.db, on_opening["asset"]["id"]))
    await archive(http, surface_url(api))
    preview = (await http.get(f"{surface_url(api)}/purge-preview")).json()
    assert preview["kind"] == "SURFACE" and (preview["surfaces"], preview["openings"], preview["photos"], preview["photo_files"]) == (0, 1, 2, 2)

    result = await http.post(f"{surface_url(api)}/purge")
    assert result.status_code == 200 and result.json() == {"purged": True, "photo_files": 2, "storage_pending": 0}
    assert await row(api.db, Surface, api.surface) is None and await row(api.db, Opening, api.opening) is None
    assert await row(api.db, Room, api.room) is not None and await row(api.db, PhotoAsset, in_room["asset"]["id"]) is not None
    assert set(purger.deleted) == mine


async def test_the_waiting_reminders_about_the_room_are_cancelled_the_sent_ones_stay(api, http, purger):
    def reminder(key, status, **where):
        return Reminder(
            owner_id=api.me, project_id=api.project, origin="USER", kind="WORK_START", ref="r", title="t", params={}, event_on=date(2026, 11, 1),
            lead_days=0, send_at=NOW + timedelta(days=3), tz="Europe/Warsaw", status=status, dedupe_key=key, **where,
        )
    waiting, sent, other = reminder("a", "PENDING", room_id=api.room), reminder("b", "SENT", room_id=api.room), reminder("c", "PENDING")
    api.db.add_all([waiting, sent, other])
    await api.db.commit()
    await archive(http, room_url(api))
    assert (await http.post(f"{room_url(api)}/purge")).status_code == 200
    for item, expected in ((waiting, "CANCELLED"), (sent, "SENT"), (other, "PENDING")):
        await api.db.refresh(item)
        assert item.status == expected


# ------------------------------------------------------------------ the documents that hold it

def holder(kind, status, a):
    """One document of the given kind and status that points to the room / surface of the rig."""
    if kind == "CONCEALED_WORKS":
        frozen = {"issued_at": NOW, "snapshot": {}, "document_html": "<p>x</p>"} if status == "ISSUED" else {}
        return ConcealedWorksProtocol(owner_id=a.me, project_id=a.project, sequence=1, status=status, photo_ids=[], surface_id=a.surface, **frozen)
    if kind == "ACCEPTANCE_ROOM":
        frozen = {"issued_at": NOW, "snapshot": {}, "document_html": "<p>x</p>"} if status == "ISSUED" else {}
        return AcceptanceProtocol(owner_id=a.me, project_id=a.project, sequence=1, status=status, room_ids=[str(a.room)], surfaces={}, **frozen)
    if kind == "ACCEPTANCE_SURFACE":
        return AcceptanceProtocol(owner_id=a.me, project_id=a.project, sequence=1, status=status, room_ids=[], surfaces={str(a.surface): {"assessed": True}})
    if kind == "DOWNTIME":
        frozen = {"notice_issued_at": NOW, "notice_snapshot": {}, "notice_html": "<p>x</p>"} if status == "NOTICED" else {}
        return DowntimeEpisode(owner_id=a.me, project_id=a.project, sequence=1, status=status, room_ids=[str(a.room)], photo_ids=[], **frozen)
    return AdjacentWork(owner_id=a.me, project_id=a.project, work_name="Elektryk", room_ids=[str(a.room)], order_relation="BEFORE_OURS", is_archived=(status == "ARCHIVED"))


HOLDERS = [
    ("CONCEALED_WORKS", "DRAFT", True), ("CONCEALED_WORKS", "ISSUED", True), ("CONCEALED_WORKS", "ARCHIVED", False),
    ("ACCEPTANCE_ROOM", "DRAFT", True), ("ACCEPTANCE_ROOM", "ISSUED", True), ("ACCEPTANCE_ROOM", "ARCHIVED", False),
    ("ACCEPTANCE_SURFACE", "DRAFT", True), ("ACCEPTANCE_SURFACE", "ARCHIVED", False),
    ("DOWNTIME", "DRAFT", True), ("DOWNTIME", "NOTICED", True), ("DOWNTIME", "ARCHIVED", False),
    ("ADJACENT_WORK", "ACTIVE", True), ("ADJACENT_WORK", "ARCHIVED", False),
]


@pytest.mark.parametrize("kind, status, holds", HOLDERS, ids=[f"{k}-{s}" for k, s, _ in HOLDERS])
async def test_a_document_that_is_not_archived_holds_the_room(api, http, purger, kind, status, holds):
    made = await upload(api)
    api.db.add(holder(kind, status, api))
    await api.db.commit()
    await archive(http, room_url(api))
    preview = (await http.get(f"{room_url(api)}/purge-preview")).json()
    assert preview["can_purge"] is (not holds) and bool(preview["blockers"]) is holds
    result = await http.post(f"{room_url(api)}/purge")
    if holds:
        assert result.status_code == 409 and code(result) == "STRUCTURE_PURGE_BLOCKED" and result.json()["detail"]["blockers"][0]["protocol_id"]
        assert await row(api.db, Room, api.room) is not None and await row(api.db, PhotoAsset, made["asset"]["id"]) is not None
        assert purger.deleted == [] and await count(api.db, PurgeLedger) == 0
    else:
        assert result.status_code == 200 and await row(api.db, Room, api.room) is None


@pytest.mark.parametrize("kind, status, holds", [("CONCEALED_WORKS", "DRAFT", True), ("CONCEALED_WORKS", "ISSUED", True), ("CONCEALED_WORKS", "ARCHIVED", False), ("ACCEPTANCE_SURFACE", "DRAFT", True)])
async def test_a_document_that_names_the_surface_holds_the_surface(api, http, purger, kind, status, holds):
    api.db.add(holder(kind, status, api))
    await api.db.commit()
    await archive(http, surface_url(api))
    result = await http.post(f"{surface_url(api)}/purge")
    assert (result.status_code == 409) is holds
    assert (await row(api.db, Surface, api.surface) is not None) is holds


async def test_a_protocol_that_uses_a_photo_of_the_room_as_evidence_holds_the_room(api, http, purger):
    made = await upload(api)
    api.db.add(ConcealedWorksProtocol(owner_id=api.me, project_id=api.project, sequence=1, status="DRAFT", photo_ids=[made["attachment"]["id"]]))
    await api.db.commit()
    await archive(http, room_url(api))
    result = await http.post(f"{room_url(api)}/purge")
    assert result.status_code == 409 and code(result) == "STRUCTURE_PURGE_BLOCKED"
    assert await row(api.db, PhotoAttachment, made["attachment"]["id"]) is not None


async def test_a_document_of_another_room_does_not_hold_this_one(api, http, purger):
    other_room_id = (await _make_room(api.db, api.project, name="Kuchnia")).id
    api.db.add(AcceptanceProtocol(owner_id=api.me, project_id=api.project, sequence=1, status="ISSUED", room_ids=[str(other_room_id)], surfaces={},
                                  issued_at=NOW, snapshot={}, document_html="<p>x</p>"))
    await api.db.commit()
    await archive(http, room_url(api))
    assert (await http.post(f"{room_url(api)}/purge")).status_code == 200


# ------------------------------------------------------------------ failures

async def test_a_failure_of_the_storage_after_the_rows_are_gone_loses_nothing_and_a_retry_finishes_it(api, http, purger):
    made = await upload(api)
    mine = await keys_of(api.db, made["asset"]["id"])
    await archive(http, room_url(api))
    purger.fault = MediaStorageUnavailable("storage down")
    result = await http.post(f"{room_url(api)}/purge")
    assert result.status_code == 200 and result.json() == {"purged": True, "photo_files": 1, "storage_pending": 1}
    assert await row(api.db, Room, api.room) is None and mine <= set(api.storage.keys())
    ledger = (await api.db.execute(select(PurgeLedger))).scalar_one()
    assert ledger.storage_state == "PENDING"
    purger.fault = None
    assert (await http.post("/api/photo-purge/retry")).json()["storage_pending"] == 0
    assert not (mine & set(api.storage.keys()))


async def test_a_photo_that_appears_meanwhile_stops_the_deletion_and_nothing_is_lost(api, http, purger):
    first = await upload(api)
    first_keys = await keys_of(api.db, first["asset"]["id"])
    await archive(http, room_url(api))
    template = await row(api.db, PhotoAttachment, first["attachment"]["id"])
    fired: list[bool] = []

    def add_a_use_of_the_photo_in_the_surface_before_the_room_is_deleted(state):
        # the first DELETE of the photo markers is the first statement of the transaction: a new use of the file lands in it
        if state.is_delete and not fired and getattr(state.statement.table, "name", "") == "photo_annotations":
            fired.append(True)
            clone = {c.name: getattr(template, c.name) for c in PhotoAttachment.__table__.columns}
            clone.update(id=uuid.uuid4(), context="SURFACE", room_id=None, surface_id=api.surface)
            state.session.add(PhotoAttachment(**clone))

    event.listen(api.db.sync_session, "do_orm_execute", add_a_use_of_the_photo_in_the_surface_before_the_room_is_deleted)
    try:
        result = await http.post(f"{room_url(api)}/purge")
    finally:
        event.remove(api.db.sync_session, "do_orm_execute", add_a_use_of_the_photo_in_the_surface_before_the_room_is_deleted)
    assert fired and result.status_code == 409 and code(result) == "STRUCTURE_PURGE_CONFLICT"
    # all or nothing: the room, the photo and its file are all still here and no ledger row was written
    assert await row(api.db, Room, api.room) is not None and await row(api.db, PhotoAttachment, first["attachment"]["id"]) is not None
    assert await row(api.db, PhotoAsset, first["asset"]["id"]) is not None and first_keys <= set(api.storage.keys())
    assert await count(api.db, PurgeLedger) == 0 and purger.deleted == []


# ------------------------------------------------------------------ owners

async def test_nothing_of_another_owner_is_reachable(api, http, purger):
    await archive(http, room_url(api))
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as stranger:
        stranger.headers["Authorization"] = f"Bearer {api.other_token}"
        for method, url in (("get", f"{room_url(api)}/purge-preview"), ("post", f"{room_url(api)}/purge"),
                            ("get", f"{surface_url(api)}/purge-preview"), ("post", f"{surface_url(api)}/purge")):
            assert (await getattr(stranger, method)(url)).status_code == 404
    assert await row(api.db, Room, api.room) is not None
    # my own token cannot reach the other owner's room either, nor a room through another project
    assert (await http.get(f"/api/projects/{api.foreign_project}/rooms/{api.foreign_room}/purge-preview")).status_code == 404
    assert (await http.post(f"/api/projects/{api.project2}/rooms/{api.room}/purge")).status_code == 404
    assert await row(api.db, Room, api.foreign_room) is not None


async def test_the_deletion_needs_a_signed_in_user(api, purger):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anonymous:
        for method, url in (("get", f"{room_url(api)}/purge-preview"), ("post", f"{room_url(api)}/purge"), ("post", f"{surface_url(api)}/purge")):
            assert (await getattr(anonymous, method)(url)).status_code in (401, 403)
