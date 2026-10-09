"""Stage 16E.2 — the contract: the gate, the document with its annexes, the working version with empty lines, the freeze (snapshot,
the exact page, the estimate), the journal and delivery, the HTTP API, the clause catalogue and the migration."""
import importlib.util
import io
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from httpx import AsyncClient
from pypdf import PdfReader
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError

from app.domain.contracts import gate as G
from app.domain.contracts.clauses import ClauseCatalog, load_clause_catalog
from app.domain.contracts.gate import evaluate_gate, load_gate_data
from app.domain.documents.contract_document import build_contract_document, render_contract_html
from app.domain.documents.renderer import DocumentRenderer
from app.domain.exceptions import ContractGateError, ContractNotEditableError, DocumentDataError, ProjectNotFoundError
from app.domain.services.contract_service import ContractService
from app.models.checklist import QualityLevel
from app.models.contract import Contract
from app.models.estimate import Estimate, EstimateStatus
from app.models.project_representative import ProjectRepresentative
from tests.test_clients import OTHER_USER, VALID_USER
from tests.test_stage15e_photo_report import seed as seed_photos
from tests.test_stage15f2_api import login, use_issuer  # noqa: F401  (a fixture)
from tests.test_stage15f2_issuing import Delivery, issuer, journal, text_of, user_of
from tests.test_stage16c_tech_card import plan, world

TODAY = date(2026, 10, 10)
OWNER_TG, STRANGER_TG = VALID_USER["id"], OTHER_USER["id"]
BACKEND = Path(__file__).resolve().parents[1]


async def person(db, w, name="Anna Nowak", authorised=True) -> ProjectRepresentative:
    row = ProjectRepresentative(owner_id=w.owner.id, project_id=w.project.id, side="CUSTOMER", name=name, role_title="Właścicielka",
                                phone="+48 600 100 200", may_accept_and_sign=authorised)
    db.add(row)
    await db.commit()
    return row


async def estimate(db, w, status=EstimateStatus.FINAL, total="147.00", version=1) -> Estimate:
    row = Estimate(owner_id=w.owner.id, project_id=w.project.id, version=version, status=status, total=Decimal(total))
    db.add(row)
    await db.commit()
    return row


async def draft(db, w, **answers) -> Contract:
    row = Contract(owner_id=w.owner.id, project_id=w.project.id, version=1, status="DRAFT", answers=answers, questionnaire_version=1)
    db.add(row)
    await db.commit()
    return row


async def ready(db, telegram_id=9801):
    """A world that passes the gate: an address for the client, a planned wall with its standard and inspection, a final estimate,
    an authorised person chosen in a draft with every required answer."""
    w = await world(db, telegram_id=telegram_id)
    client = w.project.client_id
    from app.models.client import Client

    row = (await db.execute(select(Client).where(Client.id == client))).scalar_one()
    row.street, row.postal_code, row.city = "ul. Zielona 5/7", "30-001", "Kraków"
    await db.commit()
    await plan(db, w.wall, [w.item_a, w.item_b], waits=(24, None))
    await estimate(db, w)
    w.person = await person(db, w)
    w.contract = await draft(db, w, client_status="CONSUMER", conclusion_mode="PREMISES_OF_EXECUTOR", who_accepts=[str(w.person.id)], contract_date="2026-10-12", contract_place="Kraków",
                             advance_percent=30, payment_mode="BY_STAGES", payment_due_days=14, warranty_months=24,
                             downtime_rate_per_day="150.00", work_start_date="2026-10-20",
                             premises_requirement_values={"lighting_permanent": True, "lighting_level": 300, "temperature_range": {"min": 5, "max": 25}})
    return w


def codes(blockers) -> list[str]:
    return [b.code for b in blockers]


async def gate_of(db, w, contract=None):
    data = await load_gate_data(db, w.owner.id, w.project.id)
    contract = contract or w.contract
    from app.domain.contracts.answers import effective_answers
    from app.domain.contracts.catalog import load_contract_catalog

    return evaluate_gate(effective_answers(contract.answers or {}, load_contract_catalog()), data), data


# --- the gate ---------------------------------------------------------------------------------------------------------------------


async def test_a_complete_contract_passes_the_gate(db_session):
    w = await ready(db_session)
    blockers, _ = await gate_of(db_session, w)
    assert blockers == []


