"""The final deletion of an archived room or an archived surface (archive cleanup AC-4b).

Only an ARCHIVED room / surface can be deleted (there is no trash: the archive is the reversible step) and not one that a document of the
object still points to: a protocol of concealed works that names the surface, an acceptance protocol or a downtime notice that names the room
(or the surface), a work of an adjacent trade that names the room, a photo that such a document uses as evidence. A document that is ARCHIVED
holds nothing (`purge_rules.structure_blockers`). The estimates are snapshots (their lines only lose the link to the surface): they do not hold.

The order is the one of an object (AC-5b) and of a photo (AC-2): (1) ONE transaction deletes the markers and attachments of every photo that
lives in the room / surface (its openings, its inspections and their findings too), the file rows that no other photo still uses, writes one ledger
row (`PENDING`) per file set removed, cancels the waiting calendar reminders about it and deletes the room / surface itself -- the database removes
everything below it by `ON DELETE CASCADE`; all or nothing; (2) only then the objects leave the storage and the ledger rows become `DONE`
(`PhotoPurgeService.retry_pending`, also run before every deletion). A photo added meanwhile makes a foreign key `RESTRICT` refuse: the
transaction rolls back and nothing is lost.
"""
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import (
    RoomNotFoundError,
    StructureNotArchivedError,
    StructurePurgeBlockedError,
    StructurePurgeConflictError,
    SurfaceNotFoundError,
)
from app.domain.rules.purge_rules import Blocker, DocumentRef, photo_blockers, structure_blockers
from app.domain.services.media_purger import MediaPurger
from app.domain.services.photo_purge_service import PhotoPurgeService
from app.models.acceptance_protocol import AcceptanceProtocol
from app.models.adjacent_work import AdjacentWork
from app.models.concealed_works_protocol import ConcealedWorksProtocol
from app.models.downtime_episode import DowntimeEpisode
from app.models.estimate import Estimate, EstimateLine
from app.models.inspection import Inspection, InspectionFinding
from app.models.opening import Opening
from app.models.photo_annotation import PhotoAnnotation
from app.models.photo_asset import PhotoAsset
from app.models.photo_attachment import PhotoAttachment
from app.models.project import Project
from app.models.purge_ledger import PENDING, PurgeLedger
from app.models.reminder import Reminder, ReminderStatus
from app.models.room import Room
from app.models.surface import Surface

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _Scope:
    """What the deletion reaches: the room (or none for a surface) and everything below it."""

    project_id: uuid.UUID
    kind: str  # ROOM | SURFACE
    room_ids: frozenset[uuid.UUID]
    surface_ids: frozenset[uuid.UUID]
    opening_ids: frozenset[uuid.UUID]
    inspection_ids: frozenset[uuid.UUID]
    finding_ids: frozenset[uuid.UUID]


@dataclass(frozen=True, slots=True)
class StructurePurgePreview:
    kind: str
    target_id: uuid.UUID
    name: str
    archived: bool
    surfaces: int  # of a room; 0 for a surface
    openings: int
    inspections: int
    photos: int  # attachments that go
    photo_files: int  # file sets (3 objects each) that leave the storage: those no other photo still uses
    bytes: int
    annotations: int
    estimate_lines: int  # lines of the estimates that name it: they stay as a record and lose the link
    blockers: list[Blocker]

    @property
    def can_purge(self) -> bool:
        return self.archived and not self.blockers


@dataclass(frozen=True, slots=True)
class StructurePurgeOutcome:
    photo_files: int
    storage_pending: int


