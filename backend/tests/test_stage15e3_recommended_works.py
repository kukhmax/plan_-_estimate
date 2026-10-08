"""Stage 15E.3 — risk -> recommended extra work -> price from the current estimate, as a separate block of the report.

What is listed, where the price comes from, what blocks issuing ("no unknown prices in the final version"), owner scope."""

import io
import uuid
from decimal import Decimal

import pytest
from pypdf import PdfReader
from sqlalchemy import event, select

from app.domain.documents.photo_report_document import (
    PhotoReportDocumentService,
    build_photo_report_document,
    plan_photo_report,
    recommended_view,
)
from app.domain.documents.renderer import DocumentRenderer
from app.domain.exceptions import DocumentDataError, ProjectNotFoundError
from app.domain.services.recommended_work_read_model import (
    EstimatePrice,
    RecommendedWork,
    RecommendedWorkReadModel,
    RecommendedWorks,
)
from app.models.estimate import (
    Estimate,
    EstimateLine,
    EstimateStatus,
    LineOrigin,
    QuantitySource,
)
from app.models.price_item import PriceCategory, PriceItem, PriceScope, PriceUnit
from app.models.risk import Risk
from app.models.surface import Surface, SurfaceType
from app.models.work_recommendation import (
    WorkRecommendation,
    WorkRecommendationStatus,
    WorkRecommendationTargetKind,
    WorkRecommendationTriggerType,
)
from tests.conftest import test_engine
from tests.test_stage15e2_inspection_report import world
from tests.test_stage15e_photo_report import (
    CLIENT,
    EXECUTOR,
    PROJECT,
    TODAY,
    images_for,
    make_report,
    photos_of,
)
from tests.test_stage15e_photo_report import details_for as photo_details

T = WorkRecommendationTargetKind
PRIM, CRACK = "CENNIK_PRIM_STD-01", "CENNIK_SKIM_CRACK-01"


async def item(db, owner_id, code, unit=PriceUnit.M2, name_key=None, display_name=None, price="6.00"):
    row = PriceItem(owner_id=owner_id, code=code, category=PriceCategory.PREPARATION, unit=unit, price_scope=PriceScope.LABOR,
                    price=Decimal(price), name_key=name_key, display_name=display_name)
    db.add(row)
    await db.commit()
    return row


async def estimate(db, owner_id, project_id, version=1, status=EstimateStatus.FINAL):
    row = Estimate(owner_id=owner_id, project_id=project_id, version=version, status=status, total=Decimal(0))
    db.add(row)
    await db.commit()
    return row


async def line(db, est_id, price_item, surface_id, quantity, unit_price, unit=PriceUnit.M2, position=1, opening_id=None):
    amount = (Decimal(quantity) * Decimal(unit_price)).quantize(Decimal("0.01")) if unit_price is not None else None
    db.add(EstimateLine(
        estimate_id=est_id, origin=LineOrigin.PLANNED_WORK, position=position, surface_id=surface_id, opening_id=opening_id,
        price_item_id=price_item.id, item_code=price_item.code, description=price_item.code, unit=unit, scope=PriceScope.LABOR,
        source_quantity=Decimal(quantity), quantity=Decimal(quantity), quantity_source=QuantitySource.SURFACE_NET_AREA,
        unit_price=Decimal(unit_price) if unit_price is not None else None, amount=amount))
    await db.commit()


async def risk_of(db, inspection_id, rule_code):
    return (await db.execute(select(Risk).where(Risk.inspection_id == inspection_id, Risk.rule_code == rule_code))).scalar_one()


async def rec(db, w, risk, code, *, status=WorkRecommendationStatus.PENDING, active=True, kind=T.WALL, surface_id="wall", resolved=None):
    row = WorkRecommendation(
        trigger_type=WorkRecommendationTriggerType.RISK_RULE, trigger_code=risk.rule_code, source_signature=uuid.uuid4().hex,
        inspection_id=w.inspection.id, room_id=w.salon.id, surface_id=w.wall.id if surface_id == "wall" else surface_id,
        target_kind=kind, recommended_work_code=code, status=status, is_active=active, risk_id=risk.id,
        resolved_price_item_id=resolved.id if resolved else None)
    db.add(row)
    await db.commit()
    return row


