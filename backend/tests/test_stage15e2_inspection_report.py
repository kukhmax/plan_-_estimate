"""Stage 15E.2 — what the inspection itself says in the report: answered checklist, risks, standard and date of the
inspection; plus the per-photo place line, the category of every non-general photo and the full marker legend."""

import io
import json
import uuid
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from pypdf import PdfReader
from sqlalchemy import event

from app.domain.data.risk_rules import build_baseline_risk_rules
from app.domain.documents.catalog import (
    RISK_FILE,
    checklist_names,
    localize_risk_text,
    risk_texts,
)
from app.domain.documents.photo_report_document import (
    PhotoReportDocumentService,
    answer_text,
    build_photo_report_document,
    check_limit,
    inspection_view,
    photos_of,
)
from app.domain.documents.renderer import DocumentRenderer
from app.domain.exceptions import ProjectNotFoundError
from app.domain.services.inspection_report_read_model import (
    AnswerLine,
    InspectionInfo,
    InspectionReportData,
    InspectionReportReadModel,
    RiskLine,
    RoomInfo,
)
from app.domain.services.photo_report_read_model import PhotoReport, ReportRoom
from app.models.checklist import (
    AnswerType,
    ChecklistOption,
    ChecklistQuestion,
    ChecklistSection,
    Substrate,
)
from app.models.inspection import Inspection, InspectionAnswer, InspectionStatus
from app.models.photo_attachment import PhotoCategory
from app.models.risk import Risk, RiskSeverity
from app.models.surface import Surface, SurfaceType
from tests.conftest import test_engine
from tests.test_stage15e_photo_report import (
    CLIENT,
    EXECUTOR,
    PROJECT,
    T0,
    TODAY,
    C,
    details_for,
    images_for,
    make_report,
    plan,
    reason_of,
    rphoto,
    seed,
)

FRONTEND_PL = Path(__file__).resolve().parents[2] / "frontend" / "src" / "locales" / "pl.json"


# --- Polish texts of the risks --------------------------------------------------------------------------------------------


def test_every_built_in_risk_has_its_client_texts_and_nothing_else_is_there():
    keys = {f"risk.{rule.code.lower()}.{part}" for rule in build_baseline_risk_rules() for part in ("title", "explanation", "consequence", "communication")}
    assert len(keys) == 60 and set(risk_texts()) == keys


def test_the_risk_texts_are_the_ones_the_app_shows():
    frontend = json.loads(FRONTEND_PL.read_text(encoding="utf-8"))
    for key, text in risk_texts().items():
        node = frontend
        for part in key.split("."):
            node = node[part]
        assert text == node, key
    assert "risk." in RISK_FILE.read_text(encoding="utf-8")


def test_a_risk_key_becomes_polish_and_anything_else_is_refused():
    assert localize_risk_text("risk.crack_recurrence.title") == "Pęknięcia podłoża"
    for bad in ("risk.crack_recurrence.mitigation", "risk.no_such_rule.title", "Pęknięcia", "checklist.question.cracks_present"):
        assert reason_of(localize_risk_text, bad).reason == "CATALOG_NAME_UNKNOWN"


def test_the_instruction_to_the_contractor_is_never_in_the_client_texts():
    frontend = json.loads(FRONTEND_PL.read_text(encoding="utf-8"))
    mitigation = frontend["risk"]["crack_recurrence"]["mitigation"]
    assert mitigation not in set(risk_texts().values())


# --- one answer as text ---------------------------------------------------------------------------------------------------------


