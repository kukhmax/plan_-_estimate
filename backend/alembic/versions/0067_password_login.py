"""V2-1: accounts that sign in without Telegram -- the table user_credentials (e-mail, password hash, failed attempts, lock)

Revision ID: 0067_password_login
Revises: 0066_surface_merge
Create Date: 2026-10-23 12:00:00.000000

One NEW table; no existing table or row is changed. A web account is an ordinary `users` row with a negative `telegram_user_id`; its e-mail and
password hash live here. Until the owner creates an account (python -m app.cli.users create) the table stays empty and the application works as before;
the login by password is also switched off by AUTH_PASSWORD_ENABLED (default false).

Reversible: the downgrade drops the table (the web accounts stay as users without a way to sign in).
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0067_password_login"
down_revision: str | None = "0066_surface_merge"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_credentials",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("user_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_user_credentials_email", "user_credentials", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_user_credentials_email", table_name="user_credentials")
    op.drop_table("user_credentials")
