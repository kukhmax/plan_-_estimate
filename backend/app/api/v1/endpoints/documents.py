"""Client documents HTTP API (Stage 15F): issue an estimate or a photo report, follow it, read the journal.

Thin owner-scoped controller. Everything cheap that can be wrong is answered in the request (422 with a stable code); the
slow part (the PDF and its delivery to the owner's Telegram chat) runs in the background and ends the journal row, which the
screen follows with `GET`. Ownership always comes from the authenticated user.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_document_issuer
from app.core.database import get_db
from app.domain.documents.issuer import DocumentIssuer
from app.domain.documents.photo_report_document import PhotoReportDocumentService
from app.domain.exceptions import (
    DocumentDataError,
    DocumentDeliveryDisabledError,
    DocumentDeliveryError,
    DocumentQueueFullError,
    DocumentRenderBusyError,
    DocumentRenderError,
    DocumentRenderTimeoutError,
    DocumentTooLargeError,
    EstimateNotFoundError,
    DocumentInProgressError,
    IssuedDocumentNotFoundError,
    ProjectNotFoundError,
)
from app.domain.services.issued_document_service import IssuedDocumentService
from app.models.user import User
from app.schemas.issued_document import (
    IssuedDocumentListResponse,
    IssuedDocumentRead,
    IssueDocumentRequest,
    OwnerDocumentListResponse,
    OwnerDocumentRead,
    PhotoReportSummaryRead,
    PreviewResponse,
    RoomSummaryRead,
    UnpricedWorkRead,
)

router = APIRouter()


def _error(code: str, message: str, http_status: int, **extra) -> HTTPException:
    detail = {"code": code, "message": message, **extra}
    headers = {"Retry-After": "10"} if http_status in (429, 503) else None
    return HTTPException(status_code=http_status, detail=detail, headers=headers)


def _http_error(exc: Exception) -> HTTPException:
    """Domain failures as the fixed error envelope `{"detail": {"code", "message", ...}}`."""
    if isinstance(exc, ProjectNotFoundError):
        return _error("PROJECT_NOT_FOUND", "Project not found", status.HTTP_404_NOT_FOUND)
    if isinstance(exc, EstimateNotFoundError):
        return _error("ESTIMATE_NOT_FOUND", "Estimate not found", status.HTTP_404_NOT_FOUND)
    if isinstance(exc, IssuedDocumentNotFoundError):
        return _error("DOCUMENT_NOT_FOUND", "Document not found", status.HTTP_404_NOT_FOUND)
    if isinstance(exc, DocumentInProgressError):
        return _error(exc.code, "The document is still being made", status.HTTP_409_CONFLICT)
    if isinstance(exc, DocumentDataError):
        return _error(exc.reason, str(exc), status.HTTP_422_UNPROCESSABLE_ENTITY, details=exc.details)
    if isinstance(exc, DocumentQueueFullError):
        return _error(exc.code, str(exc), status.HTTP_429_TOO_MANY_REQUESTS)
    if isinstance(exc, DocumentRenderBusyError):
        return _error(exc.code, str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
    if isinstance(exc, DocumentRenderTimeoutError):
        return _error(exc.code, str(exc), status.HTTP_504_GATEWAY_TIMEOUT)
    if isinstance(exc, DocumentTooLargeError):
        return _error(exc.code, str(exc), status.HTTP_422_UNPROCESSABLE_ENTITY)
    if isinstance(exc, DocumentDeliveryDisabledError):
        return _error(exc.code, str(exc), status.HTTP_503_SERVICE_UNAVAILABLE)
    if isinstance(exc, DocumentDeliveryError):
        # the chat cannot be written to: the owner can fix it (start the bot); anything else is a bad gateway
        http_status = status.HTTP_409_CONFLICT if exc.code == "TELEGRAM_CHAT_UNAVAILABLE" else status.HTTP_502_BAD_GATEWAY
        return _error(exc.code, str(exc), http_status)
    if isinstance(exc, DocumentRenderError):
        return _error(exc.code, str(exc), status.HTTP_500_INTERNAL_SERVER_ERROR)
    raise exc


@router.post(
    "/projects/{project_id}/documents",
    response_model=IssuedDocumentRead,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Issue a document and send it to the owner's Telegram chat",
)
async def issue_document(
    project_id: uuid.UUID,
    body: IssueDocumentRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    issuer: DocumentIssuer = Depends(get_document_issuer),
) -> IssuedDocumentRead:
    try:
        if body.kind == "ESTIMATE":
            reservation = await issuer.start_estimate(db, current_user, project_id, body.estimate_id)
        elif body.kind == "PRODUCTION_PLAN":
            reservation = await issuer.start_production_plan(db, current_user, project_id)
        elif body.kind == "TECH_CARD":
            reservation = await issuer.start_tech_card(db, current_user, project_id)
        elif body.kind == "SETTLEMENT":
            reservation = await issuer.start_settlement(db, current_user, project_id)
        elif body.kind == "MEASUREMENTS":
            reservation = await issuer.start_measurements(db, current_user, project_id)
        else:
            rooms = frozenset(body.room_ids) if body.room_ids is not None else None
            reservation = await issuer.start_photo_report(
                db, current_user, project_id, room_ids=rooms, include_project_photos=body.include_project_photos
            )
    except (ProjectNotFoundError, EstimateNotFoundError, DocumentDataError, DocumentQueueFullError) as exc:
        raise _http_error(exc) from exc
    return IssuedDocumentRead.model_validate(reservation.document)


@router.get(
    "/projects/{project_id}/documents",
    response_model=IssuedDocumentListResponse,
    summary="The journal of issued documents of a project, newest first",
)
async def list_documents(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> IssuedDocumentListResponse:
    try:
        rows = await IssuedDocumentService(db).list_for_project(current_user.id, project_id)
    except ProjectNotFoundError as exc:
        raise _http_error(exc) from exc
    items = [IssuedDocumentRead.model_validate(row) for row in rows]
    return IssuedDocumentListResponse(items=items, total=len(items))


@router.get(
    "/documents",
    response_model=OwnerDocumentListResponse,
    summary="The journal of issued documents of all objects of the owner, newest first (read only)",
)
async def list_all_documents(
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OwnerDocumentListResponse:
    rows, total = await IssuedDocumentService(db).list_for_owner(current_user.id, limit=limit, offset=offset)
    items = [
        OwnerDocumentRead(**IssuedDocumentRead.model_validate(document).model_dump(), project_name=name) for document, name in rows
    ]
    return OwnerDocumentListResponse(items=items, total=total)


@router.get(
    "/projects/{project_id}/documents/{document_id}",
    response_model=IssuedDocumentRead,
    summary="One document of the journal (the screen follows a running one with this)",
)
async def get_document(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> IssuedDocumentRead:
    try:
        row = await IssuedDocumentService(db).get(current_user.id, project_id, document_id)
    except IssuedDocumentNotFoundError as exc:
        raise _http_error(exc) from exc
    return IssuedDocumentRead.model_validate(row)


@router.delete(
    "/projects/{project_id}/documents/{document_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete one row of the journal of the sent documents (only the row: the document and the PDF in the chat stay; 409 while it is being made)",
)
async def delete_document(
    project_id: uuid.UUID,
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    try:
        await IssuedDocumentService(db).delete(current_user.id, project_id, document_id)
    except (IssuedDocumentNotFoundError, DocumentInProgressError) as exc:
        raise _http_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/projects/{project_id}/photo-report/summary",
    response_model=PhotoReportSummaryRead,
    summary="What a photo report of the project would hold (counts only)",
)
async def photo_report_summary(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    issuer: DocumentIssuer = Depends(get_document_issuer),
) -> PhotoReportSummaryRead:
    service = PhotoReportDocumentService(db, issuer.storage(), storage_name=issuer.storage_name, max_photos=issuer.max_photos)
    try:
        summary = await service.summary(current_user.id, project_id)
    except ProjectNotFoundError as exc:
        raise _http_error(exc) from exc
    return PhotoReportSummaryRead(
        photo_count=summary.photo_count,
        project_photos=summary.project_photos,
        limit=summary.limit,
        over_limit=summary.over_limit,
        has_content=summary.has_content,
        rooms=[RoomSummaryRead.model_validate(room) for room in summary.rooms],
        recommended_count=summary.recommended_count,
        unpriced_works=list(summary.unpriced_works),
        unpriced_items=[UnpricedWorkRead.model_validate(item) for item in summary.unpriced_items],
        estimate_id=summary.estimate_id,
        estimate_status=summary.estimate_status,
    )


@router.post(
    "/projects/{project_id}/estimates/{estimate_id}/preview-pdf",
    response_model=PreviewResponse,
    summary="Send a working version (watermark, no number) of an unfinished estimate to the owner's chat",
)
async def preview_estimate_pdf(
    project_id: uuid.UUID,
    estimate_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    issuer: DocumentIssuer = Depends(get_document_issuer),
) -> PreviewResponse:
    try:
        result = await issuer.preview_estimate(db, current_user, project_id, estimate_id)
    except (
        ProjectNotFoundError,
        EstimateNotFoundError,
        DocumentDataError,
        DocumentRenderError,
        DocumentDeliveryError,
    ) as exc:
        raise _http_error(exc) from exc
    return PreviewResponse(sent=True, pages=result.pages, byte_size=result.byte_size)


@router.post(
    "/projects/{project_id}/documents/tech-card/preview",
    response_model=PreviewResponse,
    summary="Send the working version (watermark, no number, empty lines for what is missing) of the technological card to the owner's chat",
)
async def preview_tech_card_pdf(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    issuer: DocumentIssuer = Depends(get_document_issuer),
) -> PreviewResponse:
    try:
        result = await issuer.preview_tech_card(db, current_user, project_id)
    except (ProjectNotFoundError, DocumentDataError, DocumentRenderError, DocumentDeliveryError) as exc:
        raise _http_error(exc) from exc
    return PreviewResponse(sent=True, pages=result.pages, byte_size=result.byte_size)


@router.post(
    "/projects/{project_id}/documents/settlement/preview",
    response_model=PreviewResponse,
    summary="Send the working version (watermark, no number) of the statement of settlements (Rozliczenie) to the owner's chat",
)
async def preview_settlement_pdf(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    issuer: DocumentIssuer = Depends(get_document_issuer),
) -> PreviewResponse:
    try:
        result = await issuer.preview_settlement(db, current_user, project_id)
    except (ProjectNotFoundError, DocumentDataError, DocumentRenderError, DocumentDeliveryError) as exc:
        raise _http_error(exc) from exc
    return PreviewResponse(sent=True, pages=result.pages, byte_size=result.byte_size)


@router.post(
    "/projects/{project_id}/documents/measurements/preview",
    response_model=PreviewResponse,
    summary="Send the working version (watermark, no number) of the measurements of the object (Obmiar obiektu) to the owner's chat",
)
async def preview_measurements_pdf(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    issuer: DocumentIssuer = Depends(get_document_issuer),
) -> PreviewResponse:
    try:
        result = await issuer.preview_measurements(db, current_user, project_id)
    except (ProjectNotFoundError, DocumentDataError, DocumentRenderError, DocumentDeliveryError) as exc:
        raise _http_error(exc) from exc
    return PreviewResponse(sent=True, pages=result.pages, byte_size=result.byte_size)


@router.post(
    "/projects/{project_id}/documents/production-plan/preview",
    response_model=PreviewResponse,
    summary="Send the working version (pale watermark, no number, empty lines for what is missing) of the production plan to the owner's chat",
)
async def preview_production_plan_pdf(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    issuer: DocumentIssuer = Depends(get_document_issuer),
) -> PreviewResponse:
    try:
        result = await issuer.preview_production_plan(db, current_user, project_id)
    except (ProjectNotFoundError, DocumentDataError, DocumentRenderError, DocumentDeliveryError) as exc:
        raise _http_error(exc) from exc
    return PreviewResponse(sent=True, pages=result.pages, byte_size=result.byte_size)


@router.post(
    "/projects/{project_id}/documents/concealed-works/preview",
    response_model=PreviewResponse,
    summary="Send the working version (pale watermark, no number, empty boxes and lines) of the protocol of concealed works to the owner's chat",
)
async def preview_concealed_pdf(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    issuer: DocumentIssuer = Depends(get_document_issuer),
) -> PreviewResponse:
    try:
        result = await issuer.preview_concealed(db, current_user, project_id)
    except (ProjectNotFoundError, DocumentDataError, DocumentRenderError, DocumentDeliveryError) as exc:
        raise _http_error(exc) from exc
    return PreviewResponse(sent=True, pages=result.pages, byte_size=result.byte_size)


@router.post(
    "/projects/{project_id}/documents/acceptance/preview",
    response_model=PreviewResponse,
    summary="Send the working version (pale watermark, no number, empty boxes and lines) of the acceptance protocol to the owner's chat",
)
async def preview_acceptance_pdf(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    issuer: DocumentIssuer = Depends(get_document_issuer),
) -> PreviewResponse:
    try:
        result = await issuer.preview_acceptance(db, current_user, project_id)
    except (ProjectNotFoundError, DocumentDataError, DocumentRenderError, DocumentDeliveryError) as exc:
        raise _http_error(exc) from exc
    return PreviewResponse(sent=True, pages=result.pages, byte_size=result.byte_size)


@router.post(
    "/projects/{project_id}/documents/decision/preview",
    response_model=PreviewResponse,
    summary="Send the working version (pale watermark, no number, empty boxes and lines) of the protocol of information and decisions to the owner's chat",
)
async def preview_decision_pdf(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    issuer: DocumentIssuer = Depends(get_document_issuer),
) -> PreviewResponse:
    try:
        result = await issuer.preview_decision(db, current_user, project_id)
    except (ProjectNotFoundError, DocumentDataError, DocumentRenderError, DocumentDeliveryError) as exc:
        raise _http_error(exc) from exc
    return PreviewResponse(sent=True, pages=result.pages, byte_size=result.byte_size)


@router.post(
    "/projects/{project_id}/documents/downtime-notice/preview",
    response_model=PreviewResponse,
    summary="Send the working version (pale watermark, no number, empty boxes and lines) of the notice of downtime to the owner's chat",
)
async def preview_downtime_notice_pdf(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    issuer: DocumentIssuer = Depends(get_document_issuer),
) -> PreviewResponse:
    try:
        result = await issuer.preview_downtime_notice(db, current_user, project_id)
    except (ProjectNotFoundError, DocumentDataError, DocumentRenderError, DocumentDeliveryError) as exc:
        raise _http_error(exc) from exc
    return PreviewResponse(sent=True, pages=result.pages, byte_size=result.byte_size)


@router.post(
    "/projects/{project_id}/documents/downtime-protocol/preview",
    response_model=PreviewResponse,
    summary="Send the working version (pale watermark, no number, empty boxes and lines) of the protocol of downtime to the owner's chat",
)
async def preview_downtime_protocol_pdf(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    issuer: DocumentIssuer = Depends(get_document_issuer),
) -> PreviewResponse:
    try:
        result = await issuer.preview_downtime_protocol(db, current_user, project_id)
    except (ProjectNotFoundError, DocumentDataError, DocumentRenderError, DocumentDeliveryError) as exc:
        raise _http_error(exc) from exc
    return PreviewResponse(sent=True, pages=result.pages, byte_size=result.byte_size)


@router.post(
    "/projects/{project_id}/documents/handover/preview",
    response_model=PreviewResponse,
    summary="Send the working version (pale watermark, no number, empty boxes and lines) of the protocol of handing over the premises to the owner's chat",
)
async def preview_handover_pdf(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    issuer: DocumentIssuer = Depends(get_document_issuer),
) -> PreviewResponse:
    try:
        result = await issuer.preview_handover(db, current_user, project_id)
    except (ProjectNotFoundError, DocumentDataError, DocumentRenderError, DocumentDeliveryError) as exc:
        raise _http_error(exc) from exc
    return PreviewResponse(sent=True, pages=result.pages, byte_size=result.byte_size)


@router.post(
    "/projects/{project_id}/documents/contract/preview",
    response_model=PreviewResponse,
    summary="Send the working version (pale watermark, no number, empty lines for what is missing) of the contract with its annexes to the owner's chat",
)
async def preview_contract_pdf(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    issuer: DocumentIssuer = Depends(get_document_issuer),
) -> PreviewResponse:
    try:
        result = await issuer.preview_contract(db, current_user, project_id)
    except (ProjectNotFoundError, DocumentDataError, DocumentRenderError, DocumentDeliveryError) as exc:
        raise _http_error(exc) from exc
    return PreviewResponse(sent=True, pages=result.pages, byte_size=result.byte_size)
