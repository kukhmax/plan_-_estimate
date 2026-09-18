"""Estimate API schemas (Stage 10E / 10E-corrections).

Money stays Decimal end-to-end — never float.
NULL unit_price ≠ 0.00: nullable Decimal serialises as JSON null.
Enums serialise as their string value (str enum mixin on model enums).
"""
from datetime import datetime
from decimal import Decimal
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.estimate import EstimateStatus, LineOrigin, QuantitySource
from app.models.price_item import PriceScope, PriceUnit


# ---------------------------------------------------------------------------
# Estimate list / summary
# ---------------------------------------------------------------------------

class EstimateSummaryRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    version: int
    status: EstimateStatus
    name: str | None = None
    total: Decimal | None = None
    currency: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EstimateListResponse(BaseModel):
    items: list[EstimateSummaryRead]
    total: int


# ---------------------------------------------------------------------------
# Estimate line — full detail (B / G)
# ---------------------------------------------------------------------------

class EstimateLineRead(BaseModel):
    id: uuid.UUID
    estimate_id: uuid.UUID
    origin: LineOrigin
    position: int
    description: str
    item_code: str | None = None
    unit: PriceUnit
    scope: PriceScope
    currency: str
    source_quantity: Decimal | None = None
    quantity: Decimal
    quantity_source: QuantitySource
    quantity_overridden: bool
    unit_price: Decimal | None = None
    price_override: bool
    amount: Decimal | None = None
    # Provenance IDs (snapshot)
    price_item_id: uuid.UUID | None = None
    plan_id: uuid.UUID | None = None
    planned_work_id: uuid.UUID | None = None
    surface_id: uuid.UUID | None = None
    room_id: uuid.UUID | None = None
    opening_id: uuid.UUID | None = None
    # Presentation metadata resolved live at read time (not stored in EstimateLine)
    room_name: str | None = None
    surface_name: str | None = None
    surface_type_value: str | None = None
    opening_name: str | None = None
    opening_type_value: str | None = None

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Estimate detail (single estimate + lines)
# ---------------------------------------------------------------------------

class EstimateRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    version: int
    status: EstimateStatus
    name: str | None = None
    total: Decimal | None = None
    currency: str
    lines: list[EstimateLineRead] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Regeneration preview / confirm — structured change entries (C6)
# ---------------------------------------------------------------------------

class LineChangeEntryRead(BaseModel):
    """One proposed or applied change entry in a regeneration diff."""
    change_type: str  # "ADDED" | "REMOVED" | "UPDATED"
    estimate_line_id: uuid.UUID | None = None
    planned_work_id: uuid.UUID
    surface_id: uuid.UUID | None = None
    opening_id: uuid.UUID | None = None
    item_code: str | None = None
    description: str
    unit: PriceUnit
    old_source_quantity: Decimal | None = None
    new_source_quantity: Decimal | None = None
    old_unit_price: Decimal | None = None
    new_unit_price: Decimal | None = None
    quantity_overridden: bool
    price_override: bool


class RegenerationPreviewResponse(BaseModel):
    added: int
    removed: int
    updated: int
    preserved_manual: int
    changes: list[LineChangeEntryRead] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Manual line creation (F)
# ---------------------------------------------------------------------------

class ManualLineCreate(BaseModel):
    description: str = Field(min_length=1, max_length=255)
    scope: PriceScope
    unit: PriceUnit
    quantity: Decimal
    unit_price: Decimal | None = None
    currency: str = Field(default="PLN", max_length=3)

    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Line PATCH (G) — update owner-controlled fields
# ---------------------------------------------------------------------------

class EstimateLineUpdate(BaseModel):
    """PATCH body for a draft line.

    Only fields present in model_fields_set are applied.

    quantity=null is rejected (NOT NULL in DB).
    unit_price=null marks the line as Do ustalenia (price_override=True, unit_price=NULL).
    unit_price=<value> sets a price override.
    reset_price_override=true restores unit_price from the current PriceBook and
        clears price_override. Rejected for MANUAL lines. Cannot be combined with
        a simultaneous unit_price assignment.

    reset_quantity_override=true restores quantity to source_quantity (or 0.000 if
        source_quantity is NULL) and clears quantity_overridden. Cannot be combined
        with a simultaneous quantity assignment.

    description is only writable on MANUAL lines.
    """
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    description: str | None = None
    reset_price_override: bool = False
    reset_quantity_override: bool = False

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def check_no_override_conflicts(self) -> "EstimateLineUpdate":
        if "unit_price" in self.model_fields_set and self.reset_price_override:
            raise ValueError(
                "Cannot set unit_price and reset_price_override simultaneously"
            )
        if "quantity" in self.model_fields_set and self.reset_quantity_override:
            raise ValueError(
                "Cannot set quantity and reset_quantity_override simultaneously"
            )
        return self
