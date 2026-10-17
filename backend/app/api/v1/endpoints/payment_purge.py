"""The archived settlement records of all objects and their final deletion (invoices and advances, IA-7): thin routes over `PaymentPurgeService`.

Only from the archive, after a preview the server computes. The files of its photos go through the same ledger and retry as a single photo (AC-2).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_media_purger
from app.core.database import get_db
from app.domain.exceptions import PaymentNotArchivedError, PaymentNotFoundError, PaymentPurgeConflictError
from app.domain.services.media_purger import MediaPurger
from app.domain.services.payment_purge_service import PaymentPurgePreview as Preview
from app.domain.services.payment_purge_service import PaymentPurgeService
from app.models.user import User
from app.schemas.payment_purge import ArchivedPaymentItem, ArchivedPaymentsResponse, PaymentPurgePreview, PaymentPurgeResult

router = APIRouter()

_MESSAGES = {
    "PAYMENT_NOT_FOUND": "Payment not found",
    "PAYMENT_NOT_ARCHIVED": "Only an archived record can be deleted for good",
    "PAYMENT_PURGE_CONFLICT": "It changed while it was being deleted; nothing was deleted",
}
FAILURES = (PaymentNotFoundError, PaymentNotArchivedError, PaymentPurgeConflictError)


def _error(status_code: int, code: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": _MESSAGES[code]})


def _map(exc: Exception) -> HTTPException:
    if isinstance(exc, PaymentNotFoundError):
        return _error(status.HTTP_404_NOT_FOUND, "PAYMENT_NOT_FOUND")
    if isinstance(exc, PaymentNotArchivedError):
        return _error(status.HTTP_409_CONFLICT, "PAYMENT_NOT_ARCHIVED")
    if isinstance(exc, PaymentPurgeConflictError):
        return _error(status.HTTP_409_CONFLICT, "PAYMENT_PURGE_CONFLICT")
    raise exc


def _preview_schema(p: Preview) -> PaymentPurgePreview:
    return PaymentPurgePreview(
        target_id=p.target_id, kind=p.kind, title=p.title, archived=p.archived, can_purge=p.can_purge, tied_payments=p.tied_payments,
        photos=p.photos, photo_files=p.photo_files, bytes=p.bytes, annotations=p.annotations, may_be_in_backups=p.photo_files > 0,
    )


@router.get(
    "/archive/payments",
    response_model=ArchivedPaymentsResponse,
    summary="Archived settlement records of all objects in work, with the object (read-only)",
)
async def list_archived_payments(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    purger: MediaPurger = Depends(get_media_purger),
) -> ArchivedPaymentsResponse:
    found = await PaymentPurgeService(db, purger).list_archived(current_user.id)
    return ArchivedPaymentsResponse(
        items=[
            ArchivedPaymentItem(
                id=item.payment.id, project_id=item.payment.project_id, project_name=item.project_name, kind=item.payment.kind,
                title=item.payment.title, number=item.payment.number, amount_gross=item.payment.amount_gross,
                occurred_on=item.payment.occurred_on, counterparty=item.payment.counterparty, category=item.payment.category, photos=item.photos,
            )
            for item in found.items
        ],
        total=found.total,
    )


@router.get(
    "/projects/{project_id}/payments/{payment_id}/purge-preview",
    response_model=PaymentPurgePreview,
    summary="What deleting this settlement record for good would remove (no side effects)",
)
async def payment_purge_preview(
    project_id: uuid.UUID,
    payment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    purger: MediaPurger = Depends(get_media_purger),
) -> PaymentPurgePreview:
    try:
        return _preview_schema(await PaymentPurgeService(db, purger).preview(current_user.id, project_id, payment_id))
    except FAILURES as exc:
        raise _map(exc) from None


@router.post(
    "/projects/{project_id}/payments/{payment_id}/purge",
    response_model=PaymentPurgeResult,
    summary="Delete an archived settlement record for good, with its photos (409 when it is not archived)",
)
async def purge_payment(
    project_id: uuid.UUID,
    payment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    purger: MediaPurger = Depends(get_media_purger),
) -> PaymentPurgeResult:
    try:
        outcome = await PaymentPurgeService(db, purger).purge(current_user.id, project_id, payment_id)
    except FAILURES as exc:
        raise _map(exc) from None
    return PaymentPurgeResult(purged=True, photo_files=outcome.photo_files, storage_pending=outcome.storage_pending)
