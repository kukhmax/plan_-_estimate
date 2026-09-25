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

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.checklist import QualityLevel, Substrate
from app.models.price_item import PriceCategory, PriceScope, PriceUnit


class OrderedPriceItemSelection(BaseModel):
    """One Price Book row ordered into the plan; list order defines position.

    `coefficient_option_ids` (Stage 12D) selects zero or more
    `CoefficientOption` rows to assign to THIS SPECIFIC occurrence -- never
    to the `PriceItem` itself, so two duplicate occurrences of the same
    Price Book row may carry independent selections. Defaults to an empty
    list, so every pre-Stage-12D caller/test that constructs this schema
    without the field is unaffected.

    `occurrence_key` (Stage 13B, D13) echoes the stable logical identity of an
    EXISTING occurrence of this plan, so it survives the full-replace save;
    omit it for a new occurrence and the server generates one. Keys are never
    client-generated. `wait_after_hours` (D9) is the optional technological
    break after this occurrence, in whole hours (>= 1; omitted = none).
    """

    price_item_id: uuid.UUID
    coefficient_option_ids: list[uuid.UUID] = Field(default_factory=list)
    occurrence_key: uuid.UUID | None = None
    wait_after_hours: int | None = Field(default=None, ge=1)

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


class PlannedWorkCoefficientOptionRead(BaseModel):
    """One selected coefficient option on a planned-work occurrence
    (Stage 12D). Denormalized just enough to render without a separate
    catalog lookup (`group_code` via `CoefficientOption.group_code`) --
    never the whole catalog (Stage 12 architecture Sec 5). No percentage
    arithmetic is performed anywhere in this schema; Stage 12E owns that.
    """

    id: uuid.UUID
    group_id: uuid.UUID
    group_code: str
    code: str
    display_name: str | None = None
    percentage: Decimal
    is_base: bool

    model_config = ConfigDict(from_attributes=True)


class SurfacePlannedWorkRead(BaseModel):
    id: uuid.UUID
    work_plan_id: uuid.UUID
    price_item_id: uuid.UUID
    position: int
    occurrence_key: uuid.UUID
    wait_after_hours: int | None = None
    price_item: SurfacePriceItemSummaryRead | None = None
    coefficient_options: list[PlannedWorkCoefficientOptionRead] = Field(
        default_factory=list
    )

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
    """PUT body for the Work Plan sub-resource (Stage 10B.2 / 12D).

    ``price_item_ids`` is the original, coefficient-less contract: an
    ordered list of bare ids, duplicates meaningful (e.g. two coat rows of
    the same catalog item). Every existing client sends this field and MUST
    keep working unchanged (Stage 12 architecture: no frontend change
    required in 12D) -- it is equivalent to sending ``planned_works`` with
    an empty ``coefficient_option_ids`` on every entry.

    ``planned_works`` (Stage 12D) is the richer, optional replacement that
    additionally carries each occurrence's coefficient selection. A request
    provides EITHER field, never both non-empty at once (ambiguous intent is
    rejected rather than silently preferring one).
    """

    substrate: Substrate
    quality_target: QualityLevel | None = None
    price_item_ids: list[uuid.UUID] = Field(default_factory=list)
    planned_works: list[OrderedPriceItemSelection] | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _check_exclusive_selection(self) -> "SurfaceWorkPlanUpsert":
        if self.planned_works is not None and self.price_item_ids:
            raise ValueError(
                "provide either price_item_ids (legacy) or planned_works "
                "(supports coefficients), not both"
            )
        return self


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