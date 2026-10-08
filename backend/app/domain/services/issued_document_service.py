"""The journal of issued documents and their numbers (Stage 15F.1).

A number is given when an attempt starts, not when it ends: the document has to print it. Two numbers are given together,
under a lock on the owner's row, so simultaneous issues can never share either:

- `number`: the type, the date and the time of issue in Polish local time, `KOSZ/2026/10/08/1953`; a second document of the
  same kind in the same minute gets `-2`, `-3`, ... (unique per owner);
- `project_seq`: the running number of the documents of one object (1, 2, 3, ...), whatever their kind.

A failed attempt keeps its number and stays in the journal as FAILED (no number disappears without a trace). A second tap
while the same document is still being made returns the same row instead of a second one. A PENDING attempt older than
`PENDING_TTL` (the server restarted in the middle of it) is FAILED with the code INTERRUPTED.
"""
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.documents.formatting import POLAND
from app.domain.exceptions import IssuedDocumentNotFoundError, ProjectNotFoundError
from app.models.issued_document import (
    IssuedDocument,
    IssuedDocumentKind,
    IssuedDocumentStatus,
)
from app.models.project import Project
from app.models.user import User

PENDING_TTL = timedelta(minutes=15)
NUMBER_PREFIX: dict[IssuedDocumentKind, str] = {
    IssuedDocumentKind.ESTIMATE: "KOSZ",
    IssuedDocumentKind.PHOTO_REPORT: "FOTO",
}


def number_base(kind: IssuedDocumentKind, issued_at: datetime) -> str:
    """`KOSZ/2026/10/08/1953`: the kind and the Polish local date and time (to the minute) of the issue."""
    moment = (issued_at if issued_at.tzinfo else issued_at.replace(tzinfo=UTC)).astimezone(POLAND)
    return f"{NUMBER_PREFIX[kind]}/{moment:%Y/%m/%d/%H%M}"


def scope_key(scope: dict | None) -> str:
    """A stable text for the scope of a document (the rooms of a part of a report), to recognise the same request again."""
    return json.dumps(scope, sort_keys=True, default=str) if scope else ""


def _utc(value: datetime | None) -> datetime | None:
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class Reservation:
    document: IssuedDocument
    reused: bool  # the same document is already being made: this is its row, nothing new was started


