"""surface work executions (Stage 13H.2)

Revision ID: 0030_surface_work_executions
Revises: 0029_application_fingerprint
Create Date: 2026-09-27 18:00:00.000000

See docs/STAGE_13_TECHNOLOGICAL_WORKFLOWS_ARCHITECTURE.md §33.

Creates surface_work_executions -- the current execution state of a surface
planned-work occurrence, keyed by its occurrence_key (UNIQUE, deliberately no
FK to surface_planned_works, whose rows every WorkPlan save recreates).
work_plan_id CASCADE (ownership chain / lifecycle), price_item_id RESTRICT
(PriceItems are archive-only; mirrors surface_planned_works). Status and
timestamps are tied together by CHECK constraints.

Creates an EMPTY table: no row means NOT_STARTED (D-H20), so no existing
planned work, plan, PriceItem, coefficient or Estimate row is read or
changed. Downgrade drops the table and its enum type.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0030_surface_work_executions"
down_revision: Union[str, None] = "0029_application_fingerprint"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "surface_work_executions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("occurrence_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "work_plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("surface_work_plans.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "price_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("price_items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("NOT_STARTED", "IN_PROGRESS", "COMPLETED", name="workexecutionstatus"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "(status = 'NOT_STARTED' AND started_at IS NULL AND completed_at IS NULL)"
            " OR (status = 'IN_PROGRESS' AND started_at IS NOT NULL AND completed_at IS NULL)"
            " OR (status = 'COMPLETED' AND started_at IS NOT NULL AND completed_at IS NOT NULL)",
            name="ck_surface_work_executions_status_timestamps",
        ),
        sa.CheckConstraint(
            "completed_at IS NULL OR completed_at >= started_at",
            name="ck_surface_work_executions_completed_after_started",
        ),
    )
    op.create_index(
        "uq_surface_work_executions_occurrence_key",
        "surface_work_executions",
        ["occurrence_key"],
        unique=True,
    )
    op.create_index(
        "ix_surface_work_executions_work_plan_id",
        "surface_work_executions",
        ["work_plan_id"],
    )
    op.create_index(
        "ix_surface_work_executions_price_item_id",
        "surface_work_executions",
        ["price_item_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_surface_work_executions_price_item_id", table_name="surface_work_executions"
    )
    op.drop_index(
        "ix_surface_work_executions_work_plan_id", table_name="surface_work_executions"
    )
    op.drop_index(
        "uq_surface_work_executions_occurrence_key", table_name="surface_work_executions"
    )
    op.drop_table("surface_work_executions")
    op.execute("DROP TYPE IF EXISTS workexecutionstatus")