async def test_an_empty_world_lists_every_thing_to_fix_in_the_order_of_fixing(db_session):
    w = await world(db_session, with_profile=False)
    w.contract = await draft(db_session, w)
    blockers, _ = await gate_of(db_session, w)
    assert codes(blockers) == [G.EXECUTOR_PROFILE_REQUIRED, G.CLIENT_ADDRESS_INCOMPLETE, G.ANSWERS_MISSING, G.NO_PLANNED_WORKS, G.ESTIMATE_REQUIRED]
    by_code = {b.code: b.details for b in blockers}
    assert by_code[G.CLIENT_ADDRESS_INCOMPLETE] == {"missing": ["street", "postal_code", "city"]}
    assert by_code[G.ANSWERS_MISSING] == {"keys": ["client_status", "conclusion_mode", "who_accepts", "contract_date", "contract_place"]}


async def test_each_blocker_stands_alone_and_goes_away_when_fixed(db_session):
    w = await ready(db_session)
    from app.models.client import Client

    client = (await db_session.execute(select(Client).where(Client.id == w.project.client_id))).scalar_one()
    client.city = ""
    await db_session.commit()
    assert codes((await gate_of(db_session, w))[0]) == [G.CLIENT_ADDRESS_INCOMPLETE]
    assert (await gate_of(db_session, w))[0][0].details == {"missing": ["city"]}
    client.city = "Kraków"
    w.person.may_accept_and_sign = False
    await db_session.commit()
    blockers, _ = await gate_of(db_session, w)
    assert codes(blockers) == [G.PERSON_NOT_AUTHORISED] and blockers[0].details == {"ids": [str(w.person.id)]}
    w.person.may_accept_and_sign = True
    w.person.is_archived = True
    await db_session.commit()
    assert codes((await gate_of(db_session, w))[0]) == [G.PERSON_NOT_AUTHORISED]
    w.person.is_archived = False
    await db_session.commit()
    assert (await gate_of(db_session, w))[0] == []


async def test_a_surface_without_its_standard_blocks_and_is_named(db_session):
    w = await ready(db_session)
    from app.models.work_plan import SurfaceWorkPlan

    row = (await db_session.execute(select(SurfaceWorkPlan).where(SurfaceWorkPlan.surface_id == w.wall.id))).scalar_one()
    row.quality_target = None
    await db_session.commit()
    (blocker,) = (await gate_of(db_session, w))[0]
    assert blocker.code == G.SURFACE_INCOMPLETE
    assert blocker.details == {"items": [{"room": "Salon", "surface": "Ściana A", "surface_type": "WALL", "missing": ["QUALITY_TARGET"]}]}
    row.quality_target = QualityLevel.S2
    await db_session.commit()


async def test_the_estimate_must_exist_and_be_final_but_an_archived_one_does_not_count(db_session):
    w = await ready(db_session)
    current = (await db_session.execute(select(Estimate))).scalar_one()
    current.status = EstimateStatus.DRAFT
    await db_session.commit()
    (blocker,) = (await gate_of(db_session, w))[0]
    assert (blocker.code, blocker.details) == (G.ESTIMATE_NOT_FINAL, {"status": "DRAFT", "version": 1})
    current.status = EstimateStatus.ARCHIVED
    await db_session.commit()
    assert codes((await gate_of(db_session, w))[0]) == [G.ESTIMATE_REQUIRED]
    current.status = EstimateStatus.ACCEPTED
    await db_session.commit()
    assert (await gate_of(db_session, w))[0] == []


async def test_a_foreign_project_is_not_found_by_the_gate(db_session):
    w = await ready(db_session)
    other = await seed_photos(db_session, telegram_id=9802)
    with pytest.raises(ProjectNotFoundError):
        await load_gate_data(db_session, other.owner.id, w.project.id)


# --- the document ---------------------------------------------------------------------------------------------------------------


async def built(db, w, *, working=False, number="UMOWA/2026/10/10/1200"):
    from app.domain.contracts.answers import effective_answers
    from app.domain.contracts.catalog import load_contract_catalog

    data = await load_gate_data(db, w.owner.id, w.project.id)
    effective = effective_answers((w.contract.answers if w.contract else None) or {}, load_contract_catalog())
    return build_contract_document(w.contract, effective, data, working=working, issued_on=TODAY, number=None if working else number), data


