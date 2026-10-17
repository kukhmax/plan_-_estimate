"""The final deletion of an object (archive cleanup AC-5b).

Only an ARCHIVED object can be deleted, and not one that holds an issued or signed contract, an issued protocol or a downtime notice that was given
(`purge_rules.object_blockers`). There is no trash for an object: the archive is the reversible step, this is the last one.

The order is what makes it safe, the same as for one photo (AC-2): (1) ONE transaction deletes the markers, attachments and file rows of every photo
of the object, writes one ledger row (`PENDING`) per file set, and deletes the object -- the database removes everything else below it
(rooms, surfaces, openings, inspections, estimates, contracts, protocols, issued-document journal, reminders ...) by its own `ON DELETE CASCADE`;
all or nothing; (2) only then the objects are removed from the storage and each ledger row is marked `DONE`. A failure after (1) loses nothing: the
ledger rows stay `PENDING` and `PhotoPurgeService.retry_pending` finishes them (it also runs before every deletion). The backups are cleaned by the
owner's separate step (AC-3) from the very same ledger.

The photo rows are deleted by their ids (the ones the ledger rows were written for): a photo uploaded meanwhile is not deleted, the foreign key
`RESTRICT` then refuses to delete the object, the transaction rolls back and nothing is lost.
"""
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import (
    ProjectNotArchivedError,
    ProjectNotFoundError,
    ProjectPurgeBlockedError,
    ProjectPurgeConflictError,
)
from app.domain.rules.purge_rules import Blocker, DocumentRef, object_blockers
from app.domain.services.media_purger import MediaPurger
from app.domain.services.photo_purge_service import PhotoPurgeService
from app.models.acceptance_protocol import AcceptanceProtocol
from app.models.concealed_works_protocol import ConcealedWorksProtocol
from app.models.contract import Contract
from app.models.decision_protocol import DecisionProtocol
from app.models.downtime_episode import DowntimeEpisode
from app.models.estimate import Estimate
from app.models.handover_protocol import HandoverProtocol
from app.models.inspection import Inspection
from app.models.issued_document import IssuedDocument
from app.models.opening import Opening
from app.models.photo_annotation import PhotoAnnotation
from app.models.photo_asset import PhotoAsset
from app.models.photo_attachment import PhotoAttachment
from app.models.project import Project
from app.models.purge_ledger import PENDING, PurgeLedger
from app.models.room import Room
from app.models.surface import Surface

logger = logging.getLogger(__name__)

# the documents the rule looks at: (kind of the rule, model)
_DOCUMENT_MODELS = (
    ("CONTRACT", Contract),
    ("HANDOVER", HandoverProtocol),
    ("CONCEALED_WORKS", ConcealedWorksProtocol),
    ("DECISION", DecisionProtocol),
    ("ACCEPTANCE", AcceptanceProtocol),
    ("DOWNTIME", DowntimeEpisode),
)


@dataclass(frozen=True, slots=True)
class ProjectPurgePreview:
    project_id: uuid.UUID
    name: str
    archived: bool
    rooms: int
    surfaces: int
    openings: int
    inspections: int
    estimates: int
    documents: int  # contracts and protocols of every kind (drafts and archived ones included)
    sent_documents: int  # rows of the journal of documents given to the client
    photos: int  # attachments
    photo_files: int  # file sets (3 objects each) that leave the storage
    bytes: int
    annotations: int
    blockers: list[Blocker]

    @property
    def can_purge(self) -> bool:
        return self.archived and not self.blockers


@dataclass(frozen=True, slots=True)
class ProjectPurgeOutcome:
    photo_files: int
    storage_pending: int  # file sets of this object still to be removed from the storage (a retry finishes them)


