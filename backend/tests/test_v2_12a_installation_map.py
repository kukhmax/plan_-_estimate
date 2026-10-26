"""V2-12a -- the map of hidden utilities (Mapa instalacji ukrytych): which photos get in, what is printed, the two forms, the refusals, the real routes and a real PDF."""
import io
import re
import uuid
from datetime import date

import pytest
from app.domain.documents.installation_map_document import (
    InstallationMapDocumentService,
    build_installation_map_document,
    collect,
    has_utility,
)
from app.domain.documents.registry import DocumentKind, get_template
from app.domain.exceptions import DocumentDataError, ProjectNotFoundError
from app.domain.services.photo_report_read_model import ReportInspection, ReportMarker
from app.models.executor_profile import ExecutorProfile
from app.models.issued_document import IssuedDocument
from app.models.photo_annotation import PhotoAnnotation
from app.models.photo_attachment import PhotoAttachmentContext as C
from httpx import AsyncClient
from pypdf import PdfReader
from sqlalchemy import select

from tests.test_clients import OTHER_USER, VALID_USER
from tests.test_stage15e_photo_report import make_report, rphoto, seed
from tests.test_stage15f2_api import login, use_issuer  # noqa: F401  (a fixture)
from tests.test_stage15f2_issuing import Delivery, issuer

DAY = date(2026, 10, 27)
NBSP = " "
TG = 9610


def marker(utility=None, label=None, **kw):
    return ReportMarker(uuid.uuid4(), 0.4, 0.5, label, 0, None, utility, kw.get("depth"), kw.get("floor"), kw.get("corner"))