def answer(answer_type="BOOLEAN", **kw) -> AnswerLine:
    base = {"section_key": None, "question_key": "checklist.question.cracks_present", "answer_type": answer_type, "unit": None,
                "value_bool": None, "value_number": None, "value_text": None, "option_label_keys": ()}
    base.update(kw)
    return AnswerLine(**base)


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        (answer(value_bool=True), "Tak"),
        (answer(value_bool=False), "Nie"),
        (answer("NUMBER", value_number=Decimal("12.50"), unit="mm"), "12,50 mm"),
        (answer("NUMBER", value_number=Decimal("12.345")), "12,345"),
        (answer("TEXT", value_text="wilgoć przy oknie"), "wilgoć przy oknie"),
        (answer("SINGLE_CHOICE", option_label_keys=("checklist.option.substrate_dusty",)), checklist_names()["checklist.option.substrate_dusty"]),
        (answer("MULTI_CHOICE", option_label_keys=("checklist.option.defect_mold", "checklist.option.defect_delamination")),
         f"{checklist_names()['checklist.option.defect_mold']}, {checklist_names()['checklist.option.defect_delamination']}"),
        (answer("MULTI_CHOICE", option_label_keys=()), "brak"),
    ],
)
def test_an_answer_is_printed_in_polish_with_its_unit(line, expected):
    assert answer_text(line) == expected


def info(**kw) -> InspectionInfo:
    base = {"inspection_id": uuid.uuid4(), "room_id": uuid.uuid4(), "surface_id": None, "surface_name": "Ściana A", "plane": None,
                "status": "COMPLETED", "created_at": T0, "completed_at": T0 + timedelta(hours=2), "substrate": "CONCRETE",
                "quality_target": "S2", "notes": None, "answers": (), "risks": ()}
    base.update(kw)
    return InspectionInfo(**base)


RISK = RiskLine("HIGH", "risk.crack_recurrence.title", "risk.crack_recurrence.explanation", "risk.crack_recurrence.consequence",
                "risk.crack_recurrence.communication", True)


def test_answers_are_grouped_by_checklist_section_in_the_order_given():
    lines = (answer(section_key=None, question_key="checklist.question.cracks_present", value_bool=True),
             answer(section_key="checklist.section.general_conditions", question_key="checklist.question.unevenness_mm",
                    answer_type="NUMBER", unit="mm", value_number=Decimal(4)),
             answer(section_key="checklist.section.general_conditions", question_key="checklist.question.cracks_present", value_bool=False),
             answer(section_key="checklist.section.drywall_joints", question_key="checklist.question.board_movement", value_bool=True))
    view = inspection_view(info(answers=lines))
    assert [g.title for g in view.groups] == [None, "Stan ogólny", "Połączenia płyt g-k"]
    assert [len(g.rows) for g in view.groups] == [1, 2, 1]
    assert view.groups[1].rows[0].answer == "4,00 mm"


def test_a_risk_view_carries_the_client_texts_and_the_flag():
    view = inspection_view(info(risks=(RISK,)))
    risk = view.risks[0]
    assert (risk.severity, risk.title, risk.blocks_finishing) == ("HIGH", "Pęknięcia podłoża", True)
    assert risk.consequence == risk_texts()["risk.crack_recurrence.consequence"] and risk.proposal.startswith("Wykonam")


# --- the plan with details ---------------------------------------------------------------------------------------------------------


SALON, KUCHNIA = uuid.UUID(int=101), uuid.UUID(int=102)


def two_room_report():
    salon, kuchnia = SALON, KUCHNIA
    report = PhotoReport(uuid.uuid4(), (), (ReportRoom(salon, "Salon", (rphoto(C.ROOM),), (), ()),))
    rooms = (RoomInfo(salon, "Salon", T0), RoomInfo(kuchnia, "Kuchnia", T0 + timedelta(hours=1)))
    return report, salon, kuchnia, rooms


def test_a_room_with_only_inspection_answers_gets_its_heading_and_the_inspection():
    report, _salon, kuchnia, rooms = two_room_report()
    content = info(room_id=kuchnia, answers=(answer(value_bool=True),))
    steps = plan(report, {}, details=InspectionReportData(rooms, (content,)))
    assert [s.kind for s in steps] == ["room", "room", "inspection"]
    assert steps[1].title == "Kuchnia" and steps[1].photos == () and steps[2].info is content
    assert steps[2].path == ("Kuchnia", "Badanie podłoża — Ściana A")


def test_an_inspection_with_nothing_to_say_and_no_photo_is_left_out_and_so_is_its_room():
    report, _salon, kuchnia, rooms = two_room_report()
    empty = info(room_id=kuchnia)
    draft = info(room_id=kuchnia, status="DRAFT", completed_at=None)
    steps = plan(report, {}, details=InspectionReportData(rooms, (empty, draft)))
    assert [s.kind for s in steps] == ["room"] and steps[0].title == "Salon"


