"""Demo data of an account (V2-2; docs/V2_2_PLAN_RU.md): an object with five rooms and demo prices, and the way to take them away.

Everything is made through the same services as the application, so the demo object is an ordinary object. It is recognised by its
name prefix and the mark in the notes of its client; `remove` touches nothing else. A price the owner has set is never overwritten.
"""
import uuid
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.data.demo_data import (
    DEMO_CLIENT_MARK,
    DEMO_PROJECT_NAME,
    DEMO_PROJECT_PREFIX,
    DEMO_ROOMS,
    demo_prices,
)
from app.domain.exceptions import ClientHasProjectsError
from app.domain.services.client_service import ClientService
from app.domain.services.data_key_service import DataKeyService
from app.domain.services.media_purger import MediaPurger
from app.domain.services.price_book_service import PriceBookService
from app.domain.services.project_purge_service import ProjectPurgeService
from app.domain.services.project_service import ProjectService
from app.domain.services.room_service import RoomService
from app.domain.services.surface_service import SurfaceService
from app.models.client import Client, ClientType
from app.models.price_item import PriceItem
from app.models.project import Project
from app.models.room import Room
from app.schemas.client import ClientCreate
from app.schemas.project import ProjectCreate
from app.schemas.room import RoomCreate


@dataclass(frozen=True)
class DemoStatus:
    project_id: uuid.UUID | None
    client_id: uuid.UUID | None
    rooms: int
    demo_priced_items: int


@dataclass(frozen=True)
class DemoSeedResult:
    created_objects: bool
    rooms: int
    priced_items: int


@dataclass(frozen=True)
class DemoRemoveResult:
    removed_project: bool
    removed_client: bool
    client_kept_reason: str | None
    prices_reset: int


class DemoDataService:
    def __init__(self, db: AsyncSession, purger: MediaPurger) -> None:
        self.db = db
        self.purger = purger

    async def _project(self, owner_id: uuid.UUID) -> Project | None:
        # the name is ciphertext in the database: the objects of the owner are read (decrypted) and the prefix is looked for here
        rows = (await self.db.execute(select(Project).where(Project.owner_id == owner_id).order_by(Project.created_at))).scalars()
        return next((row for row in rows if row.name.startswith(DEMO_PROJECT_PREFIX)), None)

    async def _client(self, owner_id: uuid.UUID) -> Client | None:
        rows = (await self.db.execute(select(Client).where(Client.owner_user_id == owner_id).order_by(Client.created_at))).scalars()
        return next((row for row in rows if (row.notes or "").startswith(DEMO_CLIENT_MARK)), None)

    async def _items(self, owner_id: uuid.UUID) -> list[PriceItem]:
        return list((await self.db.execute(select(PriceItem).where(PriceItem.owner_id == owner_id))).scalars())

    async def _in_force(self, owner_id: uuid.UUID) -> None:
        # the client data is encrypted with the key of its owner: a command line has no request to put that key in force (EN-2)
        await DataKeyService(self.db).put_in_force(owner_id)

    async def status(self, owner_id: uuid.UUID) -> DemoStatus:
        await self._in_force(owner_id)
        project, client = await self._project(owner_id), await self._client(owner_id)
        rooms = 0
        if project is not None:
            rooms = int((await self.db.execute(select(func.count()).select_from(Room).where(Room.project_id == project.id))).scalar_one())
        prices = demo_prices()
        matching = sum(1 for item in await self._items(owner_id) if item.price is not None and prices.get(item.code) == item.price)
        return DemoStatus(project.id if project else None, client.id if client else None, rooms, matching)

    async def seed(self, owner_id: uuid.UUID, *, with_prices: bool = True) -> DemoSeedResult:
        await self._in_force(owner_id)
        project, client = await self._project(owner_id), await self._client(owner_id)
        created, rooms = False, 0
        if project is None:
            if client is None:
                client = await ClientService(self.db).create_client(
                    ClientCreate(
                        client_type=ClientType.PRIVATE_PERSON, first_name="Jan", last_name="Przykładowy",
                        phone="+48 600 000 000", email="demo@example.pl", city="Kraków",
                        notes=f"{DEMO_CLIENT_MARK} Przykładowy klient: usuń komendą demo remove.",
                    ),
                    owner_id,
                )
            project = await ProjectService(self.db).create_project(
                ProjectCreate(
                    name=DEMO_PROJECT_NAME, address="ul. Przykładowa 1/2", city="Kraków", postal_code="30-001",
                    description=f"{DEMO_CLIENT_MARK} Przykładowy obiekt z pomieszczeniami i cenami demo.", client_id=client.id,
                ),
                owner_id,
            )
            room_service, surface_service = RoomService(self.db), SurfaceService(self.db)
            for demo in DEMO_ROOMS:
                room = await room_service.create_room(
                    project.id, RoomCreate(name=demo.name, length=demo.length, width=demo.width, height=demo.height), owner_id
                )
                await surface_service.generate_walls(project.id, room.id, owner_id)
                rooms += 1
            created = True
        priced = await self._apply_prices(owner_id) if with_prices else 0
        return DemoSeedResult(created, rooms, priced)

    async def _apply_prices(self, owner_id: uuid.UUID) -> int:
        await PriceBookService(self.db).ensure_owner_catalog(owner_id)
        prices = demo_prices()
        changed = 0
        for item in await self._items(owner_id):
            if item.price is None and not item.is_archived and item.code in prices:
                item.price = prices[item.code]
                changed += 1
        if changed:
            await self.db.commit()
        return changed

    async def remove(self, owner_id: uuid.UUID, *, reset_prices: bool = True) -> DemoRemoveResult:
        await self._in_force(owner_id)
        project, client = await self._project(owner_id), await self._client(owner_id)
        removed_project = removed_client = False
        kept: str | None = None
        if project is not None:
            if not project.is_archived:
                await ProjectService(self.db).archive_project(project.id, owner_id)
            await ProjectPurgeService(self.db, self.purger).purge(owner_id, project.id)
            removed_project = True
        if client is not None:
            clients = ClientService(self.db)
            if not client.is_archived:
                await clients.archive_client(client.id, owner_id)
            try:
                await clients.delete_client(client.id, owner_id)
                removed_client = True
            except ClientHasProjectsError as error:
                kept = str(error)  # the owner gave the demo client an object of its own: the client stays
        reset = await self._reset_prices(owner_id) if reset_prices else 0
        return DemoRemoveResult(removed_project, removed_client, kept, reset)

    async def _reset_prices(self, owner_id: uuid.UUID) -> int:
        prices = demo_prices()
        changed = 0
        for item in await self._items(owner_id):
            if item.price is not None and prices.get(item.code) == Decimal(item.price):
                item.price = None
                changed += 1
        if changed:
            await self.db.commit()
        return changed
