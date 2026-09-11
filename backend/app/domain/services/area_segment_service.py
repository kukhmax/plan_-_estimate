from decimal import Decimal
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import (
    AreaSegmentNotFoundError,
    NegativeNetAreaError,
    ProjectNotFoundError,
    RoomNotFoundError,
)
from app.domain.rules.room_geometry import (
    PlaneAreaTotals,
    calculate_plane_base_area,
    calculate_plane_totals,
    calculate_segment_area,
)
from app.models.area_segment import AreaOperation, AreaPlane, AreaSegment
from app.models.project import Project
from app.models.room import Room
from app.schemas.area_segment import AreaSegmentCreate, AreaSegmentUpdate


class AreaSegmentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _ensure_room_owned(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> None:
        project_stmt = select(Project.id).where(
            Project.id == project_id,
            Project.owner_id == owner_id,
        )
        project_result = await self.db.execute(project_stmt)
        if project_result.scalar_one_or_none() is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")

        room_stmt = select(Room.id).where(
            Room.id == room_id,
            Room.project_id == project_id,
        )
        room_result = await self.db.execute(room_stmt)
        if room_result.scalar_one_or_none() is None:
            raise RoomNotFoundError(f"Room {room_id} not found")

    async def _get_active_segments(
        self,
        room_id: uuid.UUID,
        plane: AreaPlane,
        exclude_segment_id: uuid.UUID | None = None,
    ) -> list[AreaSegment]:
        stmt = select(AreaSegment).where(
            AreaSegment.room_id == room_id,
            AreaSegment.plane == plane,
            AreaSegment.is_archived.is_(False),
        )
        if exclude_segment_id is not None:
            stmt = stmt.where(AreaSegment.id != exclude_segment_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def _room_base_area(self, room_id: uuid.UUID) -> Decimal | None:
        stmt = select(Room.length, Room.width).where(Room.id == room_id)
        row = (await self.db.execute(stmt)).one()
        return calculate_plane_base_area(row.length, row.width)

    async def _assert_plane_net_non_negative(
        self,
        room_id: uuid.UUID,
        plane: AreaPlane,
        segments: list[AreaSegment],
        extra: tuple[AreaOperation, Decimal] | None = None,
    ) -> None:
        pairs: list[tuple[AreaOperation, Decimal]] = [
            (segment.operation, calculate_segment_area(segment.width, segment.height))
            for segment in segments
        ]
        if extra is not None:
            pairs.append(extra)
        base_area = await self._room_base_area(room_id)
        try:
            calculate_plane_totals(pairs, base_area)
        except ValueError as exc:
            raise NegativeNetAreaError(str(exc)) from exc

    async def _plane_summaries(
        self,
        room_id: uuid.UUID,
        base_area: Decimal | None,
    ) -> dict[AreaPlane, PlaneAreaTotals | None]:
        """Effective totals per plane for the list response (base + adjustments)."""
        summaries: dict[AreaPlane, PlaneAreaTotals | None] = {}
        for plane in (AreaPlane.FLOOR, AreaPlane.CEILING):
            active = await self._get_active_segments(room_id, plane)
            pairs = [
                (segment.operation, calculate_segment_area(segment.width, segment.height))
                for segment in active
            ]
            summaries[plane] = calculate_plane_totals(pairs, base_area)
        return summaries

    async def list_area_segments(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        owner_id: uuid.UUID,
        *,
        plane: AreaPlane | None = None,
        include_archived: bool = False,
    ) -> tuple[list[AreaSegment], int, dict[AreaPlane, PlaneAreaTotals | None]]:
        await self._ensure_room_owned(project_id, room_id, owner_id)

        stmt = select(AreaSegment).where(AreaSegment.room_id == room_id)
        if plane is not None:
            stmt = stmt.where(AreaSegment.plane == plane)
        if not include_archived:
            stmt = stmt.where(AreaSegment.is_archived.is_(False))

        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar_one()

        stmt = stmt.order_by(
            AreaSegment.plane.asc(),
            AreaSegment.position.asc().nulls_last(),
            AreaSegment.created_at.asc(),
        )
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())

        summaries = await self._plane_summaries(
            room_id, await self._room_base_area(room_id)
        )
        return items, total, summaries

    async def create_area_segment(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        payload: AreaSegmentCreate,
        owner_id: uuid.UUID,
    ) -> AreaSegment:
        await self._ensure_room_owned(project_id, room_id, owner_id)

        active = await self._get_active_segments(room_id, payload.plane)
        new_area = calculate_segment_area(payload.width, payload.height)
        await self._assert_plane_net_non_negative(
            room_id, payload.plane, active, extra=(payload.operation, new_area)
        )

        segment = AreaSegment(
            room_id=room_id,
            plane=payload.plane,
            operation=payload.operation,
            width=payload.width,
            height=payload.height,
            position=payload.position,
            label=payload.label,
        )
        self.db.add(segment)
        await self.db.commit()
        await self.db.refresh(segment)
        return segment

    async def get_area_segment(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        segment_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> AreaSegment:
        await self._ensure_room_owned(project_id, room_id, owner_id)

        stmt = select(AreaSegment).where(
            AreaSegment.id == segment_id,
            AreaSegment.room_id == room_id,
        )
        result = await self.db.execute(stmt)
        segment = result.scalar_one_or_none()
        if not segment:
            raise AreaSegmentNotFoundError(f"Area segment {segment_id} not found")
        return segment

    async def update_area_segment(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        segment_id: uuid.UUID,
        payload: AreaSegmentUpdate,
        owner_id: uuid.UUID,
    ) -> AreaSegment:
        segment = await self.get_area_segment(project_id, room_id, segment_id, owner_id)

        if not segment.is_archived:
            target_operation = (
                payload.operation if payload.operation is not None else segment.operation
            )
            target_width = payload.width if payload.width is not None else segment.width
            target_height = payload.height if payload.height is not None else segment.height
            target_area = calculate_segment_area(target_width, target_height)
            other = await self._get_active_segments(
                room_id, segment.plane, exclude_segment_id=segment_id
            )
            await self._assert_plane_net_non_negative(
                room_id,
                segment.plane,
                other,
                extra=(target_operation, target_area),
            )

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(segment, field, value)

        await self.db.commit()
        await self.db.refresh(segment)
        return segment

    async def archive_area_segment(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        segment_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> AreaSegment:
        segment = await self.get_area_segment(project_id, room_id, segment_id, owner_id)

        if not segment.is_archived:
            remaining = await self._get_active_segments(
                room_id, segment.plane, exclude_segment_id=segment_id
            )
            await self._assert_plane_net_non_negative(room_id, segment.plane, remaining)

        segment.is_archived = True
        await self.db.commit()
        await self.db.refresh(segment)
        return segment

    async def restore_area_segment(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        segment_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> AreaSegment:
        segment = await self.get_area_segment(project_id, room_id, segment_id, owner_id)

        if segment.is_archived:
            active = await self._get_active_segments(room_id, segment.plane)
            segment_area = calculate_segment_area(segment.width, segment.height)
            await self._assert_plane_net_non_negative(
                room_id,
                segment.plane,
                active,
                extra=(segment.operation, segment_area),
            )

        segment.is_archived = False
        await self.db.commit()
        await self.db.refresh(segment)
        return segment