class StructurePurgeService:
    def __init__(self, db: AsyncSession, purger: MediaPurger) -> None:
        self.db = db
        self.purger = purger

    # -- scope --------------------------------------------------------------------

    async def _room(self, owner_id: uuid.UUID, project_id: uuid.UUID, room_id: uuid.UUID, *, lock: bool = False) -> Room:
        stmt = (
            select(Room).join(Project, Room.project_id == Project.id)
            .where(Room.id == room_id, Room.project_id == project_id, Project.owner_id == owner_id)
        )
        if lock:
            stmt = stmt.with_for_update(of=Room)
        room = (await self.db.execute(stmt)).scalar_one_or_none()
        if room is None:
            raise RoomNotFoundError(f"Room {room_id} not found")
        return room

    async def _surface(self, owner_id: uuid.UUID, project_id: uuid.UUID, room_id: uuid.UUID, surface_id: uuid.UUID, *, lock: bool = False) -> Surface:
        await self._room(owner_id, project_id, room_id)
        stmt = select(Surface).where(Surface.id == surface_id, Surface.room_id == room_id)
        if lock:
            stmt = stmt.with_for_update()
        surface = (await self.db.execute(stmt)).scalar_one_or_none()
        if surface is None:
            raise SurfaceNotFoundError(f"Surface {surface_id} not found")
        return surface

    async def _scope(self, project_id: uuid.UUID, kind: str, room_ids: set[uuid.UUID], surface_ids: set[uuid.UUID]) -> _Scope:
        if kind == "ROOM":
            surface_ids = set((await self.db.execute(select(Surface.id).where(Surface.room_id.in_(room_ids)))).scalars())
        opening_ids = set((await self.db.execute(select(Opening.id).where(Opening.surface_id.in_(surface_ids)))).scalars()) if surface_ids else set()
        inspection_stmt = select(Inspection.id).where(or_(Inspection.room_id.in_(room_ids), Inspection.surface_id.in_(surface_ids))) if kind == "ROOM" \
            else select(Inspection.id).where(Inspection.surface_id.in_(surface_ids))
        inspection_ids = set((await self.db.execute(inspection_stmt)).scalars())
        finding_ids = set((await self.db.execute(select(InspectionFinding.id).where(InspectionFinding.inspection_id.in_(inspection_ids)))).scalars()) if inspection_ids else set()
        return _Scope(
            project_id=project_id, kind=kind, room_ids=frozenset(room_ids if kind == "ROOM" else set()), surface_ids=frozenset(surface_ids),
            opening_ids=frozenset(opening_ids), inspection_ids=frozenset(inspection_ids), finding_ids=frozenset(finding_ids),
        )

    def _attachments_in(self, scope: _Scope):
        """The attachments (of any state) of every photo that lives in the scope."""
        parts = []
        if scope.room_ids:
            parts.append(PhotoAttachment.room_id.in_(scope.room_ids))
        if scope.surface_ids:
            parts.append(PhotoAttachment.surface_id.in_(scope.surface_ids))
        if scope.opening_ids:
            parts.append(PhotoAttachment.opening_id.in_(scope.opening_ids))
        if scope.inspection_ids:
            parts.append(PhotoAttachment.inspection_id.in_(scope.inspection_ids))
        if scope.finding_ids:
            parts.append(PhotoAttachment.finding_id.in_(scope.finding_ids))
        return select(PhotoAttachment).where(PhotoAttachment.project_id == scope.project_id, or_(*parts))

    # -- the documents that point to the scope --------------------------------------

    async def _documents(self, scope: _Scope, attachments: list[PhotoAttachment]) -> list[DocumentRef]:
        rooms = {str(r) for r in scope.room_ids}
        surfaces = {str(s) for s in scope.surface_ids}
        refs: list[DocumentRef] = []
        for row in (await self.db.execute(select(ConcealedWorksProtocol).where(ConcealedWorksProtocol.project_id == scope.project_id))).scalars():
            if row.surface_id is not None and str(row.surface_id) in surfaces:
                refs.append(DocumentRef("CONCEALED_WORKS", row.id, row.status))
        for row in (await self.db.execute(select(AcceptanceProtocol).where(AcceptanceProtocol.project_id == scope.project_id))).scalars():
            names_room = bool(rooms & {str(r) for r in (row.room_ids or [])})
            names_surface = bool(surfaces & {str(k) for k in (row.surfaces or {})})
            if names_room or names_surface:
                refs.append(DocumentRef("ACCEPTANCE", row.id, row.status))
        for row in (await self.db.execute(select(DowntimeEpisode).where(DowntimeEpisode.project_id == scope.project_id))).scalars():
            if rooms & {str(r) for r in (row.room_ids or [])}:
                refs.append(DocumentRef("DOWNTIME", row.id, row.status))
        for row in (await self.db.execute(select(AdjacentWork).where(AdjacentWork.project_id == scope.project_id))).scalars():
            if rooms & {str(r) for r in (row.room_ids or [])}:
                refs.append(DocumentRef("ADJACENT_WORK", row.id, "ARCHIVED" if row.is_archived else "ACTIVE"))
        # a photo of the scope that a protocol uses as evidence (the rule of deleting a single photo, AC-2)
        protocols = await PhotoPurgeService(self.db, self.purger).protocol_refs(scope.project_id)
        for attachment in attachments:
            for blocker in photo_blockers(attachment.id, protocols):
                refs.append(DocumentRef(blocker.kind, blocker.protocol_id, blocker.status))
        return refs

    # -- preview ------------------------------------------------------------------

    async def preview_room(self, owner_id: uuid.UUID, project_id: uuid.UUID, room_id: uuid.UUID) -> StructurePurgePreview:
        room = await self._room(owner_id, project_id, room_id)
        scope = await self._scope(project_id, "ROOM", {room.id}, set())
        return await self._preview(scope, room.id, room.name, room.is_archived)

    async def preview_surface(self, owner_id: uuid.UUID, project_id: uuid.UUID, room_id: uuid.UUID, surface_id: uuid.UUID) -> StructurePurgePreview:
        surface = await self._surface(owner_id, project_id, room_id, surface_id)
        scope = await self._scope(project_id, "SURFACE", set(), {surface.id})
        return await self._preview(scope, surface.id, surface.name, surface.is_archived)

    async def _preview(self, scope: _Scope, target_id: uuid.UUID, name: str, archived: bool) -> StructurePurgePreview:
        attachments = list((await self.db.execute(self._attachments_in(scope))).scalars())
        released, _ = await self._released_assets(attachments)
        annotations = 0
        if attachments:
            annotations = int((await self.db.execute(
                select(func.count()).select_from(PhotoAnnotation).where(PhotoAnnotation.attachment_id.in_([a.id for a in attachments]))
            )).scalar_one())
        line_parts = []
        if scope.room_ids:
            line_parts.append(EstimateLine.room_id.in_(scope.room_ids))
        if scope.surface_ids:
            line_parts.append(EstimateLine.surface_id.in_(scope.surface_ids))
        lines = 0
        if line_parts:
            lines = int((await self.db.execute(
                select(func.count()).select_from(EstimateLine).join(Estimate, EstimateLine.estimate_id == Estimate.id)
                .where(Estimate.project_id == scope.project_id, or_(*line_parts))
            )).scalar_one())
        return StructurePurgePreview(
            kind=scope.kind, target_id=target_id, name=name, archived=archived,
            surfaces=len(scope.surface_ids) if scope.kind == "ROOM" else 0, openings=len(scope.opening_ids), inspections=len(scope.inspection_ids),
            photos=len(attachments), photo_files=len(released),
            bytes=sum(a.byte_size + a.display_byte_size + a.thumbnail_byte_size for a in released), annotations=annotations,
            estimate_lines=lines, blockers=structure_blockers(await self._documents(scope, attachments)),
        )

    async def _released_assets(self, attachments: list[PhotoAttachment]) -> tuple[list[PhotoAsset], set[uuid.UUID]]:
        """The file rows that no photo OUTSIDE the scope still uses: they go with it, the others stay for their other uses."""
        if not attachments:
            return [], set()
        asset_ids = {a.asset_id for a in attachments}
        going = [a.id for a in attachments]
        still_used = set((await self.db.execute(
            select(PhotoAttachment.asset_id).where(PhotoAttachment.asset_id.in_(asset_ids), PhotoAttachment.id.not_in(going))
        )).scalars())
        released_ids = asset_ids - still_used
        assets = list((await self.db.execute(select(PhotoAsset).where(PhotoAsset.id.in_(released_ids)))).scalars()) if released_ids else []
        return assets, still_used

    # -- purge --------------------------------------------------------------------

    async def purge_room(self, owner_id: uuid.UUID, project_id: uuid.UUID, room_id: uuid.UUID) -> StructurePurgeOutcome:
        await PhotoPurgeService(self.db, self.purger).retry_pending(owner_id)
        room = await self._room(owner_id, project_id, room_id, lock=True)
        if not room.is_archived:
            raise StructureNotArchivedError("only an archived room can be deleted for good")
        scope = await self._scope(project_id, "ROOM", {room.id}, set())
        return await self._purge(owner_id, scope, delete(Room).where(Room.id == room.id, Room.project_id == project_id))

    async def purge_surface(self, owner_id: uuid.UUID, project_id: uuid.UUID, room_id: uuid.UUID, surface_id: uuid.UUID) -> StructurePurgeOutcome:
        await PhotoPurgeService(self.db, self.purger).retry_pending(owner_id)
        surface = await self._surface(owner_id, project_id, room_id, surface_id, lock=True)
        if not surface.is_archived:
            raise StructureNotArchivedError("only an archived surface can be deleted for good")
        scope = await self._scope(project_id, "SURFACE", set(), {surface.id})
        return await self._purge(owner_id, scope, delete(Surface).where(Surface.id == surface.id, Surface.room_id == room_id))

    async def _purge(self, owner_id: uuid.UUID, scope: _Scope, delete_target) -> StructurePurgeOutcome:
        attachments = list((await self.db.execute(self._attachments_in(scope))).scalars())
        blockers = structure_blockers(await self._documents(scope, attachments))
        if blockers:
            raise StructurePurgeBlockedError(blockers)
        released, _ = await self._released_assets(attachments)
        now = datetime.now(UTC)
        ledger = [
            PurgeLedger(
                owner_id=owner_id, project_id=scope.project_id, asset_id=asset.id, kind="PHOTO", storage_name=asset.storage_name,
                storage_key_original=asset.storage_key_original, storage_key_display=asset.storage_key_display,
                storage_key_thumbnail=asset.storage_key_thumbnail, sha256=asset.sha256, byte_size=asset.byte_size,
                display_byte_size=asset.display_byte_size, thumbnail_byte_size=asset.thumbnail_byte_size,
                purged_at=now, storage_state=PENDING, backup_state=PENDING,
            )
            for asset in released
        ]
        attachment_ids = [a.id for a in attachments]
        released_ids = [a.id for a in released]
        reminder_parts = []
        if scope.room_ids:
            reminder_parts.append(Reminder.room_id.in_(scope.room_ids))
        if scope.surface_ids:
            reminder_parts.append(Reminder.surface_id.in_(scope.surface_ids))
        try:
            if attachment_ids:
                await self.db.execute(delete(PhotoAnnotation).where(PhotoAnnotation.attachment_id.in_(attachment_ids)))
                await self.db.execute(delete(PhotoAttachment).where(PhotoAttachment.id.in_(attachment_ids)))
            if released_ids:
                await self.db.execute(delete(PhotoAsset).where(PhotoAsset.id.in_(released_ids)))
                self.db.add_all(ledger)
            if reminder_parts:
                # the calendar items about it have lost their source: cancel the ones that still wait (sent ones stay as history)
                await self.db.execute(
                    update(Reminder).where(Reminder.project_id == scope.project_id, Reminder.status == ReminderStatus.PENDING.value, or_(*reminder_parts))
                    .values(status=ReminderStatus.CANCELLED.value)
                )
            # the database removes everything below by its own ON DELETE CASCADE; a photo added after the lists above were read (RESTRICT)
            # makes this fail and the whole transaction rolls back
            await self.db.execute(delete_target)
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise StructurePurgeConflictError("the room / surface changed while it was being deleted") from None

        await PhotoPurgeService(self.db, self.purger).retry_pending(owner_id)
        pending = await self.db.execute(
            select(func.count()).select_from(PurgeLedger)
            .where(PurgeLedger.project_id == scope.project_id, PurgeLedger.asset_id.in_(released_ids or [uuid.UUID(int=0)]), PurgeLedger.storage_state == PENDING)
        )
        return StructurePurgeOutcome(photo_files=len(ledger), storage_pending=int(pending.scalar_one()))
