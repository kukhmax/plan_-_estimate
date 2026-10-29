"""The points and routes of a room (V2-10). A quantity goes out as a string with two places (`schemas/payment.py`)."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models.price_item import PriceCategory, PriceUnit
from app.schemas.payment import Out

Quantity = Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=2)]


class PointCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price_item_id: uuid.UUID
    quantity: Quantity
    note: str | None = Field(default=None, max_length=500)


class PointUpdate(BaseModel):
    """Only what is sent changes; `note: null` clears the note."""

    model_config = ConfigDict(extra="forbid")

    price_item_id: uuid.UUID | None = None
    quantity: Quantity | None = None
    note: str | None = Field(default=None, max_length=500)


class PointItemRead(BaseModel):
    """The price item of a row as the list shows it: the owner's name or the key of a built-in name, the unit, the price now."""

    id: uuid.UUID
    code: str
    name_key: str | None
    display_name: str | None
    category: PriceCategory
    unit: PriceUnit
    price: Out | None
    is_archived: bool


class PointRead(BaseModel):
    id: uuid.UUID
    room_id: uuid.UUID
    quantity: Out
    note: str | None
    item: PointItemRead
    source: str | None = None  # TRADE_LINK: carried over from the answer of a craftsman (the list marks it); None: typed by the owner
    created_at: datetime
    updated_at: datetime


class PointsResponse(BaseModel):
    items: list[PointRead]


class RoomPointCount(BaseModel):
    room_id: uuid.UUID
    count: int


class PointCountsResponse(BaseModel):
    items: list[RoomPointCount]


class SkippedPoint(BaseModel):
    point_id: uuid.UUID
    code: str  # POINT_ITEM_ARCHIVED | POINT_UNIT_INVALID


class AddToEstimateResponse(BaseModel):
    """What the addition did: the lines made, the rows that were in the estimate already, the rows that cannot go (and why)."""

    added: int
    already: int
    skipped: list[SkippedPoint]


class PointsPackResponse(BaseModel):
    created: int  # the items made now
    existing: int  # the items of the pack that the price book had already