async def full_world(db, telegram_id):
    """A finished inspection with the risks DUSTY_SUBSTRATE_PRIME and CRACK_RECURRENCE, two price items, a FINAL estimate that
    prices both works on the wall, and a recommendation for each."""
    w = await world(db, telegram_id)
    w.prim = await item(db, w.owner.id, PRIM, name_key="pricebook.seed.prim_std")
    w.crack = await item(db, w.owner.id, CRACK, unit=PriceUnit.LM, name_key="pricebook.seed.skim_crack", price="12.00")
    w.estimate = await estimate(db, w.owner.id, w.project.id)
    await line(db, w.estimate.id, w.prim, w.wall.id, "24.5", "6.00", position=1)
    await line(db, w.estimate.id, w.crack, w.wall.id, "3", "12.00", unit=PriceUnit.LM, position=2)
    w.dusty = await risk_of(db, w.inspection.id, "DUSTY_SUBSTRATE_PRIME")
    w.crack_risk = await risk_of(db, w.inspection.id, "CRACK_RECURRENCE")
    w.rec_prim = await rec(db, w, w.dusty, PRIM)
    w.rec_crack = await rec(db, w, w.crack_risk, CRACK)
    return w


# --- the read model ------------------------------------------------------------------------------------------------------------


async def test_a_recommended_work_takes_its_price_from_the_current_estimate(db_session):
    w = await full_world(db_session, 9901)
    works = await RecommendedWorkReadModel(db_session).build(w.owner.id, w.project.id)
    assert (works.estimate_version, works.estimate_status) == (1, "FINAL")
    assert [(i.room_name, i.surface_name, i.work_code, i.accepted) for i in works.items] == [
        ("Salon", "Ściana A", PRIM, False), ("Salon", "Ściana A", CRACK, False)]
    prim = next(i for i in works.items if i.work_code == PRIM)
    assert prim.prices == (EstimatePrice(Decimal("24.500"), "M2", Decimal("6.00"), Decimal("147.00"), "PLN"),)
    assert prim.priced and prim.work_name_key == "pricebook.seed.prim_std" and prim.risk_title_keys == ("risk.dusty_substrate_prime.title",)
    crack = next(i for i in works.items if i.work_code == CRACK)
    assert crack.prices[0].unit == "LM" and crack.prices[0].amount == Decimal("36.00") and works.unpriced == ()


async def test_the_current_estimate_is_the_latest_one_that_is_not_archived(db_session):
    w = await full_world(db_session, 9902)
    draft = await estimate(db_session, w.owner.id, w.project.id, version=2, status=EstimateStatus.DRAFT)
    await line(db_session, draft.id, w.prim, w.wall.id, "30", "7.00", position=1)
    works = await RecommendedWorkReadModel(db_session).build(w.owner.id, w.project.id)
    assert (works.estimate_version, works.estimate_status) == (2, "DRAFT")
    by_code = {i.work_code: i for i in works.items}
    assert by_code[PRIM].prices[0].unit_price == Decimal("7.00") and by_code[CRACK].prices == () and not by_code[CRACK].priced
    draft_row = (await db_session.execute(select(Estimate).where(Estimate.id == draft.id))).scalar_one()
    draft_row.status = EstimateStatus.ARCHIVED
    await db_session.commit()
    assert (await RecommendedWorkReadModel(db_session).build(w.owner.id, w.project.id)).estimate_version == 1


async def test_a_price_is_the_same_work_on_the_same_surface_and_nothing_else(db_session):
    w = await full_world(db_session, 9903)
    other_wall = Surface(room_id=w.salon.id, name="Ściana B", surface_type=SurfaceType.WALL)
    db_session.add(other_wall)
    await db_session.commit()
    est = await estimate(db_session, w.owner.id, w.project.id, version=2)
    await line(db_session, est.id, w.prim, other_wall.id, "10", "6.00", position=1)  # the same work, another surface
    works = await RecommendedWorkReadModel(db_session).build(w.owner.id, w.project.id)
    assert works.estimate_version == 2 and all(not i.priced for i in works.items)


async def test_a_second_surface_is_not_priced_by_the_line_of_the_first(db_session):
    w = await full_world(db_session, 9920)
    wall_b = Surface(room_id=w.salon.id, name="Ściana B", surface_type=SurfaceType.WALL)
    db_session.add(wall_b)
    await db_session.commit()
    await rec(db_session, w, w.dusty, PRIM, surface_id=wall_b.id)  # the same work, asked for on wall B, priced only on wall A
    works = await RecommendedWorkReadModel(db_session).build(w.owner.id, w.project.id)
    unpriced = works.unpriced
    assert [(i.surface_name, i.work_code) for i in unpriced] == [("Ściana B", PRIM)]


