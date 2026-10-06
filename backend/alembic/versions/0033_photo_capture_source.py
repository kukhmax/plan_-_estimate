"""photo capture source (Stage 14E.2)

Revision ID: 0033_photo_capture_source
Revises: 0032_photo_attachments
Create Date: 2026-10-06 12:00:00.000000

Canonical contract: docs/STAGE_14E_PHOTO_UI_CONTRACT.md §3a (owner decision D11 = A).

Adds ONE nullable VARCHAR(16) column `photo_assets.capture_source` with a CHECK
(`CAMERA` | `GALLERY`): how the client says the file entered the app. It is declared by
the client, informational and never proof; NULL = unknown (every existing row). No
default, no backfill, no index, no rewrite of existing data; no other table is touched.

Not a native enum, so the downgrade is a plain DROP CONSTRAINT + DROP COLUMN and leaves
no type behind. Reversible; downgrading loses only the informational value.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0033_photo_capture_source"
down_revision: Union[str, None] = "0032_photo_attachments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONSTRAINT = "ck_photo_assets_capture_source"


def upgrade() -> None:
    op.add_column("photo_assets", sa.Column("capture_source", sa.String(16), nullable=True))
    op.create_check_constraint(
        CONSTRAINT,
        "photo_assets",
        "capture_source IS NULL OR capture_source IN ('CAMERA', 'GALLERY')",
    )


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT, "photo_assets", type_="check")
    op.drop_column("photo_assets", "capture_source")
