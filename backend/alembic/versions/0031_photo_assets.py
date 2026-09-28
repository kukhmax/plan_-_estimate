"""photo assets (Stage 14B.4)

Revision ID: 0031_photo_assets
Revises: 0030_surface_work_executions
Create Date: 2026-09-28 18:00:00.000000

See docs/STAGE_14_PHOTO_FIXATION_ARCHITECTURE.md §15.1 and
docs/STAGE_14B_MEDIA_INFRASTRUCTURE_PLAN.md §24.

Creates photo_assets -- the immutable media asset (file facts, upload status,
logical storage name and the three explicit, write-once storage keys). No
attachment/annotation/context columns (those are later sub-stages). owner_id
and project_id are RESTRICT so evidence can never vanish through a cascade.
Every row carries complete media metadata (processing precedes the PENDING
insert, 14A §8). captured_at is camera-local time WITHOUT time zone; server
timestamps are timezone-aware.

Creates an EMPTY table: no existing table is altered. Downgrade drops the
table and its two enum types only.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0031_photo_assets"
down_revision: Union[str, None] = "0030_surface_work_executions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "photo_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("PENDING", "READY", "FAILED", name="photoassetstatus"),
            nullable=False,
        ),
        sa.Column("storage_name", sa.String(40), nullable=False),
        sa.Column("storage_key_original", sa.String(255), nullable=False),
        sa.Column("storage_key_display", sa.String(255), nullable=False),
        sa.Column("storage_key_thumbnail", sa.String(255), nullable=False),
        sa.Column(
            "content_type",
            sa.Enum("image/jpeg", "image/png", "image/webp", name="photocontenttype"),
            nullable=False,
        ),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("display_byte_size", sa.BigInteger(), nullable=False),
        sa.Column("thumbnail_byte_size", sa.BigInteger(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.CHAR(64), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=False), nullable=True),
        sa.Column(
            "uploaded_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
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
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("byte_size > 0", name="ck_photo_assets_byte_size_positive"),
        sa.CheckConstraint(
            "display_byte_size > 0", name="ck_photo_assets_display_byte_size_positive"
        ),
        sa.CheckConstraint(
            "thumbnail_byte_size > 0", name="ck_photo_assets_thumbnail_byte_size_positive"
        ),
        sa.CheckConstraint(
            "width > 0 AND height > 0", name="ck_photo_assets_dimensions_positive"
        ),
        sa.CheckConstraint(
            "length(trim(storage_name)) > 0", name="ck_photo_assets_storage_name_nonempty"
        ),
        sa.CheckConstraint(
            "length(storage_key_original) > 0 AND length(storage_key_display) > 0"
            " AND length(storage_key_thumbnail) > 0",
            name="ck_photo_assets_storage_keys_nonempty",
        ),
        sa.CheckConstraint(
            "length(sha256) = 64 AND sha256 = lower(sha256)",
            name="ck_photo_assets_sha256_format",
        ),
    )
    if op.get_context().dialect.name == "postgresql":
        # Strict lowercase-hex check (PostgreSQL regex; mirrors the model's
        # ddl_if(dialect="postgresql") constraint).
        op.create_check_constraint(
            "ck_photo_assets_sha256_hex", "photo_assets", "sha256 ~ '^[0-9a-f]{64}$'"
        )
    op.create_index(
        "uq_photo_assets_storage_key_original",
        "photo_assets",
        ["storage_key_original"],
        unique=True,
    )
    op.create_index(
        "uq_photo_assets_storage_key_display",
        "photo_assets",
        ["storage_key_display"],
        unique=True,
    )
    op.create_index(
        "uq_photo_assets_storage_key_thumbnail",
        "photo_assets",
        ["storage_key_thumbnail"],
        unique=True,
    )
    op.create_index(
        "ix_photo_assets_project_status_archived",
        "photo_assets",
        ["project_id", "status", "archived_at"],
    )
    op.create_index(
        "ix_photo_assets_status_created",
        "photo_assets",
        ["status", "created_at"],
    )
    op.create_index(
        "ix_photo_assets_owner_status",
        "photo_assets",
        ["owner_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_photo_assets_owner_status", table_name="photo_assets")
    op.drop_index("ix_photo_assets_status_created", table_name="photo_assets")
    op.drop_index("ix_photo_assets_project_status_archived", table_name="photo_assets")
    op.drop_index("uq_photo_assets_storage_key_thumbnail", table_name="photo_assets")
    op.drop_index("uq_photo_assets_storage_key_display", table_name="photo_assets")
    op.drop_index("uq_photo_assets_storage_key_original", table_name="photo_assets")
    op.drop_table("photo_assets")
    if op.get_context().dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS photocontenttype")
        op.execute("DROP TYPE IF EXISTS photoassetstatus")
