"""Protocols of a pressure test of an object (V2-12b): open the draft, record the test, abandon, issue; the working version of the form."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_pressure_service, get_current_user, get_document_issuer
from app.api.v1.endpoints.documents import _error, _http_error as _document_error
from app.core.database import get_db
from app.domain.documents.issuer import DocumentIssuer
from app.domain.exceptions import (
    PressureGateError,
    PressureInvalidError,
    PressureNotEditableError,
    PressureNotFoundError,
    DocumentDataError,
    DocumentDeliveryError,
    DocumentQueueFullError,
    DocumentRenderError,
    ProjectNotFoundError,
)
from app.domain.services.pressure_service import PressureService
from app.models.user import User
from app.schemas.pressure import PressureListResponse, PressureRead, PressureUpdate
from app.schemas.issued_document import IssuedDocumentRead, PreviewResponse

router = APIRouter()
BASE = "/projects/{project_id}/pressure-tests"
FAILURES = (ProjectNotFoundError, PressureNotFoundError, PressureNotEditableError, PressureInvalidError)
ISSUE_FAILURES = (*FAILURES, PressureGateError, DocumentDataError, DocumentQueueFullError)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PressureNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Protocol not found")
    if isinstance(exc, PressureNotEditableError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": exc.code, "message": str(exc)})
    if isinstance(exc, PressureGateError):
        return _error(
            exc.code, str(exc), status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={"blockers": [{"code": b.code, "details": b.details} for b in exc.blockers]},
        )
    if isinstance(exc, (DocumentDataError, DocumentQueueFullError)):
        return _document_error(exc)
    if isinstance(exc, PressureInvalidError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": str(exc), "details": {"key": exc.key, "reason": exc.reason}},
        )
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@router.get(BASE, response_model=PressureListResponse, summary="Protocols of the pressure tests of an object, newest first")
async def list_pressure(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: PressureService = Depends(get_pressure_service),
) -> PressureListResponse:
    try:
        rows = await service.list(project_id, current_user.id)
        items = [await service.read(r) for r in rows]
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return PressureListResponse(items=items, total=len(items))


@router.post(BASE, response_model=PressureRead, status_code=status.HTTP_201_CREATED, summary="Open the draft (the same draft when one exists)")
async def open_pressure_draft(
    project_id: uuid.UUID,
    response: Response,
    current_user: User = Depends(get_current_user),
    service: PressureService = Depends(get_pressure_service),
) -> PressureRead:
    try:
        row, created = await service.open_draft(project_id, current_user.id)
        result = await service.read(row)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    if not created:
        response.status_code = status.HTTP_200_OK
    return result


@router.get(BASE + "/{protocol_id}", response_model=PressureRead, summary="One protocol")
async def get_pressure(
    project_id: uuid.UUID,
    protocol_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: PressureService = Depends(get_pressure_service),
) -> PressureRead:
    try:
        return await service.read(await service.get(project_id, protocol_id, current_user.id))
    except FAILURES as exc:
        raise _http_error(exc) from exc


@router.patch(BASE + "/{protocol_id}", response_model=PressureRead, summary="Record the test (only a draft changes)")
async def update_pressure(
    project_id: uuid.UUID,
    protocol_id: uuid.UUID,
    payload: PressureUpdate,
    current_user: User = Depends(get_current_user),
    service: PressureService = Depends(get_pressure_service),
) -> PressureRead:
    changes = {key: getattr(payload, key) for key in payload.model_fields_set}
    if not changes:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "PRESSURE_NO_CHANGES", "message": "nothing to change"})
    try:
        return await service.read(await service.update(project_id, protocol_id, current_user.id, changes))
    except FAILURES as exc:
        raise _http_error(exc) from exc


@router.post(BASE + "/{protocol_id}/archive", response_model=PressureRead, summary="Abandon a draft")
async def archive_pressure_draft(
    project_id: uuid.UUID,
    protocol_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: PressureService = Depends(get_pressure_service),
) -> PressureRead:
    try:
        return await service.read(await service.archive_draft(project_id, protocol_id, current_user.id))
    except FAILURES as exc:
        raise _http_error(exc) from exc


@router.post(
    BASE + "/{protocol_id}/issue",
    response_model=IssuedDocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Issue a draft: freeze what was tested and send the PDF to the owner's chat",
)
async def issue_pressure(
    project_id: uuid.UUID,
    protocol_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    issuer: DocumentIssuer = Depends(get_document_issuer),
) -> IssuedDocumentRead:
    try:
        reservation = await issuer.start_pressure_test(db, current_user, project_id, protocol_id)
    except ISSUE_FAILURES as exc:
        raise _http_error(exc) from exc
    return IssuedDocumentRead.model_validate(reservation.document)


@router.post(
    "/projects/{project_id}/documents/pressure-test/preview",
    response_model=PreviewResponse,
    summary="Send the working version (pale watermark, no number) of the protocol of a pressure test to the owner's chat, to fill in on the spot",
)
async def preview_pressure_pdf(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    issuer: DocumentIssuer = Depends(get_document_issuer),
) -> PreviewResponse:
    try:
        result = await issuer.preview_pressure_test(db, current_user, project_id)
    except (ProjectNotFoundError, DocumentDataError, DocumentRenderError, DocumentDeliveryError) as exc:
        raise _document_error(exc) from exc
    return PreviewResponse(sent=True, pages=result.pages, byte_size=result.byte_size)
