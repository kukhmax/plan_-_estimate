"""The photos of the archive and of the trash across every object of the owner (archive cleanup AC-3a).

The per-object photo list needs the object, the room and the surface of a photo to be opened first. The owner's archive page lists
what was put away in ONE place, so this read model returns the photos of all objects with the object name and the place of the photo
(room, surface, opening) already resolved. It is read-only; archive, restore, trash and the final deletion stay in the services of AC-1 / AC-2.

Visibility is the one of the per-object list: READY assets of the owner; the archive view = archived attachment OR archived asset, the
trash left out; the trash view = attachments in the trash.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import PhotoAttachmentValidationError
from app.models.inspection import Inspection, InspectionFinding
from app.models.opening import Opening
from app.models.photo_asset import PhotoAsset, PhotoAssetStatus
from app.models.photo_attachment import PhotoAttachment, PhotoAttachmentContext
from app.models.project import Project
from app.models.project_payment import ProjectPayment
from app.models.room import Room
from app.models.surface import Surface

DEFAULT_LIMIT = 50
MAX_LIMIT = 100


@dataclass(frozen=True)
class PhotoPlace:
    """Where a photo lives; every name is optional (the context may not have it, or the row is gone)."""

    room_name: str | None = None
    surface_name: str | None = None
    surface_type: str | None = None
    opening_type: str | None = None
    opening_name: str | None = None
    # IA-3: the settlement record (a receipt or an invoice) a PAYMENT photo documents.
    payment_title: str | None = None
    payment_kind: str | None = None


@dataclass(frozen=True)
class ArchivedPhoto:
    attachment: PhotoAttachment
    asset: PhotoAsset
    project_name: str
    place: PhotoPlace


@dataclass(frozen=True)
class PhotoArchivePage:
    items: list[ArchivedPhoto]
    archived_total: int
    trashed_total: int


def _archived_clause():
    return (
        or_(PhotoAttachment.archived_at.is_not(None), PhotoAsset.archived_at.is_not(None)),
        PhotoAttachment.trashed_at.is_(None),
    )


class PhotoArchiveService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def _base(self, owner_id: uuid.UUID):
        return (
            select(PhotoAttachment, PhotoAsset, Project.name)
            .join(PhotoAsset, PhotoAttachment.asset_id == PhotoAsset.id)
            .join(Project, PhotoAttachment.project_id == Project.id)
            .where(
                PhotoAsset.project_id == PhotoAttachment.project_id,
                PhotoAsset.owner_id == owner_id,
                Project.owner_id == owner_id,
                PhotoAsset.status == PhotoAssetStatus.READY,
            )
        )

    async def _total(self, owner_id: uuid.UUID, *, trashed: bool) -> int:
        stmt = (
            select(func.count())
            .select_from(PhotoAttachment)
            .join(PhotoAsset, PhotoAttachment.asset_id == PhotoAsset.id)
            .join(Project, PhotoAttachment.project_id == Project.id)
            .where(
                PhotoAsset.project_id == PhotoAttachment.project_id,
                PhotoAsset.owner_id == owner_id,
                Project.owner_id == owner_id,
                PhotoAsset.status == PhotoAssetStatus.READY,
            )
        )
        stmt = stmt.where(PhotoAttachment.trashed_at.is_not(None)) if trashed else stmt.where(*_archived_clause())
        return int((await self.db.execute(stmt)).scalar_one())

    async def list_archive(self, owner_id: uuid.UUID, *, trashed: bool, limit: int = DEFAULT_LIMIT) -> PhotoArchivePage:
        if not 1 <= limit <= MAX_LIMIT:
            raise PhotoAttachmentValidationError(f"limit must be between 1 and {MAX_LIMIT}")
        stmt = self._base(owner_id)
        if trashed:
            stmt = stmt.where(PhotoAttachment.trashed_at.is_not(None)).order_by(
                PhotoAttachment.trashed_at.desc(), PhotoAttachment.id
            )
        else:
            stmt = stmt.where(*_archived_clause()).order_by(
                func.coalesce(PhotoAttachment.archived_at, PhotoAsset.archived_at).desc(), PhotoAttachment.id
            )
        rows = (await self.db.execute(stmt.limit(limit))).all()
        places = await self._places([row[0] for row in rows])
        items = [
            ArchivedPhoto(attachment=a, asset=s, project_name=name, place=places.get(a.id, PhotoPlace()))
            for a, s, name in rows
        ]
        return PhotoArchivePage(
            items=items,
            archived_total=await self._total(owner_id, trashed=False),
            trashed_total=await self._total(owner_id, trashed=True),
        )

    async def _places(self, attachments: list[PhotoAttachment]) -> dict[uuid.UUID, PhotoPlace]:
        """Names of the room / surface / opening of each attachment in a few batched queries (no query per photo)."""
        opening_ids = {a.opening_id for a in attachments if a.opening_id}
        openings: dict[uuid.UUID, Opening] = {}
        if opening_ids:
            openings = {o.id: o for o in (await self.db.execute(select(Opening).where(Opening.id.in_(opening_ids)))).scalars()}

        payment_ids = {a.payment_id for a in attachments if a.payment_id}
        payments: dict[uuid.UUID, ProjectPayment] = {}
        if payment_ids:
            payments = {p.id: p for p in (await self.db.execute(select(ProjectPayment).where(ProjectPayment.id.in_(payment_ids)))).scalars()}

        finding_ids = {a.finding_id for a in attachments if a.finding_id}
        finding_inspection: dict[uuid.UUID, uuid.UUID] = {}
        if finding_ids:
            finding_inspection = {
                row[0]: row[1]
                for row in (
                    await self.db.execute(
                        select(InspectionFinding.id, InspectionFinding.inspection_id).where(InspectionFinding.id.in_(finding_ids))
                    )
                ).all()
            }
        inspection_ids = {a.inspection_id for a in attachments if a.inspection_id} | set(finding_inspection.values())
        inspections: dict[uuid.UUID, Inspection] = {}
        if inspection_ids:
            inspections = {
                i.id: i for i in (await self.db.execute(select(Inspection).where(Inspection.id.in_(inspection_ids)))).scalars()
            }

        # The surface of an attachment: its own, the one of its opening, the one of its inspection.
        def surface_id_of(a: PhotoAttachment) -> uuid.UUID | None:
            if a.surface_id:
                return a.surface_id
            if a.opening_id and a.opening_id in openings:
                return openings[a.opening_id].surface_id
            inspection_id = a.inspection_id or (finding_inspection.get(a.finding_id) if a.finding_id else None)
            inspection = inspections.get(inspection_id) if inspection_id else None
            return inspection.surface_id if inspection else None

        surface_ids = {sid for a in attachments if (sid := surface_id_of(a))}
        surfaces: dict[uuid.UUID, Surface] = {}
        if surface_ids:
            surfaces = {s.id: s for s in (await self.db.execute(select(Surface).where(Surface.id.in_(surface_ids)))).scalars()}

        def room_id_of(a: PhotoAttachment) -> uuid.UUID | None:
            if a.room_id:
                return a.room_id
            sid = surface_id_of(a)
            if sid and sid in surfaces:
                return surfaces[sid].room_id
            inspection_id = a.inspection_id or (finding_inspection.get(a.finding_id) if a.finding_id else None)
            inspection = inspections.get(inspection_id) if inspection_id else None
            return inspection.room_id if inspection else None

        room_ids = {rid for a in attachments if (rid := room_id_of(a))}
        rooms: dict[uuid.UUID, str] = {}
        if room_ids:
            rooms = {r.id: r.name for r in (await self.db.execute(select(Room).where(Room.id.in_(room_ids)))).scalars()}

        result: dict[uuid.UUID, PhotoPlace] = {}
        for a in attachments:
            if a.context in (PhotoAttachmentContext.PROJECT,):
                result[a.id] = PhotoPlace()
                continue
            rid, sid = room_id_of(a), surface_id_of(a)
            surface = surfaces.get(sid) if sid else None
            opening = openings.get(a.opening_id) if a.opening_id else None
            payment = payments.get(a.payment_id) if a.payment_id else None
            result[a.id] = PhotoPlace(
                payment_title=payment.title if payment else None,
                payment_kind=payment.kind if payment else None,
                room_name=rooms.get(rid) if rid else None,
                surface_name=surface.name if surface else None,
                surface_type=surface.surface_type.value if surface else None,
                opening_type=opening.opening_type.value if opening else None,
                opening_name=opening.name if opening else None,
            )
        return result
