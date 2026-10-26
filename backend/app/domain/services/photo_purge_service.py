"""The final deletion of a photo (archive cleanup AC-2).

Only an attachment that is in the trash can be deleted, and not one that an issued protocol still points to. The order is what makes it
safe: (1) one transaction deletes the markers, the attachment and -- when it was the last use of the file -- the file's row, and writes the
ledger row (`PENDING`); (2) only then the objects are removed from the storage and the ledger row is marked `DONE`. A failure after (1)
loses nothing: the ledger row stays `PENDING` and `retry_pending` (also run before every purge) finishes it. Deleting an object that is
already gone is a success, so a retry is always safe.
"""
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import (
    MediaStorageError,
    PhotoAssetNotFoundError,
    PhotoPurgeBlockedError,
    PhotoPurgeConflictError,
    PhotoPurgeNotTrashedError,
)
from app.domain.rules.purge_rules import (
    Blocker,
    ProtocolRef,
    acceptance_photo_ids,
    photo_blockers,
)
from app.domain.services.media_purger import MediaPurger
from app.domain.services.photo_attachment_service import PhotoAttachmentService
from app.models.acceptance_protocol import AcceptanceProtocol
from app.models.concealed_works_protocol import ConcealedWorksProtocol
from app.models.pressure_test_protocol import PressureTestProtocol
from app.models.downtime_episode import DowntimeEpisode
from app.models.photo_annotation import PhotoAnnotation
from app.models.photo_asset import PhotoAsset
from app.models.photo_attachment import PhotoAttachment
from app.models.purge_ledger import DONE, PENDING, PurgeLedger

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PurgePreview:
    attachment_id: uuid.UUID
    trashed: bool
    annotations: int
    other_attachments: int
    deletes_files: bool
    files: int
    bytes: int
    blockers: list[Blocker]

    @property
    def can_purge(self) -> bool:
        return self.trashed and not self.blockers


@dataclass(frozen=True, slots=True)
class PurgeOutcome:
    deleted_files: bool
    storage_pending: bool


@dataclass(frozen=True, slots=True)
class PurgeStatus:
    storage_pending: int
    backup_pending: int
    last_purged_at: datetime | None


