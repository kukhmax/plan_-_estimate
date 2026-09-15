"""create price market evidence tables

Revision ID: 0015_create_market_evidence
Revises: 0014_create_price_book
Create Date: 2026-09-14 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0015_create_market_evidence"
down_revision: Union[str, None] = "0014_create_price_book"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "price_market_references",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "price_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("price_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("region", sa.String(length=120), nullable=False),
        sa.Column(
            "unit",
            # The priceunit type is owned by revision 0014; do not re-create it.
            postgresql.ENUM(
                "M2",
                "LM",
                "PCS",
                "HOUR",
                "DAY",
                "FLAT",
                name="priceunit",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "currency",
            sa.String(length=3),
            nullable=False,
            server_default=sa.text("'PLN'"),
        ),
        sa.Column("market_min", sa.Numeric(12, 2), nullable=False),
        sa.Column("market_max", sa.Numeric(12, 2), nullable=False),
        sa.Column("reference_price", sa.Numeric(12, 2), nullable=True),
        sa.Column("methodology_note", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
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
    op.create_index(
        "ix_price_market_references_price_item_id",
        "price_market_references",
        ["price_item_id"],
    )
    op.create_table(
        "price_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "market_reference_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("price_market_references.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_name", sa.String(length=255), nullable=False),
        sa.Column(
            "source_type",
            sa.Enum(
                "CONTRACTOR_PRICE_LIST",
                "MARKETPLACE",
                "MANUFACTURER",
                "MATERIAL_STORE",
                "INDUSTRY_ARTICLE",
                "OWN_PRICE",
                "OTHER",
                name="sourcetype",
            ),
            nullable=False,
        ),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("source_region", sa.String(length=120), nullable=True),
        sa.Column("quoted_price_min", sa.Numeric(12, 2), nullable=True),
        sa.Column("quoted_price_max", sa.Numeric(12, 2), nullable=True),
        sa.Column("quoted_price_single", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "quoted_unit",
            # Same priceunit type as price_market_references.unit.
            postgresql.ENUM(
                "M2",
                "LM",
                "PCS",
                "HOUR",
                "DAY",
                "FLAT",
                name="priceunit",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_price_sources_market_reference_id",
        "price_sources",
        ["market_reference_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_price_sources_market_reference_id", table_name="price_sources")
    op.drop_table("price_sources")
    op.drop_index(
        "ix_price_market_references_price_item_id",
        table_name="price_market_references",
    )
    op.drop_table("price_market_references")
    op.execute("DROP TYPE IF EXISTS sourcetype")
    # NOTE: price_items and the priceunit/qualitylevel enum types are owned by
    # earlier revisions (0014 / 0011) and intentionally left intact.