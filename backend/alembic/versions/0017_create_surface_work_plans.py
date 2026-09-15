"""create surface work plan tables

Revision ID: 0017_create_surface_work_plans
Revises: 0016_make_price_nullable
Create Date: 2026-09-15 12:00:00.000000

One SurfaceWorkPlan per Surface (surface_id UNIQUE) with the reused Stage 6
substrate/qualitylevel enums, plus ordered SurfacePlannedWork rows referencing
Price Book items (position unique within a plan, appended from 0).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0017_create_surface_work_plans"
down_revision: Union[str, None] = "0016_make_price_nullable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "surface_work_plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "surface_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("surfaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "substrate",
            # The substrate type is owned by revision 0011; do not re-create it.
            postgresql.ENUM(
                "CONCRETE",
                "GYPSUM_PLASTER",
                "CEMENT_LIME_PLASTER",
                "GYPSUM_BOARD",
                "PAINTED",
                "OTHER",
                name="substrate",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "quality_target",
            # The qualitylevel type is owned by revision 0011; do not re-create it.
            postgresql.ENUM(
                "S1",
                "S2",
                "S3",
                "S4",
                "Q1",
                "Q2",
                "Q3",
                "Q4",
                name="qualitylevel",
                create_type=False,
            ),
            nullable=True,
        ),
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
        sa.UniqueConstraint("surface_id", name="uq_surface_work_plans_surface_id"),
    )

    op.create_table(
        "surface_planned_works",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
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
        sa.Column("position", sa.Integer(), nullable=False),
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
        sa.UniqueConstraint(
            "work_plan_id",
            "position",
            name="uq_surface_planned_works_work_plan_position",
        ),
    )
    op.create_index(
        "ix_surface_planned_works_work_plan_id",
        "surface_planned_works",
        ["work_plan_id"],
    )
    op.create_index(
        "ix_surface_planned_works_price_item_id",
        "surface_planned_works",
        ["price_item_id"],
    )
    op.create_index(
        "ix_surface_planned_works_plan_position",
        "surface_planned_works",
        ["work_plan_id", "position"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_surface_planned_works_plan_position",
        table_name="surface_planned_works",
    )
    op.drop_index(
        "ix_surface_planned_works_price_item_id",
        table_name="surface_planned_works",
    )
    op.drop_index(
        "ix_surface_planned_works_work_plan_id",
        table_name="surface_planned_works",
    )
    op.drop_table("surface_planned_works")
    op.drop_table("surface_work_plans")
    # NOTE: the "substrate" and "qualitylevel" enums are owned by revision 0011
    # and intentionally left intact.