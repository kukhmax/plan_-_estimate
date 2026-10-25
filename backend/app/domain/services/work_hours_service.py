"""The work log of an object (V2-9): the hours the owner worked, a day at a time. The owner's own record: entries may be changed and deleted.

Owner-scoped like every service. The sum of the hours is made here; the margin of the object reads it (`project_margin_service.py`).
"""
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import ProjectNotFoundError, WorkHourNotFoundError
from app.models.payment_stage import WorkHour
from app.models.project import Project

ZERO = Decimal("0.00")


def _note(value: str | None) -> str | None:
    text = (value or "").strip()
    return text or None


class WorkHoursService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _ensure_project(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> None:
        found = (await self.db.execute(select(Project.id).where(Project.id == project_id, Project.owner_id == owner_id))).scalar_one_or_none()
        if found is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")

    async def _get(self, owner_id: uuid.UUID, project_id: uuid.UUID, entry_id: uuid.UUID) -> WorkHour:
        await self._ensure_project(owner_id, project_id)
        row = (await self.db.execute(
            select(WorkHour).where(WorkHour.id == entry_id, WorkHour.project_id == project_id, WorkHour.owner_id == owner_id)
        )).scalar_one_or_none()
        if row is None:
            raise WorkHourNotFoundError(f"Entry {entry_id} not found")
        return row

    async def list_entries(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> tuple[list[WorkHour], Decimal]:
        await self._ensure_project(owner_id, project_id)
        rows = list((await self.db.execute(
            select(WorkHour).where(WorkHour.project_id == project_id, WorkHour.owner_id == owner_id)
            .order_by(WorkHour.worked_on.desc(), WorkHour.created_at.desc(), WorkHour.id.desc())
        )).scalars())
        return rows, sum((r.hours for r in rows), ZERO)

    async def total_hours(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> Decimal:
        return (await self.list_entries(owner_id, project_id))[1]

    async def create(self, owner_id: uuid.UUID, project_id: uuid.UUID, data: dict[str, Any]) -> WorkHour:
        await self._ensure_project(owner_id, project_id)
        now = datetime.now(UTC)
        row = WorkHour(
            owner_id=owner_id, project_id=project_id, worked_on=data["worked_on"], hours=data["hours"], note=_note(data.get("note")),
            created_at=now, updated_at=now,
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def change(self, owner_id: uuid.UUID, project_id: uuid.UUID, entry_id: uuid.UUID, changes: dict[str, Any]) -> WorkHour:
        row = await self._get(owner_id, project_id, entry_id)
        for name in ("worked_on", "hours"):
            if name in changes and changes[name] is not None:
                setattr(row, name, changes[name])
        if "note" in changes:
            row.note = _note(changes["note"])
        row.updated_at = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def delete(self, owner_id: uuid.UUID, project_id: uuid.UUID, entry_id: uuid.UUID) -> None:
        row = await self._get(owner_id, project_id, entry_id)
        await self.db.execute(delete(WorkHour).where(WorkHour.id == row.id))
        await self.db.commit()
