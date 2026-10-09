"""contracts: the day of signing and the rule "one signed contract per object" (Stage 16E.4)

Revision ID: 0046_contract_signed
Revises: 0045_contract_issue
Create Date: 2026-10-10 14:00:00.000000

Canonical design: docs/STAGE_16_CONTRACTS_PROTOCOLS_PLAN_RU.md (16E).

Adds `contracts.signed_on` (the date written under the signatures on paper), a CHECK that a SIGNED contract has it, and a partial
unique index: at most one SIGNED contract per object. No data changes.

Reversible: the downgrade **refuses** (rather than deletes) while any contract carries a day of signing (the date of a signature
is evidence and is never dropped silently).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0046_contract_signed"
down_revision: str | None = "0045_contract_issue"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

HAS_DATE = "status <> 'SIGNED' OR signed_on IS NOT NULL"


def upgrade() -> None:
    with op.batch_alter_table("contracts") as batch:
        batch.add_column(sa.Column("signed_on", sa.Date, nullable=True))
        batch.create_check_constraint("ck_contracts_signed_has_date", HAS_DATE)
    op.create_index(
        "uq_contracts_one_signed", "contracts", ["project_id"], unique=True,
        postgresql_where=sa.text("status = 'SIGNED'"), sqlite_where=sa.text("status = 'SIGNED'"),
    )


def downgrade() -> None:
    signed = op.get_bind().execute(sa.text("SELECT count(*) FROM contracts WHERE signed_on IS NOT NULL")).scalar_one()
    if signed:
        raise RuntimeError(f"cannot downgrade: {signed} contract(s) carry a day of signing; it would be lost")
    op.drop_index("uq_contracts_one_signed", table_name="contracts")
    with op.batch_alter_table("contracts") as batch:
        batch.drop_constraint("ck_contracts_signed_has_date", type_="check")
        batch.drop_column("signed_on")
