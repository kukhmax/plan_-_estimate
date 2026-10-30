"""surface_planned_works.quantity: the owner's quantity of a work the area does not measure (owner 2026-10-30)

Revision ID: 0091_planned_work_quantity
Revises: 0090_vat_own_rate
Create Date: 2026-10-30 22:00:00.000000

One NEW nullable column (numeric 10,3, > 0) on `surface_planned_works`: the metres / pieces the owner types when a work in metres or
pieces is added to a work plan ("Dodaj do prac"); the estimate takes it instead of "Ilość do ustalenia". Every existing row gets NULL:
nothing changes in any plan or estimate until the owner types a quantity.

Reversible: the downgrade drops the check and the column (the typed quantities are lost; the estimate lines keep what they hold).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0091_planned_work_quantity"
down_revision: str | None = "0090_vat_own_rate"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("surface_planned_works") as batch:
        batch.add_column(sa.Column("quantity", sa.Numeric(10, 3), nullable=True))
        batch.create_check_constraint("ck_surface_planned_works_quantity", "quantity IS NULL OR quantity > 0")


def downgrade() -> None:
    with op.batch_alter_table("surface_planned_works") as batch:
        batch.drop_constraint("ck_surface_planned_works_quantity", type_="check")
        batch.drop_column("quantity")