class ProjectPurgeService:
    def __init__(self, db: AsyncSession, purger: MediaPurger) -> None:
        self.db = db
        self.purger = purger

    async def _project(self, owner_id: uuid.UUID, project_id: uuid.UUID, *, lock: bool = False) -> Project:
        stmt = select(Project).where(Project.id == project_id, Project.owner_id == owner_id)
        if lock:
            stmt = stmt.with_for_update()
        project = (await self.db.execute(stmt)).scalar_one_or_none()
        if project is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")
        return project

    async def _count(self, model: type, *conditions) -> int:
        return int((await self.db.execute(select(func.count()).select_from(model).where(*conditions))).scalar_one())

    async def _documents(self, project_id: uuid.UUID) -> list[DocumentRef]:
        refs: list[DocumentRef] = []
        for kind, model in _DOCUMENT_MODELS:
            for row_id, status in (await self.db.execute(select(model.id, model.status).where(model.project_id == project_id))).all():
                refs.append(DocumentRef(kind, row_id, getattr(status, "value", status)))
        return refs

    # -- preview ------------------------------------------------------------------

    async def preview(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> ProjectPurgePreview:
        project = await self._project(owner_id, project_id)
        rooms_of = select(Room.id).where(Room.project_id == project_id)
        surfaces_of = select(Surface.id).where(Surface.room_id.in_(rooms_of))
        documents = await self._documents(project_id)
        sizes = (await self.db.execute(
            select(
                func.count(),
                func.coalesce(func.sum(PhotoAsset.byte_size + PhotoAsset.display_byte_size + PhotoAsset.thumbnail_byte_size), 0),
            ).select_from(PhotoAsset).where(PhotoAsset.project_id == project_id)
        )).one()
        return ProjectPurgePreview(
            project_id=project.id,
            name=project.name,
            archived=project.is_archived,
            rooms=await self._count(Room, Room.project_id == project_id),
            surfaces=await self._count(Surface, Surface.room_id.in_(rooms_of)),
            openings=await self._count(Opening, Opening.surface_id.in_(surfaces_of)),
            inspections=await self._count(Inspection, Inspection.room_id.in_(rooms_of)),
            estimates=await self._count(Estimate, Estimate.project_id == project_id),
            documents=len(documents),
            sent_documents=await self._count(IssuedDocument, IssuedDocument.project_id == project_id),
            photos=await self._count(PhotoAttachment, PhotoAttachment.project_id == project_id),
            photo_files=int(sizes[0]),
            bytes=int(sizes[1]),
            annotations=await self._count(
                PhotoAnnotation,
                PhotoAnnotation.attachment_id.in_(select(PhotoAttachment.id).where(PhotoAttachment.project_id == project_id)),
            ),
            blockers=object_blockers(documents),
        )

    # -- purge --------------------------------------------------------------------

    async def purge(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> ProjectPurgeOutcome:
        photos = PhotoPurgeService(self.db, self.purger)
        await photos.retry_pending(owner_id)  # finish what an earlier deletion left half-done
        project = await self._project(owner_id, project_id, lock=True)
        if not project.is_archived:
            raise ProjectNotArchivedError("only an archived object can be deleted for good")
        blockers = object_blockers(await self._documents(project_id))
        if blockers:
            raise ProjectPurgeBlockedError(blockers)

        assets = list((await self.db.execute(select(PhotoAsset).where(PhotoAsset.project_id == project_id))).scalars())
        asset_ids = [asset.id for asset in assets]
        now = datetime.now(UTC)
        ledger = [
            PurgeLedger(
                owner_id=owner_id, project_id=project_id, asset_id=asset.id, kind="PHOTO", storage_name=asset.storage_name,
                storage_key_original=asset.storage_key_original, storage_key_display=asset.storage_key_display,
                storage_key_thumbnail=asset.storage_key_thumbnail, sha256=asset.sha256, byte_size=asset.byte_size,
                display_byte_size=asset.display_byte_size, thumbnail_byte_size=asset.thumbnail_byte_size,
                purged_at=now, storage_state=PENDING, backup_state=PENDING,
            )
            for asset in assets
        ]
        try:
            if asset_ids:
                attachment_ids = select(PhotoAttachment.id).where(PhotoAttachment.asset_id.in_(asset_ids))
                await self.db.execute(delete(PhotoAnnotation).where(PhotoAnnotation.attachment_id.in_(attachment_ids)))
                await self.db.execute(delete(PhotoAttachment).where(PhotoAttachment.asset_id.in_(asset_ids)))
                await self.db.execute(delete(PhotoAsset).where(PhotoAsset.id.in_(asset_ids)))
                self.db.add_all(ledger)
            # the database removes everything below the object by its own ON DELETE CASCADE; a photo that was added after the list
            # above was read (RESTRICT) makes this fail, and the whole transaction rolls back
            await self.db.execute(delete(Project).where(Project.id == project_id, Project.owner_id == owner_id))
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise ProjectPurgeConflictError("the object changed while it was being deleted") from None

        await photos.retry_pending(owner_id)  # the storage step: removes the objects of the file sets just written
        pending = await self.db.execute(
            select(func.count()).select_from(PurgeLedger).where(PurgeLedger.project_id == project_id, PurgeLedger.storage_state == PENDING)
        )
        return ProjectPurgeOutcome(photo_files=len(ledger), storage_pending=int(pending.scalar_one()))
