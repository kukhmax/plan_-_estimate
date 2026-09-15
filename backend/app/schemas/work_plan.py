"""Pydantic schemas for the per-surface work plan (Stage 10B.1).

Write schemas reject unknown fields; read schemas map from ORM attributes. The
plan carries no tenancy/price fields by design — the service resolves ownership
through the Surface chain and never snapshots prices.
"""
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.checklist import QualityLevel, Substrate


class OrderedPriceItemSelection(BaseModel):
    """One Price Book row ordered into the plan; list order defines position."""

    price_item_id: uuid.UUID

    model_config = ConfigDict(extra="forbid")


class SurfacePlannedWorkRead(BaseModel):
    id: uuid.UUID
    work_plan_id: uuid.UUID
    price_item_id: uuid.UUID
    position: int

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


class SurfaceWorkPlanRead(BaseModel):
    id: uuid.UUID
    surface_id: uuid.UUID
    substrate: Substrate
    quality_target: QualityLevel | None = None
    planned_works: list[SurfacePlannedWorkRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)