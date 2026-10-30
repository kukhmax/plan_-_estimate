"""V2-8d -- the measurements with the photos of the surfaces: which photos, where on the page, what never gets in, the limit, the routes."""
import io
import re
import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from pypdf import PdfReader
from sqlalchemy import select

from app.domain.documents.measurements_document import MeasurementsDocumentService
from app.domain.exceptions import DocumentDataError, ProjectNotFoundError
from app.models.issued_document import IssuedDocument
from app.models.photo_attachment import PhotoAttachment
from app.models.photo_attachment import PhotoAttachmentContext as C
from app.models.surface import Surface, SurfaceType
from tests.test_clients import OTHER_USER
from tests.test_stage15e_photo_report import CountingStorage
from tests.test_stage15f2_api import login, use_issuer  # noqa: F401  (a fixture)
from tests.test_stage15f2_issuing import Delivery, issuer
from tests.test_v2_8c_measurements import DAY, OWNER_TG, pdf_text, world


async def plane(db, room, surface_type) -> Surface:
    found = (
        await db.execute(select(Surface).where(Surface.room_id == room.id, Surface.surface_type == surface_type, Surface.is_archived.is_(False)))
    ).scalars().first()
    if found is None:  # a room made without the canonical planes: the test makes one
        found = Surface(room_id=room.id, name=surface_type.value.title(), surface_type=surface_type)
        db.add(found)
        await db.commit()
    return found


async def photographed(db):
    """The world of the measurements with photos: two on the ceiling of "Klatka", one on its floor, two on its first wall (one of them not marked
    for the photo report), none on its second wall, one on a wall of "Salon"; and some that must never be printed."""
    w = await world(db)
    ceiling, floor = await plane(db, w.klatka, SurfaceType.CEILING), await plane(db, w.klatka, SurfaceType.FLOOR)
    w.ceiling = [await w.attach(C.SURFACE, 100 + n, surface_id=ceiling.id) for n in range(2)]
    w.floor = [await w.attach(C.SURFACE, 110, surface_id=floor.id)]
    w.first_photos = [await w.attach(C.SURFACE, 120, surface_id=w.first.id), await w.attach(C.SURFACE, 121, surface_id=w.first.id, include=False)]
    w.salon_photo = await w.attach(C.SURFACE, 130, surface_id=w.walls[0].id)
    # never printed: a photo of the room itself, of the object, of an opening's neighbour (the inspection), and an archived attachment
    await w.attach(C.ROOM, 140, room_id=w.klatka.id)
    await w.attach(C.PROJECT, 141)
    archived = await w.attach(C.SURFACE, 142, surface_id=w.second.id)
    attachment = (await db.execute(select(PhotoAttachment).where(PhotoAttachment.asset_id == archived.id))).scalar_one()
    attachment.archived_at = datetime.now(UTC)
    await db.commit()
    return w


def service(db, w, **kw) -> MeasurementsDocumentService:
    return MeasurementsDocumentService(db, w.service(**kw))


async def build(db, w, *, with_photos=True, **kw):
    return await service(db, w, **kw.pop("service", {})).build(w.owner.id, w.project.id, working=False, issued_on=DAY, with_photos=with_photos, **kw)


# --- which photos ---------------------------------------------------------------------------------------------------------------------------


async def test_the_photos_of_the_surfaces_are_printed_where_they_belong(db_session):
    w = await photographed(db_session)
    document = await build(db_session, w)
    klatka = next(block for block in document.rooms if block.name == "Klatka")
    salon = next(block for block in document.rooms if block.name == "Salon")
    assert len(klatka.ceiling.photos) == 2 and len(klatka.floor.photos) == 1
    by_name = {wall.name: wall for wall in klatka.walls}
    assert len(by_name["Parter (przy windzie)"].photos) == 2  # the one not marked for the photo report as well
    assert by_name["Ściana 2"].photos == () and by_name["Ściana 3"].photos == ()  # none, or only an archived one: nothing is added
    assert [len(wall.photos) for wall in salon.walls] == [1, 0, 0, 0]
    assert len(document.assets) == 6 and all(name.endswith(".jpg") for name in document.assets)


