import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AreaPlane(str, enum.Enum):
    FLOOR = "FLOOR"
    CEILING = "CEILING"


class AreaOperation(str, enum.Enum):
    ADD = "ADD"
    SUBTRACT = "SUBTRACT"


class AreaSegment(Base):
    __tablename__ = "area_segments"

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
    plane: Mapped[AreaPlane] = mapped_column(
        Enum(AreaPlane, name="areaplane"),
        nullable=False,
    )
    operation: Mapped[AreaOperation] = mapped_column(
        Enum(AreaOperation, name="areaoperation"),
        nullable=False,
    )
    width: Mapped[Decimal] = mapped_column(
        Numeric(10, 3),
        nullable=False,
    )
    height: Mapped[Decimal] = mapped_column(
        Numeric(10, 3),
        nullable=False,
    )
    position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    label: Mapped[str | None] = mapped_column(String(255), nullable=True)
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
        Index("ix_area_segments_room_plane_archived", "room_id", "plane", "is_archived"),
    )
