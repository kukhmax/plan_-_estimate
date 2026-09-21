"""add coefficient snapshot columns to estimate_lines (Stage 12E)

Revision ID: 0025_estimate_line_coefficients
Revises: 0024_coefficient_assignments
Create Date: 2026-09-21 18:00:00.000000

Adds two nullable columns to `estimate_lines`:

- base_unit_price (Numeric(12, 2)): PriceItem.price captured at generation/
  regeneration time, before coefficient adjustment.
- coefficient_snapshot (JSONB on PostgreSQL, plain JSON on SQLite via
  with_variant): the immutable selected-coefficient configuration used to
  compute the line's unit_price, so a historical Estimate remains explainable
  after the live catalog is later renamed, edited, or archived.

`unit_price` is untouched and keeps its existing meaning (the effective,
commercially-used price) -- it is never repurposed into a base price.

No historical data rewrite: existing rows get NULL for both new columns,
which is the honest, correct value for lines never touched by 12E-aware
generation (legacy PLANNED_WORK lines, MANUAL lines, PRICE_BOOK lines).
Existing Estimate totals are unaffected (unit_price/amount are untouched).

Purely additive. No existing column/enum/table altered.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0025_estimate_line_coefficients"
down_revision: Union[str, None] = "0024_coefficient_assignments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "estimate_lines",
        sa.Column("base_unit_price", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "estimate_lines",
        sa.Column("coefficient_snapshot", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("estimate_lines", "coefficient_snapshot")
    op.drop_column("estimate_lines", "base_unit_price")
