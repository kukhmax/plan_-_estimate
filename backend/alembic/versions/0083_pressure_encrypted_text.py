"""pressure_test_protocols: the encrypted JSON columns are TEXT (V2-12b hotfix)

Revision ID: 0083_pressure_encrypted_text
Revises: 0082_pressure_tests
Create Date: 2026-11-02 18:00:00.000000

0082 created `attendees` and `snapshot` as JSONB, but the data encryption keeps them as text (`enc1:...`, like the other encrypted JSON columns, see 0063): the verification of the
encryption (`LIKE` over the column) and the first write of a protocol failed on a real PostgreSQL. The table was empty when this was found; the columns become TEXT (`::text`).

Reversible: the downgrade refuses while an encrypted value is stored (the older column type cannot hold it), otherwise the columns return to JSONB (`::jsonb`).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0083_pressure_encrypted_text"
down_revision: str | None = "0082_pressure_tests"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON = postgresql.JSONB().with_variant(sa.JSON(), "sqlite")
COLUMNS = (("attendees", False), ("snapshot", True))


def upgrade() -> None:
    with op.batch_alter_table("pressure_test_protocols") as batch:
        for name, nullable in COLUMNS:
            batch.alter_column(name, existing_type=JSON, type_=sa.Text(), existing_nullable=nullable, postgresql_using=f"{name}::text")


def downgrade() -> None:
    bind = op.get_bind()
    encrypted = sum(
        bind.execute(sa.text(f"SELECT count(*) FROM pressure_test_protocols WHERE {name} LIKE 'enc1:%'")).scalar_one() for name, _nullable in COLUMNS
    )
    if encrypted:
        raise RuntimeError(f"cannot downgrade: {encrypted} value(s) are encrypted (enc1:); decrypt them first, the older column type cannot hold them")
    with op.batch_alter_table("pressure_test_protocols") as batch:
        for name, nullable in COLUMNS:
            batch.alter_column(name, existing_type=sa.Text(), type_=JSON, existing_nullable=nullable, postgresql_using=f"{name}::jsonb")
