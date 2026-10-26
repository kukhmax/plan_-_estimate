"""V2-14: the link for the electrician and the plumber -- trade_links, trade_answers and trade_submissions

Revision ID: 0085_trade_links
Revises: 0084_user_trades
Create Date: 2026-11-03 10:00:00.000000

Three NEW tables: `trade_links` (only the SHA-256 of the secret, a term, the revoke mark, the last view, the owner's word to the craftsman), `trade_answers` (what the craftsman wrote for a
room: a typical position of the checklist or a position of his own; they belong to the object and the trade, not to a link) and `trade_submissions` (the journal of what he sent). The
columns that hold words (`owner_note`, `custom_name`, `note`, `master_name`) are TEXT because the data encryption keeps them as `enc1:...`. All three are owner- and object-scoped and go with
the object. No existing table changes and no existing row changes.

Reversible: the downgrade drops the three tables (the links and the journal exist nowhere else); it refuses while a craftsman's answer or a journal row exists, so nothing he wrote is lost silently.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0085_trade_links"
down_revision: str | None = "0084_user_trades"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TRADES = "trade IN ('ELECTRIC', 'PLUMBING')"


def upgrade() -> None:
    op.create_table(
        "trade_links",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trade", sa.String(16), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("language", sa.String(2), nullable=False),
        sa.Column("owner_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_viewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint(TRADES, name="ck_trade_links_trade"),
        sa.CheckConstraint("language IN ('pl', 'ru', 'uk', 'en')", name="ck_trade_links_language"),
    )
    op.create_index(
        "uq_trade_links_active",
        "trade_links",
        ["project_id", "trade"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
        sqlite_where=sa.text("revoked_at IS NULL"),
    )
    op.create_table(
        "trade_answers",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trade", sa.String(16), nullable=False),
        sa.Column("room_id", sa.Uuid(), sa.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position_key", sa.String(24), nullable=True),
        sa.Column("custom_name", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Numeric(8, 2), nullable=True),
        sa.Column("unit", sa.String(3), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(TRADES, name="ck_trade_answers_trade"),
        sa.CheckConstraint("unit IN ('PCS', 'LM')", name="ck_trade_answers_unit"),
        sa.CheckConstraint("quantity IS NULL OR quantity >= 0", name="ck_trade_answers_quantity"),
        sa.CheckConstraint(
            "(position_key IS NOT NULL AND custom_name IS NULL) OR (position_key IS NULL AND custom_name IS NOT NULL)",
            name="ck_trade_answers_typical_or_own",
        ),
        sa.CheckConstraint("position_key IS NULL OR quantity IS NOT NULL OR note IS NOT NULL", name="ck_trade_answers_typical_has_content"),
        sa.CheckConstraint("custom_name IS NULL OR quantity IS NOT NULL", name="ck_trade_answers_own_has_quantity"),
        sa.UniqueConstraint("project_id", "trade", "room_id", "position_key", name="uq_trade_answers_position"),
    )
    op.create_index("ix_trade_answers_room", "trade_answers", ["project_id", "trade", "room_id"])
    op.create_table(
        "trade_submissions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Uuid(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("link_id", sa.Uuid(), sa.ForeignKey("trade_links.id", ondelete="CASCADE"), nullable=False),
        sa.Column("trade", sa.String(16), nullable=False),
        sa.Column("master_name", sa.Text(), nullable=False),
        sa.Column("answers_hash", sa.String(64), nullable=False),
        sa.Column("answers_count", sa.Integer(), nullable=False),
        sa.Column("ip_hash", sa.String(64), nullable=False),
        sa.Column("agent_hash", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(TRADES, name="ck_trade_submissions_trade"),
    )
    op.create_index("ix_trade_submissions_project", "trade_submissions", ["project_id", "trade", "created_at"])


def downgrade() -> None:
    bind = op.get_bind()
    answers = bind.execute(sa.text("SELECT count(*) FROM trade_answers")).scalar_one()
    journal = bind.execute(sa.text("SELECT count(*) FROM trade_submissions")).scalar_one()
    if answers or journal:
        raise RuntimeError(
            f"cannot downgrade: {answers} answer(s) of craftsmen and {journal} journal row(s) exist; they are what the craftsmen wrote and are never dropped silently"
        )
    op.drop_index("ix_trade_submissions_project", table_name="trade_submissions")
    op.drop_table("trade_submissions")
    op.drop_index("ix_trade_answers_room", table_name="trade_answers")
    op.drop_table("trade_answers")
    op.drop_index("uq_trade_links_active", table_name="trade_links")
    op.drop_table("trade_links")
