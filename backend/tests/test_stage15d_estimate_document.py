"""Stage 15D — the estimate (Kosztorys) as a document: Polish names, grouping, checks, no VAT, DRAFT preview, owner scope, PDF."""

import io
import json
import re
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pypdf import PdfReader
from sqlalchemy import select

from app.domain.data.price_book_seed import build_approved_price_book_items
from app.domain.documents import formatting
from app.domain.documents.catalog import (
    CATALOG_FILE,
    KEY_PATTERN,
    localize_description,
    price_names,
)
from app.domain.documents.estimate_document import (
    EstimateDocumentService,
    build_estimate_document,
    party_from_client,
)
from app.domain.documents.renderer import DocumentRenderer
from app.domain.exceptions import DocumentDataError, EstimateNotFoundError
from app.domain.services.executor_profile_service import ExecutorProfileService
from app.models.client import Client, ClientType
from app.models.estimate import (
    Estimate,
    EstimateLine,
    EstimateStatus,
    LineOrigin,
    QuantitySource,
)
from app.models.executor_profile import ExecutorProfile
from app.models.price_item import PriceScope, PriceUnit
from app.models.project import Project
from app.models.room import Room
from app.models.surface import Surface, SurfaceType
from app.models.user import User
from app.schemas.estimate import EstimateLineRead, EstimateRead
from app.schemas.executor_profile import ExecutorProfileWrite

FRONTEND_PL = Path(__file__).resolve().parents[2] / "frontend" / "src" / "locales" / "pl.json"
TODAY = date(2026, 10, 8)
NUMBER = "KOSZ/2026/10/08/1953"


# --- builders -------------------------------------------------------------------------------------------------------


def line(pos, desc, room, surface, qty, price, unit=PriceUnit.M2, opening=None, currency="PLN"):
    q = Decimal(qty)
    p = Decimal(price) if price is not None else None
    return EstimateLineRead(
        id=uuid.uuid4(), estimate_id=uuid.uuid4(), origin=LineOrigin.PLANNED_WORK, position=pos, description=desc,
        item_code="X", unit=unit, scope=PriceScope.LABOR, currency=currency, source_quantity=q, quantity=q,
        quantity_source=QuantitySource.SURFACE_NET_AREA, quantity_overridden=False, unit_price=p, price_override=False,
        amount=(q * p).quantize(Decimal("0.01")) if p is not None else None,
        room_name=room, surface_name=surface, opening_name=opening,
    )


def estimate(lines, status=EstimateStatus.FINAL, total="auto", name="Wariant podstawowy", currency="PLN"):
    if total == "auto":
        total = sum((ln.amount for ln in lines if ln.amount is not None), Decimal(0))
    return EstimateRead(
        id=uuid.uuid4(), project_id=uuid.uuid4(), version=2, status=status, name=name, total=total, currency=currency,
        lines=lines, created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
    )


STANDARD = [
    line(1, "pricebook.seed.prep_prot", "Salon", "Ściana A", "24.5", "6.00"),
    line(2, "Gładź gipsowa dwuwarstwowa", "Salon", "Sufit", "18.345", "38.50"),
    line(3, "pricebook.seed.prep_degr", "Łazienka", "Ściana B", "9.2", "12.00", opening="Okno 1"),
    line(4, "Dojazd i załadunek", None, None, "1", "250.00", unit=PriceUnit.FLAT),
]
PROJECT = Project(name="Mieszkanie Mokotów", address="ul. Dobra 10/12", city="Warszawa", postal_code="00-001")
CLIENT = Client(client_type=ClientType.PRIVATE_PERSON, first_name="Anna", last_name="Nowak", phone="+48 500 100 200")
EXECUTOR = ExecutorProfile(
    name="Jan Kowalski Wykończenia", nip="7740001454", street="ul. Długa 1", postal_code="30-001", city="Kraków",
    phone="+48 600 100 200", email="jan@example.pl",
)


def build(est=None, client=CLIENT, executor=EXECUTOR, **kw):
    kw.setdefault("issued_on", TODAY)
    kw.setdefault("number", NUMBER if (est or estimate(STANDARD)).status is not EstimateStatus.DRAFT else None)
    return build_estimate_document(est or estimate(STANDARD), PROJECT, client, executor, **kw)


