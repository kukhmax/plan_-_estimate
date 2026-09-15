"""Price Book API schemas (Stage 9C).

Money stays a `Decimal` end-to-end: Pydantic v2 serializes it as a JSON string
in the fixed wire form supplied by the client (e.g. ``"45.50"``) — never a
float, never silently rounded. Unknown fields are rejected (``extra="forbid"``)
so a client can never smuggle an immutable identity field (``code``,
``owner_id``, ``created_at``) or the archive flag through create/update.
"""
from datetime import datetime
from decimal import Decimal
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.checklist import QualityLevel
from app.models.market_evidence import SourceType
from app.models.price_item import PriceCategory, PriceScope, PriceUnit


class PriceItemCreate(BaseModel):
    """Owner-authored catalog row; the semantic ``code`` is always server-generated."""

    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=255)
    category: PriceCategory
    unit: PriceUnit
    price: Decimal
    currency: str = Field(default="PLN", max_length=3)
    price_scope: PriceScope = PriceScope.LABOR
    quality_level: QualityLevel | None = None


class PriceItemUpdate(BaseModel):
    """Partial update; omitted fields are left unchanged by the service."""

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, max_length=255)
    category: PriceCategory | None = None
    unit: PriceUnit | None = None
    price: Decimal | None = None
    currency: str | None = Field(default=None, max_length=3)
    price_scope: PriceScope | None = None
    quality_level: QualityLevel | None = None


class PriceItemRead(BaseModel):
    id: uuid.UUID
    code: str
    name_key: str | None = None
    display_name: str | None = None
    category: PriceCategory
    unit: PriceUnit
    price: Decimal | None
    currency: str
    price_scope: PriceScope
    quality_level: QualityLevel | None = None
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PriceItemListResponse(BaseModel):
    items: list[PriceItemRead]
    total: int


class PriceSourceRead(BaseModel):
    id: uuid.UUID
    source_name: str
    source_type: SourceType
    source_url: str | None = None
    source_region: str | None = None
    quoted_price_min: Decimal | None = None
    quoted_price_max: Decimal | None = None
    quoted_price_single: Decimal | None = None
    quoted_unit: PriceUnit | None = None
    note: str | None = None
    checked_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PriceMarketReferenceRead(BaseModel):
    id: uuid.UUID
    region: str
    unit: PriceUnit
    currency: str
    market_min: Decimal
    market_max: Decimal
    reference_price: Decimal | None = None
    methodology_note: str | None = None
    checked_at: datetime
    sources: list[PriceSourceRead]

    model_config = ConfigDict(from_attributes=True)


class PriceMarketReferenceListResponse(BaseModel):
    items: list[PriceMarketReferenceRead]
    total: int