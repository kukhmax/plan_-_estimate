"""issued documents: the journal of client documents sent from the app (Stage 15F)

Revision ID: 0038_issued_documents
Revises: 0037_executor_profiles
Create Date: 2026-10-08 21:00:00.000000

Canonical design: docs/STAGE_15_DOCUMENTS_PDF_PLAN_RU.md (15F).

Creates issued_documents: one row per issue attempt of an estimate or a photo report (no file is stored: the row keeps what was
issued, its number, size, pages and checksum). `number` is unique per owner and `project_seq` (the running number of the
documents of one object) is unique per owner and project, so two simultaneous issues can never share either. Rows go with
their owner and with their project; the client is kept as a plain id (the document stays in the journal if the client is
deleted). Reversible: the downgrade drops the table (the journal is lost; no other table refers to it).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0038_issued_documents"
down_revision: str | None = "0037_executor_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "issued_documents"


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    op.create_table(
        TABLE,
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("owner_id", uuid_type, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", uuid_type, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("client_id", uuid_type, nullable=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("source_id", uuid_type, nullable=True),
        sa.Column("source_version", sa.Integer, nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("number", sa.String(64), nullable=False),
        sa.Column("project_seq", sa.Integer, nullable=False),
        sa.Column("template_version", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error_code", sa.String(64), nullable=True),
        sa.Column("scope", postgresql.JSONB().with_variant(sa.JSON(), "sqlite"), nullable=True),
        sa.Column("pages", sa.Integer, nullable=True),
        sa.Column("byte_size", sa.Integer, nullable=True),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("kind IN ('ESTIMATE', 'PHOTO_REPORT')", name="ck_issued_documents_kind"),
        sa.CheckConstraint("status IN ('PENDING', 'SENT', 'FAILED')", name="ck_issued_documents_status"),
        sa.CheckConstraint("project_seq >= 1", name="ck_issued_documents_seq_positive"),
        sa.CheckConstraint("length(number) > 0", name="ck_issued_documents_number_not_empty"),
        sa.UniqueConstraint("owner_id", "number", name="uq_issued_documents_owner_number"),
        sa.UniqueConstraint("owner_id", "project_id", "project_seq", name="uq_issued_documents_project_seq"),
    )
    op.create_index("ix_issued_documents_project_issued", TABLE, ["project_id", "issued_at"])


def downgrade() -> None:
    op.drop_index("ix_issued_documents_project_issued", table_name=TABLE)
    op.drop_table(TABLE)
