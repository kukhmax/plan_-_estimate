"""V2-8c -- the measurements of an object (Obmiar obiektu): the numbers are those of the screens, what is printed, what never is, the two forms."""
import io
import os
import re
import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from pypdf import PdfReader
from sqlalchemy import select

from app.domain.documents import formatting
from app.domain.documents.measurements_document import MeasurementsDocumentService, build_measurements_document
from app.domain.documents.registry import DocumentKind, get_template
from app.domain.exceptions import DocumentDataError, ProjectNotFoundError
from app.domain.services.room_service import RoomService
from app.domain.services.surface_service import SurfaceService
from app.models.area_segment import AreaOperation, AreaPlane
from app.models.executor_profile import ExecutorProfile
from app.models.issued_document import IssuedDocument
from app.models.opening import Opening, OpeningType
from app.models.room import Room
from app.models.surface import Surface, SurfaceType
from app.schemas.area_segment import AreaSegmentCreate
from app.schemas.room import RoomCreate
from app.schemas.surface import SurfaceRead
from tests.test_clients import OTHER_USER, VALID_USER
from tests.test_stage15e_photo_report import seed
from tests.test_stage15f2_api import login, use_issuer  # noqa: F401  (a fixture)
from tests.test_stage15f2_issuing import Delivery, issuer
from app.domain.services.area_segment_service import AreaSegmentService

OWNER_TG = VALID_USER["id"]
DAY = date(2026, 10, 27)
NBSP = " "


def page_text(html: str) -> str:
    """The words of the page as one reads them: no tags (the style block goes too), no unbreakable spaces, one space between words."""
    body = re.sub(r"<style.*?</style>", " ", html, flags=re.S)
    return " ".join(re.sub(r"<[^>]+>", " ", body).replace(NBSP, " ").split())


def pdf_text(pdf: bytes) -> str:
    return " ".join("\n".join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages).replace(NBSP, " ").split())


async def world(db, telegram_id=OWNER_TG):
    """An object with a rectangular room (5,20 x 3,60 x 2,60: four generated walls, a window of 2 x 1,70 x 1,65 on the first, with reveals) and a
    room "Klatka" of no rectangle: a ceiling of two segments (one labelled "pierwsze piętro") and walls of its own, one of them merged of two parts."""
    w = await seed(db, telegram_id=telegram_id)
    rooms = RoomService(db)
    # the two rooms of the seed are noise: archived, so that only the rooms of this test count
    for room in (w.salon, w.kuchnia):
        room.is_archived = True
    await db.commit()
    salon = await rooms.create_room(w.project.id, RoomCreate(name="Salon", description="Pokój dzienny", length=Decimal("5.2"), width=Decimal("3.6"), height=Decimal("2.6")), w.owner.id)
    walls = await SurfaceService(db).generate_walls(w.project.id, salon.id, w.owner.id)
    walls = sorted(walls, key=lambda s: s.position)
    w.salon, w.walls = salon, list(walls)
    db.add(
        Opening(surface_id=walls[0].id, opening_type=OpeningType.WINDOW, name="od ulicy", width=Decimal("1.7"), height=Decimal("1.65"), quantity=2,
                reveal_enabled=True, reveal_depth=Decimal("0.15"), reveal_left=True, reveal_right=True, reveal_top=True, reveal_bottom=False)
    )
    await db.commit()
    klatka = await rooms.create_room(w.project.id, RoomCreate(name="Klatka"), w.owner.id)
    w.klatka = klatka
    segments = AreaSegmentService(db)
    for width, height, label in (("2.7", "3.2", "pierwsze piętro"), ("2.6", "3.1", "1,5 piętro")):
        await segments.create_area_segment(w.project.id, klatka.id, AreaSegmentCreate(plane=AreaPlane.CEILING, operation=AreaOperation.ADD, width=Decimal(width), height=Decimal(height), label=label), w.owner.id)
    await segments.create_area_segment(w.project.id, klatka.id, AreaSegmentCreate(plane=AreaPlane.CEILING, operation=AreaOperation.SUBTRACT, width=Decimal("0.5"), height=Decimal("0.5"), label="komin"), w.owner.id)
    first = Surface(room_id=klatka.id, name="Parter (przy windzie)", surface_type=SurfaceType.WALL, width=Decimal("3.45"), height=Decimal("2.5"), position=1)
    second = Surface(room_id=klatka.id, name="Wall 2", surface_type=SurfaceType.WALL, width=Decimal("4.1"), height=Decimal("2.5"), position=2)
    nosize = Surface(room_id=klatka.id, name="Wall 3", surface_type=SurfaceType.WALL, position=3)
    db.add_all([first, second, nosize])
    await db.commit()
    w.first, w.second, w.nosize = first, second, nosize
    return w