def pdf_text(pdf: bytes) -> str:
    return " ".join("\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages).replace(NBSP, " ").split())


def page_text(html: str) -> str:
    body = re.sub(r"<style.*?</style>", " ", html, flags=re.S)
    return " ".join(re.sub(r"<[^>]+>", " ", body).replace(NBSP, " ").split())


async def mark(db, w, asset, **fields):
    from app.models.photo_attachment import PhotoAttachment

    attachment = (await db.execute(select(PhotoAttachment).where(PhotoAttachment.asset_id == asset.id))).scalar_one()
    db.add(PhotoAnnotation(attachment_id=attachment.id, x=0.4, y=0.5, position=0, **fields))
    await db.commit()


async def build(db, w, **kw):
    return await InstallationMapDocumentService(db, w.service()).build(w.owner.id, w.project.id, working=kw.pop("working", False), issued_on=DAY, **kw)


# --- which photos get in ---------------------------------------------------------------------------------------------------------------------

def test_only_photos_with_a_utility_marker_get_in_each_once_with_its_place():
    report, _ = make_report()
    assert collect(report) == ()  # no marker names a utility in the plain report
    pipe = rphoto(C.ROOM, minute=20, markers=[marker("WATER_COLD", floor=30)])
    plain = rphoto(C.ROOM, minute=21, markers=[marker(None, "rysa"), marker("nope")])
    room = report.rooms[0]
    wall = room.surfaces[0]
    from dataclasses import replace

    wall = replace(wall, photos=wall.photos + (rphoto(C.SURFACE, minute=22, markers=[marker("CABLE")]),),
                   openings=(replace(wall.openings[0], photos=(rphoto(C.OPENING, minute=23, markers=[marker("GAS")]),)),))
    inspection = replace(room.inspections[0], photos=(rphoto(C.INSPECTION, minute=24, markers=[marker("SEWER")]),))
    room = replace(room, photos=room.photos + (pipe, plain), surfaces=(wall,), inspections=(inspection,) + room.inspections[1:])
    twin = rphoto(C.PROJECT, minute=25, markers=[marker("HEATING")])
    report = replace(report, project_photos=report.project_photos + (twin,), rooms=(room,) + report.rooms[1:])
    found = collect(report)
    assert [s.photo.markers[0].utility for s in found] == ["HEATING", "WATER_COLD", "CABLE", "GAS", "SEWER"]
    assert [s.room for s in found] == [None, "Salon", "Salon", "Salon", "Salon"]
    assert found[0].place == "Obiekt" and found[1].place == "Salon" and found[2].place == "Salon › Ściana A" and found[3].place.startswith("Salon › Ściana A › ")
    assert found[4].place.startswith("Salon › ")
    assert has_utility(pipe) and not has_utility(plain)


# --- the page ---------------------------------------------------------------------------------------------------------------------------------

async def seeded(db, telegram_id=TG):
    w = await seed(db, telegram_id=telegram_id)
    a = await w.attach(C.ROOM, 40, room_id=w.salon.id)
    b = await w.attach(C.SURFACE, 41, surface_id=w.wall.id)
    c = await w.attach(C.ROOM, 42, room_id=w.kuchnia.id)
    await mark(db, w, a, utility="CABLE", from_floor_cm=30, depth_cm=3, label="do gniazda")
    await mark(db, w, b, utility="WATER_COLD", from_corner_cm=12.5)
    await mark(db, w, c, label="tylko rysa")  # an ordinary marker: not on the map
    return w


async def test_the_page_prints_the_photos_by_room_with_colours_a_key_and_what_lies_where(db_session):
    w = await seeded(db_session)
    document = await build(db_session, w)
    assert document.photo_count == 2 and [g.title for g in document.groups] == ["Salon"]
    assert [k.name for k in document.keys] == ["przewód elektryczny", "woda zimna"]
    html = InstallationMapDocumentService.html(document)
    text = page_text(html)
    for expected in ("Mapa instalacji ukrytych", "Liczba zdjęć: 2", "Rodzaje instalacji", "Salon › Ściana A", "Oznaczenia: 1 – przewód elektryczny · do gniazda · od podłogi 30 cm · głębokość 3 cm",
                     "1 – woda zimna · od narożnika 12,5 cm", "Mokotów", "orientacyjnymi"):
        assert expected in text, expected
    assert "tylko rysa" not in text and "WERSJA ROBOCZA" not in text
    assert 'fill="#ea580c"' in html and 'fill="#2563eb"' in html  # the colours of the types on the dots
    assert not re.search(r"\b(photo_report|installation_map)\.[a-z_]+", html)


async def test_the_issued_form_needs_a_utility_photo_and_a_profile_and_the_working_form_never_refuses(db_session):
    w = await seed(db_session, telegram_id=TG + 1)
    with pytest.raises(DocumentDataError) as empty:
        await build(db_session, w)
    assert empty.value.reason == "INSTALLATION_MAP_EMPTY"
    draft = await build(db_session, w, working=True)
    assert draft.photo_count == 0 and "WERSJA ROBOCZA" in InstallationMapDocumentService.html(draft) and draft.layout.meta.number is None
    w2 = await seeded(db_session, telegram_id=TG + 2)
    await db_session.execute(ExecutorProfile.__table__.delete().where(ExecutorProfile.owner_id == w2.owner.id))
    await db_session.commit()
    with pytest.raises(DocumentDataError) as no_profile:
        await build(db_session, w2)
    assert no_profile.value.reason == "EXECUTOR_PROFILE_REQUIRED"
    assert InstallationMapDocumentService.html(await build(db_session, w2, working=True))


async def test_more_photos_than_a_document_holds_are_refused_before_a_picture_is_read(db_session):
    w = await seeded(db_session, telegram_id=TG + 3)
    service = InstallationMapDocumentService(db_session, w.service(max_photos=1))
    with pytest.raises(DocumentDataError) as caught:
        await service.build(w.owner.id, w.project.id, working=False, issued_on=DAY, read_photos=False)
    assert caught.value.reason == "INSTALLATION_MAP_PHOTO_LIMIT_EXCEEDED" and caught.value.details == {"count": 2, "limit": 1}


async def test_a_working_version_is_never_numbered_and_an_issued_one_has_no_watermark(db_session):
    w = await seeded(db_session, telegram_id=TG + 4)
    sources = await InstallationMapDocumentService(db_session, w.service()).sources(w.owner.id, w.project.id)
    with pytest.raises(DocumentDataError) as numbered:
        build_installation_map_document(sources, None, None, working=True, issued_on=DAY, number="MAP/1")
    assert numbered.value.reason == "DRAFT_NUMBERED"
    issued = page_text(InstallationMapDocumentService.html(await build(db_session, w, number="MAP/2026/10/27/1200", sequence=3)))
    assert "WERSJA ROBOCZA" not in issued and "MAP/2026/10/27/1200" in issued


async def test_the_photos_of_another_owner_never_get_in(db_session):
    w = await seeded(db_session, telegram_id=TG + 5)
    stranger = await seeded(db_session, telegram_id=TG + 6)
    with pytest.raises(ProjectNotFoundError):
        await InstallationMapDocumentService(db_session, w.service()).sources(stranger.owner.id, w.project.id)
    assert (await build(db_session, w)).photo_count == 2


def test_the_map_is_the_template_of_its_kind():
    template = get_template(DocumentKind.INSTALLATION_MAP)
    assert (template.number_prefix, template.file, template.version) == ("MAP", "installation_map.html.j2", "1")


# --- the real routes and a real PDF ------------------------------------------------------------------------------------------------------------

async def test_the_routes_need_a_token_and_take_no_other_fields(async_client: AsyncClient, use_issuer):  # noqa: F811
    use_issuer(issuer())
    pid = uuid.uuid4()
    assert (await async_client.post(f"/api/projects/{pid}/documents", json={"kind": "INSTALLATION_MAP"})).status_code == 401
    assert (await async_client.post(f"/api/projects/{pid}/documents/installation-map/preview")).status_code == 401
    headers = await login(async_client)
    for body in ({"kind": "INSTALLATION_MAP", "estimate_id": str(uuid.uuid4())}, {"kind": "INSTALLATION_MAP", "room_ids": [str(uuid.uuid4())]}, {"kind": "INSTALLATION_MAP", "with_photos": True}):
        assert (await async_client.post(f"/api/projects/{pid}/documents", json=body, headers=headers)).status_code == 422


async def test_issuing_gives_a_numbered_pdf_with_the_photos_in_the_chat_and_a_row_in_the_journal(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await seeded(db_session, telegram_id=VALID_USER["id"])
    sender = Delivery()
    run = use_issuer(issuer(w.storage, delivery=sender))
    headers = await login(async_client)
    response = await async_client.post(f"/api/projects/{w.project.id}/documents", json={"kind": "INSTALLATION_MAP"}, headers=headers)
    assert response.status_code == 202, response.text
    row = response.json()
    assert row["kind"] == "INSTALLATION_MAP" and row["status"] == "PENDING" and row["number"].startswith("MAP/")
    await run.drain()
    shown = await async_client.get(f"/api/projects/{w.project.id}/documents/{row['id']}", headers=headers)
    assert shown.json()["status"] == "SENT" and len(sender.sent) == 1
    sent = sender.sent[0]
    assert sent["filename"].startswith("MAP-") and sent["caption"].startswith("Mapa instalacji ukrytych — Mokotów")
    text = pdf_text(sent["pdf"])
    assert row["number"] in text and "Mapa instalacji ukrytych" in text and "przewód elektryczny · do gniazda · od podłogi 30 cm" in text
    assert "WERSJA ROBOCZA" not in text and "?" not in text
    assert [d["kind"] for d in (await async_client.get(f"/api/projects/{w.project.id}/documents", headers=headers)).json()["items"]] == ["INSTALLATION_MAP"]


async def test_an_object_without_a_utility_photo_is_a_422_that_takes_no_number(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await seed(db_session, telegram_id=VALID_USER["id"])
    run = use_issuer(issuer(w.storage))
    headers = await login(async_client)
    response = await async_client.post(f"/api/projects/{w.project.id}/documents", json={"kind": "INSTALLATION_MAP"}, headers=headers)
    assert (response.status_code, response.json()["detail"]["code"]) == (422, "INSTALLATION_MAP_EMPTY")
    assert run.active == 0 and (await db_session.execute(select(IssuedDocument))).scalars().all() == []


async def test_the_preview_is_a_watermarked_pdf_without_a_number_or_a_journal_row(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await seeded(db_session, telegram_id=VALID_USER["id"])
    sender = Delivery()
    use_issuer(issuer(w.storage, delivery=sender))
    headers = await login(async_client)
    response = await async_client.post(f"/api/projects/{w.project.id}/documents/installation-map/preview", headers=headers)
    assert response.status_code == 200 and response.json()["sent"] is True
    (sent,) = sender.sent
    assert sent["filename"] == "Mapa-instalacji-wersja-robocza.pdf" and sent["caption"].startswith("WERSJA ROBOCZA — Mapa instalacji ukrytych")
    assert "WERSJA ROBOCZA" in pdf_text(sent["pdf"]) and "MAP/" not in pdf_text(sent["pdf"])
    assert (await db_session.execute(select(IssuedDocument))).scalars().all() == []


async def test_another_owner_gets_a_404_for_both_routes(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await seeded(db_session, telegram_id=VALID_USER["id"])
    use_issuer(issuer(w.storage))
    headers = await login(async_client, OTHER_USER)
    assert (await async_client.post(f"/api/projects/{w.project.id}/documents", json={"kind": "INSTALLATION_MAP"}, headers=headers)).status_code == 404
    assert (await async_client.post(f"/api/projects/{w.project.id}/documents/installation-map/preview", headers=headers)).status_code == 404
