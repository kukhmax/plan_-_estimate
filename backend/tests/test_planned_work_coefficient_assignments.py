"""Focused Stage 12D tests: coefficient assignments for planned-work OCCURRENCES.

Covers the Surface Work Plan HTTP contract (``planned_works`` with
``coefficient_option_ids``), the Reveal Work service contract (additive
``coefficient_option_ids`` parallel array), and apply-to-all copy semantics
for both. No arithmetic/percentage summation, EstimateLine snapshot, or
frontend UI exists yet -- Stage 12E owns that.
"""
from decimal import Decimal
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.domain.exceptions import (
    CoefficientOptionNotFoundError,
    OpeningRevealWorkValidationError,
    PriceCoefficientValidationError,
)
from app.domain.services.opening_reveal_work_service import OpeningRevealWorkService
from app.domain.services.price_book_service import PriceBookService
from app.domain.services.price_coefficient_service import PriceCoefficientService
from app.domain.services.work_plan_service import SurfaceWorkPlanService
from app.models.checklist import Substrate
from app.models.opening import Opening, OpeningType
from app.models.opening_reveal_planned_work import (
    OpeningRevealPlannedWork,
    OpeningRevealPlannedWorkCoefficientAssignment,
)
from app.models.price_coefficient import CoefficientGroup, CoefficientOption
from app.models.price_item import PriceCategory, PriceItem, PriceScope, PriceUnit
from app.models.project import Project
from app.models.room import Room
from app.models.surface import Surface, SurfaceType
from app.models.user import User
from app.models.work_plan import SurfacePlannedWork, SurfacePlannedWorkCoefficientAssignment
from tests.conftest import make_telegram_init_data

VALID_USER = {
    "id": 311111111,
    "username": "owner12d",
    "first_name": "Owner",
    "last_name": "User",
    "language_code": "pl",
}

OTHER_USER = {
    "id": 322222222,
    "username": "other12d",
    "first_name": "Other",
    "last_name": "Person",
    "language_code": "pl",
}


def _wp(project_id, room_id, surface_id) -> str:
    return (
        f"/api/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}"
        "/work-plan"
    )


def _reveal(project_id, room_id, surface_id, opening_id) -> str:
    return (
        f"/api/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}"
        f"/openings/{opening_id}/reveal-works"
    )


