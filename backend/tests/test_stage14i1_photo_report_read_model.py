"""Stage 14I.1 — the photo report read model: which photos reach a Stage 15 document and in what order.

Rules under test (docs/STAGE_14I_REPORT_READ_MODEL_PLAN_RU.md §2): only `include_in_report` photos (unless asked for all); the
usual visibility (READY asset, active attachment and asset, ownership chain); archived rooms / surfaces / openings /
inspections leave out everything below them; findings by lineage; works current and detached with the execution order of
categories; markers and contours in order; fully deterministic order; empty nodes dropped; read-only; the number of SQL
statements does not depend on the number of photos.
"""

import dataclasses
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import event

from app.domain.exceptions import ProjectNotFoundError
from app.domain.services.photo_report_read_model import (
    PhotoReportReadModel,
    ReportPhoto,
)
from app.domain.services.work_plan_service import SurfaceWorkPlanService
from app.models.area_segment import AreaPlane
from app.models.checklist import (
    AnswerType,
    ChecklistQuestion,
    ChecklistTemplate,
    Substrate,
)
from app.models.inspection import Inspection, InspectionFinding, InspectionStatus
from app.models.opening import Opening, OpeningType
from app.models.photo_annotation import PhotoAnnotation
from app.models.photo_asset import PhotoAssetStatus
from app.models.photo_attachment import (
    PhotoAttachment,
    PhotoAttachmentContext,
    PhotoCategory,
)
from app.models.room import Room
from app.models.surface import Surface, SurfaceType
from app.schemas.work_plan import OrderedPriceItemSelection
from tests.conftest import test_engine
from tests.test_estimates import _make_project, _make_room, _make_user
from tests.test_occurrence_key import _save
from tests.test_planned_work_coefficient_assignments import _make_price_item
from tests.test_stage14b4_photo_asset import raw_asset

C = PhotoAttachmentContext
Cat = PhotoCategory
Sel = OrderedPriceItemSelection
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def ref(value) -> SimpleNamespace:
    return SimpleNamespace(id=value)


async def add(db, *objects):
    db.add_all(objects)
    await db.commit()
    return objects[0] if len(objects) == 1 else objects


async def photo(db, w, context, *, minute=0, position=0, include=True, category=Cat.GENERAL, caption=None,
                status=PhotoAssetStatus.READY, asset_archived=False, att_archived=False, captured=None,
                owner=None, project=None, att_project=None, asset=None, **targets):
    """One asset + one attachment. `targets` are the attachment's target columns."""
    project = project or w.project
    if asset is None:
        asset = raw_asset(owner or w.me, project, status=status, uploaded_at=T0 + timedelta(minutes=minute),
                          archived_at=T0 if asset_archived else None, captured_at=captured)
        db.add(asset)
        await db.flush()
    attachment = PhotoAttachment(
        asset_id=asset.id, project_id=(att_project or project).id, context=context, category=category, caption=caption,
        include_in_report=include, position=position, archived_at=T0 if att_archived else None, **targets,
    )
    db.add(attachment)
    await db.commit()
    return asset, attachment


