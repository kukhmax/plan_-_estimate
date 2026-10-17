"""Invoices and advances IA-7 -- the archived settlement records on the archive page and their final deletion (HTTP over the real routes)."""
import datetime
import uuid

import pytest
from sqlalchemy import select

from app.domain.exceptions import MediaStorageUnavailable
from app.domain.services.photo_attachment_service import AttachmentTarget, PhotoAttachmentService
from app.models.photo_asset import PhotoAsset
from app.models.photo_attachment import PhotoAttachment, PhotoAttachmentContext
from app.models.project import Project
from app.models.project_payment import ProjectPayment
from app.models.purge_ledger import DONE, PENDING, PurgeLedger
from tests.test_ia3_payment_photos import api, base_of, count, http, purger, receipt, record  # noqa: F401  (fixtures and helpers)


def url(a, payment, tail="") -> str:
    return f"{base_of(a)}/payments/{payment}{tail}"


# ------------------------------------------------------------------ the list

async def test_the_archive_lists_archived_records_of_objects_in_work_with_the_object_named(api, http):
    old = await record(api.db, api.me, api.project, kind="INVOICE", title="Faktura stara", archived=True)
    await record(api.db, api.me, api.project, title="Aktywny wydatek")
    second = await record(api.db, api.me, api.project, title="Wydatek z paragonem", archived=True)
    await receipt(api, second)
    third = await record(api.db, api.me, api.project2, title="Wydatek z drugiego obiektu", archived=True)
    body = (await http.get("/api/archive/payments")).json()
    assert body["total"] == 3
    by_id = {item["id"]: item for item in body["items"]}
    assert set(by_id) == {str(old), str(second), str(third)}
    assert (by_id[str(old)]["kind"], by_id[str(old)]["amount_gross"], by_id[str(old)]["photos"]) == ("INVOICE", "10.00", 0)
    assert by_id[str(second)]["photos"] == 1
    assert by_id[str(old)]["project_id"] == str(api.project) and by_id[str(third)]["project_id"] == str(api.project2)
    names = (await api.db.execute(select(Project.id, Project.name).where(Project.id.in_([api.project, api.project2])))).all()
    assert {item["project_id"]: item["project_name"] for item in body["items"]} == {str(i): n for i, n in names}


async def test_nothing_of_an_archived_object_or_of_another_owner_is_listed(api, http):
    await record(api.db, api.me, api.project, title="W archiwalnym obiekcie", archived=True)
    await record(api.db, api.other, api.foreign_project, title="Cudzy", archived=True)
    project = (await api.db.execute(select(Project).where(Project.id == api.project))).scalar_one()
    project.is_archived = True
    await api.db.commit()
    body = (await http.get("/api/archive/payments")).json()
    assert body == {"items": [], "total": 0}


async def test_the_list_holds_the_newest_two_hundred_and_the_total_is_whole(api, http):
    for number in range(203):
        await record(api.db, api.me, api.project, title=f"Wydatek {number}", archived=True)
    body = (await http.get("/api/archive/payments")).json()
    assert len(body["items"]) == 200 and body["total"] == 203


async def test_the_routes_need_a_token(api):
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anonymous:
        assert (await anonymous.get("/api/archive/payments")).status_code in (401, 403)
        some = uuid.uuid4()
        assert (await anonymous.post(f"/api/projects/{api.project}/payments/{some}/purge")).status_code in (401, 403)
        assert (await anonymous.get(f"/api/projects/{api.project}/payments/{some}/purge-preview")).status_code in (401, 403)


# ------------------------------------------------------------------ the preview

async def test_the_preview_counts_what_goes_and_says_whether_it_can(api, http):
    invoice = await record(api.db, api.me, api.project, kind="INVOICE", title="Faktura", archived=True)
    pay = ProjectPayment(owner_id=api.me, project_id=api.project, kind="PAYMENT", title="Wpłata", amount_gross=5, occurred_on=datetime.date(2026, 10, 1), settles_id=invoice)
    api.db.add(pay)
    await api.db.commit()
    await receipt(api, invoice)
    preview = (await http.get(url(api, invoice, "/purge-preview"))).json()
    assert preview["archived"] is True and preview["can_purge"] is True and preview["kind"] == "INVOICE"
    assert (preview["tied_payments"], preview["photos"], preview["photo_files"]) == (1, 1, 1)
    assert preview["bytes"] > 0 and preview["may_be_in_backups"] is True
    # a record that is in work cannot be deleted and says so
    active = await record(api.db, api.me, api.project, title="Aktywny")
    live = (await http.get(url(api, active, "/purge-preview"))).json()
    assert live["archived"] is False and live["can_purge"] is False and live["photos"] == 0 and live["may_be_in_backups"] is False


async def test_a_record_of_another_owner_or_object_or_nowhere_is_not_found(api, http):
    foreign = await record(api.db, api.other, api.foreign_project, archived=True)
    elsewhere = await record(api.db, api.me, api.project2, archived=True)
    for target in (f"/api/projects/{api.foreign_project}/payments/{foreign}", f"{base_of(api)}/payments/{elsewhere}", f"{base_of(api)}/payments/{uuid.uuid4()}"):
        assert (await http.get(f"{target}/purge-preview")).status_code == 404
        assert (await http.post(f"{target}/purge")).status_code == 404
    assert await count(api.db, ProjectPayment) == 2


# ------------------------------------------------------------------ the deletion

async def test_a_record_in_work_is_not_deleted(api, http):
    active = await record(api.db, api.me, api.project)
    r = await http.post(url(api, active, "/purge"))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "PAYMENT_NOT_ARCHIVED"
    assert await count(api.db, ProjectPayment) == 1