async def get_token(async_client: AsyncClient, user_dict: dict) -> str:
    init_data = make_telegram_init_data(user_dict)
    resp = await async_client.post(
        "/api/auth/telegram", json={"init_data": init_data}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def _make_user(db, telegram_id: int) -> User:
    user = User(telegram_user_id=telegram_id, username=f"user{telegram_id}")
    db.add(user)
    await db.commit()
    return user


async def _make_project(db, owner_id: uuid.UUID) -> Project:
    project = Project(
        owner_id=owner_id,
        name="Obiekt testowy",
        address="ul. Kwiatowa 1",
        city="Kraków",
        postal_code="30-001",
    )
    db.add(project)
    await db.commit()
    return project


async def _make_room(db, project_id: uuid.UUID) -> Room:
    room = Room(project_id=project_id, name="Salon")
    db.add(room)
    await db.commit()
    return room


async def _make_surface(
    db,
    room_id: uuid.UUID,
    surface_type: SurfaceType = SurfaceType.WALL,
    *,
    name: str = "Ściana",
) -> Surface:
    surface = Surface(room_id=room_id, name=name, surface_type=surface_type)
    db.add(surface)
    await db.commit()
    return surface


async def _make_opening(
    db,
    surface_id: uuid.UUID,
    *,
    reveal_enabled: bool = True,
) -> Opening:
    opening = Opening(
        surface_id=surface_id,
        opening_type=OpeningType.WINDOW,
        width=Decimal("1.200"),
        height=Decimal("1.400"),
        quantity=1,
        reveal_enabled=reveal_enabled,
        reveal_depth=Decimal("0.250") if reveal_enabled else None,
        reveal_left=True,
        reveal_right=True,
        reveal_top=True,
        reveal_bottom=False,
    )
    db.add(opening)
    await db.commit()
    return opening


async def _make_price_item(
    db,
    owner_id: uuid.UUID,
    *,
    code: str | None = None,
    category: PriceCategory = PriceCategory.PAINTING,
    price_scope: PriceScope = PriceScope.LABOR,
    price: str | None = "12.50",
    is_archived: bool = False,
) -> PriceItem:
    item = PriceItem(
        owner_id=owner_id,
        code=code or f"ITEM_{uuid.uuid4().hex[:8].upper()}",
        category=category,
        unit=PriceUnit.M2,
        price_scope=price_scope,
        price=Decimal(price) if price is not None else None,
        is_archived=is_archived,
    )
    db.add(item)
    await db.commit()
    return item


async def _make_group_with_options(
    db,
    owner_id: uuid.UUID,
    *,
    percentages: list[str],
    base_index: int = 0,
) -> tuple[CoefficientGroup, list[CoefficientOption]]:
    service = PriceCoefficientService(db)
    group = await service.create_group(owner_id, display_name="Grupa testowa")
    options = []
    for i, pct in enumerate(percentages):
        option = await service.create_option(
            owner_id,
            group.id,
            display_name=f"Opcja {i}",
            percentage=Decimal(pct),
            is_base=(i == base_index),
        )
        options.append(option)
    return group, options


def upsert_payload(**overrides) -> dict:
    payload = dict(
        substrate="GYPSUM_PLASTER",
        quality_target=None,
        price_item_ids=[],
    )
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Surface: coefficient assignment via HTTP PUT
# ---------------------------------------------------------------------------

class TestSurfacePlannedWorkCoefficients:
    async def test_no_coefficients_backward_compatible(
        self, async_client: AsyncClient, db_session
    ):
        token = await get_token(async_client, VALID_USER)
        headers = auth_header(token)
        owner = (
            await db_session.execute(
                select(User).where(User.telegram_user_id == VALID_USER["id"])
            )
        ).scalar_one()
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, owner.id)
        resp = await async_client.put(
            _wp(project.id, room.id, surface.id),
            headers=headers,
            json=upsert_payload(price_item_ids=[str(item.id)]),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["planned_works"][0]["coefficient_options"] == []

    async def test_one_coefficient_assigned(
        self, async_client: AsyncClient, db_session
    ):
        token = await get_token(async_client, VALID_USER)
        headers = auth_header(token)
        owner = (
            await db_session.execute(
                select(User).where(User.telegram_user_id == VALID_USER["id"])
            )
        ).scalar_one()
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, owner.id)
        group, options = await _make_group_with_options(
            db_session, owner.id, percentages=["0", "15"]
        )
        resp = await async_client.put(
            _wp(project.id, room.id, surface.id),
            headers=headers,
            json=upsert_payload(
                planned_works=[
                    {
                        "price_item_id": str(item.id),
                        "coefficient_option_ids": [str(options[1].id)],
                    }
                ],
            ),
        )
        assert resp.status_code == 200, resp.text
        work = resp.json()["planned_works"][0]
        assert len(work["coefficient_options"]) == 1
        assert work["coefficient_options"][0]["id"] == str(options[1].id)
        assert work["coefficient_options"][0]["group_code"] == group.code
        assert Decimal(work["coefficient_options"][0]["percentage"]) == Decimal("15")
        assert work["coefficient_options"][0]["is_base"] is False

    async def test_base_zero_percent_persists(
        self, async_client: AsyncClient, db_session
    ):
        token = await get_token(async_client, VALID_USER)
        headers = auth_header(token)
        owner = (
            await db_session.execute(
                select(User).where(User.telegram_user_id == VALID_USER["id"])
            )
        ).scalar_one()
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, owner.id)
        _, options = await _make_group_with_options(
            db_session, owner.id, percentages=["0", "15"]
        )
        resp = await async_client.put(
            _wp(project.id, room.id, surface.id),
            headers=headers,
            json=upsert_payload(
                planned_works=[
                    {
                        "price_item_id": str(item.id),
                        "coefficient_option_ids": [str(options[0].id)],
                    }
                ],
            ),
        )
        assert resp.status_code == 200, resp.text
        work = resp.json()["planned_works"][0]
        assert len(work["coefficient_options"]) == 1
        assert Decimal(work["coefficient_options"][0]["percentage"]) == Decimal("0")
        assert work["coefficient_options"][0]["is_base"] is True

    async def test_multiple_groups_independent(
        self, async_client: AsyncClient, db_session
    ):
        token = await get_token(async_client, VALID_USER)
        headers = auth_header(token)
        owner = (
            await db_session.execute(
                select(User).where(User.telegram_user_id == VALID_USER["id"])
            )
        ).scalar_one()
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, owner.id)
        _, g1_options = await _make_group_with_options(
            db_session, owner.id, percentages=["0", "10"]
        )
        _, g2_options = await _make_group_with_options(
            db_session, owner.id, percentages=["0", "20"]
        )
        resp = await async_client.put(
            _wp(project.id, room.id, surface.id),
            headers=headers,
            json=upsert_payload(
                planned_works=[
                    {
                        "price_item_id": str(item.id),
                        "coefficient_option_ids": [
                            str(g1_options[1].id),
                            str(g2_options[1].id),
                        ],
                    }
                ],
            ),
        )
        assert resp.status_code == 200, resp.text
        ids = {o["id"] for o in resp.json()["planned_works"][0]["coefficient_options"]}
        assert ids == {str(g1_options[1].id), str(g2_options[1].id)}

    async def test_duplicate_option_rejected(
        self, async_client: AsyncClient, db_session
    ):
        token = await get_token(async_client, VALID_USER)
        headers = auth_header(token)
        owner = (
            await db_session.execute(
                select(User).where(User.telegram_user_id == VALID_USER["id"])
            )
        ).scalar_one()
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, owner.id)
        _, options = await _make_group_with_options(
            db_session, owner.id, percentages=["0", "10"]
        )
        resp = await async_client.put(
            _wp(project.id, room.id, surface.id),
            headers=headers,
            json=upsert_payload(
                planned_works=[
                    {
                        "price_item_id": str(item.id),
                        "coefficient_option_ids": [
                            str(options[1].id),
                            str(options[1].id),
                        ],
                    }
                ],
            ),
        )
        assert resp.status_code == 422

    async def test_two_single_select_options_same_group_rejected(
        self, async_client: AsyncClient, db_session
    ):
        token = await get_token(async_client, VALID_USER)
        headers = auth_header(token)
        owner = (
            await db_session.execute(
                select(User).where(User.telegram_user_id == VALID_USER["id"])
            )
        ).scalar_one()
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, owner.id)
        _, options = await _make_group_with_options(
            db_session, owner.id, percentages=["0", "10", "20"]
        )
        resp = await async_client.put(
            _wp(project.id, room.id, surface.id),
            headers=headers,
            json=upsert_payload(
                planned_works=[
                    {
                        "price_item_id": str(item.id),
                        "coefficient_option_ids": [
                            str(options[1].id),
                            str(options[2].id),
                        ],
                    }
                ],
            ),
        )
        assert resp.status_code == 422

    async def test_archived_option_rejected(
        self, async_client: AsyncClient, db_session
    ):
        token = await get_token(async_client, VALID_USER)
        headers = auth_header(token)
        owner = (
            await db_session.execute(
                select(User).where(User.telegram_user_id == VALID_USER["id"])
            )
        ).scalar_one()
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, owner.id)
        _, options = await _make_group_with_options(
            db_session, owner.id, percentages=["0", "10"]
        )
        await PriceCoefficientService(db_session).archive_option(
            owner.id, options[1].id
        )
        resp = await async_client.put(
            _wp(project.id, room.id, surface.id),
            headers=headers,
            json=upsert_payload(
                planned_works=[
                    {
                        "price_item_id": str(item.id),
                        "coefficient_option_ids": [str(options[1].id)],
                    }
                ],
            ),
        )
        assert resp.status_code == 422

    async def test_archived_group_rejected(
        self, async_client: AsyncClient, db_session
    ):
        token = await get_token(async_client, VALID_USER)
        headers = auth_header(token)
        owner = (
            await db_session.execute(
                select(User).where(User.telegram_user_id == VALID_USER["id"])
            )
        ).scalar_one()
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, owner.id)
        group, options = await _make_group_with_options(
            db_session, owner.id, percentages=["0", "10"]
        )
        await PriceCoefficientService(db_session).archive_group(owner.id, group.id)
        resp = await async_client.put(
            _wp(project.id, room.id, surface.id),
            headers=headers,
            json=upsert_payload(
                planned_works=[
                    {
                        "price_item_id": str(item.id),
                        "coefficient_option_ids": [str(options[1].id)],
                    }
                ],
            ),
        )
        assert resp.status_code == 422

    async def test_cross_owner_option_rejected(
        self, async_client: AsyncClient, db_session
    ):
        token_a = await get_token(async_client, VALID_USER)
        headers_a = auth_header(token_a)
        await get_token(async_client, OTHER_USER)
        owner_a = (
            await db_session.execute(
                select(User).where(User.telegram_user_id == VALID_USER["id"])
            )
        ).scalar_one()
        owner_b = (
            await db_session.execute(
                select(User).where(User.telegram_user_id == OTHER_USER["id"])
            )
        ).scalar_one()
        project = await _make_project(db_session, owner_a.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, owner_a.id)
        _, foreign_options = await _make_group_with_options(
            db_session, owner_b.id, percentages=["0", "10"]
        )
        resp = await async_client.put(
            _wp(project.id, room.id, surface.id),
            headers=headers_a,
            json=upsert_payload(
                planned_works=[
                    {
                        "price_item_id": str(item.id),
                        "coefficient_option_ids": [str(foreign_options[1].id)],
                    }
                ],
            ),
        )
        assert resp.status_code == 404

    async def test_material_price_item_rejected(
        self, async_client: AsyncClient, db_session
    ):
        token = await get_token(async_client, VALID_USER)
        headers = auth_header(token)
        owner = (
            await db_session.execute(
                select(User).where(User.telegram_user_id == VALID_USER["id"])
            )
        ).scalar_one()
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(
            db_session, owner.id, price_scope=PriceScope.MATERIAL
        )
        _, options = await _make_group_with_options(
            db_session, owner.id, percentages=["0", "10"]
        )
        resp = await async_client.put(
            _wp(project.id, room.id, surface.id),
            headers=headers,
            json=upsert_payload(
                planned_works=[
                    {
                        "price_item_id": str(item.id),
                        "coefficient_option_ids": [str(options[1].id)],
                    }
                ],
            ),
        )
        assert resp.status_code == 422

    async def test_labor_and_material_price_item_rejected(
        self, async_client: AsyncClient, db_session
    ):
        token = await get_token(async_client, VALID_USER)
        headers = auth_header(token)
        owner = (
            await db_session.execute(
                select(User).where(User.telegram_user_id == VALID_USER["id"])
            )
        ).scalar_one()
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(
            db_session, owner.id, price_scope=PriceScope.LABOR_AND_MATERIAL
        )
        _, options = await _make_group_with_options(
            db_session, owner.id, percentages=["0", "10"]
        )
        resp = await async_client.put(
            _wp(project.id, room.id, surface.id),
            headers=headers,
            json=upsert_payload(
                planned_works=[
                    {
                        "price_item_id": str(item.id),
                        "coefficient_option_ids": [str(options[1].id)],
                    }
                ],
            ),
        )
        assert resp.status_code == 422

    async def test_material_item_with_empty_coefficients_still_valid(
        self, async_client: AsyncClient, db_session
    ):
        token = await get_token(async_client, VALID_USER)
        headers = auth_header(token)
        owner = (
            await db_session.execute(
                select(User).where(User.telegram_user_id == VALID_USER["id"])
            )
        ).scalar_one()
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(
            db_session, owner.id, price_scope=PriceScope.MATERIAL
        )
        resp = await async_client.put(
            _wp(project.id, room.id, surface.id),
            headers=headers,
            json=upsert_payload(
                planned_works=[
                    {"price_item_id": str(item.id), "coefficient_option_ids": []}
                ],
            ),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["planned_works"][0]["coefficient_options"] == []

    async def test_duplicate_price_item_occurrences_independent_coefficients(
        self, async_client: AsyncClient, db_session
    ):
        token = await get_token(async_client, VALID_USER)
        headers = auth_header(token)
        owner = (
            await db_session.execute(
                select(User).where(User.telegram_user_id == VALID_USER["id"])
            )
        ).scalar_one()
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, owner.id)
        _, options = await _make_group_with_options(
            db_session, owner.id, percentages=["0", "10"]
        )
        resp = await async_client.put(
            _wp(project.id, room.id, surface.id),
            headers=headers,
            json=upsert_payload(
                planned_works=[
                    {
                        "price_item_id": str(item.id),
                        "coefficient_option_ids": [str(options[1].id)],
                    },
                    {
                        "price_item_id": str(item.id),
                        "coefficient_option_ids": [],
                    },
                ],
            ),
        )
        assert resp.status_code == 200, resp.text
        works = resp.json()["planned_works"]
        assert len(works) == 2
        assert len(works[0]["coefficient_options"]) == 1
        assert works[1]["coefficient_options"] == []

    async def test_ordering_deterministic(self, async_client: AsyncClient, db_session):
        token = await get_token(async_client, VALID_USER)
        headers = auth_header(token)
        owner = (
            await db_session.execute(
                select(User).where(User.telegram_user_id == VALID_USER["id"])
            )
        ).scalar_one()
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, owner.id)
        coefficient_service = PriceCoefficientService(db_session)
        g1, g1_options = await _make_group_with_options(
            db_session, owner.id, percentages=["0", "10"]
        )
        g2, g2_options = await _make_group_with_options(
            db_session, owner.id, percentages=["0", "20"]
        )
        # Groups default to the same position (0); assign explicit distinct
        # positions so the deterministic ordering has something to sort by.
        await coefficient_service.update_group(owner.id, g1.id, position=0)
        await coefficient_service.update_group(owner.id, g2.id, position=1)
        # Submitted out of catalog order; response must come back deterministic
        # (group.position, then option.position).
        resp = await async_client.put(
            _wp(project.id, room.id, surface.id),
            headers=headers,
            json=upsert_payload(
                planned_works=[
                    {
                        "price_item_id": str(item.id),
                        "coefficient_option_ids": [
                            str(g2_options[1].id),
                            str(g1_options[1].id),
                        ],
                    }
                ],
            ),
        )
        assert resp.status_code == 200, resp.text
        ordered_ids = [
            o["id"] for o in resp.json()["planned_works"][0]["coefficient_options"]
        ]
        assert ordered_ids == [str(g1_options[1].id), str(g2_options[1].id)]

    async def test_replacement_recreates_assignments(
        self, async_client: AsyncClient, db_session
    ):
        token = await get_token(async_client, VALID_USER)
        headers = auth_header(token)
        owner = (
            await db_session.execute(
                select(User).where(User.telegram_user_id == VALID_USER["id"])
            )
        ).scalar_one()
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, owner.id)
        _, options = await _make_group_with_options(
            db_session, owner.id, percentages=["0", "10"]
        )
        await async_client.put(
            _wp(project.id, room.id, surface.id),
            headers=headers,
            json=upsert_payload(
                planned_works=[
                    {
                        "price_item_id": str(item.id),
                        "coefficient_option_ids": [str(options[1].id)],
                    }
                ],
            ),
        )
        rows_before = (
            await db_session.execute(select(SurfacePlannedWorkCoefficientAssignment))
        ).scalars().all()
        assert len(rows_before) == 1
        first_assignment_id = rows_before[0].id

        # Removing the coefficient in a replace must delete the assignment.
        resp = await async_client.put(
            _wp(project.id, room.id, surface.id),
            headers=headers,
            json=upsert_payload(price_item_ids=[str(item.id)]),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["planned_works"][0]["coefficient_options"] == []
        rows_after = (
            await db_session.execute(select(SurfacePlannedWorkCoefficientAssignment))
        ).scalars().all()
        assert rows_after == []
        assert all(row.id != first_assignment_id for row in rows_after)

    async def test_changing_option_replaces_assignment(
        self, async_client: AsyncClient, db_session
    ):
        token = await get_token(async_client, VALID_USER)
        headers = auth_header(token)
        owner = (
            await db_session.execute(
                select(User).where(User.telegram_user_id == VALID_USER["id"])
            )
        ).scalar_one()
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, owner.id)
        _, options = await _make_group_with_options(
            db_session, owner.id, percentages=["0", "10", "20"]
        )
        await async_client.put(
            _wp(project.id, room.id, surface.id),
            headers=headers,
            json=upsert_payload(
                planned_works=[
                    {
                        "price_item_id": str(item.id),
                        "coefficient_option_ids": [str(options[1].id)],
                    }
                ],
            ),
        )
        resp = await async_client.put(
            _wp(project.id, room.id, surface.id),
            headers=headers,
            json=upsert_payload(
                planned_works=[
                    {
                        "price_item_id": str(item.id),
                        "coefficient_option_ids": [str(options[2].id)],
                    }
                ],
            ),
        )
        assert resp.status_code == 200, resp.text
        work = resp.json()["planned_works"][0]
        assert [o["id"] for o in work["coefficient_options"]] == [str(options[2].id)]

    async def test_invalid_replacement_leaves_old_state_unchanged(
        self, async_client: AsyncClient, db_session
    ):
        token = await get_token(async_client, VALID_USER)
        headers = auth_header(token)
        owner = (
            await db_session.execute(
                select(User).where(User.telegram_user_id == VALID_USER["id"])
            )
        ).scalar_one()
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, owner.id)
        _, options = await _make_group_with_options(
            db_session, owner.id, percentages=["0", "10"]
        )
        ok = await async_client.put(
            _wp(project.id, room.id, surface.id),
            headers=headers,
            json=upsert_payload(
                planned_works=[
                    {
                        "price_item_id": str(item.id),
                        "coefficient_option_ids": [str(options[1].id)],
                    }
                ],
            ),
        )
        assert ok.status_code == 200
        # Attempted replace references two SINGLE_SELECT options from one group.
        bad = await async_client.put(
            _wp(project.id, room.id, surface.id),
            headers=headers,
            json=upsert_payload(
                planned_works=[
                    {
                        "price_item_id": str(item.id),
                        "coefficient_option_ids": [
                            str(options[0].id),
                            str(options[1].id),
                        ],
                    }
                ],
            ),
        )
        assert bad.status_code == 422
        after = await async_client.get(
            _wp(project.id, room.id, surface.id), headers=headers
        )
        assert after.status_code == 200
        work = after.json()["planned_works"][0]
        assert [o["id"] for o in work["coefficient_options"]] == [str(options[1].id)]

    async def test_price_item_ids_and_planned_works_both_rejected(
        self, async_client: AsyncClient, db_session
    ):
        token = await get_token(async_client, VALID_USER)
        headers = auth_header(token)
        owner = (
            await db_session.execute(
                select(User).where(User.telegram_user_id == VALID_USER["id"])
            )
        ).scalar_one()
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        item = await _make_price_item(db_session, owner.id)
        resp = await async_client.put(
            _wp(project.id, room.id, surface.id),
            headers=headers,
            json=upsert_payload(
                price_item_ids=[str(item.id)],
                planned_works=[
                    {"price_item_id": str(item.id), "coefficient_option_ids": []}
                ],
            ),
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Surface: apply-to-room-walls copies coefficients
# ---------------------------------------------------------------------------

class TestSurfaceApplyCopiesCoefficients:
    async def test_apply_copies_coefficient_selection(
        self, async_client: AsyncClient, db_session
    ):
        token = await get_token(async_client, VALID_USER)
        headers = auth_header(token)
        owner = (
            await db_session.execute(
                select(User).where(User.telegram_user_id == VALID_USER["id"])
            )
        ).scalar_one()
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        source = await _make_surface(db_session, room.id, name="Ściana 1")
        target = await _make_surface(db_session, room.id, name="Ściana 2")
        item = await _make_price_item(db_session, owner.id)
        _, options = await _make_group_with_options(
            db_session, owner.id, percentages=["0", "15"]
        )
        service = SurfaceWorkPlanService(db_session)
        from app.schemas.work_plan import OrderedPriceItemSelection

        await service.set_plan(
            project.id, room.id, source.id, owner.id,
            substrate=Substrate.GYPSUM_PLASTER,
            planned_works=[
                OrderedPriceItemSelection(
                    price_item_id=item.id,
                    coefficient_option_ids=[options[1].id],
                )
            ],
        )
        resp = await async_client.post(
            f"{_wp(project.id, room.id, source.id)}/apply-to-room-walls",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        target_plan = resp.json()["targets"][0]
        assert [o["id"] for o in target_plan["planned_works"][0]["coefficient_options"]] == [
            str(options[1].id)
        ]

    async def test_apply_rejects_archived_source_coefficient(
        self, async_client: AsyncClient, db_session
    ):
        token = await get_token(async_client, VALID_USER)
        headers = auth_header(token)
        owner = (
            await db_session.execute(
                select(User).where(User.telegram_user_id == VALID_USER["id"])
            )
        ).scalar_one()
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        source = await _make_surface(db_session, room.id, name="Ściana 1")
        await _make_surface(db_session, room.id, name="Ściana 2")
        item = await _make_price_item(db_session, owner.id)
        _, options = await _make_group_with_options(
            db_session, owner.id, percentages=["0", "15"]
        )
        service = SurfaceWorkPlanService(db_session)
        from app.schemas.work_plan import OrderedPriceItemSelection

        await service.set_plan(
            project.id, room.id, source.id, owner.id,
            substrate=Substrate.GYPSUM_PLASTER,
            planned_works=[
                OrderedPriceItemSelection(
                    price_item_id=item.id,
                    coefficient_option_ids=[options[1].id],
                )
            ],
        )
        await PriceCoefficientService(db_session).archive_option(
            owner.id, options[1].id
        )
        resp = await async_client.post(
            f"{_wp(project.id, room.id, source.id)}/apply-to-room-walls",
            headers=headers,
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Reveal: coefficient assignment via service layer (additive parallel array)
# ---------------------------------------------------------------------------

class TestRevealPlannedWorkCoefficients:
    async def test_legacy_call_without_coefficients_unaffected(self, db_session):
        user = await _make_user(db_session, 411001)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id)
        item = await _make_price_item(
            db_session, user.id, category=PriceCategory.REVEAL
        )
        service = OpeningRevealWorkService(db_session)
        works = await service.set_works(opening.id, user.id, [item.id])
        assert works[0].coefficient_options == []

    async def test_one_coefficient_assigned(self, db_session):
        user = await _make_user(db_session, 411002)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id)
        item = await _make_price_item(
            db_session, user.id, category=PriceCategory.REVEAL
        )
        _, options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "10"]
        )
        service = OpeningRevealWorkService(db_session)
        works = await service.set_works(
            opening.id, user.id, [item.id],
            coefficient_option_ids=[[options[1].id]],
        )
        assert [o.id for o in works[0].coefficient_options] == [options[1].id]

    async def test_archived_option_rejected(self, db_session):
        user = await _make_user(db_session, 411003)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id)
        item = await _make_price_item(
            db_session, user.id, category=PriceCategory.REVEAL
        )
        _, options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "10"]
        )
        await PriceCoefficientService(db_session).archive_option(
            user.id, options[1].id
        )
        service = OpeningRevealWorkService(db_session)
        with pytest.raises(PriceCoefficientValidationError):
            await service.set_works(
                opening.id, user.id, [item.id],
                coefficient_option_ids=[[options[1].id]],
            )

    async def test_cross_owner_option_rejected(self, db_session):
        user = await _make_user(db_session, 411004)
        other = await _make_user(db_session, 411005)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id)
        item = await _make_price_item(
            db_session, user.id, category=PriceCategory.REVEAL
        )
        _, foreign_options = await _make_group_with_options(
            db_session, other.id, percentages=["0", "10"]
        )
        service = OpeningRevealWorkService(db_session)
        with pytest.raises(CoefficientOptionNotFoundError):
            await service.set_works(
                opening.id, user.id, [item.id],
                coefficient_option_ids=[[foreign_options[1].id]],
            )

    async def test_material_price_item_rejected(self, db_session):
        user = await _make_user(db_session, 411006)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id)
        item = await _make_price_item(
            db_session, user.id, category=PriceCategory.REVEAL,
            price_scope=PriceScope.MATERIAL,
        )
        _, options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "10"]
        )
        service = OpeningRevealWorkService(db_session)
        with pytest.raises(PriceCoefficientValidationError):
            await service.set_works(
                opening.id, user.id, [item.id],
                coefficient_option_ids=[[options[1].id]],
            )

    async def test_duplicate_occurrences_independent_coefficients(self, db_session):
        user = await _make_user(db_session, 411007)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id)
        item = await _make_price_item(
            db_session, user.id, category=PriceCategory.REVEAL
        )
        _, options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "10"]
        )
        service = OpeningRevealWorkService(db_session)
        works = await service.set_works(
            opening.id, user.id, [item.id, item.id],
            coefficient_option_ids=[[options[1].id], []],
        )
        assert [o.id for o in works[0].coefficient_options] == [options[1].id]
        assert works[1].coefficient_options == []

    async def test_replacement_recreates_assignments(self, db_session):
        user = await _make_user(db_session, 411008)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id)
        item = await _make_price_item(
            db_session, user.id, category=PriceCategory.REVEAL
        )
        _, options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "10"]
        )
        service = OpeningRevealWorkService(db_session)
        await service.set_works(
            opening.id, user.id, [item.id],
            coefficient_option_ids=[[options[1].id]],
        )
        rows = (
            await db_session.execute(
                select(OpeningRevealPlannedWorkCoefficientAssignment)
            )
        ).scalars().all()
        assert len(rows) == 1
        works = await service.set_works(opening.id, user.id, [item.id])
        assert works[0].coefficient_options == []
        rows_after = (
            await db_session.execute(
                select(OpeningRevealPlannedWorkCoefficientAssignment)
            )
        ).scalars().all()
        assert rows_after == []

    async def test_mismatched_parallel_array_length_rejected(self, db_session):
        user = await _make_user(db_session, 411009)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id)
        item = await _make_price_item(
            db_session, user.id, category=PriceCategory.REVEAL
        )
        service = OpeningRevealWorkService(db_session)
        with pytest.raises(OpeningRevealWorkValidationError):
            await service.set_works(
                opening.id, user.id, [item.id],
                coefficient_option_ids=[],
            )


