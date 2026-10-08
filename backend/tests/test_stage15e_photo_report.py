"""Stage 15E — the inspection photo report as a document: print pictures, marker / contour geometry, document order,
the 60-photo limit and parts by room, Polish texts, owner scope and the real PDF."""

import io
import json
import re
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader
from sqlalchemy import select

from app.domain.data.checklist_templates import build_baseline_templates
from app.domain.documents.catalog import (
    CHECKLIST_FILE,
    checklist_names,
    localize_checklist_text,
)
from app.domain.documents.layout import Party
from app.domain.documents.photo_report_document import (
    PRINT_MAX_EDGE,
    PhotoReportDocumentService,
    PrintImage,
    asset_files,
    build_photo_report_document,
    check_limit,
    frame_width_mm,
    marker_shapes,
    outline_shapes,
    photos_of,
    plan_photo_report,
    prepare_print_image,
)
from app.domain.documents.renderer import DocumentRenderer
from app.domain.exceptions import DocumentDataError, ProjectNotFoundError
from app.domain.services.executor_profile_service import ExecutorProfileService
from app.domain.services.media_storage import InMemoryMediaStorage
from app.domain.services.photo_report_read_model import (
    PhotoReport,
    ReportFinding,
    ReportInspection,
    ReportMarker,
    ReportOpening,
    ReportPhoto,
    ReportQuestion,
    ReportRoom,
    ReportSurface,
    ReportWork,
)
from app.models.checklist import (
    AnswerType,
    ChecklistQuestion,
    ChecklistTemplate,
    Substrate,
)
from app.models.client import Client, ClientType
from app.models.executor_profile import ExecutorProfile
from app.models.inspection import Inspection, InspectionFinding, InspectionStatus
from app.models.photo_asset import PhotoAssetStatus
from app.models.photo_attachment import (
    PhotoAttachment,
    PhotoAttachmentContext,
    PhotoCategory,
)
from app.models.project import Project
from app.models.room import Room
from app.models.surface import Surface, SurfaceType
from app.models.user import User
from app.schemas.executor_profile import ExecutorProfileWrite
from tests.test_stage14b4_photo_asset import raw_asset

FRONTEND_PL = Path(__file__).resolve().parents[2] / "frontend" / "src" / "locales" / "pl.json"
TODAY = date(2026, 10, 8)
T0 = datetime(2026, 10, 8, 12, 30, tzinfo=UTC)
C = PhotoAttachmentContext
PROJECT = Project(name="Mieszkanie Mokotów", address="ul. Dobra 10/12", city="Warszawa", postal_code="00-001")
CLIENT = Client(client_type=ClientType.PRIVATE_PERSON, first_name="Anna", last_name="Nowak")
EXECUTOR = ExecutorProfile(name="Jan Kowalski Wykończenia", nip="7740001454", city="Kraków")


def jpeg(width=1600, height=1200, color=(120, 140, 160), **save) -> bytes:
    image = Image.new("RGB", (width, height), color)
    for i in range(0, width, 40):  # some texture so the file is not trivially small
        for j in range(0, height, 40):
            image.putpixel((i, j), (i % 255, j % 255, 90))
    out = io.BytesIO()
    image.save(out, "JPEG", **save)
    return out.getvalue()


def marker(x, y, label=None, outline=None, position=0):
    return ReportMarker(uuid.uuid4(), x, y, label, position, outline)


def rphoto(context=C.ROOM, *, category=PhotoCategory.GENERAL, caption=None, markers=(), asset_id=None, minute=0, captured=True,
           storage_name="r2-primary", **ids) -> ReportPhoto:
    asset_id = asset_id or uuid.uuid4()
    base = {"room_id": None, "surface_id": None, "opening_id": None, "inspection_id": None, "question_id": None, "finding_id": None,
                "occurrence_key": None, "price_item_id": None}
    base.update(ids)
    when = T0 + timedelta(minutes=minute)
    return ReportPhoto(
        attachment_id=uuid.uuid4(), asset_id=asset_id, context=context, category=category, caption=caption,
        include_in_report=True, position=0, width=1600, height=1200, content_type="image/jpeg", byte_size=1, sha256="0" * 64,
        captured_at=when if captured else None, uploaded_at=when, storage_name=storage_name,
        storage_key_display=f"photos/v1/{asset_id}/display.jpg", storage_key_original=f"photos/v1/{asset_id}/original.jpg",
        markers=tuple(markers), **base,
    )


