"""trash for archived photo attachments (archive cleanup AC-1)

Revision ID: 0056_photo_trash
Revises: 0055_project_notes
Create Date: 2026-10-16 18:00:00.000000

One nullable column and one index on `photo_attachments`; nothing is deleted and no existing row changes:
- `trashed_at`: when an ARCHIVED attachment was put in the trash ("Kosz"). A CHECK keeps the trash a state of the archive
  (`trashed_at IS NULL OR archived_at IS NOT NULL`).
Reversible and lossless: the downgrade drops the column; the attachments stay archived (only the "in the trash" mark is lost).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0056_photo_trash"
down_revision: str | None = "0055_project_notes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # batch mode: plain ALTER on PostgreSQL (production), table rebuild on SQLite (the migration tests)
    with op.batch_alter_table("photo_attachments") as batch:
        batch.add_column(sa.Column("trashed_at", sa.DateTime(timezone=True), nullable=True))
        batch.create_check_constraint("ck_photo_attachments_trashed_is_archived", "trashed_at IS NULL OR archived_at IS NOT NULL")
    op.create_index("ix_photo_attachments_project_trashed", "photo_attachments", ["project_id", "trashed_at"])


def downgrade() -> None:
    op.drop_index("ix_photo_attachments_project_trashed", table_name="photo_attachments")
    with op.batch_alter_table("photo_attachments") as batch:
        batch.drop_constraint("ck_photo_attachments_trashed_is_archived", type_="check")
        batch.drop_column("trashed_at")
