"""Schemas of the photo archive across all objects (archive cleanup AC-3a)."""
import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.photo import PhotoListItem


class PhotoPlaceRead(BaseModel):
    room_name: str | None = None
    surface_name: str | None = None
    surface_type: str | None = None
    opening_type: str | None = None
    opening_name: str | None = None
    payment_title: str | None = None  # IA-3: a photo of a receipt / an invoice: the record it belongs to
    payment_kind: str | None = None


class ArchivedPhotoItem(PhotoListItem):
    project_id: uuid.UUID
    project_name: str
    place: PhotoPlaceRead


class PhotoArchiveResponse(BaseModel):
    items: list[ArchivedPhotoItem]
    archived_total: int  # all photos in the archive (the trash left out)
    trashed_total: int  # all photos in the trash
    urls_expire_at: datetime | None