async def test_an_archived_record_without_photos_is_deleted_and_the_sums_follow(api, http):
    invoice = await record(api.db, api.me, api.project, kind="INVOICE", title="Faktura", archived=True)
    keep = ProjectPayment(owner_id=api.me, project_id=api.project, kind="PAYMENT", title="Wpłata", amount_gross=5, occurred_on=datetime.date(2026, 10, 1), settles_id=invoice)
    api.db.add(keep)
    await api.db.commit()
    r = await http.post(url(api, invoice, "/purge"))
    assert r.status_code == 200 and r.json() == {"purged": True, "photo_files": 0, "storage_pending": 0}
    rows = (await api.db.execute(select(ProjectPayment))).scalars().all()
    assert [(row.id, row.settles_id) for row in rows] == [(keep.id, None)]  # the money stays, only the link is gone
    listing = (await http.get(f"{base_of(api)}/payments")).json()
    assert listing["summary"]["invoiced"] == "0.00" and listing["summary"]["received"] == "5.00"
    assert (await http.get("/api/archive/payments")).json() == {"items": [], "total": 0}
    assert (await http.post(url(api, invoice, "/purge"))).status_code == 404  # twice is not a success: it is gone


async def test_the_photos_of_the_record_and_their_files_go_with_it_through_the_ledger(api, http, purger):
    payment = await record(api.db, api.me, api.project, archived=True)
    await receipt(api, payment)
    await receipt(api, payment)
    assets_before = await count(api.db, PhotoAsset)
    assert assets_before == 2
    r = await http.post(url(api, payment, "/purge"))
    assert r.status_code == 200 and r.json() == {"purged": True, "photo_files": 2, "storage_pending": 0}
    assert await count(api.db, PhotoAttachment) == 0 and await count(api.db, PhotoAsset) == 0 and await count(api.db, ProjectPayment) == 0
    ledger = (await api.db.execute(select(PurgeLedger))).scalars().all()
    assert len(ledger) == 2 and {row.storage_state for row in ledger} == {DONE} and {row.kind for row in ledger} == {"PHOTO"}
    assert len(purger.deleted) == 6  # three objects of each file set left the storage


async def test_a_file_that_another_photo_still_uses_stays(api, http, purger):
    first = await record(api.db, api.me, api.project, title="A", archived=True)
    second = await record(api.db, api.me, api.project, title="B")
    made = await receipt(api, first)
    await PhotoAttachmentService(api.db).create_attachment(
        owner_id=api.me, project_id=api.project, asset_id=uuid.UUID(made["attachment"]["asset_id"]),
        target=AttachmentTarget(context=PhotoAttachmentContext.PAYMENT, payment_id=second),
    )
    preview = (await http.get(url(api, first, "/purge-preview"))).json()
    assert (preview["photos"], preview["photo_files"], preview["bytes"]) == (1, 0, 0)
    r = await http.post(url(api, first, "/purge"))
    assert r.json() == {"purged": True, "photo_files": 0, "storage_pending": 0}
    assert await count(api.db, PhotoAsset) == 1 and await count(api.db, PurgeLedger) == 0 and purger.deleted == []
    left = (await api.db.execute(select(PhotoAttachment))).scalars().all()
    assert [a.payment_id for a in left] == [second]


async def test_when_the_storage_fails_the_record_is_gone_nothing_is_lost_and_a_retry_finishes(api, http, purger):
    payment = await record(api.db, api.me, api.project, archived=True)
    await receipt(api, payment)
    purger.fault = MediaStorageUnavailable("storage down")
    r = await http.post(url(api, payment, "/purge"))
    assert r.status_code == 200 and r.json()["storage_pending"] == 1
    assert await count(api.db, ProjectPayment) == 0
    assert [row.storage_state for row in (await api.db.execute(select(PurgeLedger))).scalars()] == [PENDING]
    assert (await http.post("/api/photo-purge/retry")).status_code == 200
    assert {row.storage_state for row in (await api.db.execute(select(PurgeLedger))).scalars()} == {DONE}


async def test_a_photo_that_appears_meanwhile_stops_the_deletion_and_nothing_is_lost(api, http, purger, monkeypatch):
    from app.domain.services.payment_purge_service import PaymentPurgeService

    payment = await record(api.db, api.me, api.project, archived=True)
    await receipt(api, payment)

    async def blind(self, payment_id):  # the lists were read before the photo was added
        return []

    monkeypatch.setattr(PaymentPurgeService, "_attachments", blind)
    r = await http.post(url(api, payment, "/purge"))
    assert r.status_code == 409 and r.json()["detail"]["code"] == "PAYMENT_PURGE_CONFLICT"
    monkeypatch.undo()
    assert await count(api.db, ProjectPayment) == 1 and await count(api.db, PhotoAttachment) == 1 and await count(api.db, PhotoAsset) == 1


async def test_the_final_deletion_does_not_touch_the_other_records(api, http):
    gone = await record(api.db, api.me, api.project, title="Do usunięcia", archived=True)
    kept_archived = await record(api.db, api.me, api.project, title="Zostaje w archiwum", archived=True)
    kept_active = await record(api.db, api.me, api.project, title="Zostaje aktywny")
    await http.post(url(api, gone, "/purge"))
    ids = set((await api.db.execute(select(ProjectPayment.id))).scalars())
    assert ids == {kept_archived, kept_active}
    assert [i["id"] for i in (await http.get("/api/archive/payments")).json()["items"]] == [str(kept_archived)]


async def test_restoring_a_listed_record_takes_it_off_the_archive_list(api, http):
    payment = await record(api.db, api.me, api.project, title="Wróci", archived=True)
    assert (await http.post(url(api, payment, "/restore"))).status_code == 200
    assert (await http.get("/api/archive/payments")).json() == {"items": [], "total": 0}
