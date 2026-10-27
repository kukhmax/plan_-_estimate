"""room_points.source and material_calcs.source: what a craftsman's answer carried over (V2-14a)

Revision ID: 0086_transfer_source
Revises: 0085_trade_links
Create Date: 2026-11-04 09:00:00.000000

Two NEW nullable columns (`source`, a short word). NULL = the owner typed the row; `TRADE_LINK` = it was carried over from the answer of a craftsman, so that a second carrying over
updates exactly these rows and never touches the owner's own. No existing row is rewritten. The columns hold a label, not an evidence: the downgrade simply drops them (the rows stay,
as the owner's own).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0086_transfer_source"
down_revision: str | None = "0085_trade_links"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("room_points") as batch:
        batch.add_column(sa.Column("source", sa.String(16), nullable=True))
    with op.batch_alter_table("material_calcs") as batch:
        batch.add_column(sa.Column("source", sa.String(16), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("material_calcs") as batch:
        batch.drop_column("source")
    with op.batch_alter_table("room_points") as batch:
        batch.drop_column("source")
