"""The protocol of information and decisions of the customer (Stage 16I; annex 9 of the contract).

When the contractor recommends a technological solution (priming, fleece, drying, a longer technological break ...) and the customer
declines it -- or demands the work done against it --, the parties write it down: what was recommended, the risk in plain language, the
decision, who was present. One row per sitting of one object (`sequence` counts them); the **items** (a risk the application found, or
a recommendation the contractor writes himself) each carry their own decision. The consequences for the guarantee stay in the contract
(`§ 16 ust. 3 lit. f`), which the protocol points at. States: DRAFT (at most one per object) -> ISSUED (frozen: the time, the snapshot,
the exact page and the contract) -> ARCHIVED. Nothing is deleted.
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


class DecisionStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    ARCHIVED = "ARCHIVED"


class DecisionProtocol(Base):
    __tablename__ = "decision_protocols"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=DecisionStatus.DRAFT.value)
    held_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    held_time: Mapped[str | None] = mapped_column(String(5), nullable=True)  # "HH:MM", optional
    attendees: Mapped[list] = mapped_column(_JSONVariant, nullable=False, default=list)
    # an ordered list of items: {id, source RISK / OWN, risk_id | room_id + title + recommendation + consequence + price, decision, ...}
    items: Mapped[list] = mapped_column(_JSONVariant, nullable=False, default=list)
    understood: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # the customer declares he understood and could ask
    signature_refused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # the customer did not sign (the reason is in the notes)
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
        CheckConstraint("status IN ('DRAFT', 'ISSUED', 'ARCHIVED')", name="ck_decision_protocols_status"),
        CheckConstraint("sequence >= 1", name="ck_decision_protocols_sequence_positive"),
        CheckConstraint(
            "status <> 'ISSUED' OR (issued_at IS NOT NULL AND snapshot IS NOT NULL AND document_html IS NOT NULL)",
            name="ck_decision_protocols_frozen_when_issued",
        ),
        UniqueConstraint("project_id", "sequence", name="uq_decision_protocols_project_sequence"),
        Index(
            "uq_decision_protocols_one_draft", "project_id", unique=True,
            postgresql_where=text("status = 'DRAFT'"), sqlite_where=text("status = 'DRAFT'"),
        ),
        Index("ix_decision_protocols_project", "project_id", "status"),
    )