class PhotoPurgeService:
    def __init__(self, db: AsyncSession, purger: MediaPurger) -> None:
        self.db = db
        self.purger = purger

    # -- preview ------------------------------------------------------------------

    async def preview(self, owner_id: uuid.UUID, project_id: uuid.UUID, attachment_id: uuid.UUID) -> PurgePreview:
        attachment = await PhotoAttachmentService(self.db).get_attachment(owner_id, project_id, attachment_id)
        asset = await self._asset(attachment.asset_id, project_id)
        others = await self._count(PhotoAttachment, PhotoAttachment.asset_id == attachment.asset_id, PhotoAttachment.id != attachment.id)
        annotations = await self._count(PhotoAnnotation, PhotoAnnotation.attachment_id == attachment.id)
        blockers = photo_blockers(attachment.id, await self._protocol_refs(project_id))
        last_use = others == 0
        return PurgePreview(
            attachment_id=attachment.id,
            trashed=attachment.trashed_at is not None,
            annotations=annotations,
            other_attachments=others,
            deletes_files=last_use,
            files=3 if last_use else 0,
            bytes=(asset.byte_size + asset.display_byte_size + asset.thumbnail_byte_size) if last_use else 0,
            blockers=blockers,
        )

    # -- purge --------------------------------------------------------------------

    async def purge(self, owner_id: uuid.UUID, project_id: uuid.UUID, attachment_id: uuid.UUID) -> PurgeOutcome:
        await self.retry_pending(owner_id)  # finish what an earlier purge left half-done
        attachment = await PhotoAttachmentService(self.db).get_attachment(owner_id, project_id, attachment_id)
        if attachment.trashed_at is None:
            raise PhotoPurgeNotTrashedError("only an attachment in the trash can be deleted for good")
        blockers = photo_blockers(attachment.id, await self._protocol_refs(project_id))
        if blockers:
            raise PhotoPurgeBlockedError(blockers)
        asset = await self._asset(attachment.asset_id, project_id)
        others = await self._count(PhotoAttachment, PhotoAttachment.asset_id == attachment.asset_id, PhotoAttachment.id != attachment.id)

        ledger: PurgeLedger | None = None
        try:
            await self.db.execute(delete(PhotoAnnotation).where(PhotoAnnotation.attachment_id == attachment.id))
            await self.db.delete(attachment)
            await self.db.flush()
            if others == 0:
                ledger = PurgeLedger(
                    owner_id=owner_id, project_id=project_id, asset_id=asset.id, kind="PHOTO", storage_name=asset.storage_name,
                    storage_key_original=asset.storage_key_original, storage_key_display=asset.storage_key_display,
                    storage_key_thumbnail=asset.storage_key_thumbnail, sha256=asset.sha256, byte_size=asset.byte_size,
                    display_byte_size=asset.display_byte_size, thumbnail_byte_size=asset.thumbnail_byte_size,
                    purged_at=datetime.now(UTC), storage_state=PENDING, backup_state=PENDING,
                )
                self.db.add(ledger)
                await self.db.delete(asset)
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise PhotoPurgeConflictError("the photo changed while it was being deleted") from None

        if ledger is None:
            return PurgeOutcome(deleted_files=False, storage_pending=False)
        done = await self._finish(ledger)
        return PurgeOutcome(deleted_files=True, storage_pending=not done)

    # -- retry and status -----------------------------------------------------------

    async def retry_pending(self, owner_id: uuid.UUID) -> int:
        """Remove the objects of every deleted photo whose objects are still in the storage; returns how many are still pending."""
        rows = (await self.db.execute(
            select(PurgeLedger).where(PurgeLedger.owner_id == owner_id, PurgeLedger.storage_state == PENDING).order_by(PurgeLedger.purged_at)
        )).scalars().all()
        pending = 0
        for row in rows:
            if not await self._finish(row):
                pending += 1
        return pending

    async def status(self, owner_id: uuid.UUID) -> PurgeStatus:
        storage = await self._count(PurgeLedger, PurgeLedger.owner_id == owner_id, PurgeLedger.storage_state == PENDING)
        backup = await self._count(PurgeLedger, PurgeLedger.owner_id == owner_id, PurgeLedger.backup_state == PENDING)
        last = (await self.db.execute(select(func.max(PurgeLedger.purged_at)).where(PurgeLedger.owner_id == owner_id))).scalar_one()
        return PurgeStatus(storage_pending=storage, backup_pending=backup, last_purged_at=last)

    # -- helpers --------------------------------------------------------------------

    async def _finish(self, ledger: PurgeLedger) -> bool:
        try:
            await self.purger.delete_objects(ledger.keys())
        except MediaStorageError as exc:
            logger.warning("purge of a photo's objects postponed: %s", type(exc).__name__)
            return False
        ledger.storage_state = DONE
        ledger.storage_done_at = datetime.now(UTC)
        await self.db.commit()
        return True

    async def _asset(self, asset_id: uuid.UUID, project_id: uuid.UUID) -> PhotoAsset:
        asset = (await self.db.execute(select(PhotoAsset).where(PhotoAsset.id == asset_id, PhotoAsset.project_id == project_id))).scalar_one_or_none()
        if asset is None:
            raise PhotoAssetNotFoundError("photo not found")
        return asset

    async def _count(self, model: type, *conditions) -> int:
        return (await self.db.execute(select(func.count()).select_from(model).where(*conditions))).scalar_one()

    async def protocol_refs(self, project_id: uuid.UUID) -> list[ProtocolRef]:
        """The protocols of the object that point to photos (used by the deletion of a room / surface too)."""
        return await self._protocol_refs(project_id)

    async def _protocol_refs(self, project_id: uuid.UUID) -> list[ProtocolRef]:
        refs: list[ProtocolRef] = []
        for row in (await self.db.execute(select(ConcealedWorksProtocol).where(ConcealedWorksProtocol.project_id == project_id))).scalars():
            refs.append(ProtocolRef("CONCEALED_WORKS", row.id, row.status, frozenset(str(p) for p in row.photo_ids or [])))
        for row in (await self.db.execute(select(PressureTestProtocol).where(PressureTestProtocol.project_id == project_id))).scalars():
            refs.append(ProtocolRef("PRESSURE_TEST", row.id, row.status, frozenset(str(p) for p in row.photo_ids or [])))
        for row in (await self.db.execute(select(DowntimeEpisode).where(DowntimeEpisode.project_id == project_id))).scalars():
            refs.append(ProtocolRef("DOWNTIME", row.id, row.status, frozenset(str(p) for p in row.photo_ids or [])))
        for row in (await self.db.execute(select(AcceptanceProtocol).where(AcceptanceProtocol.project_id == project_id))).scalars():
            refs.append(ProtocolRef("ACCEPTANCE", row.id, row.status, acceptance_photo_ids(row.surfaces)))
        return refs
