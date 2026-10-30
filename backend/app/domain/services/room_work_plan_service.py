"""The plan of the works of a whole room (V2-5; docs/V2_5_PLAN_RU.md).

The room keeps one plan (the substrate, the class, the works of the walls and the works of the ceiling). Saving it brings every wall and the ceiling that
has no plan, or whose plan follows the room's, to the same works; a surface with a plan of its own and a surface whose execution has started are left as
they are, and the answer says which. Nothing that was done is ever erased. The estimate and everything else read the ordinary plans of the surfaces.
"""
import uuid
from decimal import Decimal
from collections import defaultdict

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes, selectinload

from app.domain.exceptions import (
    PriceItemNotFoundError,
    RoomNotFoundError,
    RoomPlanError,
    SurfaceWorkPlanValidationError,
)
from app.domain.rules.inspection_rules import assert_quality_scale_valid
from app.domain.rules.work_execution_rules import PROTECTED_STATUSES
from app.domain.services.canonical_planes import find_active_plane_surface
from app.domain.services.work_plan_service import SurfaceWorkPlanService
from app.models.price_item import PriceItem
from app.models.project import Project
from app.models.room import Room
from app.models.room_work_plan import RoomPlannedWork, RoomPlanTarget, RoomWorkPlan
from app.models.surface import Surface, SurfaceType
from app.models.work_execution import SurfaceWorkExecution
from app.models.work_plan import SurfaceWorkPlan
from app.schemas.room_work_plan import (
    RoomWorkPlanRead,
    RoomWorkPlanResponse,
    RoomWorkPlanWrite,
    SurfaceOutcome,
    SurfacePlanState,
)
from app.schemas.work_plan import OrderedPriceItemSelection


