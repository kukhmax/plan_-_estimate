"""V2-12a: the hidden utilities on photo markers (type and distances)

Revision ID: 0080_photo_utilities
Revises: 0079_material_packages
Create Date: 2026-11-01 10:00:00.000000

Four NEW nullable columns of `photo_annotations` (the point markers of a photo): `utility` (the type of a hidden utility the marker shows: `CABLE`, `WATER_COLD`, `WATER_HOT`, `SEWER`,
`HEATING`, `GAS`) and three distances in centimetres with one decimal: `depth_cm` (in the wall or the chase), `from_floor_cm`, `from_corner_cm`. NULL means "not said": every existing marker
stays as it is. The type is a plain string with a CHECK (no PostgreSQL enum), each distance is checked to 0..1000 cm.

Reversible: the downgrade **refuses** (rather than drops) while a marker carries a type or a distance -- they are the owner's own input and are never dropped silently.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0080_photo_utilities"
down_revision: str | None = "0079_material_packages"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHECKS = (
    ("ck_photo_annotations_utility", "utility IS NULL OR utility IN ('CABLE', 'WATER_COLD', 'WATER_HOT', 'SEWER', 'HEATING', 'GAS')"),
    ("ck_photo_annotations_depth_cm", "depth_cm IS NULL OR (depth_cm >= 0 AND depth_cm <= 1000)"),
    ("ck_photo_annotations_from_floor_cm", "from_floor_cm IS NULL OR (from_floor_cm >= 0 AND from_floor_cm <= 1000)"),
    ("ck_photo_annotations_from_corner_cm", "from_corner_cm IS NULL OR (from_corner_cm >= 0 AND from_corner_cm <= 1000)"),
)


def upgrade() -> None:
    with op.batch_alter_table("photo_annotations") as batch:
        batch.add_column(sa.Column("utility", sa.String(12), nullable=True))
        batch.add_column(sa.Column("depth_cm", sa.Numeric(5, 1), nullable=True))
        batch.add_column(sa.Column("from_floor_cm", sa.Numeric(5, 1), nullable=True))
        batch.add_column(sa.Column("from_corner_cm", sa.Numeric(5, 1), nullable=True))
        for name, check in CHECKS:
            batch.create_check_constraint(name, check)


def downgrade() -> None:
    bind = op.get_bind()
    used = bind.execute(
        sa.text("SELECT count(*) FROM photo_annotations WHERE utility IS NOT NULL OR depth_cm IS NOT NULL OR from_floor_cm IS NOT NULL OR from_corner_cm IS NOT NULL")
    ).scalar_one()
    if used:
        raise RuntimeError(f"cannot downgrade: {used} photo marker(s) carry a utility type or a distance; they are the owner's own input and are never dropped silently")
    with op.batch_alter_table("photo_annotations") as batch:
        for name, _ in reversed(CHECKS):
            batch.drop_constraint(name, type_="check")
        for column in ("from_corner_cm", "from_floor_cm", "depth_cm", "utility"):
            batch.drop_column(column)
