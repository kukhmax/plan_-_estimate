"""Estimate domain service (Stage 10D / 12E).

Implements generation, regeneration, totals, version sequencing, and FINAL
validation for the Estimate aggregate. No public API routes here (Stage 10E).

Key invariants enforced:
- Surface.net_area is never modified (quantity is read-only at generation)
- Reveal totals are read from opening geometry, never merged into wall area
- EstimateLine snapshot fields are written once and never re-read from PriceBook
  or geometry post-creation
- FINAL/ACCEPTED documents are never silently regenerated
- Manual lines survive DRAFT regeneration untouched
- Owner-set quantity and price overrides survive DRAFT regeneration

Stage 12E integrates Stage 12D planned-work coefficient assignments into
this SAME engine -- no second pricing system. For a PLANNED_WORK occurrence
with a non-empty coefficient selection, `unit_price` (when not manually
overridden) is `PriceItem.price` (the "base") adjusted by the ADDITIVE sum
of the selected percentages, never compounded:

    effective = base * (1 + sum(percentages) / 100)

`base_unit_price`/`coefficient_snapshot` on EstimateLine record the exact
facts used to compute that `effective` value, so a historical Estimate stays
explainable after the live catalog changes. See `_resolve_occurrence_pricing`
and `_calculate_effective_unit_price` below for the arithmetic, and
`docs/stage-12-architecture.md` for the full canonical contract.
"""
import uuid
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.exceptions import (
    EstimateDraftExistsError,
    EstimateNotFoundError,
    EstimateStateError,
    EstimateValidationError,
    PriceItemNotFoundError,
    ProjectNotFoundError,
)
from app.domain.rules.room_geometry import (
    AREA_PRECISION,
    calculate_plane_base_area,
    calculate_plane_totals,
    calculate_reveal,
    calculate_segment_area,
    calculate_surface_gross_area,
    calculate_wall_net_area,
)
from app.models.area_segment import AreaPlane, AreaSegment
from app.models.estimate import (
    Estimate,
    EstimateLine,
    EstimateStatus,
    LineOrigin,
    QuantitySource,
)
from app.models.opening import Opening, OpeningType
from app.models.opening_reveal_planned_work import (
    OpeningRevealPlannedWork,
    OpeningRevealPlannedWorkCoefficientAssignment,
)
from app.models.price_coefficient import CoefficientOption
from app.models.price_item import PriceCategory, PriceItem, PriceScope, PriceUnit
from app.models.project import Project
from app.models.room import Room
from app.models.surface import Surface, SurfaceType
from app.models.workflow_template import (
    SurfaceWorkPlanTemplateApplication,
    TemplateApplicationMode,
)
from app.models.work_plan import (
    SurfacePlannedWork,
    SurfacePlannedWorkCoefficientAssignment,
    SurfaceWorkPlan,
)

_AMOUNT_PRECISION = Decimal("0.01")


@dataclass
class LineChangeEntry:
    """One proposed or applied change in a regeneration diff (C6)."""

    change_type: str  # "ADDED" | "REMOVED" | "UPDATED"
    estimate_line_id: uuid.UUID | None
    planned_work_id: uuid.UUID
    surface_id: uuid.UUID | None
    opening_id: uuid.UUID | None
    item_code: str | None
    description: str
    unit: object  # PriceUnit — avoid circular import
    old_source_quantity: Decimal | None
    new_source_quantity: Decimal | None
    old_unit_price: Decimal | None
    new_unit_price: Decimal | None
    quantity_overridden: bool
    price_override: bool
    # Stage 12E: coefficient/base-price provenance for this change (Sec 15).
    old_base_unit_price: Decimal | None = None
    new_base_unit_price: Decimal | None = None
    old_coefficient_snapshot: list[dict] | None = None
    new_coefficient_snapshot: list[dict] | None = None
    # Presentation-only provenance (Stage 10G.3B follow-up), resolved live from
    # current DB records analogous to EstimateLineRead's enrichment — never
    # part of the change identity. surface_id/opening_id/planned_work_id above
    # remain the authoritative provenance IDs; these are display labels only,
    # nullable because a REMOVED entry's referenced Surface/Opening may no
    # longer exist.
    room_name: str | None = None
    surface_name: str | None = None
    surface_type_value: str | None = None
    opening_name: str | None = None
    opening_type_value: str | None = None


@dataclass
class RegenerationResult:
    """Summary of changes applied during a DRAFT regeneration."""

    added: int = 0
    updated: int = 0
    removed: int = 0
    preserved_manual: int = 0
    lines: list[EstimateLine] = field(default_factory=list)
    changes: list[LineChangeEntry] = field(default_factory=list)


def _item_description(item: PriceItem) -> str:
    """Resolve the display label for the snapshot (display_name > name_key > code)."""
    if item.display_name:
        return item.display_name
    if item.name_key:
        return item.name_key
    return item.code


