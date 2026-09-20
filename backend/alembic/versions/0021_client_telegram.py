"""add client telegram_username

Revision ID: 0021_client_telegram
Revises: 0020_create_estimates
Create Date: 2026-09-20 12:00:00.000000

Stage 10G.4 client contact correction: adds an optional Telegram
username/nick CONTACT field to clients (e.g. "@vasiya"). This is display
contact information only — it is unrelated to, and never used by, Telegram
Mini App authentication (User.telegram_user_id / chat_id) and involves no
Telegram Bot API integration.

Purely additive: existing rows get telegram_username = NULL. No backfill,
no data migration, no changes to any authentication table/column.

Revision ID shortened from the original "0021_add_client_telegram_username"
(34 chars) to fit alembic_version.version_num VARCHAR(32) — the schema
operation below is unchanged.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0021_client_telegram"
down_revision: Union[str, None] = "0020_create_estimates"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "clients",
        sa.Column("telegram_username", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("clients", "telegram_username")
