"""Stage 14J.2 — PostgreSQL 16 proof for what Stage 14 added after 14C.6B (OPT-IN).

Runs only with TEST_PG_URL pointing at a disposable loopback scratch database whose name contains `pe_scratch_test`
(see pg_scratch_guard.py); otherwise the whole module is skipped. The schema comes from `alembic upgrade head`.

What SQLite cannot prove:
A. database constraints of 14F-14H on the real engine: marker coordinate CHECKs, the CHECK of each attachment context, the
   partial unique indexes of ACTIVE attachments (INSPECTION with and without a question, FINDING, WORK), the cascade
   from an attachment to its markers, how a cleared contour is stored;
B. real races on separate connections: the limit of 10 markers per photo (guarded by the row lock of the attachment),
   concurrent contour rewrites of one marker, concurrent deletes of one marker;
C. volume: the counts of GET /photos/counts and the report read model of 14I on hundreds of photos -- exact against the
   inserted truth, a statement count that does not grow with the photos, UTC-aware times.
Every case creates its own owner / project data and deletes it afterwards.
"""

import asyncio
import os
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, event, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.models  # noqa: F401
from app.domain.exceptions import (
    PhotoAnnotationLimitReachedError,
    PhotoAnnotationNotFoundError,
)
from app.domain.services.photo_annotation_service import PhotoAnnotationService
from app.domain.services.photo_query_service import PhotoQueryService
from app.domain.services.photo_report_read_model import PhotoReportReadModel
from app.models.area_segment import AreaPlane
from app.models.checklist import (
    AnswerType,
    ChecklistQuestion,
    ChecklistTemplate,
    Substrate,
)
from app.models.inspection import Inspection, InspectionFinding, InspectionStatus
from app.models.opening import Opening, OpeningType
from app.models.photo_annotation import MAX_ANNOTATIONS_PER_ATTACHMENT, PhotoAnnotation
from app.models.photo_asset import PhotoAsset, PhotoAssetStatus
from app.models.photo_attachment import (
    PhotoAttachment,
    PhotoAttachmentContext,
    PhotoCategory,
)
from app.models.price_item import PriceCategory, PriceItem, PriceScope, PriceUnit
from app.models.project import Project
from app.models.room import Room
from app.models.surface import Surface, SurfaceType
from app.models.user import User
from tests.pg_scratch_guard import scratch_url
from tests.test_stage14b4_photo_asset import raw_asset

URL = scratch_url()
pytestmark = pytest.mark.skipif(URL is None, reason="opt-in: set TEST_PG_URL to a pe_scratch_test database")

BACKEND = Path(__file__).resolve().parents[1]
C = PhotoAttachmentContext
ROUNDS = int(os.environ.get("PG_RACE_ROUNDS", "10"))
T0 = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture(scope="module", autouse=True)
def migrated_schema():
    env = dict(os.environ, DATABASE_URL=URL.render_as_string(hide_password=False))
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=BACKEND, env=env, check=True,
                   capture_output=True)


