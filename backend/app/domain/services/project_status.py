"""The status of an object follows its work (owner 2026-10-31): the client's or the contract's acceptance of the estimate starts the work
("W realizacji"), a final acceptance protocol that is not a refusal ends it ("Zakończony"). The owner may still change it by hand; the
status only moves forward and never back (an object completed by hand is never reopened by an estimate)."""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project, ProjectStatus

_ORDER = {ProjectStatus.PLANNING: 0, ProjectStatus.IN_PROGRESS: 1, ProjectStatus.COMPLETED: 2}


async def advance_project_status(db: AsyncSession, project_id: uuid.UUID, target: ProjectStatus) -> bool:
    """Move the object forward to `target` (no commit; the caller's transaction carries it). True when it moved."""
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if project is None or _ORDER.get(project.status, 0) >= _ORDER[target]:
        return False
    project.status = target
    return True
