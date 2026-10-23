"""Merged walls: the parts a merged wall consists of, and the journal of what moved to it (backlog: "Объединить стены").

A merged wall is one `Surface` (the first wall the owner chose) that keeps the size of EVERY joined wall as a row of `surface_parts`: its
gross area is the sum of the parts, its photos and openings are those of all the joined walls. The other joined walls are archived, not
deleted (their plans, inspections and history stay), and each of them has a part whose `source_surface_id` points at it.

`surface_merge_moves` remembers which photo attachments and openings moved from which wall, so "Rozłącz" can give them back; whatever was
added to the merged wall after the merge stays on it.
"""

import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, Numeric, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SurfacePart(Base):
    __tablename__ = "surface_parts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # the merged wall
    surface_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("surfaces.id", ondelete="CASCADE"), nullable=False
    )
    # the wall this part was (the merged wall itself for its own first part); null when that wall is gone
    source_surface_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("surfaces.id", ondelete="SET NULL"), nullable=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    width: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    height: Mapped[Decimal] = mapped_column(Numeric(10, 3), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_surface_parts_surface_position", "surface_id", "position"),
        Index("ix_surface_parts_source_surface_id", "source_surface_id"),
    )


class MergeMoveKind(str, enum.Enum):
    PHOTO = "PHOTO"
    OPENING = "OPENING"


class SurfaceMergeMove(Base):
    __tablename__ = "surface_merge_moves"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    surface_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("surfaces.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[MergeMoveKind] = mapped_column(Enum(MergeMoveKind, name="mergemovekind"), nullable=False)
    # the id of the photo attachment or of the opening (no foreign key: the journal never blocks deleting them)
    item_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    from_surface_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("surfaces.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (Index("ix_surface_merge_moves_surface_id", "surface_id"),)
