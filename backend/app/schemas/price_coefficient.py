"""Price coefficient catalog API schemas (Stage 12C).

Money-like percentage values stay `Decimal` end-to-end (Pydantic v2
serializes them as a JSON string in the exact wire form, never a float).
Unknown fields are rejected (`extra="forbid"`) so a client can never smuggle
an immutable identity field (`code`, `owner_id`, `created_at`) or the archive
flag through create/update -- mirrors `app/schemas/price.py` exactly.
"""
from datetime import datetime
from decimal import Decimal
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.price_coefficient import CoefficientSelectionMode


class CoefficientOptionCreate(BaseModel):
    """`code` is always server-generated -- never accepted from the client."""

    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=255)
    percentage: Decimal
    is_base: bool = False


class CoefficientOptionUpdate(BaseModel):
    """Partial update; omitted fields are left unchanged by the service.

    Archival is a separate, explicit action (`/archive`, `/restore`), not a
    field here -- mirrors the dedicated Price Book archive/restore endpoints.
    """

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    percentage: Decimal | None = None
    is_base: bool | None = None


class CoefficientOptionRead(BaseModel):
    id: uuid.UUID
    group_id: uuid.UUID
    code: str
    name_key: str | None = None
    display_name: str | None = None
    percentage: Decimal
    is_base: bool
    position: int
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class CoefficientGroupCreate(BaseModel):
    """`code` and `selection_mode` are server-controlled -- `selection_mode`
    is always `SINGLE_SELECT` in Stage 12C, the only mode implemented."""

    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=255)


class CoefficientGroupUpdate(BaseModel):
    """Partial update; `code`/`selection_mode` are immutable on this path."""

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    position: int | None = None


class CoefficientGroupRead(BaseModel):
    id: uuid.UUID
    code: str
    name_key: str | None = None
    display_name: str | None = None
    selection_mode: CoefficientSelectionMode
    position: int
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    options: list[CoefficientOptionRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class CoefficientGroupListResponse(BaseModel):
    items: list[CoefficientGroupRead]
    total: int
