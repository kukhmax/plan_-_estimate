"""Surface Work Plan domain service (Stage 10B.1).

A SurfaceWorkPlan is the planning configuration for exactly one Surface:
the substrate, the agreed quality target, and an ordered list of Price Book
references. The plan never snapshots prices and never mutates a PriceItem;
archiving prevents its occurrence count from increasing while existing
occurrences may survive replacement. Ownership always resolves through
Surface -> Room -> Project -> Owner, so no tenancy columns exist on the plan.
"""
import uuid
from collections import Counter

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.exceptions import (
    PriceItemNotFoundError,
    ProjectNotFoundError,
    RoomNotFoundError,
    SurfaceNotFoundError,
    SurfaceWorkPlanNotFoundError,
    SurfaceWorkPlanValidationError,
)
from app.domain.rules.inspection_rules import assert_quality_scale_valid
from app.models.checklist import QualityLevel, Substrate
from app.models.price_item import PriceItem
from app.models.project import Project
from app.models.room import Room
from app.models.surface import Surface, SurfaceType
from app.models.work_plan import SurfacePlannedWork, SurfaceWorkPlan
from app.schemas.work_plan import OrderedPriceItemSelection


class SurfaceWorkPlanService:
    """Owner-scoped operations over the per-surface work plan."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _ensure_surface_owned(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        surface_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> Surface:
        """Resolve the ownership chain and return the surface (or raise 404s)."""
        project_stmt = select(Project.id).where(
            Project.id == project_id,
            Project.owner_id == owner_id,
        )
        if (await self.db.execute(project_stmt)).scalar_one_or_none() is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")

        room_stmt = select(Room.id).where(
            Room.id == room_id,
            Room.project_id == project_id,
        )
        if (await self.db.execute(room_stmt)).scalar_one_or_none() is None:
            raise RoomNotFoundError(f"Room {room_id} not found")

        surface_stmt = select(Surface).where(
            Surface.id == surface_id,
            Surface.room_id == room_id,
        )
        surface = (await self.db.execute(surface_stmt)).scalar_one_or_none()
        if surface is None:
            raise SurfaceNotFoundError(f"Surface {surface_id} not found")
        return surface

    async def _resolve_owned_items(
        self,
        owner_id: uuid.UUID,
        selection: list[OrderedPriceItemSelection],
        existing_counts: Counter[uuid.UUID],
    ) -> list[PriceItem]:
        """Validate every selection row and return it in the given order.

        Active items may be selected freely. An archived item's requested count
        cannot exceed the count already persisted on this same plan. Duplicate
        references and exact payload order are preserved.
        """
        if not selection:
            return []
        ids = [row.price_item_id for row in selection]
        requested_counts = Counter(ids)
        items = (
            await self.db.execute(select(PriceItem).where(PriceItem.id.in_(ids)))
        ).scalars().all()
        by_id = {item.id: item for item in items}
        validated: list[PriceItem] = []
        for row in selection:
            item = by_id.get(row.price_item_id)
            if item is None or item.owner_id != owner_id:
                raise PriceItemNotFoundError(
                    f"Price item {row.price_item_id} not found"
                )
            if (
                item.is_archived
                and requested_counts[item.id] > existing_counts[item.id]
            ):
                raise SurfaceWorkPlanValidationError(
                    f"Archived price item {row.price_item_id} cannot be selected "
                    "for a work plan"
                )
            validated.append(item)
        return validated

    async def _rewrite_works(
        self,
        plan: SurfaceWorkPlan,
        selection: list[PriceItem],
    ) -> None:
        """Atomically replace the plan's works, appending position from 0.

        The old rows are deleted with an immediate statement: SQLAlchemy's unit
        of work inserts new rows before deleting cleared orphans, which would
        collide on the unique (work_plan_id, position).
        """
        if plan.id is not None:
            await self.db.execute(
                delete(SurfacePlannedWork).where(
                    SurfacePlannedWork.work_plan_id == plan.id
                )
            )
        plan.planned_works.clear()
        for position, item in enumerate(selection):
            plan.planned_works.append(
                SurfacePlannedWork(
                    work_plan_id=plan.id,
                    price_item_id=item.id,
                    position=position,
                )
            )

    async def lock_plan(self, surface_id: uuid.UUID) -> SurfaceWorkPlan | None:
        """Acquire a row-level exclusive lock on the surface's plan, if any.

        Used by Stage 11 recommendation acceptance to serialize concurrent
        appends to the same plan before computing the next occurrence's
        position (see append_one_planned_work_no_commit). Mirrors the
        existing EstimateService._lock_project row-lock precedent. Returns
        None (never creates) when the surface has no plan yet -- callers
        must not invent one.
        """
        stmt = (
            select(SurfaceWorkPlan)
            .where(SurfaceWorkPlan.surface_id == surface_id)
            .with_for_update()
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def append_one_planned_work_no_commit(
        self,
        plan: SurfaceWorkPlan,
        price_item: PriceItem,
    ) -> SurfacePlannedWork:
        """Append exactly one new occurrence, additive-only, never committing.

        Unlike set_plan/replace_planned_works/apply_to_room_walls, this never
        calls _rewrite_works: no existing row is deleted, renumbered, or
        otherwise touched, and substrate/quality_target are left exactly as
        they are. The caller MUST already hold plan's row lock (lock_plan
        above) before calling this, so the MAX(position) read below is safe
        under concurrent appends to the same plan. Duplicates are allowed by
        design (Stage 10 invariant) -- this never checks whether price_item
        already appears in the plan. The caller owns the transaction: this
        method only adds and flushes, it never commits.
        """
        if price_item.is_archived:
            raise SurfaceWorkPlanValidationError(
                f"Archived price item {price_item.id} cannot be selected "
                "for a work plan"
            )
        max_position = (
            await self.db.execute(
                select(func.max(SurfacePlannedWork.position)).where(
                    SurfacePlannedWork.work_plan_id == plan.id
                )
            )
        ).scalar_one()
        next_position = 0 if max_position is None else max_position + 1

        work = SurfacePlannedWork(
            work_plan_id=plan.id,
            price_item_id=price_item.id,
            position=next_position,
        )
        self.db.add(work)
        await self.db.flush()
        return work

    async def _fetch_plan(self, surface_id: uuid.UUID) -> SurfaceWorkPlan | None:
        stmt = (
            select(SurfaceWorkPlan)
            .where(SurfaceWorkPlan.surface_id == surface_id)
            .options(
                selectinload(SurfaceWorkPlan.planned_works).selectinload(
                    SurfacePlannedWork.price_item
                )
            )
            .execution_options(populate_existing=True)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_work_plan(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        surface_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> SurfaceWorkPlan | None:
        """Return the surface's plan (with ordered works) or None when unplanned."""
        await self._ensure_surface_owned(project_id, room_id, surface_id, owner_id)
        return await self._fetch_plan(surface_id)

    async def set_plan(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        surface_id: uuid.UUID,
        owner_id: uuid.UUID,
        *,
        substrate: Substrate,
        quality_target: QualityLevel | None = None,
        planned_works: list[OrderedPriceItemSelection] | None = None,
    ) -> SurfaceWorkPlan:
        """Create or fully replace the surface's plan in one atomic commit.

        Setting a plan is an explicit owner action: the substrate and quality
        target are validated together (S/Q scale compatibility reuses the
        Stage 6 rule), the works replace any previous planning, and an
        incompatible current quality target on a substrate change must be
        cleared explicitly rather than silently converted.
        """
        await self._ensure_surface_owned(project_id, room_id, surface_id, owner_id)
        assert_quality_scale_valid(substrate, quality_target)

        selection = planned_works or []
        plan = await self._fetch_plan(surface_id)
        existing_counts = (
            Counter(work.price_item_id for work in plan.planned_works)
            if plan is not None
            else Counter()
        )
        validated = await self._resolve_owned_items(
            owner_id, selection, existing_counts
        )

        if plan is None:
            plan = SurfaceWorkPlan(
                surface_id=surface_id,
                substrate=substrate,
                quality_target=quality_target,
            )
            self.db.add(plan)
        else:
            plan.substrate = substrate
            plan.quality_target = quality_target
        await self._rewrite_works(plan, validated)
        await self.db.commit()
        return await self._fetch_plan(surface_id)

    async def replace_planned_works(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        surface_id: uuid.UUID,
        owner_id: uuid.UUID,
        *,
        planned_works: list[OrderedPriceItemSelection],
    ) -> SurfaceWorkPlan:
        """Replace only the works of an existing plan (substrate/quality kept).

        Nothing changes when the plan does not exist yet — the caller must
        establish the plan configuration first, then order its works.
        """
        await self._ensure_surface_owned(project_id, room_id, surface_id, owner_id)
        plan = await self._fetch_plan(surface_id)
        if plan is None:
            raise SurfaceWorkPlanNotFoundError(
                f"Surface {surface_id} has no work plan yet"
            )

        existing_counts = Counter(
            work.price_item_id for work in plan.planned_works
        )
        validated = await self._resolve_owned_items(
            owner_id, planned_works, existing_counts
        )
        await self._rewrite_works(plan, validated)
        await self.db.commit()
        return await self._fetch_plan(surface_id)

    async def apply_to_room_walls(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        source_surface_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> list[SurfaceWorkPlan]:
        """Atomically copy a source wall's planning configuration to every
        other active WALL surface in the same room (Stage 10B.2).

        Only planning configuration is copied: substrate, quality target, and
        the ordered planned works. Geometry, openings/deductions, inspections,
        findings, risks, photos, archive state, and every Price Book row are
        never touched. Each target receives its own persisted plan rows, so the
        walls stay independent afterwards. The whole batch commits together or
        not at all — every source-side validation runs before any mutation, so
        a failed apply cannot leave half the room updated.
        """
        source = await self._ensure_surface_owned(
            project_id, room_id, source_surface_id, owner_id
        )
        if source.surface_type != SurfaceType.WALL:
            raise SurfaceWorkPlanValidationError(
                "apply-to-room-walls requires a WALL source surface"
            )
        if source.is_archived:
            raise SurfaceWorkPlanValidationError(
                "an archived surface cannot start apply-to-room-walls"
            )
        source_plan = await self._fetch_plan(source.id)
        if source_plan is None:
            raise SurfaceWorkPlanNotFoundError(
                f"Surface {source.id} has no work plan to apply"
            )

        # New target rows must never silently reference an archived catalog
        # item; NULL commercial prices are fine (planning is independent of
        # commercial completeness). The source plan itself is never mutated.
        validated_items: list[PriceItem] = []
        for work in source_plan.planned_works:
            item = work.price_item
            if item is None or item.is_archived:
                raise SurfaceWorkPlanValidationError(
                    f"Source plan references an archived price item "
                    f"{work.price_item_id}; update the source plan first"
                )
            validated_items.append(item)

        targets = (
            await self.db.execute(
                select(Surface)
                .where(
                    Surface.room_id == source.room_id,
                    Surface.surface_type == SurfaceType.WALL,
                    Surface.id != source.id,
                    Surface.is_archived.is_(False),
                )
                .order_by(Surface.position.nulls_last(), Surface.id)
            )
        ).scalars().all()

        target_plans: list[SurfaceWorkPlan] = []
        for target in targets:
            target_plan = await self._fetch_plan(target.id)
            if target_plan is None:
                target_plan = SurfaceWorkPlan(
                    surface_id=target.id,
                    substrate=source_plan.substrate,
                    quality_target=source_plan.quality_target,
                )
                self.db.add(target_plan)
            else:
                target_plan.substrate = source_plan.substrate
                target_plan.quality_target = source_plan.quality_target
            await self._rewrite_works(target_plan, validated_items)
            target_plans.append(target_plan)

        await self.db.commit()
        return [await self._fetch_plan(p.surface_id) for p in target_plans]