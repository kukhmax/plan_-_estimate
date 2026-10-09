"""handover_protocols: the protocol of handing over the premises (Stage 16F.1)

Revision ID: 0047_handover_protocols
Revises: 0046_contract_signed
Create Date: 2026-10-10 18:00:00.000000

Canonical design: docs/STAGE_16_CONTRACTS_PROTOCOLS_PLAN_RU.md (16F).

One row per handover of one object: the day, the people present, the state of each requirement per room (JSON) and the decision per
room. At most one DRAFT per object (partial unique index), `sequence` unique per object. Reversible: the downgrade **refuses**
(rather than deletes) while any protocol exists.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0047_handover_protocols"
down_revision: str | None = "0046_contract_signed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "handover_protocols",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Uuid, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("held_on", sa.Date, nullable=True),
        sa.Column("held_time", sa.String(5), nullable=True),
        sa.Column("attendees", JSON, nullable=False),
        sa.Column("rooms", JSON, nullable=False),
        sa.Column("meters", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('DRAFT', 'ISSUED', 'ARCHIVED')", name="ck_handover_protocols_status"),
        sa.CheckConstraint("sequence >= 1", name="ck_handover_protocols_sequence_positive"),
        sa.UniqueConstraint("project_id", "sequence", name="uq_handover_protocols_project_sequence"),
    )
    op.create_index(
        "uq_handover_protocols_one_draft", "handover_protocols", ["project_id"], unique=True,
        postgresql_where=sa.text("status = 'DRAFT'"), sqlite_where=sa.text("status = 'DRAFT'"),
    )
    op.create_index("ix_handover_protocols_project", "handover_protocols", ["project_id", "status"])


def downgrade() -> None:
    count = op.get_bind().execute(sa.text("SELECT count(*) FROM handover_protocols")).scalar_one()
    if count:
        raise RuntimeError(f"cannot downgrade: {count} handover protocol(s) exist; they are evidence and are never dropped silently")
    op.drop_index("ix_handover_protocols_project", table_name="handover_protocols")
    op.drop_index("uq_handover_protocols_one_draft", table_name="handover_protocols")
    op.drop_table("handover_protocols")
