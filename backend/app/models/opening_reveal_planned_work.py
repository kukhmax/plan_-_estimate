"""OpeningRevealPlannedWork entity (Stage 10D / D19).

A headerless ordered child of Opening. The Opening itself is the scope header
(reveal_enabled, reveal_depth, side flags from Stage 5F). Work items for an
opening's reveal hang directly off the Opening as an ordered list.

PriceCategory.REVEAL is enforced at the service layer, not as a DB constraint.
Duplicate price_item_id values within the same opening are allowed (two coat rows).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class OpeningRevealPlannedWork(Base):
    __tablename__ = "opening_reveal_planned_works"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    opening_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("openings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    price_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("price_items.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
        comment=(
            "Must reference a PriceItem with category=REVEAL (enforced at service "
            "layer). Archived items are rejected for new selections but existing "
            "rows are never deleted by archiving."
        ),
    )
    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Ordinal position within the opening's reveal work list, from 0",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    price_item: Mapped["PriceItem"] = relationship()  # noqa: F821

    __table_args__ = (
        Index(
            "ix_opening_reveal_planned_works_opening_position",
            "opening_id",
            "position",
        ),
    )
