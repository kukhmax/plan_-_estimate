"""make price_items.price nullable

Stage 9E.7: NULL is the canonical value for a seeded catalog row whose owner
commercial price has not been set yet ("Do ustalenia"). 0.00 stays a real,
explicitly set zero price and is never reused as a sentinel.

Revision ID: 0016_make_price_nullable
Revises: 0015_create_market_evidence
Create Date: 2026-09-15 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0016_make_price_nullable"
down_revision: Union[str, None] = "0015_create_market_evidence"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "price_items",
        "price",
        existing_type=sa.Numeric(12, 2),
        nullable=True,
    )


def downgrade() -> None:
    # Reverting to NOT NULL requires every row to carry a price. Seed rows are
    # materialized with price = NULL only for owners who bootstrapped after the
    # 9E.7 seed set shipped; any such NULL must be resolved before downgrading.
    op.alter_column(
        "price_items",
        "price",
        existing_type=sa.Numeric(12, 2),
        nullable=False,
    )