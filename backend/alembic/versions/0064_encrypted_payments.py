"""the title, the number, the shop / supplier and the note of the settlement records become TEXT for the encryption (EN-2b-3)

Revision ID: 0064_encrypted_payments
Revises: 0063_encrypted_documents
Create Date: 2026-10-18 20:00:00.000000

What an invoice, an advance, a payment or an expense is for, its number, the shop or supplier and the note name the customer's work and the owner's
suppliers. They are stored as ciphertext (`enc1:...`) from now on, and ciphertext is TEXT: `title` (VARCHAR 500), `number` (VARCHAR 64) and
`counterparty` (VARCHAR 255) become TEXT, `note` already is. No row is changed: an old plain value stays and is read as before until the re-encoding
command seals it. The amounts, dates, the kind and the category stay plain (the totals and the due days are made on them). The blank-title check
stays (the service refuses a blank title before it is sealed).

Reversible, but the downgrade **refuses** while any of these columns holds a ciphertext (`enc1:`): the older code cannot read it.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0064_encrypted_payments"
down_revision: str | None = "0063_encrypted_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# table -> [(column, length it had, nullable)]; `note` was TEXT and is only encrypted
COLUMNS: dict[str, list[tuple[str, int | None, bool]]] = {
    "project_payments": [("title", 500, False), ("number", 64, True), ("counterparty", 255, True), ("note", None, True)],
}


def upgrade() -> None:
    for table, columns in COLUMNS.items():
        with op.batch_alter_table(table) as batch:
            for name, length, nullable in columns:
                if length is None:
                    continue  # already TEXT: encrypted without a change of type
                batch.alter_column(name, existing_type=sa.String(length), type_=sa.Text(), existing_nullable=nullable)


def downgrade() -> None:
    bind = op.get_bind()
    encrypted = 0
    for table, columns in COLUMNS.items():
        for name, _length, _nullable in columns:
            encrypted += bind.execute(sa.text(f"SELECT count(*) FROM {table} WHERE {name} LIKE 'enc1:%'")).scalar_one()
    if encrypted:
        raise RuntimeError(f"cannot downgrade: {encrypted} value(s) are encrypted (enc1:); decrypt them first, the older code cannot read them")

    for table, columns in COLUMNS.items():
        with op.batch_alter_table(table) as batch:
            for name, length, nullable in columns:
                if length is None:
                    continue
                batch.alter_column(name, existing_type=sa.Text(), type_=sa.String(length), existing_nullable=nullable)
