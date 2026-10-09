"""project representatives: the persons who act for each side of an object (Stage 16B.2)

Revision ID: 0040_project_representatives
Revises: 0039_client_address
Create Date: 2026-10-09 15:00:00.000000

Canonical design: docs/STAGE_16_CONTRACTS_PROTOCOLS_PLAN_RU.md (16B.2).

Creates project_representatives: the register of persons of one object (the customer, the customer's representative, the
supervision, the contractor's representative) with the owner's mark "may accept the work and sign the protocols". Rows go with
their owner and with their project; nothing else refers to the table (a contract copies the chosen persons into its own snapshot).
Reversible: the downgrade drops the index and the table (the register is typed in again).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0040_project_representatives"
down_revision: str | None = "0039_client_address"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "project_representatives"


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    op.create_table(
        TABLE,
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("owner_id", uuid_type, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", uuid_type, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("side", sa.String(32), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("role_title", sa.String(255), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("may_accept_and_sign", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_archived", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "side IN ('CUSTOMER', 'CUSTOMER_REPRESENTATIVE', 'SUPERVISION', 'CONTRACTOR')",
            name="ck_project_representatives_side",
        ),
        sa.CheckConstraint("length(name) > 0", name="ck_project_representatives_name_not_empty"),
    )
    op.create_index("ix_project_representatives_project", TABLE, ["project_id", "is_archived"])


def downgrade() -> None:
    op.drop_index("ix_project_representatives_project", table_name=TABLE)
    op.drop_table(TABLE)
