import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import ProjectNotFoundError, RoomNotFoundError
from app.models.project import Project
from app.models.room import Room
from app.schemas.room import RoomCreate, RoomUpdate


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

    async def list_rooms(
        self,
        project_id: uuid.UUID,
        owner_id: uuid.UUID,
        *,
        include_archived: bool = False,
    ) -> tuple[list[Room], int]:
        await self._ensure_project_owned(project_id, owner_id)

        stmt = select(Room).where(Room.project_id == project_id)
        if not include_archived:
            stmt = stmt.where(Room.is_archived.is_(False))

        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar_one()

        stmt = stmt.order_by(Room.created_at.desc())
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())
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
        )
        self.db.add(room)
        await self.db.commit()
        await self.db.refresh(room)
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
        return room
