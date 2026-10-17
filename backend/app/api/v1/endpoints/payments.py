"""Settlements of an object (invoices and advances, IA-1): thin routes over `PaymentService`.

Invoices issued to the client, money taken from the client (advances and payments) and expenses on materials; the agreed amount of the object.
A register for the owner: nothing here issues a legal invoice.
"""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user, get_payment_service
from app.domain.exceptions import (
    ClientIdConflictError,
    PaymentInvalidError,
    PaymentNotFoundError,
    ProjectNotFoundError,
)
from app.domain.services.payment_service import FinanceView, PaymentService
from app.models.user import User
from app.schemas.payment import (
    AgreedSuggestionRead,
    FinanceRead,
    FinanceWrite,
    Kind,
    PaymentCreate,
    PaymentListResponse,
    PaymentRead,
    PaymentSummary,
    PaymentUpdate,
)

router = APIRouter()

FAILURES = (ProjectNotFoundError, PaymentNotFoundError, PaymentInvalidError, ClientIdConflictError)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PaymentNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Payment not found")
    if isinstance(exc, PaymentInvalidError):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": exc.code, "message": str(exc)})
    if isinstance(exc, ClientIdConflictError):
        return HTTPException(status.HTTP_409_CONFLICT, detail={"code": exc.code, "message": "The id is already used by another record"})
    return HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")


def _read(row, standings) -> PaymentRead:
    item = PaymentRead.model_validate(row)
    standing = standings.get(row.id)
    if standing is not None:
        item.settled, item.remaining, item.state = standing.settled, standing.remaining, standing.state
    return item


def _finance(view: FinanceView) -> FinanceRead:
    suggestion = view.suggestion
    return FinanceRead(
        agreed_amount=view.agreed_amount,
        currency=view.currency,
        suggestion=None if suggestion is None else AgreedSuggestionRead(
            amount=suggestion.amount, estimate_id=suggestion.estimate_id, estimate_version=suggestion.estimate_version, status=suggestion.status
        ),
    )


@router.get("/projects/{project_id}/payments", response_model=PaymentListResponse, summary="The settlement records of an object with the summary")
async def list_payments(
    project_id: uuid.UUID,
    kind: Kind | None = Query(default=None),
    include_archived: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    service: PaymentService = Depends(get_payment_service),
) -> PaymentListResponse:
    try:
        found = await service.list_payments(current_user.id, project_id, kind=kind, include_archived=include_archived, today=datetime.now(UTC).date())
        finance = await service.get_finance(current_user.id, project_id)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return PaymentListResponse(
        items=[_read(row, found.standings) for row in found.items],
        total=found.total,
        summary=PaymentSummary(**{name: getattr(found.summary, name) for name in PaymentSummary.model_fields}),
        agreed_amount=finance.agreed_amount,
    )


@router.post("/projects/{project_id}/payments", response_model=PaymentRead, status_code=status.HTTP_201_CREATED, summary="Add a settlement record")
async def create_payment(
    project_id: uuid.UUID,
    payload: PaymentCreate,
    current_user: User = Depends(get_current_user),
    service: PaymentService = Depends(get_payment_service),
) -> PaymentRead:
    data = payload.model_dump(exclude={"id"})
    try:
        row = await service.create_payment(current_user.id, project_id, data, client_id=payload.id)
        found = await service.list_payments(current_user.id, project_id, include_archived=True)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return _read(row, found.standings)


@router.patch("/projects/{project_id}/payments/{payment_id}", response_model=PaymentRead, summary="Change a settlement record")
async def update_payment(
    project_id: uuid.UUID,
    payment_id: uuid.UUID,
    payload: PaymentUpdate,
    current_user: User = Depends(get_current_user),
    service: PaymentService = Depends(get_payment_service),
) -> PaymentRead:
    try:
        row = await service.update_payment(current_user.id, project_id, payment_id, payload.model_dump(exclude_unset=True))
        found = await service.list_payments(current_user.id, project_id, include_archived=True)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return _read(row, found.standings)


async def _archive(project_id: uuid.UUID, payment_id: uuid.UUID, archived: bool, user: User, service: PaymentService) -> PaymentRead:
    try:
        row = await service.set_archived(user.id, project_id, payment_id, archived)
        found = await service.list_payments(user.id, project_id, include_archived=True)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return _read(row, found.standings)


@router.post("/projects/{project_id}/payments/{payment_id}/archive", response_model=PaymentRead, summary="Archive a settlement record (it is never erased)")
async def archive_payment(
    project_id: uuid.UUID, payment_id: uuid.UUID, current_user: User = Depends(get_current_user), service: PaymentService = Depends(get_payment_service)
) -> PaymentRead:
    return await _archive(project_id, payment_id, True, current_user, service)


@router.post("/projects/{project_id}/payments/{payment_id}/restore", response_model=PaymentRead, summary="Bring an archived settlement record back")
async def restore_payment(
    project_id: uuid.UUID, payment_id: uuid.UUID, current_user: User = Depends(get_current_user), service: PaymentService = Depends(get_payment_service)
) -> PaymentRead:
    return await _archive(project_id, payment_id, False, current_user, service)


@router.get("/projects/{project_id}/finance", response_model=FinanceRead, summary="The agreed amount of an object and the hint from its estimate")
async def get_finance(
    project_id: uuid.UUID, current_user: User = Depends(get_current_user), service: PaymentService = Depends(get_payment_service)
) -> FinanceRead:
    try:
        return _finance(await service.get_finance(current_user.id, project_id))
    except FAILURES as exc:
        raise _http_error(exc) from exc


@router.put("/projects/{project_id}/finance", response_model=FinanceRead, summary="Set (or clear, with null) the agreed amount of an object")
async def put_finance(
    project_id: uuid.UUID,
    payload: FinanceWrite,
    current_user: User = Depends(get_current_user),
    service: PaymentService = Depends(get_payment_service),
) -> FinanceRead:
    try:
        return _finance(await service.set_agreed_amount(current_user.id, project_id, payload.agreed_amount))
    except FAILURES as exc:
        raise _http_error(exc) from exc
