"""create projects table

Revision ID: 0003_create_projects
Revises: 0002_create_clients
Create Date: 2026-09-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003_create_projects"
down_revision: Union[str, None] = "0002_create_clients"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("address", sa.String(length=512), nullable=False),
        sa.Column("city", sa.String(length=255), nullable=False),
        sa.Column("postal_code", sa.String(length=20), nullable=False),
        sa.Column("description", sa.String(length=4096), nullable=True),
        sa.Column(
            "status",
            sa.Enum("PLANNING", "IN_PROGRESS", "COMPLETED", name="projectstatus"),
            nullable=False,
            server_default="PLANNING",
        ),
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
    op.create_index("ix_projects_owner_id", "projects", ["owner_id"])
    op.create_index(
        "ix_projects_owner_archived",
        "projects",
        ["owner_id", "is_archived"],
    )


def downgrade() -> None:
    op.drop_index("ix_projects_owner_archived", table_name="projects")
    op.drop_index("ix_projects_owner_id", table_name="projects")
    op.drop_table("projects")
    op.execute("DROP TYPE IF EXISTS projectstatus")