def images_for(photos, width=1000, height=750) -> dict:
    data = jpeg(width, height)
    return {p.asset_id: PrintImage(data, width, height) for p in photos}


def make_report() -> tuple[PhotoReport, dict]:
    """One project photo; a Salon with a wall (own photo, a window, two works), an inspection of that wall with a question
    and a finding; a Kuchnia with one photo."""
    wall_id, window_id, ins_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    question = ReportQuestion(uuid.uuid4(), "checklist.question.cracks_present", 1, (rphoto(C.INSPECTION, minute=5), rphoto(C.INSPECTION, minute=6)))
    finding = ReportFinding(uuid.uuid4(), uuid.uuid4(), "CRACKS", "checklist.question.unevenness_mm", {"number": "12.5"}, True,
                            (rphoto(C.FINDING, minute=7, markers=[marker(0.25, 0.5, "rysa przy oknie", [(0.1, 0.1), (0.2, 0.3), (0.4, 0.4)]), marker(0.9, 0.95)]),))
    gone = ReportFinding(uuid.uuid4(), uuid.uuid4(), "MOLD", "checklist.question.cracks_present", {"bool": True}, False, (rphoto(C.FINDING, minute=8),))
    inspection = ReportInspection(ins_id, wall_id, None, "COMPLETED", (rphoto(C.INSPECTION, minute=4),), (question,), (finding, gone))
    ceiling_inspection = ReportInspection(uuid.uuid4(), None, "CEILING", "DRAFT", (rphoto(C.INSPECTION, minute=9),), (), ())
    works = (
        ReportWork(uuid.uuid4(), uuid.uuid4(), "CENNIK_PREP_PROT-01", "pricebook.seed.prep_prot", None, True,
                   (rphoto(C.WORK, category=PhotoCategory.BEFORE, minute=2), rphoto(C.WORK, category=PhotoCategory.AFTER, minute=3))),
        ReportWork(uuid.uuid4(), uuid.uuid4(), "CUSTOM_X", None, "Gładź na wymiar", False, (rphoto(C.WORK, category=PhotoCategory.IN_PROGRESS, minute=3),)),
    )
    surface = ReportSurface(wall_id, "Ściana A", "WALL", (rphoto(C.SURFACE, minute=1),), (ReportOpening(window_id, "Okno", (rphoto(C.OPENING, minute=1),)),), works)
    salon = ReportRoom(uuid.uuid4(), "Salon", (rphoto(C.ROOM, caption="Widok ogólny <b>salonu</b>"),), (surface,), (inspection, ceiling_inspection))
    kuchnia = ReportRoom(uuid.uuid4(), "Kuchnia", (rphoto(C.ROOM, minute=10),), (), ())
    report = PhotoReport(uuid.uuid4(), (rphoto(C.PROJECT, minute=0),), (salon, kuchnia))
    return report, {wall_id: "Ściana A"}


def reason_of(fn, *args, **kw) -> DocumentDataError:
    with pytest.raises(DocumentDataError) as caught:
        fn(*args, **kw)
    return caught.value


# --- the print picture -------------------------------------------------------------------------------------------------


def test_a_large_photo_is_scaled_to_the_print_size_and_stays_a_jpeg():
    printed = prepare_print_image(jpeg(3000, 2000))
    assert (printed.width, printed.height) == (PRINT_MAX_EDGE, 667)
    image = Image.open(io.BytesIO(printed.data))
    assert image.format == "JPEG" and image.size == (printed.width, printed.height) and len(printed.data) < 400_000


def test_a_small_photo_is_never_scaled_up():
    printed = prepare_print_image(jpeg(400, 300))
    assert (printed.width, printed.height) == (400, 300)


def test_exif_orientation_is_applied_and_no_metadata_is_kept():
    image = Image.new("RGB", (1200, 800), "white")
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90 degrees: a portrait photo stored as landscape pixels
    out = io.BytesIO()
    image.save(out, "JPEG", exif=exif)
    printed = prepare_print_image(out.getvalue())
    assert printed.height > printed.width
    assert not Image.open(io.BytesIO(printed.data)).getexif()


def test_a_transparent_png_is_flattened():
    out = io.BytesIO()
    Image.new("RGBA", (50, 50), (255, 0, 0, 0)).save(out, "PNG")
    printed = prepare_print_image(out.getvalue())
    assert Image.open(io.BytesIO(printed.data)).mode == "RGB"


@pytest.mark.parametrize("raw", [b"", b"not an image", jpeg()[:200]])
def test_an_unreadable_photo_is_an_error_not_a_gap(raw):
    assert reason_of(prepare_print_image, raw).reason == "PHOTO_UNREADABLE"


