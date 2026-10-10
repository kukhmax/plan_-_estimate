"""The protocol of acceptance of the work, partial or final (Stage 16H): the surfaces of the chosen rooms are assessed and the result is
**derived**, never typed.

One row per acceptance event of one object (`sequence` counts them, the rooms being accepted one after another or all at once;
whether it is partial or final follows from the rooms in scope). The row holds the day, the people present -- or the days the
absent customer was notified (contract § 14 ust. 5) --, the rooms in scope, the conditions of the assessment, the tools used, the
**remarks per surface** (place, description, class removable / significant, deadline, photos) and the things the contract asks the
protocol to carry (batches of the materials, the instruction of use, the amount due and the amount retained). The result of a surface
and of the whole follows from the completeness of the works and the classes of the remarks (plan, section 5). States: DRAFT (at most
one per object) -> ISSUED (frozen: the time, the snapshot, the exact page and the contract) -> ARCHIVED. Nothing is deleted.
"""
import enum
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON as GenericJSON

from app.core.database import Base

_JSONVariant = JSONB().with_variant(GenericJSON(), "sqlite")


class AcceptanceStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    ARCHIVED = "ARCHIVED"


class AcceptanceProtocol(Base):
    __tablename__ = "acceptance_protocols"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=AcceptanceStatus.DRAFT.value)
    held_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    held_time: Mapped[str | None] = mapped_column(String(5), nullable=True)  # "HH:MM", optional
    customer_absent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notified_on: Mapped[date | None] = mapped_column(Date, nullable=True)  # the first call to the acceptance
    renotified_on: Mapped[date | None] = mapped_column(Date, nullable=True)  # the second call, with an additional term (contract § 14 ust. 5)
    attendees: Mapped[list] = mapped_column(_JSONVariant, nullable=False, default=list)
    room_ids: Mapped[list] = mapped_column(_JSONVariant, nullable=False, default=list)  # the rooms in scope
    conditions_note: Mapped[str | None] = mapped_column(Text, nullable=True)  # the conditions agreed before the work (S4)
    instrument_keys: Mapped[list] = mapped_column(_JSONVariant, nullable=False, default=list)  # keys of the catalogue of instruments
    surfaces: Mapped[dict] = mapped_column(_JSONVariant, nullable=False, default=dict)  # per surface: assessed + remarks
    batches: Mapped[str | None] = mapped_column(Text, nullable=True)
    instructions_given: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    amount_due: Mapped[str | None] = mapped_column(String(16), nullable=True)  # "1234.50", the owner's number
    amount_retained: Mapped[str | None] = mapped_column(String(16), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # what an issued protocol freezes
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    snapshot: Mapped[dict | None] = mapped_column(_JSONVariant, nullable=True)
    document_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    contract_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    contract_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        CheckConstraint("status IN ('DRAFT', 'ISSUED', 'ARCHIVED')", name="ck_acceptance_protocols_status"),
        CheckConstraint("sequence >= 1", name="ck_acceptance_protocols_sequence_positive"),
        CheckConstraint(
            "status <> 'ISSUED' OR (issued_at IS NOT NULL AND snapshot IS NOT NULL AND document_html IS NOT NULL)",
            name="ck_acceptance_protocols_frozen_when_issued",
        ),
        UniqueConstraint("project_id", "sequence", name="uq_acceptance_protocols_project_sequence"),
        Index(
            "uq_acceptance_protocols_one_draft", "project_id", unique=True,
            postgresql_where=text("status = 'DRAFT'"), sqlite_where=text("status = 'DRAFT'"),
        ),
        Index("ix_acceptance_protocols_project", "project_id", "status"),
    )