async def world(db) -> SimpleNamespace:
    me = await _make_user(db, 9101)
    other = await _make_user(db, 9102)
    project = await _make_project(db, me.id)
    project2 = await _make_project(db, me.id, name="Drugi")
    foreign = await _make_project(db, other.id, name="Obcy")
    r1 = await add(db, Room(project_id=project.id, name="Salon", created_at=T0))
    r2 = await add(db, Room(project_id=project.id, name="Kuchnia", created_at=T0 + timedelta(hours=1)))
    r_arch = await add(db, Room(project_id=project.id, name="Stary", is_archived=True, created_at=T0 + timedelta(hours=2)))
    other_room = await _make_room(db, project2.id)
    # surfaces of the salon: positions 2, 1, none (the order is by position, unknown last)
    s_wall_b = await add(db, Surface(room_id=r1.id, name="Ściana B", surface_type=SurfaceType.WALL, position=2))
    s_wall_a = await add(db, Surface(room_id=r1.id, name="Ściana A", surface_type=SurfaceType.WALL, position=1))
    s_ceiling = await add(db, Surface(room_id=r1.id, name="Sufit", surface_type=SurfaceType.CEILING))
    s_arch = await add(db, Surface(room_id=r1.id, name="Zarchiwizowana", surface_type=SurfaceType.WALL, is_archived=True))
    s_kitchen = await add(db, Surface(room_id=r2.id, name="Kuchnia ściana", surface_type=SurfaceType.WALL))
    s_in_arch_room = await add(db, Surface(room_id=r_arch.id, name="W starym", surface_type=SurfaceType.WALL))
    o_window = await add(db, Opening(surface_id=s_wall_b.id, opening_type=OpeningType.WINDOW, width=Decimal("1.2"),
                                     height=Decimal("1.4"), quantity=1, name="Okno", created_at=T0))
    o_arch = await add(db, Opening(surface_id=s_wall_b.id, opening_type=OpeningType.DOOR, width=Decimal("0.9"),
                                   height=Decimal("2.0"), quantity=1, is_archived=True))
    template = await add(db, ChecklistTemplate(code=f"TPL_{uuid.uuid4().hex[:8]}", version=1, substrate=Substrate.CONCRETE,
                                              title_key="t"))
    # the ids run against the wanted order, so an order that falls back to the id is caught
    q_late = await add(db, ChecklistQuestion(id=uuid.UUID(int=1), template_id=template.id, position=2, key="q2",
                                             text_key="q.late", answer_type=AnswerType.BOOLEAN))
    q_early = await add(db, ChecklistQuestion(id=uuid.UUID(int=2**127), template_id=template.id, position=1, key="q1",
                                              text_key="q.early", answer_type=AnswerType.BOOLEAN))

    def inspection(room, surface=None, plane=None, archived=False, minute=0):
        return Inspection(room_id=room.id, surface_id=surface.id if surface else None, plane=plane,
                          template_id=template.id, substrate=Substrate.CONCRETE, status=InspectionStatus.COMPLETED,
                          is_archived=archived, created_at=T0 + timedelta(minutes=minute))

    i_wall = await add(db, inspection(r1, s_wall_b))
    i_ceiling = await add(db, inspection(r1, plane=AreaPlane.CEILING, minute=1))
    i_arch = await add(db, inspection(r1, s_wall_a, archived=True, minute=2))
    i_kitchen = await add(db, inspection(r2))
    l1, l2, l3 = uuid.UUID(int=2**127), uuid.UUID(int=2), uuid.uuid4()  # l1 is first by position but last by id
    f1_old = await add(db, InspectionFinding(inspection_id=i_wall.id, question_id=q_early.id, finding_key="CRACK",
                                             lineage_id=l1, is_active=False, position=1, created_at=T0))
    f1_new = await add(db, InspectionFinding(inspection_id=i_wall.id, question_id=q_early.id, finding_key="CRACK_NEW",
                                             lineage_id=l1, is_active=True, position=1, created_at=T0 + timedelta(minutes=5)))
    f2_gone = await add(db, InspectionFinding(inspection_id=i_wall.id, finding_key="MOLD", lineage_id=l2, is_active=False,
                                              position=2, created_at=T0))
    f3 = await add(db, InspectionFinding(inspection_id=i_ceiling.id, finding_key="DAMP", lineage_id=l3, is_active=True,
                                         position=1))
    f_arch = await add(db, InspectionFinding(inspection_id=i_arch.id, finding_key="X", lineage_id=uuid.uuid4(),
                                             is_active=True, position=1))
    return SimpleNamespace(
        me=me, other=other, project=project, project2=project2, foreign=foreign, other_room=other_room,
        r1=r1, r2=r2, r_arch=r_arch, wall_b=s_wall_b, wall_a=s_wall_a, ceiling=s_ceiling, s_arch=s_arch, kitchen=s_kitchen,
        in_arch_room=s_in_arch_room, window=o_window, o_arch=o_arch, template=template, q_late=q_late, q_early=q_early,
        i_wall=i_wall, i_ceiling=i_ceiling, i_arch=i_arch, i_kitchen=i_kitchen,
        f1_old=f1_old, f1_new=f1_new, f2_gone=f2_gone, f3=f3, f_arch=f_arch, l1=l1, l2=l2, l3=l3,
    )


async def build(db, w, **kw):
    return await PhotoReportReadModel(db).build(w.me.id, w.project.id, **kw)