def test_a_photo_with_too_many_pixels_is_refused_before_decoding():
    assert reason_of(prepare_print_image, jpeg(400, 300), max_pixels=100_000).reason == "PHOTO_UNREADABLE"


# --- geometry of markers and contours ----------------------------------------------------------------------------------------


def test_a_marker_sits_at_its_fraction_of_the_picture_and_is_numbered_in_order():
    first, second = marker_shapes((marker(0.25, 0.5), marker(1.0, 0.0)), 1000, 750)
    assert (first.number, first.cx, first.cy, first.r) == (1, "250.0", "375.0", "32.0")
    assert (second.number, second.cx, second.cy) == (2, "1000.0", "0.0")
    assert float(first.ty) > float(first.cy)  # the baseline of the digit is below the centre of the dot


def test_a_marker_outside_the_picture_is_pulled_onto_it():
    shape = marker_shapes((marker(-0.2, 1.4),), 1000, 750)[0]
    assert (shape.cx, shape.cy) == ("0.0", "750.0")


def test_a_contour_is_a_polyline_in_picture_units_and_a_single_point_is_no_contour():
    shapes = outline_shapes((marker(0.1, 0.1, outline=[(0.1, 0.2), (0.5, 0.4), (1.0, 1.0)]), marker(0.5, 0.5), marker(0.2, 0.2, outline=[(0.1, 0.1)])), 1000, 500)
    assert [s.points for s in shapes] == ["100.0,100.0 500.0,200.0 1000.0,500.0"]
    assert float(shapes[0].under_width) > float(shapes[0].width) > 0


def test_the_dot_size_follows_the_picture_width():
    small = marker_shapes((marker(0.5, 0.5),), 500, 375)[0]
    large = marker_shapes((marker(0.5, 0.5),), 1000, 750)[0]
    assert float(large.r) == 2 * float(small.r)


def test_a_portrait_photo_is_printed_narrower_so_it_does_not_take_a_page():
    assert frame_width_mm(1000, 750) == "87.0"  # landscape: the whole cell
    assert frame_width_mm(750, 1000) == "67.5"  # portrait: 90 mm high at most
    assert frame_width_mm(200, 1000) == "18.0" and frame_width_mm(400, 300) == "87.0"
    html = PhotoReportDocumentService.html(build()[0])
    assert 'style="width: 87.0mm"' in html


# --- the plan: order, headings, limit -----------------------------------------------------------------------------------------


def kinds(steps):
    return [s.kind for s in steps]


def test_the_plan_follows_the_document_order_of_the_read_model():
    report, names = make_report()
    steps = plan_photo_report(report, names)
    assert kinds(steps) == ["project", "room", "surface", "opening", "work", "work", "inspection", "question", "finding", "finding",
                            "inspection", "room"]
    photos = photos_of(steps)
    assert len(photos) == 14
    assert [s.title for s in steps if s.kind in ("room", "surface", "opening")] == ["Salon", "Ściana A", "Okno", "Kuchnia"]


def test_names_are_polish_and_owner_names_are_kept():
    report, names = make_report()
    steps = plan_photo_report(report, names)
    works = [s for s in steps if s.kind == "work"]
    assert works[0].title.startswith("Zabezpieczenie podłóg") and not works[0].muted
    assert works[1].title == "Gładź na wymiar" and works[1].muted
    assert [s.title for s in steps if s.kind == "question"] == [checklist_names()["checklist.question.cracks_present"]]
    findings = [s for s in steps if s.kind == "finding"]
    assert findings[0].detail == "12,50 mm" and not findings[0].muted
    assert findings[1].detail == "tak" and findings[1].muted
    inspections = [s for s in steps if s.kind == "inspection"]
    assert (inspections[0].title, inspections[0].code, inspections[0].detail) == ("Ściana A", None, "COMPLETED")
    assert (inspections[1].title, inspections[1].code, inspections[1].detail) == (None, "CEILING", "DRAFT")


def test_a_text_finding_keeps_its_text():
    finding = ReportFinding(uuid.uuid4(), uuid.uuid4(), "X", None, {"text": "wilgoć przy oknie"}, True, (rphoto(C.FINDING),))
    room = ReportRoom(uuid.uuid4(), "Salon", (), (), (ReportInspection(uuid.uuid4(), None, None, "COMPLETED", (), (), (finding,)),))
    step = next(s for s in plan_photo_report(PhotoReport(uuid.uuid4(), (), (room,)), {}) if s.kind == "finding")
    assert (step.title, step.detail) == (None, "wilgoć przy oknie")


