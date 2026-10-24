"""The owner's own documents of the knowledge base (V2-7a): list with a search, read, add, change, delete, and the file.

Services commit internally (the convention of the application). Every query filters by `owner_id`: a document of another owner does not exist.
The file of a document is replaced or removed together with its row, so a document never points at a missing file.
"""
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import knowledge_documents as rules
from app.domain.knowledge_documents import (
    DocumentFields,
    OwnDocumentError,
    OwnDocumentNotFoundError,
)
from app.models.knowledge_document import KnowledgeDocument, KnowledgeDocumentFile


@dataclass(frozen=True)
class NewFile:
    announced_name: str | None
    content: bytes


@dataclass(frozen=True)
class StoredFile:
    name: str
    mime: str
    content: bytes


class KnowledgeDocumentService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list(self, owner_id: uuid.UUID, query: str = "", kind: str | None = None) -> list[KnowledgeDocument]:
        if kind is not None and kind.upper() not in rules.KINDS:
            raise OwnDocumentError("KIND_UNKNOWN", "unknown kind of document", "kind")
        stmt = select(KnowledgeDocument).where(KnowledgeDocument.owner_id == owner_id)
        if kind:
            stmt = stmt.where(KnowledgeDocument.kind == kind.upper())
        rows = list((await self._db.execute(stmt.order_by(KnowledgeDocument.updated_at.desc(), KnowledgeDocument.id))).scalars())
        if not query.strip():
            return rows
        scored = []
        for index, row in enumerate(rows):
            value = rules.score(query, title=row.title, tags=list(row.tags or []), when_to_use=row.when_to_use, file_name=row.file_name, body=row.body)
            if value is not None:
                scored.append((-value, index, row))
        scored.sort(key=lambda item: (item[0], item[1]))  # the best match first, equal scores keep the newest first
        return [item[2] for item in scored]

    async def get(self, owner_id: uuid.UUID, document_id: uuid.UUID) -> KnowledgeDocument:
        row = (
            await self._db.execute(
                select(KnowledgeDocument).where(KnowledgeDocument.id == document_id, KnowledgeDocument.owner_id == owner_id)
            )
        ).scalar_one_or_none()
        if row is None:
            raise OwnDocumentNotFoundError()
        return row

    async def _check_room(self, owner_id: uuid.UUID, *, adding_bytes: int, replacing_id: uuid.UUID | None, new_document: bool) -> None:
        if new_document:
            count = (await self._db.execute(select(func.count()).select_from(KnowledgeDocument).where(KnowledgeDocument.owner_id == owner_id))).scalar_one()
            if count >= rules.MAX_DOCUMENTS:
                raise OwnDocumentError("TOO_MANY_DOCUMENTS", f"at most {rules.MAX_DOCUMENTS} documents")
        if adding_bytes:
            stmt = select(func.coalesce(func.sum(KnowledgeDocument.file_size), 0)).where(KnowledgeDocument.owner_id == owner_id)
            if replacing_id is not None:
                stmt = stmt.where(KnowledgeDocument.id != replacing_id)
            used = (await self._db.execute(stmt)).scalar_one()
            if used + adding_bytes > rules.MAX_TOTAL_FILE_BYTES:
                raise OwnDocumentError("STORAGE_FULL", "the files of the documents fill the space given to them", "file")

    @staticmethod
    def _prepared_file(new_file: NewFile | None) -> tuple[str, str, bytes] | None:
        if new_file is None:
            return None
        rules.check_file(new_file.content)
        mime, extension = rules.sniff_file(new_file.content)
        return rules.safe_filename(new_file.announced_name, extension), mime, new_file.content

    async def create(self, owner_id: uuid.UUID, fields: DocumentFields, new_file: NewFile | None) -> KnowledgeDocument:
        prepared = self._prepared_file(new_file)
        if fields.body is None and fields.source_url is None and prepared is None:
            raise OwnDocumentError("CONTENT_REQUIRED", "a text, a link or a file is required")
        await self._check_room(owner_id, adding_bytes=len(prepared[2]) if prepared else 0, replacing_id=None, new_document=True)
        row = KnowledgeDocument(
            owner_id=owner_id, title=fields.title, kind=fields.kind, source_url=fields.source_url, doc_date=fields.doc_date,
            when_to_use=fields.when_to_use, body=fields.body, tags=fields.tags,
        )
        if prepared:
            row.file_name, row.file_mime, row.file_size = prepared[0], prepared[1], len(prepared[2])
        self._db.add(row)
        await self._db.flush()
        if prepared:
            self._db.add(KnowledgeDocumentFile(document_id=row.id, content=prepared[2]))
        await self._db.commit()
        await self._db.refresh(row)
        return row

    async def update(
        self, owner_id: uuid.UUID, document_id: uuid.UUID, fields: DocumentFields, new_file: NewFile | None, remove_file: bool
    ) -> KnowledgeDocument:
        row = await self.get(owner_id, document_id)
        prepared = self._prepared_file(new_file)
        keeps_file = prepared is not None or (row.file_name is not None and not remove_file)
        if fields.body is None and fields.source_url is None and not keeps_file:
            raise OwnDocumentError("CONTENT_REQUIRED", "a text, a link or a file is required")
        if prepared:
            await self._check_room(owner_id, adding_bytes=len(prepared[2]), replacing_id=row.id, new_document=False)
        row.title, row.kind, row.source_url, row.doc_date = fields.title, fields.kind, fields.source_url, fields.doc_date
        row.when_to_use, row.body, row.tags = fields.when_to_use, fields.body, fields.tags
        if prepared:
            await self._db.execute(delete(KnowledgeDocumentFile).where(KnowledgeDocumentFile.document_id == row.id))
            row.file_name, row.file_mime, row.file_size = prepared[0], prepared[1], len(prepared[2])
            self._db.add(KnowledgeDocumentFile(document_id=row.id, content=prepared[2]))
        elif remove_file and row.file_name is not None:
            await self._db.execute(delete(KnowledgeDocumentFile).where(KnowledgeDocumentFile.document_id == row.id))
            row.file_name = row.file_mime = row.file_size = None
        await self._db.commit()
        await self._db.refresh(row)
        return row

    async def delete(self, owner_id: uuid.UUID, document_id: uuid.UUID) -> None:
        row = await self.get(owner_id, document_id)
        await self._db.execute(delete(KnowledgeDocumentFile).where(KnowledgeDocumentFile.document_id == row.id))
        await self._db.delete(row)
        await self._db.commit()

    async def file(self, owner_id: uuid.UUID, document_id: uuid.UUID) -> StoredFile:
        row = await self.get(owner_id, document_id)
        if row.file_name is None or row.file_mime is None:
            raise OwnDocumentError("KNOWLEDGE_DOCUMENT_HAS_NO_FILE", "the document has no file")
        content = (
            await self._db.execute(select(KnowledgeDocumentFile.content).where(KnowledgeDocumentFile.document_id == row.id))
        ).scalar_one_or_none()
        if content is None:
            raise OwnDocumentError("KNOWLEDGE_DOCUMENT_HAS_NO_FILE", "the file of the document is missing")
        return StoredFile(row.file_name, row.file_mime, bytes(content))
