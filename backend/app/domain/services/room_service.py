from decimal import Decimal
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import ProjectNotFoundError, RoomNotFoundError
from app.domain.rules.room_geometry import (
    calculate_room_aggregate_totals,
    calculate_room_geometry,
)
from app.models.opening import Opening
from app.models.project import Project
from app.models.room import Room
from app.models.surface import Surface
from app.schemas.room import RoomCalculations, RoomCreate, RoomUpdate


class RoomService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _ensure_project_owned(
        self,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> None:
        stmt = select(Project.id).where(
            Project.id == project_id,
            Project.owner_id == owner_id,
        )
        result = await self.db.execute(stmt)
        if result.scalar_one_or_none() is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")

    async def _attach_calculations(self, room: Room) -> None:
        if room.length is not None and room.width is not None and room.height is not None:
            deduction_stmt = (
                select(
                    func.coalesce(
                        func.sum(Opening.width * Opening.height * Opening.quantity), 0
                    )
                )
                .join(Surface, Opening.surface_id == Surface.id)
                .where(
                    Surface.room_id == room.id,
                    Surface.is_archived.is_(False),
                    Opening.is_archived.is_(False),
                )
            )
            deduction_res = await self.db.execute(deduction_stmt)
            deduction = Decimal(deduction_res.scalar_one()).quantize(Decimal("0.001"))
            geom = calculate_room_geometry(room.length, room.width, room.height)
            if geom is not None:
                totals = calculate_room_aggregate_totals(geom, deduction)
                if totals is not None:
                    room.calculations = RoomCalculations(
                        floor_area=totals.floor_gross_area,
                        ceiling_area=totals.ceiling_gross_area,
                        total_wall_area=totals.total_wall_gross_area,
                        wall_area_length=geom.wall_area_length,
                        wall_area_width=geom.wall_area_width,
                        perimeter=totals.perimeter,
                        total_deduction_area=totals.total_opening_deduction_area,
                        net_wall_area=totals.total_wall_net_area,
                    )

    async def list_rooms(
        self,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        *,
        include_archived: bool = False,
    ) -> tuple[list[Room], int]:
        await self._ensure_project_owned(project_id, owner_id)

        deduction_subq = (
            select(
                Surface.room_id,
                func.coalesce(
                    func.sum(Opening.width * Opening.height * Opening.quantity), 0
                ).label("deduction_sum"),
            )
            .join(Surface, Opening.surface_id == Surface.id)
            .where(
                Opening.is_archived.is_(False),
                Surface.is_archived.is_(False),
            )
            .group_by(Surface.room_id)
            .subquery()
        )

        stmt = (
            select(Room, func.coalesce(deduction_subq.c.deduction_sum, 0))
            .outerjoin(deduction_subq, Room.id == deduction_subq.c.room_id)
            .where(Room.project_id == project_id)
        )
        if not include_archived:
            stmt = stmt.where(Room.is_archived.is_(False))

        count_stmt = select(func.count()).select_from(
            select(Room.id)
            .where(Room.project_id == project_id)
            .where(Room.is_archived.is_(False) if not include_archived else True)
            .subquery()
        )
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar_one()

        stmt = stmt.order_by(Room.created_at.desc())
        result = await self.db.execute(stmt)
        rows = result.all()

        items = []
        for room, deduction_sum in rows:
            if room.length is not None and room.width is not None and room.height is not None:
                geom = calculate_room_geometry(room.length, room.width, room.height)
                if geom is not None:
                    deduction = Decimal(deduction_sum).quantize(Decimal("0.001"))
                    totals = calculate_room_aggregate_totals(geom, deduction)
                    if totals is not None:
                        room.calculations = RoomCalculations(
                            floor_area=totals.floor_gross_area,
                            ceiling_area=totals.ceiling_gross_area,
                            total_wall_area=totals.total_wall_gross_area,
                            wall_area_length=geom.wall_area_length,
                            wall_area_width=geom.wall_area_width,
                            perimeter=totals.perimeter,
                            total_deduction_area=totals.total_opening_deduction_area,
                            net_wall_area=totals.total_wall_net_area,
                        )
            items.append(room)

        return items, total

    async def create_room(
        self,
        project_id: uuid.UUID,
        payload: RoomCreate,
        owner_id: uuid.UUID,
    ) -> Room:
        await self._ensure_project_owned(project_id, owner_id)

        room = Room(
            project_id=project_id,
            name=payload.name,
            description=payload.description,
            length=payload.length,
            width=payload.width,
            height=payload.height,
        )
        self.db.add(room)
        await self.db.commit()
        await self.db.refresh(room)
        await self._attach_calculations(room)
        return room

    async def get_room(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> Room:
        await self._ensure_project_owned(project_id, owner_id)

        stmt = select(Room).where(
            Room.id == room_id,
            Room.project_id == project_id,
        )
        result = await self.db.execute(stmt)
        room = result.scalar_one_or_none()
        if not room:
            raise RoomNotFoundError(f"Room {room_id} not found")
        await self._attach_calculations(room)
        return room

    async def update_room(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        payload: RoomUpdate,
        owner_id: uuid.UUID,
    ) -> Room:
        room = await self.get_room(project_id, room_id, owner_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(room, field, value)

        await self.db.commit()
        await self.db.refresh(room)
        await self._attach_calculations(room)
        return room

    async def archive_room(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> Room:
        room = await self.get_room(project_id, room_id, owner_id)
        room.is_archived = True
        await self.db.commit()
        await self.db.refresh(room)
        await self._attach_calculations(room)
        return room

    async def restore_room(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> Room:
        room = await self.get_room(project_id, room_id, owner_id)
        room.is_archived = False
        await self.db.commit()
        await self.db.refresh(room)
        await self._attach_calculations(room)
        return room
