"""V2-8: the link for the client -- client_links, client_proposals and client_consents

Revision ID: 0072_client_links
Revises: 0071_knowledge_documents
Create Date: 2026-10-26 10:00:00.000000

Three NEW tables: `client_links` (only the SHA-256 of the secret, a term, the revoke mark, the last view), `client_proposals` (extra works the
client decides; title and description are ciphertext columns) and `client_consents` (the journal of what the client agreed to; the signer name
is a ciphertext column). All three are owner- and object-scoped and go with the object. No existing table changes and no existing row changes.

Reversible: the downgrade drops the three tables (the links and the journal exist nowhere else).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0072_client_links"
down_revision: str | None = "0071_knowledge_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "client_links",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("language", sa.String(2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("language IN ('pl', 'ru', 'uk', 'en')", name="ck_client_links_language"),
    )
    op.create_index(
        "uq_client_links_active_project",
        "client_links",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_table(
        "client_proposals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("extra_days", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('OPEN', 'ACCEPTED', 'DECLINED', 'WITHDRAWN')", name="ck_client_proposals_status"),
        sa.CheckConstraint("amount > 0", name="ck_client_proposals_amount_positive"),
        sa.CheckConstraint("extra_days IS NULL OR extra_days >= 0", name="ck_client_proposals_days_not_negative"),
        sa.UniqueConstraint("project_id", "sequence", name="uq_client_proposals_project_sequence"),
    )
    op.create_index("ix_client_proposals_project_status", "client_proposals", ["project_id", "status"])
    op.create_table(
        "client_consents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("link_id", sa.Uuid(), sa.ForeignKey("client_links.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("estimate_id", sa.Uuid(), nullable=True),
        sa.Column("estimate_version", sa.Integer(), nullable=True),
        sa.Column("proposal_id", sa.Uuid(), nullable=True),
        sa.Column("subject_hash", sa.String(64), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("statement_lang", sa.String(2), nullable=False),
        sa.Column("signer_name", sa.Text(), nullable=False),
        sa.Column("ip_hash", sa.String(64), nullable=False),
        sa.Column("agent_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('ESTIMATE_ACCEPTED', 'PROPOSAL_ACCEPTED', 'PROPOSAL_DECLINED')", name="ck_client_consents_kind"
        ),
        sa.CheckConstraint(
            "(kind = 'ESTIMATE_ACCEPTED' AND estimate_id IS NOT NULL AND proposal_id IS NULL)"
            " OR (kind <> 'ESTIMATE_ACCEPTED' AND proposal_id IS NOT NULL)",
            name="ck_client_consents_subject",
        ),
        sa.UniqueConstraint("estimate_id", name="uq_client_consents_estimate"),
        sa.UniqueConstraint("proposal_id", name="uq_client_consents_proposal"),
    )
    op.create_index("ix_client_consents_project_created", "client_consents", ["project_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_client_consents_project_created", table_name="client_consents")
    op.drop_table("client_consents")
    op.drop_index("ix_client_proposals_project_status", table_name="client_proposals")
    op.drop_table("client_proposals")
    op.drop_index("uq_client_links_active_project", table_name="client_links")
    op.drop_table("client_links")
