"""contracts: the contract of an object with the answers of the questionnaire (Stage 16E.1)

Revision ID: 0044_contracts
Revises: 0043_issued_docs_plan
Create Date: 2026-10-09 22:00:00.000000

Canonical design: docs/STAGE_16_CONTRACTS_PROTOCOLS_PLAN_RU.md (16E).

Creates contracts: one row per version of the contract of one object, with the answers of the questionnaire "compose the contract"
(JSON) and the version of the questionnaire they belong to. States DRAFT / ISSUED / SIGNED / ARCHIVED (CHECK); a partial unique
index allows **one draft per object**; (project_id, version) is unique. Rows go with their owner and with their project.
Reversible: the downgrade drops the indexes and the table (the answers are typed in again).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0044_contracts"
down_revision: str | None = "0043_issued_docs_plan"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "contracts"


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    op.create_table(
        TABLE,
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("owner_id", uuid_type, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", uuid_type, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("answers", postgresql.JSONB().with_variant(sa.JSON(), "sqlite"), nullable=False),
        sa.Column("questionnaire_version", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('DRAFT', 'ISSUED', 'SIGNED', 'ARCHIVED')", name="ck_contracts_status"),
        sa.CheckConstraint("version >= 1", name="ck_contracts_version_positive"),
        sa.UniqueConstraint("project_id", "version", name="uq_contracts_project_version"),
    )
    op.create_index(
        "uq_contracts_one_draft", TABLE, ["project_id"], unique=True,
        postgresql_where=sa.text("status = 'DRAFT'"), sqlite_where=sa.text("status = 'DRAFT'"),
    )
    op.create_index("ix_contracts_project", TABLE, ["project_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_contracts_project", table_name=TABLE)
    op.drop_index("uq_contracts_one_draft", table_name=TABLE)
    op.drop_table(TABLE)