def said(document, section_key: str, n: int) -> str:
    """The first (or only) text printed for clause `n` of the section, placeholders filled in; a blank prints as `___`."""
    (section,) = [x for x in document.sections if x.key == section_key]
    (clause,) = [c for c in section.clauses if c.number == n]
    return " ".join("".join("___" if seg.kind == "blank" else seg.text for seg in alt) for alt in clause.alternatives)


async def test_the_contract_prints_the_answers_the_price_the_persons_and_the_annexes(db_session):
    w = await ready(db_session)
    document, _ = await built(db_session, w)
    assert len(document.sections) == 23 and document.sections[3].title == "Wynagrodzenie" and document.sections[13].title == "Odbiory"
    price = said(document, "remuneration", 2)
    assert price.startswith("Szacunkowe wynagrodzenie wynosi 147,00\xa0zł netto, powiększone o podatek VAT w stawce ___, tj. ___ brutto.")
    assert "wersja 1)" in said(document, "remuneration", 1) and "do dnia" not in said(document, "remuneration", 4)
    assert said(document, "deadlines", 1).startswith("Rozpoczęcie Prac: 20.10.2026,") and said(document, "deadlines", 2).startswith("Zakończenie Prac: ___.")
    assert said(document, "advance_and_payments", 1).startswith("Zamawiający wpłaca zaliczkę w wysokości 30\xa0% wynagrodzenia szacunkowego, tj. ___,")
    assert said(document, "advance_and_payments", 2) == "Sposób płatności: etapami — po każdym odbiorze częściowym, według obmiaru."
    assert "w terminie 14\xa0dni od doręczenia" in said(document, "advance_and_payments", 3)
    assert "w ciągu 3\xa0Dni roboczych od zgłoszenia" in said(document, "acceptance", 2) and said(document, "acceptance", 1).startswith("Strony przewidują odbiory częściowe")
    assert "w wysokości 150,00\xa0zł za dobę, łącznie nie więcej niż ___ wynagrodzenia" in said(document, "downtime", 3)
    assert "dłużej niż ___" in said(document, "downtime", 5)  # no default: a line to write in
    assert "na okres 24\xa0miesięcy od dnia odbioru końcowego" in said(document, "warranty", 2)
    assert "nie jest limitowana" in said(document, "evaluation_rules", 5)  # no limit given = no limit
    assert said(document, "liability", 3) == "☐ Kara umowna: Wykonawca zapłaci karę umowną za zwłokę" or "Kara umowna" in said(document, "liability", 3)
    assert [c.number for c in document.sections[11].clauses] == [1, 2, 3]  # the optional insurance clause is left out, the numbers stay
    assert [(p.name, p.side, p.role, p.phone, p.paid_orders) for p in document.persons] == [
        ("Anna Nowak", "Zamawiający", "Właścicielka", "+48 600 100 200", "nie")]
    values = {r.text: r.value for r in document.requirements}
    assert values["Stałe oświetlenie elektryczne w pomieszczeniach"] == "tak"
    assert values["Minimalne natężenie oświetlenia w miejscu pracy"] == "300 lx"
    assert [c.code for c in document.regulation.classes] == ["S2"] and document.regulation.tolerances == ()
    assert [r.value for r in document.intro] == ["12.10.2026", "Kraków", "Mokotów"]
    assert document.layout.client.address_lines == ("ul. Zielona 5/7", "30-001 Kraków")
    assert document.estimate_version == 1 and document.estimate_total == "147,00 zł"


