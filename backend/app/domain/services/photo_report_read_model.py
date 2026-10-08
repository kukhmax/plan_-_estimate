"""Photo report read model (Stage 14I): the photos selected for a Stage 15 document, in document order.

Canonical design: docs/STAGE_14_PHOTO_FIXATION_ARCHITECTURE.md §5, §14 and docs/STAGE_14I_REPORT_READ_MODEL_PLAN_RU.md.

One read-only service. For one project of one owner it returns an immutable tree (not ORM objects, not HTTP schemas):
project photos, then rooms -> surfaces -> openings / works and rooms -> inspections -> questions / findings. It writes
nothing, calls no storage and issues no URLs (Stage 15 reads the bytes through the storage port by the keys given here).

Rules (plan §2): only attachments with `include_in_report` (unless `only_included=False`); the usual visibility (READY
asset, active attachment and asset, full ownership chain); photos of archived rooms / surfaces / openings / inspections are
left out together with everything below them; findings are grouped by `lineage_id`; a node without selected photos and
without selected descendants is dropped; the order is fully deterministic; the number of SQL statements does not depend
on the number of photos.
"""
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.services.photo_annotation_service import PhotoAnnotationService
from app.domain.services.project_service import ProjectService
from app.models.checklist import ChecklistQuestion
from app.models.inspection import Inspection, InspectionFinding
from app.models.opening import Opening
from app.models.photo_asset import PhotoAsset, PhotoAssetStatus
from app.models.photo_attachment import (
    PhotoAttachment,
    PhotoAttachmentContext,
    PhotoCategory,
)
from app.models.price_item import PriceItem
from app.models.room import Room
from app.models.surface import Surface
from app.models.work_plan import SurfacePlannedWork, SurfaceWorkPlan

# Execution order of a work's photos (plan R6); the remaining categories follow.
WORK_CATEGORY_ORDER: tuple[PhotoCategory, ...] = (
    PhotoCategory.BEFORE,
    PhotoCategory.PREPARATION,
    PhotoCategory.IN_PROGRESS,
    PhotoCategory.HIDDEN_WORK,
    PhotoCategory.AFTER,
    PhotoCategory.GENERAL,
    PhotoCategory.DEFECT,
    PhotoCategory.DAMAGE,
)
_WORK_RANK = {category: rank for rank, category in enumerate(WORK_CATEGORY_ORDER)}
_NO_TIME = datetime(1, 1, 1, tzinfo=UTC)
_LAST = 1 << 30


@dataclass(frozen=True, slots=True)
class ReportMarker:
    id: uuid.UUID
    x: float
    y: float
    label: str | None
    position: int
    outline: tuple[tuple[float, float], ...] | None


@dataclass(frozen=True, slots=True)
class ReportPhoto:
    attachment_id: uuid.UUID
    asset_id: uuid.UUID
    context: PhotoAttachmentContext
    category: PhotoCategory
    caption: str | None
    include_in_report: bool
    position: int
    room_id: uuid.UUID | None
    surface_id: uuid.UUID | None
    opening_id: uuid.UUID | None
    inspection_id: uuid.UUID | None
    question_id: uuid.UUID | None
    finding_id: uuid.UUID | None
    occurrence_key: uuid.UUID | None
    price_item_id: uuid.UUID | None  # WORK photos: the snapshot of the occurrence's operation
    width: int
    height: int
    content_type: str
    byte_size: int
    sha256: str
    captured_at: datetime | None
    uploaded_at: datetime
    # Server-side only: how the bytes are read (display copy for the page, the original for a high-quality export).
    storage_name: str
    storage_key_display: str
    storage_key_original: str
    markers: tuple[ReportMarker, ...]


@dataclass(frozen=True, slots=True)
class ReportQuestion:
    question_id: uuid.UUID
    text_key: str
    position: int
    photos: tuple[ReportPhoto, ...]


@dataclass(frozen=True, slots=True)
class ReportFinding:
    """One finding lineage: the header is the active row of the lineage, else its last row."""

    lineage_id: uuid.UUID
    finding_id: uuid.UUID
    finding_key: str
    label_key: str | None
    value_snapshot: dict | None
    is_active: bool
    photos: tuple[ReportPhoto, ...]


