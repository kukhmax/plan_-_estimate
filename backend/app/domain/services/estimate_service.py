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
    EstimateNotFoundError,
    EstimateStateError,
    EstimateValidationError,
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
class RegenerationResult:
    """Summary of changes applied during a DRAFT regeneration."""

    added: int = 0
    updated: int = 0
    removed: int = 0
    preserved_manual: int = 0
    lines: list[EstimateLine] = field(default_factory=list)


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

    async def _fetch_estimate(
        self, estimate_id: uuid.UUID, owner_id: uuid.UUID
    ) -> Estimate:
        stmt = (
            select(Estimate)
            .where(Estimate.id == estimate_id, Estimate.owner_id == owner_id)
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
        """Create DRAFT v1 from current plans, or regenerate the existing DRAFT in place.

        If no DRAFT exists and no immutable estimate exists → creates DRAFT v1.
        If a DRAFT already exists → regenerates it in place (see regenerate_draft).
        If the latest estimate is FINAL/ACCEPTED/ARCHIVED → creates a new DRAFT
        with version = max + 1.
        """
        await self._assert_project_owned(project_id, owner_id)

        existing_draft = await self._draft_for_project(project_id, owner_id)
        if existing_draft is not None:
            result = await self._do_regenerate(existing_draft, project_id, owner_id)
            self.recalculate_totals(existing_draft)
            await self.db.commit()
            return await self._fetch_estimate(existing_draft.id, owner_id)

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
        Returns a summary of the diff applied.
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
                # Refresh snapshot, preserve overrides
                line = existing_by_pwid[work.id]
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
                result.updated += 1
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
                result.updated += 1
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
            position += 1

        # Remove lines whose planned_work_id is no longer present
        for pw_id, line in existing_by_pwid.items():
            if pw_id not in current_pw_ids:
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

    async def regenerate_draft(
        self,
        estimate_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> RegenerationResult:
        """Explicitly regenerate a DRAFT estimate in-place and return the diff summary."""
        estimate = await self._fetch_estimate(estimate_id, owner_id)
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
    ) -> Estimate:
        """Transition a DRAFT estimate to FINAL.

        Blocked if any line has unit_price=NULL (Do ustalenia).
        """
        estimate = await self._fetch_estimate(estimate_id, owner_id)
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
    ) -> EstimateLine:
        """Append a freeform MANUAL line to a DRAFT estimate."""
        from app.models.price_item import PriceScope

        estimate = await self._fetch_estimate(estimate_id, owner_id)
        if estimate.status != EstimateStatus.DRAFT:
            raise EstimateStateError(
                f"Lines can only be added to DRAFT estimates; "
                f"estimate {estimate_id} is {estimate.status.value}"
            )
        if scope == PriceScope.LABOR_AND_MATERIAL:
            raise EstimateValidationError(
                "Manual lines cannot use LABOR_AND_MATERIAL scope"
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
