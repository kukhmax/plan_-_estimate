import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import (
    ProjectNotFoundError,
    RoomNotFoundError,
    SurfaceNotFoundError,
)
from app.models.project import Project
from app.models.room import Room
from app.models.surface import Surface
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

        stmt = select(Surface).where(Surface.room_id == room_id)
        if not include_archived:
            stmt = stmt.where(Surface.is_archived.is_(False))

        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar_one()

        stmt = stmt.order_by(Surface.created_at.desc())
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())
        return items, total

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
            width=payload.width,
            height=payload.height,
        )
        self.db.add(surface)
        await self.db.commit()
        await self.db.refresh(surface)
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
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(surface, field, value)

        await self.db.commit()
        await self.db.refresh(surface)
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
