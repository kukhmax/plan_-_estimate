"""issued documents: the technological card is a kind of the journal (Stage 16C)

Revision ID: 0041_issued_documents_tech_card
Revises: 0040_project_representatives
Create Date: 2026-10-09 18:00:00.000000

Canonical design: docs/STAGE_16_CONTRACTS_PROTOCOLS_PLAN_RU.md (16C).

Widens the check on `issued_documents.kind` from ('ESTIMATE', 'PHOTO_REPORT') to also allow 'TECH_CARD'. No data changes.
Reversible: the downgrade narrows the check again and **refuses** (rather than deletes) while a TECH_CARD row exists, so the
journal is never silently lost.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0041_issued_documents_tech_card"
down_revision: str | None = "0040_project_representatives"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "issued_documents"
CHECK = "ck_issued_documents_kind"


def upgrade() -> None:
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_constraint(CHECK, type_="check")
        batch.create_check_constraint(CHECK, "kind IN ('ESTIMATE', 'PHOTO_REPORT', 'TECH_CARD')")


def downgrade() -> None:
    bind = op.get_bind()
    count = bind.execute(sa.text(f"SELECT count(*) FROM {TABLE} WHERE kind = 'TECH_CARD'")).scalar_one()
    if count:
        raise RuntimeError(f"cannot downgrade: {count} technological card(s) are in the journal; remove them first")
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_constraint(CHECK, type_="check")
        batch.create_check_constraint(CHECK, "kind IN ('ESTIMATE', 'PHOTO_REPORT')")
