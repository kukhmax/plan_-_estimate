"""executor profiles: the contractor's data for client documents (Stage 15C)

Revision ID: 0037_executor_profiles
Revises: 0036_photo_annotation_outline
Create Date: 2026-10-08 20:00:00.000000

Canonical design: docs/STAGE_15_DOCUMENTS_PDF_PLAN_RU.md (15C).

Creates executor_profiles: one row per owner (unique owner_id, CASCADE with the user), the name of the firm or person and
optional NIP / address / phone / e-mail / bank account, with CHECKs on the canonical lengths. Reversible: the downgrade
drops the table (the profile is typed in again; nothing else references it).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0037_executor_profiles"
down_revision: str | None = "0036_photo_annotation_outline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "executor_profiles"


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    op.create_table(
        TABLE,
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("owner_id", uuid_type, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("nip", sa.String(10), nullable=True),
        sa.Column("street", sa.String(255), nullable=True),
        sa.Column("postal_code", sa.String(6), nullable=True),
        sa.Column("city", sa.String(128), nullable=True),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("bank_account", sa.String(26), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("nip IS NULL OR length(nip) = 10", name="ck_executor_profiles_nip_length"),
        sa.CheckConstraint("bank_account IS NULL OR length(bank_account) = 26", name="ck_executor_profiles_account_length"),
        sa.CheckConstraint("length(name) > 0", name="ck_executor_profiles_name_not_empty"),
    )


def downgrade() -> None:
    op.drop_table(TABLE)
