"""create openings table

Revision ID: 0008_create_openings_table
Revises: 0007_add_measurement_dimensions
Create Date: 2026-09-10 11:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0008_create_openings_table"
down_revision: Union[str, None] = "0007_add_measurement_dimensions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "openings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "surface_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("surfaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "opening_type",
            sa.Enum("DOOR", "WINDOW", "OTHER", name="openingtype"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("width", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("height", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("description", sa.String(length=4096), nullable=True),
        sa.Column(
            "is_archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_openings_surface_id", "openings", ["surface_id"])
    op.create_index(
        "ix_openings_surface_archived",
        "openings",
        ["surface_id", "is_archived"],
    )


def downgrade() -> None:
    op.drop_index("ix_openings_surface_archived", table_name="openings")
    op.drop_index("ix_openings_surface_id", table_name="openings")
    op.drop_table("openings")
    op.execute("DROP TYPE IF EXISTS openingtype")
