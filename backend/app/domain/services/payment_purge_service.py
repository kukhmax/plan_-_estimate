"""The archived settlement records of all objects and their final deletion (invoices and advances, IA-7).

The archive page lists what was put away in ONE place, with the object, so a record can be restored (the route of the record) or deleted
for good without walking through the objects. Listed: an archived record of an object that is in work; nothing of an archived object (it
returns, or goes, together with the object).

Only an ARCHIVED record can be deleted (the archive is the reversible step). The order is the one of a room (AC-4b) and of a photo (AC-2):
(1) ONE transaction deletes the markers and attachments of the receipt / invoice photos of the record, the file rows that no other photo
still uses, writes one ledger row (`PENDING`) per file set removed, lets the payments that settled a deleted invoice go on without it
(they keep their money, only the link is gone) and deletes the record; all or nothing; (2) only then the objects leave the storage and the
ledger rows become `DONE` (`PhotoPurgeService.retry_pending`, also run before every deletion). A photo added meanwhile makes the
foreign key `RESTRICT` refuse: the transaction rolls back and nothing is lost. The sums of the object are made from the records that
remain, so nothing is left to repair.
"""
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import PaymentNotArchivedError, PaymentNotFoundError, PaymentPurgeConflictError
from app.domain.services.media_purger import MediaPurger
from app.domain.services.photo_purge_service import PhotoPurgeService
from app.models.photo_annotation import PhotoAnnotation
from app.models.photo_asset import PhotoAsset
from app.models.photo_attachment import PhotoAttachment
from app.models.project import Project
from app.models.project_payment import ProjectPayment
from app.models.purge_ledger import PENDING, PurgeLedger

LIMIT = 200


@dataclass(frozen=True, slots=True)
class ArchivedPayment:
    payment: ProjectPayment
    project_name: str
    photos: int


@dataclass(frozen=True, slots=True)
class ArchivedPayments:
    items: list[ArchivedPayment]
    total: int


@dataclass(frozen=True, slots=True)
class PaymentPurgePreview:
    target_id: uuid.UUID
    kind: str
    title: str
    archived: bool
    tied_payments: int  # of an invoice: the payments that settled it; they stay and lose the link
    photos: int  # attachments that go
    photo_files: int  # file sets (3 objects each) that leave the storage: those no other photo still uses
    bytes: int
    annotations: int

    @property
    def can_purge(self) -> bool:
        return self.archived


@dataclass(frozen=True, slots=True)
class PaymentPurgeOutcome:
    photo_files: int
    storage_pending: int


