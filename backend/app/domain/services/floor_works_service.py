"""The works measured by the floor of a room live in the plan of the floor (owner 2026-10-31).

"Zabezpieczenie podłóg" planned on every wall was a line on every wall with no metres of its own. Here such a work is taken off the walls and the
ceiling of the room (and off the plan of the room) and put once into the plan of the floor, where the estimate measures it by the floor's area.
An occurrence whose execution has started stays where it is (its record is the owner's).
"""
import uuid
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.domain.exceptions import RoomNotFoundError
from app.domain.rules.floor_works import is_floor_measured
from app.domain.rules.work_execution_rules import PROTECTED_STATUSES
from app.domain.services.canonical_planes import ensure_canonical_plane_surfaces
from app.domain.services.work_plan_service import SurfaceWorkPlanService
from app.models.checklist import Substrate
from app.models.price_item import PriceItem
from app.models.project import Project
from app.models.room import Room
from app.models.room_work_plan import RoomPlannedWork, RoomWorkPlan
from app.models.surface import Surface, SurfaceType
from app.models.work_execution import SurfaceWorkExecution
from app.models.work_plan import SurfacePlannedWork, SurfaceWorkPlan


@dataclass(frozen=True)
class FloorWorksResult:
    moved: int  # occurrences taken off the walls and the ceiling
    added: int  # works added to the plan of the floor (0 when it had them already)
    floor_surface_id: uuid.UUID


class FloorWorksService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _room(self, project_id: uuid.UUID, room_id: uuid.UUID, owner_id: uuid.UUID) -> Room:
        stmt = select(Room).join(Project, Project.id == Room.project_id).where(Room.id == room_id, Room.project_id == project_id, Project.owner_id == owner_id)
        room = (await self.db.execute(stmt)).scalar_one_or_none()
        if room is None:
            raise RoomNotFoundError(f"Room {room_id} not found")
        return room

    async def place_on_floor(
        self, project_id: uuid.UUID, room_id: uuid.UUID, owner_id: uuid.UUID, extra_items: list[PriceItem] | None = None
    ) -> FloorWorksResult:
        """Move the floor-measured works of the walls and the ceiling of the room into the plan of the floor (once each); `extra_items` are put
        there as well (the plan of a room that names them). Commits."""
        await self._room(project_id, room_id, owner_id)
        floor, _ceiling = await ensure_canonical_plane_surfaces(self.db, room_id)
        await self.db.flush()

        plans = list(
            (
                await self.db.execute(
                    select(SurfaceWorkPlan)
                    .join(Surface, Surface.id == SurfaceWorkPlan.surface_id)
                    .where(Surface.room_id == room_id, Surface.is_archived.is_(False), Surface.surface_type != SurfaceType.FLOOR)
                    .options(selectinload(SurfaceWorkPlan.planned_works).selectinload(SurfacePlannedWork.price_item))
                    .execution_options(populate_existing=True)
                )
            ).scalars()
        )
        found = [w for plan in plans for w in plan.planned_works if is_floor_measured(w.price_item.code, w.price_item.unit)]
        started = set()
        if found:
            started = set(
                (
                    await self.db.execute(
                        select(SurfaceWorkExecution.occurrence_key).where(
                            SurfaceWorkExecution.occurrence_key.in_([w.occurrence_key for w in found]), SurfaceWorkExecution.status.in_(PROTECTED_STATUSES)
                        )
                    )
                ).scalars()
            )
        wanted: dict[uuid.UUID, PriceItem] = {item.id: item for item in (extra_items or []) if is_floor_measured(item.code, item.unit)}
        moved = 0
        for plan in plans:
            works = list(plan.planned_works)  # read once: the collection is not loaded again after the deletes
            leaving = [w for w in works if w in found and w.occurrence_key not in started]
            if not leaving:
                continue
            for work in leaving:
                wanted.setdefault(work.price_item_id, work.price_item)
                await self.db.delete(work)
                moved += 1
            await self.db.flush()
            # the works that stay close the gap, in their order (each moves to a lower, free position)
            for position, work in enumerate(sorted((w for w in works if w not in leaving), key=lambda w: w.position)):
                if work.position != position:
                    work.position = position
                    await self.db.flush()

        # the plan of the room no longer names them for the walls / the ceiling
        room_plan_id = (await self.db.execute(select(RoomWorkPlan.id).where(RoomWorkPlan.room_id == room_id))).scalar_one_or_none()
        if room_plan_id is not None and wanted:
            await self.db.execute(delete(RoomPlannedWork).where(RoomPlannedWork.room_plan_id == room_plan_id, RoomPlannedWork.price_item_id.in_(list(wanted))))

        added = 0
        if wanted:
            plans_service = SurfaceWorkPlanService(self.db)
            await plans_service.lock_plan(floor.id)
            floor_plan = (
                await self.db.execute(
                    select(SurfaceWorkPlan).where(SurfaceWorkPlan.surface_id == floor.id).options(selectinload(SurfaceWorkPlan.planned_works)).execution_options(populate_existing=True)
                )
            ).scalar_one_or_none()
            if floor_plan is None:
                # a floor with no plan yet: "Inne" until the owner picks the substrate of the floor
                floor_plan = SurfaceWorkPlan(surface_id=floor.id, substrate=Substrate.OTHER, quality_target=None)
                self.db.add(floor_plan)
                await self.db.flush()
                has: set[uuid.UUID] = set()
            else:
                has = {w.price_item_id for w in floor_plan.planned_works}
            for item_id, item in wanted.items():
                if item_id in has:
                    continue
                await plans_service.append_one_planned_work_no_commit(floor_plan, item)
                added += 1
        await self.db.commit()
        return FloorWorksResult(moved=moved, added=added, floor_surface_id=floor.id)
