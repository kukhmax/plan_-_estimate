"""photo annotations: point markers on photo attachments (Stage 14G.1)

Revision ID: 0035_photo_annotations
Revises: 0034_finding_lineage
Create Date: 2026-10-08 12:00:00.000000

Canonical design: docs/STAGE_14_PHOTO_FIXATION_ARCHITECTURE.md §6.4 / §15.4 and
docs/STAGE_14G_POINT_ANNOTATIONS_PLAN_RU.md.

Creates the EMPTY table photo_annotations (a point marker = normalized x / y of the display image,
optional short label, display position) and its enum type. No existing table is altered and no data
moves. attachment_id is CASCADE: a marker means nothing without its attachment (attachments are
archived through the API, never deleted). Reversible: the downgrade drops the index, the table and
the enum type and nothing else.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0035_photo_annotations"
down_revision: str | None = "0034_finding_lineage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "photo_annotations"
INDEX = "ix_photo_annotations_attachment_position"


def upgrade() -> None:
    uuid_type = postgresql.UUID(as_uuid=True)
    op.create_table(
        TABLE,
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column(
            "attachment_id",
            uuid_type,
            sa.ForeignKey("photo_attachments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.Enum("POINT", name="photoannotationkind"), nullable=False),
        sa.Column("x", sa.Numeric(7, 6), nullable=False),
        sa.Column("y", sa.Numeric(7, 6), nullable=False),
        sa.Column("label", sa.String(40), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("x >= 0 AND x <= 1", name="ck_photo_annotations_x_range"),
        sa.CheckConstraint("y >= 0 AND y <= 1", name="ck_photo_annotations_y_range"),
        sa.CheckConstraint("position >= 0", name="ck_photo_annotations_position_nonneg"),
    )
    op.create_index(INDEX, TABLE, ["attachment_id", "position"])


def downgrade() -> None:
    op.drop_index(INDEX, table_name=TABLE)
    op.drop_table(TABLE)
    if op.get_context().dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS photoannotationkind")