class IssuedDocumentService:
    def __init__(self, db: AsyncSession, *, clock=lambda: datetime.now(UTC)) -> None:
        self.db = db
        self.clock = clock

    async def reserve(
        self,
        owner_id: uuid.UUID,
        project_id: uuid.UUID,
        kind: IssuedDocumentKind,
        *,
        title: str,
        template_version: str,
        source_id: uuid.UUID | None = None,
        source_version: int | None = None,
        client_id: uuid.UUID | None = None,
        scope: dict | None = None,
    ) -> Reservation:
        """Start an attempt: expire stale ones, return the live attempt of the same document if there is one, else give the
        next numbers and write a PENDING row. Raises ProjectNotFoundError for a project that is not the owner's."""
        # The numbers are the owner's (a time number is unique per owner), so the lock is on the owner's row: two objects of
        # one owner issued at the same moment must not both take the same number. Documents are issued rarely and the lock is
        # held only for the few statements below, never while a document is rendered or sent.
        locked = (
            await self.db.execute(select(User.id).where(User.id == owner_id).with_for_update())
        ).scalar_one_or_none()
        project = (
            await self.db.execute(select(Project.id).where(Project.id == project_id, Project.owner_id == owner_id))
        ).scalar_one_or_none()
        if locked is None or project is None:
            await self.db.rollback()
            raise ProjectNotFoundError(f"Project {project_id} not found")
        now = self.clock()
        await self._expire_stale(owner_id, project_id, now)

        pending = (
            await self.db.execute(
                select(IssuedDocument).where(
                    IssuedDocument.owner_id == owner_id,
                    IssuedDocument.project_id == project_id,
                    IssuedDocument.kind == kind.value,
                    IssuedDocument.status == IssuedDocumentStatus.PENDING.value,
                )
            )
        ).scalars().all()
        for row in pending:
            if row.source_id == source_id and scope_key(row.scope) == scope_key(scope):
                await self.db.commit()
                return Reservation(row, reused=True)

        seq = (
            await self.db.execute(
                select(func.max(IssuedDocument.project_seq)).where(
                    IssuedDocument.owner_id == owner_id, IssuedDocument.project_id == project_id
                )
            )
        ).scalar_one() or 0
        base = number_base(kind, now)
        taken = set(
            (
                await self.db.execute(
                    select(IssuedDocument.number).where(
                        IssuedDocument.owner_id == owner_id, IssuedDocument.number.like(f"{base}%")
                    )
                )
            ).scalars()
        )
        number, suffix = base, 1
        while number in taken:
            suffix += 1
            number = f"{base}-{suffix}"
        document = IssuedDocument(
            owner_id=owner_id,
            project_id=project_id,
            client_id=client_id,
            kind=kind.value,
            source_id=source_id,
            source_version=source_version,
            title=title[:255],
            number=number,
            project_seq=seq + 1,
            template_version=template_version,
            status=IssuedDocumentStatus.PENDING.value,
            scope=scope,
            issued_at=now,
        )
        self.db.add(document)
        await self.db.commit()
        await self.db.refresh(document)
        return Reservation(document, reused=False)

    async def mark_sent(self, owner_id: uuid.UUID, document_id: uuid.UUID, *, pages: int, byte_size: int, sha256: str) -> IssuedDocument:
        document = await self._owned(owner_id, document_id)
        document.status = IssuedDocumentStatus.SENT.value
        document.error_code = None
        document.pages, document.byte_size, document.sha256 = pages, byte_size, sha256
        document.sent_at = self.clock()
        await self.db.commit()
        await self.db.refresh(document)
        return document

    async def mark_failed(self, owner_id: uuid.UUID, document_id: uuid.UUID, code: str) -> IssuedDocument:
        document = await self._owned(owner_id, document_id)
        document.status = IssuedDocumentStatus.FAILED.value
        document.error_code = code[:64]
        await self.db.commit()
        await self.db.refresh(document)
        return document

    async def get(self, owner_id: uuid.UUID, project_id: uuid.UUID, document_id: uuid.UUID) -> IssuedDocument:
        await self._expire_stale(owner_id, project_id, self.clock())
        await self.db.commit()
        document = (
            await self.db.execute(
                select(IssuedDocument).where(
                    IssuedDocument.id == document_id,
                    IssuedDocument.owner_id == owner_id,
                    IssuedDocument.project_id == project_id,
                )
            )
        ).scalar_one_or_none()
        if document is None:
            raise IssuedDocumentNotFoundError(f"Document {document_id} not found")
        return document

    async def list_for_project(self, owner_id: uuid.UUID, project_id: uuid.UUID, *, limit: int = 100) -> list[IssuedDocument]:
        """Newest first. Raises ProjectNotFoundError for a project that is not the owner's."""
        owned = (
            await self.db.execute(select(Project.id).where(Project.id == project_id, Project.owner_id == owner_id))
        ).scalar_one_or_none()
        if owned is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")
        await self._expire_stale(owner_id, project_id, self.clock())
        await self.db.commit()
        rows = (
            await self.db.execute(
                select(IssuedDocument)
                .where(IssuedDocument.owner_id == owner_id, IssuedDocument.project_id == project_id)
                .order_by(IssuedDocument.project_seq.desc())
                .limit(limit)
            )
        ).scalars()
        return list(rows)

    async def _owned(self, owner_id: uuid.UUID, document_id: uuid.UUID) -> IssuedDocument:
        document = (
            await self.db.execute(
                select(IssuedDocument).where(IssuedDocument.id == document_id, IssuedDocument.owner_id == owner_id)
            )
        ).scalar_one_or_none()
        if document is None:
            raise IssuedDocumentNotFoundError(f"Document {document_id} not found")
        return document

    async def _expire_stale(self, owner_id: uuid.UUID, project_id: uuid.UUID, now: datetime) -> None:
        await self.db.execute(
            update(IssuedDocument)
            .where(
                IssuedDocument.owner_id == owner_id,
                IssuedDocument.project_id == project_id,
                IssuedDocument.status == IssuedDocumentStatus.PENDING.value,
                IssuedDocument.issued_at < _utc(now) - PENDING_TTL,
            )
            .values(status=IssuedDocumentStatus.FAILED.value, error_code="INTERRUPTED")
            .execution_options(synchronize_session="fetch")
        )
