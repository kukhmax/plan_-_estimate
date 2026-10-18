"""The archived contracts and protocols of all objects and their final deletion (archive of documents, AC-6).

The six records that are put into the archive instead of being deleted (the contract, the protocols of handover, concealed works,
acceptance and decision, the downtime episode) are listed in ONE place with their object, so the owner sees what is there and can
delete it for good. Listed: an archived record of an object that is in work; nothing of an archived object (it returns, or goes,
together with the object). Only the data of the card are shown: the page of an issued document is not kept for reading, the PDF is in
the chat it was sent to. The lines of the journal of issued documents stay (they are deleted on their own, DJ-1).

Only an ARCHIVED record can be deleted. A contract that a protocol or an episode which is not archived still refers to is refused
(the protocols are first archived or deleted); the references of archived ones stay as plain values, nothing else points to a record.
The list is sorted by the date it was archived, which is `updated_at` of the record: the object name is ciphertext, it is not sorted by.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import ArchivedDocumentInUseError, ArchivedDocumentNotArchivedError, ArchivedDocumentNotFoundError
from app.models.acceptance_protocol import AcceptanceProtocol, AcceptanceStatus
from app.models.concealed_works_protocol import ConcealedStatus, ConcealedWorksProtocol
from app.models.contract import Contract, ContractStatus
from app.models.decision_protocol import DecisionProtocol, DecisionStatus
from app.models.downtime_episode import DowntimeEpisode, DowntimeStatus
from app.models.handover_protocol import HandoverProtocol, HandoverStatus
from app.models.issued_document import IssuedDocument, IssuedDocumentKind
from app.models.project import Project

LIMIT = 200

# kind of the archive -> (model, value of the ARCHIVED status, kinds of the journal lines of the record)
_KINDS: dict[str, tuple[type, str, tuple[str, ...]]] = {
    "CONTRACT": (Contract, ContractStatus.ARCHIVED.value, (IssuedDocumentKind.CONTRACT.value,)),
    "HANDOVER": (HandoverProtocol, HandoverStatus.ARCHIVED.value, (IssuedDocumentKind.HANDOVER_PROTOCOL.value,)),
    "CONCEALED": (ConcealedWorksProtocol, ConcealedStatus.ARCHIVED.value, (IssuedDocumentKind.CONCEALED_WORKS_PROTOCOL.value,)),
    "ACCEPTANCE": (AcceptanceProtocol, AcceptanceStatus.ARCHIVED.value, (IssuedDocumentKind.FINAL_PROTOCOL.value,)),
    "DECISION": (DecisionProtocol, DecisionStatus.ARCHIVED.value, (IssuedDocumentKind.DECISION_PROTOCOL.value,)),
    "DOWNTIME": (
        DowntimeEpisode, DowntimeStatus.ARCHIVED.value,
        (IssuedDocumentKind.DOWNTIME_NOTICE.value, IssuedDocumentKind.DOWNTIME_PROTOCOL.value),
    ),
}
KINDS = tuple(_KINDS)


@dataclass(frozen=True, slots=True)
class ArchivedDocument:
    kind: str
    id: uuid.UUID
    project_id: uuid.UUID
    project_name: str
    ordinal: int  # the version of a contract, the sequence of a protocol or an episode
    number: str | None  # the number of the issued document (null for a draft that was never issued)
    issued_at: datetime | None
    archived_at: datetime


@dataclass(frozen=True, slots=True)
class ArchivedDocuments:
    items: list[ArchivedDocument]
    total: int


@dataclass(frozen=True, slots=True)
class DocumentPurgePreview:
    kind: str
    target_id: uuid.UUID
    ordinal: int
    archived: bool
    issued: bool
    journal_lines: int  # the lines of the journal of issued documents: they stay
    dependents: int  # of a contract: the protocols and episodes (not archived) that refer to it: they block the deletion

    @property
    def can_purge(self) -> bool:
        return self.archived and self.dependents == 0


def _ordinal(kind: str, row: object) -> int:
    return int(row.version if kind == "CONTRACT" else row.sequence)  # type: ignore[attr-defined]


def _issued_at(kind: str, row: object) -> datetime | None:
    if kind == "DOWNTIME":
        return row.notice_issued_at or row.protocol_issued_at  # type: ignore[attr-defined]
    return row.issued_at  # type: ignore[attr-defined]


class ArchivedDocumentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # -- the list -------------------------------------------------------------------

    async def list_archived(self, owner_id: uuid.UUID) -> ArchivedDocuments:
        found: list[tuple[str, object, str]] = []
        total = 0
        for kind, (model, archived, _journal) in _KINDS.items():
            where = (model.owner_id == owner_id, model.status == archived, Project.is_archived.is_(False))
            rows = (await self.db.execute(
                select(model, Project.name).join(Project, Project.id == model.project_id).where(*where)
                .order_by(model.updated_at.desc(), model.id.desc()).limit(LIMIT)
            )).all()
            total += int((await self.db.execute(
                select(func.count()).select_from(model).join(Project, Project.id == model.project_id).where(*where)
            )).scalar_one())
            found.extend((kind, row[0], row[1]) for row in rows)
        found.sort(key=lambda item: (item[1].updated_at, str(item[1].id)), reverse=True)
        found = found[:LIMIT]
        numbers = await self._numbers([(kind, row) for kind, row, _name in found])
        return ArchivedDocuments(
            [
                ArchivedDocument(
                    kind=kind, id=row.id, project_id=row.project_id, project_name=name, ordinal=_ordinal(kind, row),
                    number=getattr(row, "notice_number", None) or numbers.get((kind, row.id)),
                    issued_at=_issued_at(kind, row), archived_at=row.updated_at,
                )
                for kind, row, name in found
            ],
            total,
        )

    async def _numbers(self, rows: list[tuple[str, object]]) -> dict[tuple[str, uuid.UUID], str]:
        """The number from the journal of the issued document of a record (the newest line when there are several)."""
        if not rows:
            return {}
        ids = {row.id for _kind, row in rows}  # type: ignore[attr-defined]
        lines = (await self.db.execute(
            select(IssuedDocument.source_id, IssuedDocument.kind, IssuedDocument.number)
            .where(IssuedDocument.source_id.in_(ids)).order_by(IssuedDocument.issued_at.asc())
        )).all()
        by_source = {(source_id, journal_kind): number for source_id, journal_kind, number in lines}
        out: dict[tuple[str, uuid.UUID], str] = {}
        for kind, row in rows:
            for journal_kind in _KINDS[kind][2]:
                number = by_source.get((row.id, journal_kind))  # type: ignore[attr-defined]
                if number is not None:
                    out[(kind, row.id)] = number  # type: ignore[attr-defined]
        return out

    # -- preview ----------------------------------------------------------------------

    async def _record(self, owner_id: uuid.UUID, kind: str, record_id: uuid.UUID, *, lock: bool = False) -> object:
        if kind not in _KINDS:
            raise ArchivedDocumentNotFoundError(f"unknown kind {kind}")
        model = _KINDS[kind][0]
        stmt = select(model).where(model.id == record_id, model.owner_id == owner_id)
        if lock:
            stmt = stmt.with_for_update()
        row = (await self.db.execute(stmt)).scalar_one_or_none()
        if row is None:
            raise ArchivedDocumentNotFoundError(f"{kind} {record_id} not found")
        return row

    async def _dependents(self, owner_id: uuid.UUID, contract_id: uuid.UUID) -> int:
        count = 0
        for kind, (model, archived, _journal) in _KINDS.items():
            if kind == "CONTRACT":
                continue
            count += int((await self.db.execute(
                select(func.count()).select_from(model)
                .where(model.owner_id == owner_id, model.contract_id == contract_id, model.status != archived)
            )).scalar_one())
        return count

    async def preview(self, owner_id: uuid.UUID, kind: str, record_id: uuid.UUID) -> DocumentPurgePreview:
        row = await self._record(owner_id, kind, record_id)
        journal_lines = int((await self.db.execute(
            select(func.count()).select_from(IssuedDocument)
            .where(IssuedDocument.owner_id == owner_id, IssuedDocument.source_id == row.id, IssuedDocument.kind.in_(_KINDS[kind][2]))  # type: ignore[attr-defined]
        )).scalar_one())
        dependents = await self._dependents(owner_id, row.id) if kind == "CONTRACT" else 0  # type: ignore[attr-defined]
        return DocumentPurgePreview(
            kind=kind, target_id=row.id, ordinal=_ordinal(kind, row),  # type: ignore[attr-defined]
            archived=row.status == _KINDS[kind][1], issued=_issued_at(kind, row) is not None,  # type: ignore[attr-defined]
            journal_lines=journal_lines, dependents=dependents,
        )

    # -- purge --------------------------------------------------------------------------

    async def purge(self, owner_id: uuid.UUID, kind: str, record_id: uuid.UUID) -> None:
        row = await self._record(owner_id, kind, record_id, lock=True)
        if row.status != _KINDS[kind][1]:  # type: ignore[attr-defined]
            raise ArchivedDocumentNotArchivedError("only an archived record can be deleted for good")
        if kind == "CONTRACT":
            dependents = await self._dependents(owner_id, row.id)  # type: ignore[attr-defined]
            if dependents:
                raise ArchivedDocumentInUseError(dependents)
        await self.db.execute(delete(_KINDS[kind][0]).where(_KINDS[kind][0].id == record_id, _KINDS[kind][0].owner_id == owner_id))
        await self.db.commit()
