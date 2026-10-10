"""acceptance_protocols: the protocol of acceptance of the work, partial or final (Stage 16H.1)

Revision ID: 0050_acceptance_protocols
Revises: 0049_concealed_works
Create Date: 2026-10-11 09:00:00.000000

Canonical design: docs/STAGE_16_CONTRACTS_PROTOCOLS_PLAN_RU.md (16H, section 5).

One row per acceptance event of one object: the day, the people present or the days the absent customer was notified, the rooms in
scope, the conditions and tools of the assessment, the remarks per surface (JSON), what the contract asks the protocol to carry
(batches, instruction of use, the amount due and retained) and the frozen columns of an issued protocol. At most one DRAFT per object,
`sequence` unique per object, an ISSUED protocol always has its time, snapshot and page.

Reversible: the downgrade **refuses** (rather than deletes) while any protocol exists.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0050_acceptance_protocols"
down_revision: str | None = "0049_concealed_works"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "acceptance_protocols",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Uuid, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("held_on", sa.Date, nullable=True),
        sa.Column("held_time", sa.String(5), nullable=True),
        sa.Column("customer_absent", sa.Boolean, nullable=False),
        sa.Column("notified_on", sa.Date, nullable=True),
        sa.Column("renotified_on", sa.Date, nullable=True),
        sa.Column("attendees", JSON, nullable=False),
        sa.Column("room_ids", JSON, nullable=False),
        sa.Column("conditions_note", sa.Text, nullable=True),
        sa.Column("instrument_keys", JSON, nullable=False),
        sa.Column("surfaces", JSON, nullable=False),
        sa.Column("batches", sa.Text, nullable=True),
        sa.Column("instructions_given", sa.Boolean, nullable=False),
        sa.Column("amount_due", sa.String(16), nullable=True),
        sa.Column("amount_retained", sa.String(16), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snapshot", JSON, nullable=True),
        sa.Column("document_html", sa.Text, nullable=True),
        sa.Column("contract_id", sa.Uuid, nullable=True),
        sa.Column("contract_version", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('DRAFT', 'ISSUED', 'ARCHIVED')", name="ck_acceptance_protocols_status"),
        sa.CheckConstraint("sequence >= 1", name="ck_acceptance_protocols_sequence_positive"),
        sa.CheckConstraint(
            "status <> 'ISSUED' OR (issued_at IS NOT NULL AND snapshot IS NOT NULL AND document_html IS NOT NULL)",
            name="ck_acceptance_protocols_frozen_when_issued",
        ),
        sa.UniqueConstraint("project_id", "sequence", name="uq_acceptance_protocols_project_sequence"),
    )
    op.create_index(
        "uq_acceptance_protocols_one_draft", "acceptance_protocols", ["project_id"], unique=True,
        postgresql_where=sa.text("status = 'DRAFT'"), sqlite_where=sa.text("status = 'DRAFT'"),
    )
    op.create_index("ix_acceptance_protocols_project", "acceptance_protocols", ["project_id", "status"])


def downgrade() -> None:
    count = op.get_bind().execute(sa.text("SELECT count(*) FROM acceptance_protocols")).scalar_one()
    if count:
        raise RuntimeError(f"cannot downgrade: {count} acceptance protocol(s) exist; they are evidence and are never dropped silently")
    op.drop_index("ix_acceptance_protocols_project", table_name="acceptance_protocols")
    op.drop_index("uq_acceptance_protocols_one_draft", table_name="acceptance_protocols")
    op.drop_table("acceptance_protocols")
