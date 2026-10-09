"""adjacent works: the register of other contractors' works on an object (Stage 16D.1)

Revision ID: 0042_adjacent_works
Revises: 0041_issued_documents_tech_card
Create Date: 2026-10-09 20:00:00.000000

Canonical design: docs/STAGE_16_CONTRACTS_PROTOCOLS_PLAN_RU.md (16D, owner addition A4).

Creates adjacent_works: what other contractors do on the object, who does it, in which rooms (a JSON list of room ids; null = the
whole object), when, how it is ordered against the contractor's own works, who answers for cleanliness and damage and who
coordinates. Rows go with their owner and with their project; nothing else refers to the table (the production plan and the
contract copy what they need into their own snapshot). Reversible: the downgrade drops the index and the table.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0042_adjacent_works"
down_revision: str | None = "0041_issued_documents_tech_card"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "adjacent_works"


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    op.create_table(
        TABLE,
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("owner_id", uuid_type, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", uuid_type, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_name", sa.String(255), nullable=False),
        sa.Column("performer", sa.String(255), nullable=True),
        sa.Column("room_ids", postgresql.JSONB().with_variant(sa.JSON(), "sqlite"), nullable=True),
        sa.Column("period_from", sa.Date, nullable=True),
        sa.Column("period_to", sa.Date, nullable=True),
        sa.Column("order_relation", sa.String(16), nullable=False),
        sa.Column("order_note", sa.String(1000), nullable=True),
        sa.Column("responsibility_note", sa.String(1000), nullable=True),
        sa.Column("coordination_note", sa.String(1000), nullable=True),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("is_archived", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("order_relation IN ('BEFORE_OURS', 'PARALLEL', 'AFTER_OURS')", name="ck_adjacent_works_order"),
        sa.CheckConstraint("length(work_name) > 0", name="ck_adjacent_works_name_not_empty"),
        sa.CheckConstraint(
            "period_from IS NULL OR period_to IS NULL OR period_to >= period_from", name="ck_adjacent_works_period"
        ),
    )
    op.create_index("ix_adjacent_works_project", TABLE, ["project_id", "is_archived"])


def downgrade() -> None:
    op.drop_index("ix_adjacent_works_project", table_name=TABLE)
    op.drop_table(TABLE)
