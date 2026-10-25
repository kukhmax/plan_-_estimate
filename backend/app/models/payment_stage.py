"""The payment schedule of an object (V2-9): the stages in which the client is to pay, and the hours the owner worked.

A stage is a line of the owner's own list ("Zaliczka", "Po gładziach", "Odbiór"): a title, a share of the agreed amount in percent **or** a fixed
amount (exactly one of the two), an optional due day. What was received for a stage is not stored here: an advance or a payment ("Od klienta") names
its stage (`project_payments.stage_id`), and the state of the stage is made on the server from those records. A stage is a plan, not accounting: it
may be deleted (the payments tied to it stay, without a stage).

`WorkHour` is one entry of the owner's work log of an object (a day, the hours, a note) -- the owner's own record, which may be changed and deleted.
Both go with their object (`ON DELETE CASCADE`). Titles and notes are free text typed by the owner, so they are encrypted like the other records.
"""
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.encrypted_text import EncryptedText


def _now() -> datetime:
    return datetime.now(UTC)


class PaymentStage(Base):
    __tablename__ = "payment_stages"
    __table_args__ = (
        CheckConstraint(
            "(percent IS NOT NULL AND amount IS NULL) OR (percent IS NULL AND amount IS NOT NULL)", name="ck_payment_stages_percent_xor_amount"
        ),
        CheckConstraint("percent IS NULL OR (percent > 0 AND percent <= 100)", name="ck_payment_stages_percent_range"),
        CheckConstraint("amount IS NULL OR amount > 0", name="ck_payment_stages_amount_positive"),
        CheckConstraint("position >= 0", name="ck_payment_stages_position"),
        Index("ix_payment_stages_project", "project_id", "due_on"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # the order of entry: the tie-break after the due day
    title: Mapped[str] = mapped_column(EncryptedText("payment_stages.title"), nullable=False)
    percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)  # a share of the agreed amount
    amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)  # or a fixed amount
    due_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class WorkHour(Base):
    __tablename__ = "work_hours"
    __table_args__ = (
        CheckConstraint("hours > 0 AND hours <= 24", name="ck_work_hours_range"),
        Index("ix_work_hours_project", "project_id", "worked_on"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    worked_on: Mapped[date] = mapped_column(Date, nullable=False)
    hours: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(EncryptedText("work_hours.note"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)