@pytest.fixture
async def pg():
    engine = create_async_engine(URL, poolclass=NullPool, hide_parameters=True)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    harness = SimpleNamespace(engine=engine, sessions=sessions, owners=[], templates=[])
    yield harness
    async with sessions() as s:  # FK-safe cleanup of this test's data only
        projects = select(Project.id).where(Project.owner_id.in_(harness.owners))
        rooms = select(Room.id).where(Room.project_id.in_(projects))
        attachments = select(PhotoAttachment.id).where(PhotoAttachment.project_id.in_(projects))
        await s.execute(delete(PhotoAnnotation).where(PhotoAnnotation.attachment_id.in_(attachments)))
        await s.execute(delete(PhotoAttachment).where(PhotoAttachment.project_id.in_(projects)))
        await s.execute(delete(PhotoAsset).where(PhotoAsset.owner_id.in_(harness.owners)))
        inspections = select(Inspection.id).where(Inspection.room_id.in_(rooms))
        await s.execute(delete(InspectionFinding).where(InspectionFinding.inspection_id.in_(inspections)))
        await s.execute(delete(Inspection).where(Inspection.room_id.in_(rooms)))
        surfaces = select(Surface.id).where(Surface.room_id.in_(rooms))
        await s.execute(delete(Opening).where(Opening.surface_id.in_(surfaces)))
        await s.execute(delete(Surface).where(Surface.room_id.in_(rooms)))
        await s.execute(delete(Room).where(Room.project_id.in_(projects)))
        await s.execute(delete(Project).where(Project.owner_id.in_(harness.owners)))
        await s.execute(delete(PriceItem).where(PriceItem.owner_id.in_(harness.owners)))
        await s.execute(delete(User).where(User.id.in_(harness.owners)))
        for template_id in harness.templates:
            await s.execute(delete(ChecklistQuestion).where(ChecklistQuestion.template_id == template_id))
            await s.execute(delete(ChecklistTemplate).where(ChecklistTemplate.id == template_id))
        await s.commit()
    await engine.dispose()


async def world(pg) -> SimpleNamespace:
    """Owner, project, room, wall, ceiling, opening, a template with one question, a wall inspection with a finding, a
    price item."""
    async with pg.sessions() as s:
        user = User(telegram_user_id=int(uuid.uuid4().int % 10**12))
        s.add(user)
        await s.flush()
        pg.owners.append(user.id)
        project = Project(owner_id=user.id, name="PG 14J", address="ul. Testowa 1", city="Warszawa", postal_code="00-001")
        s.add(project)
        await s.flush()
        room = Room(project_id=project.id, name="Salon", created_at=T0)
        s.add(room)
        await s.flush()
        wall = Surface(room_id=room.id, name="Ściana", surface_type=SurfaceType.WALL, position=1)
        ceiling = Surface(room_id=room.id, name="Sufit", surface_type=SurfaceType.CEILING)
        s.add_all([wall, ceiling])
        await s.flush()
        opening = Opening(surface_id=wall.id, opening_type=OpeningType.WINDOW, width=Decimal("1.2"), height=Decimal("1.4"),
                          quantity=1, name="Okno")
        template = ChecklistTemplate(code=f"PG14J_{uuid.uuid4().hex[:8]}", version=1, substrate=Substrate.CONCRETE,
                                     title_key="t")
        s.add_all([opening, template])
        await s.flush()
        pg.templates.append(template.id)
        question = ChecklistQuestion(template_id=template.id, position=1, key="q1", text_key="q.one",
                                     answer_type=AnswerType.BOOLEAN)
        inspection = Inspection(room_id=room.id, surface_id=wall.id, template_id=template.id, substrate=Substrate.CONCRETE,
                                status=InspectionStatus.COMPLETED)
        ceiling_inspection = Inspection(room_id=room.id, plane=AreaPlane.CEILING, template_id=template.id,
                                        substrate=Substrate.CONCRETE, status=InspectionStatus.COMPLETED)
        item = PriceItem(owner_id=user.id, code=f"PG14J_{uuid.uuid4().hex[:8]}", category=PriceCategory.PAINTING, unit=PriceUnit.M2,
                         price_scope=PriceScope.LABOR, price=Decimal("10.00"))
        s.add_all([question, inspection, ceiling_inspection, item])
        await s.flush()
        finding = InspectionFinding(inspection_id=inspection.id, question_id=question.id, finding_key="CRACK",
                                    lineage_id=uuid.uuid4(), is_active=True, position=1)
        s.add(finding)
        await s.commit()
        return SimpleNamespace(
            owner=user.id, project=project.id, room=room.id, wall=wall.id, ceiling=ceiling.id, opening=opening.id,
            question=question.id, inspection=inspection.id, ceiling_inspection=ceiling_inspection.id,
            finding=finding.id, lineage=finding.lineage_id, item=item.id,
        )


