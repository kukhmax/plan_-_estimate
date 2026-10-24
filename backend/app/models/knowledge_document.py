"""A document of the owner's own in the knowledge base (V2-7a): a norm, a data sheet of a material, a template, a note -- kept next to the
approved entries of the catalogue, but never mixed with them and never printed in a document for the client.

Plain owner data (the owner's reference material, not data about a client): the text, the title and the tags are ordinary columns. The file
(a PDF or a photo of a page, at most 10 MB) lives in its own table so that the list of documents never reads the bytes.
"""
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.core.database import Base

KINDS = ("STATUTE", "NORM", "MANUFACTURER", "TEMPLATE", "OTHER")
_JSONList = JSONB().with_variant(JSON(), "sqlite")


def _now() -> datetime:
    return datetime.now(UTC)


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        CheckConstraint("kind IN ('STATUTE', 'NORM', 'MANUFACTURER', 'TEMPLATE', 'OTHER')", name="ck_knowledge_documents_kind"),
        CheckConstraint("length(trim(title)) > 0", name="ck_knowledge_documents_title_not_blank"),
        CheckConstraint("body IS NOT NULL OR source_url IS NOT NULL OR file_name IS NOT NULL", name="ck_knowledge_documents_has_content"),
        CheckConstraint(
            "(file_name IS NULL AND file_mime IS NULL AND file_size IS NULL) OR (file_name IS NOT NULL AND file_mime IS NOT NULL AND file_size > 0)",
            name="ck_knowledge_documents_file_together",
        ),
        Index("ix_knowledge_documents_owner_updated", "owner_id", "updated_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="OTHER")
    source_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    doc_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # "up to date as of": when the document was issued / checked
    when_to_use: Mapped[str | None] = mapped_column(Text, nullable=True)  # the owner's own words: when this document helps
    body: Mapped[str | None] = mapped_column(Text, nullable=True)  # the text, typed or pasted
    tags: Mapped[list] = mapped_column(_JSONList, nullable=False, default=list)
    file_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    file_mime: Mapped[str | None] = mapped_column(String(32), nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class KnowledgeDocumentFile(Base):
    __tablename__ = "knowledge_document_files"

    document_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("knowledge_documents.id", ondelete="CASCADE"), primary_key=True)
    content: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