async def test_the_page_has_the_sections_the_annexes_and_the_strong_watermark_while_the_wording_is_not_approved(db_session):
    w = await ready(db_session)
    document, _ = await built(db_session, w)
    html = render_contract_html(document)
    body = html[html.index("<body"):]
    assert not load_clause_catalog().approved and document.layout.draft and not document.layout.light_watermark
    assert 'class="watermark"' in body and "UMOWA/2026/10/10/1200" in body
    assert body.count("— do uzupełnienia —") == 0 and "§&nbsp;14. Odbiory" in body and "§&nbsp;23. Postanowienia końcowe" in body
    assert "☒&nbsp;konsument" in body and "☒&nbsp;w lokalu przedsiębiorstwa Wykonawcy" in body and "Wzór formularza odstąpienia" not in body  # annex 11: only off-premises
    notes = [n.text for sec in load_clause_catalog().sections for c in sec.clauses for n in c.review_notes]
    assert notes and all(note not in body for note in notes)  # the questions to the lawyer are never printed
    assert "[L" not in body and "Do wyboru" in body  # the lawyer's notes are never printed; the unanswered penalty is a choice to tick
    assert body.index("§&nbsp;23.") < body.index('class="signatures"') < body.index('<h2 class="annex-title">Załącznik 1 — Karta technologiczna')
    for heading in ("Załącznik 1 — Karta technologiczna", "Załącznik 2 — Plan produkcji prac", "Załącznik 3 — Kosztorys",
                    "Załącznik 4 — Wymagania dla pomieszczeń", "Załącznik 5 — Zasady odbioru prac",
                    "Załącznik 6 — Wzór Protokołu odbioru robót zanikających", "Załącznik 10 — Wzór Zlecenia prac dodatkowych / zamiennych",
                    "Załącznik 12 — Klauzula informacyjna RODO"):
        assert heading in body
    assert "Zakres prac w kolejności wykonania" in body and "Kolejność prac w pomieszczeniach" in body  # the card and the plan inside
    assert "wersji 1; wartość netto (bez podatku VAT): 147,00" in body
    assert "Wartości dopuszczalne: do uzupełnienia" in body and "Zlecenia płatne (§ 5)" in body
    assert body.count("object_name") == 0 and body.count("Mokotów") >= 1
    assert "WERSJA ROBOCZA" in body  # (the watermark text)


async def test_the_whole_packet_is_one_real_pdf_with_the_number_on_every_page(db_session):
    w = await ready(db_session)
    document, _ = await built(db_session, w)
    pdf = (await DocumentRenderer().render(render_contract_html(document))).pdf
    pages = PdfReader(io.BytesIO(pdf)).pages
    assert len(pages) >= 5
    assert all("UMOWA/2026/10/10/1200" in page.extract_text() for page in pages)
    flat = " ".join(text_of(pdf).split())
    for part in ("§ 14. Odbiory", "Załącznik 5", "Załącznik 12", "Anna Nowak", "ul. Zielona 5/7"):
        assert part in flat, part


async def test_the_approved_wording_would_print_without_the_watermark(db_session):
    w = await ready(db_session)
    base = load_clause_catalog().model_dump(mode="json")
    for note in [n for sec in base["sections"] for c in sec["clauses"] for n in c["review_notes"]] + [n for a in base["annexes"] for n in a["review_notes"]]:
        note["status"] = "RESOLVED"
    approved = ClauseCatalog.model_validate({**base, "approved": True, "approved_by": "Jan Kowalski", "approved_on": "2026-10-11"})
    from unittest import mock

    with mock.patch("app.domain.documents.contract_document.load_clause_catalog", return_value=approved):
        document, _ = await built(db_session, w)
        html = render_contract_html(document)
    body = html[html.index("<body"):]
    assert not document.layout.draft and 'class="watermark' not in body
    assert "§&nbsp;14. Odbiory" in body


async def test_the_working_version_never_refuses_and_leaves_lines_to_write_in(db_session):
    w = await world(db_session, with_profile=False)
    w.contract = None
    document, data = await built(db_session, w, working=True)
    assert document.working and document.layout.draft and document.layout.light_watermark and document.layout.meta.number is None
    assert document.persons == () and all(r.value is None for r in document.requirements)
    html = render_contract_html(document)
    body = html[html.index("<body"):]
    assert 'class="watermark light"' in body and body.count('class="write-line"') > 30
    assert "Nie wskazano osób upoważnionych." in body and "Kosztorys: wersja i wartość netto do wpisania." in body
    with pytest.raises(DocumentDataError) as numbered:
        build_contract_document(None, {}, data, working=True, issued_on=TODAY, number="UMOWA/1")
    assert numbered.value.reason == "DRAFT_NUMBERED"
    with pytest.raises(DocumentDataError) as no_profile:
        build_contract_document(None, {}, data, working=False, issued_on=TODAY)
    assert no_profile.value.reason == "EXECUTOR_PROFILE_REQUIRED"


async def test_the_regulation_lists_all_classes_when_nothing_is_planned_and_only_the_planned_ones_otherwise(db_session):
    w = await ready(db_session)
    _, data = await built(db_session, w)
    from app.domain.documents.contract_document import _regulation
    from app.domain.contracts.catalog import load_contract_catalog

    assert [c.code for c in _regulation(data, load_contract_catalog()).classes] == ["S2"]
    data.rooms = ()
    assert [c.code for c in _regulation(data, load_contract_catalog()).classes] == ["S1", "S2", "S3", "S4", "Q1", "Q2", "Q3", "Q4"]


