"""Stage 16C — the technological card: what a surface needs, what the numbered card refuses, the working version with empty
lines to write in, the journal and the delivery."""

import io
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from pypdf import PdfReader
from sqlalchemy import event, select

from app.domain.documents import formatting
from app.domain.documents.labels import Labels, load_labels
from app.domain.documents.renderer import DocumentRenderer
from app.domain.documents.tech_card_document import (
    BLANK_SURFACES,
    SPARE_ROWS,
    TechCardDocumentService,
    surface_title,
)
from app.domain.exceptions import DocumentDataError, ProjectNotFoundError
from app.models.checklist import QualityLevel, Substrate
from app.models.estimate import Estimate, EstimateLine, EstimateStatus, LineOrigin, QuantitySource
from app.models.issued_document import IssuedDocument
from app.models.price_item import PriceCategory, PriceItem, PriceScope, PriceUnit
from app.models.room import Room
from app.models.surface import Surface, SurfaceType
from app.models.work_plan import SurfacePlannedWork, SurfaceWorkPlan
from tests.conftest import TestingSessionLocal  # noqa: F401  (the issuer helpers use it)
from tests.test_stage15e_photo_report import seed
from tests.test_stage15f2_issuing import Delivery, StubRenderer, issuer, journal, text_of, user_of
from tests.test_stage15d_estimate_document import seed as seed_estimate

TODAY = date(2026, 10, 9)


async def price_item(db, owner_id, code, name_key, unit=PriceUnit.M2) -> PriceItem:
    row = PriceItem(owner_id=owner_id, code=code, category=PriceCategory.PREPARATION, unit=unit, price_scope=PriceScope.LABOR,
                    price=Decimal("10.00"), name_key=name_key)
    db.add(row)
    await db.commit()
    return row


async def plan(db, surface, items, *, quality=QualityLevel.S2, substrate=Substrate.CONCRETE, waits=()):
    """A plan of the surface with the given price items in order; returns the occurrence keys."""
    row = SurfaceWorkPlan(surface_id=surface.id, substrate=substrate, quality_target=quality)
    db.add(row)
    await db.flush()
    keys = []
    for position, item in enumerate(items):
        key = uuid.uuid4()
        keys.append(key)
        db.add(SurfacePlannedWork(work_plan_id=row.id, price_item_id=item.id, position=position, occurrence_key=key,
                                  wait_after_hours=waits[position] if position < len(waits) else None))
    await db.commit()
    return keys


async def world(db, **kw):
    w = await seed(db, **kw)
    w.item_a = await price_item(db, w.owner.id, "PREP_PROT", "pricebook.seed.prep_prot")
    w.item_b = await price_item(db, w.owner.id, "SKIM", "pricebook.seed.prep_prot", PriceUnit.M2)
    return w


async def build(db, w, *, working, number=None):
    return await TechCardDocumentService(db).build(w.owner.id, w.project.id, working=working, issued_on=TODAY, number=number)


# --- the numbered card ----------------------------------------------------------------------------------------------------------------


async def test_an_object_with_no_planned_works_has_no_numbered_card(db_session):
    w = await world(db_session)
    with pytest.raises(DocumentDataError) as refused:
        await build(db_session, w, working=False)
    assert refused.value.reason == "TECH_CARD_EMPTY"


async def test_a_surface_without_an_agreed_standard_or_a_finished_inspection_is_named(db_session):
    w = await world(db_session)
    other = Surface(room_id=w.salon.id, name="Wall 1", surface_type=SurfaceType.WALL)
    db_session.add(other)
    await db_session.commit()
    await plan(db_session, w.wall, [w.item_a], quality=None)  # has an inspection, lacks the standard
    await plan(db_session, other, [w.item_a])  # has the standard, lacks an inspection
    with pytest.raises(DocumentDataError) as refused:
        await build(db_session, w, working=False)
    assert refused.value.reason == "TECH_CARD_INCOMPLETE"
    items = {i["surface"]: i["missing"] for i in refused.value.details["items"]}
    # raw names: the screen puts "Wall 1" into the language of the interface itself
    assert items == {"Ściana A": ["QUALITY_TARGET"], "Wall 1": ["INSPECTION"]}
    assert {i["surface_type"] for i in refused.value.details["items"]} == {"WALL"}
    assert all(i["room"] == "Salon" for i in refused.value.details["items"])


