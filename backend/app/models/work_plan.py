"""Per-surface work planning entities (Stage 10).

A SurfaceWorkPlan is the planning configuration for exactly one Surface: the
substrate, the agreed quality target, and an ordered list of planned works.
The plan stores only references to Price Book items — never a price snapshot —
and carries no tenancy fields; ownership always resolves through
Surface -> Room -> Project -> Owner.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.checklist import QualityLevel, Substrate


class SurfaceWorkPlan(Base):
    __tablename__ = "surface_work_plans"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    surface_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("surfaces.id", ondelete="CASCADE"),
        nullable=False,
        comment="Exactly one plan per surface",
    )
    substrate: Mapped[Substrate] = mapped_column(
        Enum(Substrate, name="substrate"),
        nullable=False,
    )
    quality_target: Mapped[QualityLevel | None] = mapped_column(
        Enum(QualityLevel, name="qualitylevel"),
        nullable=True,
        comment="Agreed quality target; NULL means none agreed yet",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    planned_works: Mapped[list["SurfacePlannedWork"]] = relationship(
        back_populates="work_plan",
        cascade="all, delete-orphan",
        order_by="SurfacePlannedWork.position",
    )

    __table_args__ = (
        UniqueConstraint("surface_id", name="uq_surface_work_plans_surface_id"),
    )


class SurfacePlannedWork(Base):
    __tablename__ = "surface_planned_works"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    work_plan_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("surface_work_plans.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    price_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("price_items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment=(
            "Price Book reference only — no price copy. The same PriceItem may "
            "appear more than once (e.g. two separate coat rows); archived items "
            "are rejected for new selection but existing rows are never mutated"
        ),
    )
    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Ordinal position within the plan, appended from 0",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    work_plan: Mapped["SurfaceWorkPlan"] = relationship(
        back_populates="planned_works"
    )
    price_item: Mapped["PriceItem"] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "work_plan_id",
            "position",
            name="uq_surface_planned_works_work_plan_position",
        ),
        Index(
            "ix_surface_planned_works_plan_position",
            "work_plan_id",
            "position",
        ),
    )
