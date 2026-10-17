"""The final deletion of an object (archive cleanup AC-5b): thin routes over `ProjectPurgeService`.

An object is deleted for good only from the archive, after a preview the server computes, and never when an issued / signed document holds it.
The files of its photos go through the same ledger and retry as a single photo (AC-2).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_media_purger
from app.core.database import get_db
from app.domain.exceptions import (
    ProjectNotArchivedError,
    ProjectNotFoundError,
    ProjectPurgeBlockedError,
    ProjectPurgeConflictError,
)
from app.domain.services.media_purger import MediaPurger
from app.domain.services.project_purge_service import ProjectPurgeService
from app.models.user import User
from app.schemas.photo_purge import PurgeBlockerRead
from app.schemas.project_purge import ProjectPurgePreview, ProjectPurgeResult

router = APIRouter()

_MESSAGES = {
    "PROJECT_NOT_FOUND": "Project not found",
    "PROJECT_NOT_ARCHIVED": "Only an archived object can be deleted for good",
    "PROJECT_PURGE_BLOCKED": "An issued or signed document holds this object",
    "PROJECT_PURGE_CONFLICT": "The object changed while it was being deleted; nothing was deleted",
}


def _error(status_code: int, code: str, **extra: object) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": _MESSAGES[code], **extra})


def _map(exc: Exception) -> HTTPException:
    if isinstance(exc, ProjectNotFoundError):
        return _error(status.HTTP_404_NOT_FOUND, "PROJECT_NOT_FOUND")
    if isinstance(exc, ProjectNotArchivedError):
        return _error(status.HTTP_409_CONFLICT, "PROJECT_NOT_ARCHIVED")
    if isinstance(exc, ProjectPurgeBlockedError):
        return _error(
            status.HTTP_409_CONFLICT, "PROJECT_PURGE_BLOCKED",
            blockers=[{"kind": b.kind, "protocol_id": str(b.protocol_id), "status": b.status} for b in exc.blockers],
        )
    if isinstance(exc, ProjectPurgeConflictError):
        return _error(status.HTTP_409_CONFLICT, "PROJECT_PURGE_CONFLICT")
    raise exc


FAILURES = (ProjectNotFoundError, ProjectNotArchivedError, ProjectPurgeBlockedError, ProjectPurgeConflictError)


@router.get(
    "/projects/{project_id}/purge-preview",
    response_model=ProjectPurgePreview,
    summary="What deleting this object for good would remove (no side effects)",
)
async def project_purge_preview(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    purger: MediaPurger = Depends(get_media_purger),
) -> ProjectPurgePreview:
    try:
        preview = await ProjectPurgeService(db, purger).preview(current_user.id, project_id)
    except FAILURES as exc:
        raise _map(exc) from None
    return ProjectPurgePreview(
        project_id=preview.project_id, name=preview.name, archived=preview.archived, can_purge=preview.can_purge,
        rooms=preview.rooms, surfaces=preview.surfaces, openings=preview.openings, inspections=preview.inspections,
        estimates=preview.estimates, documents=preview.documents, sent_documents=preview.sent_documents, photos=preview.photos,
        photo_files=preview.photo_files, bytes=preview.bytes, annotations=preview.annotations,
        may_be_in_backups=preview.photo_files > 0,
        blockers=[PurgeBlockerRead(kind=b.kind, protocol_id=b.protocol_id, status=b.status) for b in preview.blockers],
    )


@router.post(
    "/projects/{project_id}/purge",
    response_model=ProjectPurgeResult,
    summary="Delete an archived object for good (409 when it is not archived or an issued / signed document holds it)",
)
async def purge_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    purger: MediaPurger = Depends(get_media_purger),
) -> ProjectPurgeResult:
    try:
        outcome = await ProjectPurgeService(db, purger).purge(current_user.id, project_id)
    except FAILURES as exc:
        raise _map(exc) from None
    return ProjectPurgeResult(purged=True, photo_files=outcome.photo_files, storage_pending=outcome.storage_pending)