def att_ids(photos) -> list[uuid.UUID]:
    return [p.attachment_id for p in photos]


# ---------------------------------------------------------------------------
# Shape and selection
# ---------------------------------------------------------------------------


async def test_a_project_without_selected_photos_gives_an_empty_report(db_session):
    w = await world(db_session)
    await photo(db_session, w, C.PROJECT, include=False)
    report = await build(db_session, w)
    assert report.project_id == w.project.id
    assert report.project_photos == () and report.rooms == ()


async def test_every_context_lands_in_its_place_of_the_document(db_session):
    w = await world(db_session)
    db = db_session
    _, project_att = await photo(db, w, C.PROJECT)
    _, room_att = await photo(db, w, C.ROOM, room_id=w.r1.id)
    _, wall_att = await photo(db, w, C.SURFACE, surface_id=w.wall_b.id)
    _, window_att = await photo(db, w, C.OPENING, opening_id=w.window.id)
    _, insp_att = await photo(db, w, C.INSPECTION, inspection_id=w.i_wall.id)
    _, quest_att = await photo(db, w, C.INSPECTION, inspection_id=w.i_wall.id, question_id=w.q_early.id)
    _, finding_att = await photo(db, w, C.FINDING, finding_id=w.f1_new.id)
    _, ceiling_insp_att = await photo(db, w, C.INSPECTION, inspection_id=w.i_ceiling.id)
    _, kitchen_att = await photo(db, w, C.SURFACE, surface_id=w.kitchen.id)

    report = await build(db, w)
    assert att_ids(report.project_photos) == [project_att.id]
    assert [r.room_id for r in report.rooms] == [w.r1.id, w.r2.id]
    salon, kitchen = report.rooms
    assert salon.name == "Salon" and att_ids(salon.photos) == [room_att.id]
    assert [s.surface_id for s in salon.surfaces] == [w.wall_b.id]
    wall = salon.surfaces[0]
    assert (wall.name, wall.surface_type) == ("Ściana B", "WALL") and att_ids(wall.photos) == [wall_att.id]
    assert [(o.opening_id, o.name) for o in wall.openings] == [(w.window.id, "Okno")]
    assert att_ids(wall.openings[0].photos) == [window_att.id]
    assert [i.inspection_id for i in salon.inspections] == [w.i_wall.id, w.i_ceiling.id]
    wall_insp, ceiling_insp = salon.inspections
    assert (wall_insp.surface_id, wall_insp.plane, wall_insp.status) == (w.wall_b.id, None, "COMPLETED")
    assert att_ids(wall_insp.photos) == [insp_att.id]
    assert [(q.question_id, q.text_key) for q in wall_insp.questions] == [(w.q_early.id, "q.early")]
    assert att_ids(wall_insp.questions[0].photos) == [quest_att.id]
    assert [(f.lineage_id, f.finding_id) for f in wall_insp.findings] == [(w.l1, w.f1_new.id)]
    assert att_ids(wall_insp.findings[0].photos) == [finding_att.id]
    assert (ceiling_insp.surface_id, ceiling_insp.plane) == (None, "CEILING") and att_ids(ceiling_insp.photos) == [ceiling_insp_att.id]
    assert [s.surface_id for s in kitchen.surfaces] == [w.kitchen.id] and att_ids(kitchen.surfaces[0].photos) == [kitchen_att.id]


async def test_only_selected_photos_by_default_and_everything_visible_on_request(db_session):
    w = await world(db_session)
    _, chosen = await photo(db_session, w, C.PROJECT, minute=0)
    _, hidden = await photo(db_session, w, C.PROJECT, minute=1, include=False)
    assert att_ids((await build(db_session, w)).project_photos) == [chosen.id]
    assert att_ids((await build(db_session, w, only_included=True)).project_photos) == [chosen.id]
    assert att_ids((await build(db_session, w, only_included=False)).project_photos) == [chosen.id, hidden.id]
    shown = (await build(db_session, w, only_included=False)).project_photos
    assert [p.include_in_report for p in shown] == [True, False]