async def test_the_page_puts_the_ceiling_photos_before_the_sizes_and_the_wall_photos_after_the_wall(db_session):
    w = await photographed(db_session)
    document = await build(db_session, w)
    html = MeasurementsDocumentService.html(document)
    klatka = html[html.index("<h2>Klatka</h2>"):]
    ceiling = klatka[klatka.index("Sufit: "):]
    assert ceiling.index("assets/") < ceiling.index("pierwsze piętro")  # the photos stand under the heading, then the rows
    wall_one = klatka[klatka.index("Parter (przy windzie)"):]
    wall_two = wall_one.index("Ściana 2")
    assert 0 < wall_one.index("assets/") < wall_two and wall_one.count("assets/", 0, wall_two) == 2  # under its own wall, before the next one
    assert re.findall(r'src="assets/(p\d+\.jpg)"', html) and all(f'assets/{name}' in html for name in document.assets)


async def test_without_the_choice_nothing_is_printed_and_no_picture_is_read(db_session):
    w = await photographed(db_session)
    counting = CountingStorage(w.storage)
    plain = MeasurementsDocumentService(db_session, __import__("app.domain.documents.photo_report_document", fromlist=["x"]).PhotoReportDocumentService(db_session, counting, storage_name="r2-primary", max_photos=60))
    document = await plain.build(w.owner.id, w.project.id, working=False, issued_on=DAY)
    assert document.assets == {} and "<img" not in MeasurementsDocumentService.html(document) and counting.calls == 0
    assert all(not block.ceiling.photos and not any(wall.photos for wall in block.walls) for block in document.rooms)


async def test_a_plane_without_rows_still_shows_its_photos_under_its_heading(db_session):
    w = await photographed(db_session)
    document = await build(db_session, w)
    klatka = next(block for block in document.rooms if block.name == "Klatka")
    assert klatka.floor.rows == () and len(klatka.floor.photos) == 1  # no rectangle and no segment: only the photo
    html = MeasurementsDocumentService.html(document)
    start = html.index("<h2>Klatka</h2>")
    end = html.find("<h2>", start + 1)  # the rooms follow the order they were entered (UX walk): Klatka may be the last one
    assert html[start:end if end != -1 else len(html)].count("Podłoga: ") == 1


async def test_the_photos_of_another_object_and_owner_never_get_in(db_session):
    w = await photographed(db_session)
    other = await photographed_other(db_session)
    document = await build(db_session, w)
    mine = {a.storage_key_display for a in w.assets}
    assert not (mine & {a.storage_key_display for a in other.assets})
    assert len(document.assets) == 6
    with pytest.raises(ProjectNotFoundError):
        await service(db_session, other).build(other.owner.id, w.project.id, working=False, issued_on=DAY, with_photos=True)


async def photographed_other(db):
    from tests.test_v2_8c_measurements import world as make_world

    other = await make_world(db, telegram_id=OWNER_TG + 77)
    surface = await plane(db, other.klatka, SurfaceType.CEILING)
    await other.attach(C.SURFACE, 200, surface_id=surface.id)
    return other


# --- the limit and the store ------------------------------------------------------------------------------------------------------------------


async def test_too_many_photos_are_refused_before_any_picture_is_read(db_session):
    w = await photographed(db_session)
    counting = CountingStorage(w.storage)
    from app.domain.documents.photo_report_document import PhotoReportDocumentService

    limited = MeasurementsDocumentService(db_session, PhotoReportDocumentService(db_session, counting, storage_name="r2-primary", max_photos=5))
    with pytest.raises(DocumentDataError) as caught:
        await limited.build(w.owner.id, w.project.id, working=True, issued_on=DAY, with_photos=True)
    assert caught.value.reason == "MEASUREMENTS_PHOTO_LIMIT_EXCEEDED" and caught.value.details == {"count": 6, "limit": 5} and counting.calls == 0
    plain = await limited.build(w.owner.id, w.project.id, working=True, issued_on=DAY)  # without the photos the limit does not matter
    assert plain.assets == {}


async def test_a_photo_that_is_gone_from_the_store_stops_the_document(db_session):
    w = await photographed(db_session)
    del w.storage._objects[w.ceiling[0].storage_key_display]
    with pytest.raises(DocumentDataError) as caught:
        await build(db_session, w)
    assert caught.value.reason == "PHOTO_UNAVAILABLE"
    assert (await build(db_session, w, with_photos=False)).assets == {}


async def test_only_checking_does_not_read_a_picture(db_session):
    w = await photographed(db_session)
    del w.storage._objects[w.ceiling[0].storage_key_display]  # would fail if it were read
    document = await build(db_session, w, read_photos=False)
    assert document.assets == {} and all(not block.ceiling.photos for block in document.rooms)


