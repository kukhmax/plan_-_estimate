"""Downtime episodes of an object (Stage 16I.3): open the episode, write the notice, issue it, write the protocol, issue it, abandon."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_document_issuer, get_downtime_service
from app.api.v1.endpoints.documents import _error, _http_error as _document_error
from app.core.database import get_db
from app.domain.documents.issuer import DocumentIssuer
from app.domain.exceptions import (
    DocumentDataError,
    DocumentQueueFullError,
    DowntimeGateError,
    DowntimeInvalidError,
    DowntimeNotEditableError,
    DowntimeNotFoundError,
    ProjectNotFoundError,
)
from app.domain.services.downtime_service import DowntimeService
from app.models.user import User
from app.schemas.downtime import DowntimeListResponse, DowntimeRead, DowntimeUpdate
from app.schemas.issued_document import IssuedDocumentRead

router = APIRouter()
BASE = "/projects/{project_id}/downtimes"
FAILURES = (ProjectNotFoundError, DowntimeNotFoundError, DowntimeNotEditableError, DowntimeInvalidError)
ISSUE_FAILURES = (*FAILURES, DowntimeGateError, DocumentDataError, DocumentQueueFullError)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, DowntimeNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Episode not found")
    if isinstance(exc, DowntimeNotEditableError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": exc.code, "message": str(exc)})
    if isinstance(exc, DowntimeGateError):
        return _error(
            exc.code, str(exc), status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={"blockers": [{"code": b.code, "details": b.details} for b in exc.blockers]},
        )
    if isinstance(exc, (DocumentDataError, DocumentQueueFullError)):
        return _document_error(exc)
    if isinstance(exc, DowntimeInvalidError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": str(exc), "details": {"key": exc.key, "reason": exc.reason}},
        )
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@router.get(BASE, response_model=DowntimeListResponse, summary="Downtime episodes of an object, newest first")
async def list_downtimes(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: DowntimeService = Depends(get_downtime_service),
) -> DowntimeListResponse:
    try:
        rows = await service.list(project_id, current_user.id)
        items = [await service.read(r) for r in rows]
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return DowntimeListResponse(items=items, total=len(items))


@router.post(BASE, response_model=DowntimeRead, status_code=status.HTTP_201_CREATED, summary="Open an episode (the same one when it is still open)")
async def open_downtime(
    project_id: uuid.UUID,
    response: Response,
    current_user: User = Depends(get_current_user),
    service: DowntimeService = Depends(get_downtime_service),
) -> DowntimeRead:
    try:
        row, created = await service.open_episode(project_id, current_user.id)
        if not created:
            response.status_code = status.HTTP_200_OK
        return await service.read(row)
    except FAILURES as exc:
        raise _http_error(exc) from exc


@router.get(BASE + "/{episode_id}", response_model=DowntimeRead, summary="One episode")
async def get_downtime(
    project_id: uuid.UUID,
    episode_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: DowntimeService = Depends(get_downtime_service),
) -> DowntimeRead:
    try:
        return await service.read(await service.get(project_id, episode_id, current_user.id))
    except FAILURES as exc:
        raise _http_error(exc) from exc


@router.patch(BASE + "/{episode_id}", response_model=DowntimeRead, summary="Record the notice (a draft) or the protocol (a noticed episode)")
async def update_downtime(
    project_id: uuid.UUID,
    episode_id: uuid.UUID,
    payload: DowntimeUpdate,
    current_user: User = Depends(get_current_user),
    service: DowntimeService = Depends(get_downtime_service),
) -> DowntimeRead:
    changes = {key: getattr(payload, key) for key in payload.model_fields_set}
    if not changes:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "DOWNTIME_NO_CHANGES", "message": "nothing to change"})
    try:
        return await service.read(await service.update(project_id, episode_id, current_user.id, changes))
    except FAILURES as exc:
        raise _http_error(exc) from exc


@router.post(BASE + "/{episode_id}/archive", response_model=DowntimeRead, summary="Abandon an open episode")
async def archive_downtime(
    project_id: uuid.UUID,
    episode_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: DowntimeService = Depends(get_downtime_service),
) -> DowntimeRead:
    try:
        return await service.read(await service.archive(project_id, episode_id, current_user.id))
    except FAILURES as exc:
        raise _http_error(exc) from exc


@router.post(
    BASE + "/{episode_id}/issue-notice",
    response_model=IssuedDocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Issue the notice of a draft episode: freeze it and send the PDF to the owner's chat",
)
async def issue_downtime_notice(
    project_id: uuid.UUID,
    episode_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    issuer: DocumentIssuer = Depends(get_document_issuer),
) -> IssuedDocumentRead:
    try:
        reservation = await issuer.start_downtime_notice(db, current_user, project_id, episode_id)
    except ISSUE_FAILURES as exc:
        raise _http_error(exc) from exc
    return IssuedDocumentRead.model_validate(reservation.document)


@router.post(
    BASE + "/{episode_id}/issue-protocol",
    response_model=IssuedDocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Issue the protocol of a noticed episode: freeze it and send the PDF to the owner's chat",
)
async def issue_downtime_protocol(
    project_id: uuid.UUID,
    episode_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    issuer: DocumentIssuer = Depends(get_document_issuer),
) -> IssuedDocumentRead:
    try:
        reservation = await issuer.start_downtime_protocol(db, current_user, project_id, episode_id)
    except ISSUE_FAILURES as exc:
        raise _http_error(exc) from exc
    return IssuedDocumentRead.model_validate(reservation.document)