def _compute_amount(
    quantity: Decimal, unit_price: Decimal | None
) -> Decimal | None:
    if unit_price is None:
        return None
    return (quantity * unit_price).quantize(_AMOUNT_PRECISION, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Stage 12E — coefficient pricing
#
# Percentages are ADDITIVE relative to the base price, never compounded:
#   effective = base * (1 + sum(selected percentages) / 100)
# All arithmetic stays exact Decimal; the effective unit price is quantized
# ONCE, at the end, to the same 0.01 precision as every other money value in
# this module. No individual coefficient, and no intermediate percentage
# sum, is ever separately rounded.
# ---------------------------------------------------------------------------

def _coefficient_label(name_key: str | None, display_name: str | None, code: str) -> str:
    """Mirrors `_item_description`'s precedence (display_name > name_key > code)."""
    if display_name:
        return display_name
    if name_key:
        return name_key
    return code


def _serialize_coefficient_option(option: "CoefficientOption") -> dict:
    """One immutable snapshot entry -- Decimal-safe (percentage stored as a
    string, never through float) and independent of the live catalog: a
    later rename/percentage-change/archive of this exact option never
    mutates an already-generated line's historical explanation."""
    group = option.group
    return {
        "group_id": str(group.id),
        "group_code": group.code,
        "group_name": _coefficient_label(group.name_key, group.display_name, group.code),
        "option_id": str(option.id),
        "option_code": option.code,
        "option_name": _coefficient_label(option.name_key, option.display_name, option.code),
        "percentage": str(option.percentage),
        "is_base": option.is_base,
    }


def _build_coefficient_snapshot(options: list["CoefficientOption"]) -> list[dict]:
    """Deterministic order (mirrors `SurfacePlannedWork.coefficient_options` /
    `OpeningRevealPlannedWork.coefficient_options`, which already sort by
    group.position/option.position/id) -- ``options`` is expected pre-sorted."""
    return [_serialize_coefficient_option(o) for o in options]


def _aggregate_percentage(options: list["CoefficientOption"]) -> Decimal:
    total = Decimal("0")
    for option in options:
        total += option.percentage
    return total


def _calculate_effective_unit_price(
    base_price: Decimal | None,
    options: list["CoefficientOption"],
    *,
    item_code: str | None = None,
) -> Decimal | None:
    """Apply the additive coefficient formula to a base price.

    NULL base stays NULL (Sec 9) -- coefficients never turn an unresolved
    price into a resolved one, and the aggregate-validity check below never
    runs for a NULL base since no arithmetic is being performed at all. A
    resolved base of exactly 0.00 (Sec 10) is still checked: 0 times any
    multiplier is 0, but a corrupt aggregate (< -100%) is rejected here
    regardless of the current base value, so a catalog misconfiguration is
    caught even while the base happens to be zero or unset-then-set-later.
    """
    if base_price is None:
        return None
    total_pct = _aggregate_percentage(options)
    multiplier = Decimal("1") + (total_pct / Decimal("100"))
    if multiplier < 0:
        raise EstimateValidationError(
            f"Aggregate coefficient adjustment of {total_pct}% on price item "
            f"{item_code or '?'} would produce a negative effective unit "
            "price; the sum of selected coefficient percentages must not be "
            "below -100%."
        )
    return (base_price * multiplier).quantize(_AMOUNT_PRECISION, rounding=ROUND_HALF_UP)


def _resolve_occurrence_pricing(
    item: "PriceItem", options: list["CoefficientOption"]
) -> tuple[Decimal | None, Decimal | None, list[dict]]:
    """Return (base_unit_price, effective_unit_price, coefficient_snapshot)
    for one planned-work occurrence. Defense-in-depth (Sec 11): a
    coefficient-bearing occurrence whose PriceItem is not LABOR-scoped is an
    impossible state under normal Stage 12D validation (assignment is
    LABOR-only at write time) but could arise if the item's price_scope was
    edited afterward via the Price Book -- raised as a domain integrity
    error rather than silently priced.
    """
    if options and item.price_scope != PriceScope.LABOR:
        raise EstimateValidationError(
            f"Price item {item.code} has price_scope={item.price_scope.value} "
            "but carries a coefficient assignment; coefficient pricing is "
            "LABOR-only (data integrity violation)"
        )
    base = item.price
    snapshot = _build_coefficient_snapshot(options)
    effective = _calculate_effective_unit_price(base, options, item_code=item.code)
    return base, effective, snapshot


def _snapshot_would_change(
    line: "EstimateLine",
    item: "PriceItem",
    new_source_qty: Decimal | None,
    qty_source: "QuantitySource",
    new_base_price: Decimal | None,
    new_effective_price: Decimal | None,
    new_snapshot: list[dict],
) -> bool:
    """Return True if regeneration would change any generated (non-override) field.

    base_unit_price/coefficient_snapshot are compared unconditionally (even
    for a price_override=True line): they represent the live pricing
    configuration, independent of whatever effective price the owner
    currently pins (Sec 18) -- so preview can flag "the underlying
    configuration changed" without ever implying the owner's override would
    be silently replaced. The final unit_price comparison stays gated by
    price_override exactly as before.
    """
    if new_source_qty != line.source_quantity:
        return True
    if qty_source != line.quantity_source:
        return True
    if _item_description(item) != line.description:
        return True
    if item.unit != line.unit:
        return True
    if item.price_scope != line.scope:
        return True
    if item.currency != line.currency:
        return True
    if new_base_price != line.base_unit_price:
        return True
    if new_snapshot != (line.coefficient_snapshot or []):
        return True
    if not line.price_override and new_effective_price != line.unit_price:
        return True
    return False


def _reveal_totals(opening: Opening) -> tuple[Decimal | None, Decimal | None]:
    """Return (total_length, total_area) for a reveal-enabled opening, else (None, None)."""
    if (
        not opening.reveal_enabled
        or opening.reveal_depth is None
        or opening.reveal_depth <= 0
    ):
        return None, None
    result = calculate_reveal(
        width=opening.width,
        height=opening.height,
        depth=opening.reveal_depth,
        left=opening.reveal_left,
        right=opening.reveal_right,
        top=opening.reveal_top,
        bottom=opening.reveal_bottom,
        quantity=opening.quantity,
    )
    if result is None:
        return None, None
    return result.total_length, result.total_area


def _resolve_reveal_quantity(
    item: "PriceItem", opening: Opening
) -> tuple[Decimal | None, "QuantitySource"]:
    """Quantity source for one opening-reveal planned-work occurrence.

    LM takes the opening's total reveal length, M2 its total reveal area.
    When that geometry cannot be derived (e.g. reveals enabled but no side
    selected, or missing depth), the quantity is unresolved (MANUAL, NULL) --
    never a REVEAL_* source with a 0.000 placeholder, which the finalize
    check would accept as a real zero.
    """
    total_length, total_area = _reveal_totals(opening)
    if item.unit == PriceUnit.LM and total_length is not None:
        return total_length, QuantitySource.REVEAL_LENGTH
    if item.unit == PriceUnit.M2 and total_area is not None:
        return total_area, QuantitySource.REVEAL_AREA
    return None, QuantitySource.MANUAL


def _resolve_surface_quantity(
    item: "PriceItem", net_area: Decimal | None
) -> tuple[Decimal | None, "QuantitySource"]:
    """Quantity source for one Surface planned-work occurrence.

    Reveal work (stable `PriceCategory.REVEAL`, never display text) is
    planned per opening (Stage 10 D19), where each opening's own reveal
    geometry and coefficients apply. A legacy reveal occurrence left on a
    Surface plan stays unresolved (MANUAL, NULL) for every unit -- never the
    wall's net area and never an aggregate that could silently double-count
    per-opening reveal lines -- so the owner resolves it explicitly and
    finalization is blocked until then. Every other item keeps the Stage 10
    rule: M2 from the surface net area, anything else unresolved.
    """
    if item.category == PriceCategory.REVEAL:
        return None, QuantitySource.MANUAL
    if item.unit == PriceUnit.M2:
        return net_area, QuantitySource.SURFACE_NET_AREA
    return None, QuantitySource.MANUAL


def _match_existing_lines(
    existing_by_pwid: dict[uuid.UUID, "EstimateLine"],
    current: list[tuple[uuid.UUID, tuple]],
) -> dict[uuid.UUID, "EstimateLine"]:
    """Pair current planned-work occurrences with existing PLANNED_WORK lines.

    `current` is [(occurrence id, logical key)] in generation order, where the
    logical key is (surface_id, opening_id or None, price_item_id).

    Occurrence ids are not durable: every WorkPlan / reveal-work save is a full
    replace that recreates the rows (Stage 10 / 12D Option C). Matching only by
    id therefore dropped every owner override (price and quantity) the moment
    the plan was re-saved, e.g. to change a coefficient. Pairing is:

    1. exact occurrence id (the plan was not re-saved since the line was made);
    2. otherwise the same logical key, duplicates paired by order -- the k-th
       unmatched current occurrence of a key takes the k-th unmatched existing
       line of that key (by estimate position), so duplicates never collapse.
    """
    matched: dict[uuid.UUID, EstimateLine] = {}
    used: set[uuid.UUID] = set()
    for work_id, _key in current:
        line = existing_by_pwid.get(work_id)
        if line is not None:
            matched[work_id] = line
            used.add(line.id)
    pool: dict[tuple, list[EstimateLine]] = {}
    for line in sorted(existing_by_pwid.values(), key=lambda ln: ln.position):
        if line.id in used:
            continue
        pool.setdefault((line.surface_id, line.opening_id, line.price_item_id), []).append(line)
    for work_id, key in current:
        if work_id in matched:
            continue
        candidates = pool.get(key)
        if candidates:
            matched[work_id] = candidates.pop(0)
    return matched


def _is_surface_line(line: "EstimateLine") -> bool:
    """A Surface PLANNED_WORK line (plan header set, no opening). Reveal lines
    have `plan_id` NULL and an `opening_id`; they keep Stage 12 matching."""
    return line.opening_id is None and line.plan_id is not None


def _match_surface_lines(
    existing: list["EstimateLine"],
    current: list[tuple[uuid.UUID, uuid.UUID, uuid.UUID, tuple]],
    legacy_blocked_plan_ids: set[uuid.UUID],
) -> dict[uuid.UUID, "EstimateLine"]:
    """Pair current Surface occurrences with existing Surface PLANNED_WORK
    lines (Stage 13E.2B occurrence identity).

    `current` is [(occurrence id, occurrence_key, plan id, (surface_id,
    price_item_id))] in generation order. Precedence:

    1. exact occurrence id (the plan was not re-saved since the line was
       made or last regenerated);
    2. the same `occurrence_key` -- the same logical work even though an
       ordinary full-replace save recreated its row. A KEYED line never goes
       further: a different key is different work, so its overrides never
       migrate to it, whatever the surface/PriceItem/order;
    3. legacy fallback, only for lines with NO key (pre-0028) on plans without
       a template REPLACE record: the Stage 12 logical key (surface,
       PriceItem), duplicates paired by line position / generation order.
       Regeneration then stores the key, so legacy lines converge to step 2.
    """
    matched: dict[uuid.UUID, EstimateLine] = {}
    used: set[uuid.UUID] = set()
    by_work_id = {line.planned_work_id: line for line in existing}
    for work_id, _key, _plan_id, _logical in current:
        line = by_work_id.get(work_id)
        if line is not None and line.id not in used:
            matched[work_id] = line
            used.add(line.id)
    by_key = {
        line.occurrence_key: line
        for line in existing
        if line.occurrence_key is not None and line.id not in used
    }
    for work_id, key, _plan_id, _logical in current:
        if work_id in matched:
            continue
        line = by_key.get(key)
        if line is not None and line.id not in used:
            matched[work_id] = line
            used.add(line.id)
    pool: dict[tuple, list[EstimateLine]] = {}
    for line in sorted(existing, key=lambda ln: ln.position):
        if (
            line.id in used
            or line.occurrence_key is not None
            or line.plan_id in legacy_blocked_plan_ids
        ):
            continue
        pool.setdefault((line.surface_id, line.price_item_id), []).append(line)
    for work_id, _key, plan_id, logical in current:
        if work_id in matched or plan_id in legacy_blocked_plan_ids:
            continue
        candidates = pool.get(logical)
        if candidates:
            line = candidates.pop(0)
            matched[work_id] = line
            used.add(line.id)
    return matched


class EstimateService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _assert_project_owned(
        self, project_id: uuid.UUID, owner_id: uuid.UUID
    ) -> Project:
        stmt = select(Project).where(
            Project.id == project_id, Project.owner_id == owner_id
        )
        project = (await self.db.execute(stmt)).scalar_one_or_none()
        if project is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")
        return project

    async def _lock_project(
        self, project_id: uuid.UUID, owner_id: uuid.UUID
    ) -> Project:
        """Acquire a row-level exclusive lock on the Project row.

        Used during Estimate generation to serialize concurrent requests
        for the same project. The lock is held until the enclosing transaction
        commits, ensuring that DRAFT-existence checks and version calculation
        cannot interleave with a concurrent generation for the same project.
        Different projects use different row locks and do not block each other.
        """
        stmt = (
            select(Project)
            .where(Project.id == project_id, Project.owner_id == owner_id)
            .with_for_update()
        )
        project = (await self.db.execute(stmt)).scalar_one_or_none()
        if project is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")
        return project

    async def _load_price_item(
        self,
        price_item_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> "PriceItem":
        """Load a PriceItem by id, scoped to owner. Raises EstimateValidationError if missing."""
        stmt = select(PriceItem).where(
            PriceItem.id == price_item_id,
            PriceItem.owner_id == owner_id,
        )
        item = (await self.db.execute(stmt)).scalar_one_or_none()
        if item is None:
            raise EstimateValidationError(
                f"Price item {price_item_id} no longer exists; cannot reset price override"
            )
        return item

    async def _load_current_occurrence(
        self, line: "EstimateLine"
    ) -> tuple["PriceItem", list["CoefficientOption"]] | None:
        """Resolve the LIVE Surface/Reveal planned-work occurrence (and its
        current PriceItem + coefficient selection) referenced by an
        EstimateLine's provenance -- used by reset_price_override (Sec 19)
        so a reset always derives from CURRENT live pricing, not a stale
        snapshot.

        Returns None when there is no occurrence to resolve: a PRICE_BOOK/
        MANUAL line (`planned_work_id` is NULL by construction, Sec 22-23),
        or a Surface/Reveal occurrence whose id no longer exists because its
        WorkPlan/Reveal was edited since this line was generated -- Stage
        10/12D occurrence ids are not durable across an edit, so the old id
        being gone is an honest, expected outcome, not an error. Callers
        fall back to a plain PriceItem reload (pre-12E behavior) in that case.
        """
        if line.planned_work_id is None:
            return None
        if line.opening_id is not None:
            stmt = (
                select(OpeningRevealPlannedWork)
                .where(OpeningRevealPlannedWork.id == line.planned_work_id)
                .options(
                    selectinload(OpeningRevealPlannedWork.price_item),
                    selectinload(OpeningRevealPlannedWork.coefficient_assignments)
                    .selectinload(
                        OpeningRevealPlannedWorkCoefficientAssignment.coefficient_option
                    )
                    .selectinload(CoefficientOption.group),
                )
            )
        else:
            options = (
                selectinload(SurfacePlannedWork.price_item),
                selectinload(SurfacePlannedWork.coefficient_assignments)
                .selectinload(SurfacePlannedWorkCoefficientAssignment.coefficient_option)
                .selectinload(CoefficientOption.group),
            )
            stmt = (
                select(SurfacePlannedWork)
                .where(SurfacePlannedWork.id == line.planned_work_id)
                .options(*options)
            )
            work = (await self.db.execute(stmt)).scalar_one_or_none()
            if (
                work is None
                and line.occurrence_key is not None
                and line.surface_id is not None
            ):
                # Stage 13E.2B: the row was recreated by an ordinary save; the
                # same logical occurrence is found by its key, confined to the
                # line's own surface (owner context is the estimate's project).
                stmt = (
                    select(SurfacePlannedWork)
                    .join(
                        SurfaceWorkPlan,
                        SurfacePlannedWork.work_plan_id == SurfaceWorkPlan.id,
                    )
                    .where(
                        SurfacePlannedWork.occurrence_key == line.occurrence_key,
                        SurfaceWorkPlan.surface_id == line.surface_id,
                    )
                    .options(*options)
                )
                work = (await self.db.execute(stmt)).scalar_one_or_none()
            if work is None:
                return None
            return work.price_item, work.coefficient_options
        work = (await self.db.execute(stmt)).scalar_one_or_none()
        if work is None:
            return None
        return work.price_item, work.coefficient_options

    async def _fetch_estimate(
        self,
        estimate_id: uuid.UUID,
        owner_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
    ) -> Estimate:
        conditions = [Estimate.id == estimate_id, Estimate.owner_id == owner_id]
        if project_id is not None:
            conditions.append(Estimate.project_id == project_id)
        stmt = (
            select(Estimate)
            .where(*conditions)
            .options(selectinload(Estimate.lines))
            .execution_options(populate_existing=True)
        )
        est = (await self.db.execute(stmt)).scalar_one_or_none()
        if est is None:
            raise EstimateNotFoundError(f"Estimate {estimate_id} not found")
        return est

    async def _draft_for_project(
        self, project_id: uuid.UUID, owner_id: uuid.UUID
    ) -> Estimate | None:
        stmt = (
            select(Estimate)
            .where(
                Estimate.project_id == project_id,
                Estimate.owner_id == owner_id,
                Estimate.status == EstimateStatus.DRAFT,
            )
            .options(selectinload(Estimate.lines))
            .execution_options(populate_existing=True)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _next_version(
        self, project_id: uuid.UUID, owner_id: uuid.UUID
    ) -> int:
        stmt = select(func.max(Estimate.version)).where(
            Estimate.project_id == project_id,
            Estimate.owner_id == owner_id,
        )
        max_v = (await self.db.execute(stmt)).scalar_one_or_none()
        return (max_v or 0) + 1

    async def _surface_net_area(self, surface: Surface) -> Decimal | None:
        """Compute a surface's authoritative M2 area, source depending on type.

        WALL: gross (width x height) minus active opening deductions.
        FLOOR/CEILING (canonical plane surfaces, Stage 10C.1A): these never
        store width/height, so gross/opening-deduction geometry does not
        apply. Their authoritative area is the same Room-level plane
        calculation the Surface UI already displays as "Razem" — Room.length
        x Room.width base plus active AreaSegment ADD/SUBTRACT adjustments
        (see AreaSegmentService._plane_summaries) — never door/window
        openings, which are WALL-only.
        """
        if surface.surface_type in (SurfaceType.FLOOR, SurfaceType.CEILING):
            return await self._plane_net_area(surface.room_id, surface.surface_type)

        gross = calculate_surface_gross_area(
            surface.surface_type, surface.width, surface.height
        )
        if gross is None:
            return None
        deduction_stmt = select(
            func.coalesce(
                func.sum(Opening.width * Opening.height * Opening.quantity), 0
            )
        ).where(
            Opening.surface_id == surface.id,
            Opening.is_archived.is_(False),
        )
        deduction = Decimal(
            (await self.db.execute(deduction_stmt)).scalar_one()
        ).quantize(AREA_PRECISION)
        net = calculate_wall_net_area(gross, deduction)
        return net

    async def _plane_net_area(
        self, room_id: uuid.UUID, surface_type: SurfaceType
    ) -> Decimal | None:
        """Authoritative FLOOR/CEILING net area — mirrors
        AreaSegmentService._plane_summaries exactly (same base-area and
        segment-totals rule functions) so the Estimate never diverges from
        what the Surface/Area-segments UI shows as "Razem".
        """
        plane = AreaPlane.FLOOR if surface_type == SurfaceType.FLOOR else AreaPlane.CEILING
        room_row = (
            await self.db.execute(select(Room.length, Room.width).where(Room.id == room_id))
        ).one_or_none()
        base_area = calculate_plane_base_area(room_row.length, room_row.width) if room_row else None

        segments_stmt = select(AreaSegment).where(
            AreaSegment.room_id == room_id,
            AreaSegment.plane == plane,
            AreaSegment.is_archived.is_(False),
        )
        segments = (await self.db.execute(segments_stmt)).scalars().all()
        pairs = [
            (segment.operation, calculate_segment_area(segment.width, segment.height))
            for segment in segments
        ]
        totals = calculate_plane_totals(pairs, base_area)
        return totals.net_area if totals is not None else None

    async def _legacy_blocked_plan_ids(
        self, plan_ids: set[uuid.UUID]
    ) -> set[uuid.UUID]:
        """Plans with a recorded template REPLACE: their legacy (key-less)
        lines may not fall back to logical matching (Stage 13E.2B)."""
        if not plan_ids:
            return set()
        stmt = select(SurfaceWorkPlanTemplateApplication.work_plan_id).where(
            SurfaceWorkPlanTemplateApplication.work_plan_id.in_(plan_ids),
            SurfaceWorkPlanTemplateApplication.mode == TemplateApplicationMode.REPLACE,
        )
        return set((await self.db.execute(stmt)).scalars().all())

    async def _match_all_lines(
        self,
        existing_by_pwid: dict[uuid.UUID, "EstimateLine"],
        surface_works: list,
        reveal_works: list,
    ) -> dict[uuid.UUID, "EstimateLine"]:
        """Surface lines use occurrence-identity matching; reveal (and any
        other non-surface PLANNED_WORK) lines keep the exact Stage 12 pairing.
        The two pools never shared a logical key (opening_id differs), so
        splitting them leaves reveal behaviour unchanged."""
        surface_lines = [ln for ln in existing_by_pwid.values() if _is_surface_line(ln)]
        other_lines = {
            pwid: ln for pwid, ln in existing_by_pwid.items() if not _is_surface_line(ln)
        }
        plan_ids = {plan.id for _w, plan, _s, _r in surface_works}
        plan_ids.update(ln.plan_id for ln in surface_lines)
        blocked = await self._legacy_blocked_plan_ids(plan_ids)
        matched = _match_surface_lines(
            surface_lines,
            [
                (w.id, w.occurrence_key, plan.id, (s.id, w.price_item_id))
                for w, plan, s, _r in surface_works
            ],
            blocked,
        )
        matched.update(
            _match_existing_lines(
                other_lines,
                [(w.id, (s.id, o.id, w.price_item_id)) for w, o, s, _r in reveal_works],
            )
        )
        return matched

    async def _load_surface_planned_works(
        self, project_id: uuid.UUID
    ) -> list[tuple[SurfacePlannedWork, SurfaceWorkPlan, Surface, Room]]:
        """Return all planned works for a project in surface.position/work.position order.

        Deliberately no `populate_existing=True` (unlike SurfaceWorkPlanService's
        own coefficient-chain loaders): this query also selects `SurfaceWorkPlan`
        as a top-level entity, and populate_existing would force-refresh any
        already identity-mapped plan object in this session, expiring its
        `planned_works` collection when this query's loader options don't
        re-populate it -- observed to break callers that hold a `SurfaceWorkPlan`
        fetched earlier in the same session. Within one generate/regenerate/
        preview call this data is read fresh regardless.
        """
        stmt = (
            select(SurfacePlannedWork, SurfaceWorkPlan, Surface, Room)
            .join(SurfaceWorkPlan, SurfacePlannedWork.work_plan_id == SurfaceWorkPlan.id)
            .join(Surface, SurfaceWorkPlan.surface_id == Surface.id)
            .join(Room, Surface.room_id == Room.id)
            .where(
                Room.project_id == project_id,
                Surface.is_archived.is_(False),
            )
            .options(
                selectinload(SurfacePlannedWork.price_item),
                # Stage 12E: eager-load the full coefficient chain so
                # SurfacePlannedWork.coefficient_options (a plain property)
                # never triggers an implicit lazy load during pricing.
                selectinload(SurfacePlannedWork.coefficient_assignments)
                .selectinload(SurfacePlannedWorkCoefficientAssignment.coefficient_option)
                .selectinload(CoefficientOption.group),
            )
            .order_by(
                Surface.position.nulls_last(),
                Surface.id,
                SurfacePlannedWork.position,
            )
        )
        rows = (await self.db.execute(stmt)).all()
        return [(r[0], r[1], r[2], r[3]) for r in rows]

    async def _load_reveal_planned_works(
        self, project_id: uuid.UUID
    ) -> list[tuple[OpeningRevealPlannedWork, Opening, Surface, Room]]:
        """Return all reveal work rows for reveal-enabled openings in a project."""
        stmt = (
            select(OpeningRevealPlannedWork, Opening, Surface, Room)
            .join(Opening, OpeningRevealPlannedWork.opening_id == Opening.id)
            .join(Surface, Opening.surface_id == Surface.id)
            .join(Room, Surface.room_id == Room.id)
            .where(
                Room.project_id == project_id,
                Opening.reveal_enabled.is_(True),
                Opening.is_archived.is_(False),
                Surface.is_archived.is_(False),
            )
            .options(
                selectinload(OpeningRevealPlannedWork.price_item),
                # Stage 12E: same coefficient chain as Surface, above.
                selectinload(OpeningRevealPlannedWork.coefficient_assignments)
                .selectinload(
                    OpeningRevealPlannedWorkCoefficientAssignment.coefficient_option
                )
                .selectinload(CoefficientOption.group),
            )
            .order_by(
                Surface.position.nulls_last(),
                Surface.id,
                Opening.id,
                OpeningRevealPlannedWork.position,
            )
        )
        rows = (await self.db.execute(stmt)).all()
        return [(r[0], r[1], r[2], r[3]) for r in rows]

    def _make_surface_line(
        self,
        estimate_id: uuid.UUID,
        position: int,
        work: SurfacePlannedWork,
        plan: SurfaceWorkPlan,
        surface: Surface,
        room: Room,
        net_area: Decimal | None,
    ) -> EstimateLine:
        item = work.price_item
        source_qty, qty_source = _resolve_surface_quantity(item, net_area)

        if source_qty is None:
            quantity = Decimal("0.000")
        else:
            quantity = source_qty

        base_price, effective_price, snapshot = _resolve_occurrence_pricing(
            item, work.coefficient_options
        )
        amount = _compute_amount(quantity, effective_price)
        return EstimateLine(
            estimate_id=estimate_id,
            origin=LineOrigin.PLANNED_WORK,
            position=position,
            plan_id=plan.id,
            planned_work_id=work.id,
            occurrence_key=work.occurrence_key,
            surface_id=surface.id,
            room_id=room.id,
            opening_id=None,
            price_item_id=item.id,
            item_code=item.code,
            description=_item_description(item),
            unit=item.unit,
            scope=item.price_scope,
            currency=item.currency,
            source_quantity=source_qty,
            quantity=quantity,
            quantity_source=qty_source,
            quantity_overridden=False,
            base_unit_price=base_price,
            coefficient_snapshot=snapshot,
            unit_price=effective_price,
            price_override=False,
            amount=amount,
        )

    def _make_reveal_line(
        self,
        estimate_id: uuid.UUID,
        position: int,
        work: OpeningRevealPlannedWork,
        opening: Opening,
        surface: Surface,
        room: Room,
    ) -> EstimateLine:
        item = work.price_item
        source_qty, qty_source = _resolve_reveal_quantity(item, opening)

        quantity = source_qty if source_qty is not None else Decimal("0.000")
        base_price, effective_price, snapshot = _resolve_occurrence_pricing(
            item, work.coefficient_options
        )
        amount = _compute_amount(quantity, effective_price)
        return EstimateLine(
            estimate_id=estimate_id,
            origin=LineOrigin.PLANNED_WORK,
            position=position,
            plan_id=None,
            planned_work_id=work.id,
            surface_id=surface.id,
            room_id=room.id,
            opening_id=opening.id,
            price_item_id=item.id,
            item_code=item.code,
            description=_item_description(item),
            unit=item.unit,
            scope=item.price_scope,
            currency=item.currency,
            source_quantity=source_qty,
            quantity=quantity,
            quantity_source=qty_source,
            quantity_overridden=False,
            base_unit_price=base_price,
            coefficient_snapshot=snapshot,
            unit_price=effective_price,
            price_override=False,
            amount=amount,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def recalculate_totals(
        self,
        estimate: Estimate,
        lines: list[EstimateLine] | None = None,
    ) -> None:
        """Recompute estimate.total = Σ quantized line amounts (NULL excluded).

        Pass lines explicitly to avoid lazy-loading on a freshly-flushed estimate.
        """
        source = lines if lines is not None else estimate.lines
        total = Decimal("0.00")
        has_priced = False
        for line in source:
            if line.amount is not None:
                total += line.amount
                has_priced = True
        estimate.total = total if has_priced else None

    async def generate_estimate(
        self,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> Estimate:
        """Create a new DRAFT from current plans.

        If no DRAFT exists and no immutable estimate exists → creates DRAFT v1.
        If the latest estimate is FINAL/ACCEPTED/ARCHIVED → creates a new DRAFT
        with version = max + 1.
        If an active DRAFT already exists → raises EstimateDraftExistsError.
        Use regenerate-preview + regenerate to update an existing DRAFT.
        """
        await self._lock_project(project_id, owner_id)

        existing_draft = await self._draft_for_project(project_id, owner_id)
        if existing_draft is not None:
            raise EstimateDraftExistsError(
                f"Project {project_id} already has an active DRAFT estimate "
                f"(id={existing_draft.id}). Use regenerate-preview + regenerate "
                "to update it, or finalize it before generating a new version."
            )

        # Check for immutable latest estimate → new version
        latest_stmt = (
            select(Estimate)
            .where(
                Estimate.project_id == project_id,
                Estimate.owner_id == owner_id,
            )
            .order_by(Estimate.version.desc())
            .limit(1)
        )
        latest = (await self.db.execute(latest_stmt)).scalar_one_or_none()
        version = 1
        if latest is not None and latest.status in (
            EstimateStatus.FINAL,
            EstimateStatus.ACCEPTED,
            EstimateStatus.ARCHIVED,
        ):
            version = latest.version + 1

        estimate = Estimate(
            owner_id=owner_id,
            project_id=project_id,
            version=version,
            status=EstimateStatus.DRAFT,
        )
        self.db.add(estimate)
        await self.db.flush()

        # Accumulate lines locally to avoid lazy-loading the relationship
        # on a freshly-flushed estimate (async sessions prohibit implicit loads).
        acc: list[EstimateLine] = []
        position = 0
        surface_works = await self._load_surface_planned_works(project_id)
        net_area_cache: dict[uuid.UUID, Decimal | None] = {}
        for work, plan, surface, room in surface_works:
            if surface.id not in net_area_cache:
                net_area_cache[surface.id] = await self._surface_net_area(surface)
            line = self._make_surface_line(
                estimate.id, position, work, plan, surface, room,
                net_area_cache[surface.id],
            )
            self.db.add(line)
            acc.append(line)
            position += 1

        reveal_works = await self._load_reveal_planned_works(project_id)
        for work, opening, surface, room in reveal_works:
            line = self._make_reveal_line(
                estimate.id, position, work, opening, surface, room
            )
            self.db.add(line)
            acc.append(line)
            position += 1

        self.recalculate_totals(estimate, acc)
        await self.db.commit()
        return await self._fetch_estimate(estimate.id, owner_id)

    async def _do_regenerate(
        self,
        estimate: Estimate,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> RegenerationResult:
        """Re-derive PLANNED_WORK lines from current plans.

        MANUAL lines are never touched. Owner overrides are preserved.
        Only counts a line as UPDATED when regeneration would actually change a
        generated field (source_quantity, snapshot description/unit/scope/currency,
        or PriceBook price when price_override=False).
        Returns a summary of the diff applied including structured change entries.
        """
        result = RegenerationResult()

        # Index existing PLANNED_WORK lines by planned_work_id
        existing_by_pwid: dict[uuid.UUID, EstimateLine] = {}
        manual_lines: list[EstimateLine] = []
        for line in estimate.lines:
            if line.origin == LineOrigin.MANUAL:
                manual_lines.append(line)
                result.preserved_manual += 1
            elif line.planned_work_id is not None:
                existing_by_pwid[line.planned_work_id] = line

        # Build current surface lines
        surface_works = await self._load_surface_planned_works(project_id)
        reveal_works = await self._load_reveal_planned_works(project_id)
        matched = await self._match_all_lines(existing_by_pwid, surface_works, reveal_works)
        net_area_cache: dict[uuid.UUID, Decimal | None] = {}
        new_lines: list[EstimateLine] = []
        position = 0

        for work, plan, surface, room in surface_works:
            if surface.id not in net_area_cache:
                net_area_cache[surface.id] = await self._surface_net_area(surface)

            item = work.price_item
            source_qty, qty_source = _resolve_surface_quantity(
                item, net_area_cache[surface.id]
            )

            base_price, effective_price, snapshot = _resolve_occurrence_pricing(
                item, work.coefficient_options
            )

            if work.id in matched:
                line = matched[work.id]
                # Capture old values before modification for change entry
                old_src_qty = line.source_quantity
                old_unit_price = line.unit_price
                old_base_price = line.base_unit_price
                old_snapshot = line.coefficient_snapshot
                changed = _snapshot_would_change(
                    line, item, source_qty, qty_source,
                    base_price, effective_price, snapshot,
                )

                # Refresh snapshot, preserve overrides; re-point to the current
                # occurrence so a later reset reads its live configuration.
                line.planned_work_id = work.id
                # Snapshot (or upgrade a legacy line to) the logical identity;
                # never reported as a change on its own.
                line.occurrence_key = work.occurrence_key
                line.position = position
                line.plan_id = plan.id
                line.surface_id = surface.id
                line.room_id = room.id
                line.item_code = item.code
                line.description = _item_description(item)
                line.unit = item.unit
                line.scope = item.price_scope
                line.currency = item.currency
                line.source_quantity = source_qty
                line.quantity_source = qty_source
                if not line.quantity_overridden:
                    line.quantity = source_qty if source_qty is not None else Decimal("0.000")
                line.base_unit_price = base_price
                line.coefficient_snapshot = snapshot
                if not line.price_override:
                    line.unit_price = effective_price
                line.amount = _compute_amount(line.quantity, line.unit_price)
                new_lines.append(line)

                if changed:
                    result.updated += 1
                    result.changes.append(LineChangeEntry(
                        change_type="UPDATED",
                        estimate_line_id=line.id,
                        planned_work_id=work.id,
                        surface_id=surface.id,
                        opening_id=None,
                        item_code=item.code,
                        description=_item_description(item),
                        unit=item.unit,
                        old_source_quantity=old_src_qty,
                        new_source_quantity=source_qty,
                        old_unit_price=old_unit_price,
                        new_unit_price=line.unit_price,
                        quantity_overridden=line.quantity_overridden,
                        price_override=line.price_override,
                        old_base_unit_price=old_base_price,
                        new_base_unit_price=base_price,
                        old_coefficient_snapshot=old_snapshot,
                        new_coefficient_snapshot=snapshot,
                    ))
            else:
                quantity = source_qty if source_qty is not None else Decimal("0.000")
                line = EstimateLine(
                    estimate_id=estimate.id,
                    origin=LineOrigin.PLANNED_WORK,
                    position=position,
                    plan_id=plan.id,
                    planned_work_id=work.id,
                    occurrence_key=work.occurrence_key,
                    surface_id=surface.id,
                    room_id=room.id,
                    opening_id=None,
                    price_item_id=item.id,
                    item_code=item.code,
                    description=_item_description(item),
                    unit=item.unit,
                    scope=item.price_scope,
                    currency=item.currency,
                    source_quantity=source_qty,
                    quantity=quantity,
                    quantity_source=qty_source,
                    quantity_overridden=False,
                    base_unit_price=base_price,
                    coefficient_snapshot=snapshot,
                    unit_price=effective_price,
                    price_override=False,
                    amount=_compute_amount(quantity, effective_price),
                )
                self.db.add(line)
                new_lines.append(line)
                result.added += 1
                result.changes.append(LineChangeEntry(
                    change_type="ADDED",
                    estimate_line_id=None,
                    planned_work_id=work.id,
                    surface_id=surface.id,
                    opening_id=None,
                    item_code=item.code,
                    description=_item_description(item),
                    unit=item.unit,
                    old_source_quantity=None,
                    new_source_quantity=source_qty,
                    old_unit_price=None,
                    new_unit_price=effective_price,
                    quantity_overridden=False,
                    price_override=False,
                    old_base_unit_price=None,
                    new_base_unit_price=base_price,
                    old_coefficient_snapshot=None,
                    new_coefficient_snapshot=snapshot,
                ))
            position += 1

        # Reveal lines
        for work, opening, surface, room in reveal_works:
            item = work.price_item
            source_qty, qty_source = _resolve_reveal_quantity(item, opening)

            base_price, effective_price, snapshot = _resolve_occurrence_pricing(
                item, work.coefficient_options
            )

            if work.id in matched:
                line = matched[work.id]
                old_src_qty = line.source_quantity
                old_unit_price = line.unit_price
                old_base_price = line.base_unit_price
                old_snapshot = line.coefficient_snapshot
                changed = _snapshot_would_change(
                    line, item, source_qty, qty_source,
                    base_price, effective_price, snapshot,
                )

                line.planned_work_id = work.id
                line.position = position
                line.surface_id = surface.id
                line.room_id = room.id
                line.opening_id = opening.id
                line.item_code = item.code
                line.description = _item_description(item)
                line.unit = item.unit
                line.scope = item.price_scope
                line.currency = item.currency
                line.source_quantity = source_qty
                line.quantity_source = qty_source
                if not line.quantity_overridden:
                    line.quantity = source_qty if source_qty is not None else Decimal("0.000")
                line.base_unit_price = base_price
                line.coefficient_snapshot = snapshot
                if not line.price_override:
                    line.unit_price = effective_price
                line.amount = _compute_amount(line.quantity, line.unit_price)
                new_lines.append(line)

                if changed:
                    result.updated += 1
                    result.changes.append(LineChangeEntry(
                        change_type="UPDATED",
                        estimate_line_id=line.id,
                        planned_work_id=work.id,
                        surface_id=surface.id,
                        opening_id=opening.id,
                        item_code=item.code,
                        description=_item_description(item),
                        unit=item.unit,
                        old_source_quantity=old_src_qty,
                        new_source_quantity=source_qty,
                        old_unit_price=old_unit_price,
                        new_unit_price=line.unit_price,
                        quantity_overridden=line.quantity_overridden,
                        price_override=line.price_override,
                        old_base_unit_price=old_base_price,
                        new_base_unit_price=base_price,
                        old_coefficient_snapshot=old_snapshot,
                        new_coefficient_snapshot=snapshot,
                    ))
            else:
                quantity = source_qty if source_qty is not None else Decimal("0.000")
                line = EstimateLine(
                    estimate_id=estimate.id,
                    origin=LineOrigin.PLANNED_WORK,
                    position=position,
                    plan_id=None,
                    planned_work_id=work.id,
                    surface_id=surface.id,
                    room_id=room.id,
                    opening_id=opening.id,
                    price_item_id=item.id,
                    item_code=item.code,
                    description=_item_description(item),
                    unit=item.unit,
                    scope=item.price_scope,
                    currency=item.currency,
                    source_quantity=source_qty,
                    quantity=quantity,
                    quantity_source=qty_source,
                    quantity_overridden=False,
                    base_unit_price=base_price,
                    coefficient_snapshot=snapshot,
                    unit_price=effective_price,
                    price_override=False,
                    amount=_compute_amount(quantity, effective_price),
                )
                self.db.add(line)
                new_lines.append(line)
                result.added += 1
                result.changes.append(LineChangeEntry(
                    change_type="ADDED",
                    estimate_line_id=None,
                    planned_work_id=work.id,
                    surface_id=surface.id,
                    opening_id=opening.id,
                    item_code=item.code,
                    description=_item_description(item),
                    unit=item.unit,
                    old_source_quantity=None,
                    new_source_quantity=source_qty,
                    old_unit_price=None,
                    new_unit_price=effective_price,
                    quantity_overridden=False,
                    price_override=False,
                    old_base_unit_price=None,
                    new_base_unit_price=base_price,
                    old_coefficient_snapshot=None,
                    new_coefficient_snapshot=snapshot,
                ))
            position += 1

        # Remove lines no current occurrence was matched to
        matched_line_ids = {line.id for line in matched.values()}
        for pw_id, line in existing_by_pwid.items():
            if line.id not in matched_line_ids:
                result.changes.append(LineChangeEntry(
                    change_type="REMOVED",
                    estimate_line_id=line.id,
                    planned_work_id=pw_id,
                    surface_id=line.surface_id,
                    opening_id=line.opening_id,
                    item_code=line.item_code,
                    description=line.description,
                    unit=line.unit,
                    old_source_quantity=line.source_quantity,
                    new_source_quantity=None,
                    old_unit_price=line.unit_price,
                    new_unit_price=None,
                    quantity_overridden=line.quantity_overridden,
                    price_override=line.price_override,
                    old_base_unit_price=line.base_unit_price,
                    new_base_unit_price=None,
                    old_coefficient_snapshot=line.coefficient_snapshot,
                    new_coefficient_snapshot=None,
                ))
                await self.db.delete(line)
                result.removed += 1

        # Append manual lines at the end (preserving their relative order)
        for line in manual_lines:
            line.position = position
            new_lines.append(line)
            position += 1

        estimate.lines = new_lines
        result.lines = new_lines
        await self._enrich_change_provenance(result.changes)
        return result

    async def list_estimates(
        self,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> list[Estimate]:
        """Return all estimates for a project ordered by version descending."""
        await self._assert_project_owned(project_id, owner_id)
        stmt = (
            select(Estimate)
            .where(
                Estimate.project_id == project_id,
                Estimate.owner_id == owner_id,
            )
            .order_by(Estimate.version.desc())
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def get_estimate_detail(
        self,
        project_id: uuid.UUID,
        estimate_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> Estimate:
        """Return a single estimate with eagerly-loaded lines."""
        return await self._fetch_estimate(estimate_id, owner_id, project_id=project_id)

    async def get_estimate_read_with_provenance(
        self,
        project_id: uuid.UUID,
        estimate_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> dict:
        """Return an estimate dict enriched with room/surface/opening display metadata.

        Provenance fields are resolved live from current DB records (not snapshotted).
        Batch-loads Room, Surface, Opening in 3 extra queries max — no N+1.
        """
        from app.schemas.estimate import EstimateRead

        estimate = await self._fetch_estimate(estimate_id, owner_id, project_id=project_id)

        room_ids = {ln.room_id for ln in estimate.lines if ln.room_id is not None}
        surface_ids = {ln.surface_id for ln in estimate.lines if ln.surface_id is not None}
        opening_ids = {ln.opening_id for ln in estimate.lines if ln.opening_id is not None}

        rooms: dict[uuid.UUID, Room] = {}
        if room_ids:
            rows = (await self.db.execute(select(Room).where(Room.id.in_(room_ids)))).scalars().all()
            rooms = {r.id: r for r in rows}

        surfaces: dict[uuid.UUID, Surface] = {}
        if surface_ids:
            rows = (await self.db.execute(select(Surface).where(Surface.id.in_(surface_ids)))).scalars().all()
            surfaces = {s.id: s for s in rows}

        openings: dict[uuid.UUID, Opening] = {}
        if opening_ids:
            rows = (await self.db.execute(select(Opening).where(Opening.id.in_(opening_ids)))).scalars().all()
            openings = {o.id: o for o in rows}

        enriched_lines = []
        for ln in estimate.lines:
            room = rooms.get(ln.room_id) if ln.room_id else None
            surface = surfaces.get(ln.surface_id) if ln.surface_id else None
            opening = openings.get(ln.opening_id) if ln.opening_id else None

            enriched_lines.append({
                "id": ln.id,
                "estimate_id": ln.estimate_id,
                "origin": ln.origin,
                "position": ln.position,
                "description": ln.description,
                "item_code": ln.item_code,
                "unit": ln.unit,
                "scope": ln.scope,
                "currency": ln.currency,
                "source_quantity": ln.source_quantity,
                "quantity": ln.quantity,
                "quantity_source": ln.quantity_source,
                "quantity_overridden": ln.quantity_overridden,
                "base_unit_price": ln.base_unit_price,
                "coefficient_snapshot": ln.coefficient_snapshot,
                "unit_price": ln.unit_price,
                "price_override": ln.price_override,
                "amount": ln.amount,
                "price_item_id": ln.price_item_id,
                "plan_id": ln.plan_id,
                "planned_work_id": ln.planned_work_id,
                "surface_id": ln.surface_id,
                "room_id": ln.room_id,
                "opening_id": ln.opening_id,
                "room_name": room.name if room else None,
                "surface_name": surface.name if surface else None,
                "surface_type_value": surface.surface_type.value if surface else None,
                "opening_name": opening.name if opening else None,
                "opening_type_value": opening.opening_type.value if opening else None,
            })

        estimate_dict = {
            "id": estimate.id,
            "project_id": estimate.project_id,
            "version": estimate.version,
            "status": estimate.status,
            "name": estimate.name,
            "total": estimate.total,
            "currency": estimate.currency,
            "created_at": estimate.created_at,
            "updated_at": estimate.updated_at,
            "lines": enriched_lines,
        }
        return EstimateRead.model_validate(estimate_dict)

    async def _enrich_change_provenance(self, changes: list["LineChangeEntry"]) -> None:
        """Batch-load Surface/Room/Opening for a regeneration diff and set
        presentation-only provenance fields in place (Stage 10G.3B follow-up,
        analogous to the accepted 10G.2 EstimateLine enrichment).

        Bounded to 3 extra queries total, independent of len(changes). Room is
        resolved via Surface.room_id (Surface belongs to Room; for reveal
        entries the change already carries surface_id directly, so no
        Opening -> Surface hop is needed). Never fabricates a name: a REMOVED
        entry's referenced Surface/Opening may no longer exist, in which case
        the corresponding field(s) simply stay None.
        """
        surface_ids = {c.surface_id for c in changes if c.surface_id is not None}
        opening_ids = {c.opening_id for c in changes if c.opening_id is not None}

        surfaces: dict[uuid.UUID, Surface] = {}
        if surface_ids:
            rows = (await self.db.execute(select(Surface).where(Surface.id.in_(surface_ids)))).scalars().all()
            surfaces = {s.id: s for s in rows}

        room_ids = {s.room_id for s in surfaces.values()}
        rooms: dict[uuid.UUID, Room] = {}
        if room_ids:
            rows = (await self.db.execute(select(Room).where(Room.id.in_(room_ids)))).scalars().all()
            rooms = {r.id: r for r in rows}

        openings: dict[uuid.UUID, Opening] = {}
        if opening_ids:
            rows = (await self.db.execute(select(Opening).where(Opening.id.in_(opening_ids)))).scalars().all()
            openings = {o.id: o for o in rows}

        for c in changes:
            surface = surfaces.get(c.surface_id) if c.surface_id else None
            room = rooms.get(surface.room_id) if surface else None
            opening = openings.get(c.opening_id) if c.opening_id else None
            c.room_name = room.name if room else None
            c.surface_name = surface.name if surface else None
            c.surface_type_value = surface.surface_type.value if surface else None
            c.opening_name = opening.name if opening else None
            c.opening_type_value = opening.opening_type.value if opening else None

    async def preview_regeneration(
        self,
        project_id: uuid.UUID,
        estimate_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> RegenerationResult:
        """Compute what a regeneration would change WITHOUT mutating the estimate.

        Only classifies a line as UPDATED when regeneration would actually change a
        generated field. Unchanged matched lines are not counted in any category.
        """
        estimate = await self._fetch_estimate(estimate_id, owner_id, project_id=project_id)
        if estimate.status != EstimateStatus.DRAFT:
            raise EstimateStateError(
                f"Only DRAFT estimates can be regenerated; "
                f"estimate {estimate_id} is {estimate.status.value}"
            )

        result = RegenerationResult()
        existing_by_pwid: dict[uuid.UUID, EstimateLine] = {}
        for line in estimate.lines:
            if line.origin == LineOrigin.MANUAL:
                result.preserved_manual += 1
            elif line.planned_work_id is not None:
                existing_by_pwid[line.planned_work_id] = line

        net_area_cache: dict[uuid.UUID, Decimal | None] = {}

        surface_works = await self._load_surface_planned_works(estimate.project_id)
        reveal_works = await self._load_reveal_planned_works(estimate.project_id)
        # Same pairing as regeneration; preview never mutates any line.
        matched = await self._match_all_lines(existing_by_pwid, surface_works, reveal_works)
        for work, _plan, surface, _room in surface_works:
            if surface.id not in net_area_cache:
                net_area_cache[surface.id] = await self._surface_net_area(surface)
            item = work.price_item
            source_qty, qty_source = _resolve_surface_quantity(
                item, net_area_cache[surface.id]
            )

            base_price, effective_price, snapshot = _resolve_occurrence_pricing(
                item, work.coefficient_options
            )

            if work.id in matched:
                line = matched[work.id]
                if _snapshot_would_change(
                    line, item, source_qty, qty_source,
                    base_price, effective_price, snapshot,
                ):
                    result.updated += 1
                    new_unit_price = line.unit_price if line.price_override else effective_price
                    result.changes.append(LineChangeEntry(
                        change_type="UPDATED",
                        estimate_line_id=line.id,
                        planned_work_id=work.id,
                        surface_id=surface.id,
                        opening_id=None,
                        item_code=item.code,
                        description=_item_description(item),
                        unit=item.unit,
                        old_source_quantity=line.source_quantity,
                        new_source_quantity=source_qty,
                        old_unit_price=line.unit_price,
                        new_unit_price=new_unit_price,
                        quantity_overridden=line.quantity_overridden,
                        price_override=line.price_override,
                        old_base_unit_price=line.base_unit_price,
                        new_base_unit_price=base_price,
                        old_coefficient_snapshot=line.coefficient_snapshot,
                        new_coefficient_snapshot=snapshot,
                    ))
            else:
                result.added += 1
                result.changes.append(LineChangeEntry(
                    change_type="ADDED",
                    estimate_line_id=None,
                    planned_work_id=work.id,
                    surface_id=surface.id,
                    opening_id=None,
                    item_code=item.code,
                    description=_item_description(item),
                    unit=item.unit,
                    old_source_quantity=None,
                    new_source_quantity=source_qty,
                    old_unit_price=None,
                    new_unit_price=effective_price,
                    quantity_overridden=False,
                    price_override=False,
                    old_base_unit_price=None,
                    new_base_unit_price=base_price,
                    old_coefficient_snapshot=None,
                    new_coefficient_snapshot=snapshot,
                ))

        for work, opening, surface, _room in reveal_works:
            item = work.price_item
            source_qty, qty_source = _resolve_reveal_quantity(item, opening)

            base_price, effective_price, snapshot = _resolve_occurrence_pricing(
                item, work.coefficient_options
            )

            if work.id in matched:
                line = matched[work.id]
                if _snapshot_would_change(
                    line, item, source_qty, qty_source,
                    base_price, effective_price, snapshot,
                ):
                    result.updated += 1
                    new_unit_price = line.unit_price if line.price_override else effective_price
                    result.changes.append(LineChangeEntry(
                        change_type="UPDATED",
                        estimate_line_id=line.id,
                        planned_work_id=work.id,
                        surface_id=surface.id,
                        opening_id=opening.id,
                        item_code=item.code,
                        description=_item_description(item),
                        unit=item.unit,
                        old_source_quantity=line.source_quantity,
                        new_source_quantity=source_qty,
                        old_unit_price=line.unit_price,
                        new_unit_price=new_unit_price,
                        quantity_overridden=line.quantity_overridden,
                        price_override=line.price_override,
                        old_base_unit_price=line.base_unit_price,
                        new_base_unit_price=base_price,
                        old_coefficient_snapshot=line.coefficient_snapshot,
                        new_coefficient_snapshot=snapshot,
                    ))
            else:
                result.added += 1
                result.changes.append(LineChangeEntry(
                    change_type="ADDED",
                    estimate_line_id=None,
                    planned_work_id=work.id,
                    surface_id=surface.id,
                    opening_id=opening.id,
                    item_code=item.code,
                    description=_item_description(item),
                    unit=item.unit,
                    old_source_quantity=None,
                    new_source_quantity=source_qty,
                    old_unit_price=None,
                    new_unit_price=effective_price,
                    quantity_overridden=False,
                    price_override=False,
                    old_base_unit_price=None,
                    new_base_unit_price=base_price,
                    old_coefficient_snapshot=None,
                    new_coefficient_snapshot=snapshot,
                ))

        matched_line_ids = {line.id for line in matched.values()}
        for pw_id, line in existing_by_pwid.items():
            if line.id not in matched_line_ids:
                result.removed += 1
                result.changes.append(LineChangeEntry(
                    change_type="REMOVED",
                    estimate_line_id=line.id,
                    planned_work_id=pw_id,
                    surface_id=line.surface_id,
                    opening_id=line.opening_id,
                    item_code=line.item_code,
                    description=line.description,
                    unit=line.unit,
                    old_source_quantity=line.source_quantity,
                    new_source_quantity=None,
                    old_unit_price=line.unit_price,
                    new_unit_price=None,
                    quantity_overridden=line.quantity_overridden,
                    price_override=line.price_override,
                    old_base_unit_price=line.base_unit_price,
                    new_base_unit_price=None,
                    old_coefficient_snapshot=line.coefficient_snapshot,
                    new_coefficient_snapshot=None,
                ))

        await self._enrich_change_provenance(result.changes)
        # Intentionally no commit — read-only preview.
        return result

    async def regenerate_draft(
        self,
        estimate_id: uuid.UUID,
        owner_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
    ) -> RegenerationResult:
        """Explicitly regenerate a DRAFT estimate in-place and return the diff summary."""
        estimate = await self._fetch_estimate(estimate_id, owner_id, project_id=project_id)
        if estimate.status != EstimateStatus.DRAFT:
            raise EstimateStateError(
                f"Only DRAFT estimates can be regenerated; "
                f"estimate {estimate_id} is {estimate.status.value}"
            )
        result = await self._do_regenerate(estimate, estimate.project_id, owner_id)
        self.recalculate_totals(estimate)
        await self.db.commit()
        return result

    async def finalize(
        self,
        estimate_id: uuid.UUID,
        owner_id: uuid.UUID,
        project_id: uuid.UUID | None = None,
    ) -> Estimate:
        """Transition a DRAFT estimate to FINAL.

        Blocked if any line has unit_price=NULL (Do ustalenia), OR if any
        PLANNED_WORK line has an unresolved quantity -- generated with no
        applicable geometry (quantity_source=MANUAL, source_quantity=NULL)
        and never confirmed by the owner (quantity_overridden=False). The
        generated Decimal("0.000") fallback in that state is a placeholder,
        never a resolved quantity; an owner who explicitly overrides to
        0.000 (quantity_overridden=True) has a legitimate, resolved zero and
        is never blocked. The check is scoped to origin=PLANNED_WORK only: a
        freeform MANUAL-origin line (`add_manual_line`) always carries this
        same (quantity_source=MANUAL, source_quantity=NULL,
        quantity_overridden=False) fingerprint by construction -- the owner
        already typed its quantity at creation time, so it is resolved by
        definition and must never be misclassified as unresolved. Both
        checks are independent: either, both, or neither may fire, and a
        message names whichever blocker(s) actually apply.
        """
        estimate = await self._fetch_estimate(estimate_id, owner_id, project_id=project_id)
        if estimate.status != EstimateStatus.DRAFT:
            raise EstimateStateError(
                f"Only DRAFT estimates can be finalized; "
                f"estimate {estimate_id} is {estimate.status.value}"
            )
        unpriced = [ln for ln in estimate.lines if ln.unit_price is None]
        unresolved_quantity = [
            ln
            for ln in estimate.lines
            if ln.origin == LineOrigin.PLANNED_WORK
            and ln.quantity_source == QuantitySource.MANUAL
            and ln.source_quantity is None
            and not ln.quantity_overridden
        ]
        if unpriced or unresolved_quantity:
            messages = []
            if unpriced:
                messages.append(
                    f"Cannot finalize: {len(unpriced)} line(s) have no price set "
                    "(Do ustalenia). Set prices in the Price Book or add line overrides."
                )
            if unresolved_quantity:
                messages.append(
                    f"Cannot finalize: {len(unresolved_quantity)} line(s) have "
                    "unresolved quantity (Ilość do ustalenia). Set quantities via "
                    "line overrides."
                )
            raise EstimateValidationError(" ".join(messages))
        estimate.status = EstimateStatus.FINAL
        await self.db.commit()
        return await self._fetch_estimate(estimate_id, owner_id)

    async def add_manual_line(
        self,
        estimate_id: uuid.UUID,
        owner_id: uuid.UUID,
        *,
        description: str,
        scope,
        unit,
        quantity: Decimal,
        unit_price: Decimal | None,
        currency: str = "PLN",
        project_id: uuid.UUID | None = None,
    ) -> EstimateLine:
        """Append a freeform MANUAL line to a DRAFT estimate."""
        from app.models.price_item import PriceScope

        estimate = await self._fetch_estimate(estimate_id, owner_id, project_id=project_id)
        if estimate.status != EstimateStatus.DRAFT:
            raise EstimateStateError(
                f"Lines can only be added to DRAFT estimates; "
                f"estimate {estimate_id} is {estimate.status.value}"
            )
        if scope == PriceScope.LABOR_AND_MATERIAL:
            raise EstimateValidationError(
                "Manual lines cannot use LABOR_AND_MATERIAL scope"
            )
        if currency != estimate.currency:
            raise EstimateValidationError(
                f"Manual line currency '{currency}' does not match "
                f"estimate currency '{estimate.currency}'"
            )
        position = (
            max((ln.position for ln in estimate.lines), default=-1) + 1
        )
        amount = _compute_amount(quantity, unit_price)
        line = EstimateLine(
            estimate_id=estimate.id,
            origin=LineOrigin.MANUAL,
            position=position,
            price_item_id=None,
            item_code=None,
            description=description,
            unit=unit,
            scope=scope,
            currency=currency,
            source_quantity=None,
            quantity=quantity,
            quantity_source=QuantitySource.MANUAL,
            quantity_overridden=False,
            unit_price=unit_price,
            price_override=True,
            amount=amount,
        )
        self.db.add(line)
        estimate.lines.append(line)
        self.recalculate_totals(estimate)
        await self.db.commit()
        return line

    async def patch_line(
        self,
        project_id: uuid.UUID,
        estimate_id: uuid.UUID,
        owner_id: uuid.UUID,
        line_id: uuid.UUID,
        *,
        provided_fields: set[str],
        quantity: Decimal | None = None,
        unit_price: Decimal | None = None,
        description: str | None = None,
        reset_price_override: bool = False,
        reset_quantity_override: bool = False,
    ) -> EstimateLine:
        """Update owner-controlled fields on a DRAFT estimate line."""
        estimate = await self._fetch_estimate(estimate_id, owner_id, project_id=project_id)
        if estimate.status != EstimateStatus.DRAFT:
            raise EstimateStateError(
                f"Lines can only be updated on DRAFT estimates; "
                f"estimate {estimate_id} is {estimate.status.value}"
            )
        line = next((ln for ln in estimate.lines if ln.id == line_id), None)
        if line is None:
            raise EstimateNotFoundError(
                f"Line {line_id} not found on estimate {estimate_id}"
            )

        recalc = False

        if "quantity" in provided_fields:
            if quantity is None:
                raise EstimateValidationError("quantity cannot be null")
            line.quantity = quantity
            line.quantity_overridden = True
            recalc = True

        if reset_quantity_override:
            line.quantity = (
                line.source_quantity
                if line.source_quantity is not None
                else Decimal("0.000")
            )
            line.quantity_overridden = False
            recalc = True

        if "unit_price" in provided_fields:
            line.unit_price = unit_price
            line.price_override = True
            recalc = True

        if reset_price_override:
            if line.origin == LineOrigin.MANUAL:
                raise EstimateValidationError(
                    "price override cannot be reset for MANUAL lines: "
                    "no PriceBook source to restore from"
                )
            if line.price_item_id is None:
                raise EstimateValidationError(
                    "line has no price item reference; cannot reset price override"
                )
            # Stage 12E Sec 19: reset re-derives from the CURRENT live base
            # price AND current coefficient assignments/values -- never the
            # historical snapshot -- so a resolved override always reflects
            # today's WorkPlan configuration, not the one active at
            # generation time.
            occurrence = await self._load_current_occurrence(line)
            if occurrence is not None:
                item, options = occurrence
                base_price, effective_price, snapshot = _resolve_occurrence_pricing(
                    item, options
                )
            else:
                # No live occurrence to resolve (PRICE_BOOK/MANUAL line, or a
                # Surface/Reveal occurrence recreated with a new id since
                # generation -- Sec 19 fallback): the base price is still
                # rereadable via price_item_id, but which coefficients (if
                # any) currently apply is genuinely not determinable, so the
                # snapshot is honestly None rather than a fabricated [].
                item = await self._load_price_item(line.price_item_id, owner_id)
                base_price, effective_price, snapshot = item.price, item.price, None
            line.base_unit_price = base_price
            line.coefficient_snapshot = snapshot
            line.unit_price = effective_price
            line.price_override = False
            recalc = True

        if "description" in provided_fields:
            if line.origin != LineOrigin.MANUAL:
                raise EstimateValidationError(
                    "description is only editable on MANUAL lines"
                )
            if description is None:
                raise EstimateValidationError("description cannot be null")
            line.description = description

        if recalc:
            line.amount = _compute_amount(line.quantity, line.unit_price)
            self.recalculate_totals(estimate)

        await self.db.commit()
        return line

    async def delete_manual_line(
        self,
        project_id: uuid.UUID,
        estimate_id: uuid.UUID,
        owner_id: uuid.UUID,
        line_id: uuid.UUID,
    ) -> None:
        """Delete a MANUAL line from a DRAFT estimate."""
        estimate = await self._fetch_estimate(estimate_id, owner_id, project_id=project_id)
        if estimate.status != EstimateStatus.DRAFT:
            raise EstimateStateError(
                f"Lines can only be deleted from DRAFT estimates; "
                f"estimate {estimate_id} is {estimate.status.value}"
            )
        line = next((ln for ln in estimate.lines if ln.id == line_id), None)
        if line is None:
            raise EstimateNotFoundError(
                f"Line {line_id} not found on estimate {estimate_id}"
            )
        if line.origin != LineOrigin.MANUAL:
            raise EstimateValidationError("Only MANUAL lines can be deleted")

        await self.db.delete(line)
        estimate.lines = [ln for ln in estimate.lines if ln.id != line_id]
        self.recalculate_totals(estimate)
        await self.db.commit()
