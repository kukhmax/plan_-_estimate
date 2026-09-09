"""add optional client association to projects

Revision ID: 0004_add_project_client
Revises: 0003_create_projects
Create Date: 2026-09-09 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004_add_project_client"
down_revision: Union[str, None] = "0003_create_projects"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("client_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_projects_client_id_clients",
        "projects",
        "clients",
        ["client_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_projects_client_id", "projects", ["client_id"])


def downgrade() -> None:
    op.drop_index("ix_projects_client_id", table_name="projects")
    op.drop_constraint(
        "fk_projects_client_id_clients",
        "projects",
        type_="foreignkey",
    )
    op.drop_column("projects", "client_id")
