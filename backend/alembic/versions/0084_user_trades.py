"""users.trades: the packages of professions an owner works in (V2-13)

Revision ID: 0084_user_trades
Revises: 0083_pressure_encrypted_text
Create Date: 2026-11-03 09:00:00.000000

One NEW nullable column `users.trades` (a JSON list of the keys of `domain/rules/trades.py`). NULL = never chosen = every trade on, so no existing owner loses anything and no data
is rewritten. The column holds a choice of what to OFFER, not an evidence: nothing in it protects other rows, so the downgrade simply drops it.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0084_user_trades"
down_revision: str | None = "0083_pressure_encrypted_text"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("trades", JSON, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("trades")
