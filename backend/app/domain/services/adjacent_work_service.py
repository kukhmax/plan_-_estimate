"""Adjacent works of an object (Stage 16D.1): the register of other contractors' works.

Every call is scoped to the owner's own project (`ProjectNotFoundError` otherwise). The rooms an entry names must be live rooms of
the same object. An entry is never deleted, only archived.
"""
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import (
    AdjacentWorkNotFoundError,
    AdjacentWorkPeriodInvalidError,
    AdjacentWorkRoomInvalidError,
    ProjectNotFoundError,
)
from app.models.adjacent_work import AdjacentWork
from app.models.project import Project
from app.models.room import Room
from app.schemas.adjacent_work import AdjacentWorkCreate, AdjacentWorkUpdate


class AdjacentWorkService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _ensure_project_owned(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        found = await self.db.execute(select(Project.id).where(Project.id == project_id, Project.owner_id == owner_id))
        if found.scalar_one_or_none() is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")

    async def _ensure_rooms(self, project_id: uuid.UUID, room_ids: list[uuid.UUID] | None) -> None:
        if not room_ids:
            return
        live = set(
            (
                await self.db.execute(
                    select(Room.id).where(Room.project_id == project_id, Room.id.in_(room_ids), Room.is_archived.is_(False))
                )
            ).scalars()
        )
        if live != set(room_ids):
            raise AdjacentWorkRoomInvalidError("a room of the entry is not a live room of this object")

    async def get(self, project_id: uuid.UUID, work_id: uuid.UUID, owner_id: uuid.UUID) -> AdjacentWork:
        await self._ensure_project_owned(project_id, owner_id)
        row = (
            await self.db.execute(
                select(AdjacentWork).where(
                    AdjacentWork.id == work_id, AdjacentWork.project_id == project_id, AdjacentWork.owner_id == owner_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise AdjacentWorkNotFoundError(f"Adjacent work {work_id} not found")
        return row

    async def list(
        self, project_id: uuid.UUID, owner_id: uuid.UUID, *, include_archived: bool = False
    ) -> tuple[list[AdjacentWork], int]:
        await self._ensure_project_owned(project_id, owner_id)
        statement = select(AdjacentWork).where(AdjacentWork.project_id == project_id, AdjacentWork.owner_id == owner_id)
        if not include_archived:
            statement = statement.where(AdjacentWork.is_archived.is_(False))
        rows = list((await self.db.execute(statement.order_by(AdjacentWork.position, AdjacentWork.created_at, AdjacentWork.id))).scalars())
        return rows, len(rows)

    async def create(self, project_id: uuid.UUID, owner_id: uuid.UUID, payload: AdjacentWorkCreate) -> AdjacentWork:
        await self._ensure_project_owned(project_id, owner_id)
        await self._ensure_rooms(project_id, payload.room_ids)
        last = (
            await self.db.execute(select(func.max(AdjacentWork.position)).where(AdjacentWork.project_id == project_id))
        ).scalar_one_or_none()
        row = AdjacentWork(
            owner_id=owner_id,
            project_id=project_id,
            work_name=payload.work_name,
            performer=payload.performer,
            room_ids=[str(r) for r in payload.room_ids] if payload.room_ids else None,
            period_from=payload.period_from,
            period_to=payload.period_to,
            order_relation=payload.order_relation.value,
            order_note=payload.order_note,
            responsibility_note=payload.responsibility_note,
            coordination_note=payload.coordination_note,
            position=0 if last is None else last + 1,
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def update(
        self, project_id: uuid.UUID, work_id: uuid.UUID, owner_id: uuid.UUID, payload: AdjacentWorkUpdate
    ) -> AdjacentWork:
        row = await self.get(project_id, work_id, owner_id)
        changes = payload.model_dump(exclude_unset=True)
        if "room_ids" in changes:
            await self._ensure_rooms(project_id, changes["room_ids"])
            changes["room_ids"] = [str(r) for r in changes["room_ids"]] if changes["room_ids"] else None
        if "order_relation" in changes:
            changes["order_relation"] = changes["order_relation"].value
        period_from = changes.get("period_from", row.period_from)
        period_to = changes.get("period_to", row.period_to)
        if period_from and period_to and period_to < period_from:
            raise AdjacentWorkPeriodInvalidError("period_to must not be before period_from")
        for field, value in changes.items():
            setattr(row, field, value)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def set_archived(self, project_id: uuid.UUID, work_id: uuid.UUID, owner_id: uuid.UUID, archived: bool) -> AdjacentWork:
        row = await self.get(project_id, work_id, owner_id)
        row.is_archived = archived
        await self.db.commit()
        await self.db.refresh(row)
        return row
