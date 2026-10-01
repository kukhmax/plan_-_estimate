"""PhotoAttachment domain service (Stage 14C.2).

Canonical contract: docs/STAGE_14C_MEDIA_API_CONTRACT.md §4–§7, §12, §16, §18.

Scope: attachment persistence and rules only -- target-chain validation,
creation (committing, and a non-committing first-attachment path for the
14C.3 upload transaction), metadata patch, attachment archive/restore and
duplicate detection. No HTTP mapping, upload orchestration, presigning,
listing or asset archive (14C.3–14C.5). Exceptions are transport-neutral.

Rules:
- Stage 14C enables only PROJECT / ROOM / SURFACE / OPENING. INSPECTION /
  FINDING (14F) and WORK (14H) exist in the schema but are rejected here.
- Ownership: project -> owner; the asset must belong to the same owner AND
  project; targets are validated along the full chain to the project
  (room -> project, surface -> room -> project, opening -> surface -> room ->
  project). Foreign and missing resources raise the same not-found error.
- A normal new attachment requires a READY asset (PENDING/FAILED assets are
  invisible, like foreign ones). An archived READY asset may be attached
  (C12); the attachment stays hidden until the asset is restored.
- Archived parent targets are NOT rejected (C12: current project semantics).
- Caption: trimmed, empty -> NULL, at most 1000 characters. Category
  defaults to GENERAL, include_in_report to false, position >= 0.
- Duplicates (same asset + equivalent target among ACTIVE attachments) raise
  PhotoAttachmentDuplicateError; the partial unique indexes stay authoritative.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import (
    OpeningNotFoundError,
    PhotoAssetNotFoundError,
    PhotoAttachmentDuplicateError,
    PhotoAttachmentNotFoundError,
    PhotoAttachmentValidationError,
    PhotoContextNotSupportedError,
    RoomNotFoundError,
    SurfaceNotFoundError,
)
from app.domain.services.project_service import ProjectService
from app.models.opening import Opening
from app.models.photo_asset import PhotoAsset, PhotoAssetStatus
from app.models.photo_attachment import (
    MAX_CAPTION_LENGTH,
    PhotoAttachment,
    PhotoAttachmentContext,
    PhotoCategory,
)
from app.models.room import Room
from app.models.surface import Surface

# Contexts enabled by the Stage 14C API (C1).
SUPPORTED_CONTEXTS: frozenset[PhotoAttachmentContext] = frozenset(
    {
        PhotoAttachmentContext.PROJECT,
        PhotoAttachmentContext.ROOM,
        PhotoAttachmentContext.SURFACE,
        PhotoAttachmentContext.OPENING,
    }
)

# Target column required by each supported context (PROJECT needs none).
_REQUIRED_TARGET: dict[PhotoAttachmentContext, str | None] = {
    PhotoAttachmentContext.PROJECT: None,
    PhotoAttachmentContext.ROOM: "room_id",
    PhotoAttachmentContext.SURFACE: "surface_id",
    PhotoAttachmentContext.OPENING: "opening_id",
}

_UNSET: Any = object()


@dataclass(frozen=True)
class AttachmentTarget:
    """Leaf-only target of a Stage 14C attachment: exactly the id the
    context needs (none for PROJECT); the chain is resolved server-side."""

    context: PhotoAttachmentContext
    room_id: uuid.UUID | None = None
    surface_id: uuid.UUID | None = None
    opening_id: uuid.UUID | None = None

    def ids(self) -> dict[str, uuid.UUID | None]:
        return {"room_id": self.room_id, "surface_id": self.surface_id, "opening_id": self.opening_id}


def normalize_caption(caption: str | None) -> str | None:
    if caption is None:
        return None
    if not isinstance(caption, str):
        raise PhotoAttachmentValidationError("caption must be text")
    cleaned = caption.strip()
    if len(cleaned) > MAX_CAPTION_LENGTH:
        raise PhotoAttachmentValidationError(f"caption must be at most {MAX_CAPTION_LENGTH} characters")
    return cleaned or None


def _validate_position(position: int) -> int:
    if isinstance(position, bool) or not isinstance(position, int) or position < 0:
        raise PhotoAttachmentValidationError("position must be a non-negative integer")
    return position


def _validate_category(category: PhotoCategory | None) -> PhotoCategory:
    if category is None:
        return PhotoCategory.GENERAL
    if not isinstance(category, PhotoCategory):
        raise PhotoAttachmentValidationError("unknown photo category")
    return category


def _validate_include(include_in_report: bool) -> bool:
    if not isinstance(include_in_report, bool):
        raise PhotoAttachmentValidationError("include_in_report must be a boolean")
    return include_in_report


def validate_attachment_fields(
    category: PhotoCategory | None, caption: str | None, include_in_report: bool
) -> None:
    """Validate first-attachment metadata up front (contract §11 step 7), so
    an upload is rejected before identification or processing."""
    _validate_category(category)
    normalize_caption(caption)
    _validate_include(include_in_report)


class PhotoAttachmentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # -- target validation ------------------------------------------------

    def _check_target_shape(self, target: AttachmentTarget) -> None:
        if target.context not in SUPPORTED_CONTEXTS:
            raise PhotoContextNotSupportedError(
                f"photo context {target.context.value} is not supported in this stage"
            )
        required = _REQUIRED_TARGET[target.context]
        for column, value in target.ids().items():
            if column == required and value is None:
                raise PhotoAttachmentValidationError(f"{column} is required for {target.context.value}")
            if column != required and value is not None:
                raise PhotoAttachmentValidationError(f"{column} is not allowed for {target.context.value}")

    async def validate_target(
        self, owner_id: uuid.UUID, project_id: uuid.UUID, target: AttachmentTarget
    ) -> None:
        """Shape + full ownership chain. Foreign and missing targets raise the
        same not-found error; archived targets are accepted (C12)."""
        self._check_target_shape(target)
        await ProjectService(self.db).get_project(project_id, owner_id)
        context = target.context
        if context is PhotoAttachmentContext.ROOM:
            stmt = select(Room.id).where(Room.id == target.room_id, Room.project_id == project_id)
            if (await self.db.execute(stmt)).scalar_one_or_none() is None:
                raise RoomNotFoundError(f"Room {target.room_id} not found")
        elif context is PhotoAttachmentContext.SURFACE:
            stmt = (
                select(Surface.id)
                .join(Room, Surface.room_id == Room.id)
                .where(Surface.id == target.surface_id, Room.project_id == project_id)
            )
            if (await self.db.execute(stmt)).scalar_one_or_none() is None:
                raise SurfaceNotFoundError(f"Surface {target.surface_id} not found")
        elif context is PhotoAttachmentContext.OPENING:
            stmt = (
                select(Opening.id)
                .join(Surface, Opening.surface_id == Surface.id)
                .join(Room, Surface.room_id == Room.id)
                .where(Opening.id == target.opening_id, Room.project_id == project_id)
            )
            if (await self.db.execute(stmt)).scalar_one_or_none() is None:
                raise OpeningNotFoundError(f"Opening {target.opening_id} not found")

    # -- creation ---------------------------------------------------------

    async def create_attachment(
        self,
        *,
        owner_id: uuid.UUID,
        project_id: uuid.UUID,
        asset_id: uuid.UUID,
        target: AttachmentTarget,
        category: PhotoCategory | None = None,
        caption: str | None = None,
        include_in_report: bool = False,
        position: int = 0,
    ) -> PhotoAttachment:
        """Attach an existing READY asset (archived allowed, C12) to a
        supported context and COMMIT."""
        await self.validate_target(owner_id, project_id, target)
        asset = await self._get_asset(owner_id, project_id, asset_id)
        if asset.status is not PhotoAssetStatus.READY:
            raise PhotoAssetNotFoundError("photo asset not found")
        attachment = self._build(asset, target, category, caption, include_in_report, position)
        if await self._active_duplicate_exists(attachment):
            raise PhotoAttachmentDuplicateError("an equivalent active attachment already exists")
        self.db.add(attachment)
        await self._commit_or_duplicate(attachment)
        await self.db.refresh(attachment)
        return attachment

    async def add_initial_attachment(
        self,
        *,
        asset: PhotoAsset,
        owner_id: uuid.UUID,
        target: AttachmentTarget,
        category: PhotoCategory | None = None,
        caption: str | None = None,
        include_in_report: bool = False,
    ) -> PhotoAttachment:
        """First attachment of a freshly added PENDING asset, inside the
        caller's transaction (contract §11 step 10). Flushes, never commits.
        The asset is new, so no duplicate can exist."""
        if asset.owner_id != owner_id or asset.status is not PhotoAssetStatus.PENDING:
            raise PhotoAssetNotFoundError("photo asset not found")
        await self.validate_target(owner_id, asset.project_id, target)
        attachment = self._build(asset, target, category, caption, include_in_report, 0)
        self.db.add(attachment)
        await self.db.flush()
        return attachment

    def _build(
        self,
        asset: PhotoAsset,
        target: AttachmentTarget,
        category: PhotoCategory | None,
        caption: str | None,
        include_in_report: bool,
        position: int,
    ) -> PhotoAttachment:
        return PhotoAttachment(
            asset_id=asset.id,
            project_id=asset.project_id,
            context=target.context,
            room_id=target.room_id,
            surface_id=target.surface_id,
            opening_id=target.opening_id,
            category=_validate_category(category),
            caption=normalize_caption(caption),
            include_in_report=_validate_include(include_in_report),
            position=_validate_position(position),
        )

    # -- read ---------------------------------------------------------------

    async def get_attachment(
        self, owner_id: uuid.UUID, project_id: uuid.UUID, attachment_id: uuid.UUID
    ) -> PhotoAttachment:
        """Owner/project-scoped attachment of a READY asset (archived states
        included). Foreign, missing and not-READY -> the same not-found."""
        stmt = (
            select(PhotoAttachment)
            .join(PhotoAsset, PhotoAttachment.asset_id == PhotoAsset.id)
            .where(
                PhotoAttachment.id == attachment_id,
                PhotoAttachment.project_id == project_id,
                PhotoAsset.project_id == project_id,
                PhotoAsset.owner_id == owner_id,
                PhotoAsset.status == PhotoAssetStatus.READY,
            )
        )
        attachment = (await self.db.execute(stmt)).scalar_one_or_none()
        if attachment is None:
            raise PhotoAttachmentNotFoundError("photo attachment not found")
        return attachment

    # -- metadata -----------------------------------------------------------

    async def update_attachment(
        self,
        owner_id: uuid.UUID,
        project_id: uuid.UUID,
        attachment_id: uuid.UUID,
        *,
        caption: Any = _UNSET,
        category: Any = _UNSET,
        include_in_report: Any = _UNSET,
        position: Any = _UNSET,
    ) -> PhotoAttachment:
        """Patch editable metadata; omitted fields are unchanged. Context and
        target are immutable (archive + attach elsewhere instead)."""
        attachment = await self.get_attachment(owner_id, project_id, attachment_id)
        if caption is not _UNSET:
            attachment.caption = normalize_caption(caption)
        if category is not _UNSET:
            if category is None:
                raise PhotoAttachmentValidationError("category cannot be empty")
            attachment.category = _validate_category(category)
        if include_in_report is not _UNSET:
            attachment.include_in_report = _validate_include(include_in_report)
        if position is not _UNSET:
            attachment.position = _validate_position(position)
        await self.db.commit()
        await self.db.refresh(attachment)
        return attachment

    # -- archive / restore ----------------------------------------------------

    async def archive_attachment(
        self, owner_id: uuid.UUID, project_id: uuid.UUID, attachment_id: uuid.UUID
    ) -> PhotoAttachment:
        """Idempotent; the asset and its objects are untouched."""
        attachment = await self.get_attachment(owner_id, project_id, attachment_id)
        if attachment.archived_at is None:
            attachment.archived_at = datetime.now(timezone.utc)
            await self.db.commit()
            await self.db.refresh(attachment)
        return attachment

    async def restore_attachment(
        self, owner_id: uuid.UUID, project_id: uuid.UUID, attachment_id: uuid.UUID
    ) -> PhotoAttachment:
        """Idempotent; fails with PhotoAttachmentDuplicateError when an
        equivalent attachment became active in the meantime."""
        attachment = await self.get_attachment(owner_id, project_id, attachment_id)
        if attachment.archived_at is None:
            return attachment
        if await self._active_duplicate_exists(attachment):
            raise PhotoAttachmentDuplicateError("an equivalent active attachment already exists")
        attachment.archived_at = None
        await self._commit_or_duplicate(attachment)
        await self.db.refresh(attachment)
        return attachment

    # -- helpers ----------------------------------------------------------------

    async def _get_asset(
        self, owner_id: uuid.UUID, project_id: uuid.UUID, asset_id: uuid.UUID
    ) -> PhotoAsset:
        stmt = select(PhotoAsset).where(
            PhotoAsset.id == asset_id,
            PhotoAsset.owner_id == owner_id,
            PhotoAsset.project_id == project_id,
        )
        asset = (await self.db.execute(stmt)).scalar_one_or_none()
        if asset is None:
            raise PhotoAssetNotFoundError("photo asset not found")
        return asset

    async def _active_duplicate_exists(self, attachment: PhotoAttachment) -> bool:
        return await self._duplicate_exists(_DuplicateKey.of(attachment))

    async def _duplicate_exists(self, key: "_DuplicateKey") -> bool:
        """Mirror of the per-context partial unique indexes (contract §6)."""
        stmt = select(PhotoAttachment.id).where(
            PhotoAttachment.asset_id == key.asset_id,
            PhotoAttachment.context == key.context,
            PhotoAttachment.archived_at.is_(None),
            PhotoAttachment.room_id.is_(None) if key.room_id is None else PhotoAttachment.room_id == key.room_id,
            PhotoAttachment.surface_id.is_(None)
            if key.surface_id is None
            else PhotoAttachment.surface_id == key.surface_id,
            PhotoAttachment.opening_id.is_(None)
            if key.opening_id is None
            else PhotoAttachment.opening_id == key.opening_id,
        )
        if key.exclude_id is not None:
            stmt = stmt.where(PhotoAttachment.id != key.exclude_id)
        return (await self.db.execute(stmt.limit(1))).first() is not None

    async def _commit_or_duplicate(self, attachment: PhotoAttachment) -> None:
        """Commit; a unique-index violation from a concurrent writer is
        reported as the domain duplicate error (the index is authoritative).
        The key is captured first: rollback expires the instance."""
        key = _DuplicateKey.of(attachment)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            if await self._duplicate_exists(key):
                raise PhotoAttachmentDuplicateError(
                    "an equivalent active attachment already exists"
                ) from None
            raise


@dataclass(frozen=True)
class _DuplicateKey:
    asset_id: uuid.UUID
    context: PhotoAttachmentContext
    room_id: uuid.UUID | None
    surface_id: uuid.UUID | None
    opening_id: uuid.UUID | None
    exclude_id: uuid.UUID | None

    @classmethod
    def of(cls, attachment: PhotoAttachment) -> "_DuplicateKey":
        return cls(
            asset_id=attachment.asset_id,
            context=attachment.context,
            room_id=attachment.room_id,
            surface_id=attachment.surface_id,
            opening_id=attachment.opening_id,
            exclude_id=attachment.id,
        )
