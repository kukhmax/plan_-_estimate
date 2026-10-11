"""A reminder: the queue of the messages to the owner and the owner's own reminders (Stage 18C).

One table holds both. `origin` AUTO rows are derived from the data of an object (a break ends, a term of the contract) and are kept in
step with it by the reconciliation: a row whose source disappeared or moved is cancelled, a new fact gets a new row, and a row that
was already sent is never touched. `origin` USER rows are the owner's own (the "Remind" button, a note) and live until they are due or
the owner removes them. `dedupe_key` is unique per owner and encodes the schedule instant, so the same fact is queued once and a moved
fact is a new row. `send_at` is an absolute instant (UTC); `tz` is the owner's zone at creation. See docs/STAGE_18_CALENDAR_REMINDERS_PLAN_RU.md.
"""
import enum
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
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


class ReminderOrigin(str, enum.Enum):
    AUTO = "AUTO"
    USER = "USER"


class ReminderStatus(str, enum.Enum):
    PENDING = "PENDING"  # waits for its time
    SENDING = "SENDING"  # taken by the delivery loop
    SENT = "SENT"
    SKIPPED = "SKIPPED"  # not sent on purpose (the kind was switched off, or a digest covered it)
    MISSED = "MISSED"  # its time passed long ago while the server could not send it
    FAILED = "FAILED"  # the sending failed for good (the bot is blocked, five attempts)
    CANCELLED = "CANCELLED"  # its source disappeared, moved or was archived, or the owner removed it
    DONE = "DONE"  # no longer needed: the work it was about has reached the status it waited for


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    room_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)  # rooms and surfaces are archived, never deleted: no FK
    surface_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    occurrence_key: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)  # the work it is about, if any
    origin: Mapped[str] = mapped_column(String(4), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)  # the EventKind
    ref: Mapped[str] = mapped_column(String(40), nullable=False, default="")  # what within the kind
    title: Mapped[str | None] = mapped_column(String(120), nullable=True)  # the owner's own words (USER)
    title_key: Mapped[str | None] = mapped_column(String(80), nullable=True)  # the text of an AUTO reminder: a key of the locale dictionaries
    params: Mapped[dict] = mapped_column(_JSONVariant, nullable=False, default=dict)
    event_on: Mapped[date | None] = mapped_column(Date, nullable=True)  # the day it is about (an all-day event)
    event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # or the instant
    lead_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    send_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    tz: Mapped[str] = mapped_column(String(64), nullable=False)
    close_on_status: Mapped[str | None] = mapped_column(String(16), nullable=True)  # IN_PROGRESS / COMPLETED: the work's status that closes it
    status: Mapped[str] = mapped_column(String(12), nullable=False, default=ReminderStatus.PENDING.value)
    dedupe_key: Mapped[str] = mapped_column(String(255), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # when the delivery loop took it
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        UniqueConstraint("owner_id", "dedupe_key", name="uq_reminders_owner_dedupe"),
        Index("ix_reminders_due", "status", "send_at"),
        Index("ix_reminders_owner_project", "owner_id", "project_id"),
        Index("ix_reminders_occurrence", "occurrence_key"),
        CheckConstraint("origin IN ('AUTO', 'USER')", name="ck_reminders_origin"),
        CheckConstraint(
            "status IN ('PENDING', 'SENDING', 'SENT', 'SKIPPED', 'MISSED', 'FAILED', 'CANCELLED', 'DONE')", name="ck_reminders_status"
        ),
        CheckConstraint("origin <> 'USER' OR title IS NOT NULL", name="ck_reminders_user_has_title"),
        CheckConstraint("origin <> 'AUTO' OR title_key IS NOT NULL", name="ck_reminders_auto_has_title_key"),
        CheckConstraint("event_on IS NULL OR event_at IS NULL", name="ck_reminders_one_event_time"),
        CheckConstraint("close_on_status IS NULL OR close_on_status IN ('IN_PROGRESS', 'COMPLETED')", name="ck_reminders_close_on_status"),
        CheckConstraint("attempts >= 0 AND lead_days >= 0", name="ck_reminders_counters"),
    )
