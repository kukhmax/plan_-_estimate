"""The contract of an object (Stage 16E).

One row per version of the contract of one object. `answers` holds what the owner answered in the questionnaire "compose the
contract" (a number, a date or a person is an answer, never part of a catalogue); `questionnaire_version` pins the questionnaire
those answers belong to. States: DRAFT (editable, at most one per object) -> ISSUED (conditions frozen, 16E.2) -> SIGNED -> ARCHIVED;
a changed contract is a new version, never an edit of an issued one. Nothing is deleted.
"""
import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON as GenericJSON

from app.core.database import Base

_JSONVariant = JSONB().with_variant(GenericJSON(), "sqlite")


class ContractStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    SIGNED = "SIGNED"
    ARCHIVED = "ARCHIVED"


class Contract(Base):
    __tablename__ = "contracts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=ContractStatus.DRAFT.value)
    answers: Mapped[dict] = mapped_column(_JSONVariant, nullable=False, default=dict)
    questionnaire_version: Mapped[int] = mapped_column(Integer, nullable=False)
    # what an issued contract freezes (16E.2): the time, the conditions, the exact page, the estimate that priced it
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    snapshot: Mapped[dict | None] = mapped_column(_JSONVariant, nullable=True)
    document_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    estimate_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    estimate_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        CheckConstraint("status IN ('DRAFT', 'ISSUED', 'SIGNED', 'ARCHIVED')", name="ck_contracts_status"),
        CheckConstraint("version >= 1", name="ck_contracts_version_positive"),
        CheckConstraint(
            "status NOT IN ('ISSUED', 'SIGNED') OR (issued_at IS NOT NULL AND snapshot IS NOT NULL AND document_html IS NOT NULL)",
            name="ck_contracts_frozen_when_issued",
        ),
        UniqueConstraint("project_id", "version", name="uq_contracts_project_version"),
        Index(
            "uq_contracts_one_draft", "project_id", unique=True,
            postgresql_where=text("status = 'DRAFT'"), sqlite_where=text("status = 'DRAFT'"),
        ),
        Index("ix_contracts_project", "project_id", "status"),
    )