# ---------------------------------------------------------------------------
# Reveal: HTTP contract for planned_works
# ---------------------------------------------------------------------------

class TestRevealPlannedWorkCoefficientsAPI:
    async def test_planned_works_payload_assigns_coefficient(
        self, async_client: AsyncClient, db_session
    ):
        token = await get_token(async_client, VALID_USER)
        headers = auth_header(token)
        owner = (
            await db_session.execute(
                select(User).where(User.telegram_user_id == VALID_USER["id"])
            )
        ).scalar_one()
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id)
        item = await _make_price_item(
            db_session, owner.id, category=PriceCategory.REVEAL
        )
        _, options = await _make_group_with_options(
            db_session, owner.id, percentages=["0", "10"]
        )
        resp = await async_client.put(
            _reveal(project.id, room.id, surface.id, opening.id),
            headers=headers,
            json={
                "planned_works": [
                    {
                        "price_item_id": str(item.id),
                        "coefficient_option_ids": [str(options[1].id)],
                    }
                ]
            },
        )
        assert resp.status_code == 200, resp.text
        assert [
            o["id"] for o in resp.json()["items"][0]["coefficient_options"]
        ] == [str(options[1].id)]

    async def test_legacy_price_item_ids_payload_unaffected(
        self, async_client: AsyncClient, db_session
    ):
        token = await get_token(async_client, VALID_USER)
        headers = auth_header(token)
        owner = (
            await db_session.execute(
                select(User).where(User.telegram_user_id == VALID_USER["id"])
            )
        ).scalar_one()
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id)
        item = await _make_price_item(
            db_session, owner.id, category=PriceCategory.REVEAL
        )
        resp = await async_client.put(
            _reveal(project.id, room.id, surface.id, opening.id),
            headers=headers,
            json={"price_item_ids": [str(item.id)]},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["items"][0]["coefficient_options"] == []

    async def test_price_item_ids_and_planned_works_both_rejected(
        self, async_client: AsyncClient, db_session
    ):
        token = await get_token(async_client, VALID_USER)
        headers = auth_header(token)
        owner = (
            await db_session.execute(
                select(User).where(User.telegram_user_id == VALID_USER["id"])
            )
        ).scalar_one()
        project = await _make_project(db_session, owner.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        opening = await _make_opening(db_session, surface.id)
        item = await _make_price_item(
            db_session, owner.id, category=PriceCategory.REVEAL
        )
        resp = await async_client.put(
            _reveal(project.id, room.id, surface.id, opening.id),
            headers=headers,
            json={
                "price_item_ids": [str(item.id)],
                "planned_works": [
                    {"price_item_id": str(item.id), "coefficient_option_ids": []}
                ],
            },
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Reveal: apply-to-room-openings copies coefficients
# ---------------------------------------------------------------------------

class TestRevealApplyCopiesCoefficients:
    async def test_apply_copies_coefficient_selection(self, db_session):
        user = await _make_user(db_session, 411010)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        source_surface = await _make_surface(db_session, room.id, name="Ściana 1")
        target_surface = await _make_surface(db_session, room.id, name="Ściana 2")
        source_opening = await _make_opening(db_session, source_surface.id)
        target_opening = await _make_opening(db_session, target_surface.id)
        item = await _make_price_item(
            db_session, user.id, category=PriceCategory.REVEAL
        )
        _, options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "10"]
        )
        service = OpeningRevealWorkService(db_session)
        await service.set_works(
            source_opening.id, user.id, [item.id],
            coefficient_option_ids=[[options[1].id]],
        )
        await service.apply_to_room_openings(
            project.id, room.id, source_opening.id, user.id
        )
        target_works = await service.get_works(target_opening.id, user.id)
        assert [o.id for o in target_works[0].coefficient_options] == [options[1].id]

    async def test_apply_rejects_archived_source_coefficient(self, db_session):
        user = await _make_user(db_session, 411011)
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        source_surface = await _make_surface(db_session, room.id, name="Ściana 1")
        target_surface = await _make_surface(db_session, room.id, name="Ściana 2")
        source_opening = await _make_opening(db_session, source_surface.id)
        await _make_opening(db_session, target_surface.id)
        item = await _make_price_item(
            db_session, user.id, category=PriceCategory.REVEAL
        )
        _, options = await _make_group_with_options(
            db_session, user.id, percentages=["0", "10"]
        )
        service = OpeningRevealWorkService(db_session)
        await service.set_works(
            source_opening.id, user.id, [item.id],
            coefficient_option_ids=[[options[1].id]],
        )
        await PriceCoefficientService(db_session).archive_option(
            user.id, options[1].id
        )
        with pytest.raises(OpeningRevealWorkValidationError):
            await service.apply_to_room_openings(
                project.id, room.id, source_opening.id, user.id
            )