async def test_the_numbered_card_lists_the_works_in_order_with_their_breaks_and_the_estimate_quantity(db_session):
    w = await world(db_session)
    keys = await plan(db_session, w.wall, [w.item_a, w.item_b, w.item_a], waits=(24, None, 4))
    estimate = Estimate(owner_id=w.owner.id, project_id=w.project.id, version=1, status=EstimateStatus.FINAL, total=Decimal("0"))
    db_session.add(estimate)
    await db_session.flush()
    db_session.add(EstimateLine(
        estimate_id=estimate.id, origin=LineOrigin.PLANNED_WORK, position=1, room_id=w.salon.id, surface_id=w.wall.id,
        occurrence_key=keys[1], description="x", unit=PriceUnit.M2, scope=PriceScope.LABOR, source_quantity=Decimal("24.5"),
        quantity=Decimal("24.5"), quantity_source=QuantitySource.SURFACE_NET_AREA, unit_price=Decimal("6.00"), amount=Decimal("147.00"),
    ))
    await db_session.commit()
    document = await build(db_session, w, working=False, number="KART/2026/10/09/1200")
    assert not document.layout.light_watermark
    assert not document.working and not document.layout.draft and document.layout.meta.number == "KART/2026/10/09/1200"
    (room,) = document.rooms  # Kuchnia has nothing planned: it is not in the card
    assert room.name == "Salon"
    (surface,) = room.surfaces
    assert (surface.name, surface.type_label, surface.substrate, surface.quality_target) == (
        "Ściana A", "ściana", "beton", "S2 — standard malarski")
    assert [(x.number, x.unit, x.quantity, x.wait_hours) for x in surface.works] == [
        (1, "m²", None, 24), (2, "m²", "24,50", None), (3, "m²", None, 4)]
    assert surface.spare_rows == 0 and surface.inspection is not None
    html = TechCardDocumentService.html(document)
    assert "Karta technologiczna" in html and "24 godz." in html and "WERSJA ROBOCZA" not in html
    assert "zł" not in html  # a card carries no prices


async def test_the_card_needs_the_executor_profile_but_the_working_version_does_not(db_session):
    w = await world(db_session, with_profile=False)
    await plan(db_session, w.wall, [w.item_a])
    with pytest.raises(DocumentDataError) as refused:
        await build(db_session, w, working=False)
    assert refused.value.reason == "EXECUTOR_PROFILE_REQUIRED"
    document = await build(db_session, w, working=True)
    assert document.layout.executor is None and document.layout.draft


async def test_a_foreign_project_is_not_found(db_session):
    w = await world(db_session)
    other = await seed(db_session, telegram_id=9602)
    with pytest.raises(ProjectNotFoundError):
        await TechCardDocumentService(db_session).build(other.owner.id, w.project.id, working=True, issued_on=TODAY)


async def test_an_archived_surface_and_an_archived_room_are_not_in_the_card(db_session):
    w = await world(db_session)
    other = Surface(room_id=w.salon.id, name="Wall 2", surface_type=SurfaceType.WALL, is_archived=True)
    db_session.add(other)
    await db_session.commit()
    await plan(db_session, other, [w.item_a])
    document = await build(db_session, w, working=True)
    assert [s.name for room in document.rooms for s in room.surfaces] == ["Ściana A"]
    room = (await db_session.execute(select(Room).where(Room.id == w.kuchnia.id))).scalar_one()
    room.is_archived = True
    await db_session.commit()
    document = await build(db_session, w, working=True)
    assert [room.name for room in document.rooms] == ["Salon"]


async def test_a_floor_takes_the_inspection_of_its_plane(db_session):
    w = await world(db_session)
    floor = Surface(room_id=w.salon.id, name="Floor", surface_type=SurfaceType.FLOOR)
    db_session.add(floor)
    w.inspection.surface_id = None
    from app.models.area_segment import AreaPlane

    w.inspection.plane = AreaPlane.FLOOR
    await db_session.commit()
    await plan(db_session, floor, [w.item_a])
    document = await build(db_session, w, working=False)
    (surface,) = document.rooms[0].surfaces
    assert surface.name == "Podłoga" and surface.type_label == "podłoga" and surface.inspection is not None


# --- the working version --------------------------------------------------------------------------------------------------------------


async def test_the_working_version_prints_what_exists_and_empty_lines_for_the_rest(db_session):
    w = await world(db_session)
    document = await build(db_session, w, working=True)
    assert document.working and document.layout.draft and document.layout.meta.number is None
    assert [room.name for room in document.rooms] == ["Salon", "Kuchnia"]
    (wall,) = document.rooms[0].surfaces
    # no plan yet: the substrate comes from the inspection, the standard is empty, the table has rows to write in
    assert (wall.substrate, wall.quality_target, wall.works, wall.spare_rows) == ("beton", None, (), SPARE_ROWS)
    assert document.rooms[1].surfaces == ()
    html = TechCardDocumentService.html(document)
    assert "WERSJA ROBOCZA" in html and "write-line" in html and "write-box" in html
    assert 'class="watermark light"' in html  # a sheet to write on: the mark is pale
    assert html.count('class="spare"') == SPARE_ROWS


