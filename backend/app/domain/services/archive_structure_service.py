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

from app.models.inspection import Inspection
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


@dataclass(frozen=True)
class ArchivedInspection:
    inspection: Inspection
    room_name: str
    surface: Surface | None
    project_id: uuid.UUID
    project_name: str


@dataclass(frozen=True)
class ArchivedInspections:
    items: list[ArchivedInspection]
    total: int


class ArchiveStructureService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_archived(self, owner_id: uuid.UUID) -> ArchivedStructure:
        rooms_where = (
            Project.owner_id == owner_id,
            Project.is_archived.is_(False),
            Room.is_archived.is_(True),
        )
        # The name of an object is ciphertext in the database (EN-2a): the order is made here, after the decryption.
        rooms = sorted(
            (
                await self.db.execute(
                    select(Room, Project.name).join(Project, Room.project_id == Project.id).where(*rooms_where)
                )
            ).all(),
            key=lambda row: (row[1] or "", row[0].name, str(row[0].id)),
        )[:LIMIT]
        rooms_total = (
            await self.db.execute(select(func.count()).select_from(Room).join(Project, Room.project_id == Project.id).where(*rooms_where))
        ).scalar_one()

        surfaces_where = (
            Project.owner_id == owner_id,
            Project.is_archived.is_(False),
            Room.is_archived.is_(False),
            Surface.is_archived.is_(True),
        )
        surfaces = sorted(
            (
                await self.db.execute(
                    select(Surface, Room.name, Project.id, Project.name)
                    .join(Room, Surface.room_id == Room.id)
                    .join(Project, Room.project_id == Project.id)
                    .where(*surfaces_where)
                )
            ).all(),
            key=lambda row: (row[3] or "", row[1], row[0].name, str(row[0].id)),
        )[:LIMIT]
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

    async def list_archived_inspections(self, owner_id: uuid.UUID) -> ArchivedInspections:
        """The archived inspections (Badania podłoża) of the rooms in work of the objects in work, newest first.

        An inspection of an archived room (or object) comes back with it, so it is not listed apart. Restoring is done by the route of the
        inspection; deleting it for good by `StructurePurgeService`.
        """
        where = (
            Project.owner_id == owner_id,
            Project.is_archived.is_(False),
            Room.is_archived.is_(False),
            Inspection.is_archived.is_(True),
        )
        rows = (
            await self.db.execute(
                select(Inspection, Room.name, Surface, Project.id, Project.name)
                .join(Room, Inspection.room_id == Room.id)
                .join(Project, Room.project_id == Project.id)
                .outerjoin(Surface, Inspection.surface_id == Surface.id)
                .where(*where)
                .order_by(Inspection.created_at.desc(), Inspection.id.asc())
                .limit(LIMIT)
            )
        ).all()
        total = (
            await self.db.execute(
                select(func.count()).select_from(Inspection).join(Room, Inspection.room_id == Room.id)
                .join(Project, Room.project_id == Project.id).where(*where)
            )
        ).scalar_one()
        return ArchivedInspections(
            items=[
                ArchivedInspection(inspection=i, room_name=room_name, surface=surface, project_id=project_id, project_name=project_name)
                for i, room_name, surface, project_id, project_name in rows
            ],
            total=int(total),
        )
