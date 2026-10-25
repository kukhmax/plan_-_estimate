"""V2-10: the points and routes of a room, four new categories of the price book

Revision ID: 0077_room_points
Revises: 0076_payment_schedule_doc
Create Date: 2026-10-29 12:00:00.000000

One NEW table: `room_points` (a row of the owner's list "Punkty i trasy" of a room: a price item of the owner, a quantity > 0, an optional note, the order). It goes with its
room and object (`ON DELETE CASCADE`); the note is free text, so it is a TEXT column that the data encryption keeps (like the other records of an object).
Four NEW values of the category of a price item: `ELECTRICAL`, `PLUMBING`, `TILE`, `POINTS_ROUTES` (PostgreSQL: committed before use, `ADD VALUE` cannot be used in the transaction
that adds it, as in 0059; elsewhere the category is a plain string). No existing row changes.

Reversible: the downgrade **refuses** (rather than deletes) while a row of the list or a price item of a new category exists -- they are the owner's own input and are never
dropped silently. The values of the PostgreSQL enum stay (a value cannot be taken out of an enum without rebuilding it, and an unused one is harmless), as in 0059.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0077_room_points"
down_revision: str | None = "0076_payment_schedule_doc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW_CATEGORIES = ("ELECTRICAL", "PLUMBING", "TILE", "POINTS_ROUTES")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            for value in NEW_CATEGORIES:
                op.execute(f"ALTER TYPE pricecategory ADD VALUE IF NOT EXISTS '{value}'")
    op.create_table(
        "room_points",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Uuid, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("room_id", sa.Uuid, sa.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("price_item_id", sa.Uuid, sa.ForeignKey("price_items.id"), nullable=False),
        sa.Column("quantity", sa.Numeric(10, 2), nullable=False),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_room_points_quantity"),
        sa.CheckConstraint("position >= 0", name="ck_room_points_position"),
    )
    op.create_index("ix_room_points_room", "room_points", ["room_id", "position"])
    op.create_index("ix_room_points_project", "room_points", ["project_id"])


def downgrade() -> None:
    bind = op.get_bind()
    rows = bind.execute(sa.text("SELECT count(*) FROM room_points")).scalar_one()
    items = bind.execute(
        sa.text("SELECT count(*) FROM price_items WHERE CAST(category AS TEXT) IN ('ELECTRICAL', 'PLUMBING', 'TILE', 'POINTS_ROUTES')")
    ).scalar_one()
    if rows or items:
        raise RuntimeError(
            f"cannot downgrade: {rows} point / route row(s) and {items} price item(s) of the new categories exist; they are the owner's own input and are never dropped silently"
        )
    op.drop_index("ix_room_points_project", table_name="room_points")
    op.drop_index("ix_room_points_room", table_name="room_points")
    op.drop_table("room_points")
