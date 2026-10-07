"""finding lineage (Stage 14F.1)

Revision ID: 0034_finding_lineage
Revises: 0033_photo_capture_source
Create Date: 2026-10-07 18:00:00.000000

Canonical design: docs/STAGE_14_PHOTO_FIXATION_ARCHITECTURE.md §6.3 / §15.5 (owner decision D14-26 = A).

Adds `inspection_findings.lineage_id` (UUID, NOT NULL, indexed): the durable identity of "the same
finding" across re-confirmations. Reconciliation (Stage 6) creates a NEW finding row when a resolved
finding is confirmed again; that row now reuses the lineage of the earlier one, so photo evidence
captured on the earlier row stays visible on the re-confirmed finding without reviving finding UUIDs
(Stage 7 / 11 signatures hash finding UUIDs and are untouched).

Steps: add the column NULLable -> deterministic backfill -> NOT NULL -> index.
Backfill: one new UUID per (inspection_id, question_id, finding_key) group, shared by every row of the
group (a NULL question_id is a value like any other, matching the reconciliation identity). No finding
UUID, flag, timestamp or other column changes. Reversible: the downgrade drops the index and the
column and nothing else.
"""
import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0034_finding_lineage"
down_revision: Union[str, None] = "0033_photo_capture_source"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "inspection_findings"
INDEX = "ix_inspection_findings_lineage_id"
_BACKFILL_BATCH = 500


def _backfill_lineage() -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, inspection_id, question_id, finding_key FROM inspection_findings "
            "WHERE lineage_id IS NULL ORDER BY created_at, id"
        ).columns(
            sa.column("id", sa.Uuid()),
            sa.column("inspection_id", sa.Uuid()),
            sa.column("question_id", sa.Uuid()),
            sa.column("finding_key", sa.String()),
        )
    ).all()
    lineage_of: dict[tuple, uuid.UUID] = {}
    assignments: list[dict] = []
    for row_id, inspection_id, question_id, finding_key in rows:
        # a NULL question_id is a value like any other (None is hashable and equal to itself)
        group = (inspection_id, question_id, finding_key)
        assignments.append({"lineage": lineage_of.setdefault(group, uuid.uuid4()), "id": row_id})
    update = sa.text("UPDATE inspection_findings SET lineage_id = :lineage WHERE id = :id").bindparams(
        sa.bindparam("lineage", type_=sa.Uuid()),
        sa.bindparam("id", type_=sa.Uuid()),
    )
    for start in range(0, len(assignments), _BACKFILL_BATCH):
        bind.execute(update, assignments[start : start + _BACKFILL_BATCH])
    remaining = bind.execute(sa.text("SELECT count(*) FROM inspection_findings WHERE lineage_id IS NULL")).scalar_one()
    if remaining:
        raise RuntimeError(f"lineage_id backfill left {remaining} inspection_findings rows NULL")


def upgrade() -> None:
    op.add_column(TABLE, sa.Column("lineage_id", sa.Uuid(), nullable=True))
    _backfill_lineage()
    with op.batch_alter_table(TABLE) as batch:
        batch.alter_column("lineage_id", existing_type=sa.Uuid(), nullable=False)
    op.create_index(INDEX, TABLE, ["lineage_id"])


def downgrade() -> None:
    op.drop_index(INDEX, table_name=TABLE)
    with op.batch_alter_table(TABLE) as batch:
        batch.drop_column("lineage_id")
