"""V2-12: the packages "Elektryka" and "Hydraulika" in the norms and the calculations of materials

Revision ID: 0079_material_packages
Revises: 0078_material_calcs
Create Date: 2026-10-31 10:00:00.000000

No new table and no new column: the check on the `package` of `material_norms` and of `material_calcs` takes two more values (`ELECTRIC`, `PLUMBING`). The norms of the new packages are
made when the owner next opens the reference (from the starting numbers of the application). No existing row changes.

Reversible: the downgrade **refuses** (rather than deletes) while a calculation of the new packages exists, or a norm of them differs from its starting value, is tied to a price item or was
renamed -- they are the owner's own input; untouched starting norms of the new packages are deleted (they are remade on the next opening).
"""
from collections.abc import Sequence
from decimal import Decimal

import sqlalchemy as sa
from alembic import op

revision: str = "0079_material_packages"
down_revision: str | None = "0078_material_calcs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NEW = ("ELECTRIC", "PLUMBING")
OLD_CHECK = "package IN ('TILE', 'DRYWALL')"
NEW_CHECK = "package IN ('TILE', 'DRYWALL', 'ELECTRIC', 'PLUMBING')"


def _swap(table: str, name: str, check: str) -> None:
    with op.batch_alter_table(table) as batch:
        batch.drop_constraint(name, type_="check")
        batch.create_check_constraint(name, check)


def upgrade() -> None:
    _swap("material_norms", "ck_material_norms_package", NEW_CHECK)
    _swap("material_calcs", "ck_material_calcs_package", NEW_CHECK)


def downgrade() -> None:
    from app.domain.data.material_norms import BY_CODE

    bind = op.get_bind()
    calcs = bind.execute(sa.text("SELECT count(*) FROM material_calcs WHERE package IN ('ELECTRIC', 'PLUMBING')")).scalar_one()
    changed = 0
    for code, value, price_item_id, name in bind.execute(sa.text("SELECT code, value, price_item_id, name FROM material_norms WHERE package IN ('ELECTRIC', 'PLUMBING')")).all():
        definition = BY_CODE.get(code)
        if definition is None or price_item_id is not None or name != definition.name or (definition.default is not None and Decimal(str(value)) != definition.default):
            changed += 1
    if calcs or changed:
        raise RuntimeError(
            f"cannot downgrade: {calcs} electrical / plumbing calculation(s) and {changed} changed norm(s) of these packages exist; they are the owner's own input and are never dropped silently"
        )
    bind.execute(sa.text("DELETE FROM material_norms WHERE package IN ('ELECTRIC', 'PLUMBING')"))
    _swap("material_norms", "ck_material_norms_package", OLD_CHECK)
    _swap("material_calcs", "ck_material_calcs_package", OLD_CHECK)
