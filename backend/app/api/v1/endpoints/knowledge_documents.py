"""The owner's own documents of the knowledge base (V2-7a): a list with a search, add / change (one multipart form: the fields and, if wanted, one
file), read, delete, the file itself, and "send the file to my chat". Private to the owner. A thin controller: the rules are in
`app.domain.knowledge_documents`, the work in `KnowledgeDocumentService`.

The form is read by hand (as the photo upload does) so that the owner is known before the first byte of a file is read and the body can never
exceed the limit, whatever Content-Length claims.
"""
import uuid
from urllib.parse import quote

import anyio
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from python_multipart.exceptions import FormParserError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.deps import get_current_user, get_db, get_document_delivery
from app.api.upload_guard import (
    RequestBodyIdleTimeoutError,
    RequestBodyTooLargeError,
    limited_receive,
)
from app.domain import knowledge_documents as rules
from app.domain.documents.delivery import DocumentDelivery
from app.domain.exceptions import DocumentDeliveryDisabledError, DocumentDeliveryError
from app.domain.knowledge_documents import (
    OwnDocumentError,
    OwnDocumentNotFoundError,
)
from app.domain.services.knowledge_document_service import (
    KnowledgeDocumentService,
    NewFile,
)
from app.models.knowledge_document import KnowledgeDocument
from app.models.user import User
from app.schemas.knowledge_document import (
    KnowledgeDocumentList,
    KnowledgeDocumentListItem,
    KnowledgeDocumentRead,
)

router = APIRouter(prefix="/knowledge/documents")

# the file, the text (100 000 characters, up to 4 bytes each is not reached: the limit of the text is checked by the rules), and the small fields
MAX_REQUEST_BYTES = rules.MAX_FILE_BYTES + 700_000
MAX_SCALAR_PART_BYTES = 450_000
FIELDS = {"title", "kind", "source_url", "doc_date", "when_to_use", "body", "tags", "remove_file"}
IDLE_TIMEOUT_SECONDS = 60.0


def _error(code: str, message: str, http_status: int, field: str | None = None) -> HTTPException:
    detail: dict = {"code": code, "message": message}
    if field:
        detail["field"] = field
    return HTTPException(status_code=http_status, detail=detail)


def _own_error(exc: OwnDocumentError) -> HTTPException:
    if isinstance(exc, OwnDocumentNotFoundError):
        return _error(exc.code, "The document was not found", status.HTTP_404_NOT_FOUND)
    if exc.code in ("TOO_MANY_DOCUMENTS", "STORAGE_FULL"):
        return _error(exc.code, str(exc), status.HTTP_409_CONFLICT, exc.field)
    if exc.code == "FILE_TOO_LARGE":
        return _error(exc.code, str(exc), status.HTTP_413_CONTENT_TOO_LARGE, exc.field)
    if exc.code == "KNOWLEDGE_DOCUMENT_HAS_NO_FILE":
        return _error(exc.code, str(exc), status.HTTP_404_NOT_FOUND)
    return _error(exc.code, str(exc), status.HTTP_422_UNPROCESSABLE_CONTENT, exc.field)


def _item(row: KnowledgeDocument) -> dict:
    return {
        "id": row.id, "title": row.title, "kind": row.kind, "source_url": row.source_url, "doc_date": row.doc_date, "tags": list(row.tags or []),
        "file_name": row.file_name, "file_mime": row.file_mime, "file_size": row.file_size, "has_text": row.body is not None,
        "snippet": rules.snippet(row.body), "updated_at": row.updated_at,
    }


def _read(row: KnowledgeDocument) -> KnowledgeDocumentRead:
    return KnowledgeDocumentRead(**_item(row), when_to_use=row.when_to_use, body=row.body, created_at=row.created_at)


async def _form(request: Request) -> tuple[rules.DocumentFields, NewFile | None, bool]:
    """The fields and the optional file of the form, read under the size limit. A wrong form is a 422 with a code, never a 5xx."""
    declared = request.headers.get("content-length")
    if declared is not None and declared.strip().isdigit() and int(declared) > MAX_REQUEST_BYTES:
        raise _error("FILE_TOO_LARGE", "The request is too large", status.HTTP_413_CONTENT_TOO_LARGE, "file")
    guarded = Request(request.scope, receive=limited_receive(request.receive, MAX_REQUEST_BYTES, idle_timeout_seconds=IDLE_TIMEOUT_SECONDS))
    scalars: dict[str, str] = {}
    upload: UploadFile | None = None
    content = b""
    try:
        async with guarded.form(max_files=1, max_fields=len(FIELDS), max_part_size=MAX_SCALAR_PART_BYTES) as form:
            for name, value in form.multi_items():
                if name == "file" and value == "":
                    continue  # the empty part a browser sends when no file was chosen
                if name == "file":
                    if upload is not None or not isinstance(value, UploadFile):
                        raise _error("FORM_INVALID", "The form is wrong", status.HTTP_422_UNPROCESSABLE_CONTENT)
                    upload = value
                elif name in FIELDS and isinstance(value, str) and name not in scalars:
                    scalars[name] = value
                else:
                    raise _error("FORM_INVALID", "The form is wrong", status.HTTP_422_UNPROCESSABLE_CONTENT)
            if upload is not None and upload.filename:
                content = await upload.read(rules.MAX_FILE_BYTES + 1)
    except RequestBodyTooLargeError:
        raise _error("FILE_TOO_LARGE", "The request is too large", status.HTTP_413_CONTENT_TOO_LARGE, "file") from None
    except RequestBodyIdleTimeoutError:
        raise _error("UPLOAD_TIMEOUT", "The upload stopped", status.HTTP_408_REQUEST_TIMEOUT) from None
    except StarletteHTTPException as exc:
        if exc.status_code == status.HTTP_400_BAD_REQUEST:
            raise _error("FORM_INVALID", "The form is wrong", status.HTTP_422_UNPROCESSABLE_CONTENT) from None
        raise
    except FormParserError:
        raise _error("FORM_INVALID", "The form is wrong", status.HTTP_422_UNPROCESSABLE_CONTENT) from None
    try:
        fields = rules.build_fields(
            title=scalars.get("title", ""), kind=scalars.get("kind", "OTHER"), source_url=scalars.get("source_url"),
            doc_date=scalars.get("doc_date"), when_to_use=scalars.get("when_to_use"), body=scalars.get("body"), tags=scalars.get("tags"),
        )
    except OwnDocumentError as exc:
        raise _own_error(exc) from None
    remove = scalars.get("remove_file", "false")
    if remove not in ("true", "false"):
        raise _error("FORM_INVALID", "The form is wrong", status.HTTP_422_UNPROCESSABLE_CONTENT, "remove_file")
    new_file = NewFile(upload.filename if upload else None, content) if content or (upload is not None and upload.filename) else None
    return fields, new_file, remove == "true"


