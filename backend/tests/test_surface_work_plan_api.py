"""Focused Stage 10B.2 API tests: Surface Work Plan HTTP + apply-to-room-walls.

Covers the three sub-resource routes (GET / PUT / POST apply) under the exact
canonical paths, owner isolation with hidden 404s, PUT upsert semantics
(ordered and duplicate PriceItems preserved, NULL quality, S/Q compatibility,
archived/foreign/NULL-price items, atomic replacement), and the WALL-only
apply-to-all bulk action (active targets only, replace semantics, independent
target plans, untouched geometry/openings/inspections, archived-source-item
rejection, NULL-price propagation, cross-owner hiding, no Price Book mutation).
"""
from decimal import Decimal
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.domain.exceptions import SurfaceWorkPlanValidationError
from app.domain.services.price_book_service import PriceBookService
from app.domain.services.work_plan_service import SurfaceWorkPlanService
from app.models.checklist import ChecklistTemplate, QualityLevel, Substrate
from app.models.inspection import Inspection, InspectionStatus
from app.models.opening import Opening, OpeningType
from app.models.price_item import PriceCategory, PriceItem, PriceUnit
from app.models.project import Project
from app.models.room import Room
from app.models.surface import Surface, SurfaceType
from app.models.user import User
from app.models.work_plan import SurfacePlannedWork, SurfaceWorkPlan
from app.schemas.work_plan import OrderedPriceItemSelection
from tests.conftest import make_telegram_init_data

VALID_USER = {
    "id": 111111111,
    "username": "owner",
    "first_name": "Owner",
    "last_name": "User",
    "language_code": "pl",
}

OTHER_USER = {
    "id": 222222222,
    "username": "other",
    "first_name": "Other",
    "last_name": "Person",
    "language_code": "pl",
}


def _wp(project_id, room_id, surface_id) -> str:
    return (
        f"/api/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}"
        "/work-plan"
    )


def _apply(project_id, room_id, source_surface_id) -> str:
    return f"{_wp(project_id, room_id, source_surface_id)}/apply-to-room-walls"


async def get_token(async_client: AsyncClient, user_dict: dict) -> str:
    init_data = make_telegram_init_data(user_dict)
    resp = await async_client.post(
        "/api/auth/telegram", json={"init_data": init_data}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def upsert_payload(**overrides) -> dict:
    payload = dict(
        substrate="GYPSUM_PLASTER",
        quality_target="S3",
        price_item_ids=[],
    )
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# DB helpers (mirror the Stage 10B.1 service-test helpers, enriched for walls)
# ---------------------------------------------------------------------------

async def _make_user(db, telegram_id: int) -> User:
    user = User(telegram_user_id=telegram_id, username=f"user{telegram_id}")
    db.add(user)
    await db.commit()
    return user


async def _make_project(
    db, owner_id: uuid.UUID, *, name: str = "Obiekt testowy"
) -> Project:
    project = Project(
        owner_id=owner_id,
        name=name,
        address="ul. Kwiatowa 1",
        city="Kraków",
        postal_code="30-001",
    )
    db.add(project)
    await db.commit()
    return project


async def _make_room(db, project_id: uuid.UUID, *, name: str = "Salon") -> Room:
    room = Room(project_id=project_id, name=name)
    db.add(room)
    await db.commit()
    return room


async def _make_surface(
    db,
    room_id: uuid.UUID,
    surface_type: SurfaceType = SurfaceType.WALL,
    *,
    name: str = "Ściana",
    position: int | None = None,
    width: Decimal | None = None,
    height: Decimal | None = None,
    is_archived: bool = False,
) -> Surface:
    surface = Surface(
        room_id=room_id,
        name=name,
        surface_type=surface_type,
        position=position,
        width=width,
        height=height,
        is_archived=is_archived,
    )
    db.add(surface)
    await db.commit()
    return surface


async def _make_price_item(
    db,
    owner_id: uuid.UUID,
    *,
    code: str | None = None,
    price: str | None = "12.50",
    is_archived: bool = False,
) -> PriceItem:
    item = PriceItem(
        owner_id=owner_id,
        code=code or f"ITEM_{uuid.uuid4().hex[:8].upper()}",
        category=PriceCategory.PAINTING,
        unit=PriceUnit.M2,
        price=Decimal(price) if price is not None else None,
        is_archived=is_archived,
    )
    db.add(item)
    await db.commit()
    return item


def _selection(*price_item_ids: uuid.UUID) -> list[OrderedPriceItemSelection]:
    return [OrderedPriceItemSelection(price_item_id=i) for i in price_item_ids]


def _plan_json(resp) -> dict:
    return resp.json()


# ---------------------------------------------------------------------------
# Unauthenticated access
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/projects/00000000-0000-0000-0000-000000000000/rooms/00000000-0000-0000-0000-000000000000/surfaces/00000000-0000-0000-0000-000000000000/work-plan"),
        ("PUT", "/api/projects/00000000-0000-0000-0000-000000000000/rooms/00000000-0000-0000-0000-000000000000/surfaces/00000000-0000-0000-0000-000000000000/work-plan"),
        ("POST", "/api/projects/00000000-0000-0000-0000-000000000000/rooms/00000000-0000-0000-0000-000000000000/surfaces/00000000-0000-0000-0000-000000000000/work-plan/apply-to-room-walls"),
    ],
)
async def test_unauthenticated_401(async_client: AsyncClient, method: str, path: str):
    resp = await async_client.request(method, path, json={})
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET work plan
# ---------------------------------------------------------------------------

