"""Photo upload response DTOs (Stage 14C.4; contract §9).

Never carries storage keys, sha256 or other internal storage facts. The
presigned derivative URLs are the only delivery references (C5).
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.domain.services.photo_quota import PhotoStorageState
from app.models.photo_asset import PhotoAssetStatus, PhotoContentType
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