def test_a_part_of_the_report_is_chosen_by_room_and_leaves_the_project_photos_out_unless_asked():
    report, names = make_report()
    kuchnia = report.rooms[1].room_id
    part = plan_photo_report(report, names, room_ids=frozenset({kuchnia}), include_project_photos=False)
    assert kinds(part) == ["room"] and part[0].title == "Kuchnia"
    with_project = plan_photo_report(report, names, room_ids=frozenset({kuchnia}))
    assert kinds(with_project) == ["project", "room"]
    assert plan_photo_report(report, names, room_ids=frozenset(), include_project_photos=False) == ()


def test_exactly_the_limit_passes_and_one_more_is_refused_with_counts_per_room():
    def room(name, count):
        return ReportRoom(uuid.uuid4(), name, tuple(rphoto(C.ROOM) for _ in range(count)), (), ())

    report = PhotoReport(uuid.uuid4(), (rphoto(C.PROJECT),), (room("Salon", 40), room("Kuchnia", 19)))
    steps = plan_photo_report(report, {})
    check_limit(report, steps, 60)  # 1 + 40 + 19 = 60
    bigger = PhotoReport(uuid.uuid4(), (rphoto(C.PROJECT),), (room("Salon", 40), room("Kuchnia", 20)))
    error = reason_of(check_limit, bigger, plan_photo_report(bigger, {}), 60)
    assert error.reason == "PHOTO_LIMIT_EXCEEDED"
    assert error.details["count"] == 61 and error.details["limit"] == 60 and error.details["project_photos"] == 1
    assert [(r["name"], r["count"]) for r in error.details["rooms"]] == [("Salon", 40), ("Kuchnia", 20)]
    part = plan_photo_report(bigger, {}, room_ids=frozenset({bigger.rooms[1].room_id}), include_project_photos=False)
    check_limit(bigger, part, 60)


def test_a_report_without_photos_is_refused():
    assert reason_of(check_limit, PhotoReport(uuid.uuid4(), (), ()), (), 60).reason == "REPORT_EMPTY"


# --- the document --------------------------------------------------------------------------------------------------------------------


def build(report=None, names=None, **kw):
    if report is None:
        report, names = make_report()
    steps = plan_photo_report(report, names or {})
    images = images_for(photos_of(steps))
    kw.setdefault("issued_on", TODAY)
    document = build_photo_report_document(steps, images, PROJECT, CLIENT, kw.pop("executor", EXECUTOR), **kw)
    return document, steps, images


def test_photos_are_numbered_through_the_document_two_to_a_row():
    document, _steps, _ = build()
    views = [p for b in document.blocks for row in b.rows for p in row]
    assert [v.number for v in views] == list(range(1, len(views) + 1)) and document.photo_count == len(views) == 14
    assert all(len(row) <= 2 for b in document.blocks for row in b.rows)
    work_block = next(b for b in document.blocks if b.kind == "work")
    assert [len(r) for r in work_block.rows] == [2] and [v.show_category for v in work_block.rows[0]] == [True, True]
    assert [v.category for v in work_block.rows[0]] == ["BEFORE", "AFTER"]
    assert not any(v.show_category for b in document.blocks if b.kind != "work" for row in b.rows for v in row)


def test_five_photos_make_rows_of_two_two_one_and_every_html_row_has_two_cells():
    report = PhotoReport(uuid.uuid4(), tuple(rphoto(C.PROJECT, minute=i) for i in range(5)), ())
    document, *_ = build(report, {})
    assert [len(row) for row in document.blocks[0].rows] == [2, 2, 1]
    html = PhotoReportDocumentService.html(document)
    rows = re.findall(r"<tr>(.*?)</tr>", html.split('<table class="photos">', 1)[1].split("</table>", 1)[0], re.S)
    assert len(rows) == 3 and all(row.count("<td") == 2 for row in rows)


def test_the_date_is_the_time_of_the_shot_and_the_upload_time_when_the_phone_gave_none():
    shot = rphoto(C.PROJECT, minute=0)
    shot = shot.__class__(**{**{f: getattr(shot, f) for f in shot.__slots__}, "captured_at": T0 - timedelta(days=2)})
    unknown = rphoto(C.PROJECT, minute=5, captured=False)
    document, *_ = build(PhotoReport(uuid.uuid4(), (shot, unknown), ()), {})
    first, second = (v for row in document.blocks[0].rows for v in row)
    assert first.taken_on == T0 - timedelta(days=2) and second.taken_on == unknown.uploaded_at
    html = PhotoReportDocumentService.html(document)
    assert "06.10.2026 14:30" in html and "08.10.2026 14:35" in html