def test_the_details_of_an_inspection_that_also_has_photos_sit_on_its_heading():
    report, names = make_report()
    first = report.rooms[0].inspections[0]
    details = details_for(report, names)
    rich = InspectionInfo(**{**{f: getattr(details.inspections[0], f) for f in details.inspections[0].__slots__},
                              "answers": (answer(value_bool=True),), "risks": (RISK,)})
    details = InspectionReportData(details.rooms, (rich, *details.inspections[1:]))
    steps = plan(report, names, details=details)
    inspections = [s for s in steps if s.kind == "inspection"]
    assert inspections[0].info is rich and inspections[1].info is None
    assert inspections[0].photos == first.photos


def test_the_report_may_consist_of_inspection_answers_alone_but_not_of_nothing():
    _report, _salon, kuchnia, rooms = two_room_report()
    only_answers = PhotoReport(uuid.uuid4(), (), ())
    content = info(room_id=kuchnia, risks=(RISK,))
    details = InspectionReportData(rooms, (content,))
    steps = plan(only_answers, {}, details=details)
    check_limit(only_answers, details, steps, 60)  # zero photos, one inspection with risks: allowed
    assert photos_of(steps) == []
    empty = InspectionReportData(rooms, (info(room_id=kuchnia),))
    assert reason_of(check_limit, only_answers, empty, plan(only_answers, {}, details=empty), 60).reason == "REPORT_EMPTY"


# --- the page ------------------------------------------------------------------------------------------------------------------------


def build_with(infos, report=None):
    report = report or PhotoReport(uuid.uuid4(), (), ())
    _, _salon, kuchnia, rooms = two_room_report()
    details = InspectionReportData(rooms, tuple(infos))
    steps = plan(report, {}, details=details)
    return build_photo_report_document(steps, images_for(photos_of(steps)), PROJECT, CLIENT, EXECUTOR, issued_on=TODAY), kuchnia


def test_the_page_prints_the_standard_the_date_the_answers_and_the_risks():
    _, _, kuchnia, _ = two_room_report()
    lines = (answer(section_key="checklist.section.general_conditions", value_bool=True),
             answer("NUMBER", section_key="checklist.section.general_conditions", question_key="checklist.question.unevenness_mm", value_number=Decimal(7), unit="mm"))
    document, _ = build_with([info(room_id=kuchnia, answers=lines, risks=(RISK,), notes="Dom z lat 70.", quality_target="S3", substrate="GYPSUM_PLASTER")])
    html = PhotoReportDocumentService.html(document)
    for expected in ("Badanie podłoża — Ściana A", "(zakończone)", "Podłoże", "tynk gipsowy", "Docelowy standard wykończenia", "S3",
                     "Data zakończenia badania", "08.10.2026", "Uwagi do badania", "Dom z lat 70.", "Odpowiedzi z listy kontrolnej",
                     "Stan ogólny", "Tak", "7,00 mm", "Wykryte ryzyka", "wysokie", "Pęknięcia podłoża", "Konsekwencje:",
                     "Proponowane rozwiązanie:", "Wykonam", "Prace wykończeniowe w tym miejscu należy wstrzymać"):
        assert expected in html, expected


def test_the_instruction_to_the_contractor_and_the_warranty_flag_are_not_on_the_page():
    _, _, kuchnia, _ = two_room_report()
    frontend = json.loads(FRONTEND_PL.read_text(encoding="utf-8"))
    document, _ = build_with([info(room_id=kuchnia, risks=(RISK,))])
    html = PhotoReportDocumentService.html(document)
    assert frontend["risk"]["crack_recurrence"]["mitigation"] not in html
    assert "odpowiedzialności" not in html and "gwarancj" not in html.lower() and "VAT" not in html


def test_a_blocking_risk_says_so_and_a_non_blocking_one_does_not():
    _, _, kuchnia, _ = two_room_report()
    soft = RiskLine("LOW", *RISK_KEYS, False)
    html = PhotoReportDocumentService.html(build_with([info(room_id=kuchnia, risks=(soft,))])[0])
    assert "wstrzymać" not in html and "niskie" in html