# --- the routes and a real PDF ------------------------------------------------------------------------------------------------------------------


def pictures(pdf: bytes) -> int:
    """The different pictures in the PDF (the renderer lists a picture in the resources of every page)."""
    return len({image.name for page in PdfReader(io.BytesIO(pdf)).pages for image in page.images})


async def test_issuing_with_photos_prints_them_and_remembers_the_choice(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await photographed(db_session)
    sender = Delivery()
    run = use_issuer(issuer(w.storage, delivery=sender))
    headers = await login(async_client)
    response = await async_client.post(f"/api/projects/{w.project.id}/documents", json={"kind": "MEASUREMENTS", "with_photos": True}, headers=headers)
    assert response.status_code == 202, response.text
    await run.drain()
    (sent,) = sender.sent
    assert pictures(sent["pdf"]) == 6 and "5,20 × 3,60 = 18,72 m²" in pdf_text(sent["pdf"])
    row = (await db_session.execute(select(IssuedDocument))).scalar_one()
    assert row.scope == {"with_photos": True} and row.kind == "MEASUREMENTS" and row.number.startswith("OBM/")
    again = await async_client.post(f"/api/projects/{w.project.id}/documents", json={"kind": "MEASUREMENTS"}, headers=headers)
    await run.drain()
    assert again.status_code == 202 and pictures(sender.sent[1]["pdf"]) == 0
    rows = (await db_session.execute(select(IssuedDocument).order_by(IssuedDocument.project_seq))).scalars().all()
    assert [r.scope for r in rows] == [{"with_photos": True}, None]


async def test_the_preview_with_photos(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await photographed(db_session)
    sender = Delivery()
    use_issuer(issuer(w.storage, delivery=sender))
    headers = await login(async_client)
    response = await async_client.post(f"/api/projects/{w.project.id}/documents/measurements/preview", json={"with_photos": True}, headers=headers)
    assert response.status_code == 200 and response.json()["sent"] is True
    assert pictures(sender.sent[0]["pdf"]) == 6 and "WERSJA ROBOCZA" in pdf_text(sender.sent[0]["pdf"])
    bare = await async_client.post(f"/api/projects/{w.project.id}/documents/measurements/preview", headers=headers)  # no body: as before
    assert bare.status_code == 200 and pictures(sender.sent[1]["pdf"]) == 0
    assert (await db_session.execute(select(IssuedDocument))).scalars().all() == []


async def test_too_many_photos_are_a_422_that_takes_no_number(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await photographed(db_session)
    run = use_issuer(issuer(w.storage, max_photos=3))
    headers = await login(async_client)
    for url, body in ((f"/api/projects/{w.project.id}/documents", {"kind": "MEASUREMENTS", "with_photos": True}),
                      (f"/api/projects/{w.project.id}/documents/measurements/preview", {"with_photos": True})):
        response = await async_client.post(url, json=body, headers=headers)
        detail = response.json()["detail"]
        assert (response.status_code, detail["code"]) == (422, "MEASUREMENTS_PHOTO_LIMIT_EXCEEDED") and detail["details"] == {"count": 6, "limit": 3}
    assert run.active == 0 and (await db_session.execute(select(IssuedDocument))).scalars().all() == []


async def test_with_photos_belongs_to_the_measurements_alone(async_client: AsyncClient, use_issuer):  # noqa: F811
    use_issuer(issuer())
    headers = await login(async_client)
    pid = uuid.uuid4()
    for kind in ("TECH_CARD", "PRODUCTION_PLAN", "SETTLEMENT", "PHOTO_REPORT"):
        assert (await async_client.post(f"/api/projects/{pid}/documents", json={"kind": kind, "with_photos": True}, headers=headers)).status_code == 422
    assert (await async_client.post(f"/api/projects/{pid}/documents/measurements/preview", json={"photos": True}, headers=headers)).status_code == 422


async def test_another_owner_gets_a_404_with_photos_too(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await photographed(db_session)
    use_issuer(issuer(w.storage))
    headers = await login(async_client, OTHER_USER)
    assert (await async_client.post(f"/api/projects/{w.project.id}/documents", json={"kind": "MEASUREMENTS", "with_photos": True}, headers=headers)).status_code == 404
    assert (await async_client.post(f"/api/projects/{w.project.id}/documents/measurements/preview", json={"with_photos": True}, headers=headers)).status_code == 404