async def test_photo_facts_for_the_document(db_session):
    w = await world(db_session)
    captured = T0 - timedelta(days=1)
    asset, attachment = await photo(db_session, w, C.ROOM, room_id=w.r1.id, minute=5, category=Cat.DEFECT,
                                    caption="Pęknięcie", position=3, captured=captured)
    shot = (await build(db_session, w)).rooms[0].photos[0]
    assert dataclasses.is_dataclass(shot) and isinstance(shot, ReportPhoto)
    assert (shot.attachment_id, shot.asset_id, shot.context, shot.category) == (attachment.id, asset.id, C.ROOM, Cat.DEFECT)
    assert (shot.caption, shot.position, shot.include_in_report, shot.room_id) == ("Pęknięcie", 3, True, w.r1.id)
    assert (shot.width, shot.height, shot.content_type, shot.byte_size, shot.sha256) == (
        asset.width, asset.height, "image/jpeg", asset.byte_size, asset.sha256)
    assert shot.captured_at == captured and shot.captured_at.tzinfo is not None
    assert shot.uploaded_at == T0 + timedelta(minutes=5) and shot.uploaded_at.tzinfo is not None
    # how the bytes are read: keys only, never a URL
    assert (shot.storage_name, shot.storage_key_display, shot.storage_key_original) == (
        asset.storage_name, asset.storage_key_display, asset.storage_key_original)
    assert not any("://" in str(getattr(shot, field.name)) for field in dataclasses.fields(shot))
    assert "thumb" not in " ".join(str(getattr(shot, field.name)) for field in dataclasses.fields(shot))


async def test_the_report_is_immutable(db_session):
    w = await world(db_session)
    await photo(db_session, w, C.PROJECT)
    report = await build(db_session, w)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.project_id = uuid.uuid4()
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.project_photos[0].caption = "x"
    assert isinstance(report.project_photos, tuple) and isinstance(report.rooms, tuple)


# ---------------------------------------------------------------------------
# Visibility and ownership
# ---------------------------------------------------------------------------


async def test_only_visible_photos_reach_the_report(db_session):
    w = await world(db_session)
    db = db_session
    _, shown = await photo(db, w, C.PROJECT, minute=0)
    await photo(db, w, C.PROJECT, minute=1, status=PhotoAssetStatus.PENDING)
    await photo(db, w, C.PROJECT, minute=2, status=PhotoAssetStatus.FAILED)
    await photo(db, w, C.PROJECT, minute=3, att_archived=True)
    await photo(db, w, C.PROJECT, minute=4, asset_archived=True)
    # another owner's asset inside this project, and an attachment of this project on the other project's asset
    await photo(db, w, C.PROJECT, minute=5, owner=w.other)
    await photo(db, w, C.PROJECT, minute=8, att_project=w.project2)  # the asset is ours, the attachment is the other project's
    other_asset = raw_asset(w.me, w.project2, status=PhotoAssetStatus.READY, uploaded_at=T0 + timedelta(minutes=6))
    db.add(other_asset)
    await db.flush()
    await photo(db, w, C.PROJECT, minute=7, asset=other_asset)
    assert att_ids((await build(db, w)).project_photos) == [shown.id]


async def test_another_owner_or_an_unknown_project_is_not_found_and_leaks_nothing(db_session):
    w = await world(db_session)
    await photo(db_session, w, C.PROJECT)
    service = PhotoReportReadModel(db_session)
    with pytest.raises(ProjectNotFoundError):
        await service.build(w.other.id, w.project.id)
    with pytest.raises(ProjectNotFoundError):
        await service.build(w.me.id, w.foreign.id)
    with pytest.raises(ProjectNotFoundError):
        await service.build(w.me.id, uuid.uuid4())


async def test_the_other_project_of_the_same_owner_is_not_mixed_in(db_session):
    w = await world(db_session)
    await photo(db_session, w, C.PROJECT, project=w.project2, att_project=w.project2)
    await photo(db_session, w, C.ROOM, project=w.project2, att_project=w.project2, room_id=w.other_room.id)
    report = await build(db_session, w)
    assert report.project_photos == () and report.rooms == ()


# ---------------------------------------------------------------------------
# Archived targets
# ---------------------------------------------------------------------------


