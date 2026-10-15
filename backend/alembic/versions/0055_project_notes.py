"""notes of the owner on an object (Stage 18)

Revision ID: 0055_project_notes
Revises: 0054_calendar_reminders
Create Date: 2026-10-15 10:00:00.000000

One new table, nothing else is touched: `project_notes` (the owner's free words on an object with the time they were written).
Reversible: the downgrade **refuses** while any note exists -- the notes are the owner's data and are never dropped silently.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0055_project_notes"
down_revision: str | None = "0054_calendar_reminders"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_notes",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Uuid, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("length(trim(body)) > 0", name="ck_project_notes_body_not_blank"),
    )
    op.create_index("ix_project_notes_project_created", "project_notes", ["project_id", "created_at"])


def downgrade() -> None:
    notes = op.get_bind().execute(sa.text("SELECT count(*) FROM project_notes")).scalar_one()
    if notes:
        raise RuntimeError(f"cannot downgrade: {notes} note(s) exist; they are the owner's data and are never dropped silently")
    op.drop_index("ix_project_notes_project_created", table_name="project_notes")
    op.drop_table("project_notes")