class PaymentPurgeService:
    def __init__(self, db: AsyncSession, purger: MediaPurger) -> None:
        self.db = db
        self.purger = purger

    # -- the list -------------------------------------------------------------------

    async def list_archived(self, owner_id: uuid.UUID) -> ArchivedPayments:
        where = (ProjectPayment.owner_id == owner_id, ProjectPayment.is_archived.is_(True), Project.is_archived.is_(False))
        rows = (await self.db.execute(
            select(ProjectPayment, Project.name).join(Project, Project.id == ProjectPayment.project_id).where(*where)
            .order_by(ProjectPayment.updated_at.desc(), ProjectPayment.id.desc()).limit(LIMIT)
        )).all()
        total = int((await self.db.execute(
            select(func.count()).select_from(ProjectPayment).join(Project, Project.id == ProjectPayment.project_id).where(*where)
        )).scalar_one())
        counts: dict[uuid.UUID, int] = {}
        if rows:
            ids = [row[0].id for row in rows]
            counts = dict((await self.db.execute(
                select(PhotoAttachment.payment_id, func.count()).where(PhotoAttachment.payment_id.in_(ids)).group_by(PhotoAttachment.payment_id)
            )).all())
        return ArchivedPayments([ArchivedPayment(row[0], row[1], int(counts.get(row[0].id, 0))) for row in rows], total)

    # -- preview ----------------------------------------------------------------------

    async def _payment(self, owner_id: uuid.UUID, project_id: uuid.UUID, payment_id: uuid.UUID, *, lock: bool = False) -> ProjectPayment:
        stmt = select(ProjectPayment).where(
            ProjectPayment.id == payment_id, ProjectPayment.project_id == project_id, ProjectPayment.owner_id == owner_id
        )
        if lock:
            stmt = stmt.with_for_update()
        row = (await self.db.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise PaymentNotFoundError(f"Payment {payment_id} not found")
        return row

    async def _attachments(self, payment_id: uuid.UUID) -> list[PhotoAttachment]:
        return list((await self.db.execute(select(PhotoAttachment).where(PhotoAttachment.payment_id == payment_id))).scalars())

    async def _released(self, attachments: list[PhotoAttachment]) -> list[PhotoAsset]:
        """The file rows that no photo OUTSIDE the record still uses: they go with it, the others stay for their other uses."""
        if not attachments:
            return []
        asset_ids = {a.asset_id for a in attachments}
        going = [a.id for a in attachments]
        still_used = set((await self.db.execute(
            select(PhotoAttachment.asset_id).where(PhotoAttachment.asset_id.in_(asset_ids), PhotoAttachment.id.not_in(going))
        )).scalars())
        released = asset_ids - still_used
        return list((await self.db.execute(select(PhotoAsset).where(PhotoAsset.id.in_(released)))).scalars()) if released else []

    async def preview(self, owner_id: uuid.UUID, project_id: uuid.UUID, payment_id: uuid.UUID) -> PaymentPurgePreview:
        payment = await self._payment(owner_id, project_id, payment_id)
        attachments = await self._attachments(payment.id)
        released = await self._released(attachments)
        annotations = 0
        if attachments:
            annotations = int((await self.db.execute(
                select(func.count()).select_from(PhotoAnnotation).where(PhotoAnnotation.attachment_id.in_([a.id for a in attachments]))
            )).scalar_one())
        tied = int((await self.db.execute(
            select(func.count()).select_from(ProjectPayment).where(ProjectPayment.settles_id == payment.id)
        )).scalar_one())
        return PaymentPurgePreview(
            target_id=payment.id, kind=payment.kind, title=payment.title, archived=payment.is_archived, tied_payments=tied,
            photos=len(attachments), photo_files=len(released),
            bytes=sum(a.byte_size + a.display_byte_size + a.thumbnail_byte_size for a in released), annotations=annotations,
        )

    # -- purge --------------------------------------------------------------------------

    async def purge(self, owner_id: uuid.UUID, project_id: uuid.UUID, payment_id: uuid.UUID) -> PaymentPurgeOutcome:
        await PhotoPurgeService(self.db, self.purger).retry_pending(owner_id)
        payment = await self._payment(owner_id, project_id, payment_id, lock=True)
        if not payment.is_archived:
            raise PaymentNotArchivedError("only an archived record can be deleted for good")
        attachments = await self._attachments(payment.id)
        released = await self._released(attachments)
        now = datetime.now(UTC)
        ledger = [
            PurgeLedger(
                owner_id=owner_id, project_id=project_id, asset_id=asset.id, kind="PHOTO", storage_name=asset.storage_name,
                storage_key_original=asset.storage_key_original, storage_key_display=asset.storage_key_display,
                storage_key_thumbnail=asset.storage_key_thumbnail, sha256=asset.sha256, byte_size=asset.byte_size,
                display_byte_size=asset.display_byte_size, thumbnail_byte_size=asset.thumbnail_byte_size,
                purged_at=now, storage_state=PENDING, backup_state=PENDING,
            )
            for asset in released
        ]
        attachment_ids = [a.id for a in attachments]
        released_ids = [a.id for a in released]
        try:
            if attachment_ids:
                await self.db.execute(delete(PhotoAnnotation).where(PhotoAnnotation.attachment_id.in_(attachment_ids)))
                await self.db.execute(delete(PhotoAttachment).where(PhotoAttachment.id.in_(attachment_ids)))
            if released_ids:
                await self.db.execute(delete(PhotoAsset).where(PhotoAsset.id.in_(released_ids)))
                self.db.add_all(ledger)
            # the payments that settled it keep their money and only lose the link (the database does the same by ON DELETE SET NULL)
            await self.db.execute(update(ProjectPayment).where(ProjectPayment.settles_id == payment.id).values(settles_id=None))
            await self.db.execute(delete(ProjectPayment).where(ProjectPayment.id == payment.id))
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise PaymentPurgeConflictError("the record changed while it was being deleted") from None

        await PhotoPurgeService(self.db, self.purger).retry_pending(owner_id)
        pending = await self.db.execute(
            select(func.count()).select_from(PurgeLedger)
            .where(PurgeLedger.project_id == project_id, PurgeLedger.asset_id.in_(released_ids or [uuid.UUID(int=0)]), PurgeLedger.storage_state == PENDING)
        )
        return PaymentPurgeOutcome(photo_files=len(ledger), storage_pending=int(pending.scalar_one()))
