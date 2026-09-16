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
    calculate_reveal,
    calculate_room_geometry,
    calculate_wall_derived_totals,
    resolve_room_totals,
)
from app.models.area_segment import AreaOperation, AreaPlane, AreaSegment
from app.models.opening import Opening, OpeningType
from app.models.project import Project
from app.models.room import Room
from app.models.surface import Surface, SurfaceType
from app.domain.services.canonical_planes import ensure_canonical_plane_surfaces
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
        window_reveal_total_length: Decimal | None = None,
        window_reveal_total_area: Decimal | None = None,
        door_reveal_total_length: Decimal | None = None,
        door_reveal_total_area: Decimal | None = None,
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

        has_window = window_reveal_total_length is not None
        has_door = door_reveal_total_length is not None
        combined_length: Decimal | None = None
        combined_area: Decimal | None = None
        if has_window or has_door:
            combined_length = (
                (window_reveal_total_length or Decimal("0.000"))
                + (door_reveal_total_length or Decimal("0.000"))
            ).quantize(AREA_PRECISION)
            combined_area = (
                (window_reveal_total_area or Decimal("0.000"))
                + (door_reveal_total_area or Decimal("0.000"))
            ).quantize(AREA_PRECISION)

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
            window_reveal_total_length=window_reveal_total_length,
            window_reveal_total_area=window_reveal_total_area,
            door_reveal_total_length=door_reveal_total_length,
            door_reveal_total_area=door_reveal_total_area,
            reveal_total_length=combined_length,
            reveal_total_area=combined_area,
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

    async def _load_reveal_aggregates(
        self,
        room_id: uuid.UUID,
    ) -> tuple[Decimal | None, Decimal | None, Decimal | None, Decimal | None]:
        """Return (window_length, window_area, door_length, door_area) from active reveals."""
        stmt = select(
            Opening.opening_type,
            Opening.width,
            Opening.height,
            Opening.quantity,
            Opening.reveal_depth,
            Opening.reveal_left,
            Opening.reveal_right,
            Opening.reveal_top,
            Opening.reveal_bottom,
        ).join(Surface, Opening.surface_id == Surface.id).where(
            Surface.room_id == room_id,
            Surface.is_archived.is_(False),
            Opening.is_archived.is_(False),
            Opening.reveal_enabled.is_(True),
            Opening.opening_type.in_([OpeningType.WINDOW, OpeningType.DOOR]),
        )
        result = await self.db.execute(stmt)
        rows = result.all()

        window_length = Decimal("0.000")
        window_area = Decimal("0.000")
        door_length = Decimal("0.000")
        door_area = Decimal("0.000")
        has_window = False
        has_door = False

        for otype, width, height, qty, depth, left, right, top, bottom in rows:
            if depth is None:
                continue
            rev = calculate_reveal(
                Decimal(str(width)),
                Decimal(str(height)),
                Decimal(str(depth)),
                bool(left),
                bool(right),
                bool(top),
                bool(bottom),
                int(qty),
            )
            if rev is None:
                continue
            if OpeningType(otype) == OpeningType.WINDOW:
                window_length += rev.total_length
                window_area += rev.total_area
                has_window = True
            else:
                door_length += rev.total_length
                door_area += rev.total_area
                has_door = True

        return (
            window_length.quantize(AREA_PRECISION) if has_window else None,
            window_area.quantize(AREA_PRECISION) if has_window else None,
            door_length.quantize(AREA_PRECISION) if has_door else None,
            door_area.quantize(AREA_PRECISION) if has_door else None,
        )

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
        w_len, w_area, d_len, d_area = await self._load_reveal_aggregates(room.id)
        room.calculations = self._build_calculations(
            geometry,
            wall_totals,
            deduction,
            floor_totals=plane_totals.get(AreaPlane.FLOOR),
            ceiling_totals=plane_totals.get(AreaPlane.CEILING),
            window_reveal_total_length=w_len,
            window_reveal_total_area=w_area,
            door_reveal_total_length=d_len,
            door_reveal_total_area=d_area,
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

        reveal_stmt = (
            select(
                Surface.room_id,
                Opening.opening_type,
                Opening.width,
                Opening.height,
                Opening.quantity,
                Opening.reveal_depth,
                Opening.reveal_left,
                Opening.reveal_right,
                Opening.reveal_top,
                Opening.reveal_bottom,
            )
            .join(Surface, Opening.surface_id == Surface.id)
            .join(Room, Surface.room_id == Room.id)
            .where(
                Room.project_id == project_id,
                Surface.is_archived.is_(False),
                Opening.is_archived.is_(False),
                Opening.reveal_enabled.is_(True),
                Opening.opening_type.in_([OpeningType.WINDOW, OpeningType.DOOR]),
            )
        )
        if not include_archived:
            reveal_stmt = reveal_stmt.where(Room.is_archived.is_(False))
        reveal_rows = (await self.db.execute(reveal_stmt)).all()

        RevealAccum = dict[str, dict[str, Decimal]]
        reveal_by_room: dict[uuid.UUID, RevealAccum] = defaultdict(
            lambda: {
                "w_len": Decimal("0.000"),
                "w_area": Decimal("0.000"),
                "d_len": Decimal("0.000"),
                "d_area": Decimal("0.000"),
            }
        )
        reveal_has_by_room: dict[uuid.UUID, dict[str, bool]] = defaultdict(
            lambda: {"window": False, "door": False}
        )
        for r_room_id, otype, width, height, qty, depth, left, right, top, bottom in reveal_rows:
            if depth is None:
                continue
            rev = calculate_reveal(
                Decimal(str(width)),
                Decimal(str(height)),
                Decimal(str(depth)),
                bool(left),
                bool(right),
                bool(top),
                bool(bottom),
                int(qty),
            )
            if rev is None:
                continue
            acc = reveal_by_room[r_room_id]
            has = reveal_has_by_room[r_room_id]
            if OpeningType(otype) == OpeningType.WINDOW:
                acc["w_len"] += rev.total_length
                acc["w_area"] += rev.total_area
                has["window"] = True
            else:
                acc["d_len"] += rev.total_length
                acc["d_area"] += rev.total_area
                has["door"] = True

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

            acc = reveal_by_room.get(room.id, {})
            has = reveal_has_by_room.get(room.id, {})
            w_len = acc.get("w_len", Decimal("0.000")).quantize(AREA_PRECISION) if has.get("window") else None
            w_area = acc.get("w_area", Decimal("0.000")).quantize(AREA_PRECISION) if has.get("window") else None
            d_len = acc.get("d_len", Decimal("0.000")).quantize(AREA_PRECISION) if has.get("door") else None
            d_area = acc.get("d_area", Decimal("0.000")).quantize(AREA_PRECISION) if has.get("door") else None

            room.calculations = self._build_calculations(
                geometry,
                wall_totals,
                deduction,
                floor_totals=floor_totals,
                ceiling_totals=ceiling_totals,
                window_reveal_total_length=w_len,
                window_reveal_total_area=w_area,
                door_reveal_total_length=d_len,
                door_reveal_total_area=d_area,
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
        # Flush first so room.id exists before the canonical planes reference it;
        # surfaces and the room commit together or not at all.
        await self.db.flush()
        await ensure_canonical_plane_surfaces(self.db, room.id)
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
