"""issued documents: the production plan is a kind of the journal (Stage 16D.2)

Revision ID: 0043_issued_docs_plan
Revises: 0042_adjacent_works
Create Date: 2026-10-09 21:00:00.000000

Canonical design: docs/STAGE_16_CONTRACTS_PROTOCOLS_PLAN_RU.md (16D).

Widens the check on `issued_documents.kind` from ('ESTIMATE', 'PHOTO_REPORT', 'TECH_CARD') to also allow 'PRODUCTION_PLAN'. No data
changes. Reversible: the downgrade narrows the check again and **refuses** (rather than deletes) while a PRODUCTION_PLAN row
exists, so the journal is never silently lost.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0043_issued_docs_plan"
down_revision: str | None = "0042_adjacent_works"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "issued_documents"
CHECK = "ck_issued_documents_kind"


def upgrade() -> None:
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_constraint(CHECK, type_="check")
        batch.create_check_constraint(CHECK, "kind IN ('ESTIMATE', 'PHOTO_REPORT', 'TECH_CARD', 'PRODUCTION_PLAN')")


def downgrade() -> None:
    bind = op.get_bind()
    count = bind.execute(sa.text(f"SELECT count(*) FROM {TABLE} WHERE kind = 'PRODUCTION_PLAN'")).scalar_one()
    if count:
        raise RuntimeError(f"cannot downgrade: {count} production plan(s) are in the journal; remove them first")
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_constraint(CHECK, type_="check")
        batch.create_check_constraint(CHECK, "kind IN ('ESTIMATE', 'PHOTO_REPORT', 'TECH_CARD')")