# --- the clause catalogue ---------------------------------------------------------------------------------------------------------


def test_the_clause_catalogue_is_the_prototype_contract_waiting_for_the_lawyer():
    catalog = load_clause_catalog()
    assert catalog.version == 2 and not catalog.approved and catalog.approved_by is None
    assert len(catalog.sections) == 23 and [a.number for a in catalog.annexes] == [6, 7, 8, 9, 10, 11, 12]
    assert catalog.open_notes == ["L7", "L8", "L4", "L2", "L3", "L13", "L5", "L14", "L15"]
    assert [s.key for s in catalog.sections][:3] == ["definitions", "subject", "state_of_premises"]


@pytest.mark.parametrize(
    "change",
    [
        {"approved": True},  # without who and when
        {"approved_by": "Jan"},  # approval without the flag
        {"approved": True, "approved_by": "Jan", "approved_on": "2026-10-11"},  # approved while a question to the lawyer is open
        {"sections": []},
        {"annexes": []},
        {"unknown": 1},
    ],
)
def test_the_clause_catalogue_refuses_an_incomplete_approval_or_the_wrong_sections(change):
    base = load_clause_catalog().model_dump(mode="json")
    with pytest.raises(ValueError):
        ClauseCatalog.model_validate({**base, **change})


# --- issuing --------------------------------------------------------------------------------------------------------------------


NOW = datetime(2026, 10, 10, 8, 30, 0, tzinfo=UTC)


async def test_issuing_freezes_the_contract_numbers_it_sends_the_pdf_and_records_it(db_session):
    w = await ready(db_session, telegram_id=9850)
    owner_id, project_id, contract_id, telegram = w.owner.id, w.project.id, w.contract.id, w.owner.telegram_user_id
    sender = Delivery()
    run = issuer(delivery=sender)
    reservation = await run.start_contract(db_session, await user_of(db_session, owner_id), project_id, contract_id)
    assert (reservation.document.kind, reservation.document.status, reservation.document.source_id, reservation.document.source_version) == (
        "CONTRACT", "PENDING", contract_id, 1)
    assert reservation.document.number.startswith("UMOWA/2026/10/08/")
    await run.drain()
    (done,) = await journal(db_session)
    number = done.number
    assert (done.status, done.error_code, done.title) == ("SENT", None, "Umowa — wersja 1")
    (message,) = sender.sent
    assert message["chat_id"] == telegram and message["filename"].startswith("UMOWA-2026-10-08-")
    assert message["caption"].startswith("Umowa — wersja 1 — Mokotów\nUMOWA/")
    assert number in text_of(message["pdf"])
    db_session.expire_all()
    row = (await db_session.execute(select(Contract).where(Contract.id == contract_id))).scalar_one()
    assert row.status == "ISSUED" and row.issued_at is not None and row.estimate_version == 1 and row.estimate_id is not None
    assert number in row.document_html
    snap = row.snapshot
    assert snap["answers"]["advance_percent"] == 30 and snap["answers"]["customer_appearance_days"] == 3
    assert snap["persons"][0]["name"] == "Anna Nowak" and snap["estimate"]["total"] == "147.00" and snap["estimate"]["version"] == 1
    assert snap["clauses"] == {"version": 2, "approved": False, "approved_by": None}
    assert snap["scope"] == {"rooms": 1, "surfaces": 1, "works": 2, "adjacent_works": 0}
    assert snap["client"]["address"] == ["ul. Zielona 5/7", "30-001 Kraków"]


async def test_a_blocked_contract_takes_no_number_and_stays_a_draft(db_session):
    w = await ready(db_session, telegram_id=9851)
    owner_id, project_id, contract_id = w.owner.id, w.project.id, w.contract.id
    est = (await db_session.execute(select(Estimate))).scalar_one()
    est.status = EstimateStatus.DRAFT
    await db_session.commit()
    run = issuer()
    with pytest.raises(ContractGateError) as blocked:
        await run.start_contract(db_session, await user_of(db_session, owner_id), project_id, contract_id)
    assert [b.code for b in blocked.value.blockers] == [G.ESTIMATE_NOT_FINAL]
    assert await journal(db_session) == [] and run.active == 0
    row = (await db_session.execute(select(Contract).where(Contract.id == contract_id))).scalar_one()
    assert row.status == "DRAFT" and row.document_html is None and row.snapshot is None


