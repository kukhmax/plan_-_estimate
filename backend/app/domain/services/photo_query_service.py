"""Photo read model (Stage 14C.5): list with keyset pagination and asset
detail. Canonical contract: docs/STAGE_14C_MEDIA_API_CONTRACT.md §16–§18,
§21, §11c.

Visibility (§18):
- archived=False (normal view): active attachment AND non-archived asset.
- archived=True (archive view): archived attachment OR archived asset --
  the restorable items, NOT a superset of the normal view.
Always READY assets only, and always the full ownership chain
(attachment.project_id = asset.project_id = project, asset.owner_id = owner),
even though the foreign keys should already guarantee it.

Ordering is (attachment.position, asset.uploaded_at, attachment.id), and the
same tuple continues a page. The cursor is opaque API state: base64url JSON
with a version, the last row's ordering tuple and a fingerprint of the
filter set it was issued for. It is strictly validated and never trusted
for anything but those typed values (no SQL fragments, no field names, no
executable serialization).
"""

import base64
import binascii
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.domain.exceptions import (
    InspectionFindingNotFoundError,
    PhotoAttachmentValidationError,
    PhotoCursorInvalidError,
)
from app.domain.services.photo_asset_service import PhotoAssetService
from app.domain.services.photo_attachment_service import (
    AttachmentTarget,
    PhotoAttachmentService,
)
from app.domain.services.project_service import ProjectService
from app.models.inspection import Inspection, InspectionFinding
from app.models.opening import Opening
from app.models.photo_asset import PhotoAsset, PhotoAssetStatus
from app.models.photo_attachment import (
    PhotoAttachment,
    PhotoAttachmentContext,
    PhotoCategory,
)
from app.models.room import Room
from app.models.surface import Surface

SITE_CONTEXTS = (
    PhotoAttachmentContext.PROJECT,
    PhotoAttachmentContext.ROOM,
    PhotoAttachmentContext.SURFACE,
    PhotoAttachmentContext.OPENING,
)
DEFAULT_LIMIT = 30
MAX_LIMIT = 100
CURSOR_VERSION = 1
_CURSOR_KEYS = {"v", "p", "u", "i", "f"}