RISK_KEYS = ("risk.crack_recurrence.title", "risk.crack_recurrence.explanation", "risk.crack_recurrence.consequence", "risk.crack_recurrence.communication")


def test_no_raw_key_reaches_the_page_and_no_answers_means_no_answers_block():
    _, _, kuchnia, _ = two_room_report()
    html = PhotoReportDocumentService.html(build_with([info(room_id=kuchnia, risks=(RISK,), notes="x")])[0])
    assert "risk." not in html.replace("risk-", "").replace('class="risk', "") and "checklist." not in html
    assert "Odpowiedzi z listy kontrolnej" not in html and "Wykryte ryzyka" in html


def test_every_photo_says_where_it_was_taken():
    report, names = make_report()
    steps = plan(report, names)
    document = build_photo_report_document(steps, images_for(photos_of(steps)), PROJECT, CLIENT, EXECUTOR, issued_on=TODAY)
    places = [v.place for b in document.blocks for row in b.rows for v in row]
    assert places[0] == "Mieszkanie Mokotów"
    assert "Salon" in places and "Salon › Ściana A" in places and "Salon › Ściana A › Otwór: Okno" in places
    assert any(p.startswith("Salon › Ściana A › Praca: Zabezpieczenie podłóg") for p in places)
    assert "Salon › Badanie podłoża — Ściana A" in places and "Salon › Badanie podłoża — Sufit" in places
    assert any(p.startswith("Salon › Badanie podłoża — Ściana A › Ustalenie: ") for p in places)
    html = PhotoReportDocumentService.html(document)
    assert 'class="place">Salon › Ściana A › Otwór: Okno' in html


def test_the_category_is_printed_for_every_photo_that_is_not_general():
    report = PhotoReport(uuid.uuid4(), (rphoto(C.PROJECT, category=PhotoCategory.DEFECT), rphoto(C.PROJECT, category=PhotoCategory.GENERAL, minute=1)), ())
    steps = plan(report, {})
    document = build_photo_report_document(steps, images_for(photos_of(steps)), PROJECT, CLIENT, EXECUTOR, issued_on=TODAY)
    defect, general = (v for row in document.blocks[0].rows for v in row)
    assert defect.show_category and not general.show_category
    html = PhotoReportDocumentService.html(document)
    assert "· Wada ·" in html and "· Ogólne ·" not in html


def test_a_marker_without_a_label_is_listed_as_without_description():
    from tests.test_stage15e_photo_report import marker

    report = PhotoReport(uuid.uuid4(), (rphoto(C.PROJECT, markers=[marker(0.2, 0.2, "pęknięcie"), marker(0.5, 0.5)]),), ())
    steps = plan(report, {})
    document = build_photo_report_document(steps, images_for(photos_of(steps)), PROJECT, CLIENT, EXECUTOR, issued_on=TODAY)
    assert "Oznaczenia: 1 – pęknięcie; 2 – (bez opisu)" in PhotoReportDocumentService.html(document)


async def test_a_report_of_answers_alone_renders_without_a_single_picture():
    _, _, kuchnia, _ = two_room_report()
    document, _ = build_with([info(room_id=kuchnia, answers=(answer(value_bool=True),), risks=(RISK,))])
    rendered = await DocumentRenderer().render(PhotoReportDocumentService.html(document), {})
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(rendered.pdf)).pages)
    assert "Wykryte ryzyka" in text and "Pęknięcia podłoża" in text and "Liczba zdjęć: 0" in text


# --- from the database --------------------------------------------------------------------------------------------------------------------


