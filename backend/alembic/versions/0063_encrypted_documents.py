"""the content columns of the documents and protocols become TEXT for the encryption (EN-2b-2)

Revision ID: 0063_encrypted_documents
Revises: 0062_data_keys
Create Date: 2026-10-18 18:00:00.000000

The snapshots, the issued HTML, the questionnaire answers, the lists of attendees and the free notes of the contracts and of the five protocols (handover,
concealed works, acceptance, decisions, downtime) and the title of an issued document carry the data of the customer (the name, the address, the
persons present). They are stored as ciphertext (`enc1:...`) from now on, and ciphertext is TEXT: the JSON(B) columns become TEXT (`USING col::text`:
the JSON text of the old value is kept as it is, and is read as it is until the re-encoding command seals it), the two VARCHAR(255) become TEXT. No row is
changed otherwise: an old plain value stays and is read as before.

Reversible, but the downgrade **refuses** while any of these columns holds a ciphertext (`enc1:`): the older code cannot read it.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0063_encrypted_documents"
down_revision: str | None = "0062_data_keys"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSON, TEXT, VARCHAR = "json", "text", "varchar"
# table -> [(column, kind, nullable)]   (kind: what the column was before)
COLUMNS: dict[str, list[tuple[str, str, bool]]] = {
    "contracts": [("answers", JSON, False), ("snapshot", JSON, True), ("document_html", TEXT, True)],
    "handover_protocols": [
        ("attendees", JSON, False), ("rooms", JSON, False), ("meters", TEXT, True), ("notes", TEXT, True), ("snapshot", JSON, True), ("document_html", TEXT, True),
    ],
    "concealed_works_protocols": [
        ("attendees", JSON, False), ("work_note", TEXT, True), ("remarks", TEXT, True), ("snapshot", JSON, True), ("document_html", TEXT, True),
    ],
    "acceptance_protocols": [
        ("attendees", JSON, False), ("conditions_note", TEXT, True), ("surfaces", JSON, False), ("notes", TEXT, True), ("snapshot", JSON, True), ("document_html", TEXT, True),
    ],
    "decision_protocols": [
        ("attendees", JSON, False), ("items", JSON, False), ("notes", TEXT, True), ("snapshot", JSON, True), ("document_html", TEXT, True),
    ],
    "downtime_episodes": [
        ("cause_note", TEXT, True), ("need_text", TEXT, True), ("days", JSON, False), ("attendees", JSON, False), ("deadline_note", TEXT, True), ("notes", TEXT, True),
        ("notice_channel", VARCHAR, True), ("notice_snapshot", JSON, True), ("notice_html", TEXT, True), ("protocol_snapshot", JSON, True), ("protocol_html", TEXT, True),
    ],
    "issued_documents": [("title", VARCHAR, False)],
}


def _old_type(kind: str):
    if kind == JSON:
        return postgresql.JSONB().with_variant(sa.JSON(), "sqlite")
    return sa.String(255) if kind == VARCHAR else sa.Text()


def upgrade() -> None:
    for table, columns in COLUMNS.items():
        with op.batch_alter_table(table) as batch:
            for name, kind, nullable in columns:
                if kind == TEXT:
                    continue  # already TEXT: encrypted without a change of type
                batch.alter_column(
                    name, existing_type=_old_type(kind), type_=sa.Text(), existing_nullable=nullable, postgresql_using=f"{name}::text",
                )


def downgrade() -> None:
    bind = op.get_bind()
    encrypted = 0
    for table, columns in COLUMNS.items():
        for name, _kind, _nullable in columns:
            encrypted += bind.execute(sa.text(f"SELECT count(*) FROM {table} WHERE {name} LIKE 'enc1:%'")).scalar_one()
    if encrypted:
        raise RuntimeError(f"cannot downgrade: {encrypted} value(s) are encrypted (enc1:); decrypt them first, the older code cannot read them")

    for table, columns in COLUMNS.items():
        with op.batch_alter_table(table) as batch:
            for name, kind, nullable in columns:
                if kind == TEXT:
                    continue
                batch.alter_column(
                    name, existing_type=sa.Text(), type_=_old_type(kind), existing_nullable=nullable,
                    postgresql_using=f"{name}::jsonb" if kind == JSON else None,
                )