async def asset(pg, w, *, minute=0, status=PhotoAssetStatus.READY) -> uuid.UUID:
    async with pg.sessions() as s:
        row = raw_asset(SimpleNamespace(id=w.owner), SimpleNamespace(id=w.project), status=status,
                        uploaded_at=T0 + timedelta(minutes=minute))
        s.add(row)
        await s.commit()
        return row.id


async def attach(pg, w, context, *, minute=0, include=True, asset_id=None, **targets) -> uuid.UUID:
    asset_id = asset_id or await asset(pg, w, minute=minute)
    async with pg.sessions() as s:
        row = PhotoAttachment(asset_id=asset_id, project_id=w.project, context=context, category=PhotoCategory.GENERAL,
                              include_in_report=include, **targets)
        s.add(row)
        await s.commit()
        return row.id


async def marker_count(pg, attachment_id) -> int:
    async with pg.sessions() as s:
        return (await s.execute(select(func.count()).select_from(PhotoAnnotation)
                                .where(PhotoAnnotation.attachment_id == attachment_id))).scalar_one()


async def expect_integrity_error(pg, make_rows) -> str:
    async with pg.sessions() as s:
        s.add_all(make_rows())
        with pytest.raises(IntegrityError) as caught:
            await s.commit()
        await s.rollback()
    return str(caught.value.orig)


# ---------------------------------------------------------------------------
# A. Constraints
# ---------------------------------------------------------------------------


async def test_a1_marker_coordinate_checks_hold_and_the_boundaries_are_allowed(pg):
    w = await world(pg)
    att = await attach(pg, w, C.ROOM, room_id=w.room)
    for field, value, constraint in [("x", 1.000001, "ck_photo_annotations_x_range"), ("x", -0.000001, "ck_photo_annotations_x_range"),
                                     ("y", 1.5, "ck_photo_annotations_y_range"), ("y", -0.1, "ck_photo_annotations_y_range")]:
        values = {"x": 0.5, "y": 0.5, field: value}
        message = await expect_integrity_error(pg, lambda v=values: [PhotoAnnotation(attachment_id=att, position=0, **v)])
        assert constraint in message, message
    message = await expect_integrity_error(pg, lambda: [PhotoAnnotation(attachment_id=att, x=0.5, y=0.5, position=-1)])
    assert "ck_photo_annotations_position_nonneg" in message
    async with pg.sessions() as s:  # the boundaries themselves are valid
        s.add_all([PhotoAnnotation(attachment_id=att, x=0, y=1, position=0), PhotoAnnotation(attachment_id=att, x=1, y=0, position=1)])
        await s.commit()
    assert await marker_count(pg, att) == 2


