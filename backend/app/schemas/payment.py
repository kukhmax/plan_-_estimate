"""Settlements of an object (invoices and advances, IA-1): invoices issued to the client, money taken from the client, expenses on materials."""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

from app.schemas.client_id import ClientId

_CENT = Decimal("0.01")


def _two_places(value: Decimal) -> str:
    """Money goes out as a string with exactly two places, whatever the database returned ("40000.00", never "40000" or "0")."""
    return format(value.quantize(_CENT), "f")


# what the server sends: a Decimal as a string with two places
Out = Annotated[Decimal, PlainSerializer(_two_places, return_type=str, when_used="json")]

Money = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=2)]
NetMoney = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
VatRate = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]

Kind = Literal["INVOICE", "ADVANCE", "PAYMENT", "EXPENSE"]
DocumentKind = Literal["RECEIPT", "INVOICE"]
Category = Literal["MATERIALS", "TOOLS", "TRANSPORT", "SERVICES", "OTHER"]
InvoiceState = Literal["PAID", "PARTIAL", "OVERDUE", "OPEN"]


class PaymentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: ClientId
    kind: Kind
    title: str = Field(min_length=1, max_length=500)  # what it is for
    amount_gross: Money
    occurred_on: date
    number: str | None = Field(default=None, max_length=64)
    amount_net: NetMoney | None = None
    vat_rate: VatRate | None = None
    due_on: date | None = None
    settles_id: uuid.UUID | None = None
    counterparty: str | None = Field(default=None, max_length=255)
    document_kind: DocumentKind | None = None
    category: Category | None = None  # an expense only
    note: str | None = Field(default=None, max_length=4000)


class PaymentUpdate(BaseModel):
    """Only the fields that are sent change; the kind never does."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=500)
    amount_gross: Money | None = None
    occurred_on: date | None = None
    number: str | None = Field(default=None, max_length=64)
    amount_net: NetMoney | None = None
    vat_rate: VatRate | None = None
    due_on: date | None = None
    settles_id: uuid.UUID | None = None
    counterparty: str | None = Field(default=None, max_length=255)
    document_kind: DocumentKind | None = None
    category: Category | None = None
    note: str | None = Field(default=None, max_length=4000)


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    kind: Kind
    title: str
    number: str | None
    amount_gross: Out
    amount_net: Out | None
    vat_rate: Out | None
    occurred_on: date
    due_on: date | None
    settles_id: uuid.UUID | None
    counterparty: str | None
    document_kind: DocumentKind | None
    category: Category | None
    note: str | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    # an invoice only: how much of it the payments tied to it have settled
    settled: Out | None = None
    remaining: Out | None = None
    state: InvoiceState | None = None


class CategoryTotalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    category: Category | None  # null: the expenses that have none (made before the categories existed)
    total: Out


class PaymentSummary(BaseModel):
    invoiced: Out
    received: Out
    expenses: Out
    invoiced_unpaid: Out
    to_receive: Out | None
    result: Out
    expenses_by_category: list[CategoryTotalRead]  # the parts of `expenses`: only the categories that have any


class PaymentListResponse(BaseModel):
    items: list[PaymentRead]
    total: int
    summary: PaymentSummary
    agreed_amount: Out | None


class AgreedSuggestionRead(BaseModel):
    amount: Out
    estimate_id: uuid.UUID
    estimate_version: int
    status: str  # ACCEPTED | FINAL


class FinanceRead(BaseModel):
    agreed_amount: Out | None
    currency: str
    suggestion: AgreedSuggestionRead | None


class FinanceWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agreed_amount: Money | None = None  # null clears it
