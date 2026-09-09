import uuid
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import ClientNotFoundError
from app.models.client import Client, ClientType
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

        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Client.first_name.ilike(pattern),
                    Client.last_name.ilike(pattern),
                    Client.company_name.ilike(pattern),
                    Client.phone.ilike(pattern),
                )
            )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar_one()

        stmt = stmt.order_by(Client.created_at.desc())
        result = await self.db.execute(stmt)
        items = list(result.scalars().all())

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
