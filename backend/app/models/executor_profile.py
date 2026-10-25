"""Executor profile: who issues the documents (Stage 15C).

One profile per owner (the contractor): the name of the firm or the person, NIP, address, phone, e-mail and an optional bank
account. It is printed in the header of every client document (estimate, photo report, later contracts and protocols). The
values are stored in their canonical form (NIP as ten digits, postal code as `00-000`, account as 26 digits); the rules are
`app/domain/rules/polish_identifiers.py`. Multi-tenant ready like every root entity: `owner_id` -> users, unique.
"""
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Uuid
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
    # V2-6: the VAT of the owner's estimates. NULL / NULL = not set; EXEMPT / NULL = "zw."; RATE / 8 or 23. New estimates copy it.
    hourly_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)  # the owner's own rate per hour (V2-9): only the margin of an object uses it
    vat_mode: Mapped[str | None] = mapped_column(String(8), nullable=True)
    vat_rate_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
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
        CheckConstraint("hourly_rate IS NULL OR hourly_rate > 0", name="ck_executor_profiles_hourly_rate"),
        CheckConstraint(
            "(vat_mode IS NULL AND vat_rate_percent IS NULL) OR (vat_mode = 'EXEMPT' AND vat_rate_percent IS NULL) "
            "OR (vat_mode = 'RATE' AND vat_rate_percent IN (8, 23))",
            name="ck_executor_profiles_vat",
        ),
    )