def test_the_same_picture_is_one_file_and_every_reference_has_a_file():
    report, names = make_report()
    shared = rphoto(C.ROOM, asset_id=uuid.uuid4(), minute=11)
    twin = rphoto(C.SURFACE, asset_id=shared.asset_id, minute=12)
    report = PhotoReport(report.project_id, report.project_photos + (shared, twin), report.rooms)
    document, steps, images = build(report, names)
    files = asset_files(document, steps, images)
    used = {v.asset_name for b in document.blocks for row in b.rows for v in row}
    assert used == set(files) and len(files) == len(photos_of(steps)) - 1  # the twin shares the picture


def test_markers_carry_their_numbers_and_only_labelled_ones_are_in_the_legend():
    document, *_ = build()
    view = next(v for b in document.blocks for row in b.rows for v in row if v.markers)
    assert [m.number for m in view.markers] == [1, 2]
    assert view.legend == ((1, "rysa przy oknie"),) and len(view.outlines) == 1


def test_a_missing_picture_or_executor_is_an_error():
    report, names = make_report()
    steps = plan_photo_report(report, names)
    partial = images_for(photos_of(steps)[:-1])
    assert reason_of(build_photo_report_document, steps, partial, PROJECT, CLIENT, EXECUTOR, issued_on=TODAY).reason == "PHOTO_UNAVAILABLE"
    assert reason_of(build_photo_report_document, steps, images_for(photos_of(steps)), PROJECT, CLIENT, None, issued_on=TODAY).reason == "EXECUTOR_PROFILE_REQUIRED"


def test_the_page_is_polish_complete_and_escaped():
    document, steps, images = build()
    html = PhotoReportDocumentService.html(document)
    for expected in ("Raport fotograficzny", "Liczba zdjęć: 14", "Zdjęcia ogólne obiektu", "Salon", "Ściana A", "Ściana", "Okno", "Praca:",
                     "Zabezpieczenie podłóg", "poza aktualnym planem prac", "Badanie podłoża — Ściana A", "(zakończone)", "— Sufit",
                     "(szkic)", "Ustalenie:", "12,50 mm", "nieaktualne", "Zdjęcie 1", "Przed", "Po", "W trakcie",
                     "Oznaczenia: 1 – rysa przy oknie", "Mieszkanie Mokotów", "08.10.2026"):
        assert expected in html, expected
    assert "&lt;b&gt;salonu&lt;/b&gt;" in html and "<b>salonu</b>" not in html
    assert not re.search(r"checklist\.(question|option)\.|pricebook\.", html)
    assert not re.search(r"\b(photo_report|photo_category|estimate|doc)\.[a-z_]+", html)
    assert set(re.findall(r'src="assets/([^"]+)"', html)) == set(asset_files(document, steps, images))


def test_the_marker_and_contour_are_drawn_where_the_geometry_says():
    document, *_ = build()
    html = PhotoReportDocumentService.html(document)
    assert 'viewBox="0 0 1000 750"' in html
    assert '<circle cx="250.0" cy="375.0" r="32.0"' in html and 'points="100.0,75.0 200.0,225.0 400.0,300.0"' in html


def test_a_partial_report_says_so():
    report, names = make_report()
    kuchnia = report.rooms[1]
    steps = plan_photo_report(report, names, room_ids=frozenset({kuchnia.room_id}), include_project_photos=False)
    document = build_photo_report_document(steps, images_for(photos_of(steps)), PROJECT, CLIENT, EXECUTOR, issued_on=TODAY, scope_rooms=("Kuchnia",))
    assert "Raport częściowy — pomieszczenia: Kuchnia" in PhotoReportDocumentService.html(document)
    assert "Raport częściowy" not in PhotoReportDocumentService.html(build()[0])


def test_there_is_no_vat_and_no_signature_block():
    html = PhotoReportDocumentService.html(build()[0]).lower()
    assert "vat" not in html and "podpis" not in html


def test_the_executor_and_client_blocks_are_printed():
    document, *_ = build()
    assert document.layout.executor.name == "Jan Kowalski Wykończenia" and document.layout.client == Party(name="Anna Nowak")


# --- Polish texts of the checklist -----------------------------------------------------------------------------------------------------


