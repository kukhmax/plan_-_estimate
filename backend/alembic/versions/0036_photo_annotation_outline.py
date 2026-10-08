"""photo annotation outline: a contour drawn around a defect (Stage 14G.4)

Revision ID: 0036_photo_annotation_outline
Revises: 0035_photo_annotations
Create Date: 2026-10-08 18:00:00.000000

Canonical design: docs/STAGE_14G_POINT_ANNOTATIONS_PLAN_RU.md section 6.

Adds the nullable JSON column photo_annotations.outline: one freehand contour per marker, a list of
[x, y] points in the same 0..1 fractions of the display image as the marker itself (3..120 points,
checked by the service). Existing rows keep NULL (no contour); nothing else changes. Reversible: the
downgrade drops the column and nothing else (only contours are lost, markers and photos stay).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0036_photo_annotation_outline"
down_revision: str | None = "0035_photo_annotations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "photo_annotations"
COLUMN = "outline"


def upgrade() -> None:
    op.add_column(TABLE, sa.Column(COLUMN, sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column(TABLE, COLUMN)
