"""issued_documents: the journal kind of the measurements of an object "Obmiar obiektu" (V2-8c)

Revision ID: 0074_measurements_document
Revises: 0073_client_decline
Create Date: 2026-10-27 10:00:00.000000

Widens `ck_issued_documents_kind` with 'MEASUREMENTS', the number prefix OBM: every size of every room of an object (the summary, the rectangles of
the ceiling and the floor, every wall with its openings and reveals), made from the data the screens already show. Nothing else changes, no row is
touched.

Reversible: the downgrade **refuses** (rather than deletes) while a journal row of this kind exists (it is a document that may have been given to a client).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0074_measurements_document"
down_revision: str | None = "0073_client_decline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS_NEW = (
    "kind IN ('ESTIMATE', 'PHOTO_REPORT', 'TECH_CARD', 'PRODUCTION_PLAN', 'CONTRACT', 'HANDOVER_PROTOCOL', 'CONCEALED_WORKS_PROTOCOL', "
    "'FINAL_PROTOCOL', 'DECISION_PROTOCOL', 'DOWNTIME_NOTICE', 'DOWNTIME_PROTOCOL', 'SETTLEMENT', 'MEASUREMENTS')"
)
KINDS_OLD = (
    "kind IN ('ESTIMATE', 'PHOTO_REPORT', 'TECH_CARD', 'PRODUCTION_PLAN', 'CONTRACT', 'HANDOVER_PROTOCOL', 'CONCEALED_WORKS_PROTOCOL', "
    "'FINAL_PROTOCOL', 'DECISION_PROTOCOL', 'DOWNTIME_NOTICE', 'DOWNTIME_PROTOCOL', 'SETTLEMENT')"
)


def upgrade() -> None:
    with op.batch_alter_table("issued_documents") as batch:
        batch.drop_constraint("ck_issued_documents_kind", type_="check")
        batch.create_check_constraint("ck_issued_documents_kind", KINDS_NEW)


def downgrade() -> None:
    journal = op.get_bind().execute(sa.text("SELECT count(*) FROM issued_documents WHERE kind = 'MEASUREMENTS'")).scalar_one()
    if journal:
        raise RuntimeError(f"cannot downgrade: {journal} journal row(s) of the measurements exist; they are documents that may have been given to a client and are never dropped silently")
    with op.batch_alter_table("issued_documents") as batch:
        batch.drop_constraint("ck_issued_documents_kind", type_="check")
        batch.create_check_constraint("ck_issued_documents_kind", KINDS_OLD)
