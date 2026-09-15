"""Pydantic schemas for the per-surface work plan (Stage 10B).

Write schemas reject unknown fields; read schemas map from ORM attributes. The
plan carries no tenancy/price fields by design — the service resolves ownership
through the Surface chain and never snapshots prices. Each planned work embeds
a compact Price Book summary so the 10C UI can render a plan without one HTTP
request per row; market research data is deliberately excluded (not Work Plan
data).
"""
import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from app.models.checklist import QualityLevel, Substrate
from app.models.price_item import PriceCategory, PriceScope, PriceUnit


class OrderedPriceItemSelection(BaseModel):
    """One Price Book row ordered into the plan; list order defines position."""

    price_item_id: uuid.UUID

    model_config = ConfigDict(extra="forbid")


class SurfacePriceItemSummaryRead(BaseModel):
    """Smallest useful Price Book view embedded in a planned work.

    Mirrors the fields the estimate UI needs per row — no market evidence, no
    timestamps. Money stays a Decimal and serializes as a JSON string exactly
    like the Price Book API.
    """

    id: uuid.UUID
    code: str
    name_key: str | None = None
    display_name: str | None = None
    category: PriceCategory
    unit: PriceUnit
    price_scope: PriceScope
    price: Decimal | None
    currency: str
    is_archived: bool
    quality_level: QualityLevel | None = None

    model_config = ConfigDict(from_attributes=True)


class SurfacePlannedWorkRead(BaseModel):
    id: uuid.UUID
    work_plan_id: uuid.UUID
    price_item_id: uuid.UUID
    position: int
    price_item: SurfacePriceItemSummaryRead | None = None

    model_config = ConfigDict(from_attributes=True)


class SurfaceWorkPlanCreate(BaseModel):
    substrate: Substrate
    quality_target: QualityLevel | None = None
    planned_works: list[OrderedPriceItemSelection] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class SurfaceWorkPlanUpdate(BaseModel):
    substrate: Substrate | None = None
    quality_target: QualityLevel | None = None
    planned_works: list[OrderedPriceItemSelection] | None = None

    model_config = ConfigDict(extra="forbid")


class SurfaceWorkPlanUpsert(BaseModel):
    """PUT body for the Work Plan sub-resource (Stage 10B.2).

    ``price_item_ids`` is an ordered list and duplicates are meaningful (e.g.
    two coat rows of the same catalog item) — the service preserves them.
    """

    substrate: Substrate
    quality_target: QualityLevel | None = None
    price_item_ids: list[uuid.UUID] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class SurfaceWorkPlanRead(BaseModel):
    id: uuid.UUID
    surface_id: uuid.UUID
    substrate: Substrate
    quality_target: QualityLevel | None = None
    planned_works: list[SurfacePlannedWorkRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class SurfaceWorkPlanApplyResult(BaseModel):
    """Compact apply-to-room-walls response (Stage 10B.2).

    Enough for the future 10C confirmation toast ("Zastosowano do 3 ścian")
    without exposing Room/Inspection/Price Book objects.
    """

    source_surface_id: uuid.UUID
    target_count: int
    target_surface_ids: list[uuid.UUID] = Field(default_factory=list)
    targets: list[SurfaceWorkPlanRead] = Field(default_factory=list)