async def test_an_object_with_no_rooms_gets_a_blank_form(db_session):
    w = await world(db_session)
    for room in (w.salon, w.kuchnia):
        row = (await db_session.execute(select(Room).where(Room.id == room.id))).scalar_one()
        row.is_archived = True
    await db_session.commit()
    document = await build(db_session, w, working=True)
    (room,) = document.rooms
    assert room.name is None and len(room.surfaces) == BLANK_SURFACES
    assert all(s.name is None and s.works == () and s.spare_rows == SPARE_ROWS for s in room.surfaces)
    html = TechCardDocumentService.html(document)
    assert html.count("<h3>") == BLANK_SURFACES and "Pomieszczenie:" in html


async def test_a_partly_filled_working_version_fills_the_free_rows_up_to_four(db_session):
    w = await world(db_session)
    await plan(db_session, w.wall, [w.item_a, w.item_b])
    document = await build(db_session, w, working=True)
    (wall,) = document.rooms[0].surfaces
    assert len(wall.works) == 2 and wall.spare_rows == SPARE_ROWS - 2
    full = await plan_more(db_session, w)
    document = await build(db_session, w, working=True)
    assert document.rooms[0].surfaces[0].spare_rows == 0 and full == 6


async def plan_more(db, w) -> int:
    row = (await db.execute(select(SurfaceWorkPlan).where(SurfaceWorkPlan.surface_id == w.wall.id))).scalar_one()
    for position in range(2, 6):
        db.add(SurfacePlannedWork(work_plan_id=row.id, price_item_id=w.item_a.id, position=position, occurrence_key=uuid.uuid4()))
    await db.commit()
    return 6


async def test_the_pdf_of_the_working_version_is_a_real_pdf_with_the_watermark_and_the_headings(db_session):
    w = await world(db_session)
    pdf = (await DocumentRenderer().render(TechCardDocumentService.html(await build(db_session, w, working=True)))).pdf
    text = " ".join(text_of(pdf).split())  # a heading may wrap inside a narrow column
    for heading in ("Karta technologiczna", "Pomieszczenie: Salon", "Podłoże", "Docelowy standard wykończenia", "Ocena podłoża",
                    "Zakres prac w kolejności wykonania", "Przerwa technologiczna po pracy", "Uwagi"):
        assert heading in text, heading
    assert "WERSJA ROBOCZA" in text
    assert len(PdfReader(io.BytesIO(pdf)).pages) >= 1


async def test_the_number_of_queries_does_not_grow_with_the_rooms_and_surfaces(db_session):
    w = await world(db_session)
    counter = {"n": 0}

    def count(*_):
        counter["n"] += 1

    bind = db_session.bind.sync_engine
    event.listen(bind, "before_cursor_execute", count)
    try:
        await plan(db_session, w.wall, [w.item_a])  # some data on every kind of table, so no statement is skipped as empty
        counter["n"] = 0
        await build(db_session, w, working=True)
        small = counter["n"]
        for index in range(6):
            room = Room(project_id=w.project.id, name=f"R{index}")
            db_session.add(room)
            await db_session.flush()
            for k in range(3):
                surface = Surface(room_id=room.id, name=f"S{k}", surface_type=SurfaceType.WALL)
                db_session.add(surface)
                await db_session.flush()
                await plan(db_session, surface, [w.item_a])
        counter["n"] = 0
        await build(db_session, w, working=True)
        assert counter["n"] == small
    finally:
        event.remove(bind, "before_cursor_execute", count)


# --- words ------------------------------------------------------------------------------------------------------------------------------


def test_every_label_the_card_can_ask_for_exists():
    labels = Labels()
    for level in QualityLevel:
        assert labels(f"techcard.quality.{level.value.lower()}")
    for kind in SurfaceType:
        assert labels(f"techcard.surface.{kind.value.lower()}")
    for substrate in Substrate:
        assert labels(f"photo_report.substrate_name.{substrate.value.lower()}")
    for unit in PriceUnit:
        assert labels(f"unit.{unit.value.lower()}")


def test_canonical_names_are_polish_and_an_owners_name_is_kept():
    assert (surface_title("Wall 3"), surface_title("Floor"), surface_title("Ceiling")) == ("Ściana 3", "Podłoga", "Sufit")
    assert surface_title("Okno wschodnie") == "Okno wschodnie" and surface_title("Wall 3 bis") == "Wall 3 bis"


