"""Pydantic schemas for the per-surface work plan (Stage 10B).

Write schemas reject unknown fields; read schemas map from ORM attributes. The
plan carries no tenancy/price fields by design — the service resolves ownership
through the Surface chain and never snapshots prices. Each planned work embeds
a compact Price Book summary so the 10C UI can render a plan without one HTTP
request per row; market research data is deliberately excluded (not Work Plan
data).
"""
import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.checklist import QualityLevel, Substrate
from app.models.price_item import PriceCategory, PriceScope, PriceUnit
from app.models.work_execution import WorkExecutionStatus
from app.models.workflow_template import TemplateApplicationMode


def _unique_detach_keys(keys: list[uuid.UUID] | None) -> list[uuid.UUID] | None:
    """`confirm_execution_detach_keys` is a set (Stage 13H.4): a key listed
    twice is rejected (422) rather than silently collapsed; order is
    irrelevant to the server."""
    if keys is not None and len(set(keys)) != len(keys):
        raise ValueError("confirm_execution_detach_keys must not contain duplicates")
    return keys


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


class PlannedWorkExecutionRead(BaseModel):
    """Read-only execution state of one CURRENT occurrence (Stage 13H.3).

    No execution row serializes as NOT_STARTED with null timestamps.
    Timestamps are when the state was recorded in the application (server
    UTC), not proof of the physical moment. `ready_after` is derived on read
    (COMPLETED + a break: completed_at + current wait_after_hours), never
    stored. Never accepted in any write payload.
    """

    status: WorkExecutionStatus
    started_at: datetime | None = None
    completed_at: datetime | None = None
    ready_after: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class SurfaceWorkExecutionRead(PlannedWorkExecutionRead):
    """Response of the dedicated execution endpoint: the addressed
    occurrence's execution state."""

    occurrence_key: uuid.UUID


class SurfaceWorkExecutionTransition(BaseModel):
    """PATCH body of the dedicated execution endpoint (Stage 13H.3).

    Only the target status and the status the client last saw
    (`expected_status`, optimistic concurrency) -- timestamps and ready_after
    are always server-derived and cannot be sent.
    """

    status: WorkExecutionStatus
    expected_status: WorkExecutionStatus

    model_config = ConfigDict(extra="forbid")


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
    # Stage 13H.3: read-only; attached by the WorkPlan read path.
    execution: PlannedWorkExecutionRead

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


class TemplateApplicationIntent(BaseModel):
    """Provenance intent sent with a WorkPlan save (Stage 13C, D7).

    It records that the owner applied a workflow template to the draft being
    saved; it never applies anything itself -- the resulting occurrences are
    already in `planned_works`. Only identifiers are client-supplied: the
    template's code/name snapshot and `applied_at` are taken server-side from
    the owner's own template at save time.

    `application_id` is a UUID the client generates ONCE per apply action and
    reuses on every retry of the same save; it becomes the history record's id,
    so a retried save never records the application twice.
    """

    application_id: uuid.UUID
    template_id: uuid.UUID
    mode: TemplateApplicationMode
    steps_applied: int = Field(ge=1)

    model_config = ConfigDict(extra="forbid")


class ApplyTemplateRequest(BaseModel):
    """Server-side template application (Stage 13E.3).

    Only identifiers and the owner's choices are client-supplied; every
    materialized PriceItem, order, note and break comes from the server's own
    template. `expected_step_ids` is the exact ordered step list the preview
    showed (template version); `expected_occurrence_keys` is the exact ordered
    plan composition the owner confirmed replacing (REPLACE only).
    `application_id` is generated once per apply action and reused on retry.

    `selected_step_ids` (13E.5B-FIX.4, APPEND only) is the owner's final
    reviewed selection: the exact set of template step ids to materialize,
    required or optional. It lets the owner skip a required candidate whose
    operation is already in the plan. It never carries PriceItems: every id
    must be a step of the current template, order still comes from the
    template. When it is sent, `selected_optional_step_ids` must be empty;
    when omitted, the 13E.3 rule applies (all required + selected optional).
    """

    application_id: uuid.UUID
    template_id: uuid.UUID
    mode: TemplateApplicationMode
    selected_optional_step_ids: list[uuid.UUID] = Field(default_factory=list)
    selected_step_ids: list[uuid.UUID] | None = None
    expected_step_ids: list[uuid.UUID]
    expected_occurrence_keys: list[uuid.UUID] | None = None
    replace_confirmed: bool = False
    # Stage 13H.4: exact set of IN_PROGRESS/COMPLETED occurrence keys the
    # owner confirmed detaching (REPLACE). None = not sent (kept out of the
    # idempotency fingerprint, so older requests keep their fingerprints).
    confirm_execution_detach_keys: list[uuid.UUID] | None = None

    model_config = ConfigDict(extra="forbid")

    _unique_confirm = field_validator("confirm_execution_detach_keys")(_unique_detach_keys)