async def build(db, w, **kw):
    return await MeasurementsDocumentService(db).build(w.owner.id, w.project.id, working=kw.pop("working", False), issued_on=kw.pop("issued_on", DAY), **kw)


async def html_of(db, w, **kw) -> str:
    return page_text(MeasurementsDocumentService.html(await build(db, w, **kw)))


# --- the numbers are those of the screens --------------------------------------------------------------------------------------------------


async def test_the_summary_and_the_totals_of_every_room_are_those_of_the_screens(db_session):
    w = await world(db_session)
    summary = await RoomService(db_session).get_project_summary(w.project.id, w.owner.id)
    rooms, _ = await RoomService(db_session).list_rooms(w.project.id, w.owner.id)
    document = await build(db_session, w)
    cells = {row.label: row.result.replace(NBSP, " ") for row in document.summary}
    fmt = lambda value: formatting.format_decimal(value, 2)  # noqa: E731  (half up, as the document and the screens round)
    assert cells["Liczba pomieszczeń"] == "2"
    assert cells["Sufity"] == f"{fmt(summary.ceiling_area)} m²" and cells["Ściany brutto"] == f"{fmt(summary.total_wall_area)} m²"
    assert cells["Odjęcia otworów"] == f"{fmt(summary.total_deduction_area)} m²" and cells["Ściany netto"] == f"{fmt(summary.net_wall_area)} m²"
    by_name = {room.name: room for room in rooms}
    for block in document.rooms:
        calc = by_name[block.name].calculations
        totals = {row.label: row.result.replace(NBSP, " ") for row in block.totals}
        assert totals["Ściany (netto)"] == f"{fmt(calc.net_wall_area)} m²"
        assert block.ceiling.total.replace(NBSP, " ") == (f"{fmt(calc.ceiling_area)} m²" if calc.ceiling_area is not None else "—")
        assert block.floor.total.replace(NBSP, " ") == (f"{fmt(calc.floor_area)} m²" if calc.floor_area is not None else "—")


async def test_the_area_of_every_wall_is_the_one_of_its_read(db_session):
    w = await world(db_session)
    document = await build(db_session, w)
    surfaces, _ = await SurfaceService(db_session).list_surfaces(w.project.id, w.salon.id, w.owner.id)
    reads = {SurfaceRead.model_validate(s).name: SurfaceRead.model_validate(s) for s in surfaces if s.surface_type == SurfaceType.WALL}
    salon = next(block for block in document.rooms if block.name == "Salon")
    assert len(salon.walls) == len(reads) == 4
    for wall in salon.walls:
        read = next(r for name, r in reads.items() if wall.name == f"Ściana {name.split()[-1]}")
        assert wall.gross.replace(NBSP, " ") == formatting.format_decimal(read.gross_area, 2) + " m²"


# --- what is printed -------------------------------------------------------------------------------------------------------------------------


async def test_the_page_lays_out_the_object_the_rooms_the_ceiling_and_the_walls(db_session):
    w = await world(db_session)
    page = await html_of(db_session, w)
    for text in (
        "Obmiar obiektu", "Podsumowanie obiektu", "Salon", "Pokój dzienny", "Klatka",
        "Prostokąt pomieszczenia 5,20 × 3,60 = 18,72 m²",
        "+ pierwsze piętro 2,70 × 3,20 = 8,64 m²", "+ 1,5 piętro 2,60 × 3,10 = 8,06 m²", "− komin 0,50 × 0,50 = 0,25 m²",
        "Sufit: 16,45 m²", "Parter (przy windzie) 3,45 × 2,50 = 8,63 m²", "Ściana 2 4,10 × 2,50 = 10,25 m²", "brak wymiarów",
        "Okno „od ulicy” 1,70 × 1,65 × 2 = 5,61 m²", "Po odjęciu otworów",
    ):
        assert text in page, text
    assert "Ściana 1 5,20 × 2,60 = 13,52 m²" in page and "Ościeża (Okno „od ulicy”) głębokość 0,15 m" in page
    klatka = next(room for room in (await build(db_session, w)).rooms if room.name == "Klatka")
    assert all("Prostokąt" not in row.label for row in klatka.ceiling.rows + klatka.floor.rows)  # a room with no rectangle has no rectangle line


async def test_a_merged_wall_prints_its_parts_and_the_sum_is_the_one_of_the_screen(db_session):
    from app.models.surface_part import SurfacePart

    w = await world(db_session)
    db_session.add_all(
        [
            SurfacePart(surface_id=w.second.id, source_surface_id=None, position=1, width=Decimal("4.1"), height=Decimal("2.5")),
            SurfacePart(surface_id=w.second.id, source_surface_id=None, position=2, width=Decimal("1.2"), height=Decimal("2.5")),
        ]
    )
    await db_session.commit()
    page = await html_of(db_session, w)
    assert "część 1 4,10 × 2,50 = 10,25 m²" in page and "część 2 1,20 × 2,50 = 3,00 m²" in page
    assert "Ściana 2 4,10 × 2,50 = 13,25 m²" in page  # the wall's own size is shown, the area is the sum of its parts (as the screen)


