"""The materials of the packages "Płytki", "GKL" (V2-11), "Elektryka" and "Hydraulika" (V2-12): the owner's norms and the owner's calculations of a room.

`MaterialNorm` is a row of the owner's reference of consumption norms (`data/material_norms.py` holds the starting rows, made when the owner first opens them): a number (`PARAM`)
or a material (`MATERIAL`) that may name the Price Book item giving its price. `MaterialCalc` is one calculation of a room: a package (tile or drywall), an optional title the owner
typed (so it is encrypted) and the data of the calculation as JSON. What a calculation needs to buy is **never stored**: it is made from the data and the norms every time
(`domain/rules/materials.py`), so a changed norm is seen at once; an estimate takes a snapshot of it.
"""
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON as GenericJSON

from app.core.database import Base
from app.core.encrypted_text import EncryptedText

_JSONVariant = JSONB().with_variant(GenericJSON(), "sqlite")


def _now() -> datetime:
    return datetime.now(UTC)


class MaterialNorm(Base):
    __tablename__ = "material_norms"
    __table_args__ = (
        UniqueConstraint("owner_id", "code", name="uq_material_norms_owner_code"),
        CheckConstraint("package IN ('TILE', 'DRYWALL', 'ELECTRIC', 'PLUMBING')", name="ck_material_norms_package"),
        CheckConstraint("kind IN ('PARAM', 'MATERIAL')", name="ck_material_norms_kind"),
        CheckConstraint("(kind = 'PARAM' AND value IS NOT NULL AND value >= 0) OR (kind = 'MATERIAL' AND value IS NULL)", name="ck_material_norms_value"),
        CheckConstraint("kind = 'MATERIAL' OR price_item_id IS NULL", name="ck_material_norms_price_only_material"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    package: Mapped[str] = mapped_column(String(8), nullable=False)
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)  # a material: what the owner reads and the estimate prints
    value: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)  # a number: the norm; a material: none
    price_item_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("price_items.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class MaterialCalc(Base):
    __tablename__ = "material_calcs"
    __table_args__ = (
        CheckConstraint("package IN ('TILE', 'DRYWALL', 'ELECTRIC', 'PLUMBING')", name="ck_material_calcs_package"),
        CheckConstraint("position >= 0", name="ck_material_calcs_position"),
        Index("ix_material_calcs_room", "room_id", "position"),
        Index("ix_material_calcs_project", "project_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    room_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("rooms.id", ondelete="CASCADE"), nullable=False)
    package: Mapped[str] = mapped_column(String(8), nullable=False)
    title: Mapped[str | None] = mapped_column(EncryptedText("material_calcs.title"), nullable=True)
    params: Mapped[dict] = mapped_column(_JSONVariant, nullable=False, default=dict)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)
