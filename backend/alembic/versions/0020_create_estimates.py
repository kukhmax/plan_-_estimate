"""create estimates, estimate_lines, opening_reveal_planned_works

Revision ID: 0020_create_estimates
Revises: 0019_add_opening_reveals
Create Date: 2026-09-17 12:00:00.000000

Stage 10D: Estimate Domain Foundation.

Creates three new tables:
  - estimates: versioned project-level commercial documents
  - estimate_lines: snapshot lines (price/quantity frozen at creation)
  - opening_reveal_planned_works: per-opening reveal work selection (D19)

New enum types (created by this migration):
  - estimatestatus: DRAFT / FINAL / ACCEPTED / ARCHIVED
  - lineorigin: PLANNED_WORK / PRICE_BOOK / MANUAL
  - quantitysource: SURFACE_NET_AREA / REVEAL_LENGTH / REVEAL_AREA / MANUAL

Reused enum types (create_type=False):
  - priceunit and pricescope from migration 0014_create_price_book

Existing tables (openings, surfaces, price_items) are never altered.
Wall net_area and deduction_area remain unchanged.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0020_create_estimates"
down_revision: Union[str, None] = "0019_add_opening_reveals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- estimates ---
    op.create_table(
        "estimates",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(120), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT", "FINAL", "ACCEPTED", "ARCHIVED",
                name="estimatestatus",
            ),
            nullable=False,
            server_default="DRAFT",
        ),
        sa.Column("total", sa.Numeric(14, 2), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="PLN"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "project_id", "version", name="uq_estimates_project_version"
        ),
    )
    op.create_index("ix_estimates_owner_id", "estimates", ["owner_id"])
    op.create_index("ix_estimates_project_id", "estimates", ["project_id"])
    op.create_index(
        "ix_estimates_owner_status", "estimates", ["owner_id", "status"]
    )

    # --- estimate_lines ---
    op.create_table(
        "estimate_lines",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column(
            "estimate_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("estimates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "origin",
            sa.Enum(
                "PLANNED_WORK", "PRICE_BOOK", "MANUAL",
                name="lineorigin",
            ),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        # provenance (traceability only)
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "planned_work_id", postgresql.UUID(as_uuid=True), nullable=True
        ),
        sa.Column(
            "surface_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("surfaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("room_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "opening_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("openings.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # price book reference
        sa.Column(
            "price_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("price_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # snapshot
        sa.Column("item_code", sa.String(120), nullable=True),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column(
            "unit",
            postgresql.ENUM(
                "M2", "LM", "PCS", "HOUR", "DAY", "FLAT",
                name="priceunit",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "scope",
            postgresql.ENUM(
                "LABOR", "MATERIAL", "LABOR_AND_MATERIAL",
                name="pricescope",
                create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("currency", sa.String(3), nullable=False, server_default="PLN"),
        # quantity
        sa.Column("source_quantity", sa.Numeric(10, 3), nullable=True),
        sa.Column("quantity", sa.Numeric(10, 3), nullable=False),
        sa.Column(
            "quantity_source",
            sa.Enum(
                "SURFACE_NET_AREA", "REVEAL_LENGTH", "REVEAL_AREA", "MANUAL",
                name="quantitysource",
            ),
            nullable=False,
        ),
        sa.Column(
            "quantity_overridden",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        # price
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "price_override",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("amount", sa.Numeric(14, 2), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_estimate_lines_estimate_id", "estimate_lines", ["estimate_id"]
    )
    op.create_index(
        "ix_estimate_lines_surface_id", "estimate_lines", ["surface_id"]
    )
    op.create_index(
        "ix_estimate_lines_opening_id", "estimate_lines", ["opening_id"]
    )

    # --- opening_reveal_planned_works ---
    op.create_table(
        "opening_reveal_planned_works",
        sa.Column(
            "id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False
        ),
        sa.Column(
            "opening_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("openings.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "price_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("price_items.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_opening_reveal_planned_works_opening_id",
        "opening_reveal_planned_works",
        ["opening_id"],
    )
    op.create_index(
        "ix_opening_reveal_planned_works_opening_position",
        "opening_reveal_planned_works",
        ["opening_id", "position"],
    )
    op.create_index(
        "ix_opening_reveal_planned_works_price_item_id",
        "opening_reveal_planned_works",
        ["price_item_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_opening_reveal_planned_works_price_item_id",
        table_name="opening_reveal_planned_works",
    )
    op.drop_table("opening_reveal_planned_works")
    op.drop_table("estimate_lines")
    op.drop_table("estimates")

    op.execute("DROP TYPE IF EXISTS quantitysource")
    op.execute("DROP TYPE IF EXISTS lineorigin")
    op.execute("DROP TYPE IF EXISTS estimatestatus")
