"""Schemas of the archived contracts and protocols and their final deletion (archive of documents, AC-6)."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

DocumentKind = Literal["CONTRACT", "HANDOVER", "CONCEALED", "ACCEPTANCE", "DECISION", "DOWNTIME"]


class ArchivedDocumentItem(BaseModel):
    kind: DocumentKind
    id: uuid.UUID
    project_id: uuid.UUID
    project_name: str
    ordinal: int  # version of a contract, sequence of a protocol or an episode
    number: str | None  # null: a draft that was never issued
    issued_at: datetime | None
    archived_at: datetime


class ArchivedDocumentsResponse(BaseModel):
    items: list[ArchivedDocumentItem]
    total: int  # the list holds the first 200; the total is whole


class DocumentPurgePreview(BaseModel):
    """What deleting the archived record for good would do -- computed by the server, no side effects."""

    kind: DocumentKind
    target_id: uuid.UUID
    ordinal: int
    archived: bool
    issued: bool
    can_purge: bool
    journal_lines: int  # lines of the journal of issued documents: they stay
    dependents: int  # of a contract: protocols and episodes (not archived) that refer to it; while there are any it is refused


class DocumentPurgeResult(BaseModel):
    purged: bool