async def test_archived_targets_take_their_photos_and_descendants_out(db_session):
    w = await world(db_session)
    db = db_session
    _, kept_wall = await photo(db, w, C.SURFACE, surface_id=w.wall_a.id)
    await photo(db, w, C.ROOM, room_id=w.r_arch.id)  # archived room
    await photo(db, w, C.SURFACE, surface_id=w.in_arch_room.id)  # a live surface in an archived room
    await photo(db, w, C.SURFACE, surface_id=w.s_arch.id)  # archived surface
    await photo(db, w, C.OPENING, opening_id=w.o_arch.id)  # archived opening
    await photo(db, w, C.INSPECTION, inspection_id=w.i_arch.id)  # archived inspection
    await photo(db, w, C.INSPECTION, inspection_id=w.i_arch.id, question_id=w.q_early.id)
    await photo(db, w, C.FINDING, finding_id=w.f_arch.id)  # finding of the archived inspection
    report = await build(db, w)
    assert [r.room_id for r in report.rooms] == [w.r1.id]
    assert [s.surface_id for s in report.rooms[0].surfaces] == [w.wall_a.id]
    assert att_ids(report.rooms[0].surfaces[0].photos) == [kept_wall.id]
    assert report.rooms[0].inspections == ()


async def test_an_inspection_of_an_archived_surface_and_the_photos_below_an_archived_surface_are_out(db_session):
    w = await world(db_session)
    db = db_session
    live_inspection = await add(db, Inspection(room_id=w.r1.id, surface_id=w.s_arch.id, template_id=w.template.id,
                                               substrate=Substrate.CONCRETE, status=InspectionStatus.COMPLETED))
    await photo(db, w, C.INSPECTION, inspection_id=live_inspection.id)
    opening_on_archived = await add(db, Opening(surface_id=w.s_arch.id, opening_type=OpeningType.WINDOW, width=Decimal(1),
                                                height=Decimal(1), quantity=1))
    await photo(db, w, C.OPENING, opening_id=opening_on_archived.id)
    assert (await build(db, w)).rooms == ()


# ---------------------------------------------------------------------------
# Findings, questions, inspections
# ---------------------------------------------------------------------------


async def test_a_finding_lineage_gathers_photos_of_all_its_rows_under_the_active_row(db_session):
    w = await world(db_session)
    db = db_session
    # a later INACTIVE row of the same lineage must not take the header from the active one
    await add(db, InspectionFinding(inspection_id=w.i_wall.id, finding_key="CRACK_LATER", lineage_id=w.l1, is_active=False,
                                    position=1, created_at=T0 + timedelta(hours=1)))
    _, old_att = await photo(db, w, C.FINDING, finding_id=w.f1_old.id, minute=2)
    _, new_att = await photo(db, w, C.FINDING, finding_id=w.f1_new.id, minute=1)
    findings = (await build(db, w)).rooms[0].inspections[0].findings
    assert len(findings) == 1
    finding = findings[0]
    assert (finding.lineage_id, finding.finding_id, finding.finding_key, finding.is_active) == (w.l1, w.f1_new.id, "CRACK_NEW", True)
    assert att_ids(finding.photos) == [new_att.id, old_att.id]  # by upload time, rows do not matter


async def test_a_lineage_without_an_active_row_is_headed_by_its_last_row(db_session):
    w = await world(db_session)
    db = db_session
    await add(db, InspectionFinding(inspection_id=w.i_wall.id, finding_key="MOLD_LATER", lineage_id=w.l2, is_active=False,
                                    position=2, created_at=T0 + timedelta(minutes=9)))
    await photo(db, w, C.FINDING, finding_id=w.f2_gone.id)
    finding = (await build(db, w)).rooms[0].inspections[0].findings[0]
    assert (finding.lineage_id, finding.finding_key, finding.is_active) == (w.l2, "MOLD_LATER", False)


async def test_findings_of_an_inspection_follow_the_finding_order_not_the_upload_order(db_session):
    w = await world(db_session)
    db = db_session
    _, second = await photo(db, w, C.FINDING, finding_id=w.f2_gone.id, minute=0)  # position 2, uploaded first
    _, first = await photo(db, w, C.FINDING, finding_id=w.f1_new.id, minute=5)  # position 1, uploaded later
    findings = (await build(db, w)).rooms[0].inspections[0].findings
    assert [f.lineage_id for f in findings] == [w.l1, w.l2]
    assert att_ids(findings[0].photos) == [first.id] and att_ids(findings[1].photos) == [second.id]


