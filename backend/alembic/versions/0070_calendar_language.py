"""V2-7: the language of the messages of the calendar may be Ukrainian or English too

Revision ID: 0070_calendar_language
Revises: 0069_vat
Create Date: 2026-10-24 21:00:00.000000

Only the check `ck_calendar_settings_language` changes: `language` may be NULL (the language of Telegram) or one of 'pl', 'ru', 'uk', 'en'. No row changes,
no column changes: every existing owner keeps what was saved.

Reversible: the downgrade sets 'uk' and 'en' back to NULL ("as in Telegram", the only way the old check allows to say it) and restores the old check.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0070_calendar_language"
down_revision: str | None = "0069_vat"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_NAME = "ck_calendar_settings_language"


def upgrade() -> None:
    op.drop_constraint(_NAME, "calendar_settings", type_="check")
    op.create_check_constraint(_NAME, "calendar_settings", "language IS NULL OR language IN ('pl', 'ru', 'uk', 'en')")


def downgrade() -> None:
    op.execute("UPDATE calendar_settings SET language = NULL WHERE language IN ('uk', 'en')")
    op.drop_constraint(_NAME, "calendar_settings", type_="check")
    op.create_check_constraint(_NAME, "calendar_settings", "language IS NULL OR language IN ('pl', 'ru')")
