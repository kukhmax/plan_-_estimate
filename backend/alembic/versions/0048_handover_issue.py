"""handover_protocols: the frozen snapshot of an issued protocol and the HANDOVER_PROTOCOL kind of the journal (Stage 16F.2)

Revision ID: 0048_handover_issue
Revises: 0047_handover_protocols
Create Date: 2026-10-10 20:00:00.000000

Canonical design: docs/STAGE_16_CONTRACTS_PROTOCOLS_PLAN_RU.md (16F).

Adds to handover_protocols the columns of an issued protocol: `issued_at`, the `snapshot` of what was found (JSON), `document_html`
(the exact page that was issued, so the same document can be made again) and the contract it was made under (`contract_id`,
`contract_version`, plain values). A CHECK makes the freeze a rule of the database: an ISSUED protocol always has its time, its
snapshot and its page. Widens `ck_issued_documents_kind` with 'HANDOVER_PROTOCOL'. No data changes.

Reversible: the downgrade **refuses** (rather than deletes) while an issued protocol or a HANDOVER_PROTOCOL journal row exists.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0048_handover_issue"
down_revision: str | None = "0047_handover_protocols"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FROZEN = "status <> 'ISSUED' OR (issued_at IS NOT NULL AND snapshot IS NOT NULL AND document_html IS NOT NULL)"
KINDS_NEW = "kind IN ('ESTIMATE', 'PHOTO_REPORT', 'TECH_CARD', 'PRODUCTION_PLAN', 'CONTRACT', 'HANDOVER_PROTOCOL')"
KINDS_OLD = "kind IN ('ESTIMATE', 'PHOTO_REPORT', 'TECH_CARD', 'PRODUCTION_PLAN', 'CONTRACT')"


def upgrade() -> None:
    with op.batch_alter_table("handover_protocols") as batch:
        batch.add_column(sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("snapshot", postgresql.JSONB().with_variant(sa.JSON(), "sqlite"), nullable=True))
        batch.add_column(sa.Column("document_html", sa.Text, nullable=True))
        batch.add_column(sa.Column("contract_id", sa.Uuid, nullable=True))
        batch.add_column(sa.Column("contract_version", sa.Integer, nullable=True))
        batch.create_check_constraint("ck_handover_protocols_frozen_when_issued", FROZEN)
    with op.batch_alter_table("issued_documents") as batch:
        batch.drop_constraint("ck_issued_documents_kind", type_="check")
        batch.create_check_constraint("ck_issued_documents_kind", KINDS_NEW)


def downgrade() -> None:
    bind = op.get_bind()
    issued = bind.execute(sa.text("SELECT count(*) FROM handover_protocols WHERE status = 'ISSUED'")).scalar_one()
    journal = bind.execute(sa.text("SELECT count(*) FROM issued_documents WHERE kind = 'HANDOVER_PROTOCOL'")).scalar_one()
    if issued or journal:
        raise RuntimeError(
            f"cannot downgrade: {issued} issued protocol(s) and {journal} protocol journal row(s) exist; remove them first"
        )
    with op.batch_alter_table("issued_documents") as batch:
        batch.drop_constraint("ck_issued_documents_kind", type_="check")
        batch.create_check_constraint("ck_issued_documents_kind", KINDS_OLD)
    with op.batch_alter_table("handover_protocols") as batch:
        batch.drop_constraint("ck_handover_protocols_frozen_when_issued", type_="check")
        batch.drop_column("contract_version")
        batch.drop_column("contract_id")
        batch.drop_column("document_html")
        batch.drop_column("snapshot")
        batch.drop_column("issued_at")
