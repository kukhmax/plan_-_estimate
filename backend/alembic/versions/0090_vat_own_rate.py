"""VAT: an own rate -- the check of estimates.vat_rate_percent / executor_profiles.vat_rate_percent allows a whole percent 0..100 (owner 2026-10-30)

Revision ID: 0090_vat_own_rate
Revises: 0089_floor_substrates
Create Date: 2026-10-30 12:00:00.000000

Until now the check allowed only 8 and 23 (0069). The owner may type an own rate (5 %, 0 %, ...), so the check becomes `vat_rate_percent BETWEEN 0 AND 100`;
nothing else changes and no row changes. Reversible: the downgrade **refuses** while an estimate or the owner's profile has a rate other than 8 / 23 (the owner's own
input is never altered silently); otherwise it puts the old check back.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0090_vat_own_rate"
down_revision: str | None = "0089_floor_substrates"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLES = (("executor_profiles", "ck_executor_profiles_vat"), ("estimates", "ck_estimates_vat"))
_BASE = "(vat_mode IS NULL AND vat_rate_percent IS NULL) OR (vat_mode = 'EXEMPT' AND vat_rate_percent IS NULL) "
_NEW = _BASE + "OR (vat_mode = 'RATE' AND vat_rate_percent BETWEEN 0 AND 100)"
_OLD = _BASE + "OR (vat_mode = 'RATE' AND vat_rate_percent IN (8, 23))"


def upgrade() -> None:
    for table, check in _TABLES:
        op.drop_constraint(check, table, type_="check")
        op.create_check_constraint(check, table, _NEW)


def downgrade() -> None:
    bind = op.get_bind()
    for table, _ in _TABLES:
        own = bind.exec_driver_sql(f"SELECT count(*) FROM {table} WHERE vat_mode = 'RATE' AND vat_rate_percent NOT IN (8, 23)").scalar()
        if own:
            raise RuntimeError(f"{own} row(s) of {table} have an own VAT rate: change them to 8 or 23 first, then downgrade")
    for table, check in _TABLES:
        op.drop_constraint(check, table, type_="check")
        op.create_check_constraint(check, table, _OLD)