@router.get("", response_model=KnowledgeDocumentList, summary="The owner's own documents: the newest first, or the best match of a search")
async def list_documents(
    q: str = Query("", max_length=200),
    kind: str | None = Query(None, max_length=16),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeDocumentList:
    try:
        rows = await KnowledgeDocumentService(db).list(current_user.id, q, kind)
    except OwnDocumentError as exc:
        raise _own_error(exc) from None
    return KnowledgeDocumentList(
        items=[KnowledgeDocumentListItem(**_item(row)) for row in rows], total=len(rows),
        max_documents=rules.MAX_DOCUMENTS, max_file_bytes=rules.MAX_FILE_BYTES,
    )


@router.post("", response_model=KnowledgeDocumentRead, status_code=status.HTTP_201_CREATED, summary="Add a document (multipart form)")
async def add_document(
    request: Request, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> KnowledgeDocumentRead:
    owner_id = current_user.id
    fields, new_file, _remove = await _form(request)
    try:
        return _read(await KnowledgeDocumentService(db).create(owner_id, fields, new_file))
    except OwnDocumentError as exc:
        raise _own_error(exc) from None


@router.get("/{document_id}", response_model=KnowledgeDocumentRead, summary="One document with its text")
async def get_document(
    document_id: uuid.UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> KnowledgeDocumentRead:
    try:
        return _read(await KnowledgeDocumentService(db).get(current_user.id, document_id))
    except OwnDocumentError as exc:
        raise _own_error(exc) from None


@router.put("/{document_id}", response_model=KnowledgeDocumentRead, summary="Change a document (multipart form: every field, the file only if it is replaced)")
async def change_document(
    document_id: uuid.UUID, request: Request, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> KnowledgeDocumentRead:
    owner_id = current_user.id
    fields, new_file, remove_file = await _form(request)
    try:
        return _read(await KnowledgeDocumentService(db).update(owner_id, document_id, fields, new_file, remove_file))
    except OwnDocumentError as exc:
        raise _own_error(exc) from None


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a document with its file (for good)")
async def delete_document(
    document_id: uuid.UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Response:
    try:
        await KnowledgeDocumentService(db).delete(current_user.id, document_id)
    except OwnDocumentError as exc:
        raise _own_error(exc) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{document_id}/file", summary="The file of a document (a PDF, a JPEG or a PNG)")
async def get_document_file(
    document_id: uuid.UUID, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> Response:
    try:
        stored = await KnowledgeDocumentService(db).file(current_user.id, document_id)
    except OwnDocumentError as exc:
        raise _own_error(exc) from None
    ascii_name = "".join(ch if ch.isascii() and ch not in '"\\' else "_" for ch in stored.name)
    headers = {
        "Content-Disposition": f"inline; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(stored.name)}",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "sandbox",
        "Cache-Control": "private, no-store",
    }
    return Response(content=stored.content, media_type=stored.mime, headers=headers)


@router.post("/{document_id}/send", summary="Send the file of a document to the owner's Telegram chat")
async def send_document_file(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    delivery: DocumentDelivery = Depends(get_document_delivery),
) -> dict:
    chat_id = current_user.telegram_user_id
    try:
        service = KnowledgeDocumentService(db)
        row = await service.get(current_user.id, document_id)
        stored = await service.file(current_user.id, document_id)
        title = row.title
    except OwnDocumentError as exc:
        raise _own_error(exc) from None
    try:
        with anyio.fail_after(120):
            await delivery.send_document(chat_id, stored.name, stored.content, title)
    except DocumentDeliveryDisabledError as exc:
        raise _error(exc.code, str(exc), status.HTTP_503_SERVICE_UNAVAILABLE) from None
    except DocumentDeliveryError as exc:
        http_status = status.HTTP_409_CONFLICT if exc.code == "TELEGRAM_CHAT_UNAVAILABLE" else status.HTTP_502_BAD_GATEWAY
        raise _error(exc.code, str(exc), http_status) from None
    except TimeoutError:
        raise _error("TELEGRAM_UNAVAILABLE", "Telegram did not answer in time", status.HTTP_502_BAD_GATEWAY) from None
    return {"sent": True}
