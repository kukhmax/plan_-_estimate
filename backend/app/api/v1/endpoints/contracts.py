"""Contracts of an object (Stage 16E.1): open the draft, answer the questionnaire "compose the contract", abandon the draft."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_contract_service, get_current_user, get_document_issuer
from app.api.v1.endpoints.documents import _error, _http_error as _document_error
from app.core.database import get_db
from app.domain.documents.issuer import DocumentIssuer
from app.domain.exceptions import (
    ContractAnswerInvalidError,
    ContractGateError,
    ContractNotEditableError,
    ContractNotFoundError,
    ContractSignError,
    DocumentDataError,
    DocumentQueueFullError,
    ProjectNotFoundError,
)
from app.domain.services.contract_service import ContractService, contract_read
from app.models.user import User
from app.schemas.contract import (
    ContractAnswersUpdate,
    ContractGateRead,
    ContractListResponse,
    ContractRead,
    ContractSignRequest,
    GateBlockerRead,
)
from app.schemas.issued_document import IssuedDocumentRead

router = APIRouter()
BASE = "/projects/{project_id}/contracts"
FAILURES = (ProjectNotFoundError, ContractNotFoundError, ContractNotEditableError, ContractAnswerInvalidError, ContractSignError)
ISSUE_FAILURES = (*FAILURES, ContractGateError, DocumentDataError, DocumentQueueFullError)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ContractNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contract not found")
    if isinstance(exc, ContractNotEditableError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": exc.code, "message": str(exc)})
    if isinstance(exc, ContractSignError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": str(exc), "details": {"reason": exc.reason}},
        )
    if isinstance(exc, ContractGateError):
        return _error(
            exc.code, str(exc), status.HTTP_422_UNPROCESSABLE_ENTITY,
            details={"blockers": [{"code": b.code, "details": b.details} for b in exc.blockers]},
        )
    if isinstance(exc, (DocumentDataError, DocumentQueueFullError)):
        return _document_error(exc)
    if isinstance(exc, ContractAnswerInvalidError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": str(exc), "details": {"key": exc.key, "reason": exc.reason}},
        )
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@router.get(BASE, response_model=ContractListResponse, summary="Contracts of an object, newest version first")
async def list_contracts(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: ContractService = Depends(get_contract_service),
) -> ContractListResponse:
    try:
        rows = await service.list(project_id, current_user.id)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return ContractListResponse(items=[contract_read(r) for r in rows], total=len(rows))


@router.post(BASE, response_model=ContractRead, status_code=status.HTTP_201_CREATED, summary="Open the draft of the contract (the same draft when one exists)")
async def open_contract_draft(
    project_id: uuid.UUID,
    response: Response,
    current_user: User = Depends(get_current_user),
    service: ContractService = Depends(get_contract_service),
) -> ContractRead:
    try:
        row, created = await service.open_draft(project_id, current_user.id)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    if not created:
        response.status_code = status.HTTP_200_OK
    return contract_read(row)


@router.get(BASE + "/{contract_id}", response_model=ContractRead, summary="One contract")
async def get_contract(
    project_id: uuid.UUID,
    contract_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: ContractService = Depends(get_contract_service),
) -> ContractRead:
    try:
        row = await service.get(project_id, contract_id, current_user.id)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return contract_read(row)


@router.patch(BASE + "/{contract_id}/answers", response_model=ContractRead, summary="Answer the questionnaire (only a draft changes)")
async def update_contract_answers(
    project_id: uuid.UUID,
    contract_id: uuid.UUID,
    payload: ContractAnswersUpdate,
    current_user: User = Depends(get_current_user),
    service: ContractService = Depends(get_contract_service),
) -> ContractRead:
    try:
        row = await service.update_answers(project_id, contract_id, current_user.id, payload.answers)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return contract_read(row)


@router.post(BASE + "/{contract_id}/archive", response_model=ContractRead, summary="Abandon a draft")
async def archive_contract_draft(
    project_id: uuid.UUID,
    contract_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: ContractService = Depends(get_contract_service),
) -> ContractRead:
    try:
        row = await service.archive_draft(project_id, contract_id, current_user.id)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return contract_read(row)


@router.post(BASE + "/{contract_id}/sign", response_model=ContractRead, summary="The issued contract was signed: it becomes SIGNED, its estimate ACCEPTED")
async def sign_contract(
    project_id: uuid.UUID,
    contract_id: uuid.UUID,
    payload: ContractSignRequest,
    current_user: User = Depends(get_current_user),
    service: ContractService = Depends(get_contract_service),
) -> ContractRead:
    try:
        row = await service.sign(project_id, contract_id, current_user.id, payload.signed_on)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return contract_read(row)


@router.post(BASE + "/{contract_id}/close", response_model=ContractRead, summary="Close an issued or signed contract (archive)")
async def close_contract(
    project_id: uuid.UUID,
    contract_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: ContractService = Depends(get_contract_service),
) -> ContractRead:
    try:
        row = await service.close(project_id, contract_id, current_user.id)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return contract_read(row)


@router.get(BASE + "/{contract_id}/gate", response_model=ContractGateRead, summary="What stands between a draft and its issue")
async def contract_gate(
    project_id: uuid.UUID,
    contract_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: ContractService = Depends(get_contract_service),
) -> ContractGateRead:
    try:
        _, _, blockers = await service.gate(project_id, contract_id, current_user.id)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return ContractGateRead(ready=not blockers, blockers=[GateBlockerRead(code=b.code, details=b.details) for b in blockers])


@router.post(
    BASE + "/{contract_id}/issue",
    response_model=IssuedDocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Issue a draft: freeze its conditions and send the PDF to the owner's chat",
)
async def issue_contract(
    project_id: uuid.UUID,
    contract_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    issuer: DocumentIssuer = Depends(get_document_issuer),
) -> IssuedDocumentRead:
    try:
        reservation = await issuer.start_contract(db, current_user, project_id, contract_id)
    except ISSUE_FAILURES as exc:
        raise _http_error(exc) from exc
    return IssuedDocumentRead.model_validate(reservation.document)
