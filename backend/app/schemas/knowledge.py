"""The knowledge base over HTTP (Stage 17B), read only. The catalogue models are the content; these are the envelopes."""

from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.domain.knowledge.catalog import Entry, Link, Situation, Source


class KnowledgeMetaRead(BaseModel):
    version: int
    updated_on: date
    disclaimer_pl: str | None
    disclaimer_ru: str | None
    disclaimer_status: Literal["DRAFT", "APPROVED"]
    sources: int
    entries: int
    situations: int


class KnowledgeEntryListItem(BaseModel):
    """A row of the list: what the owner needs to choose an entry (Q6: a list of titles first, the details on tap)."""

    code: str
    kind: Literal["STATUTE", "NORM", "ITB", "OTHER"]
    source: str
    source_designation: str
    locator: str | None
    title_pl: str
    title_ru: str
    status: Literal["DRAFT", "APPROVED"]
    tags: list[str]


class KnowledgeEntryList(BaseModel):
    items: list[KnowledgeEntryListItem]
    total: int


class KnowledgeEntryRead(BaseModel):
    entry: Entry
    source: Source
    # where the application points at this entry (risks, clauses, phrases, documents)
    linked_from: list[Link]


class KnowledgeSituationListItem(BaseModel):
    code: str
    title_pl: str
    title_ru: str
    status: Literal["DRAFT", "APPROVED"]


class KnowledgeSituationList(BaseModel):
    items: list[KnowledgeSituationListItem]


class KnowledgeLinkRead(BaseModel):
    target_kind: Literal["RISK", "CLAUSE", "PHRASE", "DOCUMENT"]
    target: str
    entries: list[KnowledgeEntryListItem]


class KnowledgeLinkIndex(BaseModel):
    """Every place of the application that points at the knowledge base, in one answer (Stage 17E): the screens ask once."""

    items: list[KnowledgeLinkRead]


__all__ = [
    "KnowledgeEntryList",
    "KnowledgeEntryListItem",
    "KnowledgeEntryRead",
    "KnowledgeLinkIndex",
    "KnowledgeLinkRead",
    "KnowledgeMetaRead",
    "KnowledgeSituationList",
    "KnowledgeSituationListItem",
    "Situation",
]
