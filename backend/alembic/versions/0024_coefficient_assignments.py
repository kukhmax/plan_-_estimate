"""assign coefficients to planned-work occurrences (Stage 12D)

Revision ID: 0024_coefficient_assignments
Revises: 0023_price_coefficients
Create Date: 2026-09-21 15:00:00.000000

Adds the two join tables that let ONE planned-work OCCURRENCE (a single row
in surface_planned_works or opening_reveal_planned_works) carry zero or more
selected CoefficientOption rows:

- surface_planned_work_coefficient_assignments
- opening_reveal_planned_work_coefficient_assignments

Per docs/stage-12-architecture.md ("Option C"), these assignments are never
expected to survive independently across a WorkPlan/Reveal replace: the
service layer validates a full proposed selection, then deletes and
recreates the parent occurrence row together with its coefficient
assignments in the same atomic operation. The FK to the parent occurrence
is therefore CASCADE (deleting the occurrence deletes its assignments); the
FK to coefficient_options is RESTRICT, since options are only ever
soft-archived, never hard-deleted, so an assignment can never be left
dangling.

No percentage or price snapshot is stored on the assignment -- that belongs
to Stage 12E's EstimateLine work. No existing table/column/enum is altered.
Purely additive.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0024_coefficient_assignments"
down_revision: Union[str, None] = "0023_price_coefficients"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "surface_planned_work_coefficient_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "surface_planned_work_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("surface_planned_works.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "coefficient_option_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("coefficient_options.id", ondelete="RESTRICT"),
            nullable=False,
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
        sa.UniqueConstraint(
            "surface_planned_work_id",
            "coefficient_option_id",
            name="uq_surface_planned_work_coefficient_option",
        ),
    )
    op.create_index(
        "ix_surface_planned_work_coefficient_assignments_work_id",
        "surface_planned_work_coefficient_assignments",
        ["surface_planned_work_id"],
    )
    op.create_index(
        "ix_surface_planned_work_coefficient_assignments_option_id",
        "surface_planned_work_coefficient_assignments",
        ["coefficient_option_id"],
    )

    op.create_table(
        "opening_reveal_planned_work_coefficient_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "opening_reveal_planned_work_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opening_reveal_planned_works.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "coefficient_option_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("coefficient_options.id", ondelete="RESTRICT"),
            nullable=False,
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
        sa.UniqueConstraint(
            "opening_reveal_planned_work_id",
            "coefficient_option_id",
            name="uq_opening_reveal_planned_work_coefficient_option",
        ),
    )
    op.create_index(
        "ix_opening_reveal_coefficient_assignments_work_id",
        "opening_reveal_planned_work_coefficient_assignments",
        ["opening_reveal_planned_work_id"],
    )
    op.create_index(
        "ix_opening_reveal_coefficient_assignments_option_id",
        "opening_reveal_planned_work_coefficient_assignments",
        ["coefficient_option_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_opening_reveal_coefficient_assignments_option_id",
        table_name="opening_reveal_planned_work_coefficient_assignments",
    )
    op.drop_index(
        "ix_opening_reveal_coefficient_assignments_work_id",
        table_name="opening_reveal_planned_work_coefficient_assignments",
    )
    op.drop_table("opening_reveal_planned_work_coefficient_assignments")

    op.drop_index(
        "ix_surface_planned_work_coefficient_assignments_option_id",
        table_name="surface_planned_work_coefficient_assignments",
    )
    op.drop_index(
        "ix_surface_planned_work_coefficient_assignments_work_id",
        table_name="surface_planned_work_coefficient_assignments",
    )
    op.drop_table("surface_planned_work_coefficient_assignments")
