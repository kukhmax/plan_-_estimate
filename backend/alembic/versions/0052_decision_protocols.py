"""decision_protocols: the protocol of information and decisions of the customer and its journal kind (Stage 16I.1)

Revision ID: 0052_decision_protocols
Revises: 0051_final_protocol_kind
Create Date: 2026-10-10 23:30:00.000000

Canonical design: docs/STAGE_16_CONTRACTS_PROTOCOLS_PLAN_RU.md (16I).

One row per sitting of one object: the day and time, the people present, the items (a risk of the application or a recommendation of the
contractor, each with the decision of the customer), the declaration that the customer understood, the refusal to sign, notes; the frozen
columns of an issued protocol (time, snapshot, exact page, contract). At most one DRAFT per object, `sequence` unique per object, an ISSUED
protocol always has its time, snapshot and page. Widens `ck_issued_documents_kind` with 'DECISION_PROTOCOL'.

Reversible: the downgrade **refuses** (rather than deletes) while any protocol or a journal row of this kind exists.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0052_decision_protocols"
down_revision: str | None = "0051_final_protocol_kind"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")
KINDS_NEW = (
    "kind IN ('ESTIMATE', 'PHOTO_REPORT', 'TECH_CARD', 'PRODUCTION_PLAN', 'CONTRACT', 'HANDOVER_PROTOCOL', 'CONCEALED_WORKS_PROTOCOL', "
    "'FINAL_PROTOCOL', 'DECISION_PROTOCOL')"
)
KINDS_OLD = (
    "kind IN ('ESTIMATE', 'PHOTO_REPORT', 'TECH_CARD', 'PRODUCTION_PLAN', 'CONTRACT', 'HANDOVER_PROTOCOL', 'CONCEALED_WORKS_PROTOCOL', 'FINAL_PROTOCOL')"
)


def upgrade() -> None:
    op.create_table(
        "decision_protocols",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Uuid, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("held_on", sa.Date, nullable=True),
        sa.Column("held_time", sa.String(5), nullable=True),
        sa.Column("attendees", JSON, nullable=False),
        sa.Column("items", JSON, nullable=False),
        sa.Column("understood", sa.Boolean, nullable=False),
        sa.Column("signature_refused", sa.Boolean, nullable=False),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snapshot", JSON, nullable=True),
        sa.Column("document_html", sa.Text, nullable=True),
        sa.Column("contract_id", sa.Uuid, nullable=True),
        sa.Column("contract_version", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('DRAFT', 'ISSUED', 'ARCHIVED')", name="ck_decision_protocols_status"),
        sa.CheckConstraint("sequence >= 1", name="ck_decision_protocols_sequence_positive"),
        sa.CheckConstraint(
            "status <> 'ISSUED' OR (issued_at IS NOT NULL AND snapshot IS NOT NULL AND document_html IS NOT NULL)",
            name="ck_decision_protocols_frozen_when_issued",
        ),
        sa.UniqueConstraint("project_id", "sequence", name="uq_decision_protocols_project_sequence"),
    )
    op.create_index(
        "uq_decision_protocols_one_draft", "decision_protocols", ["project_id"], unique=True,
        postgresql_where=sa.text("status = 'DRAFT'"), sqlite_where=sa.text("status = 'DRAFT'"),
    )
    op.create_index("ix_decision_protocols_project", "decision_protocols", ["project_id", "status"])
    with op.batch_alter_table("issued_documents") as batch:
        batch.drop_constraint("ck_issued_documents_kind", type_="check")
        batch.create_check_constraint("ck_issued_documents_kind", KINDS_NEW)


def downgrade() -> None:
    bind = op.get_bind()
    protocols = bind.execute(sa.text("SELECT count(*) FROM decision_protocols")).scalar_one()
    journal = bind.execute(sa.text("SELECT count(*) FROM issued_documents WHERE kind = 'DECISION_PROTOCOL'")).scalar_one()
    if protocols or journal:
        raise RuntimeError(
            f"cannot downgrade: {protocols} decision protocol(s) and {journal} journal row(s) exist; they are evidence and are never dropped silently"
        )
    with op.batch_alter_table("issued_documents") as batch:
        batch.drop_constraint("ck_issued_documents_kind", type_="check")
        batch.create_check_constraint("ck_issued_documents_kind", KINDS_OLD)
    op.drop_index("ix_decision_protocols_project", table_name="decision_protocols")
    op.drop_index("uq_decision_protocols_one_draft", table_name="decision_protocols")
    op.drop_table("decision_protocols")
