"""The archived contracts and protocols of all objects and their final deletion (AC-6): thin routes over `ArchivedDocumentService`.

Only the data of the card; only from the archive, after a preview the server computes.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.domain.exceptions import ArchivedDocumentInUseError, ArchivedDocumentNotArchivedError, ArchivedDocumentNotFoundError
from app.domain.services.archived_document_service import ArchivedDocumentService
from app.models.user import User
from app.schemas.archived_document import (
    ArchivedDocumentItem,
    ArchivedDocumentsResponse,
    DocumentKind,
    DocumentPurgePreview,
    DocumentPurgeResult,
)

router = APIRouter()

_MESSAGES = {
    "DOCUMENT_RECORD_NOT_FOUND": "Document record not found",
    "DOCUMENT_RECORD_NOT_ARCHIVED": "Only an archived record can be deleted for good",
    "DOCUMENT_RECORD_IN_USE": "Protocols still refer to this contract; archive or delete them first",
}
FAILURES = (ArchivedDocumentNotFoundError, ArchivedDocumentNotArchivedError, ArchivedDocumentInUseError)


def _error(status_code: int, code: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": _MESSAGES[code]})


def _map(exc: Exception) -> HTTPException:
    if isinstance(exc, ArchivedDocumentNotFoundError):
        return _error(status.HTTP_404_NOT_FOUND, "DOCUMENT_RECORD_NOT_FOUND")
    if isinstance(exc, ArchivedDocumentNotArchivedError):
        return _error(status.HTTP_409_CONFLICT, "DOCUMENT_RECORD_NOT_ARCHIVED")
    if isinstance(exc, ArchivedDocumentInUseError):
        return _error(status.HTTP_409_CONFLICT, "DOCUMENT_RECORD_IN_USE")
    raise exc


@router.get(
    "/archive/documents",
    response_model=ArchivedDocumentsResponse,
    summary="Archived contracts and protocols of all objects in work, with the object (read-only)",
)
async def list_archived_documents(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ArchivedDocumentsResponse:
    found = await ArchivedDocumentService(db).list_archived(current_user.id)
    return ArchivedDocumentsResponse(
        items=[
            ArchivedDocumentItem(
                kind=item.kind, id=item.id, project_id=item.project_id, project_name=item.project_name, ordinal=item.ordinal,
                number=item.number, issued_at=item.issued_at, archived_at=item.archived_at,
            )
            for item in found.items
        ],
        total=found.total,
    )


@router.get(
    "/archive/documents/{kind}/{record_id}/purge-preview",
    response_model=DocumentPurgePreview,
    summary="What deleting this archived contract / protocol for good would do (no side effects)",
)
async def archived_document_purge_preview(
    kind: DocumentKind,
    record_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentPurgePreview:
    try:
        p = await ArchivedDocumentService(db).preview(current_user.id, kind, record_id)
    except FAILURES as exc:
        raise _map(exc) from None
    return DocumentPurgePreview(
        kind=kind, target_id=p.target_id, ordinal=p.ordinal, archived=p.archived, issued=p.issued, can_purge=p.can_purge,
        journal_lines=p.journal_lines, dependents=p.dependents,
    )


@router.post(
    "/archive/documents/{kind}/{record_id}/purge",
    response_model=DocumentPurgeResult,
    summary="Delete an archived contract / protocol for good (409 when it is not archived or protocols still refer to it)",
)
async def purge_archived_document(
    kind: DocumentKind,
    record_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DocumentPurgeResult:
    try:
        await ArchivedDocumentService(db).purge(current_user.id, kind, record_id)
    except FAILURES as exc:
        raise _map(exc) from None
    return DocumentPurgeResult(purged=True)
