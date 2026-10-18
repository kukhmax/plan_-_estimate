import uuid
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import ClientHasProjectsError, ClientNotArchivedError, ClientNotFoundError
from app.models.client import Client, ClientType
from app.models.project import Project
from app.schemas.client import ClientCreate, ClientUpdate


class ClientService:
    """Domain service for client management with strict owner isolation."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_clients(
        self,
        owner_user_id: uuid.UUID,
        *,
        include_archived: bool = False,
        search: Optional[str] = None,
    ) -> tuple[list[Client], int]:
        stmt = select(Client).where(Client.owner_user_id == owner_user_id)

        if not include_archived:
            stmt = stmt.where(Client.is_archived.is_(False))

        stmt = stmt.order_by(Client.created_at.desc())
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())

        if search:
            # The fields are ciphertext in the database (EN-2a), so the search runs here, on the decrypted clients of the owner.
            needle = search.casefold()
            items = [
                client
                for client in items
                if any(
                    needle in value.casefold()
                    for value in (client.first_name, client.last_name, client.company_name, client.phone)
                    if value
                )
            ]

        total = len(items)
        return items, total

    async def get_client(self, client_id: uuid.UUID, owner_user_id: uuid.UUID) -> Client:
        stmt = select(Client).where(
            Client.id == client_id,
            Client.owner_user_id == owner_user_id,
        )
        result = await self.db.execute(stmt)
        client = result.scalar_one_or_none()
        if not client:
            raise ClientNotFoundError(f"Client {client_id} not found")
        return client

    async def create_client(
        self, payload: ClientCreate, owner_user_id: uuid.UUID
    ) -> Client:
        client = Client(
            owner_user_id=owner_user_id,
            client_type=payload.client_type,
            first_name=payload.first_name,
            last_name=payload.last_name,
            company_name=payload.company_name,
            phone=payload.phone,
            email=payload.email,
            nip=payload.nip,
            street=payload.street,
            postal_code=payload.postal_code,
            city=payload.city,
            telegram_username=payload.telegram_username,
            notes=payload.notes,
        )
        self.db.add(client)
        await self.db.commit()
        await self.db.refresh(client)
        return client

    async def update_client(
        self, client_id: uuid.UUID, payload: ClientUpdate, owner_user_id: uuid.UUID
    ) -> Client:
        client = await self.get_client(client_id, owner_user_id)

        update_data = payload.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(client, field, value)

        await self.db.commit()
        await self.db.refresh(client)
        return client

    async def archive_client(
        self, client_id: uuid.UUID, owner_user_id: uuid.UUID
    ) -> Client:
        client = await self.get_client(client_id, owner_user_id)
        client.is_archived = True
        await self.db.commit()
        await self.db.refresh(client)
        return client

    async def restore_client(
        self, client_id: uuid.UUID, owner_user_id: uuid.UUID
    ) -> Client:
        # When restoring, we must search including archived records
        stmt = select(Client).where(
            Client.id == client_id,
            Client.owner_user_id == owner_user_id,
        )
        result = await self.db.execute(stmt)
        client = result.scalar_one_or_none()
        if not client:
            raise ClientNotFoundError(f"Client {client_id} not found")

        client.is_archived = False
        await self.db.commit()
        await self.db.refresh(client)
        return client

    async def delete_preview(self, client_id: uuid.UUID, owner_user_id: uuid.UUID) -> tuple[Client, int]:
        """What the final deletion of a client would meet: the client and the number of its objects (archived ones included)."""
        client = await self.get_client(client_id, owner_user_id)
        return client, await self._count_projects(client.id, owner_user_id)

    async def _count_projects(self, client_id: uuid.UUID, owner_user_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(Project)
            .where(Project.client_id == client_id, Project.owner_id == owner_user_id)
        )
        return int((await self.db.execute(stmt)).scalar_one())

    async def delete_client(self, client_id: uuid.UUID, owner_user_id: uuid.UUID) -> None:
        """Delete an ARCHIVED client that has no objects (archive cleanup AC-5a). A client owns no files, so nothing else is removed.

        The client row is locked first: creating an object for this client takes a share lock on the same row, so an object
        cannot appear between the count and the deletion.
        """
        stmt = (
            select(Client)
            .where(Client.id == client_id, Client.owner_user_id == owner_user_id)
            .with_for_update()
        )
        client = (await self.db.execute(stmt)).scalar_one_or_none()
        if client is None:
            raise ClientNotFoundError(f"Client {client_id} not found")
        if not client.is_archived:
            raise ClientNotArchivedError(f"Client {client_id} is not archived")
        projects = await self._count_projects(client.id, owner_user_id)
        if projects > 0:
            raise ClientHasProjectsError(projects)
        await self.db.delete(client)
        await self.db.commit()
