"""Persons of an object (Stage 16B.2): the register of who acts for each side and who may accept the work and sign protocols.

Every call is scoped to the owner's own project (`ProjectNotFoundError` otherwise, and nothing about another owner's object is
revealed). A person is never deleted, only archived.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import ProjectNotFoundError, ProjectRepresentativeNotFoundError
from app.models.project import Project
from app.models.project_representative import ProjectRepresentative
from app.schemas.project_representative import ProjectRepresentativeCreate, ProjectRepresentativeUpdate


class ProjectRepresentativeService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _ensure_project_owned(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        found = await self.db.execute(select(Project.id).where(Project.id == project_id, Project.owner_id == owner_id))
        if found.scalar_one_or_none() is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")

    async def get(self, project_id: uuid.UUID, representative_id: uuid.UUID, owner_id: uuid.UUID) -> ProjectRepresentative:
        await self._ensure_project_owned(project_id, owner_id)
        row = (
            await self.db.execute(
                select(ProjectRepresentative).where(
                    ProjectRepresentative.id == representative_id,
                    ProjectRepresentative.project_id == project_id,
                    ProjectRepresentative.owner_id == owner_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise ProjectRepresentativeNotFoundError(f"Representative {representative_id} not found")
        return row

    async def list(
        self, project_id: uuid.UUID, owner_id: uuid.UUID, *, include_archived: bool = False
    ) -> tuple[list[ProjectRepresentative], int]:
        await self._ensure_project_owned(project_id, owner_id)
        statement = select(ProjectRepresentative).where(
            ProjectRepresentative.project_id == project_id, ProjectRepresentative.owner_id == owner_id
        )
        if not include_archived:
            statement = statement.where(ProjectRepresentative.is_archived.is_(False))
        rows = list(
            (await self.db.execute(statement.order_by(ProjectRepresentative.created_at, ProjectRepresentative.id))).scalars()
        )
        return rows, len(rows)

    async def create(
        self, project_id: uuid.UUID, owner_id: uuid.UUID, payload: ProjectRepresentativeCreate
    ) -> ProjectRepresentative:
        await self._ensure_project_owned(project_id, owner_id)
        row = ProjectRepresentative(
            owner_id=owner_id,
            project_id=project_id,
            side=payload.side.value,
            name=payload.name,
            role_title=payload.role_title,
            phone=payload.phone,
            email=payload.email,
            may_accept_and_sign=payload.may_accept_and_sign,
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def update(
        self,
        project_id: uuid.UUID,
        representative_id: uuid.UUID,
        owner_id: uuid.UUID,
        payload: ProjectRepresentativeUpdate,
    ) -> ProjectRepresentative:
        row = await self.get(project_id, representative_id, owner_id)
        for field, value in payload.model_dump(exclude_unset=True).items():
            setattr(row, field, value.value if field == "side" else value)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def set_archived(
        self, project_id: uuid.UUID, representative_id: uuid.UUID, owner_id: uuid.UUID, archived: bool
    ) -> ProjectRepresentative:
        row = await self.get(project_id, representative_id, owner_id)
        row.is_archived = archived
        await self.db.commit()
        await self.db.refresh(row)
        return row
