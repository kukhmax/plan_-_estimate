"""The quick estimate (V2-4; docs/V2_4_PLAN_RU.md): a client, an object, rooms with walls and a work plan on each wall, and a draft estimate -- from one request.

Everything is made by the services the application already uses, so the result is an ordinary object and an ordinary draft estimate (the finishing and
the PDF are the ordinary buttons). The doors and windows are not deducted: the screen says so. Everything is checked before anything is created.
"""
import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.data.quick_estimate_data import QUICK_WORK_CODES, QUICK_WORKS
from app.domain.exceptions import ClientNotFoundError, QuickEstimateError
from app.domain.rules.inspection_rules import assert_quality_scale_valid
from app.domain.services.canonical_planes import find_active_plane_surface
from app.domain.services.client_service import ClientService
from app.domain.services.estimate_service import EstimateService
from app.domain.services.floor_works_service import FloorWorksService
from app.domain.services.price_book_service import PriceBookService
from app.domain.services.project_service import ProjectService
from app.domain.services.room_service import RoomService
from app.domain.services.surface_service import SurfaceService
from app.domain.services.work_plan_service import SurfaceWorkPlanService
from app.models.checklist import QualityLevel, Substrate
from app.models.client import ClientType
from app.models.estimate import EstimateLine
from app.models.price_item import PriceItem
from app.models.surface import SurfaceType
from app.schemas.client import ClientCreate
from app.schemas.project import ProjectCreate
from app.schemas.quick_estimate import QuickEstimateCreate, QuickEstimateResult
from app.schemas.room import RoomCreate
from app.schemas.work_plan import OrderedPriceItemSelection

OFFERED_SUBSTRATES: tuple[Substrate, ...] = (
    Substrate.GYPSUM_PLASTER,
    Substrate.CEMENT_LIME_PLASTER,
    Substrate.CONCRETE,
    Substrate.GYPSUM_BOARD,
)
DEFAULT_SUBSTRATE = Substrate.GYPSUM_PLASTER
DEFAULT_QUALITY = QualityLevel.S2


def split_name(full: str) -> tuple[str | None, str | None]:
    """"Jan Kowalski" -> ("Jan", "Kowalski"); one word is the last name."""
    parts = full.strip().split(None, 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return None, parts[0]


class QuickEstimateService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _rows(self, owner_id: uuid.UUID, codes: set[str]) -> dict[str, PriceItem]:
        found = (
            await self.db.execute(
                select(PriceItem).where(PriceItem.owner_id == owner_id, PriceItem.is_archived.is_(False), PriceItem.code.in_(codes))
            )
        ).scalars()
        return {row.code: row for row in found}

    async def option_items(self, owner_id: uuid.UUID) -> list[PriceItem]:
        """Every price row the screen can use (wall and ceiling rows), the catalog completed first."""
        await PriceBookService(self.db).ensure_owner_catalog(owner_id)
        codes = {work.code for work in QUICK_WORKS} | {work.ceiling_code for work in QUICK_WORKS}
        rows = await self._rows(owner_id, codes)
        ordered: list[PriceItem] = []
        for work in QUICK_WORKS:
            for code in (work.code, work.ceiling_code):
                if code in rows and rows[code] not in ordered:
                    ordered.append(rows[code])
        return ordered

    async def create(self, owner_id: uuid.UUID, payload: QuickEstimateCreate) -> QuickEstimateResult:
        # -- everything is checked before anything is made ---------------------------------------------------------------------------
        unknown = [code for code in payload.work_codes if code not in QUICK_WORK_CODES]
        if unknown:
            raise QuickEstimateError("QUICK_WORK_UNKNOWN", f"not a work of the quick estimate: {', '.join(unknown)}")
        chosen = [work for work in QUICK_WORKS if work.code in set(payload.work_codes)]  # the order of the screen, never of the request
        assert_quality_scale_valid(payload.substrate, payload.quality_target)
        if payload.substrate not in OFFERED_SUBSTRATES:
            raise QuickEstimateError("QUICK_SUBSTRATE_UNKNOWN", f"substrate not offered: {payload.substrate.value}")
        await PriceBookService(self.db).ensure_owner_catalog(owner_id)
        needed = {work.code for work in chosen} | ({work.ceiling_code for work in chosen} if payload.include_ceiling else set())
        rows = await self._rows(owner_id, needed)
        missing = sorted(needed - set(rows))
        if missing:
            raise QuickEstimateError("QUICK_WORK_UNAVAILABLE", f"price rows missing or archived: {', '.join(missing)}")
        clients = ClientService(self.db)
        if payload.client_id is not None:
            try:
                client = await clients.get_client(payload.client_id, owner_id)
            except ClientNotFoundError as error:
                raise QuickEstimateError("CLIENT_NOT_FOUND", "no such client") from error
        else:
            client = None

        # -- the objects ---------------------------------------------------------------------------------------------------------------
        if client is None:
            first, last = split_name(payload.client_name or "")
            client = await clients.create_client(
                ClientCreate(client_type=ClientType.PRIVATE_PERSON, first_name=first, last_name=last, phone=(payload.client_phone or None), city=payload.city),
                owner_id,
            )
        project = await ProjectService(self.db).create_project(
            ProjectCreate(name=payload.address.strip()[:255], address=payload.address.strip(), city=payload.city.strip(), postal_code="—", client_id=client.id),
            owner_id,
        )
        rooms, surfaces, plans = RoomService(self.db), SurfaceService(self.db), SurfaceWorkPlanService(self.db)
        wall_works = [OrderedPriceItemSelection(price_item_id=rows[work.code].id) for work in chosen]
        ceiling_works = [OrderedPriceItemSelection(price_item_id=rows[work.ceiling_code].id) for work in chosen] if payload.include_ceiling else []
        for spec in payload.rooms:
            room = await rooms.create_room(project.id, RoomCreate(name=spec.name, length=spec.length, width=spec.width, height=spec.height), owner_id)
            walls = await surfaces.generate_walls(project.id, room.id, owner_id)
            for wall in walls:
                await plans.set_plan(
                    project.id, room.id, wall.id, owner_id,
                    substrate=payload.substrate, quality_target=payload.quality_target, planned_works=wall_works,
                )
            if ceiling_works:
                ceiling = await find_active_plane_surface(self.db, room.id, SurfaceType.CEILING)
                if ceiling is not None:
                    await plans.set_plan(
                        project.id, room.id, ceiling.id, owner_id,
                        substrate=payload.substrate, quality_target=payload.quality_target, planned_works=ceiling_works,
                    )
            # owner 2026-10-31: the protection of the floors goes once into the plan of the floor
            await FloorWorksService(self.db).place_on_floor(project.id, room.id, owner_id)

        estimate = await EstimateService(self.db).generate_estimate(project.id, owner_id)
        lines = int((await self.db.execute(select(func.count()).select_from(EstimateLine).where(EstimateLine.estimate_id == estimate.id))).scalar_one())
        unpriced = int(
            (
                await self.db.execute(
                    select(func.count()).select_from(EstimateLine).where(EstimateLine.estimate_id == estimate.id, EstimateLine.unit_price.is_(None))
                )
            ).scalar_one()
        )
        total: Decimal | None = estimate.total
        return QuickEstimateResult(
            project_id=project.id, client_id=client.id, estimate_id=estimate.id, rooms=len(payload.rooms), lines=lines, unpriced_lines=unpriced, total=total
        )
