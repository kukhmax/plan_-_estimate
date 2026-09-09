import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import ClientNotFoundError, ProjectNotFoundError
from app.models.client import Client
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectUpdate


class ProjectService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_projects(
        self,
        owner_id: uuid.UUID,
        *,
        include_archived: bool = False,
    ) -> tuple[list[Project], int]:
        stmt = select(Project).where(Project.owner_id == owner_id)

        if not include_archived:
            stmt = stmt.where(Project.is_archived.is_(False))

        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar_one()

        stmt = stmt.order_by(Project.created_at.desc())
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    async def get_project(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> Project:
        stmt = select(Project).where(
            Project.id == project_id,
            Project.owner_id == owner_id,
        )
        result = await self.db.execute(stmt)
        project = result.scalar_one_or_none()
        if not project:
            raise ProjectNotFoundError(f"Project {project_id} not found")
        return project

    async def _ensure_client_owned(
        self, client_id: uuid.UUID, owner_id: uuid.UUID
    ) -> None:
        stmt = select(Client.id).where(
            Client.id == client_id,
            Client.owner_user_id == owner_id,
        )
        result = await self.db.execute(stmt)
        if result.scalar_one_or_none() is None:
            raise ClientNotFoundError(f"Client {client_id} not found")

    async def create_project(
        self, payload: ProjectCreate, owner_id: uuid.UUID
    ) -> Project:
        if payload.client_id is not None:
            await self._ensure_client_owned(payload.client_id, owner_id)

        project = Project(
            owner_id=owner_id,
            client_id=payload.client_id,
            name=payload.name,
            address=payload.address,
            city=payload.city,
            postal_code=payload.postal_code,
            description=payload.description,
            status=payload.status,
        )
        self.db.add(project)
        await self.db.commit()
        await self.db.refresh(project)
        return project

    async def update_project(
        self,
        project_id: uuid.UUID,
        payload: ProjectUpdate,
        owner_id: uuid.UUID,
    ) -> Project:
        project = await self.get_project(project_id, owner_id)
        update_data = payload.model_dump(exclude_unset=True)

        client_id = update_data.get("client_id")
        if client_id is not None:
            await self._ensure_client_owned(client_id, owner_id)

        for field, value in update_data.items():
            setattr(project, field, value)

        await self.db.commit()
        await self.db.refresh(project)
        return project

    async def archive_project(
        self, project_id: uuid.UUID, owner_id: uuid.UUID
    ) -> Project:
        project = await self.get_project(project_id, owner_id)
        project.is_archived = True
        await self.db.commit()
        await self.db.refresh(project)
        return project

    async def restore_project(
        self, project_id: uuid.UUID, owner_id: uuid.UUID
    ) -> Project:
        project = await self.get_project(project_id, owner_id)
        project.is_archived = False
        await self.db.commit()
        await self.db.refresh(project)
        return project