async def test_an_archived_room_wall_and_opening_are_not_printed(db_session):
    w = await world(db_session)
    w.klatka.is_archived = True
    w.walls[1].is_archived = True
    opening = (await db_session.execute(select(Opening))).scalar_one()
    opening.is_archived = True
    await db_session.commit()
    document = await build(db_session, w)
    page = page_text(MeasurementsDocumentService.html(document))
    assert [room.name for room in document.rooms] == ["Salon"]
    assert "Klatka" not in page and "Okno" not in page and "Ościeża (" not in page
    assert len(document.rooms[0].walls) == 3
    assert "Liczba pomieszczeń 1" in page


async def test_the_rooms_of_another_object_and_owner_never_get_in(db_session):
    w = await world(db_session)
    other = await seed(db_session, telegram_id=OWNER_TG + 77)
    other_room = Room(project_id=other.project.id, name="Tajny pokój obcego", length=Decimal("9"), width=Decimal("9"), height=Decimal("3"))
    db_session.add(other_room)
    await db_session.commit()
    page = await html_of(db_session, w)
    assert "Tajny pokój" not in page
    with pytest.raises(ProjectNotFoundError):
        await MeasurementsDocumentService(db_session).build(other.owner.id, w.project.id, working=False, issued_on=DAY)


async def test_the_words_of_a_room_cannot_break_the_page(db_session):
    w = await world(db_session)
    w.klatka.name = "<script>alert(1)</script> {{ 7*7 }}"
    await db_session.commit()
    raw = MeasurementsDocumentService.html(await build(db_session, w))
    assert "<script>" not in raw and "&lt;script&gt;" in raw and "{{ 7*7 }}" in raw.replace("&#123;", "{")


async def test_a_room_with_no_sizes_is_listed_with_dashes_and_nothing_invented(db_session):
    w = await seed(db_session, telegram_id=OWNER_TG + 5)
    document = await MeasurementsDocumentService(db_session).build(w.owner.id, w.project.id, working=False, issued_on=DAY)
    for room in document.rooms:
        assert room.ceiling.total == "—" and room.floor.total == "—" and room.ceiling.rows == ()


# --- the two forms of the document -------------------------------------------------------------------------------------------------------------


async def test_the_issued_form_needs_a_room_and_a_profile_and_the_working_form_never_refuses(db_session):
    w = await seed(db_session, telegram_id=OWNER_TG + 9)
    for room in (w.salon, w.kuchnia):
        room.is_archived = True
    await db_session.commit()
    with pytest.raises(DocumentDataError) as empty:
        await build(db_session, w)
    assert empty.value.reason == "MEASUREMENTS_EMPTY"
    draft = await build(db_session, w, working=True)
    page = page_text(MeasurementsDocumentService.html(draft))
    assert "WERSJA ROBOCZA" in page and "Brak pomieszczeń." in page and draft.layout.meta.number is None
    w2 = await world(db_session, telegram_id=OWNER_TG + 11)
    await db_session.execute(ExecutorProfile.__table__.delete().where(ExecutorProfile.owner_id == w2.owner.id))
    await db_session.commit()
    with pytest.raises(DocumentDataError) as no_profile:
        await build(db_session, w2)
    assert no_profile.value.reason == "EXECUTOR_PROFILE_REQUIRED"
    assert MeasurementsDocumentService.html(await build(db_session, w2, working=True))


async def test_a_working_version_is_never_numbered_and_an_issued_one_has_no_watermark(db_session):
    w = await world(db_session)
    sources = await MeasurementsDocumentService(db_session).sources(w.owner.id, w.project.id)
    with pytest.raises(DocumentDataError) as numbered:
        build_measurements_document(sources, None, working=True, issued_on=DAY, number="OBM/1")
    assert numbered.value.reason == "DRAFT_NUMBERED"
    issued = await html_of(db_session, w, number="OBM/2026/10/27/1200", sequence=4)
    assert "WERSJA ROBOCZA" not in issued and "OBM/2026/10/27/1200" in issued


async def test_the_measurements_are_the_template_of_their_kind(db_session):
    template = get_template(DocumentKind.MEASUREMENTS)
    assert (template.number_prefix, template.file, template.version) == ("OBM", "measurements.html.j2", "1")


# --- the real routes and a real PDF -------------------------------------------------------------------------------------------------------------


