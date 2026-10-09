"""Handover protocols of an object (Stage 16F.1): open the draft, record what was found per room, abandon the draft."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_document_issuer, get_handover_service
from app.api.v1.endpoints.documents import _error, _http_error as _document_error
from app.core.database import get_db
from app.domain.documents.issuer import DocumentIssuer
from app.domain.exceptions import (
    DocumentDataError,
    DocumentQueueFullError,
    HandoverGateError,
    HandoverInvalidError,
    HandoverNotEditableError,
    HandoverNotFoundError,
    ProjectNotFoundError,
)
from app.domain.services.handover_service import HandoverService
from app.models.user import User
from app.schemas.handover import HandoverListResponse, HandoverRead, HandoverUpdate
from app.schemas.issued_document import IssuedDocumentRead

router = APIRouter()
BASE = "/projects/{project_id}/handovers"
FAILURES = (ProjectNotFoundError, HandoverNotFoundError, HandoverNotEditableError, HandoverInvalidError)
ISSUE_FAILURES = (*FAILURES, HandoverGateError, DocumentDataError, DocumentQueueFullError)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, HandoverNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Handover protocol not found")
    if isinstance(exc, HandoverNotEditableError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": exc.code, "message": str(exc)})
    if isinstance(exc, HandoverGateError):
        return _error(
            exc.code, str(exc), status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={"blockers": [{"code": b.code, "details": b.details} for b in exc.blockers]},
        )
    if isinstance(exc, (DocumentDataError, DocumentQueueFullError)):
        return _document_error(exc)
    if isinstance(exc, HandoverInvalidError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": str(exc), "details": {"key": exc.key, "reason": exc.reason}},
        )
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@router.get(BASE, response_model=HandoverListResponse, summary="Handover protocols of an object, newest first")
async def list_handovers(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: HandoverService = Depends(get_handover_service),
) -> HandoverListResponse:
    try:
        rows = await service.list(project_id, current_user.id)
        items = [await service.read(r) for r in rows]
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return HandoverListResponse(items=items, total=len(items))


@router.post(BASE, response_model=HandoverRead, status_code=status.HTTP_201_CREATED, summary="Open the draft (the same draft when one exists)")
async def open_handover_draft(
    project_id: uuid.UUID,
    response: Response,
    current_user: User = Depends(get_current_user),
    service: HandoverService = Depends(get_handover_service),
) -> HandoverRead:
    try:
        row, created = await service.open_draft(project_id, current_user.id)
        result = await service.read(row)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    if not created:
        response.status_code = status.HTTP_200_OK
    return result


@router.get(BASE + "/{handover_id}", response_model=HandoverRead, summary="One handover protocol")
async def get_handover(
    project_id: uuid.UUID,
    handover_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: HandoverService = Depends(get_handover_service),
) -> HandoverRead:
    try:
        return await service.read(await service.get(project_id, handover_id, current_user.id))
    except FAILURES as exc:
        raise _http_error(exc) from exc


@router.patch(BASE + "/{handover_id}", response_model=HandoverRead, summary="Record what was found (only a draft changes)")
async def update_handover(
    project_id: uuid.UUID,
    handover_id: uuid.UUID,
    payload: HandoverUpdate,
    current_user: User = Depends(get_current_user),
    service: HandoverService = Depends(get_handover_service),
) -> HandoverRead:
    changes = {key: getattr(payload, key) for key in payload.model_fields_set}
    if not changes:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "HANDOVER_NO_CHANGES", "message": "nothing to change"})
    try:
        return await service.read(await service.update(project_id, handover_id, current_user.id, changes))
    except FAILURES as exc:
        raise _http_error(exc) from exc


@router.post(BASE + "/{handover_id}/archive", response_model=HandoverRead, summary="Abandon a draft")
async def archive_handover_draft(
    project_id: uuid.UUID,
    handover_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: HandoverService = Depends(get_handover_service),
) -> HandoverRead:
    try:
        return await service.read(await service.archive_draft(project_id, handover_id, current_user.id))
    except FAILURES as exc:
        raise _http_error(exc) from exc


@router.post(
    BASE + "/{handover_id}/issue",
    response_model=IssuedDocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Issue a draft: freeze what was found and send the PDF to the owner's chat",
)
async def issue_handover(
    project_id: uuid.UUID,
    handover_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    issuer: DocumentIssuer = Depends(get_document_issuer),
) -> IssuedDocumentRead:
    try:
        reservation = await issuer.start_handover(db, current_user, project_id, handover_id)
    except ISSUE_FAILURES as exc:
        raise _http_error(exc) from exc
    return IssuedDocumentRead.model_validate(reservation.document)