class RoomWorkPlanService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # -- reading ---------------------------------------------------------------------------------------------------------------------

    async def _room(self, project_id: uuid.UUID, room_id: uuid.UUID, owner_id: uuid.UUID) -> Room:
        stmt = select(Room).join(Project, Project.id == Room.project_id).where(Room.id == room_id, Room.project_id == project_id, Project.owner_id == owner_id)
        room = (await self.db.execute(stmt)).scalar_one_or_none()
        if room is None:
            raise RoomNotFoundError(f"Room {room_id} not found")
        return room

    async def _plan(self, room_id: uuid.UUID) -> RoomWorkPlan | None:
        stmt = (
            select(RoomWorkPlan).where(RoomWorkPlan.room_id == room_id).options(selectinload(RoomWorkPlan.works)).execution_options(populate_existing=True)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def _targets(self, room_id: uuid.UUID) -> list[Surface]:
        """The active walls (in the order of the room) and the ceiling: the surfaces a room plan can reach."""
        walls = (
            await self.db.execute(
                select(Surface)
                .where(Surface.room_id == room_id, Surface.surface_type == SurfaceType.WALL, Surface.is_archived.is_(False))
                .order_by(Surface.position.asc().nulls_last(), Surface.created_at.asc())
            )
        ).scalars()
        found = list(walls)
        ceiling = await find_active_plane_surface(self.db, room_id, SurfaceType.CEILING)
        if ceiling is not None:
            found.append(ceiling)
        return found

    async def _surface_plans(self, surface_ids: list[uuid.UUID]) -> dict[uuid.UUID, SurfaceWorkPlan]:
        if not surface_ids:
            return {}
        rows = (
            await self.db.execute(
                select(SurfaceWorkPlan).where(SurfaceWorkPlan.surface_id.in_(surface_ids)).options(selectinload(SurfaceWorkPlan.planned_works))
                .execution_options(populate_existing=True)
            )
        ).scalars()
        return {row.surface_id: row for row in rows}

    async def _started(self, plan: SurfaceWorkPlan | None) -> bool:
        if plan is None or not plan.planned_works:
            return False
        keys = [work.occurrence_key for work in plan.planned_works]
        found = await self.db.execute(
            select(SurfaceWorkExecution.occurrence_key).where(SurfaceWorkExecution.occurrence_key.in_(keys), SurfaceWorkExecution.status.in_(PROTECTED_STATUSES)).limit(1)
        )
        return found.first() is not None

    @staticmethod
    def _read(plan: RoomWorkPlan) -> RoomWorkPlanRead:
        by_target: dict[str, list[uuid.UUID]] = defaultdict(list)
        for work in sorted(plan.works, key=lambda w: (w.target, w.position)):
            by_target[work.target].append(work.price_item_id)
        return RoomWorkPlanRead(
            id=plan.id, room_id=plan.room_id, substrate=plan.substrate, quality_target=plan.quality_target,
            walls=by_target[RoomPlanTarget.WALLS.value], ceiling=by_target[RoomPlanTarget.CEILING.value], updated_at=plan.updated_at,
        )

    async def _states(self, room_id: uuid.UUID) -> list[SurfacePlanState]:
        targets = await self._targets(room_id)
        plans = await self._surface_plans([s.id for s in targets])
        states = []
        for surface in targets:
            plan = plans.get(surface.id)
            state = "NONE" if plan is None else ("FOLLOWS" if plan.follows_room_plan else "OWN")
            states.append(SurfacePlanState(surface_id=surface.id, name=surface.name, surface_type=surface.surface_type, state=state, started=await self._started(plan)))
        return states

    async def get(self, project_id: uuid.UUID, room_id: uuid.UUID, owner_id: uuid.UUID) -> RoomWorkPlanResponse:
        await self._room(project_id, room_id, owner_id)
        plan = await self._plan(room_id)
        return RoomWorkPlanResponse(plan=self._read(plan) if plan else None, surfaces=await self._states(room_id))

    # -- saving ----------------------------------------------------------------------------------------------------------------------

    async def _check_items(self, owner_id: uuid.UUID, ids: list[uuid.UUID]) -> None:
        wanted = set(ids)
        if not wanted:
            return
        found = {
            row.id: row
            for row in (await self.db.execute(select(PriceItem).where(PriceItem.owner_id == owner_id, PriceItem.id.in_(wanted)))).scalars()
        }
        missing = wanted - set(found)
        if missing:
            raise PriceItemNotFoundError(f"price items not found: {sorted(str(i) for i in missing)}")
        archived = [str(i) for i, row in found.items() if row.is_archived]
        if archived:
            raise SurfaceWorkPlanValidationError(f"archived price items cannot be selected: {sorted(archived)}")

    async def _bring(
        self, project_id: uuid.UUID, room_id: uuid.UUID, owner_id: uuid.UUID, surface: Surface, plan: RoomWorkPlan, existing: SurfaceWorkPlan | None
    ) -> str:
        """One surface: made / brought to the plan of the room, or left alone. Returns the outcome."""
        target = RoomPlanTarget.CEILING if surface.surface_type == SurfaceType.CEILING else RoomPlanTarget.WALLS
        items = [w.price_item_id for w in sorted(plan.works, key=lambda w: w.position) if w.target == target.value]
        if existing is not None and not existing.follows_room_plan:
            return "SKIPPED_OWN"
        if existing is not None and await self._started(existing):
            return "SKIPPED_STARTED"
        if existing is None and not items:
            return "SKIPPED_EMPTY"
        # the keys of the works that stay are kept: the same price row in the same turn is the same occurrence
        # (and its quantity of metres / pieces, owner 2026-10-30)
        spare: dict[uuid.UUID, list[tuple[uuid.UUID, Decimal | None]]] = defaultdict(list)
        if existing is not None:
            for work in sorted(existing.planned_works, key=lambda w: w.position):
                spare[work.price_item_id].append((work.occurrence_key, work.quantity))
        selection = []
        for item in items:
            key, quantity = spare[item].pop(0) if spare[item] else (None, None)
            selection.append(OrderedPriceItemSelection(price_item_id=item, occurrence_key=key, quantity=quantity))
        await SurfaceWorkPlanService(self.db).set_plan(
            project_id, room_id, surface.id, owner_id,
            substrate=plan.substrate, quality_target=plan.quality_target, planned_works=selection, follows_room_plan=True,
        )
        return "CREATED" if existing is None else "UPDATED"

    async def put(self, project_id: uuid.UUID, room_id: uuid.UUID, owner_id: uuid.UUID, payload: RoomWorkPlanWrite) -> RoomWorkPlanResponse:
        await self._room(project_id, room_id, owner_id)
        assert_quality_scale_valid(payload.substrate, payload.quality_target)
        await self._check_items(owner_id, [*payload.walls, *payload.ceiling])
        plan = await self._plan(room_id)
        if plan is None:
            plan = RoomWorkPlan(room_id=room_id, substrate=payload.substrate, quality_target=payload.quality_target, works=[])
            self.db.add(plan)
            await self.db.flush()
        else:
            plan.substrate, plan.quality_target = payload.substrate, payload.quality_target
            # an immediate statement, then the loaded list is forgotten (not cleared: that would walk the delete-orphan cascade a second time)
            await self.db.execute(delete(RoomPlannedWork).where(RoomPlannedWork.room_plan_id == plan.id))
            attributes.set_committed_value(plan, "works", [])
        for target, ids in ((RoomPlanTarget.WALLS, payload.walls), (RoomPlanTarget.CEILING, payload.ceiling)):
            for position, item_id in enumerate(ids):
                self.db.add(RoomPlannedWork(room_plan_id=plan.id, target=target.value, price_item_id=item_id, position=position))
        await self.db.commit()
        plan = await self._plan(room_id)
        assert plan is not None

        targets = await self._targets(room_id)
        existing = await self._surface_plans([s.id for s in targets])
        results = []
        for surface in targets:
            outcome = await self._bring(project_id, room_id, owner_id, surface, plan, existing.get(surface.id))
            results.append(SurfaceOutcome(surface_id=surface.id, name=surface.name, surface_type=surface.surface_type, outcome=outcome))
        return RoomWorkPlanResponse(plan=self._read(plan), surfaces=await self._states(room_id), results=results)

    async def follow(self, project_id: uuid.UUID, room_id: uuid.UUID, surface_id: uuid.UUID, owner_id: uuid.UUID) -> SurfaceOutcome:
        """"Back to the plan of the room" for one surface (a plan of its own is replaced). Refused for a surface that has started."""
        await self._room(project_id, room_id, owner_id)
        plan = await self._plan(room_id)
        if plan is None:
            raise RoomPlanError("ROOM_PLAN_MISSING", "the room has no plan yet")
        surface = next((s for s in await self._targets(room_id) if s.id == surface_id), None)
        if surface is None:
            raise RoomPlanError("ROOM_PLAN_SURFACE", "the plan of a room reaches the walls and the ceiling of that room only")
        existing = (await self._surface_plans([surface_id])).get(surface_id)
        if existing is not None and await self._started(existing):
            raise RoomPlanError("ROOM_PLAN_STARTED", "the work on this surface has started; its plan is not replaced")
        if existing is not None:
            existing.follows_room_plan = True  # a plan of its own is brought to the plan of the room (as a follower)
        outcome = await self._bring(project_id, room_id, owner_id, surface, plan, existing)
        return SurfaceOutcome(surface_id=surface.id, name=surface.name, surface_type=surface.surface_type, outcome=outcome)