async def test_question_photos_follow_the_question_order_and_stay_apart_from_the_inspection_ones(db_session):
    w = await world(db_session)
    db = db_session
    _, late = await photo(db, w, C.INSPECTION, inspection_id=w.i_wall.id, question_id=w.q_late.id, minute=0)
    _, early = await photo(db, w, C.INSPECTION, inspection_id=w.i_wall.id, question_id=w.q_early.id, minute=1)
    _, general = await photo(db, w, C.INSPECTION, inspection_id=w.i_wall.id, minute=2)
    inspection = (await build(db, w)).rooms[0].inspections[0]
    assert [(q.text_key, q.position) for q in inspection.questions] == [("q.early", 1), ("q.late", 2)]
    assert [att_ids(q.photos) for q in inspection.questions] == [[early.id], [late.id]]
    assert att_ids(inspection.photos) == [general.id]


async def test_a_room_level_inspection_belongs_to_its_room(db_session):
    w = await world(db_session)
    _, att = await photo(db_session, w, C.INSPECTION, inspection_id=w.i_kitchen.id)
    kitchen = (await build(db_session, w)).rooms[0]
    assert kitchen.room_id == w.r2.id and kitchen.surfaces == ()
    assert (kitchen.inspections[0].surface_id, kitchen.inspections[0].plane) == (None, None)
    assert att_ids(kitchen.inspections[0].photos) == [att.id]


# ---------------------------------------------------------------------------
# Execution photos
# ---------------------------------------------------------------------------


async def work_world(db, w):
    service = SurfaceWorkPlanService(db)
    item_a = await _make_price_item(db, w.me.id, code="REPORT_A")
    item_b = await _make_price_item(db, w.me.id, code="REPORT_B")
    item_b.display_name = "Gruntowanie"
    item_b.name_key = "price.b"
    await db.commit()
    plan = await _save(service, ref(w.me.id), ref(w.project.id), ref(w.r1.id), ref(w.wall_a.id),
                       [Sel(price_item_id=item_a.id), Sel(price_item_id=item_b.id)])
    keys = [x.occurrence_key for x in plan.planned_works]
    return SimpleNamespace(service=service, a=item_a, b=item_b, keys=keys, plan=plan)


async def work_photo(db, w, key, item, **kw):
    return await photo(db, w, C.WORK, surface_id=w.wall_a.id, occurrence_key=key, price_item_id=item.id, **kw)


async def test_works_are_current_or_detached_with_their_operation_and_execution_order(db_session):
    w = await world(db_session)
    db = db_session
    k = await work_world(db, w)
    key_a, key_b = k.keys
    item_a_id, item_b_id = k.a.id, k.b.id
    _, after = await work_photo(db, w, key_b, k.b, category=Cat.AFTER, minute=0)
    _, before = await work_photo(db, w, key_b, k.b, category=Cat.BEFORE, minute=9)
    _, hidden = await work_photo(db, w, key_b, k.b, category=Cat.HIDDEN_WORK, minute=5)
    _, prep = await work_photo(db, w, key_b, k.b, category=Cat.PREPARATION, minute=7)
    _, progress = await work_photo(db, w, key_b, k.b, category=Cat.IN_PROGRESS, minute=3)
    _, a_photo = await work_photo(db, w, key_a, k.a)
    # replace the plan: the first work goes away, its evidence stays as a detached work
    await _save(k.service, ref(w.me.id), ref(w.project.id), ref(w.r1.id), ref(w.wall_a.id), [Sel(price_item_id=item_b_id)])
    current = {x.occurrence_key for x in await _plan_keys(db, w)}
    assert key_a not in current  # the first work is no longer in the plan
    surface = (await build(db, w)).rooms[0].surfaces[0]
    assert surface.surface_id == w.wall_a.id and surface.photos == ()
    works = {x.occurrence_key: x for x in surface.works}
    assert set(works) == {key_a, key_b}
    detached = works[key_a]
    assert (detached.current, detached.price_item_id, detached.price_item_code) == (False, item_a_id, "REPORT_A")
    assert att_ids(detached.photos) == [a_photo.id]
    kept = works[key_b]
    assert (kept.price_item_id, kept.price_item_code, kept.price_item_name_key, kept.price_item_display_name) == (
        item_b_id, "REPORT_B", "price.b", "Gruntowanie")
    assert kept.current is (key_b in current)
    assert att_ids(kept.photos) == [before.id, prep.id, progress.id, hidden.id, after.id]


