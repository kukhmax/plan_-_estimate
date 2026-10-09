"""Works of other contractors on the same object (Stage 16D.1): the register that the production plan and the contract refer to.

Electricians, plumbers, tilers, the developer's own crews: what they do, who does it, in which rooms, when, and how it is ordered
against the contractor's own finishing work ("electrics before plaster", "floors after painting"), who answers for cleanliness
and damage, who coordinates. Free text for what only the owner can know; the only fixed vocabulary is the order against our own
works. `room_ids` is a list of rooms of the same object; null means the whole object. Nothing is deleted: archive instead.
"""
import enum
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, ForeignKey, Index, Integer, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON as GenericJSON

from app.core.database import Base

_JSONVariant = JSONB().with_variant(GenericJSON(), "sqlite")


class AdjacentWorkOrder(str, enum.Enum):
    BEFORE_OURS = "BEFORE_OURS"  # done before the contractor's own works
    PARALLEL = "PARALLEL"  # at the same time
    AFTER_OURS = "AFTER_OURS"  # done after the contractor's own works


class AdjacentWork(Base):
    __tablename__ = "adjacent_works"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    work_name: Mapped[str] = mapped_column(String(255), nullable=False)
    performer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    room_ids: Mapped[list | None] = mapped_column(_JSONVariant, nullable=True)
    period_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    order_relation: Mapped[str] = mapped_column(String(16), nullable=False)
    order_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    responsibility_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    coordination_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        CheckConstraint("order_relation IN ('BEFORE_OURS', 'PARALLEL', 'AFTER_OURS')", name="ck_adjacent_works_order"),
        CheckConstraint("length(work_name) > 0", name="ck_adjacent_works_name_not_empty"),
        CheckConstraint(
            "period_from IS NULL OR period_to IS NULL OR period_to >= period_from", name="ck_adjacent_works_period"
        ),
        Index("ix_adjacent_works_project", "project_id", "is_archived"),
    )