def test_every_built_in_question_and_option_has_a_polish_text_and_nothing_else_is_there():
    keys = set()
    for template in build_baseline_templates():
        for section in template.sections:
            for question in section.questions:
                keys.add(question.text_key)
                keys |= {option.label_key for option in question.options}
    assert keys and set(checklist_names()) == keys


def test_the_checklist_texts_are_the_ones_the_app_shows():
    frontend = json.loads(FRONTEND_PL.read_text(encoding="utf-8"))
    for key, text in checklist_names().items():
        node = frontend
        for part in key.split("."):
            node = node[part]
        assert text == node, key
    assert "checklist.question" in CHECKLIST_FILE.read_text(encoding="utf-8")


def test_a_checklist_key_becomes_polish_an_owner_text_is_kept_and_an_unknown_key_is_an_error():
    assert localize_checklist_text("checklist.question.cracks_present") == checklist_names()["checklist.question.cracks_present"]
    assert localize_checklist_text("Czy są rysy?") == "Czy są rysy?"
    assert reason_of(localize_checklist_text, "checklist.question.no_such").reason == "CATALOG_NAME_UNKNOWN"


# --- from the database and the store ---------------------------------------------------------------------------------------------------------


class World:
    pass


async def seed(db, telegram_id=9501, *, with_profile=True, extra_photos=0) -> World:
    w = World()
    w.storage = InMemoryMediaStorage()
    w.owner = User(telegram_user_id=telegram_id, username=f"u{telegram_id}")
    db.add(w.owner)
    await db.flush()
    client = Client(owner_user_id=w.owner.id, client_type=ClientType.PRIVATE_PERSON, first_name="Anna", last_name="Nowak")
    db.add(client)
    await db.flush()
    w.project = Project(owner_id=w.owner.id, client_id=client.id, name="Mokotów", address="ul. Dobra 1", city="Warszawa", postal_code="00-001")
    db.add(w.project)
    await db.flush()
    w.salon = Room(project_id=w.project.id, name="Salon", created_at=T0)
    w.kuchnia = Room(project_id=w.project.id, name="Kuchnia", created_at=T0 + timedelta(hours=1))
    db.add_all([w.salon, w.kuchnia])
    await db.flush()
    w.wall = Surface(room_id=w.salon.id, name="Ściana A", surface_type=SurfaceType.WALL)
    db.add(w.wall)
    template = ChecklistTemplate(code=f"TPL_{uuid.uuid4().hex[:8]}", version=1, substrate=Substrate.CONCRETE, title_key="t")
    db.add(template)
    await db.flush()
    w.question = ChecklistQuestion(template_id=template.id, position=1, key="q1", text_key="checklist.question.cracks_present",
                                   answer_type=AnswerType.BOOLEAN)
    db.add(w.question)
    await db.flush()
    w.inspection = Inspection(room_id=w.salon.id, surface_id=w.wall.id, template_id=template.id, substrate=Substrate.CONCRETE,
                              status=InspectionStatus.COMPLETED, created_at=T0)
    db.add(w.inspection)
    await db.flush()
    w.finding = InspectionFinding(inspection_id=w.inspection.id, question_id=w.question.id, finding_key="CRACKS", lineage_id=uuid.uuid4(),
                                  label_key="checklist.question.cracks_present", value_snapshot={"bool": True}, is_active=True, position=1)
    db.add(w.finding)
    await db.commit()
    w.assets = []

    async def attach(context, minute, **targets):
        asset = raw_asset(w.owner, w.project, status=PhotoAssetStatus.READY, uploaded_at=T0 + timedelta(minutes=minute),
                          width=1600, height=1200)
        db.add(asset)
        await db.flush()
        db.add(PhotoAttachment(asset_id=asset.id, project_id=w.project.id, context=context, category=PhotoCategory.GENERAL,
                               include_in_report=targets.pop("include", True), position=0, **targets))
        await db.commit()
        w.storage._objects[asset.storage_key_display] = type("O", (), {"data": jpeg(), "content_type": "image/jpeg"})()
        w.assets.append(asset)
        return asset

    w.attach = attach
    await attach(C.PROJECT, 0)
    await attach(C.ROOM, 1, room_id=w.salon.id)
    await attach(C.INSPECTION, 2, inspection_id=w.inspection.id, question_id=w.question.id)
    await attach(C.FINDING, 3, finding_id=w.finding.id)
    await attach(C.ROOM, 4, room_id=w.kuchnia.id)
    for n in range(extra_photos):
        await attach(C.ROOM, 10 + n, room_id=w.kuchnia.id)
    if with_profile:
        await ExecutorProfileService(db).save(w.owner.id, ExecutorProfileWrite(name="Jan Kowalski Wykończenia", nip="7740001454", city="Kraków"))
    w.service = lambda **kw: PhotoReportDocumentService(db, w.storage, storage_name="r2-primary", max_photos=kw.pop("max_photos", 60))
    return w


