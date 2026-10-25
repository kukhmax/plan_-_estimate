"""issued_documents: the journal kind of the payment schedule "Harmonogram płatności" (V2-9a)

Revision ID: 0076_payment_schedule_doc
Revises: 0075_payment_schedule
Create Date: 2026-10-28 14:00:00.000000

Widens `ck_issued_documents_kind` with 'PAYMENT_SCHEDULE', the number prefix HPL: the stages in which the client pays, with the amount, the day and the
state of each, made from the schedule the screen "Etapy" already shows. Nothing else changes, no row is touched.

Reversible: the downgrade **refuses** (rather than deletes) while a journal row of this kind exists (it is a document that may have been given to a client).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0076_payment_schedule_doc"
down_revision: str | None = "0075_payment_schedule"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS_NEW = (
    "kind IN ('ESTIMATE', 'PHOTO_REPORT', 'TECH_CARD', 'PRODUCTION_PLAN', 'CONTRACT', 'HANDOVER_PROTOCOL', 'CONCEALED_WORKS_PROTOCOL', "
    "'FINAL_PROTOCOL', 'DECISION_PROTOCOL', 'DOWNTIME_NOTICE', 'DOWNTIME_PROTOCOL', 'SETTLEMENT', 'MEASUREMENTS', 'PAYMENT_SCHEDULE')"
)
KINDS_OLD = (
    "kind IN ('ESTIMATE', 'PHOTO_REPORT', 'TECH_CARD', 'PRODUCTION_PLAN', 'CONTRACT', 'HANDOVER_PROTOCOL', 'CONCEALED_WORKS_PROTOCOL', "
    "'FINAL_PROTOCOL', 'DECISION_PROTOCOL', 'DOWNTIME_NOTICE', 'DOWNTIME_PROTOCOL', 'SETTLEMENT', 'MEASUREMENTS')"
)


def upgrade() -> None:
    with op.batch_alter_table("issued_documents") as batch:
        batch.drop_constraint("ck_issued_documents_kind", type_="check")
        batch.create_check_constraint("ck_issued_documents_kind", KINDS_NEW)


def downgrade() -> None:
    journal = op.get_bind().execute(sa.text("SELECT count(*) FROM issued_documents WHERE kind = 'PAYMENT_SCHEDULE'")).scalar_one()
    if journal:
        raise RuntimeError(f"cannot downgrade: {journal} journal row(s) of the payment schedule exist; they are documents that may have been given to a client and are never dropped silently")
    with op.batch_alter_table("issued_documents") as batch:
        batch.drop_constraint("ck_issued_documents_kind", type_="check")
        batch.create_check_constraint("ck_issued_documents_kind", KINDS_OLD)
