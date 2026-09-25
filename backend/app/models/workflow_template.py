"""Stage 13B — technological workflow templates (persistence foundation).

See `docs/STAGE_13_TECHNOLOGICAL_WORKFLOWS_ARCHITECTURE.md` §4, §14.

A `WorkflowTemplate` is an owner-scoped, reusable RECIPE: an ordered list of
`WorkflowTemplateStep` rows, each pointing directly at a billable `PriceItem`
(D1). Its applicability filters (substrate / quality target / surface type)
are recipe-selection metadata only -- never project state. A template is
never coupled to an actual plan: applying it copies steps into ordinary
`SurfacePlannedWork` occurrences (13E), and template edits are
non-retroactive.

`SurfaceWorkPlanTemplateApplication` is HISTORICAL provenance (D7) attached
to the durable `SurfaceWorkPlan` header: a snapshot of which template was
applied, how, and when. It is not current state -- the plan remains the source
of truth, and the Estimate never reads templates or this history.
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class TemplateApplicationMode(str, enum.Enum):
    APPEND = "APPEND"
    REPLACE = "REPLACE"


class WorkflowTemplate(Base):
    """Owner-scoped technological recipe (mirrors the Stage 12 catalog shape:
    immutable `code`, `name_key` for a future program default, editable
    `display_name`, soft archive)."""

    __tablename__ = "workflow_templates"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Stable identifier, immutable after creation (CUSTOM_* for owner-created).
    code: Mapped[str] = mapped_column(String(120), nullable=False)
    # Localized name key for a future program-default template (13D).
    name_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Applicability filters: lists of enum values; NULL/empty = any (D6).
    applies_to_substrates: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    applies_to_quality: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    applies_to_surface_types: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    steps: Mapped[list["WorkflowTemplateStep"]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="WorkflowTemplateStep.position",
    )

    __table_args__ = (
        UniqueConstraint("owner_id", "code", name="uq_workflow_templates_owner_code"),
        Index("ix_workflow_templates_owner_archived", "owner_id", "is_archived"),
    )


class WorkflowTemplateStep(Base):
    """One ordered step of a template. References a `PriceItem` directly
    (atomic or bundled, never REVEAL). `wait_after_hours` is the minimum
    technological/drying break AFTER this step: NULL = no break, otherwise a
    whole number of hours >= 1. It is not billable, not a PriceItem property
    and not a reminder. Steps carry no coefficients (D8)."""

    __tablename__ = "workflow_template_steps"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("workflow_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    price_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("price_items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    is_optional: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
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

    template: Mapped["WorkflowTemplate"] = relationship(back_populates="steps")
    price_item: Mapped["PriceItem"] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "template_id", "position", name="uq_workflow_template_steps_template_position"
        ),
        CheckConstraint(
            "wait_after_hours IS NULL OR wait_after_hours >= 1",
            name="ck_workflow_template_steps_wait_after_hours",
        ),
    )


class SurfaceWorkPlanTemplateApplication(Base):
    """Immutable history record: a template was applied to this plan (D7).

    `template_code` / `template_name` are snapshots taken at save time, so a
    later rename, archive or deletion of the template never rewrites history;
    `template_id` is informational only and becomes NULL if the template row
    is ever deleted.
    """

    __tablename__ = "surface_work_plan_template_applications"

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
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("workflow_templates.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    template_code: Mapped[str] = mapped_column(String(120), nullable=False)
    template_name: Mapped[str] = mapped_column(String(255), nullable=False)
    mode: Mapped[TemplateApplicationMode] = mapped_column(
        Enum(TemplateApplicationMode, name="templateapplicationmode"),
        nullable=False,
    )
    steps_applied: Mapped[int] = mapped_column(Integer, nullable=False)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    work_plan: Mapped["SurfaceWorkPlan"] = relationship(
        back_populates="template_applications"
    )

    __table_args__ = (
        CheckConstraint(
            "steps_applied >= 0",
            name="ck_surface_work_plan_template_applications_steps_applied",
        ),
    )
