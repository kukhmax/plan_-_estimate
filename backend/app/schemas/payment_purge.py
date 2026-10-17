"""Schemas of the archived settlement records and their final deletion (invoices and advances, IA-7)."""
import uuid
from datetime import date

from pydantic import BaseModel

from app.schemas.payment import Category, Kind, Out


class ArchivedPaymentItem(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    project_name: str
    kind: Kind
    title: str
    number: str | None
    amount_gross: Out
    occurred_on: date
    counterparty: str | None
    category: Category | None
    photos: int  # receipt / invoice photos of the record: they go with it


class ArchivedPaymentsResponse(BaseModel):
    items: list[ArchivedPaymentItem]
    total: int  # the list holds the first 200; the total is whole


class PaymentPurgePreview(BaseModel):
    """What deleting the archived record for good would remove -- computed by the server, no side effects."""

    target_id: uuid.UUID
    kind: Kind
    title: str
    archived: bool
    can_purge: bool
    tied_payments: int  # of an invoice: the payments that settled it stay and lose the link
    photos: int
    photo_files: int  # file sets (original, display, thumbnail) removed from the storage (those no other photo still uses)
    bytes: int
    annotations: int
    may_be_in_backups: bool


class PaymentPurgeResult(BaseModel):
    purged: bool
    photo_files: int
    storage_pending: int
