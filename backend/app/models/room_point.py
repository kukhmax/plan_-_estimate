"""The points and routes of a room (V2-10): the owner's list "Punkty i trasy" -- a socket, a water point (pieces), a chase, a pipe run (metres).

A row names a Price Book item whose unit is `PCS` or `LM` and a quantity; the room it is in is the only place it is anchored to (a wall is not needed). The row is the
owner's own list, not accounting: it may be changed and deleted. An estimate takes the rows as a snapshot (`room_points_service.add_to_estimate`). Rows go with their
room and object (`ON DELETE CASCADE`); the note is free text typed by the owner, so it is encrypted like the other records.
"""
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.encrypted_text import EncryptedText


def _now() -> datetime:
    return datetime.now(UTC)


class RoomPoint(Base):
    __tablename__ = "room_points"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_room_points_quantity"),
        CheckConstraint("position >= 0", name="ck_room_points_position"),
        Index("ix_room_points_room", "room_id", "position"),
        Index("ix_room_points_project", "project_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    room_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    price_item_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("price_items.id"), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    note: Mapped[str | None] = mapped_column(EncryptedText("room_points.note"), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)