async def test_a_line_of_an_opening_does_not_price_the_work_of_the_wall(db_session):
    w = await full_world(db_session, 9921)
    await db_session.execute(EstimateLine.__table__.delete().where(EstimateLine.item_code == CRACK))
    await db_session.commit()
    from app.models.opening import Opening, OpeningType

    window = Opening(surface_id=w.wall.id, opening_type=OpeningType.WINDOW, width=Decimal("1.2"), height=Decimal("1.4"), quantity=1)
    db_session.add(window)
    await db_session.commit()
    await line(db_session, w.estimate.id, w.crack, w.wall.id, "2", "12.00", unit=PriceUnit.LM, position=3, opening_id=window.id)
    works = await RecommendedWorkReadModel(db_session).build(w.owner.id, w.project.id)
    assert [i.work_code for i in works.unpriced] == [CRACK]


async def test_an_object_without_an_estimate_has_every_work_unpriced(db_session):
    w = await full_world(db_session, 9904)
    await db_session.execute(EstimateLine.__table__.delete())
    await db_session.execute(Estimate.__table__.delete())
    await db_session.commit()
    works = await RecommendedWorkReadModel(db_session).build(w.owner.id, w.project.id)
    assert works.estimate_version is None and len(works.items) == 2 and len(works.unpriced) == 2


async def test_a_line_without_a_price_is_not_a_price(db_session):
    w = await full_world(db_session, 9905)
    est = await estimate(db_session, w.owner.id, w.project.id, version=2, status=EstimateStatus.DRAFT)
    await line(db_session, est.id, w.prim, w.wall.id, "24.5", None, position=1)
    await line(db_session, est.id, w.crack, w.wall.id, "3", "12.00", unit=PriceUnit.LM, position=2)
    works = await RecommendedWorkReadModel(db_session).build(w.owner.id, w.project.id)
    assert [i.work_code for i in works.unpriced] == [PRIM]


async def test_dismissed_inactive_room_level_and_archived_recommendations_are_not_listed(db_session):
    w = await full_world(db_session, 9906)
    for row in (w.rec_prim, w.rec_crack):
        await db_session.delete(row)
    await db_session.commit()
    await rec(db_session, w, w.dusty, PRIM, status=WorkRecommendationStatus.DISMISSED)
    await rec(db_session, w, w.dusty, PRIM, active=False)
    await rec(db_session, w, w.dusty, PRIM, kind=T.ROOM, surface_id=None)
    works = await RecommendedWorkReadModel(db_session).build(w.owner.id, w.project.id)
    assert works.items == ()
    accepted = await rec(db_session, w, w.dusty, PRIM, status=WorkRecommendationStatus.ACCEPTED)
    assert accepted.status is WorkRecommendationStatus.ACCEPTED
    listed = await RecommendedWorkReadModel(db_session).build(w.owner.id, w.project.id)
    assert [(i.work_code, i.accepted) for i in listed.items] == [(PRIM, True)]
    w.wall.is_archived = True
    await db_session.commit()
    assert (await RecommendedWorkReadModel(db_session).build(w.owner.id, w.project.id)).items == ()
    w.wall.is_archived = False
    w.inspection.is_archived = True
    await db_session.commit()
    assert (await RecommendedWorkReadModel(db_session).build(w.owner.id, w.project.id)).items == ()
    w.inspection.is_archived = False
    w.salon.is_archived = True
    await db_session.commit()
    assert (await RecommendedWorkReadModel(db_session).build(w.owner.id, w.project.id)).items == ()


async def test_several_reasons_for_one_work_on_one_surface_make_one_entry(db_session):
    w = await full_world(db_session, 9907)
    await rec(db_session, w, w.crack_risk, PRIM)  # a second risk asks for the same primer
    works = await RecommendedWorkReadModel(db_session).build(w.owner.id, w.project.id)
    prim = [i for i in works.items if i.work_code == PRIM]
    assert len(prim) == 1 and set(prim[0].risk_title_keys) == {"risk.dusty_substrate_prime.title", "risk.crack_recurrence.title"}


