import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SurfaceType(str, enum.Enum):
    WALL = "WALL"
    CEILING = "CEILING"
    FLOOR = "FLOOR"
    OTHER = "OTHER"


class Surface(Base):
    __tablename__ = "surfaces"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    room_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("rooms.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    surface_type: Mapped[SurfaceType] = mapped_column(
        Enum(SurfaceType, name="surfacetype"),
        nullable=False,
    )
    description: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    position: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        comment="Sequential order among surfaces of a room (null for legacy surfaces)",
    )
    width: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 3),
        nullable=True,
    )
    height: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 3),
        nullable=True,
    )
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_surfaces_room_archived", "room_id", "is_archived"),
    )