@dataclass(frozen=True, slots=True)
class ReportInspection:
    inspection_id: uuid.UUID
    surface_id: uuid.UUID | None
    plane: str | None  # "FLOOR" / "CEILING" when the inspection targets a whole plane of the room
    status: str
    photos: tuple[ReportPhoto, ...]
    questions: tuple[ReportQuestion, ...]
    findings: tuple[ReportFinding, ...]


@dataclass(frozen=True, slots=True)
class ReportWork:
    occurrence_key: uuid.UUID
    price_item_id: uuid.UUID | None
    price_item_code: str | None
    price_item_name_key: str | None
    price_item_display_name: str | None
    current: bool  # still in the surface's work plan; False = detached (removed / replaced), its evidence stays
    photos: tuple[ReportPhoto, ...]


@dataclass(frozen=True, slots=True)
class ReportOpening:
    opening_id: uuid.UUID
    name: str | None
    photos: tuple[ReportPhoto, ...]


@dataclass(frozen=True, slots=True)
class ReportSurface:
    surface_id: uuid.UUID
    name: str
    surface_type: str
    photos: tuple[ReportPhoto, ...]
    openings: tuple[ReportOpening, ...]
    works: tuple[ReportWork, ...]


@dataclass(frozen=True, slots=True)
class ReportRoom:
    room_id: uuid.UUID
    name: str
    photos: tuple[ReportPhoto, ...]
    surfaces: tuple[ReportSurface, ...]
    inspections: tuple[ReportInspection, ...]


@dataclass(frozen=True, slots=True)
class PhotoReport:
    project_id: uuid.UUID
    project_photos: tuple[ReportPhoto, ...]
    rooms: tuple[ReportRoom, ...]


def _utc(value: datetime | None) -> datetime | None:
    """Times come out as aware UTC whatever the database driver returned (a naive value is already UTC)."""
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def photo_sort_key(photo: ReportPhoto) -> tuple:
    """position, captured_at (unknown last), uploaded_at, id -- the order of photos inside one node (plan R7)."""
    return (
        photo.position,
        photo.captured_at is None,
        photo.captured_at or _NO_TIME,
        photo.uploaded_at,
        photo.attachment_id,
    )


def _sorted(photos: Iterable[ReportPhoto]) -> tuple[ReportPhoto, ...]:
    return tuple(sorted(photos, key=photo_sort_key))


def _work_sort_key(photo: ReportPhoto) -> tuple:
    return (_WORK_RANK.get(photo.category, len(_WORK_RANK)), *photo_sort_key(photo))