async def test_an_accepted_work_is_priced_by_the_price_item_it_was_accepted_with(db_session):
    w = await full_world(db_session, 9908)
    custom = await item(db_session, w.owner.id, "CUSTOM_PRIMER", display_name="Grunt specjalny")
    est = await estimate(db_session, w.owner.id, w.project.id, version=2)
    await line(db_session, est.id, custom, w.wall.id, "20", "9.00", position=1)
    await db_session.delete(w.rec_prim)
    await db_session.commit()
    await rec(db_session, w, w.dusty, PRIM, status=WorkRecommendationStatus.ACCEPTED, resolved=custom)
    works = await RecommendedWorkReadModel(db_session).build(w.owner.id, w.project.id)
    entry = next(i for i in works.items if i.work_code == PRIM)
    assert entry.priced and entry.work_display_name == "Grunt specjalny" and entry.prices[0].unit_price == Decimal("9.00")


async def test_another_owners_prices_and_estimates_are_never_used(db_session):
    w = await full_world(db_session, 9909)
    stranger = await full_world(db_session, 9910)
    with pytest.raises(ProjectNotFoundError):
        await RecommendedWorkReadModel(db_session).build(stranger.owner.id, w.project.id)
    # the stranger prices the same work differently: it must not leak into the first owner's object
    est = (await db_session.execute(select(EstimateLine).where(EstimateLine.estimate_id == stranger.estimate.id, EstimateLine.item_code == PRIM))).scalar_one()
    est.unit_price, est.amount = Decimal("99.00"), Decimal("2425.50")
    await db_session.commit()
    mine = await RecommendedWorkReadModel(db_session).build(w.owner.id, w.project.id)
    assert next(i for i in mine.items if i.work_code == PRIM).prices[0].unit_price == Decimal("6.00")