async def test_the_service_builds_the_report_from_the_database_and_the_store(db_session):
    w = await seed(db_session)
    document, assets = await w.service().build(w.owner.id, w.project.id, issued_on=TODAY)
    assert [b.kind for b in document.blocks] == ["project", "room", "inspection", "question", "finding", "room"]
    assert [b.title for b in document.blocks if b.kind in ("room", "inspection", "question", "finding")] == [
        "Salon", "Ściana A", checklist_names()["checklist.question.cracks_present"], checklist_names()["checklist.question.cracks_present"], "Kuchnia"]
    assert document.photo_count == len(w.assets) == 5 and len(assets) == 5
    for data in assets.values():
        assert max(Image.open(io.BytesIO(data)).size) <= PRINT_MAX_EDGE
    assert document.layout.client.name == "Anna Nowak" and document.layout.executor.tax_id == "774-000-14-54"


async def test_a_photo_not_marked_for_the_report_is_left_out(db_session):
    w = await seed(db_session, telegram_id=9502)
    await w.attach(C.ROOM, 30, room_id=w.salon.id, include=False)
    document, _ = await w.service().build(w.owner.id, w.project.id, issued_on=TODAY)
    assert document.photo_count == 5


async def test_another_owner_cannot_print_the_report_and_sees_nothing_of_it(db_session):
    w = await seed(db_session, telegram_id=9503)
    stranger = await seed(db_session, telegram_id=9504)
    with pytest.raises(ProjectNotFoundError):
        await w.service().build(stranger.owner.id, w.project.id, issued_on=TODAY)
    document, assets = await stranger.service().build(stranger.owner.id, stranger.project.id, issued_on=TODAY)
    mine = {a.storage_key_display for a in w.assets}
    assert document.photo_count == 5 and not (mine & {a.storage_key_display for a in stranger.assets}) and len(assets) == 5


async def test_the_executor_profile_is_required(db_session):
    w = await seed(db_session, telegram_id=9505, with_profile=False)
    with pytest.raises(DocumentDataError) as caught:
        await w.service().build(w.owner.id, w.project.id, issued_on=TODAY)
    assert caught.value.reason == "EXECUTOR_PROFILE_REQUIRED"
    assert (await db_session.execute(select(ExecutorProfile))).first() is None


async def test_a_missing_or_broken_object_stops_the_report(db_session):
    w = await seed(db_session, telegram_id=9506)
    del w.storage._objects[w.assets[1].storage_key_display]
    with pytest.raises(DocumentDataError) as missing:
        await w.service().build(w.owner.id, w.project.id, issued_on=TODAY)
    assert missing.value.reason == "PHOTO_UNAVAILABLE"
    w2 = await seed(db_session, telegram_id=9507)
    w2.storage._objects[w2.assets[2].storage_key_display].data = b"not a picture"
    with pytest.raises(DocumentDataError) as broken:
        await w2.service().build(w2.owner.id, w2.project.id, issued_on=TODAY)
    assert broken.value.reason == "PHOTO_UNREADABLE"


async def test_a_photo_in_another_store_is_refused(db_session):
    w = await seed(db_session, telegram_id=9508)
    service = PhotoReportDocumentService(db_session, w.storage, storage_name="other-store", max_photos=60)
    with pytest.raises(DocumentDataError) as caught:
        await service.build(w.owner.id, w.project.id, issued_on=TODAY)
    assert caught.value.reason == "PHOTO_UNAVAILABLE"


class CountingStorage(InMemoryMediaStorage):
    def __init__(self, inner: InMemoryMediaStorage) -> None:
        super().__init__()
        self._objects = inner._objects
        self.calls = 0
        self.active = 0
        self.peak = 0

    async def download_to(self, key, path):
        import asyncio

        self.calls += 1
        self.active += 1
        self.peak = max(self.peak, self.active)
        await asyncio.sleep(0.01)
        try:
            await super().download_to(key, path)
        finally:
            self.active -= 1


