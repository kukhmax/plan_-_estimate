"""Per-surface work planning entities (Stage 10).

A SurfaceWorkPlan is the planning configuration for exactly one Surface: the
substrate, the agreed quality target, and an ordered list of planned works.
The plan stores only references to Price Book items — never a price snapshot —
and carries no tenancy fields; ownership always resolves through
Surface -> Room -> Project -> Owner.

Stage 13B (D13) gives every planned-work occurrence two identities: `id` is
the database row and may change on every full-replace save; `occurrence_key`
is the stable logical identity of that occurrence and survives such saves
(see docs/STAGE_13_TECHNOLOGICAL_WORKFLOWS_ARCHITECTURE.md §22).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
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
from app.models.price_coefficient import CoefficientOption


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
    # Stage 13 historical provenance (D7); never loaded implicitly.
    template_applications: Mapped[list["SurfaceWorkPlanTemplateApplication"]] = relationship(
        back_populates="work_plan",
        cascade="all, delete-orphan",
        order_by="SurfaceWorkPlanTemplateApplication.applied_at",
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
    # Stable logical occurrence identity (D13): server-generated, globally
    # unique, preserved across full-replace saves; never derived from the
    # PriceItem, position, plan or a template step.
    occurrence_key: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
        default=uuid.uuid4,
    )
    # Minimum technological/drying break AFTER this occurrence, in whole
    # hours (D9): NULL = none. Plan configuration only -- not billable, not a
    # PriceItem property, ignored by the Estimate, not a reminder.
    wait_after_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
    coefficient_assignments: Mapped[list["SurfacePlannedWorkCoefficientAssignment"]] = relationship(
        back_populates="surface_planned_work",
        cascade="all, delete-orphan",
    )

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
        Index(
            "uq_surface_planned_works_occurrence_key",
            "occurrence_key",
            unique=True,
        ),
        CheckConstraint(
            "wait_after_hours IS NULL OR wait_after_hours >= 1",
            name="ck_surface_planned_works_wait_after_hours",
        ),
    )

    @property
    def coefficient_options(self) -> list["CoefficientOption"]:
        """Selected coefficient options for this occurrence, in a stable,
        deterministic read order (CoefficientGroup.position, then
        CoefficientOption.position, then id as a tie-breaker) -- independent
        of whatever order the client submitted them in (Stage 12
        architecture Sec 13). Requires `coefficient_assignments` (and each
        assignment's `coefficient_option.group`) to already be eager-loaded;
        never triggers a lazy load itself.
        """
        return sorted(
            (a.coefficient_option for a in self.coefficient_assignments),
            key=lambda o: (o.group.position, o.position, str(o.id)),
        )


class SurfacePlannedWorkCoefficientAssignment(Base):
    """One selected `CoefficientOption` applied to one specific planned-work
    OCCURRENCE (Stage 12D) -- never to a `PriceItem`, Surface, Room, or
    Project. Deliberately stores no percentage/display-name snapshot and no
    effective price: those are live configuration, re-read fresh at every
    Estimate generation (Stage 12E); this row is pure assignment.

    Per Stage 12B architecture Option C, this table has NO durable identity
    concern of its own: it is always deleted and recreated atomically
    together with its parent `SurfacePlannedWork` row on every ordinary
    WorkPlan replace (`ondelete="CASCADE"` on `surface_planned_work_id`),
    exactly like `SurfacePlannedWork` itself is deleted/recreated relative to
    `SurfaceWorkPlan`. `coefficient_option_id` uses `ondelete="RESTRICT"`
    (mirrors `SurfacePlannedWork.price_item_id`) since a `CoefficientOption`
    is only ever soft-archived, never hard-deleted.
    """

    __tablename__ = "surface_planned_work_coefficient_assignments"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    surface_planned_work_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("surface_planned_works.id", ondelete="CASCADE"),
        nullable=False,
    )
    coefficient_option_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("coefficient_options.id", ondelete="RESTRICT"),
        nullable=False,
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

    surface_planned_work: Mapped["SurfacePlannedWork"] = relationship(
        back_populates="coefficient_assignments"
    )
    coefficient_option: Mapped["CoefficientOption"] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "surface_planned_work_id",
            "coefficient_option_id",
            name="uq_surface_planned_work_coefficient_option",
        ),
        # Explicit names match migration 0024, which shortened the
        # auto-generated names to fit PostgreSQL's 63-byte identifier limit.
        Index("ix_surface_planned_work_coefficient_assignments_work_id", "surface_planned_work_id"),
        Index("ix_surface_planned_work_coefficient_assignments_option_id", "coefficient_option_id"),
    )
