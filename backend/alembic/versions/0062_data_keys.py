"""data_keys and the encrypted columns of the clients, the objects, the persons of an object and the notes (EN-2a)

Revision ID: 0062_data_keys
Revises: 0061_expense_category
Create Date: 2026-10-18 14:00:00.000000

`data_keys`: the data key of an owner, stored only wrapped by the key of the server (docs/CLIENT_DATA_ENCRYPTION_PLAN_RU.md section 4).
The personal text columns become `TEXT` (a ciphertext is longer than its text); no row is touched: an old plain value stays as it is and is
read as it is, a value is written as ciphertext when it is next saved, and the re-encoding command of EN-2b turns the rest. The four indexes
of the client columns lose their meaning (the search runs on the decrypted values) and are dropped.

Reversible, but the downgrade **refuses** while any of these columns holds a ciphertext (`enc1:`): the older code cannot read it, so the values
are decrypted first (EN-2b command); it never turns a ciphertext into silently unreadable text.
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0062_data_keys"
down_revision: str | None = "0061_expense_category"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# table -> [(column, old length, nullable)]
COLUMNS: dict[str, list[tuple[str, int, bool]]] = {
    "clients": [
        ("first_name", 255, True), ("last_name", 255, True), ("company_name", 512, True), ("phone", 50, True), ("email", 255, True),
        ("nip", 20, True), ("street", 255, True), ("postal_code", 10, True), ("city", 128, True), ("telegram_username", 64, True),
        ("notes", 4096, True),
    ],
    "projects": [("name", 255, False), ("address", 512, False), ("city", 255, False), ("postal_code", 20, False), ("description", 4096, True)],
    "project_representatives": [("name", 255, False), ("phone", 50, True), ("email", 255, True)],
}
TEXT_COLUMNS = {"project_notes": ["body"]}  # already TEXT: encrypted without a change of type


def upgrade() -> None:
    op.create_table(
        "data_keys",
        sa.Column("id", sa.Uuid(), primary_key=True, nullable=False),
        sa.Column("owner_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key_id", sa.String(64), nullable=False),
        sa.Column("wrapped_dek", sa.Text(), nullable=False),
        sa.Column("wrapped_by", sa.String(16), nullable=False, server_default="SERVER_KEK"),
        sa.Column("kek_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("wrapped_by IN ('SERVER_KEK', 'OWNER_KEY')", name="ck_data_keys_wrapped_by"),
        sa.UniqueConstraint("key_id", name="uq_data_keys_key_id"),
    )
    op.create_index("ix_data_keys_owner_id", "data_keys", ["owner_id"])
    op.create_index(
        "uq_data_keys_one_active_per_owner", "data_keys", ["owner_id"], unique=True,
        postgresql_where=sa.text("active"), sqlite_where=sa.text("active"),
    )

    op.drop_index("ix_clients_owner_last_name", table_name="clients")
    op.drop_index("ix_clients_owner_first_name", table_name="clients")
    op.drop_index("ix_clients_phone", table_name="clients")
    op.drop_index("ix_clients_company_name", table_name="clients")

    for table, columns in COLUMNS.items():
        with op.batch_alter_table(table) as batch:
            for name, length, nullable in columns:
                batch.alter_column(name, existing_type=sa.String(length), type_=sa.Text(), existing_nullable=nullable)


def downgrade() -> None:
    bind = op.get_bind()
    encrypted = 0
    for table, columns in {**{t: [c[0] for c in cols] for t, cols in COLUMNS.items()}, **TEXT_COLUMNS}.items():
        for name in columns:
            encrypted += bind.execute(sa.text(f"SELECT count(*) FROM {table} WHERE {name} LIKE 'enc1:%'")).scalar_one()
    if encrypted:
        raise RuntimeError(f"cannot downgrade: {encrypted} value(s) are encrypted (enc1:); decrypt them first, the older code cannot read them")

    for table, columns in COLUMNS.items():
        with op.batch_alter_table(table) as batch:
            for name, length, nullable in columns:
                batch.alter_column(name, existing_type=sa.Text(), type_=sa.String(length), existing_nullable=nullable)

    op.create_index("ix_clients_company_name", "clients", ["company_name"])
    op.create_index("ix_clients_phone", "clients", ["phone"])
    op.create_index("ix_clients_owner_first_name", "clients", ["owner_user_id", "first_name"])
    op.create_index("ix_clients_owner_last_name", "clients", ["owner_user_id", "last_name"])

    op.drop_index("uq_data_keys_one_active_per_owner", table_name="data_keys")
    op.drop_index("ix_data_keys_owner_id", table_name="data_keys")
    op.drop_table("data_keys")