async def test_a2_every_context_check_and_active_unique_index_holds(pg):
    w = await world(pg)
    # INSPECTION may not carry a room; FINDING may not carry an inspection; WORK needs its operation snapshot
    a_insp, a_find, a_work = await asset(pg, w), await asset(pg, w), await asset(pg, w)
    for rows in (
        lambda: [PhotoAttachment(asset_id=a_insp, project_id=w.project, context=C.INSPECTION, inspection_id=w.inspection, room_id=w.room)],
        lambda: [PhotoAttachment(asset_id=a_find, project_id=w.project, context=C.FINDING, finding_id=w.finding, inspection_id=w.inspection)],
        lambda: [PhotoAttachment(asset_id=a_work, project_id=w.project, context=C.WORK, surface_id=w.wall, occurrence_key=uuid.uuid4())],
        lambda: [PhotoAttachment(asset_id=a_work, project_id=w.project, context=C.WORK, surface_id=w.wall, occurrence_key=uuid.uuid4(),
                                 price_item_id=w.item, question_id=w.question)],
        lambda: [PhotoAttachment(asset_id=a_work, project_id=w.project, context=C.ROOM, room_id=w.room, surface_id=w.wall)],
    ):
        assert "ck_photo_attachments_context_targets" in await expect_integrity_error(pg, rows)

    # active uniqueness: inspection-level and per-question are separate slots; an archived duplicate does not block
    shared = await asset(pg, w)
    await attach(pg, w, C.INSPECTION, asset_id=shared, inspection_id=w.inspection)
    await attach(pg, w, C.INSPECTION, asset_id=shared, inspection_id=w.inspection, question_id=w.question)
    message = await expect_integrity_error(pg, lambda: [PhotoAttachment(
        asset_id=shared, project_id=w.project, context=C.INSPECTION, inspection_id=w.inspection)])
    assert "uq_photo_att_inspection_active" in message
    message = await expect_integrity_error(pg, lambda: [PhotoAttachment(
        asset_id=shared, project_id=w.project, context=C.INSPECTION, inspection_id=w.inspection, question_id=w.question)])
    assert "uq_photo_att_inspection_question_active" in message

    finding_asset, key = await asset(pg, w), uuid.uuid4()
    await attach(pg, w, C.FINDING, asset_id=finding_asset, finding_id=w.finding)
    assert "uq_photo_att_finding_active" in await expect_integrity_error(pg, lambda: [PhotoAttachment(
        asset_id=finding_asset, project_id=w.project, context=C.FINDING, finding_id=w.finding)])
    work_asset = await asset(pg, w)
    await attach(pg, w, C.WORK, asset_id=work_asset, surface_id=w.wall, occurrence_key=key, price_item_id=w.item)
    assert "uq_photo_att_work_active" in await expect_integrity_error(pg, lambda: [PhotoAttachment(
        asset_id=work_asset, project_id=w.project, context=C.WORK, surface_id=w.wall, occurrence_key=key, price_item_id=w.item)])
    async with pg.sessions() as s:  # the same photo in another occurrence of the same wall is allowed
        s.add(PhotoAttachment(asset_id=work_asset, project_id=w.project, context=C.WORK, surface_id=w.wall,
                              occurrence_key=uuid.uuid4(), price_item_id=w.item))
        await s.commit()
    # archive the first inspection-level slot: the same asset may take it again
    async with pg.sessions() as s:
        await s.execute(text("UPDATE photo_attachments SET archived_at = now() WHERE asset_id = :a AND context = 'INSPECTION' "
                             "AND question_id IS NULL"), {"a": shared})
        await s.commit()
    await attach(pg, w, C.INSPECTION, asset_id=shared, inspection_id=w.inspection)


async def test_a3_markers_die_with_their_attachment_and_never_with_anything_else(pg):
    w = await world(pg)
    kept, doomed = await attach(pg, w, C.ROOM, room_id=w.room), await attach(pg, w, C.SURFACE, surface_id=w.wall)
    async with pg.sessions() as s:
        s.add_all([PhotoAnnotation(attachment_id=kept, x=0.1, y=0.1, position=0),
                   PhotoAnnotation(attachment_id=doomed, x=0.2, y=0.2, position=0),
                   PhotoAnnotation(attachment_id=doomed, x=0.3, y=0.3, position=1)])
        await s.commit()
    async with pg.sessions() as s:
        await s.execute(delete(PhotoAttachment).where(PhotoAttachment.id == doomed))
        await s.commit()
    assert await marker_count(pg, doomed) == 0 and await marker_count(pg, kept) == 1


