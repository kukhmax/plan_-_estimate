"""create price coefficient catalog (Stage 12C)

Revision ID: 0023_price_coefficients
Revises: 0022_work_recommendations
Create Date: 2026-09-21 12:00:00.000000

Adds the Stage 12 coefficient catalog persistence foundation only:

- coefficient_groups: an owner-scoped, named group of mutually-exclusive
  options (SINGLE_SELECT is the only mode this cut implements). Mirrors
  PriceItem's shape: a stable, immutable `code` plus an editable
  `display_name`.
- coefficient_options: one selectable percentage adjustment within a group.
  `percentage` is a signed Decimal delta relative to a base labor price
  (10.000 = +10%), never a multiplier. `is_base` is an explicit boolean
  column, not inferred from `percentage == 0` -- see
  docs/stage-12-architecture.md Sec 4 for the rationale. The "at most one
  active base option per group" invariant is enforced at the service layer
  (PriceCoefficientService._clear_other_base_options), consistent with how
  this codebase enforces other cross-row domain invariants (e.g.
  assert_quality_scale_valid) rather than via a DB constraint.

No owner-specific data seed: the baseline catalog (app/domain/data/
price_coefficients.py) ships intentionally empty until Stage 12G defines and
the owner approves real default groups/options (docs/stage-12-architecture.md
Sec 2, Sec 21, Sec 25).

Purely additive. No existing table/column/enum is altered. No planned-work
assignment (Stage 12D), no EstimateLine coefficient snapshot (Stage 12E), and
no frontend integration are introduced by this migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0023_price_coefficients"
down_revision: Union[str, None] = "0022_work_recommendations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "coefficient_groups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=120), nullable=False),
        sa.Column("name_key", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column(
            "selection_mode",
            sa.Enum("SINGLE_SELECT", name="coefficientselectionmode"),
            nullable=False,
            server_default="SINGLE_SELECT",
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
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
        sa.UniqueConstraint("owner_id", "code", name="uq_coefficient_groups_owner_code"),
    )
    op.create_index(
        "ix_coefficient_groups_owner_id", "coefficient_groups", ["owner_id"]
    )
    op.create_index(
        "ix_coefficient_groups_owner_archived",
        "coefficient_groups",
        ["owner_id", "is_archived"],
    )

    op.create_table(
        "coefficient_options",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "group_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("coefficient_groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=120), nullable=False),
        sa.Column("name_key", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("percentage", sa.Numeric(6, 3), nullable=False),
        sa.Column("is_base", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
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
        sa.UniqueConstraint("group_id", "code", name="uq_coefficient_options_group_code"),
    )
    op.create_index(
        "ix_coefficient_options_group_id", "coefficient_options", ["group_id"]
    )
    op.create_index(
        "ix_coefficient_options_group_archived",
        "coefficient_options",
        ["group_id", "is_archived"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_coefficient_options_group_archived", table_name="coefficient_options"
    )
    op.drop_index("ix_coefficient_options_group_id", table_name="coefficient_options")
    op.drop_table("coefficient_options")

    op.drop_index(
        "ix_coefficient_groups_owner_archived", table_name="coefficient_groups"
    )
    op.drop_index("ix_coefficient_groups_owner_id", table_name="coefficient_groups")
    op.drop_table("coefficient_groups")

    op.execute("DROP TYPE IF EXISTS coefficientselectionmode")