class TemplateApplicationRead(BaseModel):
    id: uuid.UUID
    template_id: uuid.UUID | None = None
    template_code: str
    template_name: str
    mode: TemplateApplicationMode
    steps_applied: int
    applied_at: datetime

    model_config = ConfigDict(from_attributes=True)


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
    # Stage 13C: optional provenance of template applications in this save.
    template_applications: list[TemplateApplicationIntent] = Field(default_factory=list)
    # Stage 13H.4: exact set of IN_PROGRESS/COMPLETED occurrence keys this
    # save may detach (removed from the plan; history kept). Empty = none.
    confirm_execution_detach_keys: list[uuid.UUID] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    _unique_confirm = field_validator("confirm_execution_detach_keys")(_unique_detach_keys)

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
    # Historical provenance (oldest first); snapshot, not current state.
    template_applications: list[TemplateApplicationRead] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class ApplyToRoomWallsRequest(BaseModel):
    """Optional body of apply-to-room-walls (Stage 13H.4). Omitted body =
    no confirmation. One flat set across all target walls: occurrence keys
    are globally unique, so a key identifies its wall unambiguously."""

    confirm_execution_detach_keys: list[uuid.UUID] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    _unique_confirm = field_validator("confirm_execution_detach_keys")(_unique_detach_keys)


class ExecutionDetachAffectedRead(BaseModel):
    """One entry of the 409 WORK_EXECUTION_DETACH_CONFIRMATION_REQUIRED
    `affected` list (Stage 13H.4): enough to render the confirmation (which
    wall, which numbered work, its PriceItem label and status) without the
    client reconstructing it from a possibly stale plan."""

    surface_id: uuid.UUID
    occurrence_key: uuid.UUID
    position: int
    status: WorkExecutionStatus
    price_item_id: uuid.UUID
    price_item_code: str
    price_item_name_key: str | None = None
    price_item_display_name: str | None = None

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


class ExecutionSnapshotItem(BaseModel):
    """One entry of the exact ordered source snapshot (Stage 13H.5B)."""

    occurrence_key: uuid.UUID
    status: WorkExecutionStatus

    model_config = ConfigDict(extra="forbid")


class BulkExecutionApplyRequest(BaseModel):
    """Apply body: the EXACT ordered snapshot of ALL current source
    occurrences (NOT_STARTED included) as returned by the preview. Any key,
    order, count or status difference at apply time is a 409."""

    expected_source: list[ExecutionSnapshotItem]

    model_config = ConfigDict(extra="forbid")

    @field_validator("expected_source")
    @classmethod
    def _unique_keys(cls, items: list[ExecutionSnapshotItem]) -> list[ExecutionSnapshotItem]:
        keys = [i.occurrence_key for i in items]
        if len(set(keys)) != len(keys):
            raise ValueError("expected_source must not repeat an occurrence_key")
        return items


class BulkExecutionWallRead(BaseModel):
    """Per target wall (occurrence counts, one bucket per source occurrence:
    changed + unchanged + unmatched + ambiguous == source occurrences)."""

    surface_id: uuid.UUID
    has_plan: bool
    changed: int
    unchanged: int
    unmatched: int
    ambiguous: int
    unmatched_price_item_ids: list[uuid.UUID] = Field(default_factory=list)
    ambiguous_price_item_ids: list[uuid.UUID] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class BulkExecutionResultRead(BaseModel):
    """Preview (`applied` false: what would happen now) and apply (`applied`
    true: what happened) share this shape; totals are sums over `walls`.
    `expected_source` is the canonical snapshot to send back on apply."""

    source_surface_id: uuid.UUID
    applied: bool
    expected_source: list[ExecutionSnapshotItem]
    changed: int
    unchanged: int
    unmatched: int
    ambiguous: int
    walls: list[BulkExecutionWallRead]
