"""The final deletion of an archived room, surface or inspection (archive cleanup AC-4b, AC-7): thin routes over `StructurePurgeService`.

Only from the archive, after a preview the server computes, and never while a document that is not archived still points to it. The files
of its photos go through the same ledger and retry as a single photo (AC-2).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_media_purger
from app.core.database import get_db
from app.domain.exceptions import (
    InspectionNotFoundError,
    RoomNotFoundError,
    StructureNotArchivedError,
    StructurePurgeBlockedError,
    StructurePurgeConflictError,
    SurfaceNotFoundError,
)
from app.domain.services.media_purger import MediaPurger
from app.domain.services.structure_purge_service import StructurePurgePreview as Preview
from app.domain.services.structure_purge_service import StructurePurgeService
from app.models.user import User
from app.schemas.photo_purge import PurgeBlockerRead
from app.schemas.structure_purge import StructurePurgePreview, StructurePurgeResult

router = APIRouter()

_MESSAGES = {
    "ROOM_NOT_FOUND": "Room not found",
    "SURFACE_NOT_FOUND": "Surface not found",
    "INSPECTION_NOT_FOUND": "Inspection not found",
    "STRUCTURE_NOT_ARCHIVED": "Only an archived room, surface or inspection can be deleted for good",
    "STRUCTURE_PURGE_BLOCKED": "A document that is not archived still points to it",
    "STRUCTURE_PURGE_CONFLICT": "It changed while it was being deleted; nothing was deleted",
}


def _error(status_code: int, code: str, **extra: object) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": _MESSAGES[code], **extra})


def _map(exc: Exception) -> HTTPException:
    if isinstance(exc, RoomNotFoundError):
        return _error(status.HTTP_404_NOT_FOUND, "ROOM_NOT_FOUND")
    if isinstance(exc, SurfaceNotFoundError):
        return _error(status.HTTP_404_NOT_FOUND, "SURFACE_NOT_FOUND")
    if isinstance(exc, InspectionNotFoundError):
        return _error(status.HTTP_404_NOT_FOUND, "INSPECTION_NOT_FOUND")
    if isinstance(exc, StructureNotArchivedError):
        return _error(status.HTTP_409_CONFLICT, "STRUCTURE_NOT_ARCHIVED")
    if isinstance(exc, StructurePurgeBlockedError):
        return _error(
            status.HTTP_409_CONFLICT, "STRUCTURE_PURGE_BLOCKED",
            blockers=[{"kind": b.kind, "protocol_id": str(b.protocol_id), "status": b.status} for b in exc.blockers],
        )
    if isinstance(exc, StructurePurgeConflictError):
        return _error(status.HTTP_409_CONFLICT, "STRUCTURE_PURGE_CONFLICT")
    raise exc


FAILURES = (RoomNotFoundError, SurfaceNotFoundError, InspectionNotFoundError, StructureNotArchivedError, StructurePurgeBlockedError, StructurePurgeConflictError)


def _preview_schema(p: Preview) -> StructurePurgePreview:
    return StructurePurgePreview(
        kind=p.kind, target_id=p.target_id, name=p.name, archived=p.archived, can_purge=p.can_purge, surfaces=p.surfaces,
        openings=p.openings, inspections=p.inspections, photos=p.photos, photo_files=p.photo_files, bytes=p.bytes,
        annotations=p.annotations, estimate_lines=p.estimate_lines, may_be_in_backups=p.photo_files > 0,
        answers=p.answers, findings=p.findings, risks=p.risks, recommendations=p.recommendations,
        blockers=[PurgeBlockerRead(kind=b.kind, protocol_id=b.protocol_id, status=b.status) for b in p.blockers],
    )


@router.get(
    "/projects/{project_id}/rooms/{room_id}/purge-preview",
    response_model=StructurePurgePreview,
    summary="What deleting this room for good would remove (no side effects)",
)
async def room_purge_preview(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    purger: MediaPurger = Depends(get_media_purger),
) -> StructurePurgePreview:
    try:
        return _preview_schema(await StructurePurgeService(db, purger).preview_room(current_user.id, project_id, room_id))
    except FAILURES as exc:
        raise _map(exc) from None


@router.post(
    "/projects/{project_id}/rooms/{room_id}/purge",
    response_model=StructurePurgeResult,
    summary="Delete an archived room for good (409 when it is not archived or a document that is not archived still points to it)",
)
async def purge_room(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    purger: MediaPurger = Depends(get_media_purger),
) -> StructurePurgeResult:
    try:
        outcome = await StructurePurgeService(db, purger).purge_room(current_user.id, project_id, room_id)
    except FAILURES as exc:
        raise _map(exc) from None
    return StructurePurgeResult(purged=True, photo_files=outcome.photo_files, storage_pending=outcome.storage_pending)


@router.get(
    "/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}/purge-preview",
    response_model=StructurePurgePreview,
    summary="What deleting this surface for good would remove (no side effects)",
)
async def surface_purge_preview(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    surface_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    purger: MediaPurger = Depends(get_media_purger),
) -> StructurePurgePreview:
    try:
        return _preview_schema(await StructurePurgeService(db, purger).preview_surface(current_user.id, project_id, room_id, surface_id))
    except FAILURES as exc:
        raise _map(exc) from None


@router.post(
    "/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}/purge",
    response_model=StructurePurgeResult,
    summary="Delete an archived surface for good (409 when it is not archived or a document that is not archived still points to it)",
)
async def purge_surface(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    surface_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    purger: MediaPurger = Depends(get_media_purger),
) -> StructurePurgeResult:
    try:
        outcome = await StructurePurgeService(db, purger).purge_surface(current_user.id, project_id, room_id, surface_id)
    except FAILURES as exc:
        raise _map(exc) from None
    return StructurePurgeResult(purged=True, photo_files=outcome.photo_files, storage_pending=outcome.storage_pending)


@router.get(
    "/projects/{project_id}/rooms/{room_id}/inspections/{inspection_id}/purge-preview",
    response_model=StructurePurgePreview,
    summary="What deleting this inspection for good would remove (no side effects)",
)
async def inspection_purge_preview(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    inspection_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    purger: MediaPurger = Depends(get_media_purger),
) -> StructurePurgePreview:
    try:
        return _preview_schema(await StructurePurgeService(db, purger).preview_inspection(current_user.id, project_id, room_id, inspection_id))
    except FAILURES as exc:
        raise _map(exc) from None


@router.post(
    "/projects/{project_id}/rooms/{room_id}/inspections/{inspection_id}/purge",
    response_model=StructurePurgeResult,
    summary="Delete an archived inspection for good (409 when it is not archived or a protocol still uses a photo of it)",
)
async def purge_inspection(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    inspection_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    purger: MediaPurger = Depends(get_media_purger),
) -> StructurePurgeResult:
    try:
        outcome = await StructurePurgeService(db, purger).purge_inspection(current_user.id, project_id, room_id, inspection_id)
    except FAILURES as exc:
        raise _map(exc) from None
    return StructurePurgeResult(purged=True, photo_files=outcome.photo_files, storage_pending=outcome.storage_pending)
