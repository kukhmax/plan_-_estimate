"""Schemas of the owner's own documents of the knowledge base (V2-7a)."""
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

DocumentKind = Literal["STATUTE", "NORM", "MANUFACTURER", "TEMPLATE", "OTHER"]


class KnowledgeDocumentListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    kind: DocumentKind
    source_url: str | None
    doc_date: date | None
    tags: list[str]
    file_name: str | None
    file_mime: str | None
    file_size: int | None
    has_text: bool
    snippet: str | None
    updated_at: datetime


class KnowledgeDocumentRead(KnowledgeDocumentListItem):
    when_to_use: str | None
    body: str | None
    created_at: datetime


class KnowledgeDocumentList(BaseModel):
    items: list[KnowledgeDocumentListItem]
    total: int
    max_documents: int
    max_file_bytes: int