class PhotoReportReadModel:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def build(
        self, owner_id: uuid.UUID, project_id: uuid.UUID, *, only_included: bool = True
    ) -> PhotoReport:
        """Raises ProjectNotFoundError for a project that is not this owner's (nothing else is read then)."""
        await ProjectService(self.db).get_project(project_id, owner_id)
        rows = await self._visible(owner_id, project_id, only_included)
        markers = await self._markers([attachment.id for attachment, _ in rows])
        photos = [self._photo(attachment, asset, markers.get(attachment.id, ())) for attachment, asset in rows]

        rooms = list((await self.db.execute(select(Room).where(Room.project_id == project_id))).scalars().all())
        room_ids = [room.id for room in rooms]
        surfaces = await self._rows(Surface, Surface.room_id, room_ids)
        openings = await self._rows(Opening, Opening.surface_id, [surface.id for surface in surfaces])
        inspections = await self._rows(Inspection, Inspection.room_id, room_ids)
        findings = await self._rows(InspectionFinding, InspectionFinding.inspection_id, [i.id for i in inspections])
        questions = await self._questions({p.question_id for p in photos if p.question_id is not None})
        planned = await self._planned_works([surface.id for surface in surfaces])
        prices = await self._price_items({p.price_item_id for p in photos if p.price_item_id is not None})

        # A node is live when it is not archived itself; a node under an archived parent never reaches the report
        # because the assembly attaches children only to live parents. An inspection hangs on its room, not on the
        # surface it targets, so its own surface is checked here.
        live_rooms = {room.id for room in rooms if not room.is_archived}
        live_surfaces = {s.id for s in surfaces if not s.is_archived}
        live_openings = {o.id for o in openings if not o.is_archived}
        live_inspections = {
            i.id for i in inspections if not i.is_archived and (i.surface_id is None or i.surface_id in live_surfaces)
        }
        finding_by_id = {f.id: f for f in findings}
        lineage_rows: dict[uuid.UUID, list[InspectionFinding]] = {}
        for finding in findings:
            lineage_rows.setdefault(finding.lineage_id, []).append(finding)

        by_project: list[ReportPhoto] = []
        by_room: dict[uuid.UUID, list[ReportPhoto]] = {}
        by_surface: dict[uuid.UUID, list[ReportPhoto]] = {}
        by_opening: dict[uuid.UUID, list[ReportPhoto]] = {}
        by_inspection: dict[uuid.UUID, list[ReportPhoto]] = {}
        by_question: dict[tuple[uuid.UUID, uuid.UUID], list[ReportPhoto]] = {}
        by_lineage: dict[uuid.UUID, list[ReportPhoto]] = {}
        by_work: dict[tuple[uuid.UUID, uuid.UUID], list[ReportPhoto]] = {}
        for photo in photos:
            context = photo.context
            if context is PhotoAttachmentContext.PROJECT:
                by_project.append(photo)
            elif context is PhotoAttachmentContext.ROOM and photo.room_id in live_rooms:
                by_room.setdefault(photo.room_id, []).append(photo)
            elif context is PhotoAttachmentContext.SURFACE and photo.surface_id in live_surfaces:
                by_surface.setdefault(photo.surface_id, []).append(photo)
            elif context is PhotoAttachmentContext.OPENING and photo.opening_id in live_openings:
                by_opening.setdefault(photo.opening_id, []).append(photo)
            elif context is PhotoAttachmentContext.INSPECTION and photo.inspection_id in live_inspections:
                if photo.question_id is None:
                    by_inspection.setdefault(photo.inspection_id, []).append(photo)
                else:
                    by_question.setdefault((photo.inspection_id, photo.question_id), []).append(photo)
            elif context is PhotoAttachmentContext.FINDING and photo.finding_id in finding_by_id:
                by_lineage.setdefault(finding_by_id[photo.finding_id].lineage_id, []).append(photo)
            elif context is PhotoAttachmentContext.WORK and photo.surface_id in live_surfaces and photo.occurrence_key:
                by_work.setdefault((photo.surface_id, photo.occurrence_key), []).append(photo)

        return PhotoReport(
            project_id=project_id,
            project_photos=_sorted(by_project),
            rooms=self._rooms(
                rooms, surfaces, openings, inspections, planned, prices, questions, lineage_rows,
                live_rooms, live_surfaces, live_openings, live_inspections,
                by_room, by_surface, by_opening, by_inspection, by_question, by_lineage, by_work,
            ),
        )

    # -- assembly ------------------------------------------------------------------------------------------------

    @staticmethod
    def _rooms(
        rooms, surfaces, openings, inspections, planned, prices, questions, lineage_rows,
        live_rooms, live_surfaces, live_openings, live_inspections,
        by_room, by_surface, by_opening, by_inspection, by_question, by_lineage, by_work,
    ) -> tuple[ReportRoom, ...]:
        opening_nodes: dict[uuid.UUID, list[ReportOpening]] = {}
        for opening in sorted(openings, key=lambda o: (_utc(o.created_at), o.id)):
            if opening.id in live_openings and by_opening.get(opening.id):
                opening_nodes.setdefault(opening.surface_id, []).append(
                    ReportOpening(opening.id, opening.name, _sorted(by_opening[opening.id]))
                )

        work_nodes: dict[uuid.UUID, list[ReportWork]] = {}
        grouped: dict[uuid.UUID, list[tuple[uuid.UUID, list[ReportPhoto]]]] = {}
        for (surface_id, occurrence_key), group in by_work.items():
            grouped.setdefault(surface_id, []).append((occurrence_key, group))
        for surface_id, entries in grouped.items():
            current = planned.get(surface_id, {})
            nodes = []
            for occurrence_key, group in entries:
                ordered = tuple(sorted(group, key=_work_sort_key))
                price_item = prices.get(next((p.price_item_id for p in ordered if p.price_item_id), None))
                nodes.append((
                    (occurrence_key not in current, current.get(occurrence_key, _LAST), ordered[0].uploaded_at, occurrence_key),
                    ReportWork(
                        occurrence_key=occurrence_key,
                        price_item_id=price_item.id if price_item else None,
                        price_item_code=price_item.code if price_item else None,
                        price_item_name_key=price_item.name_key if price_item else None,
                        price_item_display_name=price_item.display_name if price_item else None,
                        current=occurrence_key in current,
                        photos=ordered,
                    ),
                ))
            work_nodes[surface_id] = [node for _, node in sorted(nodes, key=lambda item: item[0])]

        surface_nodes: dict[uuid.UUID, list[ReportSurface]] = {}
        for surface in sorted(surfaces, key=lambda s: (s.position is None, s.position or 0, _utc(s.created_at), s.id)):
            if surface.id not in live_surfaces:
                continue
            own = by_surface.get(surface.id, [])
            node_openings = tuple(opening_nodes.get(surface.id, ()))
            node_works = tuple(work_nodes.get(surface.id, ()))
            if own or node_openings or node_works:
                surface_nodes.setdefault(surface.room_id, []).append(
                    ReportSurface(
                        surface_id=surface.id,
                        name=surface.name,
                        surface_type=surface.surface_type.value,
                        photos=_sorted(own),
                        openings=node_openings,
                        works=node_works,
                    )
                )

        inspection_nodes: dict[uuid.UUID, list[ReportInspection]] = {}
        lineage_by_inspection: dict[uuid.UUID, list[tuple[tuple, ReportFinding]]] = {}
        for lineage_id, group in by_lineage.items():
            rows = lineage_rows[lineage_id]
            header = max([r for r in rows if r.is_active] or rows, key=_finding_order)
            if header.inspection_id in live_inspections:
                lineage_by_inspection.setdefault(header.inspection_id, []).append((
                    (*_finding_order(header), lineage_id),
                    ReportFinding(
                        lineage_id=lineage_id,
                        finding_id=header.id,
                        finding_key=header.finding_key,
                        label_key=header.label_key,
                        value_snapshot=header.value_snapshot,
                        is_active=header.is_active,
                        photos=_sorted(group),
                    ),
                ))
        for inspection in sorted(inspections, key=lambda i: (_utc(i.created_at), i.id)):
            if inspection.id not in live_inspections:
                continue
            own = by_inspection.get(inspection.id, [])
            question_nodes = tuple(
                ReportQuestion(question_id, questions[question_id].text_key, questions[question_id].position, _sorted(group))
                for (inspection_id, question_id), group in sorted(
                    by_question.items(),
                    key=lambda item: (questions[item[0][1]].position, item[0][1]),
                )
                if inspection_id == inspection.id and question_id in questions
            )
            finding_nodes = tuple(node for _, node in sorted(lineage_by_inspection.get(inspection.id, ()), key=lambda item: item[0]))
            if own or question_nodes or finding_nodes:
                inspection_nodes.setdefault(inspection.room_id, []).append(
                    ReportInspection(
                        inspection_id=inspection.id,
                        surface_id=inspection.surface_id,
                        plane=inspection.plane.value if inspection.plane else None,
                        status=inspection.status.value,
                        photos=_sorted(own),
                        questions=question_nodes,
                        findings=finding_nodes,
                    )
                )

        room_nodes: list[ReportRoom] = []
        for room in sorted(rooms, key=lambda r: (_utc(r.created_at), r.id)):
            if room.id not in live_rooms:
                continue
            own = by_room.get(room.id, [])
            node_surfaces = tuple(surface_nodes.get(room.id, ()))
            node_inspections = tuple(inspection_nodes.get(room.id, ()))
            if own or node_surfaces or node_inspections:
                room_nodes.append(ReportRoom(room.id, room.name, _sorted(own), node_surfaces, node_inspections))
        return tuple(room_nodes)

    # -- queries (each one statement, independent of the number of photos) ------------------------------------------

    async def _visible(
        self, owner_id: uuid.UUID, project_id: uuid.UUID, only_included: bool
    ) -> list[tuple[PhotoAttachment, PhotoAsset]]:
        stmt = (
            select(PhotoAttachment, PhotoAsset)
            .join(PhotoAsset, PhotoAttachment.asset_id == PhotoAsset.id)
            .where(
                PhotoAttachment.project_id == project_id,
                PhotoAsset.project_id == project_id,
                PhotoAsset.owner_id == owner_id,
                PhotoAsset.status == PhotoAssetStatus.READY,
                PhotoAttachment.archived_at.is_(None),
                PhotoAsset.archived_at.is_(None),
            )
        )
        if only_included:
            stmt = stmt.where(PhotoAttachment.include_in_report.is_(True))
        return [(row[0], row[1]) for row in (await self.db.execute(stmt)).all()]

    async def _markers(self, attachment_ids: list[uuid.UUID]) -> dict[uuid.UUID, tuple[ReportMarker, ...]]:
        found: dict[uuid.UUID, list[ReportMarker]] = {}
        for marker in await PhotoAnnotationService(self.db).list_for_attachments(attachment_ids):
            outline = tuple((float(point[0]), float(point[1])) for point in marker.outline) if marker.outline else None
            found.setdefault(marker.attachment_id, []).append(
                ReportMarker(marker.id, float(marker.x), float(marker.y), marker.label, marker.position, outline)
            )
        return {attachment_id: tuple(items) for attachment_id, items in found.items()}

    async def _rows(self, model, column, ids: list[uuid.UUID]) -> list:
        if not ids:
            return []
        return list((await self.db.execute(select(model).where(column.in_(ids)))).scalars().all())

    async def _questions(self, ids: set[uuid.UUID]) -> dict[uuid.UUID, ChecklistQuestion]:
        if not ids:
            return {}
        rows = (await self.db.execute(select(ChecklistQuestion).where(ChecklistQuestion.id.in_(ids)))).scalars().all()
        return {question.id: question for question in rows}

    async def _planned_works(self, surface_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict[uuid.UUID, int]]:
        """surface -> {occurrence_key: position in the current plan}."""
        if not surface_ids:
            return {}
        stmt = (
            select(SurfaceWorkPlan.surface_id, SurfacePlannedWork.occurrence_key, SurfacePlannedWork.position)
            .join(SurfacePlannedWork, SurfacePlannedWork.work_plan_id == SurfaceWorkPlan.id)
            .where(SurfaceWorkPlan.surface_id.in_(surface_ids))
        )
        found: dict[uuid.UUID, dict[uuid.UUID, int]] = {}
        for surface_id, occurrence_key, position in (await self.db.execute(stmt)).all():
            found.setdefault(surface_id, {})[occurrence_key] = position
        return found

    async def _price_items(self, ids: set[uuid.UUID]) -> dict[uuid.UUID, PriceItem]:
        if not ids:
            return {}
        rows = (await self.db.execute(select(PriceItem).where(PriceItem.id.in_(ids)))).scalars().all()
        return {item.id: item for item in rows}

    # -- small helpers -------------------------------------------------------------------------------------------------

    @staticmethod
    def _photo(attachment: PhotoAttachment, asset: PhotoAsset, markers: tuple[ReportMarker, ...]) -> ReportPhoto:
        return ReportPhoto(
            attachment_id=attachment.id,
            asset_id=asset.id,
            context=attachment.context,
            category=attachment.category,
            caption=attachment.caption,
            include_in_report=attachment.include_in_report,
            position=attachment.position,
            room_id=attachment.room_id,
            surface_id=attachment.surface_id,
            opening_id=attachment.opening_id,
            inspection_id=attachment.inspection_id,
            question_id=attachment.question_id,
            finding_id=attachment.finding_id,
            occurrence_key=attachment.occurrence_key,
            price_item_id=attachment.price_item_id,
            width=asset.width,
            height=asset.height,
            content_type=asset.content_type.value,
            byte_size=asset.byte_size,
            sha256=asset.sha256,
            captured_at=_utc(asset.captured_at),
            uploaded_at=_utc(asset.uploaded_at),
            storage_name=asset.storage_name,
            storage_key_display=asset.storage_key_display,
            storage_key_original=asset.storage_key_original,
            markers=markers,
        )


def _finding_order(row: InspectionFinding) -> tuple:
    return (row.position is None, row.position or 0, _utc(row.created_at), row.id)
