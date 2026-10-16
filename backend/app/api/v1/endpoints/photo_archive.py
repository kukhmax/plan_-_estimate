"""The photos of the archive and of the trash across all objects (archive cleanup AC-3a): a thin route over `PhotoArchiveService`.

The photos themselves are changed (restore, trash, delete for good) by the routes of the object (AC-1 / AC-2); this route only lists.
"""
from datetime import UTC, datetime, timedelta
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import PhotoRuntime, get_current_user, get_photo_runtime
from app.core.config import settings
from app.core.database import get_db
from app.domain.exceptions import MediaStorageDisabled, PhotoAttachmentValidationError
from app.domain.services.photo_annotation_service import PhotoAnnotationService
from app.domain.services.photo_archive_service import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    PhotoArchiveService,
)
from app.models.user import User
from app.schemas.photo import PhotoAssetRead, PhotoAttachmentRead
from app.schemas.photo_archive import (
    ArchivedPhotoItem,
    PhotoArchiveResponse,
    PhotoPlaceRead,
)

router = APIRouter()


class ArchiveView(str, Enum):
    archived = "archived"
    trashed = "trashed"


@router.get(
    "/photos/archive",
    response_model=PhotoArchiveResponse,
    summary="Photos in the archive or in the trash, across all objects of the owner",
)
async def list_photo_archive(
    view: ArchiveView = Query(default=ArchiveView.archived),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    runtime: PhotoRuntime = Depends(get_photo_runtime),
) -> PhotoArchiveResponse:
    try:
        page = await PhotoArchiveService(db).list_archive(
            current_user.id, trashed=view is ArchiveView.trashed, limit=limit
        )
    except PhotoAttachmentValidationError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "PHOTO_ATTACHMENT_INVALID", "message": "Invalid photo archive request"},
        ) from None
    ttl = settings.PHOTO_SIGNED_URL_TTL_SECONDS
    urls: list[str | None] = []
    expires_at: datetime | None = datetime.now(UTC) + timedelta(seconds=ttl)
    try:
        for item in page.items:
            urls.append(await runtime.storage.presign_get(item.asset.storage_key_thumbnail, ttl))
    except MediaStorageDisabled:
        urls, expires_at = [None] * len(page.items), None
    markers = await PhotoAnnotationService(db).counts_for_attachments([i.attachment.id for i in page.items])
    return PhotoArchiveResponse(
        items=[
            ArchivedPhotoItem(
                attachment=PhotoAttachmentRead.model_validate(item.attachment),
                asset=PhotoAssetRead.model_validate(item.asset),
                thumbnail_url=url,
                annotation_count=markers.get(item.attachment.id, 0),
                project_id=item.attachment.project_id,
                project_name=item.project_name,
                place=PhotoPlaceRead(**item.place.__dict__),
            )
            for item, url in zip(page.items, urls, strict=True)
        ],
        archived_total=page.archived_total,
        trashed_total=page.trashed_total,
        urls_expire_at=expires_at if page.items else None,
    )
