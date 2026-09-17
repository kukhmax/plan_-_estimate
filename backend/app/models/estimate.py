"""Estimate and EstimateLine entities (Stage 10D).

An Estimate is a versioned, project-level commercial document. Each line is a
snapshot — the Price Book, geometry, and reveal geometry can change after line
creation without affecting the line. FINAL/ACCEPTED documents are immutable.
"""
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
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.price_item import PriceScope, PriceUnit


class EstimateStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    FINAL = "FINAL"
    ACCEPTED = "ACCEPTED"
    ARCHIVED = "ARCHIVED"


class LineOrigin(str, enum.Enum):
    PLANNED_WORK = "PLANNED_WORK"
    PRICE_BOOK = "PRICE_BOOK"
    MANUAL = "MANUAL"


class QuantitySource(str, enum.Enum):
    SURFACE_NET_AREA = "SURFACE_NET_AREA"
    REVEAL_LENGTH = "REVEAL_LENGTH"
    REVEAL_AREA = "REVEAL_AREA"
    MANUAL = "MANUAL"


class Estimate(Base):
    """Versioned project-level commercial document."""

    __tablename__ = "estimates"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Monotonically increasing per project; meaningful commercial revision only",
    )
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[EstimateStatus] = mapped_column(
        Enum(EstimateStatus, name="estimatestatus"),
        nullable=False,
        default=EstimateStatus.DRAFT,
    )
    total: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2),
        nullable=True,
        comment="Sum of quantized line amounts; NULL while all lines are unpriced",
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="PLN"
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

    lines: Mapped[list["EstimateLine"]] = relationship(
        back_populates="estimate",
        cascade="all, delete-orphan",
        order_by="EstimateLine.position",
    )

    __table_args__ = (
        UniqueConstraint(
            "project_id", "version", name="uq_estimates_project_version"
        ),
        Index("ix_estimates_owner_status", "owner_id", "status"),
    )


class EstimateLine(Base):
    """Materialized, priced, immutable snapshot line inside an Estimate.

    The snapshot fields (item_code through amount) are written once at
    line-creation time and are never re-read from the Price Book or geometry
    post-creation. Provenance refs (plan_id, planned_work_id, surface_id,
    room_id, opening_id) are stored for traceability only.

    Surface PLANNED_WORK: plan_id + planned_work_id + surface_id + room_id set;
                          opening_id = NULL.
    Reveal PLANNED_WORK:  planned_work_id + surface_id + room_id + opening_id set;
                          plan_id = NULL (OpeningRevealPlannedWork has no header).
    PRICE_BOOK / MANUAL:  all provenance refs NULL (MANUAL may omit price_item_id).
    """

    __tablename__ = "estimate_lines"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    estimate_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("estimates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    origin: Mapped[LineOrigin] = mapped_column(
        Enum(LineOrigin, name="lineorigin"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Display order within the estimate",
    )

    # Provenance (traceability only — never recomputed from these refs)
    plan_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    planned_work_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    surface_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("surfaces.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    room_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    opening_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("openings.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Price Book reference (nullable — NULL only for MANUAL lines)
    price_item_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid,
        ForeignKey("price_items.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Commercial snapshot — written once, never re-read from book or geometry
    item_code: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
        comment="PriceItem.code at creation; NULL for MANUAL lines",
    )
    description: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    unit: Mapped[PriceUnit] = mapped_column(
        Enum(PriceUnit, name="priceunit"),
        nullable=False,
    )
    scope: Mapped[PriceScope] = mapped_column(
        Enum(PriceScope, name="pricescope"),
        nullable=False,
        comment="MANUAL lines restricted to LABOR or MATERIAL",
    )
    currency: Mapped[str] = mapped_column(
        String(3), nullable=False, default="PLN"
    )

    # Quantity snapshot
    source_quantity: Mapped[Decimal | None] = mapped_column(
        Numeric(10, 3),
        nullable=True,
        comment="Suggested qty at generation; NULL when geometry not available",
    )
    quantity: Mapped[Decimal] = mapped_column(
        Numeric(10, 3),
        nullable=False,
        comment="Commercial quantity; defaults to source_quantity, owner-overridable",
    )
    quantity_source: Mapped[QuantitySource] = mapped_column(
        Enum(QuantitySource, name="quantitysource"),
        nullable=False,
    )
    quantity_overridden: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # Price snapshot
    unit_price: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
        comment="NULL = Do ustalenia; 0.00 = explicit zero",
    )
    price_override: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # Amount
    amount: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2),
        nullable=True,
        comment="quantity * unit_price quantized 0.01; NULL while unpriced",
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

    estimate: Mapped["Estimate"] = relationship(back_populates="lines")
