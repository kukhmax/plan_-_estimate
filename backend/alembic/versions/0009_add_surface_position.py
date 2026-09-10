"""add position column to surfaces

Revision ID: 0009_add_surface_position
Revises: 0008_create_openings_table
Create Date: 2026-09-10 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009_add_surface_position"
down_revision: Union[str, None] = "0008_create_openings_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "surfaces",
        sa.Column("position", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("surfaces", "position")