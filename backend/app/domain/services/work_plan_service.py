"""Surface Work Plan domain service (Stage 10B.1).

A SurfaceWorkPlan is the planning configuration for exactly one Surface:
the substrate, the agreed quality target, and an ordered list of Price Book
references. The plan never snapshots prices and never mutates a PriceItem;
archiving a PriceItem excludes it from future selection but leaves existing
plan rows untouched. Ownership always resolves through
Surface -> Room -> Project -> Owner, so no tenancy columns exist on the plan.
"""
import uuid

from sqlalchemy import delete, select
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
from app.models.surface import Surface
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
    ) -> list[PriceItem]:
        """Validate every selection row and return it in the given order.

        Each referenced PriceItem must exist under the owner and must not be
        archived. Duplicate references are preserved — the architecture allows
        the same PriceItem more than once (e.g. two separate coat rows).
        """
        if not selection:
            return []
        ids = [row.price_item_id for row in selection]
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
            if item.is_archived:
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
        validated = await self._resolve_owned_items(owner_id, selection)

        plan = await self._fetch_plan(surface_id)
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

        validated = await self._resolve_owned_items(owner_id, planned_works)
        await self._rewrite_works(plan, validated)
        await self.db.commit()
        return await self._fetch_plan(surface_id)