def html_of(doc):
    return EstimateDocumentService.html(doc)


# --- Polish names of the built-in catalog ----------------------------------------------------------------------------


def test_every_seeded_price_item_has_a_polish_name_and_nothing_else_is_there():
    seed_keys = {item.name_key for item in build_approved_price_book_items()}
    assert len(seed_keys) == 49
    assert set(price_names()) == seed_keys


def test_the_names_are_the_ones_the_app_shows():
    frontend = json.loads(FRONTEND_PL.read_text(encoding="utf-8"))
    for key, text in price_names().items():
        node = frontend
        for part in key.split("."):
            node = node[part]
        assert text == node, key


def test_a_built_in_key_becomes_polish_and_an_owner_name_is_kept():
    assert localize_description("pricebook.seed.prep_prot").startswith("Zabezpieczenie podłóg")
    for own in ("Gładź na wymiar klienta", "Wałek 2.5 mm", "pricebook", "x.y.z", "Pricebook.seed.prep_prot", "pricebook.seed.prep_prot "):
        assert localize_description(own) == own


def test_an_unknown_built_in_key_is_an_error_not_a_raw_key_on_a_client_document():
    with pytest.raises(DocumentDataError) as caught:
        localize_description("pricebook.seed.no_such_work")
    assert caught.value.reason == "CATALOG_NAME_UNKNOWN"
    assert KEY_PATTERN.match("pricebook.seed.no_such_work")
    with pytest.raises(DocumentDataError):
        build(estimate([line(1, "pricebook.seed.no_such_work", "Salon", None, "1", "1.00")]))


def test_the_catalog_file_is_plain_polish_text():
    raw = CATALOG_FILE.read_text(encoding="utf-8")
    assert "pricebook.seed" in raw and all(not v.startswith("pricebook.") for v in price_names().values())


# --- formatting of a quantity ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "expected"),
    [("12.5", "12,50"), ("12.500", "12,50"), ("18.345", "18,345"), ("0.001", "0,001"), ("1234.5", "1 234,50"), ("0", "0,00"), ("7.1", "7,10")],
)
def test_a_quantity_is_never_rounded_away(value, expected):
    assert formatting.format_quantity_exact(Decimal(value)) == expected


def test_the_quantity_filter_refuses_a_float():
    with pytest.raises(TypeError):
        formatting.format_quantity_exact(1.5)  # type: ignore[arg-type]


# --- the document model ------------------------------------------------------------------------------------------------


def test_lines_are_grouped_by_room_in_order_of_appearance_and_numbered_through():
    doc = build()
    assert [g.title for g in doc.groups] == ["Salon", "Łazienka", None]
    assert [ln.number for g in doc.groups for ln in g.lines] == [1, 2, 3, 4]
    assert [ln.description[:12] for g in doc.groups for ln in g.lines][:3] == ["Zabezpieczen", "Gładź gipsow", "Odtłuszczani"]
    assert doc.groups[1].lines[0].detail == "Ściana B · Okno 1" and doc.groups[2].lines[0].detail is None
    assert doc.groups[0].lines[0].detail == "Ściana A"


def test_positions_decide_the_order_not_the_input_order():
    shuffled = [STANDARD[3], STANDARD[1], STANDARD[0], STANDARD[2]]
    doc = build(estimate(shuffled))
    assert [g.title for g in doc.groups] == ["Salon", "Łazienka", None]
    assert [ln.amount for g in doc.groups for ln in g.lines] == [ln.amount for ln in STANDARD]


def test_sums_are_the_stored_amounts_added_up_and_nothing_is_recomputed():
    doc = build()
    assert [g.subtotal for g in doc.groups] == [Decimal("853.28"), Decimal("110.40"), Decimal("250.00")]
    assert doc.total == Decimal("1213.68") == sum(g.subtotal for g in doc.groups)
    # a stored amount that is not quantity x price (an owner override of the snapshot) is printed as stored
    odd = line(1, "Ryczałt", "Salon", None, "3", "10.00")
    odd = odd.model_copy(update={"amount": Decimal("29.99")})
    assert build(estimate([odd])).groups[0].lines[0].amount == Decimal("29.99")


