"""OpeningRevealPlannedWork entity (Stage 10D / D19).

A headerless ordered child of Opening. The Opening itself is the scope header
(reveal_enabled, reveal_depth, side flags from Stage 5F). Work items for an
opening's reveal hang directly off the Opening as an ordered list.

PriceCategory.REVEAL is enforced at the service layer, not as a DB constraint.
Duplicate price_item_id values within the same opening are allowed (two coat rows).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, Integer, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.price_coefficient import CoefficientOption


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
    coefficient_assignments: Mapped[
        list["OpeningRevealPlannedWorkCoefficientAssignment"]
    ] = relationship(
        back_populates="opening_reveal_planned_work",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index(
            "ix_opening_reveal_planned_works_opening_position",
            "opening_id",
            "position",
        ),
    )

    @property
    def coefficient_options(self) -> list["CoefficientOption"]:
        """Selected coefficient options for this occurrence, in a stable,
        deterministic read order -- mirrors `SurfacePlannedWork.
        coefficient_options` exactly (Stage 12 architecture Sec 13). Requires
        `coefficient_assignments` (and each assignment's `coefficient_option.
        group`) to already be eager-loaded; never triggers a lazy load.
        """
        return sorted(
            (a.coefficient_option for a in self.coefficient_assignments),
            key=lambda o: (o.group.position, o.position, str(o.id)),
        )


class OpeningRevealPlannedWorkCoefficientAssignment(Base):
    """One selected `CoefficientOption` applied to one specific reveal
    planned-work OCCURRENCE (Stage 12D). Mirrors
    `SurfacePlannedWorkCoefficientAssignment` exactly -- see that class's
    docstring for the full rationale (no snapshot, atomic delete/recreate
    with its parent row, RESTRICT on the option FK since options are only
    ever soft-archived).
    """

    __tablename__ = "opening_reveal_planned_work_coefficient_assignments"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    opening_reveal_planned_work_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("opening_reveal_planned_works.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    coefficient_option_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("coefficient_options.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
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

    opening_reveal_planned_work: Mapped["OpeningRevealPlannedWork"] = relationship(
        back_populates="coefficient_assignments"
    )
    coefficient_option: Mapped["CoefficientOption"] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "opening_reveal_planned_work_id",
            "coefficient_option_id",
            name="uq_opening_reveal_planned_work_coefficient_option",
        ),
    )
