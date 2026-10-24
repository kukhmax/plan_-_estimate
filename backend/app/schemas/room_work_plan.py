"""Room work plan API schemas (V2-5; docs/V2_5_PLAN_RU.md)."""
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.checklist import QualityLevel, Substrate
from app.models.surface import SurfaceType

MAX_WORKS = 40


class RoomWorkPlanWrite(BaseModel):
    """PUT body: the ordered price rows for the walls and for the ceiling (duplicates are meaningful: two coats)."""

    model_config = ConfigDict(extra="forbid")

    substrate: Substrate
    quality_target: QualityLevel | None = None
    walls: list[uuid.UUID] = Field(default_factory=list, max_length=MAX_WORKS)
    ceiling: list[uuid.UUID] = Field(default_factory=list, max_length=MAX_WORKS)


class RoomWorkPlanRead(BaseModel):
    id: uuid.UUID
    room_id: uuid.UUID
    substrate: Substrate
    quality_target: QualityLevel | None
    walls: list[uuid.UUID]
    ceiling: list[uuid.UUID]
    updated_at: datetime | None = None


SurfaceState = Literal["NONE", "FOLLOWS", "OWN"]
Outcome = Literal["CREATED", "UPDATED", "SKIPPED_OWN", "SKIPPED_STARTED", "SKIPPED_EMPTY"]


class SurfacePlanState(BaseModel):
    surface_id: uuid.UUID
    name: str
    surface_type: SurfaceType
    state: SurfaceState
    started: bool


class SurfaceOutcome(BaseModel):
    surface_id: uuid.UUID
    name: str
    surface_type: SurfaceType
    outcome: Outcome


class RoomWorkPlanResponse(BaseModel):
    plan: RoomWorkPlanRead | None
    surfaces: list[SurfacePlanState]
    results: list[SurfaceOutcome] = Field(default_factory=list)
