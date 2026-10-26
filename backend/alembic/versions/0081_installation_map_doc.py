"""issued_documents: the journal kind of the map of hidden utilities "Mapa instalacji ukrytych" (V2-12a)

Revision ID: 0081_installation_map_doc
Revises: 0080_photo_utilities
Create Date: 2026-11-01 11:00:00.000000

Widens `ck_issued_documents_kind` with 'INSTALLATION_MAP', the number prefix MAP: the photos of the object whose markers name a hidden utility, with the markers in the colour of
their type and what lies where. Nothing else changes, no row is touched.

Reversible: the downgrade **refuses** (rather than deletes) while a journal row of this kind exists (it is a document that may have been given to a client).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0081_installation_map_doc"
down_revision: str | None = "0080_photo_utilities"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS_NEW = (
    "kind IN ('ESTIMATE', 'PHOTO_REPORT', 'TECH_CARD', 'PRODUCTION_PLAN', 'CONTRACT', 'HANDOVER_PROTOCOL', 'CONCEALED_WORKS_PROTOCOL', "
    "'FINAL_PROTOCOL', 'DECISION_PROTOCOL', 'DOWNTIME_NOTICE', 'DOWNTIME_PROTOCOL', 'SETTLEMENT', 'MEASUREMENTS', 'PAYMENT_SCHEDULE', 'INSTALLATION_MAP')"
)
KINDS_OLD = (
    "kind IN ('ESTIMATE', 'PHOTO_REPORT', 'TECH_CARD', 'PRODUCTION_PLAN', 'CONTRACT', 'HANDOVER_PROTOCOL', 'CONCEALED_WORKS_PROTOCOL', "
    "'FINAL_PROTOCOL', 'DECISION_PROTOCOL', 'DOWNTIME_NOTICE', 'DOWNTIME_PROTOCOL', 'SETTLEMENT', 'MEASUREMENTS', 'PAYMENT_SCHEDULE')"
)


def upgrade() -> None:
    with op.batch_alter_table("issued_documents") as batch:
        batch.drop_constraint("ck_issued_documents_kind", type_="check")
        batch.create_check_constraint("ck_issued_documents_kind", KINDS_NEW)


def downgrade() -> None:
    journal = op.get_bind().execute(sa.text("SELECT count(*) FROM issued_documents WHERE kind = 'INSTALLATION_MAP'")).scalar_one()
    if journal:
        raise RuntimeError(f"cannot downgrade: {journal} journal row(s) of the map of installations exist; they are documents that may have been given to a client and are never dropped silently")
    with op.batch_alter_table("issued_documents") as batch:
        batch.drop_constraint("ck_issued_documents_kind", type_="check")
        batch.create_check_constraint("ck_issued_documents_kind", KINDS_OLD)
