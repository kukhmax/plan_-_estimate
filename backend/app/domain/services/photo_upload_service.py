"""Photo upload orchestration (Stage 14C.3).

Canonical contract: docs/STAGE_14C_MEDIA_API_CONTRACT.md §11–§15, §19, C8–C11,
C16, R-1.

Scope: everything AFTER bounded reception. The caller (14C.4 HTTP layer)
has already authenticated, enforced the request/byte limits and copied the
file part into a `pe-photo-` workspace; it passes the path of exactly those
bytes plus parsed metadata. No HTTP, multipart, presigning or listing here.

Algorithm (contract §11):
- Gate (§19): uploads disabled -> PhotoUploadsDisabledError before any
  processing, row or object write; applies to new, replay and resume alike.
- Step 7: canonical UUIDv4 upload_id, project ownership, attachment fields,
  target chain, SHA-256 of exactly the received bytes.
- Step 8 identification: no row -> new; foreign owner or other project ->
  PhotoUploadIdConflictError WITHOUT any SHA comparison; own + same project
  + different SHA -> the same error; READY -> replay (archived included,
  request metadata ignored, C16); PENDING/FAILED -> resume.
- New (steps 9-11): inside the processing slot run the 14B pipeline, check
  the logical quota and commit the PENDING asset together with its first
  attachment in ONE transaction; then write-once PUT original, display,
  thumbnail; then compare-and-set PENDING -> READY.
- Resume (steps 12-16): FAILED -> PENDING by CAS; HEAD each expected key;
  wrong size -> FAILED + MediaObjectConflict; missing original -> PUT the
  SHA-verified retry bytes; missing derivative -> regenerate from those
  bytes inside the slot, must equal the recorded format/dimensions/sizes,
  else FAILED + PhotoUploadResumeMismatchError; never quota-rejected.
- Finalize (step 17): CAS PENDING -> READY. A lost race re-reads: READY ->
  concurrently finalized (200); otherwise back to step 8. Storage errors
  (PUT and resume HEAD) and resume mismatches -> CAS to FAILED and the error
  is re-raised; if that CAS loses to READY, the READY outcome stands.

Convergence without a retry count (owner review of 14C.3). Step 8 is
re-entered (`_Reidentify`) only after a transition COMMITTED BY ANOTHER
REQUEST was observed, always in a fresh transaction (every CAS commits
before its reload; the PK path rolls back):
  1. PK collision on the step-10 insert -> another request created the row.
     Rows are never deleted, so the "no row" branch is never re-entered.
  2. Lost FAILED -> PENDING -> another request claimed recovery.
  3. Lost PENDING -> READY with the row not READY -> another request
     committed PENDING -> FAILED.
A request alone can never loop. The only way back to FAILED is a won
PENDING -> FAILED, and the request that wins it ends at once (`_fail`
raises), so every concurrent request makes the row FAILED at most once and
FAILED -> PENDING claims are bounded by that. The number of re-reads of one
request is therefore bounded by the number of other requests concurrently
using the same upload_id; the loop below terminates for any finite set of
requests and has no artificial cap.

The database and object storage are NOT atomic. Objects are only written
after the PENDING row is committed, and nothing is ever deleted: a later DB
failure leaves objects that the integrity tool reports as PENDING_INCOMPLETE
or FAILED_RELATED, never ORPHAN_CANDIDATE.
"""

import hmac
import logging
import uuid
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

import anyio
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import (
    MediaObjectConflict,
    MediaStorageError,
    PhotoAssetAlreadyExistsError,
    PhotoAssetTransitionConflictError,
    PhotoStorageQuotaExceededError,
    PhotoUploadIdConflictError,
    PhotoUploadMalformedError,
    PhotoUploadResumeMismatchError,
    PhotoUploadsDisabledError,
    PhotoValidationError,
)
from app.domain.photos.image_processing import ImageProcessor, ProcessedImage, hash_file_bounded
from app.domain.photos.keys import DERIVATIVE_CONTENT_TYPE, ORIGINAL_CONTENT_TYPES
from app.domain.photos.temp import photo_workspace
from app.domain.services.media_storage import MediaStorage
from app.domain.services.photo_asset_service import PhotoAssetService
from app.domain.services.photo_attachment_service import (
    AttachmentTarget,
    PhotoAttachmentService,
    validate_attachment_fields,
)
from app.domain.services.photo_quota import (
    PhotoStorageState,
    exceeds_soft_cap,
    logical_usage_bytes,
    storage_state,
)
from app.domain.services.project_service import ProjectService
from app.models.photo_asset import PhotoAsset, PhotoAssetStatus, PhotoCaptureSource
from app.models.photo_attachment import PhotoAttachment, PhotoCategory

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)

