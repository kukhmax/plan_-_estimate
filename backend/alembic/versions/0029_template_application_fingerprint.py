"""template application request fingerprint (Stage 13E.3)

Revision ID: 0029_application_fingerprint
Revises: 0028_estimate_occurrence_key
Create Date: 2026-09-26 18:00:00.000000

(Revision id shorter than the file name: alembic_version.version_num is
VARCHAR(32).)

Adds surface_work_plan_template_applications.request_fingerprint -- a
server-computed SHA-256 (hex, 64 chars) of the semantic apply-template
request. The existing columns (template, mode, steps_applied) cannot tell an
identical retry from an application_id reused with a different optional-step
selection, template version or REPLACE composition; the fingerprint can.
Nullable: rows written through the Stage 13C WorkPlan PUT intent have none.
Additive; downgrade drops the column.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0029_application_fingerprint"
down_revision: Union[str, None] = "0028_estimate_occurrence_key"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "surface_work_plan_template_applications",
        sa.Column("request_fingerprint", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("surface_work_plan_template_applications", "request_fingerprint")
