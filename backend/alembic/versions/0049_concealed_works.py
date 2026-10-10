"""concealed_works_protocols: the protocol of acceptance of concealed works and its journal kind (Stage 16G)

Revision ID: 0049_concealed_works
Revises: 0048_handover_issue
Create Date: 2026-10-10 22:00:00.000000

Canonical design: docs/STAGE_16_CONTRACTS_PROTOCOLS_PLAN_RU.md (16G).

One row per acceptance of one kind of work on one surface, accepted before it is covered: the day, the people present or the day the
absent customer was notified, the material and batch, the photos chosen as evidence, the result and the consent to cover; the frozen
columns of an issued protocol (time, snapshot, exact page, contract). At most one DRAFT per object, `sequence` unique per object,
an ISSUED protocol always has its time, snapshot and page. Widens `ck_issued_documents_kind` with 'CONCEALED_WORKS_PROTOCOL'.

Reversible: the downgrade **refuses** (rather than deletes) while any protocol or a journal row of this kind exists.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0049_concealed_works"
down_revision: str | None = "0048_handover_issue"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")
KINDS_NEW = "kind IN ('ESTIMATE', 'PHOTO_REPORT', 'TECH_CARD', 'PRODUCTION_PLAN', 'CONTRACT', 'HANDOVER_PROTOCOL', 'CONCEALED_WORKS_PROTOCOL')"
KINDS_OLD = "kind IN ('ESTIMATE', 'PHOTO_REPORT', 'TECH_CARD', 'PRODUCTION_PLAN', 'CONTRACT', 'HANDOVER_PROTOCOL')"


def upgrade() -> None:
    op.create_table(
        "concealed_works_protocols",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Uuid, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("held_on", sa.Date, nullable=True),
        sa.Column("held_time", sa.String(5), nullable=True),
        sa.Column("customer_absent", sa.Boolean, nullable=False),
        sa.Column("notified_on", sa.Date, nullable=True),
        sa.Column("attendees", JSON, nullable=False),
        sa.Column("surface_id", sa.Uuid, nullable=True),
        sa.Column("work_kind", sa.String(40), nullable=True),
        sa.Column("work_note", sa.Text, nullable=True),
        sa.Column("material", sa.String(500), nullable=True),
        sa.Column("batch", sa.String(255), nullable=True),
        sa.Column("photo_ids", JSON, nullable=False),
        sa.Column("result", sa.String(16), nullable=True),
        sa.Column("remarks", sa.Text, nullable=True),
        sa.Column("cover_consent", sa.String(16), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snapshot", JSON, nullable=True),
        sa.Column("document_html", sa.Text, nullable=True),
        sa.Column("contract_id", sa.Uuid, nullable=True),
        sa.Column("contract_version", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('DRAFT', 'ISSUED', 'ARCHIVED')", name="ck_concealed_works_status"),
        sa.CheckConstraint("sequence >= 1", name="ck_concealed_works_sequence_positive"),
        sa.CheckConstraint("result IS NULL OR result IN ('ACCEPTED', 'WITH_REMARKS')", name="ck_concealed_works_result"),
        sa.CheckConstraint("cover_consent IS NULL OR cover_consent IN ('GIVEN', 'WITHHELD')", name="ck_concealed_works_cover_consent"),
        sa.CheckConstraint(
            "status <> 'ISSUED' OR (issued_at IS NOT NULL AND snapshot IS NOT NULL AND document_html IS NOT NULL)",
            name="ck_concealed_works_frozen_when_issued",
        ),
        sa.UniqueConstraint("project_id", "sequence", name="uq_concealed_works_project_sequence"),
    )
    op.create_index(
        "uq_concealed_works_one_draft", "concealed_works_protocols", ["project_id"], unique=True,
        postgresql_where=sa.text("status = 'DRAFT'"), sqlite_where=sa.text("status = 'DRAFT'"),
    )
    op.create_index("ix_concealed_works_project", "concealed_works_protocols", ["project_id", "status"])
    with op.batch_alter_table("issued_documents") as batch:
        batch.drop_constraint("ck_issued_documents_kind", type_="check")
        batch.create_check_constraint("ck_issued_documents_kind", KINDS_NEW)


def downgrade() -> None:
    bind = op.get_bind()
    protocols = bind.execute(sa.text("SELECT count(*) FROM concealed_works_protocols")).scalar_one()
    journal = bind.execute(sa.text("SELECT count(*) FROM issued_documents WHERE kind = 'CONCEALED_WORKS_PROTOCOL'")).scalar_one()
    if protocols or journal:
        raise RuntimeError(
            f"cannot downgrade: {protocols} concealed works protocol(s) and {journal} journal row(s) exist; they are evidence and are never dropped silently"
        )
    with op.batch_alter_table("issued_documents") as batch:
        batch.drop_constraint("ck_issued_documents_kind", type_="check")
        batch.create_check_constraint("ck_issued_documents_kind", KINDS_OLD)
    op.drop_index("ix_concealed_works_project", table_name="concealed_works_protocols")
    op.drop_index("uq_concealed_works_one_draft", table_name="concealed_works_protocols")
    op.drop_table("concealed_works_protocols")
