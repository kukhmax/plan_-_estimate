"""Journal of issued client documents (Stage 15F).

One row per issue attempt of an estimate, a photo report, a technological card, a production plan or a contract. No file is stored (owner decision): the row says what was issued,
under which number, with which template version, how big it is and its checksum. `number` (date-time based, unique per owner)
and `project_seq` (the running number of the documents of one object, unique per owner and project) are given when the
attempt starts, under a lock on the project row, so a failed attempt keeps its number and stays visible as FAILED.
"""
import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON as GenericJSON

from app.core.database import Base

_JSONVariant = JSONB().with_variant(GenericJSON(), "sqlite")


class IssuedDocumentKind(str, enum.Enum):
    ESTIMATE = "ESTIMATE"
    PHOTO_REPORT = "PHOTO_REPORT"
    TECH_CARD = "TECH_CARD"
    PRODUCTION_PLAN = "PRODUCTION_PLAN"
    CONTRACT = "CONTRACT"
    HANDOVER_PROTOCOL = "HANDOVER_PROTOCOL"
    CONCEALED_WORKS_PROTOCOL = "CONCEALED_WORKS_PROTOCOL"
    FINAL_PROTOCOL = "FINAL_PROTOCOL"
    DECISION_PROTOCOL = "DECISION_PROTOCOL"
    DOWNTIME_NOTICE = "DOWNTIME_NOTICE"
    DOWNTIME_PROTOCOL = "DOWNTIME_PROTOCOL"


class IssuedDocumentStatus(str, enum.Enum):
    PENDING = "PENDING"  # reserved; rendering or sending is in progress
    SENT = "SENT"
    FAILED = "FAILED"


class IssuedDocument(Base):
    __tablename__ = "issued_documents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    client_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    source_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    number: Mapped[str] = mapped_column(String(64), nullable=False)
    project_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    template_version: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    scope: Mapped[dict | None] = mapped_column(_JSONVariant, nullable=True)
    pages: Mapped[int | None] = mapped_column(Integer, nullable=True)
    byte_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        CheckConstraint("kind IN ('ESTIMATE', 'PHOTO_REPORT', 'TECH_CARD', 'PRODUCTION_PLAN', 'CONTRACT', 'HANDOVER_PROTOCOL', 'CONCEALED_WORKS_PROTOCOL', 'FINAL_PROTOCOL', 'DECISION_PROTOCOL', 'DOWNTIME_NOTICE', 'DOWNTIME_PROTOCOL')", name="ck_issued_documents_kind"),
        CheckConstraint("status IN ('PENDING', 'SENT', 'FAILED')", name="ck_issued_documents_status"),
        CheckConstraint("project_seq >= 1", name="ck_issued_documents_seq_positive"),
        CheckConstraint("length(number) > 0", name="ck_issued_documents_number_not_empty"),
        UniqueConstraint("owner_id", "number", name="uq_issued_documents_owner_number"),
        UniqueConstraint("owner_id", "project_id", "project_seq", name="uq_issued_documents_project_seq"),
        Index("ix_issued_documents_project_issued", "project_id", "issued_at"),
    )
