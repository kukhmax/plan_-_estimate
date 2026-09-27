"""Execution state of surface planned-work occurrences (Stage 13H).

One row holds the CURRENT execution state of one planned-work occurrence,
identified by `SurfacePlannedWork.occurrence_key` (D-H1) -- never by the
planned-work row id, which every ordinary WorkPlan save recreates. There is
deliberately NO foreign key to `surface_planned_works`: the row must survive
that recreation, and it is kept as detached history when its occurrence is
removed from the plan (D-H7: detached = its key is no longer in the plan; no
flag column). No row means NOT_STARTED (D-H20): rows are created lazily on the
first transition away from NOT_STARTED and kept on reset.

`started_at` / `completed_at` record when the state was entered IN THE
APPLICATION (server UTC time). They are not proof of the physical moment the
construction operation started or ended, and are not editable in v1 (D-H4).

Execution is independent of pricing: nothing commercial reads this table and
plan saves never write it (D-H15). See
docs/STAGE_13_TECHNOLOGICAL_WORKFLOWS_ARCHITECTURE.md §33.
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WorkExecutionStatus(str, enum.Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"


class SurfaceWorkExecution(Base):
    __tablename__ = "surface_work_executions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # Logical occurrence identity (D-H1); unique, no FK (see module docstring).
    occurrence_key: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    # Ownership chain and lifecycle: the plan is never deleted by the API.
    work_plan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("surface_work_plans.id", ondelete="CASCADE"),
        nullable=False,
    )
    # The occurrence's operation, so detached history stays identifiable.
    # PriceItems are archive-only; RESTRICT mirrors surface_planned_works.
    price_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("price_items.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[WorkExecutionStatus] = mapped_column(
        Enum(WorkExecutionStatus, name="workexecutionstatus"),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("uq_surface_work_executions_occurrence_key", "occurrence_key", unique=True),
        Index("ix_surface_work_executions_work_plan_id", "work_plan_id"),
        Index("ix_surface_work_executions_price_item_id", "price_item_id"),
        CheckConstraint(
            "(status = 'NOT_STARTED' AND started_at IS NULL AND completed_at IS NULL)"
            " OR (status = 'IN_PROGRESS' AND started_at IS NOT NULL AND completed_at IS NULL)"
            " OR (status = 'COMPLETED' AND started_at IS NOT NULL AND completed_at IS NOT NULL)",
            name="ck_surface_work_executions_status_timestamps",
        ),
        CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name="ck_surface_work_executions_completed_after_started",
        ),
    )