P, R, F = PhotoAssetStatus.PENDING, PhotoAssetStatus.READY, PhotoAssetStatus.FAILED


@dataclass(frozen=True)
class PhotoUploadConfig:
    uploads_enabled: bool
    storage_backend: str
    storage_name: str
    max_upload_bytes: int
    warning_bytes: int
    soft_cap_bytes: int
    temp_dir: str

    @classmethod
    def from_settings(cls, settings: "Settings") -> "PhotoUploadConfig":
        return cls(
            uploads_enabled=settings.PHOTO_UPLOADS_ENABLED,
            storage_backend=settings.MEDIA_STORAGE_BACKEND,
            storage_name=settings.MEDIA_STORAGE_NAME,
            max_upload_bytes=settings.PHOTO_MAX_UPLOAD_BYTES,
            warning_bytes=settings.PHOTO_STORAGE_WARNING_BYTES,
            soft_cap_bytes=settings.PHOTO_STORAGE_SOFT_CAP_BYTES,
            temp_dir=settings.PHOTO_TEMP_DIR,
        )

    @property
    def uploads_available(self) -> bool:
        return self.uploads_enabled and self.storage_backend == "s3"


@dataclass(frozen=True)
class PhotoUploadRequest:
    """Already-received bounded upload: `original_path` holds exactly the
    client's file bytes (inside the caller's workspace, which it removes)."""

    owner_id: uuid.UUID
    project_id: uuid.UUID
    upload_id: str
    target: AttachmentTarget
    original_path: Path
    category: PhotoCategory | None = None
    caption: str | None = None
    include_in_report: bool = False
    original_filename: str | None = None
    # Client-declared entry path (14E.2, D11 = A): informational, stored on the FIRST upload only;
    # a replay / resume of an existing asset never changes it (C16).
    capture_source: PhotoCaptureSource | None = None


class PhotoUploadOutcome(StrEnum):
    CREATED = "CREATED"  # new asset finalized by this request (HTTP 201)
    RESUMED = "RESUMED"  # PENDING/FAILED asset finalized by this request (201)
    REPLAYED = "REPLAYED"  # asset was already READY (200)
    CONCURRENTLY_FINALIZED = "CONCURRENTLY_FINALIZED"  # a parallel request finalized it (200)

    @property
    def created(self) -> bool:
        return self in (PhotoUploadOutcome.CREATED, PhotoUploadOutcome.RESUMED)


@dataclass(frozen=True)
class PhotoUploadResult:
    outcome: PhotoUploadOutcome
    asset: PhotoAsset  # always READY
    # The asset's first attachment (earliest created_at, id), any archive state.
    attachment: PhotoAttachment | None
    storage_state: PhotoStorageState


class _Reidentify(Exception):
    """Internal: another request changed the row; return to step 8."""


class _ConcurrentlyFinalized(Exception):
    """Internal: while this request failed, a parallel one finalized READY."""


def parse_upload_id(raw: str) -> uuid.UUID:
    """Canonical lowercase UUIDv4 string only (contract §9)."""
    try:
        value = uuid.UUID(raw) if isinstance(raw, str) else None
    except ValueError:
        value = None
    if value is None or value.version != 4 or str(value) != raw:
        raise PhotoUploadMalformedError("upload_id must be a canonical lowercase UUIDv4")
    return value


def same_original(stored_sha256: str, retry_sha256: str) -> bool:
    """Content identity of retry bytes. Only ever called after the owner and
    project matched (contract §14: never compare against a foreign asset)."""
    return hmac.compare_digest(stored_sha256, retry_sha256)


def matches_record(asset: PhotoAsset, processed: ProcessedImage) -> bool:
    """Deterministic-regeneration check for resume (contract §13): the
    regenerated format, dimensions and derivative sizes equal the row."""
    return (
        ORIGINAL_CONTENT_TYPES[processed.format] == asset.content_type.value
        and processed.byte_size == asset.byte_size
        and processed.width == asset.width
        and processed.height == asset.height
        and processed.display.byte_size == asset.display_byte_size
        and processed.thumbnail.byte_size == asset.thumbnail_byte_size
    )