def test_the_client_party_is_a_company_or_a_person():
    assert party_from_client(CLIENT).name == "Anna Nowak"
    company = Client(client_type=ClientType.COMPANY, company_name="Dom-Bud Sp. z o.o.", first_name="Jan", nip="774-000-14-54")
    party = party_from_client(company)
    assert party.name == "Dom-Bud Sp. z o.o." and party.tax_id == "774-000-14-54"
    assert party_from_client(Client(client_type=ClientType.COMPANY, company_name="X", nip="7740001454")).tax_id == "774-000-14-54"
    assert party_from_client(Client(client_type=ClientType.COMPANY, company_name="X", nip="12345")).tax_id == "12345"
    assert party_from_client(Client(client_type=ClientType.PRIVATE_PERSON)).name == "—"


def test_the_executor_and_the_place_come_from_the_profile():
    doc = build()
    assert doc.layout.executor.name == "Jan Kowalski Wykończenia" and doc.layout.meta.place == "Kraków"
    assert doc.layout.meta.number == NUMBER and doc.layout.meta.issued_on == TODAY and doc.layout.meta.title == "Kosztorys"
    assert doc.object_name == "Mieszkanie Mokotów" and doc.object_lines == ("ul. Dobra 10/12", "00-001 Warszawa")


# --- what may be printed -------------------------------------------------------------------------------------------------


def reason_of(**kw):
    with pytest.raises(DocumentDataError) as caught:
        kw.pop("fn", build)(**kw)
    return caught.value.reason


def test_an_archived_or_empty_estimate_is_refused():
    assert reason_of(est=estimate(STANDARD, status=EstimateStatus.ARCHIVED)) == "ESTIMATE_ARCHIVED"
    assert reason_of(est=estimate([], total=None)) == "ESTIMATE_EMPTY"


def test_an_issued_estimate_needs_every_price_and_a_matching_total():
    unpriced = [*STANDARD[:3], line(4, "Dojazd", None, None, "1", None)]
    assert reason_of(est=estimate(unpriced)) == "ESTIMATE_UNPRICED"
    assert reason_of(est=estimate(STANDARD, total=Decimal("1213.67"))) == "ESTIMATE_TOTAL_MISMATCH"
    assert reason_of(est=estimate(STANDARD, total=None)) == "ESTIMATE_TOTAL_MISMATCH"


def test_a_second_currency_is_refused():
    mixed = [*STANDARD[:3], line(4, "Dojazd", None, None, "1", "10.00", currency="EUR")]
    assert reason_of(est=estimate(mixed)) == "ESTIMATE_CURRENCY_MIXED"


def test_an_issued_estimate_needs_the_executor_profile_and_a_draft_does_not():
    assert reason_of(executor=None) == "EXECUTOR_PROFILE_REQUIRED"
    assert reason_of(est=estimate(STANDARD, status=EstimateStatus.ACCEPTED), executor=None) == "EXECUTOR_PROFILE_REQUIRED"
    doc = build(estimate(STANDARD, status=EstimateStatus.DRAFT), executor=None)
    assert doc.layout.executor is None and doc.layout.meta.place is None and doc.layout.draft


def test_an_accepted_estimate_prints_like_a_final_one():
    doc = build(estimate(STANDARD, status=EstimateStatus.ACCEPTED))
    assert not doc.layout.draft and doc.total == Decimal("1213.68")


def test_a_draft_is_never_numbered():
    assert reason_of(est=estimate(STANDARD, status=EstimateStatus.DRAFT), number=NUMBER) == "DRAFT_NUMBERED"
    assert build(estimate(STANDARD, status=EstimateStatus.DRAFT)).layout.meta.number is None


def test_a_draft_with_an_open_price_prints_it_as_to_be_set_and_has_no_total():
    lines = [*STANDARD[:3], line(4, "Dojazd", None, None, "1", None)]
    doc = build(estimate(lines, status=EstimateStatus.DRAFT, total=Decimal("963.68")))
    assert doc.total is None and doc.groups[2].subtotal is None and doc.groups[0].subtotal == Decimal("853.28")
    html = html_of(doc)
    assert html.count("do ustalenia") == 4  # unit price, amount, group total, grand total
    assert "WERSJA ROBOCZA" in html and "nie został jeszcze zatwierdzony" in html


def test_a_priced_draft_still_checks_its_total():
    assert reason_of(est=estimate(STANDARD, status=EstimateStatus.DRAFT, total=Decimal("1.00"))) == "ESTIMATE_TOTAL_MISMATCH"


