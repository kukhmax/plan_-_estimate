"""Who may enter the application (closed registration; backlog item, not a roadmap stage).

One row per Telegram account that has asked for access or was admitted: `PENDING` (it opened the bot while the registration was closed;
waits for the administrator), `ACTIVE` (may work), `BLOCKED` (refused, whatever the mode). The administrator is a row with `is_admin`; an
administrator can always enter and cannot be blocked through the screen. `access_settings` holds two values: `closed` ("1" = only the
ACTIVE accounts enter; no row or "0" = anyone may register, as before) and `contact` (the text shown to a refused person).

The profile columns are what Telegram itself says about the account (username, first and last name): they let the administrator
recognise a pending request. Nothing of a client is kept here.
"""
import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AccessStatus(str, enum.Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"


class AccessEntry(Base):
    __tablename__ = "access_entries"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default=AccessStatus.PENDING.value)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (CheckConstraint("status IN ('PENDING', 'ACTIVE', 'BLOCKED')", name="ck_access_entries_status"),)


class AccessSetting(Base):
    __tablename__ = "access_settings"

    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