async def test_the_number_of_statements_does_not_depend_on_the_number_of_recommendations(db_session):
    w = await full_world(db_session, 9911)

    async def count() -> int:
        statements = []

        def collect(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(test_engine.sync_engine, "before_cursor_execute", collect)
        try:
            await RecommendedWorkReadModel(db_session).build(w.owner.id, w.project.id)
        finally:
            event.remove(test_engine.sync_engine, "before_cursor_execute", collect)
        return len(statements)

    first = await count()
    for n in range(4):
        wall = Surface(room_id=w.salon.id, name=f"Ściana {n}", surface_type=SurfaceType.WALL)
        db_session.add(wall)
        await db_session.commit()
        await rec(db_session, w, w.dusty, PRIM, surface_id=wall.id)
    assert await count() == first and first <= 12


# --- the document ---------------------------------------------------------------------------------------------------------------------------


def work(price=True, name_key="pricebook.seed.prim_std", **kw) -> RecommendedWork:
    prices = (EstimatePrice(Decimal("24.500"), "M2", Decimal("6.00"), Decimal("147.00"), "PLN"),) if price else ()
    base = {"room_id": uuid.uuid4(), "room_name": "Salon", "surface_id": uuid.uuid4(), "surface_name": "Ściana A", "work_code": PRIM,
                "work_display_name": None, "work_name_key": name_key, "risk_title_keys": ("risk.dusty_substrate_prime.title",),
                "finding_label_keys": (), "accepted": False, "prices": prices}
    base.update(kw)
    return RecommendedWork(**base)


def works(*items, version=3, status="FINAL") -> RecommendedWorks:
    return RecommendedWorks(version, status, tuple(items))


def test_the_block_shows_risk_work_and_price_exactly_as_in_the_estimate():
    view = recommended_view(works(work(), work(work_code=CRACK, name_key="pricebook.seed.skim_crack", risk_title_keys=("risk.crack_recurrence.title",),
                                              prices=(EstimatePrice(Decimal(3), "LM", Decimal("12.00"), Decimal("36.00"), "PLN"),))))
    assert (view.estimate_version, view.estimate_is_draft, view.total, view.currency) == (3, False, Decimal("183.00"), "PLN")
    first = view.rows[0]
    assert first.place == "Salon › Ściana A" and first.work == "Gruntowanie gruntem penetrującym (pod szpachlowanie)"
    assert first.reason == "Zakurzone podłoże" and view.rows[1].reason == "Pęknięcia podłoża"
    assert (first.quantity, first.unit, first.unit_price, first.amount) == (Decimal("24.500"), "M2", Decimal("6.00"), Decimal("147.00"))


def test_nothing_recommended_means_no_block():
    assert recommended_view(works()) is None


def test_a_work_without_a_price_stops_the_document_and_names_it():
    with pytest.raises(DocumentDataError) as caught:
        recommended_view(works(work(), work(price=False, surface_name="Ściana B")))
    error = caught.value
    assert error.reason == "RECOMMENDED_WORK_UNPRICED" and error.details["count"] == 1 and error.details["estimate_version"] == 3
    assert error.details["works"].startswith("Salon › Ściana B: ")
    with pytest.raises(DocumentDataError):
        recommended_view(RecommendedWorks(None, None, (work(price=False),)))  # no estimate at all
    with pytest.raises(DocumentDataError):
        recommended_view(works(work(prices=(EstimatePrice(Decimal(1), "M2", None, None, "PLN"),))))  # a line to be priced later


def test_two_currencies_are_refused():
    mixed = works(work(), work(prices=(EstimatePrice(Decimal(1), "M2", Decimal("1.00"), Decimal("1.00"), "EUR"),)))
    with pytest.raises(DocumentDataError) as caught:
        recommended_view(mixed)
    assert caught.value.reason == "ESTIMATE_CURRENCY_MIXED"


def test_an_owner_name_and_an_unknown_built_in_key():
    view = recommended_view(works(work(work_display_name="Grunt specjalny", name_key=None, work_name_key=None)))
    assert view.rows[0].work == "Grunt specjalny"
    with pytest.raises(DocumentDataError) as caught:
        recommended_view(works(work(name_key="pricebook.seed.no_such_work")))
    assert caught.value.reason == "CATALOG_NAME_UNKNOWN"


def html_with(recommended) -> str:
    report, names = make_report()
    steps = plan_photo_report(report, photo_details(report, names), project_name="x")
    document = build_photo_report_document(steps, images_for(photos_of(steps)), PROJECT, CLIENT, EXECUTOR, issued_on=TODAY, recommended=recommended)
    return PhotoReportDocumentService.html(document)


def test_the_page_has_a_separate_block_with_the_note_the_rows_and_the_total():
    html = html_with(works(work(), work(work_code=CRACK, name_key="pricebook.seed.skim_crack", risk_title_keys=("risk.crack_recurrence.title",),
                                          prices=(EstimatePrice(Decimal(3), "LM", Decimal("12.00"), Decimal("36.00"), "PLN"),))))
    for expected in ("Rekomendowane prace dodatkowe", "Prace zalecane w związku z wykrytymi ryzykami, wraz z ceną z kosztorysu.",
                     "Ceny wg kosztorysu, wersja 3.", "Salon › Ściana A", "Powód: Zakurzone podłoże", "Powód: Pęknięcia podłoża", "m²", "mb",
                     "24,50", "6,00 zł", "147,00 zł", "36,00 zł", "Razem — rekomendowane prace dodatkowe", "183,00 zł"):
        assert expected in html, expected
    assert html.index("Rekomendowane prace dodatkowe") > html.index("Zdjęcie 14")  # after every photo, a block of its own
    assert "nieznan" not in html and "do ustalenia" not in html
    assert "wersja robocza" not in html


def test_the_block_says_when_the_prices_come_from_a_draft_estimate():
    assert "Ceny wg kosztorysu, wersja 4 (wersja robocza)." in html_with(works(work(), version=4, status="DRAFT"))


def test_no_block_when_nothing_is_recommended():
    assert "Rekomendowane prace dodatkowe" not in html_with(works())
    assert "Rekomendowane prace dodatkowe" not in html_with(None)


def test_a_part_of_a_report_lists_only_the_works_of_its_rooms():
    salon, kuchnia = uuid.uuid4(), uuid.uuid4()
    all_works = works(work(room_id=salon), work(room_id=kuchnia, room_name="Kuchnia"))
    assert [i.room_name for i in all_works.in_rooms(frozenset({kuchnia})).items] == ["Kuchnia"]
    assert all_works.in_rooms(None) is all_works and all_works.in_rooms(frozenset()).items == ()


# --- the service: the check comes first -------------------------------------------------------------------------------------------------------


async def test_issuing_is_refused_before_any_photo_is_read_when_a_work_has_no_price(db_session):
    from tests.test_stage15f2_issuing import issuer

    w = await full_world(db_session, 9912)
    await db_session.execute(EstimateLine.__table__.delete().where(EstimateLine.item_code == CRACK))
    await db_session.commit()
    touched = []
    run = issuer(w.storage)
    run.storage = lambda: touched.append("storage") or w.storage
    from app.models.user import User

    user = (await db_session.execute(select(User).where(User.id == w.owner.id))).scalar_one()
    project_id = w.project.id
    with pytest.raises(DocumentDataError) as caught:
        await run.start_photo_report(db_session, user, project_id)
    assert caught.value.reason == "RECOMMENDED_WORK_UNPRICED" and "Ściana A" in caught.value.details["works"]
    assert run.active == 0 and touched == ["storage"]  # the store is only asked for, no photo is read


async def test_a_part_of_the_report_is_not_stopped_by_a_work_of_another_room(db_session):
    from app.models.room import Room

    w = await full_world(db_session, 9922)
    kuchnia = Room(project_id=w.project.id, name="Kuchnia")
    db_session.add(kuchnia)
    await db_session.commit()
    wall = Surface(room_id=kuchnia.id, name="Ściana K", surface_type=SurfaceType.WALL)
    db_session.add(wall)
    await db_session.commit()
    other = WorkRecommendation(
        trigger_type=WorkRecommendationTriggerType.RISK_RULE, trigger_code="DUSTY_SUBSTRATE_PRIME", source_signature=uuid.uuid4().hex,
        inspection_id=w.inspection.id, room_id=kuchnia.id, surface_id=wall.id, target_kind=T.WALL, recommended_work_code=PRIM,
        status=WorkRecommendationStatus.PENDING, is_active=True, risk_id=w.dusty.id)
    db_session.add(other)
    await db_session.commit()  # in the kitchen, with no line in the estimate
    service = PhotoReportDocumentService(db_session, w.storage, storage_name="r2-primary", max_photos=60)
    owner_id, project_id, salon_id = w.owner.id, w.project.id, w.salon.id
    with pytest.raises(DocumentDataError) as whole:
        await service.prepare(owner_id, project_id)
    assert whole.value.reason == "RECOMMENDED_WORK_UNPRICED" and "Kuchnia › Ściana K" in whole.value.details["works"]
    _, _, _, recommended = await service.prepare(owner_id, project_id, room_ids=frozenset({salon_id}))
    assert {i.room_name for i in recommended.items} == {"Salon"}


async def test_the_summary_counts_the_works_and_names_the_unpriced_ones(db_session):
    w = await full_world(db_session, 9913)
    await db_session.execute(EstimateLine.__table__.delete().where(EstimateLine.item_code == CRACK))
    await db_session.commit()
    summary = await PhotoReportDocumentService(db_session, w.storage, storage_name="r2-primary", max_photos=60).summary(w.owner.id, w.project.id)
    assert summary.recommended_count == 2 and len(summary.unpriced_works) == 1 and summary.unpriced_works[0].startswith("Salon › Ściana A: ")


async def test_the_pdf_carries_the_block_with_the_total(db_session):
    w = await full_world(db_session, 9914)
    service = PhotoReportDocumentService(db_session, w.storage, storage_name="r2-primary", max_photos=60)
    rendered = await service.render(w.owner.id, w.project.id, DocumentRenderer(), issued_on=TODAY)
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(rendered.pdf)).pages).replace(" ", " ")
    assert "Rekomendowane prace dodatkowe" in text and "Ceny wg kosztorysu, wersja 1." in text and "183,00 zł" in text


async def test_a_long_block_breaks_over_pages_keeps_its_header_and_ends_with_the_total():
    many = works(*(work(surface_name=f"Ściana {n}") for n in range(70)))
    report, names = make_report()
    steps = plan_photo_report(report, photo_details(report, names), project_name="x")
    document = build_photo_report_document(steps, images_for(photos_of(steps)), PROJECT, CLIENT, EXECUTOR, issued_on=TODAY, recommended=many)
    rendered = await DocumentRenderer().render(PhotoReportDocumentService.html(document))
    pages = [p.extract_text().replace(" ", " ") for p in PdfReader(io.BytesIO(rendered.pdf)).pages]
    block_pages = [p for p in pages if "Opis pozycji" in p]
    assert len(block_pages) >= 2  # the table header is repeated where the block continues
    assert "Razem — rekomendowane prace dodatkowe 10 290,00 zł" in pages[-1]  # 70 x 147,00
    assert sum(p.count("Powód: Zakurzone podłoże") for p in pages) == 70