# --- the printed page --------------------------------------------------------------------------------------------------------


def test_the_page_shows_snapshot_values_in_polish_format():
    html = html_of(build())
    for expected in ("Kosztorys", NUMBER, "08.10.2026", "Wersja 2", "Wariant podstawowy", "Mieszkanie Mokotów", "Salon",
                     "18,345", "706,28 zł", "1 213,68 zł", "ryczałt", "Razem — Salon", "Pozycje ogólne", "NIP: 774-000-14-54"):
        assert expected in html, expected
    assert "WERSJA ROBOCZA" not in html


def test_there_is_no_vat_anywhere_on_the_page():
    text = html_of(build()).lower()
    for word in ("vat", "netto", "brutto", "podatek"):
        assert word not in text


def test_no_raw_translation_key_reaches_the_page():
    assert not re.search(r"pricebook\.[a-z]", html_of(build()))


def test_hostile_names_are_escaped():
    hostile = [line(1, "<script>x</script>", "</td><h1>room</h1>", "<b>s</b>", "1", "1.00")]
    client = Client(client_type=ClientType.PRIVATE_PERSON, first_name="<i>Anna</i>", last_name="Иванова")
    html = html_of(build(estimate(hostile), client=client))
    assert "<script>x" not in html and "<h1>room</h1>" not in html and "<b>s</b>" not in html and "<i>Anna</i>" not in html
    assert "&lt;script&gt;x&lt;/script&gt;" in html and "Иванова" in html


def test_every_label_the_template_prints_is_polish_and_not_a_key():
    html = html_of(build())
    assert not re.search(r"\b(estimate|doc|party|unit)\.[a-z_]+", html)


# --- from the database ------------------------------------------------------------------------------------------------------------


async def seed(db, telegram_id=9401, with_profile=True):
    owner = User(telegram_user_id=telegram_id, username=f"u{telegram_id}")
    db.add(owner)
    await db.flush()
    client = Client(owner_user_id=owner.id, client_type=ClientType.PRIVATE_PERSON, first_name="Anna", last_name="Nowak")
    db.add(client)
    await db.flush()
    project = Project(owner_id=owner.id, client_id=client.id, name="Mokotów", address="ul. Dobra 1", city="Warszawa", postal_code="00-001")
    db.add(project)
    await db.flush()
    room = Room(project_id=project.id, name="Salon")
    db.add(room)
    await db.flush()
    wall = Surface(room_id=room.id, name="Ściana A", surface_type=SurfaceType.WALL)
    db.add(wall)
    await db.flush()
    est = Estimate(owner_id=owner.id, project_id=project.id, version=1, status=EstimateStatus.FINAL, total=Decimal("147.00"))
    db.add(est)
    await db.flush()
    db.add(EstimateLine(
        estimate_id=est.id, origin=LineOrigin.PLANNED_WORK, position=1, room_id=room.id, surface_id=wall.id,
        description="pricebook.seed.prep_prot", unit=PriceUnit.M2, scope=PriceScope.LABOR, source_quantity=Decimal("24.5"),
        quantity=Decimal("24.5"), quantity_source=QuantitySource.SURFACE_NET_AREA, unit_price=Decimal("6.00"), amount=Decimal("147.00"),
    ))
    await db.commit()
    if with_profile:
        await ExecutorProfileService(db).save(owner.id, ExecutorProfileWrite(name="Jan Kowalski Wykończenia", nip="7740001454", city="Kraków"))
    return owner, project, est


async def test_the_service_assembles_the_document_from_the_database(db_session):
    owner, project, est = await seed(db_session)
    doc = await EstimateDocumentService(db_session).build(project.id, est.id, owner.id, issued_on=TODAY, number=NUMBER)
    assert doc.groups[0].title == "Salon" and doc.groups[0].lines[0].detail == "Ściana A"
    assert doc.groups[0].lines[0].description.startswith("Zabezpieczenie podłóg")
    assert doc.layout.client.name == "Anna Nowak" and doc.layout.executor.tax_id == "774-000-14-54" and doc.total == Decimal("147.00")


