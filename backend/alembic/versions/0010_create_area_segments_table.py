"""create area_segments table

Revision ID: 0010_create_area_segments_table
Revises: 0009_add_surface_position
Create Date: 2026-09-11 08:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0010_create_area_segments_table"
down_revision: Union[str, None] = "0009_add_surface_position"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "area_segments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "room_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rooms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("plane", sa.Enum("FLOOR", "CEILING", name="areaplane"), nullable=False),
        sa.Column(
            "operation",
            sa.Enum("ADD", "SUBTRACT", name="areaoperation"),
            nullable=False,
        ),
        sa.Column("width", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("height", sa.Numeric(precision=10, scale=3), nullable=False),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("label", sa.String(length=255), nullable=True),
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
    op.create_index("ix_area_segments_room_id", "area_segments", ["room_id"])
    op.create_index(
        "ix_area_segments_room_plane_archived",
        "area_segments",
        ["room_id", "plane", "is_archived"],
    )


def downgrade() -> None:
    op.drop_index("ix_area_segments_room_plane_archived", table_name="area_segments")
    op.drop_index("ix_area_segments_room_id", table_name="area_segments")
    op.drop_table("area_segments")
    op.execute("DROP TYPE IF EXISTS areaplane")
    op.execute("DROP TYPE IF EXISTS areaoperation")
