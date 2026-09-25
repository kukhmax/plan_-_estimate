"""estimate line occurrence identity snapshot (Stage 13E.2B)

Revision ID: 0028_estimate_occurrence_key
Revises: 0027_workflow_templates
Create Date: 2026-09-26 12:00:00.000000

(The revision id is shorter than the file name because
alembic_version.version_num is VARCHAR(32) -- same precedent as
0016_make_price_nullable.)

See docs/STAGE_13_TECHNOLOGICAL_WORKFLOWS_ARCHITECTURE.md §24.

1. add estimate_lines.occurrence_key (UUID, NULL, no foreign key -- a snapshot
   that must outlive the SurfacePlannedWork occurrence it identifies);
2. backfill it ONLY where the pairing is exact: DRAFT estimate, PLANNED_WORK,
   surface line (opening_id NULL), planned_work_id resolving to an existing
   surface_planned_works row with the same price_item_id, and that
   planned_work_id not duplicated inside the same estimate. Everything else
   (stale ids, PriceItem mismatch, reveal, MANUAL, PRICE_BOOK, FINAL,
   ACCEPTED, ambiguous duplicates) stays NULL. Nothing is inferred from
   PriceItem, surface, position or ordering;
3. create the partial unique index (estimate_id, occurrence_key) WHERE
   occurrence_key IS NOT NULL -- one line per logical occurrence per estimate.

Additive and non-destructive; downgrade drops the index and the column.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0028_estimate_occurrence_key"
down_revision: Union[str, None] = "0027_workflow_templates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX_NAME = "uq_estimate_lines_estimate_occurrence_key"

# Shared with the automated backfill test (tests/test_estimate_occurrence_identity.py).
BACKFILL_SQL = """
UPDATE estimate_lines
SET occurrence_key = (
    SELECT spw.occurrence_key
    FROM surface_planned_works AS spw
    WHERE spw.id = estimate_lines.planned_work_id
)
WHERE estimate_lines.origin = 'PLANNED_WORK'
  AND estimate_lines.opening_id IS NULL
  AND estimate_lines.planned_work_id IS NOT NULL
  AND EXISTS (
      SELECT 1 FROM estimates AS e
      WHERE e.id = estimate_lines.estimate_id AND e.status = 'DRAFT'
  )
  AND EXISTS (
      SELECT 1 FROM surface_planned_works AS spw
      WHERE spw.id = estimate_lines.planned_work_id
        AND spw.price_item_id = estimate_lines.price_item_id
  )
  AND NOT EXISTS (
      SELECT 1 FROM estimate_lines AS dup
      WHERE dup.estimate_id = estimate_lines.estimate_id
        AND dup.planned_work_id = estimate_lines.planned_work_id
        AND dup.id <> estimate_lines.id
  )
"""


def upgrade() -> None:
    op.add_column(
        "estimate_lines",
        sa.Column("occurrence_key", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.execute(sa.text(BACKFILL_SQL))
    op.create_index(
        INDEX_NAME,
        "estimate_lines",
        ["estimate_id", "occurrence_key"],
        unique=True,
        postgresql_where=sa.text("occurrence_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="estimate_lines")
    op.drop_column("estimate_lines", "occurrence_key")