async def _plan_keys(db, w):
    from sqlalchemy import select

    from app.models.work_plan import SurfacePlannedWork, SurfaceWorkPlan

    rows = await db.execute(
        select(SurfacePlannedWork).join(SurfaceWorkPlan, SurfacePlannedWork.work_plan_id == SurfaceWorkPlan.id)
        .where(SurfaceWorkPlan.surface_id == w.wall_a.id)
    )
    return list(rows.scalars().all())


async def test_current_works_come_in_plan_order_before_detached_ones(db_session):
    w = await world(db_session)
    db = db_session
    k = await work_world(db, w)
    key_a, key_b = k.keys
    await work_photo(db, w, key_b, k.b, minute=0)  # uploaded first, but second in the plan
    await work_photo(db, w, key_a, k.a, minute=9)
    works = (await build(db, w)).rooms[0].surfaces[0].works
    assert [x.occurrence_key for x in works] == [key_a, key_b] and all(x.current for x in works)
    ghost_key = uuid.uuid4()
    await work_photo(db, w, ghost_key, k.a, minute=1)
    works = (await build(db, w)).rooms[0].surfaces[0].works
    assert [x.occurrence_key for x in works] == [key_a, key_b, ghost_key]
    assert [x.current for x in works] == [True, True, False]


# ---------------------------------------------------------------------------
# Markers and contours
# ---------------------------------------------------------------------------


async def test_markers_and_contours_travel_with_their_attachment_in_display_order(db_session):
    w = await world(db_session)
    db = db_session
    _, att = await photo(db, w, C.ROOM, room_id=w.r1.id, minute=0)
    _, second_att = await photo(db, w, C.ROOM, room_id=w.r1.id, minute=1)
    marker_b = await add(db, PhotoAnnotation(attachment_id=att.id, x=0.8, y=0.6, label="B", position=1))
    marker_a = await add(db, PhotoAnnotation(attachment_id=att.id, x=0.25, y=0.5, label=None, position=0,
                                            outline=[[0.1, 0.1], [0.4, 0.1], [0.4, 0.4]]))
    other = await add(db, PhotoAnnotation(attachment_id=second_att.id, x=0.5, y=0.5, label="Inne", position=0))
    photos = (await build(db, w)).rooms[0].photos
    first, second = photos
    assert first.attachment_id == att.id
    assert [(m.id, m.x, m.y, m.label, m.position) for m in first.markers] == [
        (marker_a.id, 0.25, 0.5, None, 0), (marker_b.id, 0.8, 0.6, "B", 1)]
    assert first.markers[0].outline == ((0.1, 0.1), (0.4, 0.1), (0.4, 0.4))
    assert first.markers[1].outline is None
    assert [m.id for m in second.markers] == [other.id]


async def test_the_same_image_in_two_places_keeps_two_independent_marker_sets(db_session):
    w = await world(db_session)
    db = db_session
    asset, _ = await photo(db, w, C.ROOM, room_id=w.r1.id)
    _, wall_att = await photo(db, w, C.SURFACE, surface_id=w.wall_a.id, asset=asset)
    await add(db, PhotoAnnotation(attachment_id=wall_att.id, x=0.1, y=0.2, label="tylko ściana", position=0))
    salon = (await build(db, w)).rooms[0]
    assert salon.photos[0].markers == ()
    assert [m.label for m in salon.surfaces[0].photos[0].markers] == ["tylko ściana"]


# ---------------------------------------------------------------------------
# Order, empty nodes, read-only, statements
# ---------------------------------------------------------------------------


async def test_photo_order_is_position_then_capture_then_upload_then_id(db_session):
    w = await world(db_session)
    db = db_session
    _, pos1_late = await photo(db, w, C.PROJECT, position=1, minute=0)
    _, pos0_no_capture = await photo(db, w, C.PROJECT, position=0, minute=9)
    _, pos0_captured_late = await photo(db, w, C.PROJECT, position=0, minute=1, captured=T0 + timedelta(hours=2))
    _, pos0_captured_early = await photo(db, w, C.PROJECT, position=0, minute=2, captured=T0 + timedelta(hours=1))
    order = att_ids((await build(db, w)).project_photos)
    assert order == [pos0_captured_early.id, pos0_captured_late.id, pos0_no_capture.id, pos1_late.id]