async def world(db, telegram_id=9601):
    w = await seed(db, telegram_id=telegram_id)
    section = ChecklistSection(template_id=w.question.template_id, key="general", position=1, title_key="checklist.section.general_conditions")
    db.add(section)
    await db.flush()
    w.question.section_id = section.id
    q_num = ChecklistQuestion(id=uuid.UUID(int=w.owner.telegram_user_id * 10 + 1), template_id=w.question.template_id, section_id=section.id, position=2, key="q2",
                              text_key="checklist.question.unevenness_mm", answer_type=AnswerType.NUMBER, unit_key="mm")
    q_one = ChecklistQuestion(id=uuid.UUID(int=w.owner.telegram_user_id * 10 + 2), template_id=w.question.template_id, section_id=section.id, position=3, key="q3",
                              text_key="checklist.question.substrate_condition", answer_type=AnswerType.SINGLE_CHOICE)
    q_skip = ChecklistQuestion(template_id=w.question.template_id, section_id=section.id, position=4, key="q4",
                               text_key="checklist.question.adhesion_weak", answer_type=AnswerType.BOOLEAN)
    db.add_all([q_num, q_one, q_skip])
    await db.flush()
    db.add(ChecklistOption(question_id=q_one.id, position=1, key="DUSTY", label_key="checklist.option.substrate_dusty"))
    await db.commit()
    db.add_all([
        InspectionAnswer(inspection_id=w.inspection.id, question_id=w.question.id, value_bool=True),
        InspectionAnswer(inspection_id=w.inspection.id, question_id=q_num.id, value_number=Decimal("6.5")),
        InspectionAnswer(inspection_id=w.inspection.id, question_id=q_one.id, option_key="DUSTY"),
        InspectionAnswer(inspection_id=w.inspection.id, question_id=q_skip.id),  # touched, not answered
    ])

    def risk(severity, code, position, active=True):
        slug = code.lower()
        return Risk(room_id=w.salon.id, inspection_id=w.inspection.id, risk_code=code, rule_code=code, rule_version=1,
                    severity=severity, title_key=f"risk.{slug}.title", explanation_key=f"risk.{slug}.explanation",
                    consequence_key=f"risk.{slug}.consequence", mitigation_key=f"risk.{slug}.mitigation",
                    communication_key=f"risk.{slug}.communication", source_signature=uuid.uuid4().hex, is_active=active,
                    position=position, blocks_finishing=severity is RiskSeverity.CRITICAL)

    db.add_all([risk(RiskSeverity.LOW, "DUSTY_SUBSTRATE_PRIME", 0), risk(RiskSeverity.CRITICAL, "MOISTURE_BLOCK_FINISHING", 5),
                risk(RiskSeverity.HIGH, "CRACK_RECURRENCE", 1), risk(RiskSeverity.HIGH, "BOARD_MOVEMENT_CRACK", 0),
                risk(RiskSeverity.CRITICAL, "MOLD_TREATMENT_BEFORE_FINISH", 9, active=False)])
    w.inspection.notes = "  Stary tynk.  "
    w.inspection.quality_target = None
    await db.commit()
    w.q_num, w.q_one = q_num, q_one
    return w


async def test_the_reader_returns_answered_questions_and_active_risks_in_order(db_session):
    w = await world(db_session)
    data = await InspectionReportReadModel(db_session).build(w.owner.id, w.project.id)
    assert [r.name for r in data.rooms] == ["Salon", "Kuchnia"]
    (inspection,) = data.inspections
    assert inspection.surface_name == "Ściana A" and inspection.status == "COMPLETED" and inspection.notes == "Stary tynk."
    assert [a.question_key for a in inspection.answers] == [
        "checklist.question.cracks_present", "checklist.question.unevenness_mm", "checklist.question.substrate_condition"]
    assert inspection.answers[1].value_number == Decimal("6.5") and inspection.answers[1].unit == "mm"
    assert inspection.answers[2].option_label_keys == ("checklist.option.substrate_dusty",)
    assert {a.section_key for a in inspection.answers} == {"checklist.section.general_conditions"}
    assert [(r.severity, r.title_key) for r in inspection.risks] == [
        ("CRITICAL", "risk.moisture_block_finishing.title"), ("HIGH", "risk.board_movement_crack.title"),
        ("HIGH", "risk.crack_recurrence.title"), ("LOW", "risk.dusty_substrate_prime.title")]
    assert inspection.risks[0].blocks_finishing and not inspection.risks[1].blocks_finishing


async def test_a_draft_inspection_has_no_answers_or_risks_in_the_report(db_session):
    w = await world(db_session, telegram_id=9602)
    w.inspection.status = InspectionStatus.DRAFT
    await db_session.commit()
    (inspection,) = (await InspectionReportReadModel(db_session).build(w.owner.id, w.project.id)).inspections
    assert inspection.status == "DRAFT" and inspection.answers == () and inspection.risks == () and not inspection.has_content


