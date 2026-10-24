"""The plan of the works of a whole room (V2-5; docs/V2_5_PLAN_RU.md).

One plan per room: the substrate and the agreed class, and two ordered lists of price rows -- for the walls and for the ceiling. A wall or a ceiling
whose own plan follows it (`SurfaceWorkPlan.follows_room_plan`) is kept equal to it; a surface with a plan of its own is never touched.
The plan stores only references to the Price Book, never a price (like the plan of a surface); it carries no coefficients and no breaks.
"""
import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.checklist import QualityLevel, Substrate


class RoomPlanTarget(str, enum.Enum):
    WALLS = "WALLS"
    CEILING = "CEILING"


class RoomWorkPlan(Base):
    __tablename__ = "room_work_plans"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    room_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False, comment="Exactly one plan per room")
    substrate: Mapped[Substrate] = mapped_column(Enum(Substrate, name="substrate"), nullable=False)
    quality_target: Mapped[QualityLevel | None] = mapped_column(Enum(QualityLevel, name="qualitylevel"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    works: Mapped[list["RoomPlannedWork"]] = relationship(
        back_populates="room_plan", cascade="all, delete-orphan", order_by="(RoomPlannedWork.target, RoomPlannedWork.position)"
    )

    __table_args__ = (UniqueConstraint("room_id", name="uq_room_work_plans_room_id"),)


class RoomPlannedWork(Base):
    __tablename__ = "room_planned_works"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    room_plan_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("room_work_plans.id", ondelete="CASCADE"), nullable=False)
    target: Mapped[str] = mapped_column(String(8), nullable=False, comment="WALLS or CEILING")
    price_item_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("price_items.id", ondelete="RESTRICT"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    room_plan: Mapped["RoomWorkPlan"] = relationship(back_populates="works")

    __table_args__ = (
        UniqueConstraint("room_plan_id", "target", "position", name="uq_room_planned_works_plan_target_position"),
        Index("ix_room_planned_works_plan", "room_plan_id"),
        CheckConstraint("target IN ('WALLS', 'CEILING')", name="ck_room_planned_works_target"),
    )
