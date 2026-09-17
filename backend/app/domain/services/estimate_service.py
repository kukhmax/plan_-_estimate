"""Estimate domain service (Stage 10D).

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
    calculate_reveal,
    calculate_surface_gross_area,
    calculate_wall_net_area,
)
from app.models.estimate import (
    Estimate,
    EstimateLine,
    EstimateStatus,
    LineOrigin,
    QuantitySource,
)
from app.models.opening import Opening, OpeningType
from app.models.opening_reveal_planned_work import OpeningRevealPlannedWork
from app.models.price_item import PriceItem, PriceUnit
from app.models.project import Project
from app.models.room import Room
from app.models.surface import Surface
from app.models.work_plan import SurfacePlannedWork, SurfaceWorkPlan

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


def _snapshot_would_change(
    line: "EstimateLine",
    item: "PriceItem",
    new_source_qty: Decimal | None,
    qty_source: "QuantitySource",
) -> bool:
    """Return True if regeneration would change any generated (non-override) field."""
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
    if not line.price_override and item.price != line.unit_price:
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
        """Compute wall net area: gross - active opening deductions."""
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

    async def _load_surface_planned_works(
        self, project_id: uuid.UUID
    ) -> list[tuple[SurfacePlannedWork, SurfaceWorkPlan, Surface, Room]]:
        """Return all planned works for a project in surface.position/work.position order."""
        stmt = (
            select(SurfacePlannedWork, SurfaceWorkPlan, Surface, Room)
            .join(SurfaceWorkPlan, SurfacePlannedWork.work_plan_id == SurfaceWorkPlan.id)
            .join(Surface, SurfaceWorkPlan.surface_id == Surface.id)
            .join(Room, Surface.room_id == Room.id)
            .where(
                Room.project_id == project_id,
                Surface.is_archived.is_(False),
            )
            .options(selectinload(SurfacePlannedWork.price_item))
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
            .options(selectinload(OpeningRevealPlannedWork.price_item))
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
        is_m2 = item.unit == PriceUnit.M2
        source_qty = net_area if is_m2 else None
        qty_source = QuantitySource.SURFACE_NET_AREA if is_m2 else QuantitySource.MANUAL

        if source_qty is None:
            quantity = Decimal("0.000")
        else:
            quantity = source_qty

        amount = _compute_amount(quantity, item.price)
        return EstimateLine(
            estimate_id=estimate_id,
            origin=LineOrigin.PLANNED_WORK,
            position=position,
            plan_id=plan.id,
            planned_work_id=work.id,
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
            unit_price=item.price,
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
        total_length, total_area = _reveal_totals(opening)

        if item.unit == PriceUnit.LM:
            source_qty = total_length
            qty_source = QuantitySource.REVEAL_LENGTH
        elif item.unit == PriceUnit.M2:
            source_qty = total_area
            qty_source = QuantitySource.REVEAL_AREA
        else:
            source_qty = None
            qty_source = QuantitySource.MANUAL

        quantity = source_qty if source_qty is not None else Decimal("0.000")
        amount = _compute_amount(quantity, item.price)
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
            unit_price=item.price,
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
        await self._assert_project_owned(project_id, owner_id)

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
        net_area_cache: dict[uuid.UUID, Decimal | None] = {}
        current_pw_ids: set[uuid.UUID] = set()
        new_lines: list[EstimateLine] = []
        position = 0

        for work, plan, surface, room in surface_works:
            current_pw_ids.add(work.id)
            if surface.id not in net_area_cache:
                net_area_cache[surface.id] = await self._surface_net_area(surface)
            net_area = net_area_cache[surface.id]

            item = work.price_item
            is_m2 = item.unit == PriceUnit.M2
            source_qty = net_area if is_m2 else None
            qty_source = (
                QuantitySource.SURFACE_NET_AREA if is_m2 else QuantitySource.MANUAL
            )

            if work.id in existing_by_pwid:
                line = existing_by_pwid[work.id]
                # Capture old values before modification for change entry
                old_src_qty = line.source_quantity
                old_unit_price = line.unit_price
                changed = _snapshot_would_change(line, item, source_qty, qty_source)

                # Refresh snapshot, preserve overrides
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
                if not line.price_override:
                    line.unit_price = item.price
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
                    ))
            else:
                quantity = source_qty if source_qty is not None else Decimal("0.000")
                line = EstimateLine(
                    estimate_id=estimate.id,
                    origin=LineOrigin.PLANNED_WORK,
                    position=position,
                    plan_id=plan.id,
                    planned_work_id=work.id,
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
                    unit_price=item.price,
                    price_override=False,
                    amount=_compute_amount(quantity, item.price),
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
                    new_unit_price=item.price,
                    quantity_overridden=False,
                    price_override=False,
                ))
            position += 1

        # Reveal lines
        reveal_works = await self._load_reveal_planned_works(project_id)
        for work, opening, surface, room in reveal_works:
            current_pw_ids.add(work.id)
            item = work.price_item
            total_length, total_area = _reveal_totals(opening)

            if item.unit == PriceUnit.LM:
                source_qty = total_length
                qty_source = QuantitySource.REVEAL_LENGTH
            elif item.unit == PriceUnit.M2:
                source_qty = total_area
                qty_source = QuantitySource.REVEAL_AREA
            else:
                source_qty = None
                qty_source = QuantitySource.MANUAL

            if work.id in existing_by_pwid:
                line = existing_by_pwid[work.id]
                old_src_qty = line.source_quantity
                old_unit_price = line.unit_price
                changed = _snapshot_would_change(line, item, source_qty, qty_source)

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
                if not line.price_override:
                    line.unit_price = item.price
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
                    unit_price=item.price,
                    price_override=False,
                    amount=_compute_amount(quantity, item.price),
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
                    new_unit_price=item.price,
                    quantity_overridden=False,
                    price_override=False,
                ))
            position += 1

        # Remove lines whose planned_work_id is no longer present
        for pw_id, line in existing_by_pwid.items():
            if pw_id not in current_pw_ids:
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

        current_pw_ids: set[uuid.UUID] = set()
        net_area_cache: dict[uuid.UUID, Decimal | None] = {}

        surface_works = await self._load_surface_planned_works(estimate.project_id)
        for work, _plan, surface, _room in surface_works:
            current_pw_ids.add(work.id)
            if surface.id not in net_area_cache:
                net_area_cache[surface.id] = await self._surface_net_area(surface)
            net_area = net_area_cache[surface.id]
            item = work.price_item
            is_m2 = item.unit == PriceUnit.M2
            source_qty = net_area if is_m2 else None
            qty_source = QuantitySource.SURFACE_NET_AREA if is_m2 else QuantitySource.MANUAL

            if work.id in existing_by_pwid:
                line = existing_by_pwid[work.id]
                if _snapshot_would_change(line, item, source_qty, qty_source):
                    result.updated += 1
                    new_unit_price = line.unit_price if line.price_override else item.price
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
                    new_unit_price=item.price,
                    quantity_overridden=False,
                    price_override=False,
                ))

        reveal_works = await self._load_reveal_planned_works(estimate.project_id)
        for work, opening, surface, _room in reveal_works:
            current_pw_ids.add(work.id)
            item = work.price_item
            total_length, total_area = _reveal_totals(opening)
            if item.unit == PriceUnit.LM:
                source_qty = total_length
                qty_source = QuantitySource.REVEAL_LENGTH
            elif item.unit == PriceUnit.M2:
                source_qty = total_area
                qty_source = QuantitySource.REVEAL_AREA
            else:
                source_qty = None
                qty_source = QuantitySource.MANUAL

            if work.id in existing_by_pwid:
                line = existing_by_pwid[work.id]
                if _snapshot_would_change(line, item, source_qty, qty_source):
                    result.updated += 1
                    new_unit_price = line.unit_price if line.price_override else item.price
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
                    new_unit_price=item.price,
                    quantity_overridden=False,
                    price_override=False,
                ))

        for pw_id, line in existing_by_pwid.items():
            if pw_id not in current_pw_ids:
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
                ))

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

        Blocked if any line has unit_price=NULL (Do ustalenia).
        """
        estimate = await self._fetch_estimate(estimate_id, owner_id, project_id=project_id)
        if estimate.status != EstimateStatus.DRAFT:
            raise EstimateStateError(
                f"Only DRAFT estimates can be finalized; "
                f"estimate {estimate_id} is {estimate.status.value}"
            )
        unpriced = [ln for ln in estimate.lines if ln.unit_price is None]
        if unpriced:
            raise EstimateValidationError(
                f"Cannot finalize: {len(unpriced)} line(s) have no price set "
                "(Do ustalenia). Set prices in the Price Book or add line overrides."
            )
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
            item = await self._load_price_item(line.price_item_id, owner_id)
            line.unit_price = item.price
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
