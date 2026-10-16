"""The final deletion of photos (archive cleanup AC-2): thin routes over `PhotoPurgeService`.

A photo is deleted for good only from the trash (`/trash`, AC-1), after a preview the server computes. The storage purger is a separate
dependency from the photo storage (which has no delete).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_media_purger
from app.core.database import get_db
from app.domain.exceptions import (
    PhotoAssetNotFoundError,
    PhotoAttachmentNotFoundError,
    PhotoPurgeBlockedError,
    PhotoPurgeConflictError,
    PhotoPurgeNotTrashedError,
    ProjectNotFoundError,
)
from app.domain.services.media_purger import MediaPurger
from app.domain.services.photo_purge_service import PhotoPurgeService
from app.domain.services.project_service import ProjectService
from app.models.user import User
from app.schemas.photo_purge import (
    PhotoPurgePreview,
    PhotoPurgeResult,
    PhotoPurgeStatus,
    PurgeBlockerRead,
)

router = APIRouter()

_MESSAGES = {
    "PROJECT_NOT_FOUND": "Project not found",
    "PHOTO_ATTACHMENT_NOT_FOUND": "Photo attachment not found",
    "PHOTO_NOT_FOUND": "Photo not found",
    "PHOTO_PURGE_NOT_TRASHED": "Only a photo in the trash can be deleted for good",
    "PHOTO_PURGE_BLOCKED": "A protocol still points to this photo",
    "PHOTO_PURGE_CONFLICT": "The photo changed while it was being deleted",
}


def _error(status_code: int, code: str, **extra: object) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": _MESSAGES[code], **extra})


def _map(exc: Exception) -> HTTPException:
    if isinstance(exc, ProjectNotFoundError):
        return _error(status.HTTP_404_NOT_FOUND, "PROJECT_NOT_FOUND")
    if isinstance(exc, PhotoAttachmentNotFoundError):
        return _error(status.HTTP_404_NOT_FOUND, "PHOTO_ATTACHMENT_NOT_FOUND")
    if isinstance(exc, PhotoAssetNotFoundError):
        return _error(status.HTTP_404_NOT_FOUND, "PHOTO_NOT_FOUND")
    if isinstance(exc, PhotoPurgeNotTrashedError):
        return _error(status.HTTP_409_CONFLICT, "PHOTO_PURGE_NOT_TRASHED")
    if isinstance(exc, PhotoPurgeBlockedError):
        return _error(
            status.HTTP_409_CONFLICT, "PHOTO_PURGE_BLOCKED",
            blockers=[{"kind": b.kind, "protocol_id": str(b.protocol_id), "status": b.status} for b in exc.blockers],
        )
    if isinstance(exc, PhotoPurgeConflictError):
        return _error(status.HTTP_409_CONFLICT, "PHOTO_PURGE_CONFLICT")
    raise exc


FAILURES = (
    ProjectNotFoundError, PhotoAttachmentNotFoundError, PhotoAssetNotFoundError,
    PhotoPurgeNotTrashedError, PhotoPurgeBlockedError, PhotoPurgeConflictError,
)


@router.get(
    "/projects/{project_id}/photo-attachments/{attachment_id}/purge-preview",
    response_model=PhotoPurgePreview,
    summary="What deleting this photo for good would remove (no side effects)",
)
async def purge_preview(
    project_id: uuid.UUID,
    attachment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    purger: MediaPurger = Depends(get_media_purger),
) -> PhotoPurgePreview:
    try:
        await ProjectService(db).get_project(project_id, current_user.id)
        preview = await PhotoPurgeService(db, purger).preview(current_user.id, project_id, attachment_id)
    except FAILURES as exc:
        raise _map(exc) from None
    return PhotoPurgePreview(
        attachment_id=preview.attachment_id, trashed=preview.trashed, can_purge=preview.can_purge, annotations=preview.annotations,
        other_attachments=preview.other_attachments, deletes_files=preview.deletes_files, files=preview.files, bytes=preview.bytes,
        may_be_in_backups=preview.deletes_files,
        blockers=[PurgeBlockerRead(kind=b.kind, protocol_id=b.protocol_id, status=b.status) for b in preview.blockers],
    )


@router.post(
    "/projects/{project_id}/photo-attachments/{attachment_id}/purge",
    response_model=PhotoPurgeResult,
    summary="Delete a photo in the trash for good (409 when it is not in the trash or a protocol points to it)",
)
async def purge_photo(
    project_id: uuid.UUID,
    attachment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    purger: MediaPurger = Depends(get_media_purger),
) -> PhotoPurgeResult:
    try:
        await ProjectService(db).get_project(project_id, current_user.id)
        outcome = await PhotoPurgeService(db, purger).purge(current_user.id, project_id, attachment_id)
    except FAILURES as exc:
        raise _map(exc) from None
    return PhotoPurgeResult(purged=True, deleted_files=outcome.deleted_files, storage_pending=outcome.storage_pending)


@router.get("/photo-purge/status", response_model=PhotoPurgeStatus, summary="How many deleted photos still wait to be removed from the storage / the backups")
async def purge_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    purger: MediaPurger = Depends(get_media_purger),
) -> PhotoPurgeStatus:
    state = await PhotoPurgeService(db, purger).status(current_user.id)
    return PhotoPurgeStatus(storage_pending=state.storage_pending, backup_pending=state.backup_pending, last_purged_at=state.last_purged_at)


@router.post("/photo-purge/retry", response_model=PhotoPurgeStatus, summary="Try again to remove the objects of deleted photos that are still in the storage")
async def purge_retry(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    purger: MediaPurger = Depends(get_media_purger),
) -> PhotoPurgeStatus:
    service = PhotoPurgeService(db, purger)
    await service.retry_pending(current_user.id)
    state = await service.status(current_user.id)
    return PhotoPurgeStatus(storage_pending=state.storage_pending, backup_pending=state.backup_pending, last_purged_at=state.last_purged_at)
