"""PhotoAsset persistence primitives (Stage 14B.4).

Only the persistence boundary: create a PENDING asset from locally processed
media, read it owner-scoped, apply upload state transitions, and list rows
for integrity tooling. No object-storage call happens here and no storage
adapter is coupled to the model; the upload workflow that orders "insert
PENDING -> put objects -> READY/FAILED" is Stage 14C (14A §8).

Storage keys are always built by the single key builder from the asset id
and the decoded format, so a row can never carry keys that disagree with its
identity. URLs are never persisted.

Stage 14C.2 refinements (docs/STAGE_14C_MEDIA_API_CONTRACT.md C10):
- `add_pending` is the non-committing creation path: it validates, adds and
  flushes the PENDING row but never commits, so the upload service can commit
  the asset together with its first attachment. `create_pending` keeps its
  original committing behaviour on top of it.
- Status transitions are compare-and-set (`UPDATE ... WHERE id AND status =
  :expected`); a stale caller can never move READY backwards.
"""

import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import (
    PhotoAssetAlreadyExistsError,
    PhotoAssetNotFoundError,
    PhotoAssetStateError,
    PhotoAssetTransitionConflictError,
    PhotoAssetValidationError,
)
from app.domain.photos.image_processing import ProcessedImage
from app.domain.photos.keys import ORIGINAL_CONTENT_TYPES, build_photo_object_keys
from app.domain.services.project_service import ProjectService
from app.models.photo_asset import (
    PhotoAsset,
    PhotoAssetStatus,
    PhotoCaptureSource,
    PhotoContentType,
)

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
        capture_source: PhotoCaptureSource | None = None,
    ) -> PhotoAsset:
        """Insert and COMMIT a PENDING asset with complete metadata (processing
        already happened). Verifies the project belongs to the owner."""
        asset = await self.add_pending(
            asset_id=asset_id,
            owner_id=owner_id,
            project_id=project_id,
            storage_name=storage_name,
            processed=processed,
            original_filename=original_filename,
            capture_source=capture_source,
        )
        await self.db.commit()
        await self.db.refresh(asset)
        return asset

    async def add_pending(
        self,
        *,
        asset_id: uuid.UUID,
        owner_id: uuid.UUID,
        project_id: uuid.UUID,
        storage_name: str,
        processed: ProcessedImage,
        original_filename: str | None = None,
        capture_source: PhotoCaptureSource | None = None,
    ) -> PhotoAsset:
        """Validate and add a PENDING asset inside the caller's transaction.

        Flushes (so constraint violations surface here) but NEVER commits:
        the caller owns the transaction and commits the asset together with
        its first attachment, or rolls both back. A concurrent insert of the
        same id surfaces as an IntegrityError on flush; the caller rolls back
        and re-reads (contract §11 step 10)."""
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
            capture_source=capture_source,  # client-declared, informational (14E.2, D11)
            uploaded_at=datetime.now(timezone.utc),
        )
        self.db.add(asset)
        await self.db.flush()
        return asset

    async def get_for_owner(self, asset_id: uuid.UUID, owner_id: uuid.UUID) -> PhotoAsset:
        stmt = select(PhotoAsset).where(PhotoAsset.id == asset_id, PhotoAsset.owner_id == owner_id)
        asset = (await self.db.execute(stmt)).scalar_one_or_none()
        if asset is None:
            raise PhotoAssetNotFoundError("photo asset not found")
        return asset

    async def get_ready(self, asset_id: uuid.UUID, owner_id: uuid.UUID, project_id: uuid.UUID) -> PhotoAsset:
        """Public-read lookup (Stage 14C.5, contract §16): id AND owner AND
        project AND READY. Foreign, missing, other-project, PENDING and FAILED
        assets raise the same PhotoAssetNotFoundError."""
        stmt = select(PhotoAsset).where(
            PhotoAsset.id == asset_id,
            PhotoAsset.owner_id == owner_id,
            PhotoAsset.project_id == project_id,
            PhotoAsset.status == PhotoAssetStatus.READY,
        )
        asset = (await self.db.execute(stmt)).scalar_one_or_none()
        if asset is None:
            raise PhotoAssetNotFoundError("photo asset not found")
        return asset

    async def archive(self, asset_id: uuid.UUID, owner_id: uuid.UUID, project_id: uuid.UUID) -> PhotoAsset:
        """Archive a READY asset (contract §18): sets archived_at only. No
        attachment cascade, no status change, no storage operation. Idempotent."""
        asset = await self.get_ready(asset_id, owner_id, project_id)
        if asset.archived_at is None:
            asset.archived_at = datetime.now(timezone.utc)
            await self.db.commit()
            await self.db.refresh(asset)
        return asset

    async def restore(self, asset_id: uuid.UUID, owner_id: uuid.UUID, project_id: uuid.UUID) -> PhotoAsset:
        """Clear archived_at only; attachment archive states stay as they
        were. Idempotent."""
        asset = await self.get_ready(asset_id, owner_id, project_id)
        if asset.archived_at is not None:
            asset.archived_at = None
            await self.db.commit()
            await self.db.refresh(asset)
        return asset

    async def transition(
        self, asset_id: uuid.UUID, owner_id: uuid.UUID, to_status: PhotoAssetStatus
    ) -> PhotoAsset:
        """Apply one upload state transition (PENDING->READY|FAILED,
        FAILED->PENDING) from the status currently read. Metadata never
        changes; READY is terminal. The write is compare-and-set, so a stale
        read loses with PhotoAssetTransitionConflictError instead of
        overwriting a parallel update."""
        asset = await self.get_for_owner(asset_id, owner_id)
        return await self.compare_and_set_status(
            asset_id, owner_id, expected=asset.status, target=to_status
        )

    async def compare_and_set_status(
        self,
        asset_id: uuid.UUID,
        owner_id: uuid.UUID,
        *,
        expected: PhotoAssetStatus,
        target: PhotoAssetStatus,
    ) -> PhotoAsset:
        """Atomically move the asset from `expected` to `target` and commit.

        `UPDATE photo_assets SET status=:target WHERE id=:id AND
        owner_id=:owner AND status=:expected`; the affected-row count decides.
        0 rows -> the current row is reloaded: missing/foreign ->
        PhotoAssetNotFoundError, otherwise PhotoAssetTransitionConflictError
        carrying the status actually found (e.g. READY written by a parallel
        request). READY is never moved backwards because no transition leaves
        READY and the WHERE clause pins the expected status."""
        if target not in ALLOWED_TRANSITIONS[expected]:
            raise PhotoAssetStateError(f"cannot move photo asset from {expected.value} to {target.value}")
        stmt = (
            update(PhotoAsset)
            .where(
                PhotoAsset.id == asset_id,
                PhotoAsset.owner_id == owner_id,
                PhotoAsset.status == expected,
            )
            .values(status=target, updated_at=datetime.now(timezone.utc))
            .execution_options(synchronize_session=False)
        )
        result = await self.db.execute(stmt)
        affected = result.rowcount  # type: ignore[attr-defined]
        await self.db.commit()
        current = await self._reload(asset_id, owner_id)
        if affected != 1:
            raise PhotoAssetTransitionConflictError(
                f"photo asset is no longer {expected.value}", current_status=current.status
            )
        return current

    async def _reload(self, asset_id: uuid.UUID, owner_id: uuid.UUID) -> PhotoAsset:
        """Owner-scoped read that overwrites any stale identity-map state."""
        stmt = (
            select(PhotoAsset)
            .where(PhotoAsset.id == asset_id, PhotoAsset.owner_id == owner_id)
            .execution_options(populate_existing=True)
        )
        asset = (await self.db.execute(stmt)).scalar_one_or_none()
        if asset is None:
            raise PhotoAssetNotFoundError("photo asset not found")
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