async def test_get_wall_plan(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    owner = (
        await db_session.execute(
            select(User).where(User.telegram_user_id == VALID_USER["id"])
        )
    ).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    surface = await _make_surface(db_session, room.id, position=0)
    item_a = await _make_price_item(db_session, owner.id, code="A")
    item_b = await _make_price_item(db_session, owner.id, code="B")
    service = SurfaceWorkPlanService(db_session)
    await service.set_plan(
        project.id, room.id, surface.id, owner.id,
        substrate=Substrate.GYPSUM_PLASTER,
        quality_target=QualityLevel.S3,
        planned_works=_selection(item_a.id, item_b.id),
    )
    resp = await async_client.get(_wp(project.id, room.id, surface.id), headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["substrate"] == "GYPSUM_PLASTER"
    assert data["quality_target"] == "S3"
    assert [w["price_item_id"] for w in data["planned_works"]] == [
        str(item_a.id),
        str(item_b.id),
    ]
    # Embedded Price Book summary: enough for 10C, no market evidence.
    first = data["planned_works"][0]
    assert first["price_item"]["id"] == str(item_a.id)
    assert first["price_item"]["code"] == "A"
    assert first["price_item"]["price"] == "12.50"
    assert first["price_item"]["is_archived"] is False
    assert "sources" not in first["price_item"]


async def test_get_floor_plan(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    owner = (
        await db_session.execute(
            select(User).where(User.telegram_user_id == VALID_USER["id"])
        )
    ).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    surface = await _make_surface(db_session, room.id, SurfaceType.FLOOR)
    item = await _make_price_item(db_session, owner.id)
    service = SurfaceWorkPlanService(db_session)
    await service.set_plan(
        project.id, room.id, surface.id, owner.id,
        substrate=Substrate.CONCRETE,
        quality_target=QualityLevel.S2,
        planned_works=_selection(item.id),
    )
    resp = await async_client.get(_wp(project.id, room.id, surface.id), headers=headers)
    assert resp.status_code == 200
    assert resp.json()["substrate"] == "CONCRETE"


async def test_get_ceiling_plan(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    owner = (
        await db_session.execute(
            select(User).where(User.telegram_user_id == VALID_USER["id"])
        )
    ).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    surface = await _make_surface(db_session, room.id, SurfaceType.CEILING)
    item = await _make_price_item(db_session, owner.id)
    service = SurfaceWorkPlanService(db_session)
    await service.set_plan(
        project.id, room.id, surface.id, owner.id,
        substrate=Substrate.GYPSUM_PLASTER,
        quality_target=QualityLevel.S3,
        planned_works=_selection(item.id),
    )
    resp = await async_client.get(_wp(project.id, room.id, surface.id), headers=headers)
    assert resp.status_code == 200
    assert resp.json()["quality_target"] == "S3"


async def test_get_no_plan_returns_404(async_client: AsyncClient, db_session):
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
    resp = await async_client.get(_wp(project.id, room.id, surface.id), headers=headers)
    assert resp.status_code == 404


async def test_get_foreign_surface_hidden(async_client: AsyncClient, db_session):
    token_a = await get_token(async_client, VALID_USER)
    headers_a = auth_header(token_a)
    token_b = await get_token(async_client, OTHER_USER)
    headers_b = auth_header(token_b)
    owner_a = (
        await db_session.execute(
            select(User).where(User.telegram_user_id == VALID_USER["id"])
        )
    ).scalar_one()
    project = await _make_project(db_session, owner_a.id)
    room = await _make_room(db_session, project.id)
    surface = await _make_surface(db_session, room.id)
    item = await _make_price_item(db_session, owner_a.id)
    service = SurfaceWorkPlanService(db_session)
    await service.set_plan(
        project.id, room.id, surface.id, owner_a.id,
        substrate=Substrate.CONCRETE,
        planned_works=_selection(item.id),
    )
    # Owner B must not see the plan or even discover the surface.
    resp = await async_client.get(
        _wp(project.id, room.id, surface.id), headers=headers_b
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PUT / upsert work plan
# ---------------------------------------------------------------------------

async def test_put_create_plan(async_client: AsyncClient, db_session):
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
    data = resp.json()
    assert data["surface_id"] == str(surface.id)
    assert data["substrate"] == "GYPSUM_PLASTER"
    assert data["quality_target"] == "S3"
    assert [w["position"] for w in data["planned_works"]] == [0]


async def test_put_update_existing_plan(async_client: AsyncClient, db_session):
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
    item_a = await _make_price_item(db_session, owner.id, code="A")
    item_b = await _make_price_item(db_session, owner.id, code="B")
    await async_client.put(
        _wp(project.id, room.id, surface.id),
        headers=headers,
        json=upsert_payload(price_item_ids=[str(item_a.id)]),
    )
    resp = await async_client.put(
        _wp(project.id, room.id, surface.id),
        headers=headers,
        json=upsert_payload(
            substrate="CONCRETE",
            quality_target="S2",
            price_item_ids=[str(item_b.id), str(item_a.id)],
        ),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["substrate"] == "CONCRETE"
    assert data["quality_target"] == "S2"
    assert [w["price_item_id"] for w in data["planned_works"]] == [
        str(item_b.id),
        str(item_a.id),
    ]


async def test_put_ordered_works_preserved(async_client: AsyncClient, db_session):
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
    ids = [str((await _make_price_item(db_session, owner.id)).id) for _ in range(4)]
    resp = await async_client.put(
        _wp(project.id, room.id, surface.id),
        headers=headers,
        json=upsert_payload(price_item_ids=ids),
    )
    assert resp.status_code == 200, resp.text
    works = resp.json()["planned_works"]
    assert [w["position"] for w in works] == [0, 1, 2, 3]
    assert [w["price_item_id"] for w in works] == ids


async def test_put_duplicate_items_preserved(async_client: AsyncClient, db_session):
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
    item = await _make_price_item(db_session, owner.id, code="SKIM")
    # preparation, primer, skim, sanding, primer, painting — repeated primer row.
    resp = await async_client.put(
        _wp(project.id, room.id, surface.id),
        headers=headers,
        json=upsert_payload(price_item_ids=[str(item.id), str(item.id)]),
    )
    assert resp.status_code == 200, resp.text
    works = resp.json()["planned_works"]
    assert [w["price_item_id"] for w in works] == [str(item.id), str(item.id)]
    assert [w["position"] for w in works] == [0, 1]
    # Both rows persist in the DB.
    rows = (
        await db_session.execute(
            select(SurfacePlannedWork).order_by(SurfacePlannedWork.position)
        )
    ).scalars().all()
    assert len(rows) == 2


async def test_put_null_quality_accepted(async_client: AsyncClient, db_session):
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
    resp = await async_client.put(
        _wp(project.id, room.id, surface.id),
        headers=headers,
        json=upsert_payload(quality_target=None),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["quality_target"] is None


async def test_put_incompatible_quality_rejected(async_client: AsyncClient, db_session):
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
    # GYPSUM_BOARD uses Q1–Q4; S3 is the S-scale.
    resp = await async_client.put(
        _wp(project.id, room.id, surface.id),
        headers=headers,
        json=upsert_payload(substrate="GYPSUM_BOARD", quality_target="S3"),
    )
    assert resp.status_code == 422


async def test_put_substrate_change_no_silent_conversion(
    async_client: AsyncClient, db_session
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
    ok = await async_client.put(
        _wp(project.id, room.id, surface.id),
        headers=headers,
        json=upsert_payload(),  # GYPSUM_PLASTER + S3
    )
    assert ok.status_code == 200
    # Substrate change with an incompatible quality must fail, not convert S3→Q3.
    bad = await async_client.put(
        _wp(project.id, room.id, surface.id),
        headers=headers,
        json=upsert_payload(substrate="GYPSUM_BOARD", quality_target="S3"),
    )
    assert bad.status_code == 422
    # The failed request left the accepted configuration untouched.
    after = await async_client.get(
        _wp(project.id, room.id, surface.id), headers=headers
    )
    assert after.status_code == 200
    assert after.json()["substrate"] == "GYPSUM_PLASTER"
    assert after.json()["quality_target"] == "S3"
    # Explicit clearing is the required path.
    cleared = await async_client.put(
        _wp(project.id, room.id, surface.id),
        headers=headers,
        json=upsert_payload(substrate="GYPSUM_BOARD", quality_target=None),
    )
    assert cleared.status_code == 200
    assert cleared.json()["substrate"] == "GYPSUM_BOARD"
    assert cleared.json()["quality_target"] is None


async def test_put_archived_item_rejected(async_client: AsyncClient, db_session):
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
    await PriceBookService(db_session).archive_item(owner.id, item.id)
    resp = await async_client.put(
        _wp(project.id, room.id, surface.id),
        headers=headers,
        json=upsert_payload(price_item_ids=[str(item.id)]),
    )
    assert resp.status_code == 422
    # No plan was created by the failed request.
    after = await async_client.get(
        _wp(project.id, room.id, surface.id), headers=headers
    )
    assert after.status_code == 404


async def test_put_null_price_item_accepted(async_client: AsyncClient, db_session):
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
    item = await _make_price_item(db_session, owner.id, price=None)
    resp = await async_client.put(
        _wp(project.id, room.id, surface.id),
        headers=headers,
        json=upsert_payload(price_item_ids=[str(item.id)]),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["planned_works"][0]["price_item"]["price"] is None


async def test_put_foreign_item_rejected(async_client: AsyncClient, db_session):
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
    foreign_item = await _make_price_item(db_session, owner_b.id)
    resp = await async_client.put(
        _wp(project.id, room.id, surface.id),
        headers=headers_a,
        json=upsert_payload(price_item_ids=[str(foreign_item.id)]),
    )
    assert resp.status_code == 404


async def test_put_replacement_atomic_on_invalid_item(
    async_client: AsyncClient, db_session
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
    a = await _make_price_item(db_session, owner.id, code="A")
    b = await _make_price_item(db_session, owner.id, code="B")
    c = await _make_price_item(db_session, owner.id, code="C")
    d = await _make_price_item(db_session, owner.id, code="D")
    ok = await async_client.put(
        _wp(project.id, room.id, surface.id),
        headers=headers,
        json=upsert_payload(price_item_ids=[str(a.id), str(b.id), str(c.id)]),
    )
    assert ok.status_code == 200
    # b is archived; the next PUT must not partially replace the works.
    await PriceBookService(db_session).archive_item(owner.id, b.id)
    bad = await async_client.put(
        _wp(project.id, room.id, surface.id),
        headers=headers,
        json=upsert_payload(price_item_ids=[str(d.id), str(b.id), str(a.id)]),
    )
    assert bad.status_code == 422
    after = await async_client.get(
        _wp(project.id, room.id, surface.id), headers=headers
    )
    assert after.status_code == 200
    assert [w["price_item_id"] for w in after.json()["planned_works"]] == [
        str(a.id),
        str(b.id),
        str(c.id),
    ]


# ---------------------------------------------------------------------------
# Apply to all walls
# ---------------------------------------------------------------------------

async def _wall_room(db_session, owner_id, wall_count: int, source_position: int = 0):
    """Room with ``wall_count`` active WALL surfaces (positions 0..n-1)."""
    project = await _make_project(db_session, owner_id)
    room = await _make_room(db_session, project.id)
    surfaces = [
        await _make_surface(
            db_session, room.id, name=f"Ściana {i}", position=i
        )
        for i in range(wall_count)
    ]
    return project, room, surfaces


async def test_apply_copies_to_all_active_walls(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    owner = (
        await db_session.execute(
            select(User).where(User.telegram_user_id == VALID_USER["id"])
        )
    ).scalar_one()
    project, room, walls = await _wall_room(db_session, owner.id, 4)
    source = walls[0]
    item_a = await _make_price_item(db_session, owner.id, code="A")
    item_b = await _make_price_item(db_session, owner.id, code="B")
    service = SurfaceWorkPlanService(db_session)
    await service.set_plan(
        project.id, room.id, source.id, owner.id,
        substrate=Substrate.GYPSUM_PLASTER,
        quality_target=QualityLevel.S3,
        planned_works=_selection(item_a.id, item_b.id),
    )
    resp = await async_client.post(_apply(project.id, room.id, source.id), headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["source_surface_id"] == str(source.id)
    assert data["target_count"] == 3
    # Target ordering follows surface position: walls[1], walls[2], walls[3].
    assert data["target_surface_ids"] == [str(w.id) for w in walls[1:]]
    for target in data["targets"]:
        assert target["substrate"] == "GYPSUM_PLASTER"
        assert target["quality_target"] == "S3"
        assert [w["price_item_id"] for w in target["planned_works"]] == [
            str(item_a.id),
            str(item_b.id),
        ]
    # Persisted: each target has its own plan rows.
    for wall in walls[1:]:
        plan = (
            await db_session.execute(
                select(SurfaceWorkPlan).where(SurfaceWorkPlan.surface_id == wall.id)
            )
        ).scalar_one()
        rows = (
            await db_session.execute(
                select(SurfacePlannedWork)
                .where(SurfacePlannedWork.work_plan_id == plan.id)
                .order_by(SurfacePlannedWork.position)
            )
        ).scalars().all()
        assert len(rows) == 2


async def test_apply_source_unchanged(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    owner = (
        await db_session.execute(
            select(User).where(User.telegram_user_id == VALID_USER["id"])
        )
    ).scalar_one()
    project, room, walls = await _wall_room(db_session, owner.id, 2)
    source = walls[0]
    item = await _make_price_item(db_session, owner.id)
    service = SurfaceWorkPlanService(db_session)
    await service.set_plan(
        project.id, room.id, source.id, owner.id,
        substrate=Substrate.GYPSUM_PLASTER,
        quality_target=QualityLevel.S3,
        planned_works=_selection(item.id),
    )
    await async_client.post(_apply(project.id, room.id, source.id), headers=headers)
    resp = await async_client.get(_wp(project.id, room.id, source.id), headers=headers)
    assert resp.status_code == 200
    assert resp.json()["substrate"] == "GYPSUM_PLASTER"
    assert resp.json()["quality_target"] == "S3"
    assert [w["price_item_id"] for w in resp.json()["planned_works"]] == [
        str(item.id)
    ]


async def test_apply_replaces_existing_target_plans(
    async_client: AsyncClient, db_session
):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    owner = (
        await db_session.execute(
            select(User).where(User.telegram_user_id == VALID_USER["id"])
        )
    ).scalar_one()
    project, room, walls = await _wall_room(db_session, owner.id, 2)
    source, target = walls
    source_item = await _make_price_item(db_session, owner.id, code="SRC")
    target_item = await _make_price_item(db_session, owner.id, code="TGT")
    service = SurfaceWorkPlanService(db_session)
    await service.set_plan(
        project.id, room.id, source.id, owner.id,
        substrate=Substrate.GYPSUM_PLASTER,
        quality_target=QualityLevel.S3,
        planned_works=_selection(source_item.id),
    )
    await service.set_plan(
        project.id, room.id, target.id, owner.id,
        substrate=Substrate.CONCRETE,
        quality_target=QualityLevel.S2,
        planned_works=_selection(target_item.id),
    )
    resp = await async_client.post(_apply(project.id, room.id, source.id), headers=headers)
    assert resp.status_code == 200
    # Wall 2 planning configuration was replaced; nothing else changed.
    after = await async_client.get(
        _wp(project.id, room.id, target.id), headers=headers
    )
    assert after.status_code == 200
    assert after.json()["substrate"] == "GYPSUM_PLASTER"
    assert after.json()["quality_target"] == "S3"
    assert [w["price_item_id"] for w in after.json()["planned_works"]] == [
        str(source_item.id)
    ]
    assert target_item.price == Decimal("12.50")


async def test_apply_targets_independent_after_copy(
    async_client: AsyncClient, db_session
):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    owner = (
        await db_session.execute(
            select(User).where(User.telegram_user_id == VALID_USER["id"])
        )
    ).scalar_one()
    project, room, walls = await _wall_room(db_session, owner.id, 4)
    source, w2, w3, w4 = walls
    item_a = await _make_price_item(db_session, owner.id, code="A")
    item_b = await _make_price_item(db_session, owner.id, code="B")
    service = SurfaceWorkPlanService(db_session)
    await service.set_plan(
        project.id, room.id, source.id, owner.id,
        substrate=Substrate.GYPSUM_PLASTER,
        quality_target=QualityLevel.S3,
        planned_works=_selection(item_a.id, item_b.id),
    )
    await async_client.post(_apply(project.id, room.id, source.id), headers=headers)
    # Edit wall 2 after the copy — walls 1/3/4 must not change.
    await service.replace_planned_works(
        project.id, room.id, w2.id, owner.id, planned_works=_selection(item_a.id)
    )
    for wall in (source, w3, w4):
        plan = await service.get_work_plan(project.id, room.id, wall.id, owner.id)
        assert [w.price_item_id for w in plan.planned_works] == [
            item_a.id,
            item_b.id,
        ]
    w2_plan = await service.get_work_plan(project.id, room.id, w2.id, owner.id)
    assert [w.price_item_id for w in w2_plan.planned_works] == [item_a.id]


async def test_apply_geometry_unchanged(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    owner = (
        await db_session.execute(
            select(User).where(User.telegram_user_id == VALID_USER["id"])
        )
    ).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    source = await _make_surface(
        db_session, room.id, width=Decimal("4000.000"), height=Decimal("2600.000")
    )
    target = await _make_surface(
        db_session, room.id, name="Ściana z oknem",
        width=Decimal("5000.000"), height=Decimal("2600.000"),
    )
    item = await _make_price_item(db_session, owner.id)
    service = SurfaceWorkPlanService(db_session)
    await service.set_plan(
        project.id, room.id, source.id, owner.id,
        substrate=Substrate.GYPSUM_PLASTER,
        quality_target=QualityLevel.S3,
        planned_works=_selection(item.id),
    )
    resp = await async_client.post(_apply(project.id, room.id, source.id), headers=headers)
    assert resp.status_code == 200
    target_after = (
        await db_session.execute(
            select(Surface).where(Surface.id == target.id)
        )
    ).scalar_one()
    assert target_after.width == Decimal("5000.000")
    assert target_after.height == Decimal("2600.000")
    assert target_after.name == "Ściana z oknem"


async def test_apply_openings_unchanged(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    owner = (
        await db_session.execute(
            select(User).where(User.telegram_user_id == VALID_USER["id"])
        )
    ).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    source = await _make_surface(db_session, room.id)
    target = await _make_surface(db_session, room.id, name="Ściana z oknem")
    opening = Opening(
        surface_id=target.id,
        opening_type=OpeningType.WINDOW,
        name="Okno salon",
        width=Decimal("120.000"),
        height=Decimal("140.000"),
        quantity=1,
    )
    db_session.add(opening)
    await db_session.commit()
    item = await _make_price_item(db_session, owner.id)
    service = SurfaceWorkPlanService(db_session)
    await service.set_plan(
        project.id, room.id, source.id, owner.id,
        substrate=Substrate.GYPSUM_PLASTER,
        quality_target=QualityLevel.S3,
        planned_works=_selection(item.id),
    )
    resp = await async_client.post(_apply(project.id, room.id, source.id), headers=headers)
    assert resp.status_code == 200
    opening_after = (
        await db_session.execute(
            select(Opening).where(Opening.id == opening.id)
        )
    ).scalar_one()
    assert opening_after.opening_type == OpeningType.WINDOW
    assert opening_after.width == Decimal("120.000")
    assert opening_after.height == Decimal("140.000")


async def test_apply_inspection_unchanged(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    owner = (
        await db_session.execute(
            select(User).where(User.telegram_user_id == VALID_USER["id"])
        )
    ).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    source = await _make_surface(db_session, room.id)
    target = await _make_surface(db_session, room.id, name="Ściana badana")
    template = ChecklistTemplate(code=f"TPL_{uuid.uuid4().hex[:8]}", version=1, title_key="x")
    db_session.add(template)
    await db_session.commit()
    inspection = Inspection(
        room_id=room.id,
        surface_id=target.id,
        template_id=template.id,
        substrate=Substrate.CONCRETE,
        quality_target=QualityLevel.S2,
        status=InspectionStatus.DRAFT,
    )
    db_session.add(inspection)
    await db_session.commit()
    item = await _make_price_item(db_session, owner.id)
    service = SurfaceWorkPlanService(db_session)
    await service.set_plan(
        project.id, room.id, source.id, owner.id,
        substrate=Substrate.GYPSUM_PLASTER,
        quality_target=QualityLevel.S3,
        planned_works=_selection(item.id),
    )
    resp = await async_client.post(_apply(project.id, room.id, source.id), headers=headers)
    assert resp.status_code == 200
    inspection_after = (
        await db_session.execute(
            select(Inspection).where(Inspection.id == inspection.id)
        )
    ).scalar_one()
    assert inspection_after.substrate == Substrate.CONCRETE
    assert inspection_after.quality_target == QualityLevel.S2
    assert inspection_after.status == InspectionStatus.DRAFT


async def test_apply_archived_walls_skipped(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    owner = (
        await db_session.execute(
            select(User).where(User.telegram_user_id == VALID_USER["id"])
        )
    ).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    source = await _make_surface(db_session, room.id, position=0)
    archived = await _make_surface(
        db_session, room.id, name="Ściana archiwowana", position=1, is_archived=True
    )
    active = await _make_surface(db_session, room.id, name="Ściana aktywna", position=2)
    item = await _make_price_item(db_session, owner.id)
    service = SurfaceWorkPlanService(db_session)
    await service.set_plan(
        project.id, room.id, source.id, owner.id,
        substrate=Substrate.GYPSUM_PLASTER,
        quality_target=QualityLevel.S3,
        planned_works=_selection(item.id),
    )
    resp = await async_client.post(_apply(project.id, room.id, source.id), headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["target_count"] == 1
    assert data["target_surface_ids"] == [str(active.id)]
    # Archived wall was not touched and keeps no plan.
    archived_plan = await service.get_work_plan(project.id, room.id, archived.id, owner.id)
    assert archived_plan is None


@pytest.mark.parametrize(
    "surface_type", [SurfaceType.FLOOR, SurfaceType.CEILING, SurfaceType.OTHER]
)
async def test_apply_non_wall_rejected(
    async_client: AsyncClient, db_session, surface_type
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
    source = await _make_surface(db_session, room.id, surface_type)
    item = await _make_price_item(db_session, owner.id)
    service = SurfaceWorkPlanService(db_session)
    await service.set_plan(
        project.id, room.id, source.id, owner.id,
        substrate=Substrate.CONCRETE,
        planned_works=_selection(item.id),
    )
    resp = await async_client.post(_apply(project.id, room.id, source.id), headers=headers)
    assert resp.status_code == 422


async def test_apply_no_source_plan_rejected(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    owner = (
        await db_session.execute(
            select(User).where(User.telegram_user_id == VALID_USER["id"])
        )
    ).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    source = await _make_surface(db_session, room.id)
    await _make_surface(db_session, room.id, name="Ściana 2")
    resp = await async_client.post(_apply(project.id, room.id, source.id), headers=headers)
    assert resp.status_code == 404


async def test_apply_zero_targets_success(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    owner = (
        await db_session.execute(
            select(User).where(User.telegram_user_id == VALID_USER["id"])
        )
    ).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    source = await _make_surface(db_session, room.id)
    item = await _make_price_item(db_session, owner.id)
    service = SurfaceWorkPlanService(db_session)
    await service.set_plan(
        project.id, room.id, source.id, owner.id,
        substrate=Substrate.GYPSUM_PLASTER,
        quality_target=QualityLevel.S3,
        planned_works=_selection(item.id),
    )
    resp = await async_client.post(_apply(project.id, room.id, source.id), headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["target_count"] == 0
    assert resp.json()["target_surface_ids"] == []
    assert resp.json()["targets"] == []


async def test_apply_archived_source_item_rejected_atomically(
    async_client: AsyncClient, db_session
):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    owner = (
        await db_session.execute(
            select(User).where(User.telegram_user_id == VALID_USER["id"])
        )
    ).scalar_one()
    project, room, walls = await _wall_room(db_session, owner.id, 3)
    source = walls[0]
    item = await _make_price_item(db_session, owner.id, code="SRC")
    target_item = await _make_price_item(db_session, owner.id, code="TGT")
    service = SurfaceWorkPlanService(db_session)
    await service.set_plan(
        project.id, room.id, source.id, owner.id,
        substrate=Substrate.GYPSUM_PLASTER,
        quality_target=QualityLevel.S3,
        planned_works=_selection(item.id),
    )
    # Wall 2 already has its own plan; it must survive the failed apply.
    await service.set_plan(
        project.id, room.id, walls[1].id, owner.id,
        substrate=Substrate.CONCRETE,
        quality_target=QualityLevel.S2,
        planned_works=_selection(target_item.id),
    )
    # Archive the item now referenced by the source plan.
    await PriceBookService(db_session).archive_item(owner.id, item.id)
    resp = await async_client.post(_apply(project.id, room.id, source.id), headers=headers)
    assert resp.status_code == 422
    # No target was updated — the batch is atomic.
    for wall in walls[1:]:
        plan = await service.get_work_plan(project.id, room.id, wall.id, owner.id)
        if wall == walls[1]:
            assert plan is not None
            assert plan.substrate == Substrate.CONCRETE
            assert plan.quality_target == QualityLevel.S2
            assert [w.price_item_id for w in plan.planned_works] == [target_item.id]
        else:
            assert plan is None


async def test_apply_null_price_source_item_copies(
    async_client: AsyncClient, db_session
):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    owner = (
        await db_session.execute(
            select(User).where(User.telegram_user_id == VALID_USER["id"])
        )
    ).scalar_one()
    project, room, walls = await _wall_room(db_session, owner.id, 2)
    source, target = walls
    unpriced = await _make_price_item(db_session, owner.id, price=None)
    service = SurfaceWorkPlanService(db_session)
    await service.set_plan(
        project.id, room.id, source.id, owner.id,
        substrate=Substrate.GYPSUM_PLASTER,
        quality_target=QualityLevel.S3,
        planned_works=_selection(unpriced.id),
    )
    resp = await async_client.post(_apply(project.id, room.id, source.id), headers=headers)
    assert resp.status_code == 200, resp.text
    target_plan = await service.get_work_plan(project.id, room.id, target.id, owner.id)
    assert [w.price_item_id for w in target_plan.planned_works] == [unpriced.id]
    assert target_plan.planned_works[0].price_item.price is None


async def test_apply_cross_owner_source_hidden(async_client: AsyncClient, db_session):
    token_a = await get_token(async_client, VALID_USER)
    await get_token(async_client, OTHER_USER)
    token_b = await get_token(async_client, OTHER_USER)
    headers_b = auth_header(token_b)
    owner_a = (
        await db_session.execute(
            select(User).where(User.telegram_user_id == VALID_USER["id"])
        )
    ).scalar_one()
    project, room, walls = await _wall_room(db_session, owner_a.id, 2)
    source = walls[0]
    item = await _make_price_item(db_session, owner_a.id)
    service = SurfaceWorkPlanService(db_session)
    await service.set_plan(
        project.id, room.id, source.id, owner_a.id,
        substrate=Substrate.GYPSUM_PLASTER,
        quality_target=QualityLevel.S3,
        planned_works=_selection(item.id),
    )
    # Owner B cannot apply Owner A's source wall (project is hidden).
    resp = await async_client.post(
        _apply(project.id, room.id, source.id), headers=headers_b
    )
    assert resp.status_code == 404


async def test_apply_does_not_touch_price_item_prices(
    async_client: AsyncClient, db_session
):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    owner = (
        await db_session.execute(
            select(User).where(User.telegram_user_id == VALID_USER["id"])
        )
    ).scalar_one()
    project, room, walls = await _wall_room(db_session, owner.id, 3)
    source = walls[0]
    item_a = await _make_price_item(db_session, owner.id, code="A", price="9.99")
    item_b = await _make_price_item(db_session, owner.id, code="B", price=None)
    service = SurfaceWorkPlanService(db_session)
    await service.set_plan(
        project.id, room.id, source.id, owner.id,
        substrate=Substrate.GYPSUM_PLASTER,
        quality_target=QualityLevel.S3,
        planned_works=_selection(item_a.id, item_b.id),
    )
    resp = await async_client.post(_apply(project.id, room.id, source.id), headers=headers)
    assert resp.status_code == 200
    a = (
        await db_session.execute(select(PriceItem).where(PriceItem.id == item_a.id))
    ).scalar_one()
    b = (
        await db_session.execute(select(PriceItem).where(PriceItem.id == item_b.id))
    ).scalar_one()
    assert a.price == Decimal("9.99")
    assert a.is_archived is False
    assert b.price is None


# ---------------------------------------------------------------------------
# Route family registration guard (mirrors Stage 6/8 pattern)
# ---------------------------------------------------------------------------

def test_work_plan_route_family_registered():
    from app.main import app

    paths = {p for p in app.openapi()["paths"] if "work-plan" in p}
    assert paths == {
        "/api/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}"
        "/work-plan",
        "/api/projects/{project_id}/rooms/{room_id}/surfaces/{source_surface_id}"
        "/work-plan/apply-to-room-walls",
    }
