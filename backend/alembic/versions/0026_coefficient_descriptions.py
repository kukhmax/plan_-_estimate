"""add description to coefficient groups and options (Stage 12G)

Revision ID: 0026_coefficient_descriptions
Revises: 0025_estimate_line_coefficients
Create Date: 2026-09-24 12:00:00.000000

Adds a nullable, owner-editable `description` (Text) to `coefficient_groups`
and `coefficient_options`. Explanatory catalog content only: it is never a
pricing input and is not part of any EstimateLine coefficient snapshot.

No data rewrite: existing rows get NULL. The program default catalog (with
descriptions) is installed by the application's lazy bootstrap, never by
this migration (docs/stage-12-architecture.md Sec 5 / Sec 27.3).

Purely additive. No existing column/enum/table altered.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0026_coefficient_descriptions"
down_revision: Union[str, None] = "0025_estimate_line_coefficients"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "coefficient_groups",
        sa.Column("description", sa.Text(), nullable=True),
    )
    op.add_column(
        "coefficient_options",
        sa.Column("description", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("coefficient_options", "description")
    op.drop_column("coefficient_groups", "description")