@dataclass(frozen=True)
class PhotoListFilters:
    context: PhotoAttachmentContext | None = None
    room_id: uuid.UUID | None = None
    surface_id: uuid.UUID | None = None
    opening_id: uuid.UUID | None = None
    # Stage 14F.2: INSPECTION photos of one inspection (optionally one question of it) and FINDING photos of one finding row.
    inspection_id: uuid.UUID | None = None
    question_id: uuid.UUID | None = None
    finding_id: uuid.UUID | None = None
    # Stage 14H.1: WORK photos of one surface (all its occurrences, detached ones included), or of one occurrence.
    occurrence_key: uuid.UUID | None = None
    category: PhotoCategory | None = None
    include_in_report: bool | None = None
    archived: bool = False
    # Stage 14E.6: every photo whose target is this room OR lies inside it (its surfaces, their openings). Exclusive with
    # the single-target filters above.
    in_room_id: uuid.UUID | None = None
    # Stage 14F.2: every FINDING photo of one finding lineage (all rows of the lineage). Exclusive with the target filters.
    lineage_id: uuid.UUID | None = None
    # Stage 14F.3: only the four site contexts (PROJECT / ROOM / SURFACE / OPENING): the object-wide list keeps its 14E meaning
    # now that inspection evidence exists. Exclusive with every other target filter.
    site_only: bool = False

    def fingerprint(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> str:
        canonical = json.dumps(
            [
                str(owner_id), str(project_id),
                self.context.value if self.context else None,
                str(self.room_id) if self.room_id else None,
                str(self.surface_id) if self.surface_id else None,
                str(self.opening_id) if self.opening_id else None,
                self.category.value if self.category else None,
                self.include_in_report,
                self.archived,
                str(self.in_room_id) if self.in_room_id else None,
                str(self.inspection_id) if self.inspection_id else None,
                str(self.question_id) if self.question_id else None,
                str(self.finding_id) if self.finding_id else None,
                str(self.lineage_id) if self.lineage_id else None,
                self.site_only,
                str(self.occurrence_key) if self.occurrence_key else None,
            ],
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode()).hexdigest()[:32]


@dataclass(frozen=True)
class PhotoCounts:
    """Visible photos per target (Stage 14E.2, contract 14E §9): active attachments of READY,
    non-archived assets of this project, grouped by their (leaf) target. Targets with no photo are
    absent, so the size is bounded by the number of photographed targets."""

    project: int
    rooms: dict[uuid.UUID, int]
    surfaces: dict[uuid.UUID, int]
    openings: dict[uuid.UUID, int]
    # Stage 14E.6: photos per room INCLUDING those of its surfaces and their openings (the room card shows all of them).
    room_totals: dict[uuid.UUID, int]
    # Stage 14F.2: inspection evidence — kept apart from the room totals above.
    inspections: dict[uuid.UUID, int]
    findings: dict[uuid.UUID, int]
    lineages: dict[uuid.UUID, int]
    # Stage 14F.3: question-level photos only, per inspection then per question (the question button of a checklist).
    questions: dict[uuid.UUID, dict[uuid.UUID, int]]
    # Stage 14H.1: execution evidence (WORK) per occurrence_key and per surface -- never in surfaces / rooms / room_totals.
    works: dict[uuid.UUID, int]
    work_surfaces: dict[uuid.UUID, int]


@dataclass(frozen=True)
class PhotoListPage:
    items: list[tuple[PhotoAttachment, PhotoAsset]]
    next_cursor: str | None


@dataclass(frozen=True)
class _CursorPosition:
    position: int
    uploaded_at: datetime
    attachment_id: uuid.UUID


def encode_cursor(attachment: PhotoAttachment, asset: PhotoAsset, fingerprint: str) -> str:
    payload = {
        "v": CURSOR_VERSION,
        "p": attachment.position,
        "u": asset.uploaded_at.isoformat(),
        "i": str(attachment.id),
        "f": fingerprint,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def decode_cursor(cursor: str, fingerprint: str) -> _CursorPosition:
    """Strict decoding; anything unexpected -> PhotoCursorInvalidError."""
    invalid = PhotoCursorInvalidError("invalid cursor")
    if not cursor or len(cursor) > 512 or not all(c.isalnum() or c in "-_" for c in cursor):
        raise invalid
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        payload = json.loads(raw)
    except (binascii.Error, ValueError, UnicodeDecodeError):
        raise invalid from None
    if not isinstance(payload, dict) or set(payload) != _CURSOR_KEYS:
        raise invalid
    version, position, uploaded, attachment_id, cursor_fingerprint = (
        payload["v"], payload["p"], payload["u"], payload["i"], payload["f"]
    )
    if type(version) is not int or version != CURSOR_VERSION:
        raise invalid
    if type(position) is not int or position < 0:
        raise invalid
    if not isinstance(uploaded, str) or not isinstance(attachment_id, str) or not isinstance(cursor_fingerprint, str):
        raise invalid
    if cursor_fingerprint != fingerprint:
        raise invalid  # issued for another filter set (or another owner / project)
    try:
        uploaded_at = datetime.fromisoformat(uploaded)
        parsed_id = uuid.UUID(attachment_id)
    except ValueError:
        raise invalid from None
    return _CursorPosition(position=position, uploaded_at=uploaded_at, attachment_id=parsed_id)


def _after(cursor: _CursorPosition) -> ColumnElement[bool]:
    """Row strictly after the cursor in (position, uploaded_at, id) order."""
    return or_(
        PhotoAttachment.position > cursor.position,
        and_(
            PhotoAttachment.position == cursor.position,
            or_(
                PhotoAsset.uploaded_at > cursor.uploaded_at,
                and_(PhotoAsset.uploaded_at == cursor.uploaded_at, PhotoAttachment.id > cursor.attachment_id),
            ),
        ),
    )


class PhotoQueryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _validate_filters(
        self, owner_id: uuid.UUID, project_id: uuid.UUID, filters: PhotoListFilters
    ) -> None:
        await ProjectService(self.db).get_project(project_id, owner_id)
        target_ids = (
            filters.room_id, filters.surface_id, filters.opening_id,
            filters.inspection_id, filters.question_id, filters.finding_id,
        )
        if filters.occurrence_key is not None and filters.context is not PhotoAttachmentContext.WORK:
            raise PhotoAttachmentValidationError("occurrence_key requires the WORK context")
        if filters.site_only:
            if filters.context or filters.in_room_id or filters.lineage_id or any(target_ids):
                raise PhotoAttachmentValidationError("site_only cannot be combined with a context or a target id")
            return
        if filters.lineage_id is not None:
            if filters.context or filters.in_room_id or any(target_ids):
                raise PhotoAttachmentValidationError("lineage cannot be combined with a context or a target id")
            stmt = (
                select(InspectionFinding.id)
                .join(Inspection, InspectionFinding.inspection_id == Inspection.id)
                .join(Room, Inspection.room_id == Room.id)
                .where(InspectionFinding.lineage_id == filters.lineage_id, Room.project_id == project_id)
                .limit(1)
            )
            if (await self.db.execute(stmt)).scalar_one_or_none() is None:
                raise InspectionFindingNotFoundError(f"Finding lineage {filters.lineage_id} not found")
            return
        if filters.in_room_id is not None:
            if filters.context or any(target_ids):
                raise PhotoAttachmentValidationError("in_room_id cannot be combined with a context or a target id")
            await PhotoAttachmentService(self.db).validate_target(
                owner_id,
                project_id,
                AttachmentTarget(context=PhotoAttachmentContext.ROOM, room_id=filters.in_room_id),
            )
            return
        if filters.context is None:
            if any(target_ids):
                raise PhotoAttachmentValidationError("a target id requires a matching context")
            return
        if filters.context is PhotoAttachmentContext.WORK:
            # A surface's execution photos, or one occurrence of it. The occurrence is NOT required to be current: the
            # evidence of a removed / replaced work (detached) stays listable. Only the surface chain is validated.
            if filters.surface_id is None:
                raise PhotoAttachmentValidationError("surface_id is required for WORK")
            if any(v is not None for v in (
                filters.room_id, filters.opening_id, filters.inspection_id, filters.question_id, filters.finding_id,
            )):
                raise PhotoAttachmentValidationError("only surface_id and occurrence_key are allowed for WORK")
            await PhotoAttachmentService(self.db).validate_target(
                owner_id,
                project_id,
                AttachmentTarget(context=PhotoAttachmentContext.SURFACE, surface_id=filters.surface_id),
            )
            return
        # Same shape + ownership-chain validation as attach/upload (C12: archived
        # targets are accepted; unsupported contexts are rejected).
        await PhotoAttachmentService(self.db).validate_target(
            owner_id,
            project_id,
            AttachmentTarget(
                context=filters.context,
                room_id=filters.room_id,
                surface_id=filters.surface_id,
                opening_id=filters.opening_id,
                inspection_id=filters.inspection_id,
                question_id=filters.question_id,
                finding_id=filters.finding_id,
            ),
        )

    async def list_photos(
        self,
        owner_id: uuid.UUID,
        project_id: uuid.UUID,
        filters: PhotoListFilters,
        *,
        limit: int = DEFAULT_LIMIT,
        cursor: str | None = None,
    ) -> PhotoListPage:
        if not 1 <= limit <= MAX_LIMIT:
            raise PhotoAttachmentValidationError(f"limit must be between 1 and {MAX_LIMIT}")
        await self._validate_filters(owner_id, project_id, filters)
        fingerprint = filters.fingerprint(owner_id, project_id)
        position = decode_cursor(cursor, fingerprint) if cursor is not None else None

        stmt = (
            select(PhotoAttachment, PhotoAsset)
            .join(PhotoAsset, PhotoAttachment.asset_id == PhotoAsset.id)
            .where(
                PhotoAttachment.project_id == project_id,
                PhotoAsset.project_id == project_id,
                PhotoAsset.owner_id == owner_id,
                PhotoAsset.status == PhotoAssetStatus.READY,
            )
        )
        if filters.archived:
            stmt = stmt.where(or_(PhotoAttachment.archived_at.is_not(None), PhotoAsset.archived_at.is_not(None)))
        else:
            stmt = stmt.where(PhotoAttachment.archived_at.is_(None), PhotoAsset.archived_at.is_(None))
        if filters.context is not None:
            stmt = stmt.where(PhotoAttachment.context == filters.context)
            if filters.room_id is not None:
                stmt = stmt.where(PhotoAttachment.room_id == filters.room_id)
            if filters.surface_id is not None:
                stmt = stmt.where(PhotoAttachment.surface_id == filters.surface_id)
            if filters.opening_id is not None:
                stmt = stmt.where(PhotoAttachment.opening_id == filters.opening_id)
            if filters.inspection_id is not None:
                stmt = stmt.where(PhotoAttachment.inspection_id == filters.inspection_id)
            if filters.question_id is not None:
                stmt = stmt.where(PhotoAttachment.question_id == filters.question_id)
            if filters.finding_id is not None:
                stmt = stmt.where(PhotoAttachment.finding_id == filters.finding_id)
            if filters.occurrence_key is not None:
                stmt = stmt.where(PhotoAttachment.occurrence_key == filters.occurrence_key)
        if filters.site_only:
            stmt = stmt.where(PhotoAttachment.context.in_(SITE_CONTEXTS))
        if filters.lineage_id is not None:
            lineage_findings = select(InspectionFinding.id).where(InspectionFinding.lineage_id == filters.lineage_id)
            stmt = stmt.where(
                PhotoAttachment.context == PhotoAttachmentContext.FINDING,
                PhotoAttachment.finding_id.in_(lineage_findings),
            )
        if filters.in_room_id is not None:
            stmt = stmt.where(self._within_room(filters.in_room_id))
        if filters.category is not None:
            stmt = stmt.where(PhotoAttachment.category == filters.category)
        if filters.include_in_report is not None:
            stmt = stmt.where(PhotoAttachment.include_in_report == filters.include_in_report)
        if position is not None:
            stmt = stmt.where(_after(position))
        stmt = stmt.order_by(PhotoAttachment.position, PhotoAsset.uploaded_at, PhotoAttachment.id).limit(limit + 1)

        rows = [(row[0], row[1]) for row in (await self.db.execute(stmt)).all()]
        page = rows[:limit]
        next_cursor = encode_cursor(*page[-1], fingerprint) if len(rows) > limit else None
        return PhotoListPage(items=page, next_cursor=next_cursor)

    @staticmethod
    def _within_room(room_id: uuid.UUID) -> ColumnElement[bool]:
        """Target is the room itself, one of its surfaces, or an opening of one of its surfaces."""
        room_surfaces = select(Surface.id).where(Surface.room_id == room_id)
        room_openings = select(Opening.id).where(Opening.surface_id.in_(room_surfaces))
        return or_(
            and_(PhotoAttachment.context == PhotoAttachmentContext.ROOM, PhotoAttachment.room_id == room_id),
            and_(PhotoAttachment.context == PhotoAttachmentContext.SURFACE, PhotoAttachment.surface_id.in_(room_surfaces)),
            and_(PhotoAttachment.context == PhotoAttachmentContext.OPENING, PhotoAttachment.opening_id.in_(room_openings)),
        )

    async def counts(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> PhotoCounts:
        """Badge counts for the whole project in ONE aggregate query (same visibility as the normal
        list: active attachment AND non-archived asset, READY only, full ownership chain). Read-only;
        works with uploads disabled (C11)."""
        await ProjectService(self.db).get_project(project_id, owner_id)
        supported = (
            PhotoAttachmentContext.PROJECT,
            PhotoAttachmentContext.ROOM,
            PhotoAttachmentContext.SURFACE,
            PhotoAttachmentContext.OPENING,
            PhotoAttachmentContext.INSPECTION,
            PhotoAttachmentContext.FINDING,
            PhotoAttachmentContext.WORK,
        )
        stmt = (
            select(
                PhotoAttachment.context,
                PhotoAttachment.room_id,
                PhotoAttachment.surface_id,
                PhotoAttachment.opening_id,
                PhotoAttachment.inspection_id,
                PhotoAttachment.question_id,
                PhotoAttachment.finding_id,
                PhotoAttachment.occurrence_key,
                func.count(),
            )
            .join(PhotoAsset, PhotoAttachment.asset_id == PhotoAsset.id)
            .where(
                PhotoAttachment.project_id == project_id,
                PhotoAsset.project_id == project_id,
                PhotoAsset.owner_id == owner_id,
                PhotoAsset.status == PhotoAssetStatus.READY,
                PhotoAttachment.archived_at.is_(None),
                PhotoAsset.archived_at.is_(None),
                PhotoAttachment.context.in_(supported),
            )
            .group_by(
                PhotoAttachment.context,
                PhotoAttachment.room_id,
                PhotoAttachment.surface_id,
                PhotoAttachment.opening_id,
                PhotoAttachment.inspection_id,
                PhotoAttachment.question_id,
                PhotoAttachment.finding_id,
                PhotoAttachment.occurrence_key,
            )
        )
        project_total = 0
        rooms: dict[uuid.UUID, int] = {}
        surfaces: dict[uuid.UUID, int] = {}
        openings: dict[uuid.UUID, int] = {}
        inspections: dict[uuid.UUID, int] = {}
        findings: dict[uuid.UUID, int] = {}
        questions: dict[uuid.UUID, dict[uuid.UUID, int]] = {}
        works: dict[uuid.UUID, int] = {}
        work_surfaces: dict[uuid.UUID, int] = {}
        for context, room_id, surface_id, opening_id, inspection_id, question_id, finding_id, occurrence_key, total in (
            await self.db.execute(stmt)
        ).all():
            if context is PhotoAttachmentContext.PROJECT:
                project_total += int(total)
            elif context is PhotoAttachmentContext.ROOM and room_id is not None:
                rooms[room_id] = rooms.get(room_id, 0) + int(total)
            elif context is PhotoAttachmentContext.SURFACE and surface_id is not None:
                surfaces[surface_id] = surfaces.get(surface_id, 0) + int(total)
            elif context is PhotoAttachmentContext.OPENING and opening_id is not None:
                openings[opening_id] = openings.get(opening_id, 0) + int(total)
            elif context is PhotoAttachmentContext.INSPECTION and inspection_id is not None:
                inspections[inspection_id] = inspections.get(inspection_id, 0) + int(total)
                if question_id is not None:
                    per_question = questions.setdefault(inspection_id, {})
                    per_question[question_id] = per_question.get(question_id, 0) + int(total)
            elif context is PhotoAttachmentContext.FINDING and finding_id is not None:
                findings[finding_id] = findings.get(finding_id, 0) + int(total)
            elif context is PhotoAttachmentContext.WORK and occurrence_key is not None and surface_id is not None:
                works[occurrence_key] = works.get(occurrence_key, 0) + int(total)
                work_surfaces[surface_id] = work_surfaces.get(surface_id, 0) + int(total)
        room_totals = dict(rooms)
        if surfaces:
            rows = await self.db.execute(select(Surface.id, Surface.room_id).where(Surface.id.in_(list(surfaces))))
            for surface_id, room_id in rows.all():
                room_totals[room_id] = room_totals.get(room_id, 0) + surfaces[surface_id]
        if openings:
            rows = await self.db.execute(
                select(Opening.id, Surface.room_id)
                .join(Surface, Opening.surface_id == Surface.id)
                .where(Opening.id.in_(list(openings)))
            )
            for opening_id, room_id in rows.all():
                room_totals[room_id] = room_totals.get(room_id, 0) + openings[opening_id]
        lineages: dict[uuid.UUID, int] = {}
        if findings:
            rows = await self.db.execute(
                select(InspectionFinding.id, InspectionFinding.lineage_id).where(InspectionFinding.id.in_(list(findings)))
            )
            for finding_id, lineage_id in rows.all():
                lineages[lineage_id] = lineages.get(lineage_id, 0) + findings[finding_id]
        return PhotoCounts(
            project=project_total, rooms=rooms, surfaces=surfaces, openings=openings, room_totals=room_totals,
            inspections=inspections, findings=findings, lineages=lineages, questions=questions,
            works=works, work_surfaces=work_surfaces,
        )

    async def get_detail(
        self, owner_id: uuid.UUID, project_id: uuid.UUID, asset_id: uuid.UUID
    ) -> tuple[PhotoAsset, list[PhotoAttachment]]:
        """READY asset of this owner and project (archived included) with all
        its attachments of this project, archived ones included, in creation
        order (the first one is the upload's first attachment)."""
        await ProjectService(self.db).get_project(project_id, owner_id)
        asset = await PhotoAssetService(self.db).get_ready(asset_id, owner_id, project_id)
        stmt = (
            select(PhotoAttachment)
            .where(PhotoAttachment.asset_id == asset.id, PhotoAttachment.project_id == project_id)
            .order_by(PhotoAttachment.created_at, PhotoAttachment.id)
        )
        return asset, list((await self.db.execute(stmt)).scalars().all())
