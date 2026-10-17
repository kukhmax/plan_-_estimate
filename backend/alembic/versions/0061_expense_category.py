"""project_payments: the category of an expense (invoices and advances, IA-6b)

Revision ID: 0061_expense_category
Revises: 0060_settlement_document
Create Date: 2026-10-18 12:00:00.000000

One nullable column, `category` (MATERIALS, TOOLS, TRANSPORT, SERVICES, OTHER), only for an expense: what the owner spent the money on, so the
summary of the materials can say it by part. Every existing row stays as it is (no category); no row is touched.

Reversible: the downgrade **refuses** (rather than drops the column) while any expense has a category -- it is what the owner wrote down.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0061_expense_category"
down_revision: str | None = "0060_settlement_document"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CATEGORIES = "'MATERIALS', 'TOOLS', 'TRANSPORT', 'SERVICES', 'OTHER'"
CHECK_VALUES = f"category IS NULL OR category IN ({CATEGORIES})"
CHECK_ONLY_EXPENSE = "category IS NULL OR kind = 'EXPENSE'"


def upgrade() -> None:
    with op.batch_alter_table("project_payments") as batch:
        batch.add_column(sa.Column("category", sa.String(16), nullable=True))
        batch.create_check_constraint("ck_project_payments_category", CHECK_VALUES)
        batch.create_check_constraint("ck_project_payments_category_only_expense", CHECK_ONLY_EXPENSE)


def downgrade() -> None:
    written = op.get_bind().execute(sa.text("SELECT count(*) FROM project_payments WHERE category IS NOT NULL")).scalar_one()
    if written:
        raise RuntimeError(f"cannot downgrade: {written} expense(s) have a category; it is what the owner wrote down and is never dropped silently")
    with op.batch_alter_table("project_payments") as batch:
        batch.drop_constraint("ck_project_payments_category_only_expense", type_="check")
        batch.drop_constraint("ck_project_payments_category", type_="check")
        batch.drop_column("category")
