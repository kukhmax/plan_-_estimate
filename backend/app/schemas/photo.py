"""Photo upload response DTOs (Stage 14C.4; contract §9).

Never carries storage keys, sha256 or other internal storage facts. The
presigned derivative URLs are the only delivery references (C5).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, StrictBool, StrictInt, field_validator

from app.domain.services.photo_quota import PhotoStorageState
from app.models.photo_asset import (
    PhotoAssetStatus,
    PhotoCaptureSource,
    PhotoContentType,
)
from app.models.photo_attachment import PhotoAttachmentContext, PhotoCategory


class PhotoAssetRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    status: PhotoAssetStatus
    content_type: PhotoContentType
    byte_size: int
    width: int
    height: int
    original_filename: str | None
    captured_at: datetime | None
    # Client-declared, informational, never proof; null = unknown (14E.2, D11).
    capture_source: PhotoCaptureSource | None
    uploaded_at: datetime
    archived_at: datetime | None


class PhotoAttachmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    project_id: uuid.UUID
    context: PhotoAttachmentContext
    room_id: uuid.UUID | None
    surface_id: uuid.UUID | None
    opening_id: uuid.UUID | None
    category: PhotoCategory
    caption: str | None
    include_in_report: bool
    position: int
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PhotoStorageRead(BaseModel):
    state: PhotoStorageState


class PhotoUploadResponse(BaseModel):
    asset: PhotoAssetRead
    attachment: PhotoAttachmentRead | None
    thumbnail_url: str
    display_url: str
    urls_expire_at: datetime
    storage: PhotoStorageRead


# ---------------------------------------------------------------------------
# Stage 14C.5 — reads, metadata, attach, storage status (contract §16–§18, §21)
# URL fields are nullable: MEDIA_STORAGE_BACKEND=disabled returns metadata
# with null delivery URLs (§17).
# ---------------------------------------------------------------------------


class PhotoListItem(BaseModel):
    attachment: PhotoAttachmentRead
    asset: PhotoAssetRead
    thumbnail_url: str | None


class PhotoListResponse(BaseModel):
    items: list[PhotoListItem]
    next_cursor: str | None
    urls_expire_at: datetime | None


class PhotoDetailResponse(BaseModel):
    asset: PhotoAssetRead
    attachments: list[PhotoAttachmentRead]
    thumbnail_url: str | None
    display_url: str | None
    urls_expire_at: datetime | None


class PhotoAttachmentPatch(BaseModel):
    """Metadata only. Omitted = unchanged; `caption: null` clears; the other
    fields reject null. Identity, context, target and storage fields are
    rejected as unknown (extra="forbid")."""

    model_config = ConfigDict(extra="forbid")

    caption: str | None = None
    category: PhotoCategory | None = None
    include_in_report: StrictBool | None = None
    position: StrictInt | None = None

    @field_validator("category", "include_in_report", "position", mode="before")
    @classmethod
    def _no_explicit_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("null is not allowed; omit the field to keep it unchanged")
        return value


class PhotoAttachRequest(BaseModel):
    """Attach an existing READY asset to another supported context."""

    model_config = ConfigDict(extra="forbid")

    context: PhotoAttachmentContext
    room_id: uuid.UUID | None = None
    surface_id: uuid.UUID | None = None
    opening_id: uuid.UUID | None = None
    category: PhotoCategory | None = None
    caption: str | None = None
    include_in_report: StrictBool = False


class PhotoCountsResponse(BaseModel):
    """GET /projects/{p}/photos/counts (14E.2): visible photos per target; empty targets omitted."""

    project: int
    rooms: dict[uuid.UUID, int]
    surfaces: dict[uuid.UUID, int]
    openings: dict[uuid.UUID, int]


class PhotoStorageStatus(BaseModel):
    uploads_enabled: bool
    media_available: bool
    used_bytes: int
    warning_bytes: int
    soft_cap_bytes: int
    state: PhotoStorageState
