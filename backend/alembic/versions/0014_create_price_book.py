"""create price book tables

Revision ID: 0014_create_price_book
Revises: 0013_create_communication_engine
Create Date: 2026-09-13 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0014_create_price_book"
down_revision: Union[str, None] = "0013_create_communication_engine"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "price_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.String(length=120), nullable=False),
        sa.Column("name_key", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column(
            "category",
            sa.Enum(
                "PREPARATION",
                "SKIM_COAT",
                "PLASTER",
                "DRYWALL",
                "PAINTING",
                "GLASS_FIBER",
                "MICROCEMENT",
                "DECORATIVE",
                "REVEAL",
                "MATERIAL",
                "OTHER",
                name="pricecategory",
            ),
            nullable=False,
        ),
        sa.Column(
            "unit",
            sa.Enum("M2", "LM", "PCS", "HOUR", "DAY", "FLAT", name="priceunit"),
            nullable=False,
        ),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default=sa.text("'PLN'"),
        ),
        sa.Column(
            "price_scope",
            sa.Enum("LABOR", "MATERIAL", "LABOR_AND_MATERIAL", name="pricescope"),
            nullable=False,
            server_default=sa.text("'LABOR'"),
        ),
        sa.Column(
            "quality_level",
            # The qualitylevel type is owned by revision 0011; do not re-create it.
            postgresql.ENUM(
                "S1",
                "S2",
                "S3",
                "S4",
                "Q1",
                "Q2",
                "Q3",
                "Q4",
                name="qualitylevel",
                create_type=False,
            ),
            nullable=True,
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
        sa.UniqueConstraint("owner_id", "code", name="uq_price_items_owner_code"),
    )
    op.create_index(
        "ix_price_items_owner_id",
        "price_items",
        ["owner_id"],
    )
    op.create_index(
        "ix_price_items_owner_archived",
        "price_items",
        ["owner_id", "is_archived"],
    )


def downgrade() -> None:
    op.drop_index("ix_price_items_owner_archived", table_name="price_items")
    op.drop_index("ix_price_items_owner_id", table_name="price_items")
    op.drop_table("price_items")
    op.execute("DROP TYPE IF EXISTS pricecategory")
    op.execute("DROP TYPE IF EXISTS priceunit")
    op.execute("DROP TYPE IF EXISTS pricescope")
    # NOTE: the "qualitylevel" enum is owned by revision 0011 and
    # intentionally left intact.