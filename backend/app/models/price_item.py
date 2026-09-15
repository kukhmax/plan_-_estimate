import enum
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.checklist import QualityLevel


class PriceUnit(str, enum.Enum):
    M2 = "M2"
    LM = "LM"
    PCS = "PCS"
    HOUR = "HOUR"
    DAY = "DAY"
    FLAT = "FLAT"


class PriceCategory(str, enum.Enum):
    PREPARATION = "PREPARATION"
    SKIM_COAT = "SKIM_COAT"
    PLASTER = "PLASTER"
    DRYWALL = "DRYWALL"
    PAINTING = "PAINTING"
    GLASS_FIBER = "GLASS_FIBER"
    MICROCEMENT = "MICROCEMENT"
    DECORATIVE = "DECORATIVE"
    REVEAL = "REVEAL"
    MATERIAL = "MATERIAL"
    OTHER = "OTHER"


class PriceScope(str, enum.Enum):
    LABOR = "LABOR"
    MATERIAL = "MATERIAL"
    LABOR_AND_MATERIAL = "LABOR_AND_MATERIAL"


class PriceItem(Base):
    """An owner-editable reference-price row in the contractor's Price Book.

    Stage 9 is a catalog, not an estimate: a PriceItem belongs to no
    Project/room/inspection and answers only "what do we charge per unit?".
    """

    __tablename__ = "price_items"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        comment=(
            "Stable semantic identifier (CENNIK_* / CUSTOM_*); immutable after "
            "creation — the Stage 11 recommended-work → price-item mapping key"
        ),
    )
    name_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Localized name key for seeded rows",
    )
    display_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="User-authored name for custom rows (display precedence over name_key)",
    )
    category: Mapped[PriceCategory] = mapped_column(
        Enum(PriceCategory, name="pricecategory"),
        nullable=False,
    )
    unit: Mapped[PriceUnit] = mapped_column(
        Enum(PriceUnit, name="priceunit"),
        nullable=False,
    )
    price: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment=(
            "Unit price in PLN; exactly 2 decimal places. NULL = owner commercial "
            "price not set yet (Stage 10 rejects estimate lines); 0.00 is a real, "
            "explicitly set zero price and must never be reused as a 'not set' sentinel"
        ),
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="PLN",
        comment=(
            "ISO 4217-style code stored as a string (no DB enum); MVP accepts "
            "only PLN so future currencies need no enum migration"
        ),
    )
    price_scope: Mapped[PriceScope] = mapped_column(
        Enum(PriceScope, name="pricescope"),
        nullable=False,
        default=PriceScope.LABOR,
    )
    quality_level: Mapped[QualityLevel | None] = mapped_column(
        Enum(QualityLevel, name="qualitylevel"),
        nullable=True,
        comment=(
            "Optional pricing/applicability hint only; Stage 9 does not own "
            "substrate↔quality compatibility (Stage 6 is authoritative)"
        ),
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
        UniqueConstraint("owner_id", "code", name="uq_price_items_owner_code"),
        Index("ix_price_items_owner_archived", "owner_id", "is_archived"),
    )