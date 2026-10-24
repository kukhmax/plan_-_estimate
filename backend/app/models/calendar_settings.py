"""The calendar settings of the owner (Stage 18C): the time zone, the kinds that send a message, the quiet hours, the digest.

One row per owner; a missing row means the defaults (the zone of Poland, the default kinds, quiet 21:00-07:00, the digest at 08:00).
The zone is a setting of the owner, not of an object (decision Q15): each reminder keeps its own instant and the zone it was made in, so
a change of the setting moves only the reminders that are still to be scheduled by a day.
"""
import uuid
from datetime import UTC, datetime, time

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Time,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON as GenericJSON

from app.core.database import Base

_JSONVariant = JSONB().with_variant(GenericJSON(), "sqlite")


class CalendarSettings(Base):
    __tablename__ = "calendar_settings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Europe/Warsaw")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    kind_overrides: Mapped[dict] = mapped_column(_JSONVariant, nullable=False, default=dict)  # {"BREAK_START": true, "BREAK_END": false}
    quiet_from: Mapped[time] = mapped_column(Time, nullable=False, default=lambda: time(21, 0))
    quiet_to: Mapped[time] = mapped_column(Time, nullable=False, default=lambda: time(7, 0))
    digest_at: Mapped[time] = mapped_column(Time, nullable=False, default=lambda: time(8, 0))
    language: Mapped[str | None] = mapped_column(String(2), nullable=True)  # null: the language of the application
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )

    __table_args__ = (
        UniqueConstraint("owner_id", name="uq_calendar_settings_owner"),
        CheckConstraint("language IS NULL OR language IN ('pl', 'ru', 'uk', 'en')", name="ck_calendar_settings_language"),
    )
