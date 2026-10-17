"""Invoices and advances IA-3 -- photos of receipts and invoices: the context PAYMENT (HTTP over the real routes, in-memory storage).

What matters: a photo is kept with one settlement record of the SAME object and owner; the target shape is strict (the record and nothing
else); the photos of records never leak into the site photos, the counts of the object, the photo report or the protocols; they appear in
the owner's archive with the record named; archive, trash and the final deletion work as for every other photo; and the object's own
deletion takes the records and their photos away together.
"""
import uuid
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api import deps
from app.domain.services.media_purger import InMemoryMediaPurger
from app.main import app
from app.models.photo_asset import PhotoAsset
from app.models.photo_attachment import PhotoAttachment, PhotoAttachmentContext
from app.models.project_payment import ProjectPayment
from tests import test_stage14c4_photos_api as c4
from tests.test_stage14c4_photos_api import call, form, path_for
from tests.test_stage14c5_photos_api import code, upload
from tests.test_stage14i1_photo_report_read_model import C, build, photo, world

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


def base_of(a) -> str:
    return f"/api/projects/{a.project}"


async def record(db, owner, project, *, kind="EXPENSE", title="Farba", archived=False) -> uuid.UUID:
    row = ProjectPayment(owner_id=owner, project_id=project, kind=kind, title=title, amount_gross=10, occurred_on=NOW.date(), is_archived=archived)
    db.add(row)
    await db.commit()
    return row.id


async def receipt(api, payment_id, **kw) -> dict:
    return await upload(api, context="PAYMENT", target=("payment_id", str(payment_id)), **kw)


async def count(db, model) -> int:
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


# ------------------------------------------------------------------ uploading

async def test_a_receipt_is_kept_with_its_record(api, http):
    payment = await record(api.db, api.me, api.project)
    made = await receipt(api, payment)
    attachment = made["attachment"]
    assert attachment["context"] == "PAYMENT" and attachment["payment_id"] == str(payment)
    for column in ("room_id", "surface_id", "opening_id", "inspection_id", "question_id", "finding_id", "occurrence_key", "price_item_id"):
        assert attachment[column] is None


async def test_the_record_is_required_and_nothing_else_is_allowed(api, http):
    payment = await record(api.db, api.me, api.project)
    missing = await call(path_for(api.project), token=api.token, body=form(api, context="PAYMENT", target=("caption", "")))
    assert (missing.status, c4.detail(missing)["code"]) == (422, "PHOTO_UPLOAD_MALFORMED")
    for extra in (("room_id", str(api.room)), ("surface_id", str(api.surface))):
        mixed = await call(path_for(api.project), token=api.token, body=form(api, context="PAYMENT", target=("payment_id", str(payment)), extra=(extra,)))
        assert (mixed.status, c4.detail(mixed)["code"]) == (422, "PHOTO_UPLOAD_MALFORMED")
    # another context cannot carry the record either
    wrong = await call(path_for(api.project), token=api.token, body=form(api, context="ROOM", extra=(("payment_id", str(payment)),)))
    assert (wrong.status, c4.detail(wrong)["code"]) == (422, "PHOTO_UPLOAD_MALFORMED")
    assert await count(api.db, PhotoAttachment) == 0


async def test_a_record_of_another_object_another_owner_or_nowhere_is_not_found(api, http):
    other_object = await record(api.db, api.me, api.project2)
    foreign = await record(api.db, api.other, api.foreign_project)
    for payment in (other_object, foreign, uuid.uuid4()):
        r = await call(path_for(api.project), token=api.token, body=form(api, context="PAYMENT", target=("payment_id", str(payment))))
        assert (r.status, c4.detail(r)["code"]) == (404, "PAYMENT_NOT_FOUND")
    # a record that names this object but another owner (a damaged row) is still not this owner's: the owner is checked on its own
    damaged = await record(api.db, api.other, api.project)
    r = await call(path_for(api.project), token=api.token, body=form(api, context="PAYMENT", target=("payment_id", str(damaged))))
    assert (r.status, c4.detail(r)["code"]) == (404, "PAYMENT_NOT_FOUND")
    # the owner of the record cannot use it through an object that is not theirs
    mine = await record(api.db, api.me, api.project)
    r = await call(path_for(api.foreign_project), token=api.token, body=form(api, context="PAYMENT", target=("payment_id", str(mine))))
    assert r.status == 404
    assert await count(api.db, PhotoAttachment) == 0


async def test_an_archived_record_still_takes_photos(api, http):
    payment = await record(api.db, api.me, api.project, archived=True)
    assert (await receipt(api, payment))["attachment"]["payment_id"] == str(payment)


