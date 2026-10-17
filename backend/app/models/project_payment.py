"""The settlements of an object (invoices and advances, IA-1): what the contractor invoiced, took from the client and spent on materials.

A register for the owner, not an accounting system: nothing here issues a legal invoice (VAT, KSeF), it only records what the owner did.
Money is `Decimal` (two places) and every total is made on the server (`domain/rules/payment_totals.py`).

`kind`: INVOICE (an invoice issued to the client), ADVANCE (an advance taken from the client), PAYMENT (a payment taken from the client,
optionally settling one invoice), EXPENSE (money spent on materials, with a receipt or an invoice kept as photos later). A record is archived,
never erased (it is accounting); it goes with its object (`ON DELETE CASCADE`).
"""
import enum
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    Uuid,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PaymentKind(str, enum.Enum):
    INVOICE = "INVOICE"
    ADVANCE = "ADVANCE"
    PAYMENT = "PAYMENT"
    EXPENSE = "EXPENSE"


class PaymentDocumentKind(str, enum.Enum):
    RECEIPT = "RECEIPT"
    INVOICE = "INVOICE"


class ExpenseCategory(str, enum.Enum):
    """What an expense was spent on (IA-6b); an expense made before the categories existed has none."""

    MATERIALS = "MATERIALS"
    TOOLS = "TOOLS"
    TRANSPORT = "TRANSPORT"
    SERVICES = "SERVICES"
    OTHER = "OTHER"


MONEY_IN_KINDS = (PaymentKind.ADVANCE.value, PaymentKind.PAYMENT.value)
CATEGORIES_SQL = ", ".join(f"'{category.value}'" for category in ExpenseCategory)


def _now() -> datetime:
    return datetime.now(UTC)


class ProjectPayment(Base):
    __tablename__ = "project_payments"
    __table_args__ = (
        CheckConstraint("kind IN ('INVOICE', 'ADVANCE', 'PAYMENT', 'EXPENSE')", name="ck_project_payments_kind"),
        CheckConstraint("amount_gross > 0", name="ck_project_payments_amount_positive"),
        CheckConstraint("amount_net IS NULL OR amount_net >= 0", name="ck_project_payments_net_not_negative"),
        CheckConstraint("vat_rate IS NULL OR (vat_rate >= 0 AND vat_rate <= 100)", name="ck_project_payments_vat_range"),
        CheckConstraint("length(trim(title)) > 0", name="ck_project_payments_title_not_blank"),
        CheckConstraint("document_kind IS NULL OR document_kind IN ('RECEIPT', 'INVOICE')", name="ck_project_payments_document_kind"),
        CheckConstraint("document_kind IS NULL OR kind = 'EXPENSE'", name="ck_project_payments_document_kind_only_expense"),
        CheckConstraint("counterparty IS NULL OR kind = 'EXPENSE'", name="ck_project_payments_counterparty_only_expense"),
        CheckConstraint(f"category IS NULL OR category IN ({CATEGORIES_SQL})", name="ck_project_payments_category"),
        CheckConstraint("category IS NULL OR kind = 'EXPENSE'", name="ck_project_payments_category_only_expense"),
        CheckConstraint("due_on IS NULL OR kind = 'INVOICE'", name="ck_project_payments_due_only_invoice"),
        CheckConstraint("settles_id IS NULL OR kind IN ('ADVANCE', 'PAYMENT')", name="ck_project_payments_settles_only_money_in"),
        CheckConstraint("settles_id IS NULL OR settles_id <> id", name="ck_project_payments_settles_not_self"),
        Index("ix_project_payments_project_kind", "project_id", "kind", "occurred_on"),
        Index("ix_project_payments_settles", "settles_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)  # what it is for
    number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    amount_gross: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    amount_net: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    vat_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    occurred_on: Mapped[date] = mapped_column(Date, nullable=False)
    due_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    settles_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("project_payments.id", ondelete="SET NULL"), nullable=True)
    counterparty: Mapped[str | None] = mapped_column(String(255), nullable=True)
    document_kind: Mapped[str | None] = mapped_column(String(8), nullable=True)
    category: Mapped[str | None] = mapped_column(String(16), nullable=True)  # an expense only (IA-6b)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)


class ProjectFinance(Base):
    """The agreed amount of an object: the total price agreed with the client for the whole work (one row per object, optional)."""

    __tablename__ = "project_finance"
    __table_args__ = (CheckConstraint("agreed_amount IS NULL OR agreed_amount > 0", name="ck_project_finance_agreed_positive"),)

    project_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("projects.id", ondelete="CASCADE"), primary_key=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    agreed_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="PLN", server_default="PLN")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now)
