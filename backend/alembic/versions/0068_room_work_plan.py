"""V2-5: the plan of the works of a whole room -- room_work_plans, room_planned_works and surface_work_plans.follows_room_plan

Revision ID: 0068_room_work_plan
Revises: 0067_password_login
Create Date: 2026-10-24 12:00:00.000000

Two NEW tables (one plan per room; its works for the walls and for the ceiling, as ordered references to the Price Book) and one NEW column
`surface_work_plans.follows_room_plan` (boolean, NOT NULL, default false: every existing plan stays a plan of its own, so nothing changes until the owner
saves a plan of a room). No row of an existing table is changed.

Reversible: the downgrade drops the column and the two tables.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0068_room_work_plan"
down_revision: str | None = "0067_password_login"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "room_work_plans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("room_id", sa.Uuid(), nullable=False),
        sa.Column(
            "substrate",
            postgresql.ENUM(
                "CONCRETE", "GYPSUM_PLASTER", "CEMENT_LIME_PLASTER", "GYPSUM_BOARD", "PAINTED", "OTHER", name="substrate", create_type=False
            ),
            nullable=False,
        ),
        sa.Column(
            "quality_target",
            postgresql.ENUM("S1", "S2", "S3", "S4", "Q1", "Q2", "Q3", "Q4", name="qualitylevel", create_type=False),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("room_id", name="uq_room_work_plans_room_id"),
    )
    op.create_table(
        "room_planned_works",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("room_plan_id", sa.Uuid(), nullable=False),
        sa.Column("target", sa.String(8), nullable=False),
        sa.Column("price_item_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["room_plan_id"], ["room_work_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["price_item_id"], ["price_items.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("room_plan_id", "target", "position", name="uq_room_planned_works_plan_target_position"),
        sa.CheckConstraint("target IN ('WALLS', 'CEILING')", name="ck_room_planned_works_target"),
    )
    op.create_index("ix_room_planned_works_plan", "room_planned_works", ["room_plan_id"])
    op.create_index("ix_room_planned_works_price_item_id", "room_planned_works", ["price_item_id"])
    op.add_column("surface_work_plans", sa.Column("follows_room_plan", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("surface_work_plans", "follows_room_plan")
    op.drop_index("ix_room_planned_works_price_item_id", table_name="room_planned_works")
    op.drop_index("ix_room_planned_works_plan", table_name="room_planned_works")
    op.drop_table("room_planned_works")
    op.drop_table("room_work_plans")
