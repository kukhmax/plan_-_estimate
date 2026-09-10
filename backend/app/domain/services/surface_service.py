from decimal import Decimal
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import (
    DeductionExceedsGrossAreaError,
    ProjectNotFoundError,
    RoomNotFoundError,
    SurfaceNotFoundError,
    WallGenerationConflictError,
    WallGenerationDimensionsMissingError,
)
from app.domain.rules.room_geometry import (
    generate_canonical_walls,
    matches_canonical_wall_set,
)
from app.models.opening import Opening
from app.models.project import Project
from app.models.room import Room
from app.models.surface import Surface, SurfaceType
from app.schemas.surface import SurfaceCreate, SurfaceUpdate


class SurfaceService:
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

    async def list_surfaces(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        owner_id: uuid.UUID,
        *,
        include_archived: bool = False,
    ) -> tuple[list[Surface], int]:
        await self._ensure_room_owned(project_id, room_id, owner_id)

        deduction_subq = (
            select(
                Opening.surface_id,
                func.coalesce(
                    func.sum(Opening.width * Opening.height * Opening.quantity), 0
                ).label("deduction_sum"),
            )
            .where(Opening.is_archived.is_(False))
            .group_by(Opening.surface_id)
            .subquery()
        )

        stmt = (
            select(Surface, func.coalesce(deduction_subq.c.deduction_sum, 0))
            .outerjoin(deduction_subq, Surface.id == deduction_subq.c.surface_id)
            .where(Surface.room_id == room_id)
        )
        if not include_archived:
            stmt = stmt.where(Surface.is_archived.is_(False))

        count_stmt = select(func.count()).select_from(
            select(Surface.id)
            .where(Surface.room_id == room_id)
            .where(Surface.is_archived.is_(False) if not include_archived else True)
            .subquery()
        )
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar_one()

        stmt = stmt.order_by(
            Surface.position.asc().nulls_last(),
            Surface.created_at.desc(),
        )
        result = await self.db.execute(stmt)
        rows = result.all()

        items = []
        for surface, deduction_sum in rows:
            if surface.surface_type == SurfaceType.WALL and surface.width is not None and surface.height is not None:
                surface.deduction_area = Decimal(deduction_sum).quantize(Decimal("0.001"))
            items.append(surface)

        return items, total

    async def generate_walls(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> list[Surface]:
        """Generate the 4 canonical rectangular walls for a room.

        Rules (never destructive):
        - Missing room dimensions -> WallGenerationDimensionsMissingError.
        - No active WALLs -> create exactly the 4 canonical walls.
        - Active WALLs exactly matching the canonical set -> idempotent no-op.
        - Any other configuration -> WallGenerationConflictError, nothing changed.
        """
        await self._ensure_room_owned(project_id, room_id, owner_id)

        room_stmt = select(Room).where(Room.id == room_id)
        room_result = await self.db.execute(room_stmt)
        room = room_result.scalar_one_or_none()
        if room is None:
            raise RoomNotFoundError(f"Room {room_id} not found")

        if room.length is None or room.width is None or room.height is None:
            raise WallGenerationDimensionsMissingError(
                "Cannot generate walls for a room without length, width and height"
            )

        stmt = (
            select(Surface)
            .where(
                Surface.room_id == room_id,
                Surface.is_archived.is_(False),
                Surface.surface_type == SurfaceType.WALL,
            )
            .order_by(
                Surface.position.asc().nulls_last(),
                Surface.created_at.desc(),
            )
        )
        result = await self.db.execute(stmt)
        existing_walls = list(result.scalars().all())

        existing_snapshot = [
            (wall.position, wall.surface_type, wall.width, wall.height)
            for wall in existing_walls
        ]

        if matches_canonical_wall_set(
            room.length,
            room.width,
            room.height,
            existing_snapshot,
        ):
            return existing_walls

        if existing_snapshot:
            raise WallGenerationConflictError(
                "Room already contains walls that do not match the 4-wall rectangle; no walls were changed"
            )

        created: list[Surface] = []
        for position, name, width, height in generate_canonical_walls(
            room.length,
            room.width,
            room.height,
        ):
            wall = Surface(
                room_id=room_id,
                name=name,
                surface_type=SurfaceType.WALL,
                description=None,
                position=position,
                width=width,
                height=height,
            )
            wall.deduction_area = Decimal("0.000")
            self.db.add(wall)
            created.append(wall)
        await self.db.commit()
        for wall in created:
            await self.db.refresh(wall)
        return created

    async def create_surface(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        payload: SurfaceCreate,
        owner_id: uuid.UUID,
    ) -> Surface:
        await self._ensure_room_owned(project_id, room_id, owner_id)

        surface = Surface(
            room_id=room_id,
            name=payload.name,
            surface_type=payload.surface_type,
            description=payload.description,
            position=payload.position,
            width=payload.width,
            height=payload.height,
        )
        self.db.add(surface)
        await self.db.commit()
        await self.db.refresh(surface)
        if surface.surface_type == SurfaceType.WALL and surface.width is not None and surface.height is not None:
            surface.deduction_area = Decimal("0.000")
        return surface

    async def get_surface(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        surface_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> Surface:
        await self._ensure_room_owned(project_id, room_id, owner_id)

        stmt = select(Surface).where(
            Surface.id == surface_id,
            Surface.room_id == room_id,
        )
        result = await self.db.execute(stmt)
        surface = result.scalar_one_or_none()
        if not surface:
            raise SurfaceNotFoundError(f"Surface {surface_id} not found")

        if surface.surface_type == SurfaceType.WALL and surface.width is not None and surface.height is not None:
            deduction_stmt = select(
                func.coalesce(
                    func.sum(Opening.width * Opening.height * Opening.quantity), 0
                )
            ).where(
                Opening.surface_id == surface_id,
                Opening.is_archived.is_(False),
            )
            deduction_res = await self.db.execute(deduction_stmt)
            surface.deduction_area = Decimal(deduction_res.scalar_one()).quantize(Decimal("0.001"))

        return surface

    async def update_surface(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        surface_id: uuid.UUID,
        payload: SurfaceUpdate,
        owner_id: uuid.UUID,
    ) -> Surface:
        surface = await self.get_surface(project_id, room_id, surface_id, owner_id)

        target_width = payload.width if payload.width is not None else surface.width
        target_height = payload.height if payload.height is not None else surface.height
        target_type = payload.surface_type if payload.surface_type is not None else surface.surface_type

        # Validate that new dimensions do not cause existing active deductions to exceed gross area
        if target_type == SurfaceType.WALL and target_width is not None and target_height is not None:
            new_gross = (target_width * target_height).quantize(Decimal("0.001"))
            deduction_stmt = select(
                func.coalesce(
                    func.sum(Opening.width * Opening.height * Opening.quantity), 0
                )
            ).where(
                Opening.surface_id == surface_id,
                Opening.is_archived.is_(False),
            )
            deduction_res = await self.db.execute(deduction_stmt)
            current_deductions = Decimal(deduction_res.scalar_one()).quantize(Decimal("0.001"))
            if current_deductions > new_gross:
                raise DeductionExceedsGrossAreaError(
                    f"New gross area ({new_gross}) is smaller than current active opening deductions ({current_deductions})"
                )

        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(surface, field, value)

        await self.db.commit()
        await self.db.refresh(surface)
        if surface.surface_type == SurfaceType.WALL and surface.width is not None and surface.height is not None:
            deduction_stmt = select(
                func.coalesce(
                    func.sum(Opening.width * Opening.height * Opening.quantity), 0
                )
            ).where(
                Opening.surface_id == surface_id,
                Opening.is_archived.is_(False),
            )
            deduction_res = await self.db.execute(deduction_stmt)
            surface.deduction_area = Decimal(deduction_res.scalar_one()).quantize(Decimal("0.001"))
        return surface

    async def archive_surface(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        surface_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> Surface:
        surface = await self.get_surface(project_id, room_id, surface_id, owner_id)
        surface.is_archived = True
        await self.db.commit()
        await self.db.refresh(surface)
        return surface

    async def restore_surface(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        surface_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> Surface:
        surface = await self.get_surface(project_id, room_id, surface_id, owner_id)
        surface.is_archived = False
        await self.db.commit()
        await self.db.refresh(surface)
        return surface