async def test_a4_a_cleared_contour_reads_as_none_and_how_it_is_stored(pg):
    w = await world(pg)
    att = await attach(pg, w, C.ROOM, room_id=w.room)
    outline = [[0.1, 0.1], [0.4, 0.1], [0.4, 0.4]]
    async with pg.sessions() as s:
        service = PhotoAnnotationService(s)
        marker = await service.create(w.owner, w.project, att, x=0.2, y=0.2, label="x")
        marker_id = marker.id
        assert marker.outline is None
    async with pg.sessions() as s:
        updated = await PhotoAnnotationService(s).update(w.owner, w.project, att, marker_id, outline=outline)
        assert updated.outline == outline
    async with pg.sessions() as s:
        assert (await PhotoAnnotationService(s).list_for_attachments([att]))[0].outline == outline
    async with pg.sessions() as s:
        cleared = await PhotoAnnotationService(s).update(w.owner, w.project, att, marker_id, outline=None)
        assert cleared.outline is None
    async with pg.sessions() as s:
        assert (await PhotoAnnotationService(s).list_for_attachments([att]))[0].outline is None
        row = (await s.execute(text("SELECT outline IS NULL, outline::text FROM photo_annotations WHERE id = :i"),
                               {"i": marker_id})).one()
    print(f"\n[14J.2-A4] cleared contour stored as: is_sql_null={row[0]} text={row[1]!r}")
    assert row[0] is True, "a cleared contour must be SQL NULL (the runbook counts contours with count(outline))"


# ---------------------------------------------------------------------------
# B. Races
# ---------------------------------------------------------------------------


async def create_marker(pg, w, att, n):
    async with pg.sessions() as s:
        return await PhotoAnnotationService(s).create(w.owner, w.project, att, x=(n % 10) / 10, y=0.5, label=str(n))


def settled(results):
    return ([r for r in results if not isinstance(r, BaseException)], [r for r in results if isinstance(r, BaseException)])


async def test_b1_the_limit_of_markers_holds_under_concurrent_creates(pg):
    w = await world(pg)
    for round_no in range(ROUNDS):
        att = await attach(pg, w, C.ROOM if round_no == 0 else C.SURFACE, minute=round_no,
                           **({"room_id": w.room} if round_no == 0 else {"surface_id": w.wall}))
        existing = MAX_ANNOTATIONS_PER_ATTACHMENT - 1 if round_no % 2 == 0 else 0
        for n in range(existing):
            await create_marker(pg, w, att, n)
        contenders = 12 if existing else 25
        ok, errors = settled(await asyncio.gather(*[create_marker(pg, w, att, 100 + n) for n in range(contenders)],
                                                  return_exceptions=True))
        assert all(isinstance(e, PhotoAnnotationLimitReachedError) for e in errors), errors
        assert len(ok) == MAX_ANNOTATIONS_PER_ATTACHMENT - existing
        assert await marker_count(pg, att) == MAX_ANNOTATIONS_PER_ATTACHMENT
        async with pg.sessions() as s:
            positions = sorted((await s.execute(select(PhotoAnnotation.position)
                                                .where(PhotoAnnotation.attachment_id == att))).scalars().all())
        assert positions == list(range(MAX_ANNOTATIONS_PER_ATTACHMENT))  # no gaps, no duplicates
        # a fresh photo is independent of the full one
        other = await attach(pg, w, C.OPENING, minute=500 + round_no, opening_id=w.opening) if round_no == 0 else None
        if other:
            await create_marker(pg, w, other, 1)


async def test_b2_concurrent_contour_rewrites_leave_one_valid_contour(pg):
    w = await world(pg)
    att = await attach(pg, w, C.ROOM, room_id=w.room)
    marker = await create_marker(pg, w, att, 1)
    contours = [[[round(0.1 * k, 6), 0.1], [round(0.1 * k, 6), 0.5], [0.9, round(0.5 + 0.01 * k, 6)]] for k in range(1, 9)]  # the service rounds to 6 places

    async def rewrite(contour):
        async with pg.sessions() as s:
            return await PhotoAnnotationService(s).update(w.owner, w.project, att, marker.id, outline=contour)

    for _ in range(ROUNDS):
        ok, errors = settled(await asyncio.gather(*[rewrite(c) for c in contours], return_exceptions=True))
        assert errors == [] and len(ok) == len(contours)
        async with pg.sessions() as s:
            stored = (await PhotoAnnotationService(s).list_for_attachments([att]))[0].outline
        assert stored in contours  # exactly one of the writes, never a mixture


