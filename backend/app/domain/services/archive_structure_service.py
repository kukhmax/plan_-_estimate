"""The archived rooms and surfaces across all objects of the owner (archive cleanup AC-4a).

The rooms of an object show their archived rooms behind "Pokaż zarchiwizowane"; the owner's archive page lists what was put away in
ONE place, with the object, so it can be restored without walking through the objects. Read-only: restoring is done by the routes of
the room and of the surface.

What is listed: an archived room of an object that is in work; an archived surface of a room that is in work (a surface of an
archived room comes back with the room's own list once the room is restored, so it is not listed apart). Nothing of an archived
object is listed: it returns together with the object.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.room import Room
from app.models.surface import Surface

LIMIT = 200


@dataclass(frozen=True)
class ArchivedRoom:
    room: Room
    project_id: uuid.UUID
    project_name: str


@dataclass(frozen=True)
class ArchivedSurface:
    surface: Surface
    room_name: str
    project_id: uuid.UUID
    project_name: str


@dataclass(frozen=True)
class ArchivedStructure:
    rooms: list[ArchivedRoom]
    surfaces: list[ArchivedSurface]
    rooms_total: int
    surfaces_total: int


class ArchiveStructureService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_archived(self, owner_id: uuid.UUID) -> ArchivedStructure:
        rooms_where = (
            Project.owner_id == owner_id,
            Project.is_archived.is_(False),
            Room.is_archived.is_(True),
        )
        rooms = (
            await self.db.execute(
                select(Room, Project.name)
                .join(Project, Room.project_id == Project.id)
                .where(*rooms_where)
                .order_by(Project.name, Room.name, Room.id)
                .limit(LIMIT)
            )
        ).all()
        rooms_total = (
            await self.db.execute(select(func.count()).select_from(Room).join(Project, Room.project_id == Project.id).where(*rooms_where))
        ).scalar_one()

        surfaces_where = (
            Project.owner_id == owner_id,
            Project.is_archived.is_(False),
            Room.is_archived.is_(False),
            Surface.is_archived.is_(True),
        )
        surfaces = (
            await self.db.execute(
                select(Surface, Room.name, Project.id, Project.name)
                .join(Room, Surface.room_id == Room.id)
                .join(Project, Room.project_id == Project.id)
                .where(*surfaces_where)
                .order_by(Project.name, Room.name, Surface.name, Surface.id)
                .limit(LIMIT)
            )
        ).all()
        surfaces_total = (
            await self.db.execute(
                select(func.count())
                .select_from(Surface)
                .join(Room, Surface.room_id == Room.id)
                .join(Project, Room.project_id == Project.id)
                .where(*surfaces_where)
            )
        ).scalar_one()

        return ArchivedStructure(
            rooms=[ArchivedRoom(room=r, project_id=r.project_id, project_name=name) for r, name in rooms],
            surfaces=[
                ArchivedSurface(surface=s, room_name=room_name, project_id=project_id, project_name=project_name)
                for s, room_name, project_id, project_name in surfaces
            ],
            rooms_total=int(rooms_total),
            surfaces_total=int(surfaces_total),
        )
