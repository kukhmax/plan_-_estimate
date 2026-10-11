"""calendar and reminders: planned dates of works, the queue of reminders, the calendar settings (Stage 18C)

Revision ID: 0054_calendar_reminders
Revises: 0053_downtime_episodes
Create Date: 2026-10-11 12:00:00.000000

Canonical design: docs/STAGE_18_CALENDAR_REMINDERS_PLAN_RU.md (section 4).

Three new tables, nothing else is touched: `work_schedule` (the planned date of a work, by `occurrence_key`, no foreign key to the plan so it
survives every plan save), `reminders` (the queue of messages to the owner and the owner's own reminders; unique `(owner_id, dedupe_key)`,
an index for the delivery loop on `(status, send_at)`), `calendar_settings` (one row per owner: zone, kinds, quiet hours, digest).

Reversible: the downgrade **refuses** (rather than deletes) while any planned date or any own (USER) reminder exists -- they are the owner's
data; the derived (AUTO) reminders and the settings are dropped, the reconciliation rebuilds the former.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0054_calendar_reminders"
down_revision: str | None = "0053_downtime_episodes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "work_schedule",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Uuid, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("occurrence_key", sa.Uuid, nullable=False),
        sa.Column("planned_date", sa.Date, nullable=False),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("uq_work_schedule_occurrence_key", "work_schedule", ["occurrence_key"], unique=True)
    op.create_index("ix_work_schedule_project", "work_schedule", ["project_id"])

    op.create_table(
        "reminders",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Uuid, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=True),
        sa.Column("room_id", sa.Uuid, nullable=True),
        sa.Column("surface_id", sa.Uuid, nullable=True),
        sa.Column("occurrence_key", sa.Uuid, nullable=True),
        sa.Column("origin", sa.String(4), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("ref", sa.String(40), nullable=False),
        sa.Column("title", sa.String(120), nullable=True),
        sa.Column("title_key", sa.String(80), nullable=True),
        sa.Column("params", JSON, nullable=False),
        sa.Column("event_on", sa.Date, nullable=True),
        sa.Column("event_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lead_days", sa.Integer, nullable=False),
        sa.Column("send_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tz", sa.String(64), nullable=False),
        sa.Column("close_on_status", sa.String(16), nullable=True),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("dedupe_key", sa.String(255), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("error_code", sa.String(40), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("origin IN ('AUTO', 'USER')", name="ck_reminders_origin"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'SENDING', 'SENT', 'SKIPPED', 'MISSED', 'FAILED', 'CANCELLED', 'DONE')", name="ck_reminders_status"
        ),
        sa.CheckConstraint("origin <> 'USER' OR title IS NOT NULL", name="ck_reminders_user_has_title"),
        sa.CheckConstraint("origin <> 'AUTO' OR title_key IS NOT NULL", name="ck_reminders_auto_has_title_key"),
        sa.CheckConstraint("event_on IS NULL OR event_at IS NULL", name="ck_reminders_one_event_time"),
        sa.CheckConstraint("close_on_status IS NULL OR close_on_status IN ('IN_PROGRESS', 'COMPLETED')", name="ck_reminders_close_on_status"),
        sa.CheckConstraint("attempts >= 0 AND lead_days >= 0", name="ck_reminders_counters"),
        sa.UniqueConstraint("owner_id", "dedupe_key", name="uq_reminders_owner_dedupe"),
    )
    op.create_index("ix_reminders_due", "reminders", ["status", "send_at"])
    op.create_index("ix_reminders_owner_project", "reminders", ["owner_id", "project_id"])
    op.create_index("ix_reminders_occurrence", "reminders", ["occurrence_key"])

    op.create_table(
        "calendar_settings",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("enabled", sa.Boolean, nullable=False),
        sa.Column("kind_overrides", JSON, nullable=False),
        sa.Column("quiet_from", sa.Time, nullable=False),
        sa.Column("quiet_to", sa.Time, nullable=False),
        sa.Column("digest_at", sa.Time, nullable=False),
        sa.Column("language", sa.String(2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("language IS NULL OR language IN ('pl', 'ru')", name="ck_calendar_settings_language"),
        sa.UniqueConstraint("owner_id", name="uq_calendar_settings_owner"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    planned = bind.execute(sa.text("SELECT count(*) FROM work_schedule")).scalar_one()
    own = bind.execute(sa.text("SELECT count(*) FROM reminders WHERE origin = 'USER'")).scalar_one()
    if planned or own:
        raise RuntimeError(
            f"cannot downgrade: {planned} planned date(s) and {own} own reminder(s) exist; they are the owner's data and are never dropped silently"
        )
    op.drop_table("calendar_settings")
    op.drop_index("ix_reminders_occurrence", table_name="reminders")
    op.drop_index("ix_reminders_owner_project", table_name="reminders")
    op.drop_index("ix_reminders_due", table_name="reminders")
    op.drop_table("reminders")
    op.drop_index("ix_work_schedule_project", table_name="work_schedule")
    op.drop_index("uq_work_schedule_occurrence_key", table_name="work_schedule")
    op.drop_table("work_schedule")