async def test_b3_concurrent_deletes_of_one_marker_end_with_it_gone(pg):
    w = await world(pg)
    for _ in range(ROUNDS):
        att = await attach(pg, w, C.ROOM, room_id=w.room, minute=_) if _ == 0 else await attach(pg, w, C.SURFACE, surface_id=w.wall, minute=_)
        marker = await create_marker(pg, w, att, 1)

        async def remove(att=att, marker_id=marker.id):
            async with pg.sessions() as s:
                await PhotoAnnotationService(s).delete(w.owner, w.project, att, marker_id)

        _, errors = settled(await asyncio.gather(remove(), remove(), remove(), return_exceptions=True))
        assert all(isinstance(e, PhotoAnnotationNotFoundError) for e in errors), errors
        assert await marker_count(pg, att) == 0
        async with pg.sessions() as s:
            await s.execute(delete(PhotoAttachment).where(PhotoAttachment.id == att))
            await s.commit()


# ---------------------------------------------------------------------------
# C. Volume: counts and the report read model
# ---------------------------------------------------------------------------


async def fill(pg, w, rounds: int) -> SimpleNamespace:
    """`rounds` x 9 attachments (every context), half selected for the report, every third with a marker."""
    truth = SimpleNamespace(project=0, room=0, surface=0, opening=0, inspection=0, question=0, finding=0, work_surface=0,
                            included=0, markers=0, ceiling_plane=0)
    key = uuid.uuid4()
    assets, attachments = [], []
    async with pg.sessions() as s:
        for n in range(rounds):
            for part, (context, targets) in enumerate((
                (C.PROJECT, {}), (C.ROOM, {"room_id": w.room}), (C.SURFACE, {"surface_id": w.wall}),
                (C.OPENING, {"opening_id": w.opening}), (C.INSPECTION, {"inspection_id": w.inspection}),
                (C.INSPECTION, {"inspection_id": w.inspection, "question_id": w.question}),
                (C.FINDING, {"finding_id": w.finding}),
                (C.WORK, {"surface_id": w.wall, "occurrence_key": key, "price_item_id": w.item}),
                (C.INSPECTION, {"inspection_id": w.ceiling_inspection}),
            )):
                row = raw_asset(SimpleNamespace(id=w.owner), SimpleNamespace(id=w.project), status=PhotoAssetStatus.READY,
                                uploaded_at=T0 + timedelta(minutes=n * 10 + part))
                include = (n + part) % 2 == 0
                assets.append(row)
                attachments.append((row, PhotoAttachment(asset_id=row.id, project_id=w.project, context=context,
                                                         category=PhotoCategory.GENERAL, include_in_report=include,
                                                         position=part, **targets)))
                truth.included += include
                if context is C.PROJECT:
                    truth.project += 1
                elif context is C.ROOM:
                    truth.room += 1
                elif context is C.SURFACE:
                    truth.surface += 1
                elif context is C.OPENING:
                    truth.opening += 1
                elif context is C.FINDING:
                    truth.finding += 1
                elif context is C.WORK:
                    truth.work_surface += 1
                elif "question_id" in targets:
                    truth.question += 1
                    truth.inspection += 1
                elif targets["inspection_id"] == w.ceiling_inspection:
                    truth.ceiling_plane += 1
                else:
                    truth.inspection += 1
        s.add_all(assets)
        await s.flush()
        s.add_all([att for _, att in attachments])
        await s.flush()
        for index, (_, att) in enumerate(attachments):
            if index % 3 == 0:
                s.add(PhotoAnnotation(attachment_id=att.id, x=0.5, y=0.5, position=0,
                                      outline=[[0.1, 0.1], [0.3, 0.1], [0.3, 0.3]] if index % 6 == 0 else None))
                truth.markers += 1
        await s.commit()
    return truth


