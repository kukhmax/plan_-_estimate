"""Executor profile: who issues the documents (Stage 15C).

One profile per owner (the contractor): the name of the firm or the person, NIP, address, phone, e-mail and an optional bank
account. It is printed in the header of every client document (estimate, photo report, later contracts and protocols). The
values are stored in their canonical form (NIP as ten digits, postal code as `00-000`, account as 26 digits); the rules are
`app/domain/rules/polish_identifiers.py`. Multi-tenant ready like every root entity: `owner_id` -> users, unique.
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ExecutorProfile(Base):
    __tablename__ = "executor_profiles"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    nip: Mapped[str | None] = mapped_column(String(10), nullable=True)
    street: Mapped[str | None] = mapped_column(String(255), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(6), nullable=True)
    city: Mapped[str | None] = mapped_column(String(128), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bank_account: Mapped[str | None] = mapped_column(String(26), nullable=True)
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
        CheckConstraint("nip IS NULL OR length(nip) = 10", name="ck_executor_profiles_nip_length"),
        CheckConstraint("bank_account IS NULL OR length(bank_account) = 26", name="ck_executor_profiles_account_length"),
        CheckConstraint("length(name) > 0", name="ck_executor_profiles_name_not_empty"),
    )
