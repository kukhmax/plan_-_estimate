"""PhotoAsset persistence primitives (Stage 14B.4).

Only the persistence boundary: create a PENDING asset from locally processed
media, read it owner-scoped, apply upload state transitions, and list rows
for integrity tooling. No object-storage call happens here and no storage
adapter is coupled to the model; the upload workflow that orders "insert
PENDING -> put objects -> READY/FAILED" is Stage 14C (14A §8).

Storage keys are always built by the single key builder from the asset id
and the decoded format, so a row can never carry keys that disagree with its
identity. URLs are never persisted.
"""

import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import (
    PhotoAssetAlreadyExistsError,
    PhotoAssetNotFoundError,
    PhotoAssetStateError,
    PhotoAssetValidationError,
)
from app.domain.photos.image_processing import ProcessedImage
from app.domain.photos.keys import ORIGINAL_CONTENT_TYPES, build_photo_object_keys
from app.domain.services.project_service import ProjectService
from app.models.photo_asset import PhotoAsset, PhotoAssetStatus, PhotoContentType

SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")
MAX_STORAGE_NAME_LENGTH = 40
MAX_FILENAME_LENGTH = 255

# Upload state machine (14A §8). READY is terminal.
ALLOWED_TRANSITIONS: dict[PhotoAssetStatus, frozenset[PhotoAssetStatus]] = {
    PhotoAssetStatus.PENDING: frozenset({PhotoAssetStatus.READY, PhotoAssetStatus.FAILED}),
    PhotoAssetStatus.FAILED: frozenset({PhotoAssetStatus.PENDING}),
    PhotoAssetStatus.READY: frozenset(),
}


def sanitize_original_filename(name: str | None) -> str | None:
    """Display-only metadata: keep the last path segment, drop control
    characters, trim, cap length. Never used for storage identity."""
    if name is None:
        return None
    base = re.split(r"[\\/]", name)[-1]
    cleaned = "".join(ch for ch in base if unicodedata.category(ch)[0] != "C").strip()
    return cleaned[:MAX_FILENAME_LENGTH] or None


@dataclass(frozen=True)
class PhotoAssetSnapshot:
    """Read-only copy of a PhotoAsset row for integrity tooling."""

    id: uuid.UUID
    status: PhotoAssetStatus
    storage_name: str
    storage_key_original: str
    storage_key_display: str
    storage_key_thumbnail: str
    byte_size: int
    display_byte_size: int
    thumbnail_byte_size: int
    sha256: str
    created_at: datetime

    @classmethod
    def from_model(cls, asset: PhotoAsset) -> "PhotoAssetSnapshot":
        return cls(
            id=asset.id,
            status=asset.status,
            storage_name=asset.storage_name,
            storage_key_original=asset.storage_key_original,
            storage_key_display=asset.storage_key_display,
            storage_key_thumbnail=asset.storage_key_thumbnail,
            byte_size=asset.byte_size,
            display_byte_size=asset.display_byte_size,
            thumbnail_byte_size=asset.thumbnail_byte_size,
            sha256=asset.sha256,
            created_at=asset.created_at,
        )


class PhotoAssetService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_pending(
        self,
        *,
        asset_id: uuid.UUID,
        owner_id: uuid.UUID,
        project_id: uuid.UUID,
        storage_name: str,
        processed: ProcessedImage,
        original_filename: str | None = None,
    ) -> PhotoAsset:
        """Insert a PENDING asset with complete metadata (processing already
        happened). Verifies the project belongs to the owner."""
        await ProjectService(self.db).get_project(project_id, owner_id)
        try:
            keys = build_photo_object_keys(asset_id, processed.format)
        except ValueError as exc:
            raise PhotoAssetValidationError(str(exc)) from None
        self._validate(storage_name, processed)
        if await self.db.get(PhotoAsset, asset_id) is not None:
            raise PhotoAssetAlreadyExistsError("photo asset already exists")

        asset = PhotoAsset(
            id=asset_id,
            owner_id=owner_id,
            project_id=project_id,
            status=PhotoAssetStatus.PENDING,
            storage_name=storage_name,
            storage_key_original=keys.original,
            storage_key_display=keys.display,
            storage_key_thumbnail=keys.thumbnail,
            content_type=PhotoContentType(ORIGINAL_CONTENT_TYPES[processed.format]),
            byte_size=processed.byte_size,
            display_byte_size=processed.display.byte_size,
            thumbnail_byte_size=processed.thumbnail.byte_size,
            width=processed.width,
            height=processed.height,
            sha256=processed.sha256,
            original_filename=sanitize_original_filename(original_filename),
            captured_at=processed.captured_at,  # camera-local, no timezone
            uploaded_at=datetime.now(timezone.utc),
        )
        self.db.add(asset)
        await self.db.commit()
        await self.db.refresh(asset)
        return asset

    async def get_for_owner(self, asset_id: uuid.UUID, owner_id: uuid.UUID) -> PhotoAsset:
        stmt = select(PhotoAsset).where(PhotoAsset.id == asset_id, PhotoAsset.owner_id == owner_id)
        asset = (await self.db.execute(stmt)).scalar_one_or_none()
        if asset is None:
            raise PhotoAssetNotFoundError("photo asset not found")
        return asset

    async def transition(
        self, asset_id: uuid.UUID, owner_id: uuid.UUID, to_status: PhotoAssetStatus
    ) -> PhotoAsset:
        """Apply one upload state transition (PENDING->READY|FAILED,
        FAILED->PENDING). Metadata never changes; READY is terminal."""
        asset = await self.get_for_owner(asset_id, owner_id)
        if to_status not in ALLOWED_TRANSITIONS[asset.status]:
            raise PhotoAssetStateError(f"cannot move photo asset from {asset.status.value} to {to_status.value}")
        asset.status = to_status
        await self.db.commit()
        await self.db.refresh(asset)
        return asset

    async def list_for_integrity(self, storage_name: str | None = None) -> list[PhotoAssetSnapshot]:
        """All assets (every owner, every status, archived included) for
        read-only integrity tooling; optionally one logical store only."""
        stmt = select(PhotoAsset).order_by(PhotoAsset.created_at, PhotoAsset.id)
        if storage_name is not None:
            stmt = stmt.where(PhotoAsset.storage_name == storage_name)
        rows = (await self.db.execute(stmt)).scalars().all()
        return [PhotoAssetSnapshot.from_model(row) for row in rows]

    @staticmethod
    def _validate(storage_name: str, processed: ProcessedImage) -> None:
        if not storage_name or not storage_name.strip() or len(storage_name) > MAX_STORAGE_NAME_LENGTH:
            raise PhotoAssetValidationError("storage_name must be 1-40 characters")
        if not SHA256_HEX.match(processed.sha256 or ""):
            raise PhotoAssetValidationError("sha256 must be 64 lowercase hex characters")
        sizes = (processed.byte_size, processed.display.byte_size, processed.thumbnail.byte_size)
        if any(size <= 0 for size in sizes):
            raise PhotoAssetValidationError("byte sizes must be positive")
        if processed.width <= 0 or processed.height <= 0:
            raise PhotoAssetValidationError("dimensions must be positive")
        if processed.captured_at is not None and processed.captured_at.tzinfo is not None:
            raise PhotoAssetValidationError("captured_at must be camera-local (no timezone)")
