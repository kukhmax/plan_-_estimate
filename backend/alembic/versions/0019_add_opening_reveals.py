"""add opening reveal columns

Revision ID: 0019_add_opening_reveals
Revises: 0018_canonical_plane_surfaces
Create Date: 2026-09-16 23:30:00.000000

Stage 5F: adds optional reveal (ościeże) configuration to the openings table.
Six new columns: reveal_enabled (default false), reveal_depth (nullable meters),
reveal_left/right/top/bottom (side selection, defaults match the contract:
left=true, right=true, top=true, bottom=false).

All existing rows default to reveals disabled; no data migration needed.
Opening deduction area and wall net area are unchanged by this migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0019_add_opening_reveals"
down_revision: Union[str, None] = "0018_canonical_plane_surfaces"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "openings",
        sa.Column("reveal_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column(
        "openings",
        sa.Column("reveal_depth", sa.Numeric(precision=10, scale=3), nullable=True),
    )
    op.add_column(
        "openings",
        sa.Column("reveal_left", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "openings",
        sa.Column("reveal_right", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "openings",
        sa.Column("reveal_top", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column(
        "openings",
        sa.Column("reveal_bottom", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("openings", "reveal_bottom")
    op.drop_column("openings", "reveal_top")
    op.drop_column("openings", "reveal_right")
    op.drop_column("openings", "reveal_left")
    op.drop_column("openings", "reveal_depth")
    op.drop_column("openings", "reveal_enabled")
