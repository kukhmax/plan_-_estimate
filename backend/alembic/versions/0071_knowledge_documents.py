"""V2-7a: the owner's own documents in the knowledge base -- knowledge_documents and knowledge_document_files

Revision ID: 0071_knowledge_documents
Revises: 0070_calendar_language
Create Date: 2026-10-25 10:00:00.000000

Two NEW tables: `knowledge_documents` (title, kind, link, date, "when to use", text, tags, the name / type / size of the file) and
`knowledge_document_files` (the bytes of the file, one row per document, in a table of its own so that a list never reads them). Both are
owner-scoped; deleting an owner or a document takes its rows. No existing table changes and no existing row changes.

Reversible: the downgrade drops the two tables (the documents of the owner are lost with them: they exist nowhere else).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0071_knowledge_documents"
down_revision: str | None = "0070_calendar_language"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("source_url", sa.String(1000), nullable=True),
        sa.Column("doc_date", sa.Date(), nullable=True),
        sa.Column("when_to_use", sa.Text(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("tags", postgresql.JSONB(), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=True),
        sa.Column("file_mime", sa.String(32), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('STATUTE', 'NORM', 'MANUFACTURER', 'TEMPLATE', 'OTHER')", name="ck_knowledge_documents_kind"),
        sa.CheckConstraint("length(trim(title)) > 0", name="ck_knowledge_documents_title_not_blank"),
        sa.CheckConstraint("body IS NOT NULL OR source_url IS NOT NULL OR file_name IS NOT NULL", name="ck_knowledge_documents_has_content"),
        sa.CheckConstraint(
            "(file_name IS NULL AND file_mime IS NULL AND file_size IS NULL) OR (file_name IS NOT NULL AND file_mime IS NOT NULL AND file_size > 0)",
            name="ck_knowledge_documents_file_together",
        ),
    )
    op.create_index("ix_knowledge_documents_owner_updated", "knowledge_documents", ["owner_id", "updated_at"])
    op.create_table(
        "knowledge_document_files",
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("content", sa.LargeBinary(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("knowledge_document_files")
    op.drop_index("ix_knowledge_documents_owner_updated", table_name="knowledge_documents")
    op.drop_table("knowledge_documents")
