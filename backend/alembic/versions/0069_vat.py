"""V2-6: the VAT of an estimate -- executor_profiles.vat_mode / vat_rate_percent and estimates.vat_mode / vat_rate_percent

Revision ID: 0069_vat
Revises: 0068_room_work_plan
Create Date: 2026-10-24 18:00:00.000000

Two NEW nullable columns on `executor_profiles` (the owner's VAT setting) and two on `estimates` (the snapshot a new estimate takes from it, changed on a
DRAFT only), each pair with a check that the mode and the rate belong together (NULL / NULL = not set, EXEMPT / NULL = "zw.", RATE / 8 or 23). Every existing
row gets NULL / NULL: nothing changes in any existing profile, estimate or document until the owner sets a VAT.

Reversible: the downgrade drops the checks and the columns.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0069_vat"
down_revision: str | None = "0068_room_work_plan"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_CHECK = (
    "(vat_mode IS NULL AND vat_rate_percent IS NULL) OR (vat_mode = 'EXEMPT' AND vat_rate_percent IS NULL) "
    "OR (vat_mode = 'RATE' AND vat_rate_percent IN (8, 23))"
)


def upgrade() -> None:
    for table, check in (("executor_profiles", "ck_executor_profiles_vat"), ("estimates", "ck_estimates_vat")):
        op.add_column(table, sa.Column("vat_mode", sa.String(8), nullable=True))
        op.add_column(table, sa.Column("vat_rate_percent", sa.Integer(), nullable=True))
        op.create_check_constraint(check, table, _CHECK)


def downgrade() -> None:
    for table, check in (("estimates", "ck_estimates_vat"), ("executor_profiles", "ck_executor_profiles_vat")):
        op.drop_constraint(check, table, type_="check")
        op.drop_column(table, "vat_rate_percent")
        op.drop_column(table, "vat_mode")
