"""create rooms table

Revision ID: 0005_create_rooms
Revises: 0004_add_project_client
Create Date: 2026-09-09 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005_create_rooms"
down_revision: Union[str, None] = "0004_add_project_client"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "rooms",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
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
    op.create_index("ix_rooms_project_id", "rooms", ["project_id"])
    op.create_index(
        "ix_rooms_project_archived",
        "rooms",
        ["project_id", "is_archived"],
    )


def downgrade() -> None:
    op.drop_index("ix_rooms_project_archived", table_name="rooms")
    op.drop_index("ix_rooms_project_id", table_name="rooms")
    op.drop_table("rooms")
