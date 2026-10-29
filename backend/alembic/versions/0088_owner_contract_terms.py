"""owner_contract_terms: the owner's standard terms of a contract (UX walk B2, owner 2026-10-29 "Мои стандартные условия в профиле")

Revision ID: 0088_owner_contract_terms
Revises: 0087_estimate_vat_included
Create Date: 2026-10-29 18:00:00.000000

One NEW table, one row per owner: the answers of the questionnaire that are the same for every order, encrypted (TEXT, like
`contracts.answers`). Nothing existing is read or rewritten; a new contract draft takes these first and the latest contract of
another object for the rest. The downgrade drops the table (the terms are typed in again).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0088_owner_contract_terms"
down_revision: str | None = "0087_estimate_vat_included"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "owner_contract_terms"


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    op.create_table(
        TABLE,
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("owner_id", uuid_type, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("answers", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("owner_id", name="uq_owner_contract_terms_owner"),
    )


def downgrade() -> None:
    op.drop_table(TABLE)