async def test_the_same_upload_sent_again_is_not_a_second_photo(api, http):
    payment = await record(api.db, api.me, api.project)
    upload_id = str(uuid.uuid4())
    first = await receipt(api, payment, upload_id=upload_id)
    sent_again = await call(
        path_for(api.project), token=api.token, body=form(api, upload_id=upload_id, context="PAYMENT", target=("payment_id", str(payment)))
    )
    assert sent_again.status == 200  # the answer of the first try, not a new photo
    again = sent_again.json()
    assert first["asset"]["id"] == again["asset"]["id"]
    assert await count(api.db, PhotoAttachment) == 1


# ------------------------------------------------------------------ reading

async def test_the_photos_of_one_record_are_listed_apart_from_the_others(api, http):
    one, two = await record(api.db, api.me, api.project, title="A"), await record(api.db, api.me, api.project, title="B")
    a = await receipt(api, one)
    await receipt(api, two)
    await upload(api, context="ROOM")
    listed = (await http.get(f"{base_of(api)}/photos", params={"context": "PAYMENT", "payment_id": str(one)})).json()
    assert [item["attachment"]["id"] for item in listed["items"]] == [a["attachment"]["id"]]
    # like every other context the list names its target: all the receipts at once are not a list
    assert (await http.get(f"{base_of(api)}/photos", params={"context": "PAYMENT"})).status_code == 422


async def test_a_record_filter_needs_its_context_and_a_known_record(api, http):
    payment = await record(api.db, api.me, api.project)
    assert (await http.get(f"{base_of(api)}/photos", params={"payment_id": str(payment)})).status_code == 422
    assert (await http.get(f"{base_of(api)}/photos", params={"context": "ROOM", "room_id": str(api.room), "payment_id": str(payment)})).status_code == 422
    unknown = await http.get(f"{base_of(api)}/photos", params={"context": "PAYMENT", "payment_id": str(uuid.uuid4())})
    assert unknown.status_code == 404 and code(unknown) == "PAYMENT_NOT_FOUND"
    assert (await http.get(f"{base_of(api)}/photos", params={"site_only": "true", "payment_id": str(payment)})).status_code == 422


async def test_the_site_photos_of_the_object_leave_receipts_out(api, http):
    payment = await record(api.db, api.me, api.project)
    await receipt(api, payment)
    site = await upload(api, context="PROJECT")
    listed = (await http.get(f"{base_of(api)}/photos", params={"site_only": "true"})).json()
    assert [item["attachment"]["id"] for item in listed["items"]] == [site["attachment"]["id"]]


async def test_the_counts_are_per_record_and_never_in_the_site_numbers(api, http):
    one, two = await record(api.db, api.me, api.project), await record(api.db, api.me, api.project)
    await receipt(api, one)
    await receipt(api, one)
    made = await receipt(api, two)
    await upload(api, context="PROJECT")
    counts = (await http.get(f"{base_of(api)}/photos/counts")).json()
    assert counts["payments"] == {str(one): 2, str(two): 1}
    assert counts["project"] == 1 and counts["rooms"] == {} and counts["room_totals"] == {}
    await http.post(f"{base_of(api)}/photo-attachments/{made['attachment']['id']}/archive")
    assert (await http.get(f"{base_of(api)}/photos/counts")).json()["payments"] == {str(one): 2}


async def test_a_photo_of_a_record_is_shown_again_on_the_record_once_attached(api, http):
    payment = await record(api.db, api.me, api.project)
    made = await upload(api, context="ROOM")
    attached = await http.post(f"{base_of(api)}/photos/{made['asset']['id']}/attachments", json={"context": "PAYMENT", "payment_id": str(payment)})
    assert attached.status_code == 201 and attached.json()["payment_id"] == str(payment)
    again = await http.post(f"{base_of(api)}/photos/{made['asset']['id']}/attachments", json={"context": "PAYMENT", "payment_id": str(payment)})
    assert again.status_code == 409
    missing = await http.post(f"{base_of(api)}/photos/{made['asset']['id']}/attachments", json={"context": "PAYMENT"})
    assert missing.status_code == 422
    foreign = await http.post(f"{base_of(api)}/photos/{made['asset']['id']}/attachments", json={"context": "PAYMENT", "payment_id": str(uuid.uuid4())})
    assert foreign.status_code == 404 and code(foreign) == "PAYMENT_NOT_FOUND"


# ------------------------------------------------------------------ the archive, the trash, the deletion

