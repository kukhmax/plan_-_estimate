from collections import defaultdict
from decimal import Decimal
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import ProjectNotFoundError, RoomNotFoundError
from app.domain.rules.room_geometry import (
    AREA_PRECISION,
    PlaneAreaTotals,
    RoomGeometryResult,
    WallDerivedTotals,
    calculate_plane_base_area,
    calculate_plane_totals,
    calculate_room_geometry,
    calculate_wall_derived_totals,
    resolve_room_totals,
)
from app.models.area_segment import AreaOperation, AreaPlane, AreaSegment
from app.models.opening import Opening
from app.models.project import Project
from app.models.room import Room
from app.models.surface import Surface, SurfaceType
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

    async def _load_wall_totals(
        self,
        room_id: uuid.UUID,
        deduction: Decimal,
    ) -> WallDerivedTotals | None:
        wall_stmt = select(Surface.width, Surface.height).where(
            Surface.room_id == room_id,
            Surface.is_archived.is_(False),
            Surface.surface_type == SurfaceType.WALL,
            Surface.width.is_not(None),
            Surface.height.is_not(None),
        )
        wall_result = await self.db.execute(wall_stmt)
        wall_pairs = [
            (Decimal(row[0]), Decimal(row[1])) for row in wall_result.all()
        ]
        return calculate_wall_derived_totals(wall_pairs, deduction)

    @staticmethod
    def _build_calculations(
        geometry: RoomGeometryResult | None,
        wall_totals: WallDerivedTotals | None,
        deduction: Decimal,
        floor_totals: PlaneAreaTotals | None = None,
        ceiling_totals: PlaneAreaTotals | None = None,
    ) -> RoomCalculations | None:
        resolved = resolve_room_totals(
            geometry,
            wall_totals,
            deduction,
            floor_segments=floor_totals,
            ceiling_segments=ceiling_totals,
        )
        if resolved is None:
            return None
        return RoomCalculations(
            floor_area=resolved.floor_area,
            ceiling_area=resolved.ceiling_area,
            total_wall_area=resolved.total_wall_area,
            wall_area_length=resolved.wall_area_length,
            wall_area_width=resolved.wall_area_width,
            perimeter=resolved.perimeter,
            total_deduction_area=resolved.total_deduction_area,
            net_wall_area=resolved.net_wall_area,
            wall_count=resolved.wall_count,
        )

    async def _load_plane_segment_totals(
        self,
        room_id: uuid.UUID,
        base_area: Decimal | None,
    ) -> dict[AreaPlane, PlaneAreaTotals]:
        segment_stmt = select(
            AreaSegment.plane,
            AreaSegment.operation,
            AreaSegment.width,
            AreaSegment.height,
        ).where(
            AreaSegment.room_id == room_id,
            AreaSegment.is_archived.is_(False),
        )
        result = await self.db.execute(segment_stmt)

        pairs_by_plane: dict[AreaPlane, list[tuple[AreaOperation, Decimal]]] = defaultdict(list)
        for plane, operation, width, height in result.all():
            area = (Decimal(width) * Decimal(height)).quantize(AREA_PRECISION)
            pairs_by_plane[plane].append((operation, area))

        totals: dict[AreaPlane, PlaneAreaTotals] = {}
        for plane in (AreaPlane.FLOOR, AreaPlane.CEILING):
            pairs = pairs_by_plane.get(plane)
            if not pairs:
                continue
            try:
                totals[plane] = calculate_plane_totals(pairs, base_area)
            except ValueError as exc:
                raise RoomNotFoundError(
                    f"Plane {plane.value} has negative net area: {exc}"
                ) from exc
        return totals

    async def _attach_calculations(self, room: Room) -> None:
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

        wall_totals = await self._load_wall_totals(room.id, deduction)
        plane_totals = await self._load_plane_segment_totals(
            room.id, calculate_plane_base_area(room.length, room.width)
        )
        geometry = calculate_room_geometry(room.length, room.width, room.height)
        room.calculations = self._build_calculations(
            geometry,
            wall_totals,
            deduction,
            floor_totals=plane_totals.get(AreaPlane.FLOOR),
            ceiling_totals=plane_totals.get(AreaPlane.CEILING),
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

        wall_stmt = (
            select(Surface.room_id, Surface.width, Surface.height)
            .join(Room, Surface.room_id == Room.id)
            .where(
                Room.project_id == project_id,
                Surface.is_archived.is_(False),
                Surface.surface_type == SurfaceType.WALL,
                Surface.width.is_not(None),
                Surface.height.is_not(None),
            )
        )
        if not include_archived:
            wall_stmt = wall_stmt.where(Room.is_archived.is_(False))
        wall_rows = (await self.db.execute(wall_stmt)).all()

        wall_pairs_by_room: dict[uuid.UUID, list[tuple[Decimal, Decimal]]] = defaultdict(list)
        for room_id, width, height in wall_rows:
            wall_pairs_by_room[room_id].append((Decimal(width), Decimal(height)))

        segment_stmt = (
            select(
                AreaSegment.room_id,
                AreaSegment.plane,
                AreaSegment.operation,
                AreaSegment.width,
                AreaSegment.height,
            )
            .join(Room, AreaSegment.room_id == Room.id)
            .where(
                Room.project_id == project_id,
                AreaSegment.is_archived.is_(False),
            )
        )
        if not include_archived:
            segment_stmt = segment_stmt.where(Room.is_archived.is_(False))
        segment_rows = (await self.db.execute(segment_stmt)).all()

        segment_pairs_by_room: dict[
            uuid.UUID, dict[AreaPlane, list[tuple[AreaOperation, Decimal]]]
        ] = defaultdict(lambda: defaultdict(list))
        for room_id, plane, operation, width, height in segment_rows:
            area = (Decimal(width) * Decimal(height)).quantize(AREA_PRECISION)
            segment_pairs_by_room[room_id][plane].append((operation, area))

        stmt = stmt.order_by(Room.created_at.desc())
        result = await self.db.execute(stmt)
        rows = result.all()

        items = []
        for room, deduction_sum in rows:
            deduction = Decimal(deduction_sum).quantize(Decimal("0.001"))
            geometry = calculate_room_geometry(room.length, room.width, room.height)
            pairs = wall_pairs_by_room.get(room.id)
            wall_totals: WallDerivedTotals | None = None
            if pairs:
                wall_totals = calculate_wall_derived_totals(pairs, deduction)

            plane_segments = segment_pairs_by_room.get(room.id, {})
            base_area = calculate_plane_base_area(room.length, room.width)
            floor_totals = (
                calculate_plane_totals(plane_segments.get(AreaPlane.FLOOR, []), base_area)
                if plane_segments.get(AreaPlane.FLOOR)
                else None
            )
            ceiling_totals = (
                calculate_plane_totals(plane_segments.get(AreaPlane.CEILING, []), base_area)
                if plane_segments.get(AreaPlane.CEILING)
                else None
            )

            room.calculations = self._build_calculations(
                geometry,
                wall_totals,
                deduction,
                floor_totals=floor_totals,
                ceiling_totals=ceiling_totals,
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
