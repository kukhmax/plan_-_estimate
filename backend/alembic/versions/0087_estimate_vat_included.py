"""estimates.vat_included: the prices of an estimate may already include the VAT (owner 2026-10-27, "вычесть НДС из сметы")

Revision ID: 0087_estimate_vat_included
Revises: 0086_transfer_source
Create Date: 2026-10-28 09:00:00.000000

One NEW column, NOT NULL with the server default false: every existing estimate keeps adding the VAT on top of its net lines, nothing is rewritten.
True (only together with the mode RATE, a check) = the lines are gross and the VAT is taken out of their sum. The downgrade drops the column.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0087_estimate_vat_included"
down_revision: str | None = "0086_transfer_source"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("estimates") as batch:
        batch.add_column(sa.Column("vat_included", sa.Boolean(), nullable=False, server_default=sa.text("false")))
        batch.create_check_constraint("ck_estimates_vat_included", "vat_included = false OR vat_mode = 'RATE'")


def downgrade() -> None:
    with op.batch_alter_table("estimates") as batch:
        batch.drop_constraint("ck_estimates_vat_included", type_="check")
        batch.drop_column("vat_included")