async def test_archived_things_leave_the_report(db_session):
    w = await world(db_session, telegram_id=9603)
    w.wall.is_archived = True
    await db_session.commit()
    assert (await InspectionReportReadModel(db_session).build(w.owner.id, w.project.id)).inspections == ()
    w.wall.is_archived = False
    w.inspection.is_archived = True
    await db_session.commit()
    assert (await InspectionReportReadModel(db_session).build(w.owner.id, w.project.id)).inspections == ()
    w.inspection.is_archived = False
    w.salon.is_archived = True
    await db_session.commit()
    data = await InspectionReportReadModel(db_session).build(w.owner.id, w.project.id)
    assert [r.name for r in data.rooms] == ["Kuchnia"] and data.inspections == ()


async def test_another_owner_cannot_read_the_inspections_of_a_project(db_session):
    w = await world(db_session, telegram_id=9604)
    stranger = await world(db_session, telegram_id=9605)
    with pytest.raises(ProjectNotFoundError):
        await InspectionReportReadModel(db_session).build(stranger.owner.id, w.project.id)
    mine = await InspectionReportReadModel(db_session).build(w.owner.id, w.project.id)
    theirs = await InspectionReportReadModel(db_session).build(stranger.owner.id, stranger.project.id)
    assert {i.inspection_id for i in mine.inspections}.isdisjoint({i.inspection_id for i in theirs.inspections})


async def test_the_number_of_statements_does_not_depend_on_the_number_of_inspections(db_session):
    w = await world(db_session, telegram_id=9606)
    counts = []

    async def run() -> int:
        statements = []

        def count(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(test_engine.sync_engine, "before_cursor_execute", count)
        try:
            await InspectionReportReadModel(db_session).build(w.owner.id, w.project.id)
        finally:
            event.remove(test_engine.sync_engine, "before_cursor_execute", count)
        return len(statements)

    counts.append(await run())
    for n in range(5):
        extra_wall = Surface(room_id=w.salon.id, name=f"Ściana {n}", surface_type=SurfaceType.WALL)
        db_session.add(extra_wall)
        await db_session.flush()
        inspection = Inspection(room_id=w.salon.id, surface_id=extra_wall.id, template_id=w.question.template_id,
                                substrate=Substrate.CONCRETE, status=InspectionStatus.COMPLETED, created_at=T0 + timedelta(minutes=n + 1))
        db_session.add(inspection)
        await db_session.flush()
        db_session.add(InspectionAnswer(inspection_id=inspection.id, question_id=w.question.id, value_bool=True))
        await db_session.commit()
    counts.append(await run())
    assert counts[0] == counts[1] and counts[0] <= 10


async def test_the_service_prints_the_inspection_from_the_database(db_session):
    w = await world(db_session, telegram_id=9607)
    document, _ = await w.service().build(w.owner.id, w.project.id, issued_on=TODAY)
    html = PhotoReportDocumentService.html(document)
    for expected in ("Stan ogólny", "6,50 mm", checklist_names()["checklist.option.substrate_dusty"], "Stary tynk.", "beton",
                     "Wykryte ryzyka", "krytyczne", "Prace wykończeniowe w tym miejscu należy wstrzymać"):
        assert expected in html, expected
    assert html.index("krytyczne") < html.index("niskie")  # the most severe risk first
    assert "Odtłuszczanie" not in html and "wykryto pleśń" not in html.lower()  # the inactive risk is not there


async def test_the_pdf_of_an_inspection_with_answers_risks_and_photos(db_session):
    w = await world(db_session, telegram_id=9608)
    rendered = await w.service().render(w.owner.id, w.project.id, DocumentRenderer(), issued_on=TODAY)
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(rendered.pdf)).pages)
    for expected in ("Odpowiedzi z listy kontrolnej", "Wykryte ryzyka", "Podłoże", "Zdjęcie 1", "Salon › Badanie podłoża — Ściana A"):
        assert expected in text, expected
