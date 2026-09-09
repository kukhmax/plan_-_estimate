"""create surfaces table

Revision ID: 0006_create_surfaces
Revises: 0005_create_rooms
Create Date: 2026-09-09 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0006_create_surfaces"
down_revision: Union[str, None] = "0005_create_rooms"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "surfaces",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "room_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("rooms.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "surface_type",
            sa.Enum("WALL", "CEILING", "FLOOR", "OTHER", name="surfacetype"),
            nullable=False,
        ),
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
    op.create_index("ix_surfaces_room_id", "surfaces", ["room_id"])
    op.create_index(
        "ix_surfaces_room_archived",
        "surfaces",
        ["room_id", "is_archived"],
    )


def downgrade() -> None:
    op.drop_index("ix_surfaces_room_archived", table_name="surfaces")
    op.drop_index("ix_surfaces_room_id", table_name="surfaces")
    op.drop_table("surfaces")
    op.execute("DROP TYPE IF EXISTS surfacetype")
