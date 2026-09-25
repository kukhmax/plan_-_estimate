"""Workflow template API schemas (Stage 13C).

Mirrors the Stage 12 catalog schemas: unknown fields are rejected
(`extra="forbid"`), so a client can never smuggle `owner_id`, `code`, the
archive flag or step ids through create/update. `code` is always
server-generated. Steps are an ordered list: list order IS the position
(same contract as WorkPlan `planned_works`), so duplicate or gapped positions
cannot be expressed. Templates carry no coefficients (D8).
"""
from datetime import datetime
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.checklist import QualityLevel, Substrate
from app.models.surface import SurfaceType
from app.schemas.work_plan import SurfacePriceItemSummaryRead


class WorkflowTemplateStepWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price_item_id: uuid.UUID
    is_optional: bool = False
    note: str | None = Field(default=None, max_length=4000)
    # Minimum technological/drying break AFTER this step, whole hours; null = none.
    wait_after_hours: int | None = Field(default=None, ge=1)


class WorkflowTemplateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4000)
    # Empty list = applies to any value of that dimension.
    applies_to_substrates: list[Substrate] = Field(default_factory=list)
    applies_to_quality: list[QualityLevel] = Field(default_factory=list)
    applies_to_surface_types: list[SurfaceType] = Field(default_factory=list)
    steps: list[WorkflowTemplateStepWrite] = Field(default_factory=list)


class WorkflowTemplateUpdate(BaseModel):
    """Partial metadata update; omitted fields are unchanged. Steps are
    replaced via `PUT …/steps`; archival via `/archive` and `/restore`."""

    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=255)
    # Omitted = unchanged; explicit null or blank = clear.
    description: str | None = Field(default=None, max_length=4000)
    applies_to_substrates: list[Substrate] | None = None
    applies_to_quality: list[QualityLevel] | None = None
    applies_to_surface_types: list[SurfaceType] | None = None
    position: int | None = None


class WorkflowTemplateStepsReplace(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: list[WorkflowTemplateStepWrite]


class WorkflowTemplateStepRead(BaseModel):
    id: uuid.UUID
    position: int
    price_item_id: uuid.UUID
    is_optional: bool
    note: str | None = None
    wait_after_hours: int | None = None
    # Includes is_archived / category so a UI can warn about unavailable steps.
    price_item: SurfacePriceItemSummaryRead | None = None

    model_config = ConfigDict(from_attributes=True)


class WorkflowTemplateRead(BaseModel):
    id: uuid.UUID
    code: str
    name_key: str | None = None
    display_name: str | None = None
    description: str | None = None
    applies_to_substrates: list[Substrate] = Field(default_factory=list)
    applies_to_quality: list[QualityLevel] = Field(default_factory=list)
    applies_to_surface_types: list[SurfaceType] = Field(default_factory=list)
    position: int
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    steps: list[WorkflowTemplateStepRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class WorkflowTemplateListResponse(BaseModel):
    items: list[WorkflowTemplateRead]
    total: int