def test_the_card_template_has_no_clause_like_wording_or_prices():
    from app.domain.documents.templating import TEMPLATES_DIR

    source = (TEMPLATES_DIR / "tech_card.html.j2").read_text(encoding="utf-8").lower()
    for word in ("zł", "pln", "cena", "gwarancj", "kara", "odpowiedzialn", "zobowiązuj"):
        assert word not in source, word
    for key in [k for k in _all_keys() if k.startswith("techcard.")]:
        text = load_labels()[key].lower()
        for word in ("zł", "gwarancj", "kara", "odpowiedzialn", "zobowiązuj"):
            assert word not in text, (key, word)


def _all_keys():
    return load_labels().keys()


# --- issuing ----------------------------------------------------------------------------------------------------------------------------

NOW = datetime(2026, 10, 9, 10, 15, 0, tzinfo=UTC)


async def test_a_card_is_numbered_rendered_sent_and_recorded(db_session):
    w = await world(db_session, telegram_id=9650)
    owner_id, project_id, telegram = w.owner.id, w.project.id, w.owner.telegram_user_id
    await plan(db_session, w.wall, [w.item_a])
    sender = Delivery()
    run = issuer(delivery=sender)
    reservation = await run.start_tech_card(db_session, await user_of(db_session, owner_id), project_id)
    assert (reservation.document.status, reservation.document.kind, reservation.document.project_seq) == ("PENDING", "TECH_CARD", 1)
    assert reservation.document.number.startswith("KART/2026/10/08/")
    await run.drain()
    (done,) = await journal(db_session)
    assert (done.status, done.error_code, done.title, done.template_version) == ("SENT", None, "Karta technologiczna", "1")
    (message,) = sender.sent
    assert message["chat_id"] == telegram and message["filename"].startswith("KART-2026-10-08-")
    assert message["caption"].startswith("Karta technologiczna — Mokotów\nKART/")
    text = text_of(message["pdf"])
    assert done.number in text and "WERSJA ROBOCZA" not in text and "Ściana A" in text


async def test_an_incomplete_card_takes_no_number(db_session):
    w = await world(db_session, telegram_id=9651)
    owner_id, project_id = w.owner.id, w.project.id
    await plan(db_session, w.wall, [w.item_a], quality=None)
    run = issuer()
    with pytest.raises(DocumentDataError) as refused:
        await run.start_tech_card(db_session, await user_of(db_session, owner_id), project_id)
    assert refused.value.reason == "TECH_CARD_INCOMPLETE"
    assert await journal(db_session) == [] and run.active == 0


async def test_a_second_tap_before_the_first_ends_starts_nothing_new(db_session):
    w = await world(db_session, telegram_id=9652)
    owner_id, project_id = w.owner.id, w.project.id
    await plan(db_session, w.wall, [w.item_a])
    sender = Delivery()
    run = issuer(delivery=sender)
    user = await user_of(db_session, owner_id)
    first = await run.start_tech_card(db_session, user, project_id)
    again = await run.start_tech_card(db_session, user, project_id)
    assert again.reused and again.document.id == first.document.id
    await run.drain()
    assert len(sender.sent) == 1 and len(await journal(db_session)) == 1


async def test_the_preview_goes_to_the_chat_without_a_number_or_a_journal_row(db_session):
    w = await world(db_session, telegram_id=9653)
    owner_id, project_id, telegram = w.owner.id, w.project.id, w.owner.telegram_user_id
    sender = Delivery()
    run = issuer(delivery=sender)
    result = await run.preview_tech_card(db_session, await user_of(db_session, owner_id), project_id)
    assert result.pages >= 1
    (message,) = sender.sent
    assert message["chat_id"] == telegram and message["filename"] == "Karta-technologiczna-wersja-robocza.pdf"
    assert message["caption"] == "WERSJA ROBOCZA — Karta technologiczna — Mokotów"
    assert "WERSJA ROBOCZA" in text_of(message["pdf"])
    assert await journal(db_session) == []


async def test_the_preview_works_for_an_object_that_is_still_empty(db_session):
    owner, project, _ = await seed_estimate(db_session, telegram_id=9654)
    owner_id, project_id = owner.id, project.id
    sender = Delivery()
    await issuer(delivery=sender, renderer=StubRenderer()).preview_tech_card(db_session, await user_of(db_session, owner_id), project_id)
    assert len(sender.sent) == 1


def test_formatting_import_is_used():
    assert formatting.format_quantity(Decimal("24.5")) == "24,50"
    assert IssuedDocument.__tablename__ == "issued_documents"