async def test_identical_sort_keys_fall_back_to_the_attachment_id(db_session):
    w = await world(db_session)
    db = db_session
    ids = []
    for _ in range(5):
        _, att = await photo(db, w, C.PROJECT, minute=0, position=0)
        ids.append(att.id)
    assert att_ids((await build(db, w)).project_photos) == sorted(ids)


async def test_rooms_surfaces_and_openings_have_a_fixed_order_and_a_repeated_call_gives_the_same_report(db_session):
    w = await world(db_session)
    db = db_session
    for surface in (w.wall_b, w.wall_a, w.ceiling):
        await photo(db, w, C.SURFACE, surface_id=surface.id)
    await photo(db, w, C.SURFACE, surface_id=w.kitchen.id)
    await photo(db, w, C.ROOM, room_id=w.r2.id)
    first = await build(db, w)
    assert [r.room_id for r in first.rooms] == [w.r1.id, w.r2.id]
    assert [s.surface_id for s in first.rooms[0].surfaces] == [w.wall_a.id, w.wall_b.id, w.ceiling.id]  # 1, 2, none
    assert first == await build(db, w)


async def test_a_node_without_selected_photos_and_without_selected_descendants_is_dropped(db_session):
    w = await world(db_session)
    db = db_session
    await photo(db, w, C.ROOM, room_id=w.r1.id, include=False)
    await photo(db, w, C.SURFACE, surface_id=w.wall_a.id, include=False)
    await photo(db, w, C.INSPECTION, inspection_id=w.i_wall.id, include=False)
    _, kept = await photo(db, w, C.OPENING, opening_id=w.window.id)
    report = await build(db, w)
    assert [r.room_id for r in report.rooms] == [w.r1.id]
    salon = report.rooms[0]
    assert salon.photos == () and salon.inspections == ()
    assert [s.surface_id for s in salon.surfaces] == [w.wall_b.id] and salon.surfaces[0].photos == ()
    assert att_ids(salon.surfaces[0].openings[0].photos) == [kept.id]


def capture_statements():
    statements: list[str] = []

    def on_execute(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(test_engine.sync_engine, "before_cursor_execute", on_execute)
    return statements, lambda: event.remove(test_engine.sync_engine, "before_cursor_execute", on_execute)


async def test_it_only_reads_and_the_statement_count_does_not_grow_with_the_photos(db_session):
    w = await world(db_session)
    db = db_session
    k = await work_world(db, w)

    async def add_photos(count, base):
        for n in range(count):
            minute = base + n
            await photo(db, w, C.PROJECT, minute=minute)
            await photo(db, w, C.ROOM, room_id=w.r1.id, minute=minute)
            await photo(db, w, C.SURFACE, surface_id=w.wall_b.id, minute=minute)
            await photo(db, w, C.OPENING, opening_id=w.window.id, minute=minute)
            await photo(db, w, C.INSPECTION, inspection_id=w.i_wall.id, minute=minute)
            await photo(db, w, C.INSPECTION, inspection_id=w.i_wall.id, question_id=w.q_early.id, minute=minute)
            _, attachment = await photo(db, w, C.FINDING, finding_id=w.f1_new.id, minute=minute)
            await add(db, PhotoAnnotation(attachment_id=attachment.id, x=0.5, y=0.5, position=0))
            await work_photo(db, w, k.keys[0], k.a, minute=minute)

    async def count_for_current_data():
        statements, stop = capture_statements()
        try:
            report = await build(db, w)
        finally:
            stop()
        assert all(s.lstrip().upper().startswith("SELECT") for s in statements), statements
        return len(statements), report

    await add_photos(1, 0)
    few, report_few = await count_for_current_data()
    await add_photos(9, 100)
    many, report_many = await count_for_current_data()
    assert few == many and few <= 14
    assert len(report_many.project_photos) == 10 and len(report_few.project_photos) == 1
    assert len(report_many.rooms[0].inspections[0].findings[0].photos) == 10
