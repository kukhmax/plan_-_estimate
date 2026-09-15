import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.price_item import PriceUnit


class SourceType(str, enum.Enum):
    CONTRACTOR_PRICE_LIST = "CONTRACTOR_PRICE_LIST"
    MARKETPLACE = "MARKETPLACE"
    MANUFACTURER = "MANUFACTURER"
    MATERIAL_STORE = "MATERIAL_STORE"
    INDUSTRY_ARTICLE = "INDUSTRY_ARTICLE"
    OWN_PRICE = "OWN_PRICE"
    OTHER = "OTHER"


class PriceMarketReference(Base):
    """Market evidence for one PriceItem in a given region.

    Evidence is application-maintained (no write API in 9E.6A) and must never
    mutate the parent PriceItem.price: Market evidence and working price are
    intentionally independent numbers.
    """

    __tablename__ = "price_market_references"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    price_item_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("price_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    region: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        comment="Free-text region label (e.g. Kraków / Małopolskie)",
    )
    unit: Mapped[PriceUnit] = mapped_column(
        Enum(PriceUnit, name="priceunit"),
        nullable=False,
        comment="Must equal the parent PriceItem.unit; enforced in the service layer",
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="PLN",
        comment="ISO 4217-style code as a string; MVP accepts only PLN",
    )
    market_min: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        comment="Lower bound of observed market range, exactly 2 decimal places",
    )
    market_max: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        comment="Upper bound of observed market range, exactly 2 decimal places",
    )
    reference_price: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="Single representative market value (optional), never PriceItem.price",
    )
    methodology_note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="How the range was collected (sample size, date basis)",
    )
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When the market prices were actually checked; re-checking updates this",
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

    sources: Mapped[list["PriceSource"]] = relationship(
        "PriceSource",
        back_populates="market_reference",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="PriceSource.created_at, PriceSource.id",
    )


class PriceSource(Base):
    """One observed quote backing a market reference.

    Exactly one evidence mode: SINGLE (single quote), RANGE (min/max pair) or
    QUALITATIVE (no numeric quote, only a note). There is no quote-mode column —
    the mode is derived from which fields are populated.
    """

    __tablename__ = "price_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    market_reference_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("price_market_references.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Human-readable source label (company / shop / article title)",
    )
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, name="sourcetype"),
        nullable=False,
    )
    source_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="Optional evidence URL; OWN_PRICE sources do not require one",
    )
    source_region: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
        comment="Optional source-specific region override",
    )
    quoted_price_min: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="RANGE mode only — lower bound of the quote",
    )
    quoted_price_max: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="RANGE mode only — upper bound of the quote",
    )
    quoted_price_single: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="SINGLE mode only — one representative quote",
    )
    quoted_unit: Mapped[PriceUnit | None] = mapped_column(
        Enum(PriceUnit, name="priceunit"),
        nullable=True,
        comment=(
            "Unit the source itself quoted when it differs from the reference "
            "unit; no automatic unit conversion — incompatible sources are "
            "qualitative context only"
        ),
    )
    note: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="QUALITATIVE mode requires a meaningful non-blank evidence note",
    )
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="When this source quote was checked; each source ages like its reference",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    market_reference: Mapped["PriceMarketReference"] = relationship(
        "PriceMarketReference",
        back_populates="sources",
    )