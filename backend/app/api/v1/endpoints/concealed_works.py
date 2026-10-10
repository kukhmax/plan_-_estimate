"""Protocols of concealed works of an object (Stage 16G): open the draft, record what was accepted, abandon, issue."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_concealed_service, get_current_user, get_document_issuer
from app.api.v1.endpoints.documents import _error, _http_error as _document_error
from app.core.database import get_db
from app.domain.documents.issuer import DocumentIssuer
from app.domain.exceptions import (
    ConcealedGateError,
    ConcealedInvalidError,
    ConcealedNotEditableError,
    ConcealedNotFoundError,
    DocumentDataError,
    DocumentQueueFullError,
    ProjectNotFoundError,
)
from app.domain.services.concealed_service import ConcealedService
from app.models.user import User
from app.schemas.concealed import ConcealedListResponse, ConcealedRead, ConcealedUpdate
from app.schemas.issued_document import IssuedDocumentRead

router = APIRouter()
BASE = "/projects/{project_id}/concealed-works"
FAILURES = (ProjectNotFoundError, ConcealedNotFoundError, ConcealedNotEditableError, ConcealedInvalidError)
ISSUE_FAILURES = (*FAILURES, ConcealedGateError, DocumentDataError, DocumentQueueFullError)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ConcealedNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Protocol not found")
    if isinstance(exc, ConcealedNotEditableError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": exc.code, "message": str(exc)})
    if isinstance(exc, ConcealedGateError):
        return _error(
            exc.code, str(exc), status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={"blockers": [{"code": b.code, "details": b.details} for b in exc.blockers]},
        )
    if isinstance(exc, (DocumentDataError, DocumentQueueFullError)):
        return _document_error(exc)
    if isinstance(exc, ConcealedInvalidError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": str(exc), "details": {"key": exc.key, "reason": exc.reason}},
        )
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@router.get(BASE, response_model=ConcealedListResponse, summary="Protocols of concealed works of an object, newest first")
async def list_concealed(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: ConcealedService = Depends(get_concealed_service),
) -> ConcealedListResponse:
    try:
        rows = await service.list(project_id, current_user.id)
        items = [await service.read(r) for r in rows]
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return ConcealedListResponse(items=items, total=len(items))


@router.post(BASE, response_model=ConcealedRead, status_code=status.HTTP_201_CREATED, summary="Open the draft (the same draft when one exists)")
async def open_concealed_draft(
    project_id: uuid.UUID,
    response: Response,
    current_user: User = Depends(get_current_user),
    service: ConcealedService = Depends(get_concealed_service),
) -> ConcealedRead:
    try:
        row, created = await service.open_draft(project_id, current_user.id)
        result = await service.read(row)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    if not created:
        response.status_code = status.HTTP_200_OK
    return result


@router.get(BASE + "/{protocol_id}", response_model=ConcealedRead, summary="One protocol")
async def get_concealed(
    project_id: uuid.UUID,
    protocol_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: ConcealedService = Depends(get_concealed_service),
) -> ConcealedRead:
    try:
        return await service.read(await service.get(project_id, protocol_id, current_user.id))
    except FAILURES as exc:
        raise _http_error(exc) from exc


@router.patch(BASE + "/{protocol_id}", response_model=ConcealedRead, summary="Record what was accepted (only a draft changes)")
async def update_concealed(
    project_id: uuid.UUID,
    protocol_id: uuid.UUID,
    payload: ConcealedUpdate,
    current_user: User = Depends(get_current_user),
    service: ConcealedService = Depends(get_concealed_service),
) -> ConcealedRead:
    changes = {key: getattr(payload, key) for key in payload.model_fields_set}
    if not changes:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "CONCEALED_NO_CHANGES", "message": "nothing to change"})
    try:
        return await service.read(await service.update(project_id, protocol_id, current_user.id, changes))
    except FAILURES as exc:
        raise _http_error(exc) from exc


@router.post(BASE + "/{protocol_id}/archive", response_model=ConcealedRead, summary="Abandon a draft")
async def archive_concealed_draft(
    project_id: uuid.UUID,
    protocol_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: ConcealedService = Depends(get_concealed_service),
) -> ConcealedRead:
    try:
        return await service.read(await service.archive_draft(project_id, protocol_id, current_user.id))
    except FAILURES as exc:
        raise _http_error(exc) from exc


@router.post(
    BASE + "/{protocol_id}/issue",
    response_model=IssuedDocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Issue a draft: freeze what was accepted and send the PDF to the owner's chat",
)
async def issue_concealed(
    project_id: uuid.UUID,
    protocol_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    issuer: DocumentIssuer = Depends(get_document_issuer),
) -> IssuedDocumentRead:
    try:
        reservation = await issuer.start_concealed(db, current_user, project_id, protocol_id)
    except ISSUE_FAILURES as exc:
        raise _http_error(exc) from exc
    return IssuedDocumentRead.model_validate(reservation.document)
