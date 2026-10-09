"""Persons of an object (Stage 16B.2): who may accept the work and sign the protocols.

A contract and the protocols name the people who act for each side: the customer or the customer's representative, the
supervision (technadzor), the contractor's representative. One register per object (`project_id`), multi-tenant ready
(`owner_id` -> users). `may_accept_and_sign` is the owner's own mark "this person may accept the work and sign the protocols";
the contract and the protocols copy the chosen persons into their snapshot, so a later change here never rewrites a document
that was already issued. Nothing is deleted: a person who left the object is archived.
"""
import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RepresentativeSide(str, enum.Enum):
    CUSTOMER = "CUSTOMER"  # the customer in person (Zamawiający)
    CUSTOMER_REPRESENTATIVE = "CUSTOMER_REPRESENTATIVE"  # a person who acts for the customer (przedstawiciel Zamawiającego)
    SUPERVISION = "SUPERVISION"  # technadzor / inspektor nadzoru, the developer's site manager
    CONTRACTOR = "CONTRACTOR"  # the contractor's representative (przedstawiciel Wykonawcy)


class ProjectRepresentative(Base):
    __tablename__ = "project_representatives"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    side: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    may_accept_and_sign: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        CheckConstraint(
            "side IN ('CUSTOMER', 'CUSTOMER_REPRESENTATIVE', 'SUPERVISION', 'CONTRACTOR')",
            name="ck_project_representatives_side",
        ),
        CheckConstraint("length(name) > 0", name="ck_project_representatives_name_not_empty"),
        Index("ix_project_representatives_project", "project_id", "is_archived"),
    )
