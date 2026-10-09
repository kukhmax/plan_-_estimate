"""contracts: the frozen snapshot of an issued contract and the CONTRACT kind of the journal (Stage 16E.2)

Revision ID: 0045_contract_issue
Revises: 0044_contracts
Create Date: 2026-10-10 10:00:00.000000

Canonical design: docs/STAGE_16_CONTRACTS_PROTOCOLS_PLAN_RU.md (16E).

Adds to contracts the columns of an issued contract: `issued_at`, the `snapshot` of its conditions (JSON), `document_html` (the
exact page that was issued, so the same document can be made again) and the estimate it priced (`estimate_id`,
`estimate_version`, plain values: the contract keeps the version even if the estimate is later archived). A CHECK makes the
freeze a rule of the database: an ISSUED or SIGNED contract always has its time, its snapshot and its page. Widens
`ck_issued_documents_kind` with 'CONTRACT'. No data changes.

Reversible: the downgrade **refuses** (rather than deletes) while an issued / signed contract or a CONTRACT journal row exists.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0045_contract_issue"
down_revision: str | None = "0044_contracts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FROZEN = "status NOT IN ('ISSUED', 'SIGNED') OR (issued_at IS NOT NULL AND snapshot IS NOT NULL AND document_html IS NOT NULL)"
KINDS_NEW = "kind IN ('ESTIMATE', 'PHOTO_REPORT', 'TECH_CARD', 'PRODUCTION_PLAN', 'CONTRACT')"
KINDS_OLD = "kind IN ('ESTIMATE', 'PHOTO_REPORT', 'TECH_CARD', 'PRODUCTION_PLAN')"


def upgrade() -> None:
    with op.batch_alter_table("contracts") as batch:
        batch.add_column(sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("snapshot", postgresql.JSONB().with_variant(sa.JSON(), "sqlite"), nullable=True))
        batch.add_column(sa.Column("document_html", sa.Text, nullable=True))
        batch.add_column(sa.Column("estimate_id", postgresql.UUID(as_uuid=True), nullable=True))
        batch.add_column(sa.Column("estimate_version", sa.Integer, nullable=True))
        batch.create_check_constraint("ck_contracts_frozen_when_issued", FROZEN)
    with op.batch_alter_table("issued_documents") as batch:
        batch.drop_constraint("ck_issued_documents_kind", type_="check")
        batch.create_check_constraint("ck_issued_documents_kind", KINDS_NEW)


def downgrade() -> None:
    bind = op.get_bind()
    issued = bind.execute(sa.text("SELECT count(*) FROM contracts WHERE status IN ('ISSUED', 'SIGNED')")).scalar_one()
    journal = bind.execute(sa.text("SELECT count(*) FROM issued_documents WHERE kind = 'CONTRACT'")).scalar_one()
    if issued or journal:
        raise RuntimeError(
            f"cannot downgrade: {issued} issued contract(s) and {journal} contract journal row(s) exist; remove them first"
        )
    with op.batch_alter_table("issued_documents") as batch:
        batch.drop_constraint("ck_issued_documents_kind", type_="check")
        batch.create_check_constraint("ck_issued_documents_kind", KINDS_OLD)
    with op.batch_alter_table("contracts") as batch:
        batch.drop_constraint("ck_contracts_frozen_when_issued", type_="check")
        batch.drop_column("estimate_version")
        batch.drop_column("estimate_id")
        batch.drop_column("document_html")
        batch.drop_column("snapshot")
        batch.drop_column("issued_at")