class PhotoUploadService:
    def __init__(
        self,
        db: AsyncSession,
        storage: MediaStorage,
        processor: ImageProcessor,
        config: PhotoUploadConfig,
    ) -> None:
        self.db = db
        self.storage = storage
        self.processor = processor
        self.config = config
        self.assets = PhotoAssetService(db)
        self.attachments = PhotoAttachmentService(db)

    async def upload(self, request: PhotoUploadRequest) -> PhotoUploadResult:
        if not self.config.uploads_available:
            raise PhotoUploadsDisabledError("photo uploads are disabled")
        upload_id = parse_upload_id(request.upload_id)
        await ProjectService(self.db).get_project(request.project_id, request.owner_id)
        validate_attachment_fields(request.category, request.caption, request.include_in_report)
        await self.attachments.validate_target(request.owner_id, request.project_id, request.target)
        retry_sha256, _ = await anyio.to_thread.run_sync(
            hash_file_bounded, Path(request.original_path), self.config.max_upload_bytes
        )

        while True:  # step 8; re-entered only after another request's transition (module docstring)
            asset = await self._read_asset(upload_id)
            try:
                if asset is None:
                    return await self._new_upload(request, upload_id)
                if asset.owner_id != request.owner_id or asset.project_id != request.project_id:
                    raise PhotoUploadIdConflictError()
                if not same_original(asset.sha256, retry_sha256):
                    raise PhotoUploadIdConflictError()
                if asset.status is R:
                    return await self._result(PhotoUploadOutcome.REPLAYED, asset)
                return await self._resume(request, asset)
            except _Reidentify:
                continue
            except _ConcurrentlyFinalized:
                return await self._result(
                    PhotoUploadOutcome.CONCURRENTLY_FINALIZED, await self._read_owned_id(upload_id, request.owner_id)
                )

    # -- new upload (steps 9-11) ---------------------------------------------

    async def _new_upload(self, request: PhotoUploadRequest, upload_id: uuid.UUID) -> PhotoUploadResult:
        with photo_workspace(self.config.temp_dir) as workspace:
            async with self.processor.slot():
                processed = await self.processor.run_in_slot(request.original_path, workspace)
                usage = await logical_usage_bytes(self.db, request.owner_id)
                new_bytes = processed.byte_size + processed.display.byte_size + processed.thumbnail.byte_size
                if exceeds_soft_cap(usage, new_bytes, soft_cap_bytes=self.config.soft_cap_bytes):
                    raise PhotoStorageQuotaExceededError("photo storage quota exceeded")
                asset = await self._insert_pending(request, upload_id, processed)
            await self._put_all(
                asset,
                [
                    (asset.storage_key_original, request.original_path, ORIGINAL_CONTENT_TYPES[processed.format]),
                    (asset.storage_key_display, processed.display.path, DERIVATIVE_CONTENT_TYPE),
                    (asset.storage_key_thumbnail, processed.thumbnail.path, DERIVATIVE_CONTENT_TYPE),
                ],
            )
        return await self._finalize(asset, PhotoUploadOutcome.CREATED)

    async def _insert_pending(
        self, request: PhotoUploadRequest, upload_id: uuid.UUID, processed: ProcessedImage
    ) -> PhotoAsset:
        """Step 10: the asset and its first attachment in one transaction."""
        try:
            asset = await self.assets.add_pending(
                asset_id=upload_id,
                owner_id=request.owner_id,
                project_id=request.project_id,
                storage_name=self.config.storage_name,
                processed=processed,
                original_filename=request.original_filename,
                capture_source=request.capture_source,
            )
            await self.attachments.add_initial_attachment(
                asset=asset,
                owner_id=request.owner_id,
                target=request.target,
                category=request.category,
                caption=request.caption,
                include_in_report=request.include_in_report,
            )
            await self.db.commit()
        except (PhotoAssetAlreadyExistsError, IntegrityError):
            # A concurrent request took the id first: re-read (contract §11 step 10).
            await self.db.rollback()
            raise _Reidentify() from None
        except BaseException:
            await self.db.rollback()
            raise
        logger.info("photo asset %s PENDING (owner %s, %d bytes)", upload_id, request.owner_id, processed.byte_size)
        return asset

    # -- resume (steps 12-16) -------------------------------------------------

    async def _resume(self, request: PhotoUploadRequest, asset: PhotoAsset) -> PhotoUploadResult:
        if asset.status is F:
            try:
                asset = await self.assets.compare_and_set_status(asset.id, request.owner_id, expected=F, target=P)
            except PhotoAssetTransitionConflictError:
                raise _Reidentify() from None
        expected = [
            ("original", asset.storage_key_original, asset.byte_size),
            ("display", asset.storage_key_display, asset.display_byte_size),
            ("thumbnail", asset.storage_key_thumbnail, asset.thumbnail_byte_size),
        ]
        missing: set[str] = set()
        try:
            for variant, key, size in expected:
                info = await self.storage.head_object(key)
                if info is None:
                    missing.add(variant)
                elif info.size != size:
                    raise MediaObjectConflict("existing object has an unexpected size")
        except MediaStorageError as exc:
            return await self._fail(asset, exc)

        with photo_workspace(self.config.temp_dir) as workspace:
            items: list[tuple[str, Path, str]] = []
            if "original" in missing:
                # Permitted only because the retry bytes' SHA-256 equals the stored sha256.
                items.append((asset.storage_key_original, request.original_path, asset.content_type.value))
            if missing & {"display", "thumbnail"}:
                processed = await self._regenerate(request.original_path, workspace)
                if processed is None or not matches_record(asset, processed):
                    return await self._fail(
                        asset, PhotoUploadResumeMismatchError("regenerated derivatives do not match the record")
                    )
                if "display" in missing:
                    items.append((asset.storage_key_display, processed.display.path, DERIVATIVE_CONTENT_TYPE))
                if "thumbnail" in missing:
                    items.append((asset.storage_key_thumbnail, processed.thumbnail.path, DERIVATIVE_CONTENT_TYPE))
            await self._put_all(asset, items)
        return await self._finalize(asset, PhotoUploadOutcome.RESUMED)

    async def _regenerate(self, source: Path, workspace: Path) -> ProcessedImage | None:
        """Re-run the full pipeline on the SHA-verified retry bytes. A
        rejection means the recorded derivatives cannot be regenerated."""
        async with self.processor.slot():
            try:
                return await self.processor.run_in_slot(source, workspace)
            except PhotoValidationError:
                return None

    # -- storage writes, failure and finalization -------------------------------

    async def _put_all(self, asset: PhotoAsset, items: list[tuple[str, Path, str]]) -> None:
        try:
            for key, path, content_type in items:
                await self.storage.put_object(key, path, content_type)
        except MediaStorageError as exc:
            await self._fail(asset, exc)

    async def _fail(self, asset: PhotoAsset, error: Exception) -> NoReturn:
        """CAS PENDING -> FAILED, then raise `error`. If a parallel request
        already finalized the asset, its READY outcome stands (step 17)."""
        asset_id, owner_id = asset.id, asset.owner_id
        try:
            await self.assets.compare_and_set_status(asset_id, owner_id, expected=P, target=F)
        except PhotoAssetTransitionConflictError as lost:
            if lost.current_status is R:
                raise _ConcurrentlyFinalized() from None
        except SQLAlchemyError:
            # The FAILED commit failed: the row stays PENDING (resumable,
            # failure matrix). The original error is still the outcome.
            await self.db.rollback()
            logger.error("photo asset %s: could not record FAILED after %s", asset_id, type(error).__name__)
            raise error from None
        logger.warning("photo asset %s FAILED (%s)", asset_id, type(error).__name__)
        raise error

    async def _finalize(self, asset: PhotoAsset, outcome: PhotoUploadOutcome) -> PhotoUploadResult:
        try:
            ready = await self.assets.compare_and_set_status(asset.id, asset.owner_id, expected=P, target=R)
        except PhotoAssetTransitionConflictError as lost:
            if lost.current_status is R:
                return await self._result(PhotoUploadOutcome.CONCURRENTLY_FINALIZED, await self._read_owned(asset))
            raise _Reidentify() from None
        except SQLAlchemyError:
            # READY commit failed: the row stays PENDING with all objects
            # present; a retry resumes and finalizes (failure matrix).
            await self.db.rollback()
            raise
        logger.info("photo asset %s READY (%s)", ready.id, outcome.value)
        return await self._result(outcome, ready)

    # -- reads -----------------------------------------------------------------

    async def _read_asset(self, upload_id: uuid.UUID) -> PhotoAsset | None:
        """Unscoped by owner on purpose (identification); never exposed."""
        stmt = select(PhotoAsset).where(PhotoAsset.id == upload_id).execution_options(populate_existing=True)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _read_owned(self, asset: PhotoAsset) -> PhotoAsset:
        return await self._read_owned_id(asset.id, asset.owner_id)

    async def _read_owned_id(self, asset_id: uuid.UUID, owner_id: uuid.UUID) -> PhotoAsset:
        current = await self._read_asset(asset_id)
        if current is None or current.owner_id != owner_id:  # pragma: no cover - rows are never deleted
            raise PhotoUploadIdConflictError()
        return current

    async def _result(self, outcome: PhotoUploadOutcome, asset: PhotoAsset) -> PhotoUploadResult:
        stmt = (
            select(PhotoAttachment)
            .where(PhotoAttachment.asset_id == asset.id)
            .order_by(PhotoAttachment.created_at, PhotoAttachment.id)
            .limit(1)
        )
        attachment = (await self.db.execute(stmt)).scalar_one_or_none()
        usage = await logical_usage_bytes(self.db, asset.owner_id)
        state = storage_state(
            usage, warning_bytes=self.config.warning_bytes, soft_cap_bytes=self.config.soft_cap_bytes
        )
        return PhotoUploadResult(outcome=outcome, asset=asset, attachment=attachment, storage_state=state)