async def test_the_routes_need_a_token(async_client: AsyncClient, use_issuer):  # noqa: F811
    use_issuer(issuer())
    pid = uuid.uuid4()
    assert (await async_client.post(f"/api/projects/{pid}/documents", json={"kind": "MEASUREMENTS"})).status_code == 401
    assert (await async_client.post(f"/api/projects/{pid}/documents/measurements/preview")).status_code == 401


async def test_it_takes_no_other_fields(async_client: AsyncClient, use_issuer):  # noqa: F811
    run = use_issuer(issuer())
    headers = await login(async_client)
    for body in ({"kind": "MEASUREMENTS", "estimate_id": str(uuid.uuid4())}, {"kind": "MEASUREMENTS", "room_ids": [str(uuid.uuid4())]},
                 {"kind": "MEASUREMENTS", "include_project_photos": True}):
        assert (await async_client.post(f"/api/projects/{uuid.uuid4()}/documents", json=body, headers=headers)).status_code == 422
    assert run.active == 0


async def test_issuing_gives_a_numbered_pdf_with_every_size_in_the_chat_and_a_row_in_the_journal(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await world(db_session)
    project_id = str(w.project.id)
    sender = Delivery()
    run = use_issuer(issuer(delivery=sender))
    headers = await login(async_client)
    response = await async_client.post(f"/api/projects/{project_id}/documents", json={"kind": "MEASUREMENTS"}, headers=headers)
    assert response.status_code == 202, response.text
    row = response.json()
    assert row["kind"] == "MEASUREMENTS" and row["status"] == "PENDING" and row["number"].startswith("OBM/") and row["source_id"] is None
    await run.drain()
    shown = await async_client.get(f"/api/projects/{project_id}/documents/{row['id']}", headers=headers)
    assert shown.json()["status"] == "SENT" and len(sender.sent) == 1
    sent = sender.sent[0]
    assert sent["filename"].startswith("OBM-") and sent["caption"].startswith("Obmiar obiektu — Mokotów")
    if os.environ.get("MEASUREMENTS_PDF_OUT"):  # for the eyes of a developer: the real PDF of this world
        open(os.environ["MEASUREMENTS_PDF_OUT"], "wb").write(sent["pdf"])
    text = pdf_text(sent["pdf"])
    assert row["number"] in text and "Obmiar obiektu" in text and "Podsumowanie obiektu" in text
    for expected in ("5,20 × 3,60 = 18,72 m²", "pierwsze piętro 2,70 × 3,20 = 8,64 m²", "3,45 × 2,50 = 8,63 m²", "Okno „od ulicy” 1,70 × 1,65 × 2 = 5,61 m²", "brak wymiarów"):
        assert expected in text, expected
    assert "?" not in text and "WERSJA ROBOCZA" not in text  # no glyph missing from the font, no watermark
    listed = await async_client.get(f"/api/projects/{project_id}/documents", headers=headers)
    assert [d["kind"] for d in listed.json()["items"]] == ["MEASUREMENTS"]


async def test_an_object_without_a_room_is_a_422_that_takes_no_number(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await seed(db_session, telegram_id=OWNER_TG)
    for room in (w.salon, w.kuchnia):
        room.is_archived = True
    await db_session.commit()
    run = use_issuer(issuer())
    headers = await login(async_client)
    response = await async_client.post(f"/api/projects/{w.project.id}/documents", json={"kind": "MEASUREMENTS"}, headers=headers)
    assert (response.status_code, response.json()["detail"]["code"]) == (422, "MEASUREMENTS_EMPTY")
    assert run.active == 0
    assert (await db_session.execute(select(IssuedDocument))).scalars().all() == []


async def test_the_preview_is_a_watermarked_pdf_without_a_number_or_a_journal_row(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await world(db_session)
    sender = Delivery()
    use_issuer(issuer(delivery=sender))
    headers = await login(async_client)
    response = await async_client.post(f"/api/projects/{w.project.id}/documents/measurements/preview", headers=headers)
    assert response.status_code == 200 and response.json()["sent"] is True
    (sent,) = sender.sent
    assert sent["filename"] == "Obmiar-obiektu-wersja-robocza.pdf" and sent["caption"].startswith("WERSJA ROBOCZA — Obmiar obiektu")
    assert "WERSJA ROBOCZA" in pdf_text(sent["pdf"]) and "OBM/" not in pdf_text(sent["pdf"])
    assert (await db_session.execute(select(IssuedDocument))).scalars().all() == []


async def test_another_owner_gets_a_404_for_both_routes(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await world(db_session)
    use_issuer(issuer())
    headers = await login(async_client, OTHER_USER)
    assert (await async_client.post(f"/api/projects/{w.project.id}/documents", json={"kind": "MEASUREMENTS"}, headers=headers)).status_code == 404
    assert (await async_client.post(f"/api/projects/{w.project.id}/documents/measurements/preview", headers=headers)).status_code == 404
