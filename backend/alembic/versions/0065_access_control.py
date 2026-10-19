"""closed registration: the list of the accounts that may enter (access_entries) and its two settings (access_settings)

Revision ID: 0065_access_control
Revises: 0064_encrypted_payments
Create Date: 2026-10-19 09:00:00.000000

Until now any Telegram account that opened the bot got an account of its own. From now on the application can be closed: only the accounts in
`access_entries` with the status ACTIVE enter; anyone else is refused (and noted as PENDING for the administrator to decide).

The migration keeps everybody who works today: every existing user becomes an ACTIVE entry, the EARLIEST one (the owner, who made the first
login) is the administrator, and the registration is switched to CLOSED (`access_settings.closed` = "1"). The administrator and the switch can be
changed afterwards (the screen; `python -m app.cli.access`). No user, client or other row is changed.

Reversible: the downgrade drops the two tables.
"""
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "0065_access_control"
down_revision: str | None = "0064_encrypted_payments"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    entries = op.create_table(
        "access_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("first_name", sa.String(255), nullable=True),
        sa.Column("last_name", sa.String(255), nullable=True),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("status IN ('PENDING', 'ACTIVE', 'BLOCKED')", name="ck_access_entries_status"),
    )
    op.create_index("ix_access_entries_telegram_user_id", "access_entries", ["telegram_user_id"], unique=True)
    settings = op.create_table(
        "access_settings",
        sa.Column("key", sa.String(40), nullable=False),
        sa.Column("value", sa.Text(), nullable=False, server_default=""),
        sa.PrimaryKeyConstraint("key"),
    )

    bind = op.get_bind()
    users = bind.execute(
        sa.text("SELECT telegram_user_id, username, first_name, last_name FROM users ORDER BY created_at, id")
    ).all()
    now = datetime.now(UTC)
    op.bulk_insert(
        entries,
        [
            {
                "id": uuid.uuid4(),
                "telegram_user_id": telegram_user_id,
                "username": username,
                "first_name": first_name,
                "last_name": last_name,
                "status": "ACTIVE",
                "is_admin": index == 0,
                "created_at": now,
                "decided_at": now,
            }
            for index, (telegram_user_id, username, first_name, last_name) in enumerate(users)
        ],
    )
    op.bulk_insert(settings, [{"key": "closed", "value": "1"}, {"key": "contact", "value": ""}])


def downgrade() -> None:
    op.drop_table("access_settings")
    op.drop_index("ix_access_entries_telegram_user_id", table_name="access_entries")
    op.drop_table("access_entries")
