"""issued_documents: the journal kind of the acceptance protocol (Stage 16H.2)

Revision ID: 0051_final_protocol_kind
Revises: 0050_acceptance_protocols
Create Date: 2026-10-10 23:00:00.000000

Canonical design: docs/STAGE_16_CONTRACTS_PROTOCOLS_PLAN_RU.md (16H).

Widens `ck_issued_documents_kind` with 'FINAL_PROTOCOL', the number prefix ODBIOR. Nothing else changes: the protocol's own table came
with 0050.

Reversible: the downgrade **refuses** (rather than deletes) while a journal row of this kind exists.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0051_final_protocol_kind"
down_revision: str | None = "0050_acceptance_protocols"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

KINDS_NEW = (
    "kind IN ('ESTIMATE', 'PHOTO_REPORT', 'TECH_CARD', 'PRODUCTION_PLAN', 'CONTRACT', 'HANDOVER_PROTOCOL', 'CONCEALED_WORKS_PROTOCOL', 'FINAL_PROTOCOL')"
)
KINDS_OLD = "kind IN ('ESTIMATE', 'PHOTO_REPORT', 'TECH_CARD', 'PRODUCTION_PLAN', 'CONTRACT', 'HANDOVER_PROTOCOL', 'CONCEALED_WORKS_PROTOCOL')"


def upgrade() -> None:
    with op.batch_alter_table("issued_documents") as batch:
        batch.drop_constraint("ck_issued_documents_kind", type_="check")
        batch.create_check_constraint("ck_issued_documents_kind", KINDS_NEW)


def downgrade() -> None:
    journal = op.get_bind().execute(sa.text("SELECT count(*) FROM issued_documents WHERE kind = 'FINAL_PROTOCOL'")).scalar_one()
    if journal:
        raise RuntimeError(f"cannot downgrade: {journal} journal row(s) of an acceptance protocol exist; they are evidence and are never dropped silently")
    with op.batch_alter_table("issued_documents") as batch:
        batch.drop_constraint("ck_issued_documents_kind", type_="check")
        batch.create_check_constraint("ck_issued_documents_kind", KINDS_OLD)
