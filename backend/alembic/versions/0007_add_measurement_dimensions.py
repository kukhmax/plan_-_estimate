"""add measurement dimensions to rooms and surfaces

Revision ID: 0007_add_measurement_dimensions
Revises: 0006_create_surfaces
Create Date: 2026-09-10 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_add_measurement_dimensions"
down_revision: Union[str, None] = "0006_create_surfaces"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("rooms", sa.Column("length", sa.Numeric(precision=10, scale=3), nullable=True))
    op.add_column("rooms", sa.Column("width", sa.Numeric(precision=10, scale=3), nullable=True))
    op.add_column("rooms", sa.Column("height", sa.Numeric(precision=10, scale=3), nullable=True))
    op.add_column("surfaces", sa.Column("width", sa.Numeric(precision=10, scale=3), nullable=True))
    op.add_column("surfaces", sa.Column("height", sa.Numeric(precision=10, scale=3), nullable=True))


def downgrade() -> None:
    op.drop_column("surfaces", "height")
    op.drop_column("surfaces", "width")
    op.drop_column("rooms", "height")
    op.drop_column("rooms", "width")
    op.drop_column("rooms", "length")