async def test_the_limit_is_checked_before_any_photo_is_read(db_session):
    w = await seed(db_session, telegram_id=9509)
    counting = CountingStorage(w.storage)
    service = PhotoReportDocumentService(db_session, counting, storage_name="r2-primary", max_photos=4)
    with pytest.raises(DocumentDataError) as caught:
        await service.build(w.owner.id, w.project.id, issued_on=TODAY)
    assert caught.value.reason == "PHOTO_LIMIT_EXCEEDED" and counting.calls == 0
    assert caught.value.details["count"] == 5 and caught.value.details["limit"] == 4
    assert {r["name"]: r["count"] for r in caught.value.details["rooms"]} == {"Salon": 3, "Kuchnia": 1}


async def test_a_part_by_room_is_within_the_limit_and_reads_only_its_photos(db_session):
    w = await seed(db_session, telegram_id=9510)
    counting = CountingStorage(w.storage)
    service = PhotoReportDocumentService(db_session, counting, storage_name="r2-primary", max_photos=4)
    document, assets = await service.build(w.owner.id, w.project.id, issued_on=TODAY, room_ids=frozenset({w.salon.id}))
    assert next(b.kind for b in document.blocks) == "room" and document.scope_rooms == ("Salon",)
    assert document.photo_count == 3 and counting.calls == 3 and len(assets) == 3
    assert "Raport częściowy — pomieszczenia: Salon" in PhotoReportDocumentService.html(document)


async def test_downloads_run_a_few_at_a_time_and_the_temporary_files_are_removed(db_session):
    import tempfile

    w = await seed(db_session, telegram_id=9511, extra_photos=12)
    counting = CountingStorage(w.storage)
    service = PhotoReportDocumentService(db_session, counting, storage_name="r2-primary", max_photos=60)
    before = set(Path(tempfile.gettempdir()).glob("photo-report-*"))
    document, _ = await service.build(w.owner.id, w.project.id, issued_on=TODAY)
    assert document.photo_count == 17 and counting.calls == 17
    assert 1 < counting.peak <= 4
    assert set(Path(tempfile.gettempdir()).glob("photo-report-*")) == before


async def test_the_temporary_directory_is_removed_when_a_photo_fails(db_session):
    import tempfile

    w = await seed(db_session, telegram_id=9512)
    del w.storage._objects[w.assets[0].storage_key_display]
    before = set(Path(tempfile.gettempdir()).glob("photo-report-*"))
    with pytest.raises(DocumentDataError):
        await w.service().build(w.owner.id, w.project.id, issued_on=TODAY)
    assert set(Path(tempfile.gettempdir()).glob("photo-report-*")) == before


# --- the PDF --------------------------------------------------------------------------------------------------------------------------------------


def pdf_text(rendered) -> list[str]:
    return [page.extract_text() for page in PdfReader(io.BytesIO(rendered.pdf)).pages]


async def test_the_pdf_has_the_pictures_the_headings_and_polish_text(db_session):
    w = await seed(db_session, telegram_id=9513)
    rendered = await w.service().render(w.owner.id, w.project.id, DocumentRenderer(), issued_on=TODAY)
    reader = PdfReader(io.BytesIO(rendered.pdf))
    text = "\n".join(page.extract_text() for page in reader.pages)
    for expected in ("Raport fotograficzny", "Salon", "Kuchnia", "Zdjęcie 1", "Zdjęcie 5", "Badanie podłoża", "Liczba zdjęć: 5"):
        assert expected in text, expected
    # WeasyPrint lists the shared pictures on every page, so count them by name: one per photo
    assert len({image.name for page in reader.pages for image in page.images}) == 5


async def test_sixty_photos_make_a_document_well_inside_the_limits():
    report_rooms = []
    for r in range(6):
        report_rooms.append(ReportRoom(uuid.uuid4(), f"Pomieszczenie {r + 1}", tuple(rphoto(C.ROOM, caption="Opis zdjęcia", minute=r * 10 + i) for i in range(10)), (), ()))
    report = PhotoReport(uuid.uuid4(), (), tuple(report_rooms))
    steps = plan_photo_report(report, {})
    check_limit(report, steps, 60)
    shot = prepare_print_image(jpeg(2048, 1536))
    images = {p.asset_id: shot for p in photos_of(steps)}
    document = build_photo_report_document(steps, images, PROJECT, CLIENT, EXECUTOR, issued_on=TODAY)
    rendered = await DocumentRenderer().render(PhotoReportDocumentService.html(document), asset_files(document, steps, images))
    texts = pdf_text(rendered)
    assert 5 <= rendered.pages <= 40 and rendered.byte_size < 15_000_000
    assert all(f"Strona {n} z {rendered.pages}" in page for n, page in enumerate(texts, 1))
    assert "Zdjęcie 60" in "\n".join(texts)
