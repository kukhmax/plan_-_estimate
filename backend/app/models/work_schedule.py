"""The planned date of a work (Stage 18C, decision Q12 of the owner).

One row is the date on which the owner plans one planned-work occurrence, identified -- like the execution of Stage 13H -- by
`SurfacePlannedWork.occurrence_key`, never by the row id that every plan save recreates. There is deliberately no foreign key to the
occurrence: the date survives the recreation and is kept as detached history when the occurrence leaves the plan. The date is a hint for
the calendar and a check against the technological breaks; it is never a lock and nothing commercial reads it.
"""
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WorkSchedule(Base):
    __tablename__ = "work_schedule"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    occurrence_key: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    planned_date: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        Index("uq_work_schedule_occurrence_key", "occurrence_key", unique=True),
        Index("ix_work_schedule_project", "project_id"),
    )
