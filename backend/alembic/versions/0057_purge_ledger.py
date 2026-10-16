"""the ledger of what was deleted for good (archive cleanup AC-2)

Revision ID: 0057_purge_ledger
Revises: 0056_photo_trash
Create Date: 2026-10-16 20:00:00.000000

One new table, nothing else is touched: `purge_ledger` (one row per deleted photo: the storage keys, sums, sizes, the time and the two
states -- removed from the working storage / removed from the backups). It has no foreign keys on purpose: the obligation to clean the
backups outlives the rows of the photo, its object and its owner.
Reversible, but the downgrade **refuses** while any row exists -- the ledger is the record of what must still be removed from the backups.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0057_purge_ledger"
down_revision: str | None = "0056_photo_trash"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "purge_ledger",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, nullable=False),
        sa.Column("project_id", sa.Uuid, nullable=False),
        sa.Column("asset_id", sa.Uuid, nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("storage_name", sa.String(40), nullable=False),
        sa.Column("storage_key_original", sa.String(255), nullable=False),
        sa.Column("storage_key_display", sa.String(255), nullable=False),
        sa.Column("storage_key_thumbnail", sa.String(255), nullable=False),
        sa.Column("sha256", sa.CHAR(64), nullable=False),
        sa.Column("byte_size", sa.BigInteger, nullable=False),
        sa.Column("display_byte_size", sa.BigInteger, nullable=False),
        sa.Column("thumbnail_byte_size", sa.BigInteger, nullable=False),
        sa.Column("purged_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("storage_state", sa.String(16), nullable=False),
        sa.Column("storage_done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("backup_state", sa.String(16), nullable=False),
        sa.Column("backup_done_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("kind IN ('PHOTO')", name="ck_purge_ledger_kind"),
        sa.CheckConstraint("storage_state IN ('PENDING', 'DONE')", name="ck_purge_ledger_storage_state"),
        sa.CheckConstraint("backup_state IN ('PENDING', 'DONE')", name="ck_purge_ledger_backup_state"),
        sa.CheckConstraint("storage_state <> 'DONE' OR storage_done_at IS NOT NULL", name="ck_purge_ledger_storage_done_at"),
        sa.CheckConstraint("backup_state <> 'DONE' OR backup_done_at IS NOT NULL", name="ck_purge_ledger_backup_done_at"),
    )
    op.create_index("ix_purge_ledger_owner_states", "purge_ledger", ["owner_id", "storage_state", "backup_state"])
    op.create_index("uq_purge_ledger_asset", "purge_ledger", ["asset_id"], unique=True)


def downgrade() -> None:
    rows = op.get_bind().execute(sa.text("SELECT count(*) FROM purge_ledger")).scalar_one()
    if rows:
        raise RuntimeError(f"cannot downgrade: {rows} ledger row(s) exist; they record what must still be removed from the backups and are never dropped silently")
    op.drop_index("uq_purge_ledger_asset", table_name="purge_ledger")
    op.drop_index("ix_purge_ledger_owner_states", table_name="purge_ledger")
    op.drop_table("purge_ledger")