async def test_an_issued_contract_cannot_be_issued_or_edited_again(db_session):
    w = await ready(db_session, telegram_id=9852)
    owner_id, project_id, contract_id = w.owner.id, w.project.id, w.contract.id
    run = issuer()
    user = await user_of(db_session, owner_id)
    await run.start_contract(db_session, user, project_id, contract_id)
    await run.drain()
    with pytest.raises(ContractNotEditableError):
        await run.start_contract(db_session, user, project_id, contract_id)
    with pytest.raises(ContractNotEditableError):
        await ContractService(db_session).update_answers(project_id, contract_id, owner_id, {"contract_place": "Łódź"})
    assert len(await journal(db_session)) == 1


async def test_a_new_version_starts_from_the_answers_of_the_last_and_supersedes_it_when_issued(db_session):
    w = await ready(db_session, telegram_id=9853)
    owner_id, project_id, first_id = w.owner.id, w.project.id, w.contract.id
    run = issuer()
    user = await user_of(db_session, owner_id)
    await run.start_contract(db_session, user, project_id, first_id)
    await run.drain()
    service = ContractService(db_session)
    second, created = await service.open_draft(project_id, owner_id)
    assert created and second.version == 2 and second.answers["advance_percent"] == 30
    assert second.answers is not None and second.answers is not w.contract.answers  # a copy, not the same object
    await service.update_answers(project_id, second.id, owner_id, {"advance_percent": 40})
    second_id = second.id
    await run.start_contract(db_session, user, project_id, second_id)
    await run.drain()
    prefixes = [d.number[:5] for d in await journal(db_session)]
    rows = {c.version: c for c in (await db_session.execute(select(Contract))).scalars()}
    assert (rows[1].status, rows[2].status) == ("ARCHIVED", "ISSUED")
    assert rows[1].snapshot["answers"]["advance_percent"] == 30 and rows[2].snapshot["answers"]["advance_percent"] == 40
    assert prefixes == ["UMOWA", "UMOWA"] and rows[2].document_html != rows[1].document_html


async def test_the_issued_page_does_not_change_when_the_data_do(db_session):
    w = await ready(db_session, telegram_id=9854)
    owner_id, project_id, contract_id = w.owner.id, w.project.id, w.contract.id
    sender = Delivery()
    run = issuer(delivery=sender)
    await run.start_contract(db_session, await user_of(db_session, owner_id), project_id, contract_id)
    await run.drain()
    frozen = (await db_session.execute(select(Contract).where(Contract.id == contract_id))).scalar_one().document_html
    from app.models.project import Project

    project = (await db_session.execute(select(Project).where(Project.id == project_id))).scalar_one()
    project.name = "Zupełnie inna nazwa"
    w.person.name = "Ktoś Inny"
    await db_session.commit()
    (row,) = await journal(db_session)
    again = await run._render(db_session, row)  # the same document, made again
    assert (await db_session.execute(select(Contract).where(Contract.id == contract_id))).scalar_one().document_html == frozen
    text = text_of(again.pdf)
    assert "Mokotów" in text and "Anna Nowak" in text and "Zupełnie inna nazwa" not in text and "Ktoś Inny" not in text


async def test_the_preview_follows_the_draft_and_never_leaves_a_row(db_session):
    w = await ready(db_session, telegram_id=9855)
    owner_id, project_id = w.owner.id, w.project.id
    sender = Delivery()
    result = await issuer(delivery=sender).preview_contract(db_session, await user_of(db_session, owner_id), project_id)
    assert result.pages >= 5
    (message,) = sender.sent
    assert message["filename"] == "Umowa-wersja-robocza.pdf" and message["caption"] == "WERSJA ROBOCZA — Umowa — Mokotów"
    text = " ".join(text_of(message["pdf"]).split())
    assert "WERSJA ROBOCZA" in text and "20.10.2026" in text and "Anna Nowak" in text
    assert await journal(db_session) == []


async def test_the_preview_of_an_object_with_nothing_yet_is_a_blank_packet(db_session):
    w = await world(db_session, telegram_id=9856, with_profile=False)
    sender = Delivery()
    result = await issuer(delivery=sender).preview_contract(db_session, await user_of(db_session, w.owner.id), w.project.id)
    assert result.pages >= 3 and len(sender.sent) == 1 and await journal(db_session) == []


# --- HTTP -----------------------------------------------------------------------------------------------------------------------------


def url(project_id, tail=""):
    return f"/api/projects/{project_id}/contracts{tail}"


