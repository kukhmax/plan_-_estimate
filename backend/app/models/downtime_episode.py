"""A downtime on the customer's side: the notice and the protocol of downtime (Stage 16I.3; annex 8 of the contract).

When something that the customer owes stops the work (no access, the premises not ready, no utilities, other contractors not finished,
no decision, materials not delivered, a stop order), the contractor first **notifies** him at once, in a documentary form, with the
cause and the photos (`§ 10 ust. 2`), and if the obstacle is not removed, **the days** on which he was ready and could not work are
confirmed by a **protocol** -- with the rate for readiness that the contract states. One row is one such episode of one object and
carries both documents: the notice (a draft is edited, then issued and frozen) and later the protocol (the days, the people present
or the refusal to sign; issued and frozen). States: DRAFT (the notice is being written) -> NOTICED (the notice is issued; the protocol
is being written) -> CLOSED (the protocol is issued); ARCHIVED when the episode is abandoned. At most one episode is open (DRAFT or
NOTICED) per object. Nothing is deleted.
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


class DowntimeStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    NOTICED = "NOTICED"
    CLOSED = "CLOSED"
    ARCHIVED = "ARCHIVED"


class DowntimeEpisode(Base):
    __tablename__ = "downtime_episodes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default=DowntimeStatus.DRAFT.value)
    # --- the notice (edited while DRAFT) ---
    cause_key: Mapped[str | None] = mapped_column(String(40), nullable=True)  # the catalogue of causes
    cause_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    room_ids: Mapped[list] = mapped_column(_JSONVariant, nullable=False, default=list)  # empty: the whole object
    noticed_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    noticed_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    notice_channel: Mapped[str | None] = mapped_column(String(255), nullable=True)  # e-mail / SMS / messenger ...: the documentary form
    photo_ids: Mapped[list] = mapped_column(_JSONVariant, nullable=False, default=list)
    need_text: Mapped[str | None] = mapped_column(Text, nullable=True)  # what the contractor needs from the customer
    need_by: Mapped[date | None] = mapped_column(Date, nullable=True)  # and until when
    # --- the protocol (edited while NOTICED) ---
    days: Mapped[list] = mapped_column(_JSONVariant, nullable=False, default=list)  # [{date, other_work, note}], by date
    held_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    held_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    attendees: Mapped[list] = mapped_column(_JSONVariant, nullable=False, default=list)
    signature_refused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    deadline_note: Mapped[str | None] = mapped_column(Text, nullable=True)  # the effect on the deadline, in the owner's words
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # --- what the two issued documents freeze ---
    notice_issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    notice_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notice_snapshot: Mapped[dict | None] = mapped_column(_JSONVariant, nullable=True)
    notice_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    protocol_issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    protocol_snapshot: Mapped[dict | None] = mapped_column(_JSONVariant, nullable=True)
    protocol_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    contract_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    contract_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        CheckConstraint("status IN ('DRAFT', 'NOTICED', 'CLOSED', 'ARCHIVED')", name="ck_downtime_episodes_status"),
        CheckConstraint("sequence >= 1", name="ck_downtime_episodes_sequence_positive"),
        CheckConstraint(
            "status NOT IN ('NOTICED', 'CLOSED') OR (notice_issued_at IS NOT NULL AND notice_snapshot IS NOT NULL AND notice_html IS NOT NULL)",
            name="ck_downtime_episodes_notice_frozen",
        ),
        CheckConstraint(
            "status <> 'CLOSED' OR (protocol_issued_at IS NOT NULL AND protocol_snapshot IS NOT NULL AND protocol_html IS NOT NULL)",
            name="ck_downtime_episodes_protocol_frozen",
        ),
        UniqueConstraint("project_id", "sequence", name="uq_downtime_episodes_project_sequence"),
        Index(
            "uq_downtime_episodes_one_open", "project_id", unique=True,
            postgresql_where=text("status IN ('DRAFT', 'NOTICED')"), sqlite_where=text("status IN ('DRAFT', 'NOTICED')"),
        ),
        Index("ix_downtime_episodes_project", "project_id", "status"),
    )
