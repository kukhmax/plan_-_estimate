"""The protocol of handing over the premises (Stage 16F): the state of each room before the work starts.

One row per handover of one object (`sequence` counts them: premises may be handed over in parts, room by room, on different days).
The row holds the day, the people present (copied by name from the register of persons, so a later change there never rewrites a
protocol), the state of every requirement for the premises per room (`rooms`, JSON) and the decision for each room: handed over /
handed over conditionally (the risk is then written in the protocol) / not handed over. States: DRAFT (editable, at most one per
object) -> ISSUED (frozen, 16F.2) -> ARCHIVED. Nothing is deleted.
"""
import enum
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON as GenericJSON

from app.core.database import Base

_JSONVariant = JSONB().with_variant(GenericJSON(), "sqlite")


class HandoverStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"  # frozen in 16F.2
    ARCHIVED = "ARCHIVED"


class HandoverProtocol(Base):
    __tablename__ = "handover_protocols"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=HandoverStatus.DRAFT.value)
    held_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    held_time: Mapped[str | None] = mapped_column(String(5), nullable=True)  # "HH:MM", optional
    attendees: Mapped[list] = mapped_column(_JSONVariant, nullable=False, default=list)
    rooms: Mapped[dict] = mapped_column(_JSONVariant, nullable=False, default=dict)
    meters: Mapped[str | None] = mapped_column(Text, nullable=True)  # readings of the meters, free text
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # what an issued protocol freezes (16F.2): the time, the snapshot, the exact page and the contract it was made under
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
        CheckConstraint("status IN ('DRAFT', 'ISSUED', 'ARCHIVED')", name="ck_handover_protocols_status"),
        CheckConstraint("sequence >= 1", name="ck_handover_protocols_sequence_positive"),
        CheckConstraint(
            "status <> 'ISSUED' OR (issued_at IS NOT NULL AND snapshot IS NOT NULL AND document_html IS NOT NULL)",
            name="ck_handover_protocols_frozen_when_issued",
        ),
        UniqueConstraint("project_id", "sequence", name="uq_handover_protocols_project_sequence"),
        Index(
            "uq_handover_protocols_one_draft", "project_id", unique=True,
            postgresql_where=text("status = 'DRAFT'"), sqlite_where=text("status = 'DRAFT'"),
        ),
        Index("ix_handover_protocols_project", "project_id", "status"),
    )