async def test_the_routes_need_a_token(async_client: AsyncClient, use_issuer):  # noqa: F811
    use_issuer(issuer())
    pid, cid = uuid.uuid4(), uuid.uuid4()
    assert (await async_client.get(url(pid, f"/{cid}/gate"))).status_code == 401
    assert (await async_client.post(url(pid, f"/{cid}/issue"))).status_code == 401
    assert (await async_client.post(f"/api/projects/{pid}/documents/contract/preview")).status_code == 401


async def test_the_gate_route_lists_blockers_then_the_issue_route_works_and_a_second_issue_is_409(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await ready(db_session, telegram_id=OWNER_TG)
    project_id, contract_id = str(w.project.id), str(w.contract.id)
    est = (await db_session.execute(select(Estimate))).scalar_one()
    est.status = EstimateStatus.DRAFT
    await db_session.commit()
    sender = Delivery()
    run = use_issuer(issuer(delivery=sender))
    headers = await login(async_client)
    gate = (await async_client.get(url(project_id, f"/{contract_id}/gate"), headers=headers)).json()
    assert gate == {"ready": False, "blockers": [{"code": "ESTIMATE_NOT_FINAL", "details": {"status": "DRAFT", "version": 1}}]}
    blocked = await async_client.post(url(project_id, f"/{contract_id}/issue"), headers=headers)
    assert blocked.status_code == 422
    assert blocked.json()["detail"]["code"] == "CONTRACT_GATE_BLOCKED"
    assert blocked.json()["detail"]["details"]["blockers"][0]["code"] == "ESTIMATE_NOT_FINAL"
    est.status = EstimateStatus.FINAL
    await db_session.commit()
    assert (await async_client.get(url(project_id, f"/{contract_id}/gate"), headers=headers)).json() == {"ready": True, "blockers": []}
    issued = await async_client.post(url(project_id, f"/{contract_id}/issue"), headers=headers)
    assert issued.status_code == 202, issued.text
    assert issued.json()["kind"] == "CONTRACT" and issued.json()["number"].startswith("UMOWA/") and issued.json()["source_id"] == contract_id
    await run.drain()
    assert len(sender.sent) == 1
    again = await async_client.post(url(project_id, f"/{contract_id}/issue"), headers=headers)
    assert again.status_code == 409 and again.json()["detail"]["code"] == "CONTRACT_NOT_EDITABLE"
    assert (await async_client.get(url(project_id, f"/{contract_id}"), headers=headers)).json()["status"] == "ISSUED"


async def test_the_preview_route_is_a_200_and_a_stranger_gets_404_everywhere(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    mine = await ready(db_session, telegram_id=OWNER_TG)
    theirs = await ready(db_session, telegram_id=STRANGER_TG)
    sender = Delivery()
    use_issuer(issuer(delivery=sender))
    headers = await login(async_client)
    ok = await async_client.post(f"/api/projects/{mine.project.id}/documents/contract/preview", headers=headers)
    assert ok.status_code == 200 and ok.json()["sent"] is True and len(sender.sent) == 1
    for response in (
        await async_client.post(f"/api/projects/{theirs.project.id}/documents/contract/preview", headers=headers),
        await async_client.get(url(theirs.project.id, f"/{theirs.contract.id}/gate"), headers=headers),
        await async_client.post(url(theirs.project.id, f"/{theirs.contract.id}/issue"), headers=headers),
    ):
        assert response.status_code == 404
    assert len(sender.sent) == 1


# --- migration ------------------------------------------------------------------------------------------------------------------------


def load_migration(name: str):
    spec = importlib.util.spec_from_file_location(name, BACKEND / "alembic" / "versions" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(engine, name: str, direction: str):
    module = load_migration(name)
    with engine.begin() as conn:
        module.op = Operations(MigrationContext.configure(conn))
        getattr(module, direction)()


def contract_engine():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.execute(text("CREATE TABLE users (id CHAR(32) PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE projects (id CHAR(32) PRIMARY KEY)"))
        conn.execute(text("INSERT INTO users (id) VALUES ('u1')"))
        conn.execute(text("INSERT INTO projects (id) VALUES ('p1')"))
    run(engine, "0038_issued_documents", "upgrade")
    run(engine, "0041_issued_documents_tech_card", "upgrade")
    run(engine, "0043_issued_docs_plan", "upgrade")
    run(engine, "0044_contracts", "upgrade")
    return engine


CONTRACT = ("INSERT INTO contracts (id, owner_id, project_id, version, status, answers, questionnaire_version, issued_at, snapshot, document_html, created_at, updated_at) "
            "VALUES (:id, 'u1', 'p1', :version, :status, '{}', 1, :issued, :snapshot, :html, '2026-10-10', '2026-10-10')")
JOURNAL = ("INSERT INTO issued_documents (id, owner_id, project_id, kind, title, number, project_seq, template_version, status, issued_at) "
           "VALUES (:id, 'u1', 'p1', :kind, 't', :number, :seq, '1', 'SENT', '2026-10-10')")


def test_revision_chain_and_length():
    module = load_migration("0045_contract_issue")
    assert module.revision == "0045_contract_issue" and module.down_revision == "0044_contracts" and len(module.revision) <= 32


def test_the_database_itself_refuses_an_issued_contract_without_its_snapshot_and_page():
    engine = contract_engine()
    run(engine, "0045_contract_issue", "upgrade")
    frozen = {"issued": "2026-10-10", "snapshot": "{}", "html": "<html></html>"}
    blank = {"issued": None, "snapshot": None, "html": None}
    with engine.begin() as conn:
        conn.execute(text(CONTRACT), {"id": "a", "version": 1, "status": "DRAFT", **blank})
        conn.execute(text(CONTRACT), {"id": "b", "version": 2, "status": "ARCHIVED", **blank})  # an abandoned draft
        conn.execute(text(CONTRACT), {"id": "c", "version": 3, "status": "ISSUED", **frozen})
        conn.execute(text(CONTRACT), {"id": "d", "version": 4, "status": "SIGNED", **frozen})
    for bad in ({"id": "e", "version": 5, "status": "ISSUED", **blank}, {"id": "f", "version": 6, "status": "SIGNED", **{**frozen, "html": None}},
                {"id": "g", "version": 7, "status": "ISSUED", **{**frozen, "snapshot": None}}):
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(text(CONTRACT), bad)
    with engine.begin() as conn:
        conn.execute(text(JOURNAL), {"id": "j", "kind": "CONTRACT", "number": "UMOWA/1", "seq": 1})
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text(JOURNAL), {"id": "k", "kind": "PROTOCOL", "number": "X/1", "seq": 2})


def test_downgrade_refuses_while_an_issued_contract_or_a_journal_row_exists_and_then_works():
    engine = contract_engine()
    run(engine, "0045_contract_issue", "upgrade")
    with engine.begin() as conn:
        conn.execute(text(CONTRACT), {"id": "c", "version": 1, "status": "ISSUED", "issued": "2026-10-10", "snapshot": "{}", "html": "x"})
    with pytest.raises(RuntimeError, match="1 issued contract"):
        run(engine, "0045_contract_issue", "downgrade")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM contracts"))
        conn.execute(text(JOURNAL), {"id": "j", "kind": "CONTRACT", "number": "UMOWA/1", "seq": 1})
    with pytest.raises(RuntimeError, match="1 contract journal row"):
        run(engine, "0045_contract_issue", "downgrade")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM issued_documents"))
        conn.execute(text(CONTRACT), {"id": "d", "version": 1, "status": "DRAFT", "issued": None, "snapshot": None, "html": None})
    run(engine, "0045_contract_issue", "downgrade")
    from sqlalchemy import inspect

    insp = inspect(engine)
    assert {c["name"] for c in insp.get_columns("contracts")} == {"id", "owner_id", "project_id", "version", "status", "answers",
                                                                  "questionnaire_version", "created_at", "updated_at"}
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text(JOURNAL), {"id": "k", "kind": "CONTRACT", "number": "UMOWA/2", "seq": 2})
    with engine.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM contracts")).scalar_one() == 1  # the draft survived


async def test_the_general_issue_route_does_not_take_a_contract(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    """A contract is frozen by its own route; the general one must never turn a CONTRACT request into another document."""
    w = await ready(db_session, telegram_id=OWNER_TG)
    sender = Delivery()
    run = use_issuer(issuer(delivery=sender))
    headers = await login(async_client)
    for body in ({"kind": "CONTRACT"}, {"kind": "CONTRACT", "estimate_id": str(uuid.uuid4())}):
        response = await async_client.post(f"/api/projects/{w.project.id}/documents", json=body, headers=headers)
        assert response.status_code == 422
    assert run.active == 0 and sender.sent == []
