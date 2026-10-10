"""downtime_episodes: the notice and the protocol of downtime and their journal kinds (Stage 16I.3)

Revision ID: 0053_downtime_episodes
Revises: 0052_decision_protocols
Create Date: 2026-10-11 00:10:00.000000

Canonical design: docs/STAGE_16_CONTRACTS_PROTOCOLS_PLAN_RU.md (16I).

One row per downtime on the customer's side: the cause, the rooms, the photos and what the contractor needs (the notice), the days with the
people present or the refusal to sign (the protocol), and the frozen columns of the two issued documents. At most one open episode (DRAFT or
NOTICED) per object, `sequence` unique per object; a NOTICED or CLOSED episode always has its frozen notice, a CLOSED one its frozen
protocol. Widens `ck_issued_documents_kind` with 'DOWNTIME_NOTICE' and 'DOWNTIME_PROTOCOL'.

Reversible: the downgrade **refuses** (rather than deletes) while any episode or a journal row of these kinds exists.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0053_downtime_episodes"
down_revision: str | None = "0052_decision_protocols"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")
KINDS_NEW = (
    "kind IN ('ESTIMATE', 'PHOTO_REPORT', 'TECH_CARD', 'PRODUCTION_PLAN', 'CONTRACT', 'HANDOVER_PROTOCOL', 'CONCEALED_WORKS_PROTOCOL', "
    "'FINAL_PROTOCOL', 'DECISION_PROTOCOL', 'DOWNTIME_NOTICE', 'DOWNTIME_PROTOCOL')"
)
KINDS_OLD = (
    "kind IN ('ESTIMATE', 'PHOTO_REPORT', 'TECH_CARD', 'PRODUCTION_PLAN', 'CONTRACT', 'HANDOVER_PROTOCOL', 'CONCEALED_WORKS_PROTOCOL', "
    "'FINAL_PROTOCOL', 'DECISION_PROTOCOL')"
)


def upgrade() -> None:
    op.create_table(
        "downtime_episodes",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Uuid, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("cause_key", sa.String(40), nullable=True),
        sa.Column("cause_note", sa.Text, nullable=True),
        sa.Column("room_ids", JSON, nullable=False),
        sa.Column("noticed_on", sa.Date, nullable=True),
        sa.Column("noticed_time", sa.String(5), nullable=True),
        sa.Column("notice_channel", sa.String(255), nullable=True),
        sa.Column("photo_ids", JSON, nullable=False),
        sa.Column("need_text", sa.Text, nullable=True),
        sa.Column("need_by", sa.Date, nullable=True),
        sa.Column("days", JSON, nullable=False),
        sa.Column("held_on", sa.Date, nullable=True),
        sa.Column("held_time", sa.String(5), nullable=True),
        sa.Column("attendees", JSON, nullable=False),
        sa.Column("signature_refused", sa.Boolean, nullable=False),
        sa.Column("deadline_note", sa.Text, nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("notice_issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notice_number", sa.String(64), nullable=True),
        sa.Column("notice_snapshot", JSON, nullable=True),
        sa.Column("notice_html", sa.Text, nullable=True),
        sa.Column("protocol_issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("protocol_snapshot", JSON, nullable=True),
        sa.Column("protocol_html", sa.Text, nullable=True),
        sa.Column("contract_id", sa.Uuid, nullable=True),
        sa.Column("contract_version", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('DRAFT', 'NOTICED', 'CLOSED', 'ARCHIVED')", name="ck_downtime_episodes_status"),
        sa.CheckConstraint("sequence >= 1", name="ck_downtime_episodes_sequence_positive"),
        sa.CheckConstraint(
            "status NOT IN ('NOTICED', 'CLOSED') OR (notice_issued_at IS NOT NULL AND notice_snapshot IS NOT NULL AND notice_html IS NOT NULL)",
            name="ck_downtime_episodes_notice_frozen",
        ),
        sa.CheckConstraint(
            "status <> 'CLOSED' OR (protocol_issued_at IS NOT NULL AND protocol_snapshot IS NOT NULL AND protocol_html IS NOT NULL)",
            name="ck_downtime_episodes_protocol_frozen",
        ),
        sa.UniqueConstraint("project_id", "sequence", name="uq_downtime_episodes_project_sequence"),
    )
    op.create_index(
        "uq_downtime_episodes_one_open", "downtime_episodes", ["project_id"], unique=True,
        postgresql_where=sa.text("status IN ('DRAFT', 'NOTICED')"), sqlite_where=sa.text("status IN ('DRAFT', 'NOTICED')"),
    )
    op.create_index("ix_downtime_episodes_project", "downtime_episodes", ["project_id", "status"])
    with op.batch_alter_table("issued_documents") as batch:
        batch.drop_constraint("ck_issued_documents_kind", type_="check")
        batch.create_check_constraint("ck_issued_documents_kind", KINDS_NEW)


def downgrade() -> None:
    bind = op.get_bind()
    episodes = bind.execute(sa.text("SELECT count(*) FROM downtime_episodes")).scalar_one()
    journal = bind.execute(sa.text("SELECT count(*) FROM issued_documents WHERE kind IN ('DOWNTIME_NOTICE', 'DOWNTIME_PROTOCOL')")).scalar_one()
    if episodes or journal:
        raise RuntimeError(
            f"cannot downgrade: {episodes} downtime episode(s) and {journal} journal row(s) exist; they are evidence and are never dropped silently"
        )
    with op.batch_alter_table("issued_documents") as batch:
        batch.drop_constraint("ck_issued_documents_kind", type_="check")
        batch.create_check_constraint("ck_issued_documents_kind", KINDS_OLD)
    op.drop_index("ix_downtime_episodes_project", table_name="downtime_episodes")
    op.drop_index("uq_downtime_episodes_one_open", table_name="downtime_episodes")
    op.drop_table("downtime_episodes")
