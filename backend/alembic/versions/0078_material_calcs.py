"""V2-11: the norms of consumption and the calculations of materials of a room

Revision ID: 0078_material_calcs
Revises: 0077_room_points
Create Date: 2026-10-30 10:00:00.000000

Two NEW tables. `material_norms`: the owner's reference of consumption norms (a number such as a waste in percent, or a material with the Price Book item that gives its price);
the rows are made when the owner first opens them, from the starting numbers of the application. `material_calcs`: one calculation of a room (a package, an optional title typed by
the owner -- a TEXT column that the data encryption keeps --, the data of the calculation as JSON); it goes with its room and object (`ON DELETE CASCADE`). No existing row changes.

Reversible: the downgrade **refuses** (rather than deletes) while a calculation exists, a norm differs from its starting value, a material is tied to a price item or one was renamed
-- they are the owner's own input and are never dropped silently; a table of untouched starting norms is dropped (it is remade on the next opening).
"""
from collections.abc import Sequence
from decimal import Decimal

import sqlalchemy as sa
from alembic import op

revision: str = "0078_material_calcs"
down_revision: str | None = "0077_room_points"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "material_norms",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("package", sa.String(8), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("value", sa.Numeric(12, 3), nullable=True),
        sa.Column("price_item_id", sa.Uuid, sa.ForeignKey("price_items.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_id", "code", name="uq_material_norms_owner_code"),
        sa.CheckConstraint("package IN ('TILE', 'DRYWALL')", name="ck_material_norms_package"),
        sa.CheckConstraint("kind IN ('PARAM', 'MATERIAL')", name="ck_material_norms_kind"),
        sa.CheckConstraint("(kind = 'PARAM' AND value IS NOT NULL AND value >= 0) OR (kind = 'MATERIAL' AND value IS NULL)", name="ck_material_norms_value"),
        sa.CheckConstraint("kind = 'MATERIAL' OR price_item_id IS NULL", name="ck_material_norms_price_only_material"),
    )
    op.create_table(
        "material_calcs",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("owner_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", sa.Uuid, sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("room_id", sa.Uuid, sa.ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("package", sa.String(8), nullable=False),
        sa.Column("title", sa.Text, nullable=True),
        sa.Column("params", sa.JSON().with_variant(sa.dialects.postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("package IN ('TILE', 'DRYWALL')", name="ck_material_calcs_package"),
        sa.CheckConstraint("position >= 0", name="ck_material_calcs_position"),
    )
    op.create_index("ix_material_calcs_room", "material_calcs", ["room_id", "position"])
    op.create_index("ix_material_calcs_project", "material_calcs", ["project_id"])


def downgrade() -> None:
    from app.domain.data.material_norms import BY_CODE

    bind = op.get_bind()
    calcs = bind.execute(sa.text("SELECT count(*) FROM material_calcs")).scalar_one()
    changed = 0
    for code, value, price_item_id, name in bind.execute(sa.text("SELECT code, value, price_item_id, name FROM material_norms")).all():
        definition = BY_CODE.get(code)
        if definition is None or price_item_id is not None or name != definition.name or (definition.default is not None and Decimal(str(value)) != definition.default):
            changed += 1
    if calcs or changed:
        raise RuntimeError(
            f"cannot downgrade: {calcs} material calculation(s) and {changed} changed norm(s) exist; they are the owner's own input and are never dropped silently"
        )
    op.drop_index("ix_material_calcs_project", table_name="material_calcs")
    op.drop_index("ix_material_calcs_room", table_name="material_calcs")
    op.drop_table("material_calcs")
    op.drop_table("material_norms")
