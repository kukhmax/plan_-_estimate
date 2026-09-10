import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class OpeningType(str, enum.Enum):
    DOOR = "DOOR"
    WINDOW = "WINDOW"
    OTHER = "OTHER"


class Opening(Base):
    __tablename__ = "openings"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    surface_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("surfaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    opening_type: Mapped[OpeningType] = mapped_column(
        Enum(OpeningType, name="openingtype"),
        nullable=False,
    )
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    width: Mapped[Decimal] = mapped_column(
        Numeric(10, 3),
        nullable=False,
    )
    height: Mapped[Decimal] = mapped_column(
        Numeric(10, 3),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
    )
    description: Mapped[str | None] = mapped_column(String(4096), nullable=True)
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
        Index("ix_openings_surface_archived", "surface_id", "is_archived"),
    )