async def test_another_owner_gets_not_found_for_a_foreign_estimate_or_a_foreign_project(db_session):
    owner, project, est = await seed(db_session)
    stranger, other_project, _ = await seed(db_session, telegram_id=9402)
    service = EstimateDocumentService(db_session)
    with pytest.raises(EstimateNotFoundError):
        await service.build(project.id, est.id, stranger.id, issued_on=TODAY)
    with pytest.raises(EstimateNotFoundError):
        await service.build(other_project.id, est.id, owner.id, issued_on=TODAY)
    with pytest.raises(EstimateNotFoundError):
        await service.build(project.id, uuid.uuid4(), owner.id, issued_on=TODAY)


async def test_the_executor_of_another_owner_never_appears(db_session):
    owner, project, est = await seed(db_session, telegram_id=9403, with_profile=False)
    await seed(db_session, telegram_id=9404)  # somebody else has a profile
    with pytest.raises(DocumentDataError) as caught:
        await EstimateDocumentService(db_session).build(project.id, est.id, owner.id, issued_on=TODAY, number=NUMBER)
    assert caught.value.reason == "EXECUTOR_PROFILE_REQUIRED"
    profiles = (await db_session.execute(select(ExecutorProfile))).scalars().all()
    assert len(profiles) == 1


async def test_a_project_without_a_client_prints_the_missing_marker(db_session):
    owner, project, est = await seed(db_session, telegram_id=9405)
    project.client_id = None
    await db_session.commit()
    doc = await EstimateDocumentService(db_session).build(project.id, est.id, owner.id, issued_on=TODAY, number=NUMBER)
    assert doc.layout.client is None and "— brak danych —" in html_of(doc)


async def test_a_client_of_another_owner_is_never_printed(db_session):
    owner, project, est = await seed(db_session, telegram_id=9406)
    stranger, _, _ = await seed(db_session, telegram_id=9407)
    foreign = (await db_session.execute(select(Client).where(Client.owner_user_id == stranger.id))).scalar_one()
    project.client_id = foreign.id  # cannot happen through the API; the document must still not leak it
    await db_session.commit()
    doc = await EstimateDocumentService(db_session).build(project.id, est.id, owner.id, issued_on=TODAY, number=NUMBER)
    assert doc.layout.client is None


# --- the PDF -------------------------------------------------------------------------------------------------------------------------


def pdf_pages(rendered):
    return [page.extract_text() for page in PdfReader(io.BytesIO(rendered.pdf)).pages]


async def test_the_pdf_carries_the_numbered_estimate_with_polish_text():
    rendered = await DocumentRenderer().render(html_of(build()))
    text = "\n".join(pdf_pages(rendered))
    assert rendered.pdf.startswith(b"%PDF") and rendered.pages == 1
    for expected in ("Kosztorys", NUMBER, "Zabezpieczenie podłóg", "Gładź gipsowa dwuwarstwowa", "Anna Nowak", "Jan Kowalski Wykończenia", "Strona 1 z 1"):
        assert expected in text, expected
    assert "1 213,68" in text.replace(" ", " ")
    assert "WERSJA ROBOCZA" not in text


async def test_the_draft_pdf_has_the_watermark_and_no_number():
    rendered = await DocumentRenderer().render(html_of(build(estimate(STANDARD, status=EstimateStatus.DRAFT))))
    text = "\n".join(pdf_pages(rendered))
    assert "WERSJA ROBOCZA" in text and "KOSZ/" not in text


async def test_a_long_estimate_repeats_the_header_numbers_the_pages_and_marks_every_draft_page():
    many = [line(i + 1, "Gładź gipsowa dwuwarstwowa z szlifowaniem", f"Pomieszczenie {i // 6 + 1}", f"Ściana {i % 6 + 1}", "12.5", "38.50") for i in range(72)]
    final = await DocumentRenderer().render(html_of(build(estimate(many))))
    pages = pdf_pages(final)
    assert final.pages == len(pages) >= 3
    assert all("Opis pozycji" in page for page in pages), "the table header must repeat on every page"
    assert all(f"Strona {n} z {final.pages}" in page for n, page in enumerate(pages, 1))
    assert "34 650,00" in pages[-1].replace(" ", " ")
    draft = await DocumentRenderer().render(html_of(build(estimate(many, status=EstimateStatus.DRAFT))))
    assert all("WERSJA ROBOCZA" in page for page in pdf_pages(draft))