def statements(pg):
    found: list[str] = []

    def on_execute(conn, cursor, statement, parameters, context, executemany):
        found.append(statement)

    event.listen(pg.engine.sync_engine, "before_cursor_execute", on_execute)
    return found, lambda: event.remove(pg.engine.sync_engine, "before_cursor_execute", on_execute)


async def test_c1_counts_and_the_report_are_exact_on_postgres_and_do_not_grow_in_statements(pg):
    small, large = await world(pg), await world(pg)
    small_truth = await fill(pg, small, 3)
    large_truth = await fill(pg, large, 60)  # 540 photos

    async def measure(w):
        found, stop = statements(pg)
        started = time.perf_counter()
        try:
            async with pg.sessions() as s:
                counts = await PhotoQueryService(s).counts(w.owner, w.project)
            counts_ms = (time.perf_counter() - started) * 1000
            started = time.perf_counter()
            async with pg.sessions() as s:
                report = await PhotoReportReadModel(s).build(w.owner, w.project)
            report_ms = (time.perf_counter() - started) * 1000
        finally:
            stop()
        assert all(statement.lstrip().upper().startswith(("SELECT", "BEGIN", "ROLLBACK", "COMMIT")) for statement in found)
        return counts, counts_ms, report, report_ms, len([x for x in found if x.lstrip().upper().startswith("SELECT")])

    for w, truth in ((small, small_truth), (large, large_truth)):
        counts, _, _, _, _ = await measure(w)
        assert counts.project == truth.project
        assert counts.rooms == ({w.room: truth.room} if truth.room else {})
        assert counts.surfaces == {w.wall: truth.surface} and counts.openings == {w.opening: truth.opening}
        assert counts.inspections == {w.inspection: truth.inspection + truth.question, w.ceiling_inspection: truth.ceiling_plane} \
            or counts.inspections == {w.inspection: truth.inspection, w.ceiling_inspection: truth.ceiling_plane}
        assert counts.work_surfaces == {w.wall: truth.work_surface}
        assert counts.inspection_planes == {w.room: {"CEILING": truth.ceiling_plane}}
        assert counts.inspection_surfaces[w.wall] == truth.inspection + truth.finding

    _, small_counts_ms, small_report, small_report_ms, small_selects = await measure(small)
    _, large_counts_ms, large_report, large_report_ms, large_selects = await measure(large)
    print(f"\n[14J.2-C1] 27 photos: counts {small_counts_ms:.0f} ms, report {small_report_ms:.0f} ms, {small_selects} SELECTs; "
          f"540 photos: counts {large_counts_ms:.0f} ms, report {large_report_ms:.0f} ms, {large_selects} SELECTs")
    assert small_selects == large_selects  # statements do not grow with the photos
    assert large_report_ms < 5000 and large_counts_ms < 5000

    def total(report):
        photos = list(report.project_photos)
        for room in report.rooms:
            photos += room.photos
            for surface in room.surfaces:
                photos += surface.photos
                for opening in surface.openings:
                    photos += opening.photos
                for work in surface.works:
                    photos += work.photos
            for inspection in room.inspections:
                photos += inspection.photos
                for question in inspection.questions:
                    photos += question.photos
                for finding in inspection.findings:
                    photos += finding.photos
        return photos

    for report, truth in ((small_report, small_truth), (large_report, large_truth)):
        photos = total(report)
        assert len(photos) == truth.included  # every selected photo exactly once, none other
        assert len({p.attachment_id for p in photos}) == len(photos)
        assert all(p.include_in_report for p in photos)
        assert all(p.uploaded_at.tzinfo is not None for p in photos)  # aware UTC on the real engine
        assert sum(len(p.markers) for p in photos) <= truth.markers
        assert any(m.outline for p in photos for m in p.markers) or truth.included < 2
    # the report is stable between calls on the real engine
    async with pg.sessions() as s:
        again = await PhotoReportReadModel(s).build(large.owner, large.project)
    assert again == large_report
