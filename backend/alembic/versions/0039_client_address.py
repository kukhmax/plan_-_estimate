"""client address: the address of the customer for contracts and protocols (Stage 16B.1)

Revision ID: 0039_client_address
Revises: 0038_issued_documents
Create Date: 2026-10-09 12:00:00.000000

Canonical design: docs/STAGE_16_CONTRACTS_PROTOCOLS_PLAN_RU.md (16B.1).

Adds three nullable columns to clients: street (with the house / flat number), postal_code (stored as `00-000`) and city. A
contract with a private person needs the customer's address. Existing rows keep NULL; nothing else changes. PESEL is not stored.
Reversible: the downgrade drops the three columns (the addresses are typed in again).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0039_client_address"
down_revision: str | None = "0038_issued_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "clients"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("street", sa.String(255), nullable=True))
    op.add_column(TABLE, sa.Column("postal_code", sa.String(10), nullable=True))
    op.add_column(TABLE, sa.Column("city", sa.String(128), nullable=True))


def downgrade() -> None:
    op.drop_column(TABLE, "city")
    op.drop_column(TABLE, "postal_code")
    op.drop_column(TABLE, "street")