async def test_an_archived_receipt_is_in_the_archive_of_all_objects_with_its_record_named(api, http):
    payment = await record(api.db, api.me, api.project, kind="INVOICE", title="Faktura za etap 1")
    made = await receipt(api, payment)
    await http.post(f"{base_of(api)}/photo-attachments/{made['attachment']['id']}/archive")
    body = (await http.get("/api/photos/archive")).json()
    item = body["items"][0]
    assert item["attachment"]["id"] == made["attachment"]["id"] and item["project_name"]
    assert (item["place"]["payment_title"], item["place"]["payment_kind"]) == ("Faktura za etap 1", "INVOICE")
    assert item["place"]["room_name"] is None and item["place"]["surface_name"] is None


async def test_a_receipt_goes_through_the_trash_and_is_deleted_for_good_like_any_photo(api, http, purger):
    payment = await record(api.db, api.me, api.project)
    made = await receipt(api, payment)
    att_id = made["attachment"]["id"]
    assert (await http.post(f"{base_of(api)}/photo-attachments/{att_id}/archive")).status_code == 200
    assert (await http.post(f"{base_of(api)}/photo-attachments/{att_id}/trash")).status_code == 200
    preview = (await http.get(f"{base_of(api)}/photo-attachments/{att_id}/purge-preview")).json()
    assert preview["can_purge"] is True and preview["blockers"] == []  # a receipt is no protocol evidence
    assert (await http.post(f"{base_of(api)}/photo-attachments/{att_id}/purge")).status_code == 200
    assert await count(api.db, PhotoAttachment) == 0
    assert await count(api.db, ProjectPayment) == 1  # the record stays, only its photo went


async def test_an_object_with_records_and_receipts_is_deleted_whole(api, http, purger):
    payment = await record(api.db, api.me, api.project)
    await receipt(api, payment)
    await receipt(api, payment)
    kept = await record(api.db, api.me, api.project2)
    assert (await http.post(f"{base_of(api)}/archive")).status_code == 200
    preview = (await http.get(f"{base_of(api)}/purge-preview")).json()
    assert preview["payments"] == 1 and preview["photos"] == 2 and preview["can_purge"] is True
    assert (await http.post(f"{base_of(api)}/purge")).status_code == 200
    assert await count(api.db, PhotoAttachment) == 0 and await count(api.db, PhotoAsset) == 0
    assert (await api.db.execute(select(ProjectPayment.id))).scalars().all() == [kept]


# ------------------------------------------------------------------ what the receipts never reach

async def test_a_receipt_is_never_in_the_photo_report_even_when_selected(db_session):
    w = await world(db_session)
    payment = await record(db_session, w.me.id, w.project.id)
    _, att = await photo(db_session, w, C.PAYMENT, include=True, payment_id=payment)
    _, site = await photo(db_session, w, C.PROJECT, include=True)
    for only_included in (True, False):
        report = await build(db_session, w, only_included=only_included)
        seen = [p.attachment_id for p in report.project_photos] + [p.attachment_id for room in report.rooms for p in room.photos]
        assert seen == [site.id] and att.id not in seen


# ------------------------------------------------------------------ the database itself

async def _insert(db, **fields):
    row = PhotoAttachment(**fields)
    db.add(row)
    await db.commit()


async def test_the_database_refuses_a_receipt_without_a_record_and_a_record_on_another_context(api):
    payment = await record(api.db, api.me, api.project)
    made = await receipt(api, payment)
    asset_id = uuid.UUID(made["asset"]["id"])
    for fields in (
        {"context": PhotoAttachmentContext.PAYMENT},                                        # no record
        {"context": PhotoAttachmentContext.PAYMENT, "payment_id": payment, "room_id": api.room},   # a record and a room
        {"context": PhotoAttachmentContext.ROOM, "room_id": api.room, "payment_id": payment},      # a room photo with a record
        {"context": PhotoAttachmentContext.PROJECT, "payment_id": payment},                          # an object photo with a record
        {"context": PhotoAttachmentContext.SURFACE, "surface_id": api.surface, "payment_id": payment},
    ):
        with pytest.raises(IntegrityError):
            await _insert(api.db, asset_id=asset_id, project_id=api.project, **fields)
        await api.db.rollback()


async def test_the_database_allows_one_active_receipt_of_a_file_per_record(api):
    payment = await record(api.db, api.me, api.project)
    made = await receipt(api, payment)
    asset_id = uuid.UUID(made["asset"]["id"])
    with pytest.raises(IntegrityError):
        await _insert(api.db, asset_id=asset_id, project_id=api.project, context=PhotoAttachmentContext.PAYMENT, payment_id=payment)
    await api.db.rollback()
    other = await record(api.db, api.me, api.project, title="Inny")
    await _insert(api.db, asset_id=asset_id, project_id=api.project, context=PhotoAttachmentContext.PAYMENT, payment_id=other)  # another record is fine
