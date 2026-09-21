"""Stage 12C — owner-scoped price coefficient catalog.

Persistence only (see `docs/stage-12-architecture.md`): `CoefficientGroup` is
an owner-scoped, named group of mutually-exclusive `CoefficientOption` rows
(`SINGLE_SELECT` is the only mode this cut implements). Neither entity is
assigned to any planned work in this sub-stage (12D), and neither affects any
Estimate calculation (12E) -- Stage 12C is catalog persistence only, mirroring
how Stage 9 shipped `PriceItem` before anything consumed it.
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


class CoefficientSelectionMode(str, enum.Enum):
    SINGLE_SELECT = "SINGLE_SELECT"


class CoefficientGroup(Base):
    """A named group of mutually-exclusive labor-price adjustment options.

    Mirrors `PriceItem`'s proven shape deliberately: a stable, immutable
    `code` (server-generated for owner-created groups, meaningful for a
    future bootstrap-seeded group) plus an editable `display_name`, so a
    future Stage 13 can reference a group without depending on translated
    display text (Stage 12 architecture D6).
    """

    __tablename__ = "coefficient_groups"

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
            "Stable semantic identifier, immutable after creation "
            "(mirrors PriceItem.code) -- CUSTOM_* for owner-created groups"
        ),
    )
    name_key: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Localized name key for a future bootstrap-seeded group",
    )
    display_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        comment="Owner-authored name; overrides name_key when set",
    )
    selection_mode: Mapped[CoefficientSelectionMode] = mapped_column(
        Enum(CoefficientSelectionMode, name="coefficientselectionmode"),
        nullable=False,
        default=CoefficientSelectionMode.SINGLE_SELECT,
        comment="Only SINGLE_SELECT is implemented in Stage 12C",
    )
    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Owner-controlled display ordering",
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

    options: Mapped[list["CoefficientOption"]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
        order_by="CoefficientOption.position",
    )

    __table_args__ = (
        UniqueConstraint("owner_id", "code", name="uq_coefficient_groups_owner_code"),
        Index("ix_coefficient_groups_owner_archived", "owner_id", "is_archived"),
    )


class CoefficientOption(Base):
    """One selectable percentage adjustment within a `CoefficientGroup`.

    `percentage` is a signed Decimal delta relative to the base labor price
    (e.g. `10.000` = +10%, `-5.000` = -5%) -- never a multiplier (Stage 12
    architecture D1/D4). `is_base` is an explicit boolean, not inferred from
    `percentage == 0`: which option is "the base" is a per-owner catalog
    fact about what their own Price Book price already assumes (D11), and
    more than one option could legitimately carry a `0%` adjustment without
    being that group's declared base.
    """

    __tablename__ = "coefficient_options"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("coefficient_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(
        String(120),
        nullable=False,
        comment="Stable semantic identifier, unique within its group, immutable after creation",
    )
    name_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    percentage: Mapped[Decimal] = mapped_column(
        Numeric(6, 3),
        nullable=False,
        comment=(
            "Signed percentage adjustment relative to the base labor price "
            "(10.000 = +10%, -5.000 = -5%); never a multiplier value"
        ),
    )
    is_base: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment=(
            "Marks the option representing the condition already assumed by "
            "the owner's Price Book base price (D11) -- never inferred from "
            "percentage == 0; at most one non-archived option per group may "
            "be the base (enforced at the service layer)"
        ),
    )
    position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="Owner-controlled ordering within the group",
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

    group: Mapped["CoefficientGroup"] = relationship(back_populates="options")

    __table_args__ = (
        UniqueConstraint(
            "group_id", "code", name="uq_coefficient_options_group_code"
        ),
        Index("ix_coefficient_options_group_archived", "group_id", "is_archived"),
    )

    @property
    def group_code(self) -> str:
        """Convenience accessor (Stage 12D) so a planned-work occurrence's
        selected-option read model can be serialized directly via Pydantic
        `from_attributes` without a separate catalog lookup (Stage 12
        architecture Sec 5). Requires `group` to already be eager-loaded;
        never triggers a lazy load itself."""
        return self.group.code
