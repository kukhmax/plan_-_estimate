"""merged walls: the parts of a merged wall (surface_parts) and the journal of what moved to it (surface_merge_moves)

Revision ID: 0066_surface_merge
Revises: 0065_access_control
Create Date: 2026-10-23 09:00:00.000000

"Объединить стены": one wall keeps the sizes of all the joined walls as parts (its area is their sum) and takes their photos and openings; the
joined walls are archived, not deleted. Two NEW tables only; no existing table or row is changed.

Reversible: the downgrade drops the two tables (a merged wall keeps its own width and height, so it stays a plain wall of the size it had;
the photos and openings that were moved stay where they are).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0066_surface_merge"
down_revision: str | None = "0065_access_control"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "surface_parts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("surface_id", sa.Uuid(), nullable=False),
        sa.Column("source_surface_id", sa.Uuid(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("width", sa.Numeric(10, 3), nullable=False),
        sa.Column("height", sa.Numeric(10, 3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["surface_id"], ["surfaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_surface_id"], ["surfaces.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_surface_parts_surface_position", "surface_parts", ["surface_id", "position"])
    op.create_index("ix_surface_parts_source_surface_id", "surface_parts", ["source_surface_id"])
    op.create_table(
        "surface_merge_moves",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("surface_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.Enum("PHOTO", "OPENING", name="mergemovekind"), nullable=False),
        sa.Column("item_id", sa.Uuid(), nullable=False),
        sa.Column("from_surface_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["surface_id"], ["surfaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["from_surface_id"], ["surfaces.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_surface_merge_moves_surface_id", "surface_merge_moves", ["surface_id"])


def downgrade() -> None:
    op.drop_index("ix_surface_merge_moves_surface_id", table_name="surface_merge_moves")
    op.drop_table("surface_merge_moves")
    op.execute("DROP TYPE IF EXISTS mergemovekind")
    op.drop_index("ix_surface_parts_source_surface_id", table_name="surface_parts")
    op.drop_index("ix_surface_parts_surface_position", table_name="surface_parts")
    op.drop_table("surface_parts")
