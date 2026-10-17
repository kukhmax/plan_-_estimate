"""photos of the settlement records: receipts and invoices (invoices and advances, IA-3)

Revision ID: 0059_payment_photos
Revises: 0058_project_payments
Create Date: 2026-10-17 20:00:00.000000

Adds a ninth context to `photo_attachments`: `PAYMENT`, a photo of a receipt or an invoice kept with a settlement record.
- the enum value `PAYMENT` (PostgreSQL: committed before it is used, `ADD VALUE` cannot be used in the transaction that adds it);
- the nullable column `payment_id` -> `project_payments.id`, `ON DELETE RESTRICT` like every other evidence parent, and its index;
- the CHECK of the contexts rebuilt: every old branch also requires `payment_id IS NULL`, the new branch requires only `payment_id`;
- one partial unique index for the active rows of the new context.
No row changes. Reversible while no `PAYMENT` photo exists: the downgrade **refuses** otherwise (the photos of receipts are the owner's
evidence). The enum value stays in PostgreSQL after a downgrade (a value cannot be dropped from an enum without rebuilding the type);
nothing can use it, and the next upgrade finds it already there.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0059_payment_photos"
down_revision: str | None = "0058_project_payments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECK_NAME = "ck_photo_attachments_context_targets"

# the branches as 0032 made them
OLD_CHECK = (
    "(context = 'PROJECT' AND room_id IS NULL AND surface_id IS NULL AND opening_id IS NULL"
    " AND inspection_id IS NULL AND question_id IS NULL AND finding_id IS NULL"
    " AND occurrence_key IS NULL AND price_item_id IS NULL)"
    " OR (context = 'ROOM' AND room_id IS NOT NULL AND surface_id IS NULL AND opening_id IS NULL"
    " AND inspection_id IS NULL AND question_id IS NULL AND finding_id IS NULL"
    " AND occurrence_key IS NULL AND price_item_id IS NULL)"
    " OR (context = 'SURFACE' AND surface_id IS NOT NULL AND room_id IS NULL AND opening_id IS NULL"
    " AND inspection_id IS NULL AND question_id IS NULL AND finding_id IS NULL"
    " AND occurrence_key IS NULL AND price_item_id IS NULL)"
    " OR (context = 'OPENING' AND opening_id IS NOT NULL AND room_id IS NULL AND surface_id IS NULL"
    " AND inspection_id IS NULL AND question_id IS NULL AND finding_id IS NULL"
    " AND occurrence_key IS NULL AND price_item_id IS NULL)"
    " OR (context = 'INSPECTION' AND inspection_id IS NOT NULL AND room_id IS NULL AND surface_id IS NULL"
    " AND opening_id IS NULL AND finding_id IS NULL AND occurrence_key IS NULL AND price_item_id IS NULL)"
    " OR (context = 'FINDING' AND finding_id IS NOT NULL AND room_id IS NULL AND surface_id IS NULL"
    " AND opening_id IS NULL AND inspection_id IS NULL AND question_id IS NULL"
    " AND occurrence_key IS NULL AND price_item_id IS NULL)"
    " OR (context = 'WORK' AND surface_id IS NOT NULL AND occurrence_key IS NOT NULL"
    " AND price_item_id IS NOT NULL AND room_id IS NULL AND opening_id IS NULL"
    " AND inspection_id IS NULL AND question_id IS NULL AND finding_id IS NULL)"
)

# every old branch with `payment_id IS NULL`, and the branch of the new context
NEW_CHECK = (
    "(context = 'PROJECT' AND room_id IS NULL AND surface_id IS NULL AND opening_id IS NULL AND inspection_id IS NULL AND question_id IS NULL AND finding_id IS NULL AND occurrence_key IS NULL AND price_item_id IS NULL AND payment_id IS NULL)"
    " OR (context = 'ROOM' AND room_id IS NOT NULL AND surface_id IS NULL AND opening_id IS NULL AND inspection_id IS NULL AND question_id IS NULL AND finding_id IS NULL AND occurrence_key IS NULL AND price_item_id IS NULL AND payment_id IS NULL)"
    " OR (context = 'SURFACE' AND surface_id IS NOT NULL AND room_id IS NULL AND opening_id IS NULL AND inspection_id IS NULL AND question_id IS NULL AND finding_id IS NULL AND occurrence_key IS NULL AND price_item_id IS NULL AND payment_id IS NULL)"
    " OR (context = 'OPENING' AND opening_id IS NOT NULL AND room_id IS NULL AND surface_id IS NULL AND inspection_id IS NULL AND question_id IS NULL AND finding_id IS NULL AND occurrence_key IS NULL AND price_item_id IS NULL AND payment_id IS NULL)"
    " OR (context = 'INSPECTION' AND inspection_id IS NOT NULL AND room_id IS NULL AND surface_id IS NULL AND opening_id IS NULL AND finding_id IS NULL AND occurrence_key IS NULL AND price_item_id IS NULL AND payment_id IS NULL)"
    " OR (context = 'FINDING' AND finding_id IS NOT NULL AND room_id IS NULL AND surface_id IS NULL AND opening_id IS NULL AND inspection_id IS NULL AND question_id IS NULL AND occurrence_key IS NULL AND price_item_id IS NULL AND payment_id IS NULL)"
    " OR (context = 'WORK' AND surface_id IS NOT NULL AND occurrence_key IS NOT NULL AND price_item_id IS NOT NULL AND room_id IS NULL AND opening_id IS NULL AND inspection_id IS NULL AND question_id IS NULL AND finding_id IS NULL AND payment_id IS NULL)"
    " OR (context = 'PAYMENT' AND payment_id IS NOT NULL AND room_id IS NULL AND surface_id IS NULL AND opening_id IS NULL AND inspection_id IS NULL AND question_id IS NULL AND finding_id IS NULL AND occurrence_key IS NULL AND price_item_id IS NULL)"
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE photoattachmentcontext ADD VALUE IF NOT EXISTS 'PAYMENT'")
    with op.batch_alter_table("photo_attachments") as batch:
        batch.add_column(sa.Column("payment_id", sa.Uuid, nullable=True))
        # named, as a batch (SQLite) requires; the name PostgreSQL would have given it
        batch.create_foreign_key("photo_attachments_payment_id_fkey", "project_payments", ["payment_id"], ["id"], ondelete="RESTRICT")
        batch.drop_constraint(CHECK_NAME, type_="check")
        batch.create_check_constraint(CHECK_NAME, NEW_CHECK)
    op.create_index("ix_photo_attachments_payment_id", "photo_attachments", ["payment_id"])
    where = sa.text("context = 'PAYMENT' AND archived_at IS NULL")
    op.create_index(
        "uq_photo_att_payment_active", "photo_attachments", ["asset_id", "payment_id"], unique=True, sqlite_where=where, postgresql_where=where
    )


def downgrade() -> None:
    bind = op.get_bind()
    photos = bind.execute(sa.text("SELECT count(*) FROM photo_attachments WHERE payment_id IS NOT NULL")).scalar_one()
    if photos:
        raise RuntimeError(f"cannot downgrade: {photos} photo(s) of settlement records exist; they are the owner's evidence and are never dropped silently")
    op.drop_index("uq_photo_att_payment_active", table_name="photo_attachments")
    op.drop_index("ix_photo_attachments_payment_id", table_name="photo_attachments")
    with op.batch_alter_table("photo_attachments") as batch:
        batch.drop_constraint(CHECK_NAME, type_="check")
        batch.create_check_constraint(CHECK_NAME, OLD_CHECK)
        batch.drop_column("payment_id")
