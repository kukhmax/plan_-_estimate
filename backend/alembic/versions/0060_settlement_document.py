"""issued_documents: the journal kind of the statement of settlements "Rozliczenie" (invoices and advances, IA-6a)

Revision ID: 0060_settlement_document
Revises: 0059_payment_photos
Create Date: 2026-10-18 10:00:00.000000

Widens `ck_issued_documents_kind` with 'SETTLEMENT', the number prefix ROZL: the statement of what was invoiced to the client and what the
client paid, made from the settlement records of the object (never from the expenses on materials, which are the owner's own). Nothing else
changes, no row is touched.

Reversible: the downgrade **refuses** (rather than deletes) while a journal row of this kind exists (it is a document given to a client).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0060_settlement_document"
down_revision: str | None = "0059_payment_photos"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS_NEW = (
    "kind IN ('ESTIMATE', 'PHOTO_REPORT', 'TECH_CARD', 'PRODUCTION_PLAN', 'CONTRACT', 'HANDOVER_PROTOCOL', 'CONCEALED_WORKS_PROTOCOL', "
    "'FINAL_PROTOCOL', 'DECISION_PROTOCOL', 'DOWNTIME_NOTICE', 'DOWNTIME_PROTOCOL', 'SETTLEMENT')"
)
KINDS_OLD = (
    "kind IN ('ESTIMATE', 'PHOTO_REPORT', 'TECH_CARD', 'PRODUCTION_PLAN', 'CONTRACT', 'HANDOVER_PROTOCOL', 'CONCEALED_WORKS_PROTOCOL', "
    "'FINAL_PROTOCOL', 'DECISION_PROTOCOL', 'DOWNTIME_NOTICE', 'DOWNTIME_PROTOCOL')"
)


def upgrade() -> None:
    with op.batch_alter_table("issued_documents") as batch:
        batch.drop_constraint("ck_issued_documents_kind", type_="check")
        batch.create_check_constraint("ck_issued_documents_kind", KINDS_NEW)


def downgrade() -> None:
    journal = op.get_bind().execute(sa.text("SELECT count(*) FROM issued_documents WHERE kind = 'SETTLEMENT'")).scalar_one()
    if journal:
        raise RuntimeError(f"cannot downgrade: {journal} journal row(s) of a statement of settlements exist; they are documents given to a client and are never dropped silently")
    with op.batch_alter_table("issued_documents") as batch:
        batch.drop_constraint("ck_issued_documents_kind", type_="check")
        batch.create_check_constraint("ck_issued_documents_kind", KINDS_OLD)
