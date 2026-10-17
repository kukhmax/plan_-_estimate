"""invoices, money from the client and expenses of an object; the agreed amount (invoices and advances, IA-1)

Revision ID: 0058_project_payments
Revises: 0057_purge_ledger
Create Date: 2026-10-17 15:00:00.000000

Two new tables, nothing else is touched: `project_payments` (an invoice issued to the client, an advance or a payment taken from the client,
an expense on materials: one row each) and `project_finance` (the agreed amount of an object, at most one row per object).
Reversible: the downgrade **refuses** while any row exists -- these are the owner's money records and are never dropped silently.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0058_project_payments"
down_revision: str | None = "0057_purge_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_payments",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Uuid, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("number", sa.String(64), nullable=True),
        sa.Column("amount_gross", sa.Numeric(12, 2), nullable=False),
        sa.Column("amount_net", sa.Numeric(12, 2), nullable=True),
        sa.Column("vat_rate", sa.Numeric(5, 2), nullable=True),
        sa.Column("occurred_on", sa.Date, nullable=False),
        sa.Column("due_on", sa.Date, nullable=True),
        sa.Column("settles_id", sa.Uuid, sa.ForeignKey("project_payments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("counterparty", sa.String(255), nullable=True),
        sa.Column("document_kind", sa.String(8), nullable=True),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("is_archived", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('INVOICE', 'ADVANCE', 'PAYMENT', 'EXPENSE')", name="ck_project_payments_kind"),
        sa.CheckConstraint("amount_gross > 0", name="ck_project_payments_amount_positive"),
        sa.CheckConstraint("amount_net IS NULL OR amount_net >= 0", name="ck_project_payments_net_not_negative"),
        sa.CheckConstraint("vat_rate IS NULL OR (vat_rate >= 0 AND vat_rate <= 100)", name="ck_project_payments_vat_range"),
        sa.CheckConstraint("length(trim(title)) > 0", name="ck_project_payments_title_not_blank"),
        sa.CheckConstraint("document_kind IS NULL OR document_kind IN ('RECEIPT', 'INVOICE')", name="ck_project_payments_document_kind"),
        sa.CheckConstraint("document_kind IS NULL OR kind = 'EXPENSE'", name="ck_project_payments_document_kind_only_expense"),
        sa.CheckConstraint("counterparty IS NULL OR kind = 'EXPENSE'", name="ck_project_payments_counterparty_only_expense"),
        sa.CheckConstraint("due_on IS NULL OR kind = 'INVOICE'", name="ck_project_payments_due_only_invoice"),
        sa.CheckConstraint("settles_id IS NULL OR kind IN ('ADVANCE', 'PAYMENT')", name="ck_project_payments_settles_only_money_in"),
        sa.CheckConstraint("settles_id IS NULL OR settles_id <> id", name="ck_project_payments_settles_not_self"),
    )
    op.create_index("ix_project_payments_project_kind", "project_payments", ["project_id", "kind", "occurred_on"])
    op.create_index("ix_project_payments_settles", "project_payments", ["settles_id"])

    op.create_table(
        "project_finance",
        sa.Column("project_id", sa.Uuid, sa.ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("owner_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("agreed_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="PLN"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("agreed_amount IS NULL OR agreed_amount > 0", name="ck_project_finance_agreed_positive"),
    )


def downgrade() -> None:
    bind = op.get_bind()
    payments = bind.execute(sa.text("SELECT count(*) FROM project_payments")).scalar_one()
    finance = bind.execute(sa.text("SELECT count(*) FROM project_finance")).scalar_one()
    if payments or finance:
        raise RuntimeError(
            f"cannot downgrade: {payments} payment record(s) and {finance} agreed amount(s) exist; they are the owner's money records and are never dropped silently"
        )
    op.drop_table("project_finance")
    op.drop_index("ix_project_payments_settles", table_name="project_payments")
    op.drop_index("ix_project_payments_project_kind", table_name="project_payments")
    op.drop_table("project_payments")
