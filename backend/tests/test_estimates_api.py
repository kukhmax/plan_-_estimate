"""Stage 10E focused API tests: Estimate HTTP + Opening Reveal Work HTTP.

Covers all required scenarios from the Stage 10E spec:
- list/get estimates
- generate DRAFT
- regeneration preview (no mutation)
- regeneration confirm
- manual line create (LABOR / MATERIAL / LABOR_AND_MATERIAL rejection / NULL price)
- quantity override / price override
- NULL price finalize blocked; 0.00 finalize accepted
- delete manual line / generated line rejection
- reveal works GET / PUT / DELETE
- reveal_enabled guard / non-REVEAL rejection / archived item restriction
- cross-owner isolation for estimates and openings
- Decimal serialization (no float)
"""
from decimal import Decimal
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.domain.services.estimate_service import EstimateService
from app.domain.services.work_plan_service import SurfaceWorkPlanService
from app.models.checklist import QualityLevel, Substrate
from app.models.estimate import Estimate, EstimateStatus, LineOrigin
from app.models.opening import Opening, OpeningType
from app.models.price_item import PriceCategory, PriceItem, PriceScope, PriceUnit
from app.models.project import Project
from app.models.room import Room
from app.models.surface import Surface, SurfaceType
from app.models.user import User
from app.schemas.work_plan import OrderedPriceItemSelection
from tests.conftest import make_telegram_init_data

VALID_USER = {"id": 333333333, "username": "owner", "first_name": "Owner", "language_code": "pl"}
OTHER_USER = {"id": 444444444, "username": "other", "first_name": "Other", "language_code": "pl"}


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

async def get_token(client: AsyncClient, user_dict: dict) -> str:
    resp = await client.post(
        "/api/auth/telegram",
        json={"init_data": make_telegram_init_data(user_dict)},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

async def _make_user(db, telegram_id: int) -> User:
    user = User(telegram_user_id=telegram_id, username=f"u{telegram_id}")
    db.add(user)
    await db.commit()
    return user


async def _make_project(db, owner_id: uuid.UUID) -> Project:
    p = Project(
        owner_id=owner_id,
        name="Test project",
        address="ul. Testowa 1",
        city="Kraków",
        postal_code="30-001",
    )
    db.add(p)
    await db.commit()
    return p


async def _make_room(
    db,
    project_id: uuid.UUID,
    *,
    name: str = "Salon",
    length: str | None = None,
    width: str | None = None,
) -> Room:
    r = Room(
        project_id=project_id,
        name=name,
        length=Decimal(length) if length is not None else None,
        width=Decimal(width) if width is not None else None,
    )
    db.add(r)
    await db.commit()
    return r


async def _make_plane_surface(
    db,
    room_id: uuid.UUID,
    surface_type: SurfaceType,
    *,
    name: str | None = None,
) -> Surface:
    """A canonical FLOOR/CEILING surface: no width/height (Stage 10C.1A)."""
    s = Surface(
        room_id=room_id,
        name=name or surface_type.value.title(),
        surface_type=surface_type,
        width=None,
        height=None,
    )
    db.add(s)
    await db.commit()
    return s


async def _make_surface(
    db,
    room_id: uuid.UUID,
    *,
    width: str = "4000.000",
    height: str = "2600.000",
    position: int = 0,
) -> Surface:
    s = Surface(
        room_id=room_id,
        name="Ściana",
        surface_type=SurfaceType.WALL,
        width=Decimal(width),
        height=Decimal(height),
        position=position,
    )
    db.add(s)
    await db.commit()
    return s


async def _make_opening(
    db,
    surface_id: uuid.UUID,
    *,
    reveal_enabled: bool = False,
    reveal_depth: str | None = None,
) -> Opening:
    o = Opening(
        surface_id=surface_id,
        opening_type=OpeningType.DOOR,
        name="Drzwi",
        width=Decimal("90.000"),
        height=Decimal("200.000"),
        quantity=1,
        reveal_enabled=reveal_enabled,
        reveal_depth=Decimal(reveal_depth) if reveal_depth else None,
        reveal_left=True,
        reveal_right=True,
        reveal_top=True,
        reveal_bottom=False,
    )
    db.add(o)
    await db.commit()
    return o


async def _make_price_item(
    db,
    owner_id: uuid.UUID,
    *,
    unit: PriceUnit = PriceUnit.M2,
    price: str | None = "25.00",
    category: PriceCategory = PriceCategory.PAINTING,
    scope: PriceScope = PriceScope.LABOR,
    is_archived: bool = False,
) -> PriceItem:
    item = PriceItem(
        owner_id=owner_id,
        code=f"ITEM_{uuid.uuid4().hex[:8].upper()}",
        category=category,
        unit=unit,
        price=Decimal(price) if price is not None else None,
        price_scope=scope,
        is_archived=is_archived,
    )
    db.add(item)
    await db.commit()
    return item


async def _make_reveal_item(
    db,
    owner_id: uuid.UUID,
    *,
    unit: PriceUnit = PriceUnit.LM,
    price: str | None = "15.00",
    is_archived: bool = False,
) -> PriceItem:
    return await _make_price_item(
        db,
        owner_id,
        unit=unit,
        price=price,
        category=PriceCategory.REVEAL,
        is_archived=is_archived,
    )


async def _make_work_plan(db, project_id, room_id, surface_id, owner_id, items):
    svc = SurfaceWorkPlanService(db)
    await svc.set_plan(
        project_id, room_id, surface_id, owner_id,
        substrate=Substrate.GYPSUM_PLASTER,
        planned_works=[OrderedPriceItemSelection(price_item_id=i.id) for i in items],
    )


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------

def _est(project_id) -> str:
    return f"/api/projects/{project_id}/estimates"


def _est_id(project_id, estimate_id) -> str:
    return f"/api/projects/{project_id}/estimates/{estimate_id}"


def _lines(project_id, estimate_id) -> str:
    return f"{_est_id(project_id, estimate_id)}/lines"


def _line(project_id, estimate_id, line_id) -> str:
    return f"{_lines(project_id, estimate_id)}/{line_id}"


def _reveal(project_id, room_id, surface_id, opening_id) -> str:
    return (
        f"/api/projects/{project_id}/rooms/{room_id}"
        f"/surfaces/{surface_id}/openings/{opening_id}/reveal-works"
    )


# ===========================================================================
# A. List estimates
# ===========================================================================

async def test_list_estimates_empty(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)

    resp = await async_client.get(_est(project.id), headers=auth(token))
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"items": [], "total": 0}


async def test_list_estimates_returns_drafts(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    svc = EstimateService(db_session)
    await svc.generate_estimate(project.id, owner.id)

    resp = await async_client.get(_est(project.id), headers=auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["status"] == "DRAFT"
    assert data["items"][0]["version"] == 1


# ===========================================================================
# B. Get one estimate
# ===========================================================================

async def test_get_estimate_not_found(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    fake_id = uuid.uuid4()

    resp = await async_client.get(_est_id(project.id, fake_id), headers=auth(token))
    assert resp.status_code == 404


async def test_get_estimate_with_lines(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    surface = await _make_surface(db_session, room.id)
    item = await _make_price_item(db_session, owner.id)
    await _make_work_plan(db_session, project.id, room.id, surface.id, owner.id, [item])
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)

    resp = await async_client.get(_est_id(project.id, estimate.id), headers=auth(token))
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "DRAFT"
    assert len(data["lines"]) == 1
    line = data["lines"][0]
    assert line["origin"] == "PLANNED_WORK"
    assert line["quantity_source"] == "SURFACE_NET_AREA"
    assert line["position"] == 0
    # Provenance fields exposed
    assert line["surface_id"] == str(surface.id)
    assert line["price_item_id"] == str(item.id)


# ===========================================================================
# C. Generate estimates
# ===========================================================================

async def test_generate_creates_draft(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)

    resp = await async_client.post(
        f"{_est(project.id)}/generate", headers=auth(token)
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "DRAFT"
    assert data["version"] == 1
    assert data["lines"] == []


async def test_generate_from_surface_work_plan(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    surface = await _make_surface(db_session, room.id, width="4000.000", height="2600.000")
    item = await _make_price_item(db_session, owner.id, unit=PriceUnit.M2, price="20.00")
    await _make_work_plan(db_session, project.id, room.id, surface.id, owner.id, [item])

    resp = await async_client.post(
        f"{_est(project.id)}/generate", headers=auth(token)
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data["lines"]) == 1
    line = data["lines"][0]
    assert line["unit_price"] == "20.00"
    assert line["quantity_source"] == "SURFACE_NET_AREA"
    # Total must be a string representation of Decimal, not float
    assert "." in data["total"]
    assert isinstance(data["total"], str)


async def test_generate_ownership_isolation(async_client: AsyncClient, db_session):
    token_b = await get_token(async_client, OTHER_USER)
    owner_a = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one_or_none()
    if owner_a is None:
        owner_a = User(telegram_user_id=VALID_USER["id"], username="owner_a")
        db_session.add(owner_a)
        await db_session.commit()
    project = await _make_project(db_session, owner_a.id)

    resp = await async_client.post(
        f"{_est(project.id)}/generate", headers=auth(token_b)
    )
    assert resp.status_code == 404


# ===========================================================================
# D. Regeneration preview — must NOT mutate
# ===========================================================================

async def test_regeneration_preview_no_mutation(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    surface = await _make_surface(db_session, room.id)
    item = await _make_price_item(db_session, owner.id)
    await _make_work_plan(db_session, project.id, room.id, surface.id, owner.id, [item])
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)
    original_line_id = estimate.lines[0].id

    resp = await async_client.post(
        f"{_est_id(project.id, estimate.id)}/regenerate-preview",
        headers=auth(token),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "added" in data
    assert "removed" in data
    assert "updated" in data
    assert "preserved_manual" in data

    # Verify the estimate was NOT mutated
    refreshed = (await db_session.execute(
        select(Estimate).where(Estimate.id == estimate.id)
    )).scalar_one()
    from sqlalchemy.orm import selectinload
    from sqlalchemy import select as sel
    from app.models.estimate import Estimate as Est, EstimateLine
    lines = (await db_session.execute(
        sel(EstimateLine).where(EstimateLine.estimate_id == estimate.id)
    )).scalars().all()
    assert len(lines) == 1
    assert lines[0].id == original_line_id


async def test_regeneration_preview_returns_counts(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    surface = await _make_surface(db_session, room.id)
    item = await _make_price_item(db_session, owner.id)
    await _make_work_plan(db_session, project.id, room.id, surface.id, owner.id, [item])
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)

    resp = await async_client.post(
        f"{_est_id(project.id, estimate.id)}/regenerate-preview",
        headers=auth(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    # Existing estimate has 1 planned work; same unchanged work plan →
    # no snapshot fields changed → 0 truly updated, 0 added, 0 removed.
    assert data["updated"] == 0
    assert data["added"] == 0
    assert data["removed"] == 0
    assert data["preserved_manual"] == 0
    assert data["changes"] == []


async def test_regeneration_preview_rejected_for_final(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    surface = await _make_surface(db_session, room.id)
    item = await _make_price_item(db_session, owner.id, price="10.00")
    await _make_work_plan(db_session, project.id, room.id, surface.id, owner.id, [item])
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)
    await svc.finalize(estimate.id, owner.id)

    resp = await async_client.post(
        f"{_est_id(project.id, estimate.id)}/regenerate-preview",
        headers=auth(token),
    )
    assert resp.status_code == 422


# ===========================================================================
# E. Regeneration confirm
# ===========================================================================

async def test_regeneration_confirm_mutates_draft(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    surface = await _make_surface(db_session, room.id)
    item_a = await _make_price_item(db_session, owner.id, price="10.00")
    item_b = await _make_price_item(db_session, owner.id, price="20.00")
    await _make_work_plan(db_session, project.id, room.id, surface.id, owner.id, [item_a])
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)
    assert len(estimate.lines) == 1

    # Replace work plan with two items, then confirm regeneration
    await _make_work_plan(db_session, project.id, room.id, surface.id, owner.id, [item_a, item_b])
    resp = await async_client.post(
        f"{_est_id(project.id, estimate.id)}/regenerate",
        headers=auth(token),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # set_plan replaces all SurfacePlannedWork rows with fresh IDs, so both
    # new rows are "added" and the stale old line is "removed".
    assert data["added"] == 2
    assert data["removed"] == 1
    assert data["updated"] == 0

    # Verify lines were actually updated (2 planned work lines now)
    get_resp = await async_client.get(
        _est_id(project.id, estimate.id), headers=auth(token)
    )
    assert get_resp.status_code == 200
    assert len(get_resp.json()["lines"]) == 2


async def test_regeneration_rejected_for_final(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    surface = await _make_surface(db_session, room.id)
    item = await _make_price_item(db_session, owner.id, price="10.00")
    await _make_work_plan(db_session, project.id, room.id, surface.id, owner.id, [item])
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)
    await svc.finalize(estimate.id, owner.id)

    resp = await async_client.post(
        f"{_est_id(project.id, estimate.id)}/regenerate",
        headers=auth(token),
    )
    assert resp.status_code == 422


# ===========================================================================
# D/E provenance follow-up — Stage 10G.3B: human-readable room/surface/opening
# context on regeneration preview and confirm diff entries.
# ===========================================================================

async def test_regeneration_preview_added_includes_room_and_surface_provenance(
    async_client: AsyncClient, db_session
):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id, name="Kuchnia")
    surface = await _make_surface(db_session, room.id)
    item = await _make_price_item(db_session, owner.id)
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)  # empty — no work plan yet

    await _make_work_plan(db_session, project.id, room.id, surface.id, owner.id, [item])

    resp = await async_client.post(
        f"{_est_id(project.id, estimate.id)}/regenerate-preview", headers=auth(token)
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["added"] == 1
    change = data["changes"][0]
    assert change["change_type"] == "ADDED"
    assert change["room_name"] == "Kuchnia"
    assert change["surface_name"] == "Ściana"
    assert change["surface_type_value"] == "WALL"
    assert change["opening_name"] is None
    assert change["opening_type_value"] is None


async def test_regeneration_preview_updated_includes_room_and_surface_provenance(
    async_client: AsyncClient, db_session
):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id, name="Łazienka")
    surface = await _make_surface(db_session, room.id)
    item = await _make_price_item(db_session, owner.id, unit=PriceUnit.M2, price="10.00")
    await _make_work_plan(db_session, project.id, room.id, surface.id, owner.id, [item])
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)

    # Geometry change → regeneration recomputes source_quantity → UPDATED.
    surface.width = Decimal("5000.000")
    await db_session.commit()

    resp = await async_client.post(
        f"{_est_id(project.id, estimate.id)}/regenerate-preview", headers=auth(token)
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["updated"] == 1
    change = data["changes"][0]
    assert change["change_type"] == "UPDATED"
    assert change["room_name"] == "Łazienka"
    assert change["surface_name"] == "Ściana"


async def test_regeneration_preview_removed_includes_resolvable_room_and_surface(
    async_client: AsyncClient, db_session
):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id, name="Pokój gościnny")
    surface = await _make_surface(db_session, room.id)
    item_a = await _make_price_item(db_session, owner.id, price="10.00")
    item_b = await _make_price_item(db_session, owner.id, price="20.00")
    await _make_work_plan(db_session, project.id, room.id, surface.id, owner.id, [item_a])
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)

    # Replace the work plan: item_a's line becomes REMOVED while the Surface
    # and Room it belonged to remain intact and resolvable.
    await _make_work_plan(db_session, project.id, room.id, surface.id, owner.id, [item_b])

    resp = await async_client.post(
        f"{_est_id(project.id, estimate.id)}/regenerate-preview", headers=auth(token)
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    removed = [c for c in data["changes"] if c["change_type"] == "REMOVED"]
    assert len(removed) == 1
    assert removed[0]["room_name"] == "Pokój gościnny"
    assert removed[0]["surface_name"] == "Ściana"


async def test_regeneration_preview_reveal_includes_opening_provenance(
    async_client: AsyncClient, db_session
):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id, name="Łazienka")
    surface = await _make_surface(db_session, room.id)
    item = await _make_reveal_item(db_session, owner.id)
    opening = await _make_opening(db_session, surface.id, reveal_enabled=True, reveal_depth="120.000")
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)  # empty — no reveal work yet

    from app.models.opening_reveal_planned_work import OpeningRevealPlannedWork
    reveal_work = OpeningRevealPlannedWork(opening_id=opening.id, price_item_id=item.id, position=0)
    db_session.add(reveal_work)
    await db_session.commit()

    resp = await async_client.post(
        f"{_est_id(project.id, estimate.id)}/regenerate-preview", headers=auth(token)
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    added = [c for c in data["changes"] if c["change_type"] == "ADDED"]
    assert len(added) == 1
    change = added[0]
    assert change["room_name"] == "Łazienka"
    assert change["surface_name"] == "Ściana"
    assert change["opening_name"] == "Drzwi"
    assert change["opening_type_value"] == "DOOR"


async def test_regeneration_confirm_response_also_includes_provenance(
    async_client: AsyncClient, db_session
):
    """The mutating /regenerate endpoint shares the same enrichment as preview."""
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id, name="Sypialnia")
    surface = await _make_surface(db_session, room.id)
    item = await _make_price_item(db_session, owner.id)
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)  # empty

    await _make_work_plan(db_session, project.id, room.id, surface.id, owner.id, [item])

    resp = await async_client.post(
        f"{_est_id(project.id, estimate.id)}/regenerate", headers=auth(token)
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["added"] == 1
    assert data["changes"][0]["room_name"] == "Sypialnia"
    assert data["changes"][0]["surface_name"] == "Ściana"


async def test_regeneration_preview_existing_fields_not_regressed_by_provenance(
    async_client: AsyncClient, db_session
):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    surface = await _make_surface(db_session, room.id)
    item = await _make_price_item(db_session, owner.id)
    await _make_work_plan(db_session, project.id, room.id, surface.id, owner.id, [item])
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)
    surface.width = Decimal("9000.000")
    await db_session.commit()

    resp = await async_client.post(
        f"{_est_id(project.id, estimate.id)}/regenerate-preview", headers=auth(token)
    )
    assert resp.status_code == 200, resp.text
    change = resp.json()["changes"][0]
    for key in (
        "change_type", "estimate_line_id", "planned_work_id", "surface_id", "opening_id",
        "item_code", "description", "unit", "old_source_quantity", "new_source_quantity",
        "old_unit_price", "new_unit_price", "quantity_overridden", "price_override",
        "room_name", "surface_name", "surface_type_value", "opening_name", "opening_type_value",
    ):
        assert key in change, f"missing field: {key}"


async def test_regeneration_preview_multi_room_added_shows_new_room_provenance(
    async_client: AsyncClient, db_session
):
    """Primary owner acceptance scenario: adding a new room (Kuchnia) to a
    project that already has a generated Estimate for another room (pokój 1)
    must report the new room's work as ADDED with its own room/surface
    provenance, without mutating the existing Estimate.
    """
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room_a = await _make_room(db_session, project.id, name="pokój 1")
    surface_a = await _make_surface(db_session, room_a.id)
    item = await _make_price_item(db_session, owner.id, price="35.00")
    await _make_work_plan(db_session, project.id, room_a.id, surface_a.id, owner.id, [item])
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)
    assert len(estimate.lines) == 1

    # Owner creates a new room later, with its own planned work.
    room_b = await _make_room(db_session, project.id, name="kuchnia")
    surface_b = await _make_surface(db_session, room_b.id)
    await _make_work_plan(db_session, project.id, room_b.id, surface_b.id, owner.id, [item])

    resp = await async_client.post(
        f"{_est_id(project.id, estimate.id)}/regenerate-preview", headers=auth(token)
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["added"] == 1
    assert data["changes"][0]["room_name"] == "kuchnia"
    assert data["changes"][0]["surface_name"] == "Ściana"

    # Preview must not have mutated the estimate.
    get_resp = await async_client.get(_est_id(project.id, estimate.id), headers=auth(token))
    assert len(get_resp.json()["lines"]) == 1

    # Explicit confirmation merges both rooms into the same Estimate.
    confirm_resp = await async_client.post(
        f"{_est_id(project.id, estimate.id)}/regenerate", headers=auth(token)
    )
    assert confirm_resp.status_code == 200, confirm_resp.text
    get_resp = await async_client.get(_est_id(project.id, estimate.id), headers=auth(token))
    lines = get_resp.json()["lines"]
    assert len(lines) == 2
    assert {ln["room_name"] for ln in lines} == {"pokój 1", "kuchnia"}


# ===========================================================================
# FLOOR/CEILING quantity-source correction (Stage 10G.3B owner-found bug):
# canonical plane surfaces (Stage 10C.1A) have no width/height, so the
# Estimate must source their M2 quantity from the same Room-length x
# Room-width + AreaSegment adjustment calculation the Surface UI already
# displays as "Razem" — never 0.000, and never door/window openings (WALL
# only).
# ===========================================================================

async def test_wall_m2_uses_net_area_unchanged(async_client: AsyncClient, db_session):
    """A. WALL M2 — existing net-area behavior (gross - opening deduction)."""
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    surface = await _make_surface(db_session, room.id, width="4.000", height="2.600")
    item = await _make_price_item(db_session, owner.id, unit=PriceUnit.M2, price="30.00")
    await _make_work_plan(db_session, project.id, room.id, surface.id, owner.id, [item])
    svc = EstimateService(db_session)

    estimate = await svc.generate_estimate(project.id, owner.id)
    assert len(estimate.lines) == 1
    line = estimate.lines[0]
    assert line.source_quantity == Decimal("10.400")  # 4.000m x 2.600m, no openings
    assert line.quantity == Decimal("10.400")


async def test_floor_m2_uses_room_plane_area_not_zero(async_client: AsyncClient, db_session):
    """B. FLOOR M2 — must use the authoritative Room-plane area, not 0.000."""
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id, name="Kuchnia", length="9.400", width="4.000")
    floor = await _make_plane_surface(db_session, room.id, SurfaceType.FLOOR)
    item = await _make_price_item(db_session, owner.id, unit=PriceUnit.M2, price="30.00")
    await _make_work_plan(db_session, project.id, room.id, floor.id, owner.id, [item])
    svc = EstimateService(db_session)

    estimate = await svc.generate_estimate(project.id, owner.id)
    assert len(estimate.lines) == 1
    line = estimate.lines[0]
    assert line.source_quantity == Decimal("37.600")
    assert line.quantity == Decimal("37.600")


async def test_ceiling_m2_uses_room_plane_area_not_zero(async_client: AsyncClient, db_session):
    """C. CEILING M2 — must use the authoritative Room-plane area, not 0.000
    (the owner's exact real-world scenario: 9.400m x 4.000m = 37.600 m²)."""
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id, name="kuchnia", length="9.400", width="4.000")
    ceiling = await _make_plane_surface(db_session, room.id, SurfaceType.CEILING, name="Sufit")
    item = await _make_price_item(db_session, owner.id, unit=PriceUnit.M2, price="30.00")
    await _make_work_plan(db_session, project.id, room.id, ceiling.id, owner.id, [item])
    svc = EstimateService(db_session)

    estimate = await svc.generate_estimate(project.id, owner.id)
    assert len(estimate.lines) == 1
    line = estimate.lines[0]
    assert line.source_quantity == Decimal("37.600")
    assert line.quantity == Decimal("37.600")


async def test_ceiling_m2_null_price_has_nonzero_quantity_and_null_amount(
    async_client: AsyncClient, db_session
):
    """D. CEILING M2 + NULL price ("Do ustalenia") — quantity must still be
    37.600, unit_price NULL, amount NULL. Quantity and price resolution are
    independent."""
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id, name="kuchnia", length="9.400", width="4.000")
    ceiling = await _make_plane_surface(db_session, room.id, SurfaceType.CEILING, name="Sufit")
    item = await _make_price_item(db_session, owner.id, unit=PriceUnit.M2, price=None)
    await _make_work_plan(db_session, project.id, room.id, ceiling.id, owner.id, [item])
    svc = EstimateService(db_session)

    estimate = await svc.generate_estimate(project.id, owner.id)
    line = estimate.lines[0]
    assert line.source_quantity == Decimal("37.600")
    assert line.quantity == Decimal("37.600")
    assert line.unit_price is None
    assert line.amount is None


async def test_ceiling_m2_priced_amount_resolved_normally(
    async_client: AsyncClient, db_session
):
    """E. CEILING M2 + 30.00 PLN price — correct quantity and amount."""
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id, name="kuchnia", length="9.400", width="4.000")
    ceiling = await _make_plane_surface(db_session, room.id, SurfaceType.CEILING, name="Sufit")
    item = await _make_price_item(db_session, owner.id, unit=PriceUnit.M2, price="30.00")
    await _make_work_plan(db_session, project.id, room.id, ceiling.id, owner.id, [item])
    svc = EstimateService(db_session)

    estimate = await svc.generate_estimate(project.id, owner.id)
    line = estimate.lines[0]
    assert line.quantity == Decimal("37.600")
    assert line.unit_price == Decimal("30.00")
    assert line.amount == Decimal("37.600") * Decimal("30.00")


async def test_floor_ceiling_ignore_wall_opening_deductions(
    async_client: AsyncClient, db_session
):
    """F. A door/window on a WALL surface in the same room must never affect
    FLOOR/CEILING quantity — opening deductions are WALL-only."""
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id, name="kuchnia", length="9.400", width="4.000")
    wall = await _make_surface(db_session, room.id, width="4.000", height="2.600")
    await _make_opening(db_session, wall.id)  # 90cm x 200cm door
    ceiling = await _make_plane_surface(db_session, room.id, SurfaceType.CEILING, name="Sufit")
    item = await _make_price_item(db_session, owner.id, unit=PriceUnit.M2, price="30.00")
    await _make_work_plan(db_session, project.id, room.id, ceiling.id, owner.id, [item])
    svc = EstimateService(db_session)

    estimate = await svc.generate_estimate(project.id, owner.id)
    ceiling_line = next(ln for ln in estimate.lines if ln.surface_id == ceiling.id)
    assert ceiling_line.source_quantity == Decimal("37.600")  # unaffected by the door


async def test_regeneration_preview_reports_correct_ceiling_quantity(
    async_client: AsyncClient, db_session
):
    """G. regenerate-preview must report the correct new_source_quantity for
    a newly-added CEILING M2 work — not 0.000."""
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room_a = await _make_room(db_session, project.id, name="pokój 1")
    surface_a = await _make_surface(db_session, room_a.id)
    item_a = await _make_price_item(db_session, owner.id, price="10.00")
    await _make_work_plan(db_session, project.id, room_a.id, surface_a.id, owner.id, [item_a])
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)

    room_b = await _make_room(db_session, project.id, name="kuchnia", length="9.400", width="4.000")
    ceiling = await _make_plane_surface(db_session, room_b.id, SurfaceType.CEILING, name="Sufit")
    item_b = await _make_price_item(db_session, owner.id, unit=PriceUnit.M2, price="30.00")
    await _make_work_plan(db_session, project.id, room_b.id, ceiling.id, owner.id, [item_b])

    resp = await async_client.post(
        f"{_est_id(project.id, estimate.id)}/regenerate-preview", headers=auth(token)
    )
    assert resp.status_code == 200, resp.text
    added = [c for c in resp.json()["changes"] if c["change_type"] == "ADDED"]
    assert len(added) == 1
    assert added[0]["new_source_quantity"] == "37.600"
    assert added[0]["room_name"] == "kuchnia"
    assert added[0]["surface_name"] == "Sufit"


async def test_regeneration_confirm_applies_correct_ceiling_quantity(
    async_client: AsyncClient, db_session
):
    """H. Confirmed regeneration must persist the correct CEILING quantity."""
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id, name="kuchnia", length="9.400", width="4.000")
    ceiling = await _make_plane_surface(db_session, room.id, SurfaceType.CEILING, name="Sufit")
    item = await _make_price_item(db_session, owner.id, unit=PriceUnit.M2, price="30.00")
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)  # empty — no work yet
    assert estimate.lines == []

    await _make_work_plan(db_session, project.id, room.id, ceiling.id, owner.id, [item])

    resp = await async_client.post(
        f"{_est_id(project.id, estimate.id)}/regenerate", headers=auth(token)
    )
    assert resp.status_code == 200, resp.text

    get_resp = await async_client.get(_est_id(project.id, estimate.id), headers=auth(token))
    lines = get_resp.json()["lines"]
    assert len(lines) == 1
    assert lines[0]["quantity"] == "37.600"
    assert lines[0]["amount"] == "1128.00"


async def test_ceiling_quantity_override_preserved_while_source_updates(
    async_client: AsyncClient, db_session
):
    """I. Owner quantity override survives regeneration on a CEILING line;
    source_quantity still reflects the new authoritative area."""
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id, name="kuchnia", length="9.400", width="4.000")
    ceiling = await _make_plane_surface(db_session, room.id, SurfaceType.CEILING, name="Sufit")
    item = await _make_price_item(db_session, owner.id, unit=PriceUnit.M2, price="30.00")
    await _make_work_plan(db_session, project.id, room.id, ceiling.id, owner.id, [item])
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)
    line = estimate.lines[0]
    assert line.source_quantity == Decimal("37.600")

    line.quantity = Decimal("40.000")
    line.quantity_overridden = True
    await db_session.commit()

    # Room geometry changes (owner corrects a dimension).
    room.length = Decimal("10.000")
    await db_session.commit()

    resp = await async_client.post(
        f"{_est_id(project.id, estimate.id)}/regenerate", headers=auth(token)
    )
    assert resp.status_code == 200, resp.text

    get_resp = await async_client.get(_est_id(project.id, estimate.id), headers=auth(token))
    refreshed = get_resp.json()["lines"][0]
    assert refreshed["quantity_overridden"] is True
    assert refreshed["quantity"] == "40.000"  # owner override preserved
    assert refreshed["source_quantity"] == "40.000"  # new authoritative area (10.000 x 4.000)


async def test_estimate_total_includes_priced_ceiling_and_floor_work(
    async_client: AsyncClient, db_session
):
    """J. Estimate.total naturally includes correctly-quantified,
    correctly-priced FLOOR and CEILING lines — no frontend arithmetic."""
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id, name="kuchnia", length="9.400", width="4.000")
    floor = await _make_plane_surface(db_session, room.id, SurfaceType.FLOOR, name="Podłoga")
    ceiling = await _make_plane_surface(db_session, room.id, SurfaceType.CEILING, name="Sufit")
    floor_item = await _make_price_item(db_session, owner.id, unit=PriceUnit.M2, price="50.00")
    ceiling_item = await _make_price_item(db_session, owner.id, unit=PriceUnit.M2, price="30.00")
    await _make_work_plan(db_session, project.id, room.id, floor.id, owner.id, [floor_item])
    await _make_work_plan(db_session, project.id, room.id, ceiling.id, owner.id, [ceiling_item])
    svc = EstimateService(db_session)

    estimate = await svc.generate_estimate(project.id, owner.id)
    expected_total = (Decimal("37.600") * Decimal("50.00")) + (Decimal("37.600") * Decimal("30.00"))
    assert estimate.total == expected_total


# ===========================================================================
# F. Add manual line
# ===========================================================================

async def _generate_empty_draft(db_session, owner):
    project = await _make_project(db_session, owner.id)
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)
    return project, estimate


async def test_manual_line_create_labor(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project, estimate = await _generate_empty_draft(db_session, owner)

    resp = await async_client.post(
        _lines(project.id, estimate.id),
        headers=auth(token),
        json={
            "description": "Praca ręczna",
            "scope": "LABOR",
            "unit": "HOUR",
            "quantity": "8.000",
            "unit_price": "50.00",
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["origin"] == "MANUAL"
    assert data["scope"] == "LABOR"
    assert data["unit"] == "HOUR"
    assert data["quantity"] == "8.000"
    assert data["unit_price"] == "50.00"
    assert data["amount"] == "400.00"


async def test_manual_line_create_material(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project, estimate = await _generate_empty_draft(db_session, owner)

    resp = await async_client.post(
        _lines(project.id, estimate.id),
        headers=auth(token),
        json={
            "description": "Farba",
            "scope": "MATERIAL",
            "unit": "PCS",
            "quantity": "3.000",
            "unit_price": "45.00",
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["scope"] == "MATERIAL"


async def test_manual_line_labor_and_material_rejected(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project, estimate = await _generate_empty_draft(db_session, owner)

    resp = await async_client.post(
        _lines(project.id, estimate.id),
        headers=auth(token),
        json={
            "description": "Invalid",
            "scope": "LABOR_AND_MATERIAL",
            "unit": "M2",
            "quantity": "10.000",
        },
    )
    assert resp.status_code == 422


async def test_manual_line_null_price(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project, estimate = await _generate_empty_draft(db_session, owner)

    resp = await async_client.post(
        _lines(project.id, estimate.id),
        headers=auth(token),
        json={
            "description": "Do ustalenia",
            "scope": "LABOR",
            "unit": "FLAT",
            "quantity": "1.000",
            "unit_price": None,
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["unit_price"] is None
    assert data["amount"] is None


# ===========================================================================
# G. Update editable draft line
# ===========================================================================

async def _draft_with_work_plan_line(db_session, owner):
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    surface = await _make_surface(db_session, room.id)
    item = await _make_price_item(db_session, owner.id, unit=PriceUnit.M2, price="20.00")
    await _make_work_plan(db_session, project.id, room.id, surface.id, owner.id, [item])
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)
    return project, estimate, estimate.lines[0]


async def test_quantity_override(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project, estimate, line = await _draft_with_work_plan_line(db_session, owner)

    resp = await async_client.patch(
        _line(project.id, estimate.id, line.id),
        headers=auth(token),
        json={"quantity": "99.000"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["quantity"] == "99.000"
    assert data["quantity_overridden"] is True
    # amount = 99 × 20.00
    assert data["amount"] == "1980.00"


async def test_price_override(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project, estimate, line = await _draft_with_work_plan_line(db_session, owner)

    resp = await async_client.patch(
        _line(project.id, estimate.id, line.id),
        headers=auth(token),
        json={"unit_price": "30.00"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["unit_price"] == "30.00"
    assert data["price_override"] is True


async def test_price_override_to_null(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project, estimate, line = await _draft_with_work_plan_line(db_session, owner)

    resp = await async_client.patch(
        _line(project.id, estimate.id, line.id),
        headers=auth(token),
        json={"unit_price": None},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["unit_price"] is None
    assert data["price_override"] is True
    assert data["amount"] is None


async def test_description_editable_on_manual_line(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project, estimate = await _generate_empty_draft(db_session, owner)
    line_resp = await async_client.post(
        _lines(project.id, estimate.id),
        headers=auth(token),
        json={"description": "Original", "scope": "LABOR", "unit": "HOUR", "quantity": "1.000"},
    )
    assert line_resp.status_code == 201
    line_id = line_resp.json()["id"]

    resp = await async_client.patch(
        _line(project.id, estimate.id, line_id),
        headers=auth(token),
        json={"description": "Updated description"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["description"] == "Updated description"


async def test_description_not_editable_on_planned_line(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project, estimate, line = await _draft_with_work_plan_line(db_session, owner)

    resp = await async_client.patch(
        _line(project.id, estimate.id, line.id),
        headers=auth(token),
        json={"description": "Trying to override"},
    )
    assert resp.status_code == 422


# ===========================================================================
# I. Finalize
# ===========================================================================

async def test_null_price_finalize_rejected(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    surface = await _make_surface(db_session, room.id)
    item = await _make_price_item(db_session, owner.id, price=None)
    await _make_work_plan(db_session, project.id, room.id, surface.id, owner.id, [item])
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)

    resp = await async_client.post(
        f"{_est_id(project.id, estimate.id)}/finalize",
        headers=auth(token),
    )
    assert resp.status_code == 422


async def test_zero_price_finalize_accepted(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    surface = await _make_surface(db_session, room.id)
    item = await _make_price_item(db_session, owner.id, price="0.00")
    await _make_work_plan(db_session, project.id, room.id, surface.id, owner.id, [item])
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)

    resp = await async_client.post(
        f"{_est_id(project.id, estimate.id)}/finalize",
        headers=auth(token),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "FINAL"


# ===========================================================================
# H. Delete manual line
# ===========================================================================

async def test_delete_manual_line(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project, estimate = await _generate_empty_draft(db_session, owner)
    line_resp = await async_client.post(
        _lines(project.id, estimate.id),
        headers=auth(token),
        json={"description": "To delete", "scope": "LABOR", "unit": "HOUR", "quantity": "1.000"},
    )
    assert line_resp.status_code == 201
    line_id = line_resp.json()["id"]

    del_resp = await async_client.delete(
        _line(project.id, estimate.id, line_id), headers=auth(token)
    )
    assert del_resp.status_code == 204

    # Verify line is gone
    get_resp = await async_client.get(_est_id(project.id, estimate.id), headers=auth(token))
    assert get_resp.status_code == 200
    ids = [ln["id"] for ln in get_resp.json()["lines"]]
    assert line_id not in ids


async def test_delete_generated_line_rejected(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project, estimate, line = await _draft_with_work_plan_line(db_session, owner)

    resp = await async_client.delete(
        _line(project.id, estimate.id, line.id), headers=auth(token)
    )
    assert resp.status_code == 422


# ===========================================================================
# Cross-owner isolation for estimates
# ===========================================================================

async def test_cross_owner_estimate_isolation(async_client: AsyncClient, db_session):
    token_b = await get_token(async_client, OTHER_USER)
    # Ensure owner_a exists
    owner_a = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one_or_none()
    if owner_a is None:
        owner_a = User(telegram_user_id=VALID_USER["id"], username="owner_a_cross")
        db_session.add(owner_a)
        await db_session.commit()
    project = await _make_project(db_session, owner_a.id)
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner_a.id)

    # Owner B cannot see or operate on Owner A's estimate
    resp = await async_client.get(_est_id(project.id, estimate.id), headers=auth(token_b))
    assert resp.status_code == 404

    resp = await async_client.post(
        f"{_est_id(project.id, estimate.id)}/finalize", headers=auth(token_b)
    )
    assert resp.status_code == 404


# ===========================================================================
# Decimal serialization — no float
# ===========================================================================

async def test_decimal_serialization(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    surface = await _make_surface(db_session, room.id, width="3333.333", height="2700.000")
    item = await _make_price_item(db_session, owner.id, price="13.37")
    await _make_work_plan(db_session, project.id, room.id, surface.id, owner.id, [item])
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)

    resp = await async_client.get(_est_id(project.id, estimate.id), headers=auth(token))
    assert resp.status_code == 200
    data = resp.json()
    line = data["lines"][0]
    # Verify JSON serialized as string, not float
    assert isinstance(line["unit_price"], str)
    assert isinstance(line["quantity"], str)
    assert isinstance(line["amount"], str)
    assert isinstance(data["total"], str)
    # No float imprecision: 13.37 stays exactly "13.37"
    assert line["unit_price"] == "13.37"


# ===========================================================================
# No market-price fallback
# ===========================================================================

async def test_no_market_price_fallback(async_client: AsyncClient, db_session):
    """NULL price_item.price → unit_price=NULL, amount=NULL (no fallback to market)."""
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    surface = await _make_surface(db_session, room.id)
    item = await _make_price_item(db_session, owner.id, price=None)
    await _make_work_plan(db_session, project.id, room.id, surface.id, owner.id, [item])
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)

    resp = await async_client.get(_est_id(project.id, estimate.id), headers=auth(token))
    assert resp.status_code == 200
    line = resp.json()["lines"][0]
    assert line["unit_price"] is None
    assert line["amount"] is None
    assert resp.json()["total"] is None


# ===========================================================================
# Reveal works GET / PUT / DELETE
# ===========================================================================

async def _reveal_setup(db_session, owner):
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    surface = await _make_surface(db_session, room.id)
    opening = await _make_opening(
        db_session, surface.id, reveal_enabled=True, reveal_depth="15.000"
    )
    return project, room, surface, opening


async def test_reveal_works_get_empty(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project, room, surface, opening = await _reveal_setup(db_session, owner)

    resp = await async_client.get(
        _reveal(project.id, room.id, surface.id, opening.id), headers=auth(token)
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["opening_id"] == str(opening.id)
    assert data["items"] == []


async def test_reveal_works_ordered_set(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project, room, surface, opening = await _reveal_setup(db_session, owner)
    item_a = await _make_reveal_item(db_session, owner.id, price="10.00")
    item_b = await _make_reveal_item(db_session, owner.id, price="12.00")

    resp = await async_client.put(
        _reveal(project.id, room.id, surface.id, opening.id),
        headers=auth(token),
        json={"price_item_ids": [str(item_a.id), str(item_b.id)]},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["opening_id"] == str(opening.id)
    assert len(data["items"]) == 2
    assert [it["position"] for it in data["items"]] == [0, 1]
    assert [it["price_item_id"] for it in data["items"]] == [
        str(item_a.id), str(item_b.id)
    ]
    # Embedded price_item summary
    first = data["items"][0]
    assert first["price_item"]["id"] == str(item_a.id)
    assert first["price_item"]["price"] == "10.00"
    assert "sources" not in first["price_item"]


async def test_duplicate_reveal_work_occurrences(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project, room, surface, opening = await _reveal_setup(db_session, owner)
    item = await _make_reveal_item(db_session, owner.id)

    resp = await async_client.put(
        _reveal(project.id, room.id, surface.id, opening.id),
        headers=auth(token),
        json={"price_item_ids": [str(item.id), str(item.id)]},
    )
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 2
    assert items[0]["price_item_id"] == str(item.id)
    assert items[1]["price_item_id"] == str(item.id)
    assert items[0]["position"] == 0
    assert items[1]["position"] == 1


async def test_clear_reveal_works(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project, room, surface, opening = await _reveal_setup(db_session, owner)
    item = await _make_reveal_item(db_session, owner.id)

    await async_client.put(
        _reveal(project.id, room.id, surface.id, opening.id),
        headers=auth(token),
        json={"price_item_ids": [str(item.id)]},
    )

    del_resp = await async_client.delete(
        _reveal(project.id, room.id, surface.id, opening.id), headers=auth(token)
    )
    assert del_resp.status_code == 204

    get_resp = await async_client.get(
        _reveal(project.id, room.id, surface.id, opening.id), headers=auth(token)
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["items"] == []


async def test_reveal_disabled_guard(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project, room, surface, _ = await _reveal_setup(db_session, owner)
    # Opening with reveal_enabled=False
    disabled_opening = await _make_opening(db_session, surface.id, reveal_enabled=False)
    item = await _make_reveal_item(db_session, owner.id)

    resp = await async_client.put(
        _reveal(project.id, room.id, surface.id, disabled_opening.id),
        headers=auth(token),
        json={"price_item_ids": [str(item.id)]},
    )
    assert resp.status_code == 422


async def test_non_reveal_price_item_rejected(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project, room, surface, opening = await _reveal_setup(db_session, owner)
    non_reveal = await _make_price_item(
        db_session, owner.id, category=PriceCategory.PAINTING
    )

    resp = await async_client.put(
        _reveal(project.id, room.id, surface.id, opening.id),
        headers=auth(token),
        json={"price_item_ids": [str(non_reveal.id)]},
    )
    assert resp.status_code == 422


async def test_archived_reveal_item_rejected_on_new(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project, room, surface, opening = await _reveal_setup(db_session, owner)
    archived = await _make_reveal_item(db_session, owner.id, is_archived=True)

    resp = await async_client.put(
        _reveal(project.id, room.id, surface.id, opening.id),
        headers=auth(token),
        json={"price_item_ids": [str(archived.id)]},
    )
    assert resp.status_code == 422


async def test_cross_owner_opening_isolation(async_client: AsyncClient, db_session):
    token_b = await get_token(async_client, OTHER_USER)
    owner_a = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one_or_none()
    if owner_a is None:
        owner_a = User(telegram_user_id=VALID_USER["id"], username="owner_a_rev")
        db_session.add(owner_a)
        await db_session.commit()
    project, room, surface, opening = await _reveal_setup(db_session, owner_a)
    owner_b = (await db_session.execute(
        select(User).where(User.telegram_user_id == OTHER_USER["id"])
    )).scalar_one()
    item = await _make_reveal_item(db_session, owner_b.id)

    resp = await async_client.put(
        _reveal(project.id, room.id, surface.id, opening.id),
        headers=auth(token_b),
        json={"price_item_ids": [str(item.id)]},
    )
    assert resp.status_code == 404


# ===========================================================================
# Unauthenticated access guard
# ===========================================================================

@pytest.mark.parametrize("method,path_tmpl", [
    ("GET",    "/api/projects/{p}/estimates"),
    ("POST",   "/api/projects/{p}/estimates/generate"),
    ("GET",    "/api/projects/{p}/estimates/{e}"),
    ("POST",   "/api/projects/{p}/estimates/{e}/finalize"),
    ("POST",   "/api/projects/{p}/estimates/{e}/lines"),
    ("PATCH",  "/api/projects/{p}/estimates/{e}/lines/{l}"),
    ("DELETE", "/api/projects/{p}/estimates/{e}/lines/{l}"),
])
async def test_unauthenticated_estimates_401(
    async_client: AsyncClient, method: str, path_tmpl: str
):
    nil = "00000000-0000-0000-0000-000000000000"
    path = path_tmpl.format(p=nil, e=nil, l=nil)
    resp = await async_client.request(method, path, json={})
    assert resp.status_code == 401


# ===========================================================================
# OpenAPI route registration guard
# ===========================================================================

def test_estimate_routes_registered():
    from app.main import app
    paths = {p for p in app.openapi()["paths"]}
    expected = {
        "/api/projects/{project_id}/estimates",
        "/api/projects/{project_id}/estimates/generate",
        "/api/projects/{project_id}/estimates/{estimate_id}",
        "/api/projects/{project_id}/estimates/{estimate_id}/regenerate-preview",
        "/api/projects/{project_id}/estimates/{estimate_id}/regenerate",
        "/api/projects/{project_id}/estimates/{estimate_id}/lines",
        "/api/projects/{project_id}/estimates/{estimate_id}/lines/{line_id}",
        "/api/projects/{project_id}/estimates/{estimate_id}/finalize",
    }
    for path in expected:
        assert path in paths, f"Missing route: {path}"


def test_reveal_work_routes_registered():
    from app.main import app
    paths = {p for p in app.openapi()["paths"]}
    reveal_path = (
        "/api/projects/{project_id}/rooms/{room_id}"
        "/surfaces/{surface_id}/openings/{opening_id}/reveal-works"
    )
    assert reveal_path in paths


# ===========================================================================
# C1 — No silent regeneration: POST /generate with active DRAFT → 409
# ===========================================================================

async def test_c1_generate_with_active_draft_returns_409(
    async_client: AsyncClient, db_session
):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)

    first = await async_client.post(
        f"{_est(project.id)}/generate", headers=auth(token)
    )
    assert first.status_code == 200

    second = await async_client.post(
        f"{_est(project.id)}/generate", headers=auth(token)
    )
    assert second.status_code == 409


async def test_c1_draft_lines_unchanged_after_conflict(
    async_client: AsyncClient, db_session
):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    surface = await _make_surface(db_session, room.id)
    item = await _make_price_item(db_session, owner.id, price="20.00")
    await _make_work_plan(db_session, project.id, room.id, surface.id, owner.id, [item])
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)
    original_line_id = estimate.lines[0].id

    second = await async_client.post(
        f"{_est(project.id)}/generate", headers=auth(token)
    )
    assert second.status_code == 409

    # Verify lines are unchanged
    from app.models.estimate import EstimateLine
    from sqlalchemy import select as sel
    lines = (await db_session.execute(
        sel(EstimateLine).where(EstimateLine.estimate_id == estimate.id)
    )).scalars().all()
    assert len(lines) == 1
    assert lines[0].id == original_line_id
    assert lines[0].unit_price == Decimal("20.00")


async def test_c1_no_snapshot_mutation_on_conflict(
    async_client: AsyncClient, db_session
):
    """Quantity override on a line must survive repeated POST /generate (409 path)."""
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project, estimate, line = await _draft_with_work_plan_line(db_session, owner)

    # Override quantity
    await async_client.patch(
        _line(project.id, estimate.id, line.id),
        headers=auth(token),
        json={"quantity": "99.000"},
    )

    # Trigger 409 (draft already exists)
    resp = await async_client.post(
        f"{_est(project.id)}/generate", headers=auth(token)
    )
    assert resp.status_code == 409

    # The line override must survive
    from app.models.estimate import EstimateLine
    from sqlalchemy import select as sel
    refreshed = (await db_session.execute(
        sel(EstimateLine).where(EstimateLine.id == line.id)
    )).scalar_one()
    assert refreshed.quantity == Decimal("99.000")
    assert refreshed.quantity_overridden is True


# ===========================================================================
# C2 — Reveal nested-path hierarchy validation
# ===========================================================================

async def _reveal_setup_two_projects(db_session, owner):
    """Creates two isolated project/room/surface/opening setups for the same owner."""
    project_a = await _make_project(db_session, owner.id)
    room_a = await _make_room(db_session, project_a.id)
    surface_a = await _make_surface(db_session, room_a.id)
    opening_a = await _make_opening(
        db_session, surface_a.id, reveal_enabled=True, reveal_depth="15.000"
    )
    project_b = await _make_project(db_session, owner.id)
    room_b = await _make_room(db_session, project_b.id)
    surface_b = await _make_surface(db_session, room_b.id)
    opening_b = await _make_opening(
        db_session, surface_b.id, reveal_enabled=True, reveal_depth="15.000"
    )
    return (project_a, room_a, surface_a, opening_a,
            project_b, room_b, surface_b, opening_b)


async def test_c2_reveal_wrong_project_404(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    (project_a, room_a, surface_a, opening_a,
     project_b, room_b, surface_b, opening_b) = await _reveal_setup_two_projects(
        db_session, owner
    )

    # opening_b accessed via project_a path → 404
    resp = await async_client.get(
        _reveal(project_a.id, room_b.id, surface_b.id, opening_b.id),
        headers=auth(token),
    )
    assert resp.status_code == 404


async def test_c2_reveal_wrong_room_404(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room_a = await _make_room(db_session, project.id)
    surface_a = await _make_surface(db_session, room_a.id)
    opening_a = await _make_opening(
        db_session, surface_a.id, reveal_enabled=True, reveal_depth="15.000"
    )
    room_b = await _make_room(db_session, project.id)

    # Correct project, wrong room in path
    resp = await async_client.get(
        _reveal(project.id, room_b.id, surface_a.id, opening_a.id),
        headers=auth(token),
    )
    assert resp.status_code == 404


async def test_c2_reveal_wrong_surface_404(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    surface_a = await _make_surface(db_session, room.id, position=0)
    opening_a = await _make_opening(
        db_session, surface_a.id, reveal_enabled=True, reveal_depth="15.000"
    )
    surface_b = await _make_surface(db_session, room.id, position=1)

    # Correct project/room, wrong surface in path
    resp = await async_client.get(
        _reveal(project.id, room.id, surface_b.id, opening_a.id),
        headers=auth(token),
    )
    assert resp.status_code == 404


async def test_c2_reveal_correct_hierarchy_200(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project, room, surface, opening = await _reveal_setup(db_session, owner)

    resp = await async_client.get(
        _reveal(project.id, room.id, surface.id, opening.id),
        headers=auth(token),
    )
    assert resp.status_code == 200


async def test_c2_reveal_put_wrong_surface_404(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    surface_a = await _make_surface(db_session, room.id, position=0)
    opening_a = await _make_opening(
        db_session, surface_a.id, reveal_enabled=True, reveal_depth="15.000"
    )
    surface_b = await _make_surface(db_session, room.id, position=1)
    item = await _make_reveal_item(db_session, owner.id)

    resp = await async_client.put(
        _reveal(project.id, room.id, surface_b.id, opening_a.id),
        headers=auth(token),
        json={"price_item_ids": [str(item.id)]},
    )
    assert resp.status_code == 404


async def test_c2_reveal_delete_wrong_project_404(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    (project_a, room_a, surface_a, opening_a,
     project_b, room_b, surface_b, opening_b) = await _reveal_setup_two_projects(
        db_session, owner
    )

    resp = await async_client.delete(
        _reveal(project_a.id, room_b.id, surface_b.id, opening_b.id),
        headers=auth(token),
    )
    assert resp.status_code == 404


# ===========================================================================
# C3 — Manual line currency consistency
# ===========================================================================

async def test_c3_manual_line_matching_currency_accepted(
    async_client: AsyncClient, db_session
):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project, estimate = await _generate_empty_draft(db_session, owner)

    resp = await async_client.post(
        _lines(project.id, estimate.id),
        headers=auth(token),
        json={
            "description": "Praca",
            "scope": "LABOR",
            "unit": "HOUR",
            "quantity": "2.000",
            "unit_price": "50.00",
            "currency": "PLN",
        },
    )
    assert resp.status_code == 201, resp.text


async def test_c3_manual_line_mismatched_currency_rejected(
    async_client: AsyncClient, db_session
):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project, estimate = await _generate_empty_draft(db_session, owner)

    resp = await async_client.post(
        _lines(project.id, estimate.id),
        headers=auth(token),
        json={
            "description": "Praca EUR",
            "scope": "LABOR",
            "unit": "HOUR",
            "quantity": "2.000",
            "unit_price": "50.00",
            "currency": "EUR",
        },
    )
    assert resp.status_code == 422


async def test_c3_total_unchanged_after_rejected_currency(
    async_client: AsyncClient, db_session
):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project, estimate, line = await _draft_with_work_plan_line(db_session, owner)

    before = (await async_client.get(
        _est_id(project.id, estimate.id), headers=auth(token)
    )).json()["total"]

    await async_client.post(
        _lines(project.id, estimate.id),
        headers=auth(token),
        json={
            "description": "EUR line",
            "scope": "LABOR",
            "unit": "HOUR",
            "quantity": "1.000",
            "unit_price": "1000.00",
            "currency": "EUR",
        },
    )

    after = (await async_client.get(
        _est_id(project.id, estimate.id), headers=auth(token)
    )).json()["total"]
    assert before == after


# ===========================================================================
# C4 — Price override reset
# ===========================================================================

async def test_c4_reset_price_override_to_pricebook(
    async_client: AsyncClient, db_session
):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project, estimate, line = await _draft_with_work_plan_line(db_session, owner)

    # Set an override
    await async_client.patch(
        _line(project.id, estimate.id, line.id),
        headers=auth(token),
        json={"unit_price": "99.00"},
    )

    # Reset the override
    resp = await async_client.patch(
        _line(project.id, estimate.id, line.id),
        headers=auth(token),
        json={"reset_price_override": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["price_override"] is False
    # Restored to original PriceBook price (20.00 from _draft_with_work_plan_line)
    assert data["unit_price"] == "20.00"


async def test_c4_reset_price_override_pricebook_null(
    async_client: AsyncClient, db_session
):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    surface = await _make_surface(db_session, room.id)
    item = await _make_price_item(db_session, owner.id, unit=PriceUnit.M2, price=None)
    await _make_work_plan(db_session, project.id, room.id, surface.id, owner.id, [item])
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)
    line = estimate.lines[0]

    # Set an override
    await async_client.patch(
        _line(project.id, estimate.id, line.id),
        headers=auth(token),
        json={"unit_price": "30.00"},
    )

    # Reset — PriceBook price is NULL so unit_price → NULL, price_override=False
    resp = await async_client.patch(
        _line(project.id, estimate.id, line.id),
        headers=auth(token),
        json={"reset_price_override": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["price_override"] is False
    assert data["unit_price"] is None


async def test_c4_reset_price_override_pricebook_zero(
    async_client: AsyncClient, db_session
):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    surface = await _make_surface(db_session, room.id)
    item = await _make_price_item(db_session, owner.id, unit=PriceUnit.M2, price="0.00")
    await _make_work_plan(db_session, project.id, room.id, surface.id, owner.id, [item])
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)
    line = estimate.lines[0]

    await async_client.patch(
        _line(project.id, estimate.id, line.id),
        headers=auth(token),
        json={"unit_price": "50.00"},
    )
    resp = await async_client.patch(
        _line(project.id, estimate.id, line.id),
        headers=auth(token),
        json={"reset_price_override": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["price_override"] is False
    assert data["unit_price"] == "0.00"


async def test_c4_reset_price_override_rejected_for_manual(
    async_client: AsyncClient, db_session
):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project, estimate = await _generate_empty_draft(db_session, owner)
    line_resp = await async_client.post(
        _lines(project.id, estimate.id),
        headers=auth(token),
        json={"description": "Manual", "scope": "LABOR", "unit": "HOUR", "quantity": "1.000"},
    )
    line_id = line_resp.json()["id"]

    resp = await async_client.patch(
        _line(project.id, estimate.id, line_id),
        headers=auth(token),
        json={"reset_price_override": True},
    )
    assert resp.status_code == 422


async def test_c4_set_and_reset_price_conflict_422(
    async_client: AsyncClient, db_session
):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project, estimate, line = await _draft_with_work_plan_line(db_session, owner)

    resp = await async_client.patch(
        _line(project.id, estimate.id, line.id),
        headers=auth(token),
        json={"unit_price": "35.00", "reset_price_override": True},
    )
    assert resp.status_code == 422


# ===========================================================================
# C5 — Quantity override reset
# ===========================================================================

async def test_c5_quantity_reset_to_source(async_client: AsyncClient, db_session):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project, estimate, line = await _draft_with_work_plan_line(db_session, owner)
    original_src_qty = line.source_quantity

    # Override quantity
    await async_client.patch(
        _line(project.id, estimate.id, line.id),
        headers=auth(token),
        json={"quantity": "999.000"},
    )

    # Reset quantity override
    resp = await async_client.patch(
        _line(project.id, estimate.id, line.id),
        headers=auth(token),
        json={"reset_quantity_override": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["quantity_overridden"] is False
    # Quantity restored to source_quantity
    assert Decimal(data["quantity"]) == original_src_qty


async def test_c5_quantity_reset_null_source_gives_zero(
    async_client: AsyncClient, db_session
):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    surface = await _make_surface(db_session, room.id)
    # HOUR unit → source_quantity is NULL (not area-based)
    item = await _make_price_item(
        db_session, owner.id, unit=PriceUnit.HOUR, price="50.00"
    )
    await _make_work_plan(db_session, project.id, room.id, surface.id, owner.id, [item])
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)
    line = estimate.lines[0]
    assert line.source_quantity is None

    # Override quantity
    await async_client.patch(
        _line(project.id, estimate.id, line.id),
        headers=auth(token),
        json={"quantity": "5.000"},
    )

    # Reset with null source → quantity = 0.000
    resp = await async_client.patch(
        _line(project.id, estimate.id, line.id),
        headers=auth(token),
        json={"reset_quantity_override": True},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["quantity_overridden"] is False
    assert data["quantity"] == "0.000"


async def test_c5_set_and_reset_quantity_conflict_422(
    async_client: AsyncClient, db_session
):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project, estimate, line = await _draft_with_work_plan_line(db_session, owner)

    resp = await async_client.patch(
        _line(project.id, estimate.id, line.id),
        headers=auth(token),
        json={"quantity": "11.000", "reset_quantity_override": True},
    )
    assert resp.status_code == 422


# ===========================================================================
# C6 — Actionable regeneration preview with structured change entries
# ===========================================================================

async def test_c6_preview_structured_added_entry(
    async_client: AsyncClient, db_session
):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    surface_a = await _make_surface(db_session, room.id, position=0)
    item_a = await _make_price_item(db_session, owner.id, price="20.00")
    await _make_work_plan(
        db_session, project.id, room.id, surface_a.id, owner.id, [item_a]
    )
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)

    # Add a second surface with a new item — this planned work is new
    surface_b = await _make_surface(db_session, room.id, position=1)
    item_b = await _make_price_item(db_session, owner.id, price="15.00")
    await _make_work_plan(
        db_session, project.id, room.id, surface_b.id, owner.id, [item_b]
    )

    resp = await async_client.post(
        f"{_est_id(project.id, estimate.id)}/regenerate-preview",
        headers=auth(token),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["added"] == 1
    changes = data["changes"]
    assert len(changes) == 1
    entry = changes[0]
    assert entry["change_type"] == "ADDED"
    assert entry["estimate_line_id"] is None
    assert entry["new_unit_price"] == "15.00"
    assert entry["old_unit_price"] is None
    assert entry["quantity_overridden"] is False
    assert entry["price_override"] is False


async def test_c6_preview_structured_removed_entry(
    async_client: AsyncClient, db_session
):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    surface = await _make_surface(db_session, room.id)
    item = await _make_price_item(db_session, owner.id, price="20.00")
    await _make_work_plan(db_session, project.id, room.id, surface.id, owner.id, [item])
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)
    existing_line_id = estimate.lines[0].id

    # Archive the surface so its planned works disappear from the plan
    surface.is_archived = True
    db_session.add(surface)
    await db_session.commit()

    resp = await async_client.post(
        f"{_est_id(project.id, estimate.id)}/regenerate-preview",
        headers=auth(token),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["removed"] == 1
    changes = data["changes"]
    assert len(changes) == 1
    entry = changes[0]
    assert entry["change_type"] == "REMOVED"
    assert entry["estimate_line_id"] == str(existing_line_id)
    assert entry["new_unit_price"] is None
    assert entry["old_unit_price"] == "20.00"


async def test_c6_preview_structured_updated_entry(
    async_client: AsyncClient, db_session
):
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    surface = await _make_surface(db_session, room.id)
    item = await _make_price_item(db_session, owner.id, price="20.00")
    await _make_work_plan(db_session, project.id, room.id, surface.id, owner.id, [item])
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)
    existing_line_id = estimate.lines[0].id

    # Modify the PriceItem price directly (same planned_work_id preserved)
    item.price = Decimal("30.00")
    db_session.add(item)
    await db_session.commit()

    resp = await async_client.post(
        f"{_est_id(project.id, estimate.id)}/regenerate-preview",
        headers=auth(token),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["updated"] == 1
    changes = data["changes"]
    assert len(changes) == 1
    entry = changes[0]
    assert entry["change_type"] == "UPDATED"
    assert entry["estimate_line_id"] == str(existing_line_id)
    assert entry["old_unit_price"] == "20.00"
    assert entry["new_unit_price"] == "30.00"


async def test_c6_preview_override_flags_in_changes(
    async_client: AsyncClient, db_session
):
    """quantity_overridden=True is reflected in the UPDATED change entry."""
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    surface = await _make_surface(db_session, room.id)
    item = await _make_price_item(db_session, owner.id, price="20.00")
    await _make_work_plan(db_session, project.id, room.id, surface.id, owner.id, [item])
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)
    line = estimate.lines[0]

    # Set a quantity override
    await async_client.patch(
        _line(project.id, estimate.id, line.id),
        headers=auth(token),
        json={"quantity": "99.000"},
    )

    # Now change the PriceItem price to force an UPDATED entry
    item.price = Decimal("35.00")
    db_session.add(item)
    await db_session.commit()

    resp = await async_client.post(
        f"{_est_id(project.id, estimate.id)}/regenerate-preview",
        headers=auth(token),
    )
    data = resp.json()
    assert data["updated"] == 1
    entry = data["changes"][0]
    assert entry["quantity_overridden"] is True
    # price_override is False (only quantity was overridden)
    assert entry["price_override"] is False


async def test_c6_preview_no_db_mutation(async_client: AsyncClient, db_session):
    """Calling preview must not alter any DB row."""
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    surface = await _make_surface(db_session, room.id)
    item = await _make_price_item(db_session, owner.id, price="20.00")
    await _make_work_plan(db_session, project.id, room.id, surface.id, owner.id, [item])
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)

    # Modify price book to produce a "would change" scenario
    item.price = Decimal("99.00")
    db_session.add(item)
    await db_session.commit()

    # Capture state before preview
    from app.models.estimate import EstimateLine
    from sqlalchemy import select as sel
    line_before = (await db_session.execute(
        sel(EstimateLine).where(EstimateLine.estimate_id == estimate.id)
    )).scalar_one()
    price_before = line_before.unit_price

    await async_client.post(
        f"{_est_id(project.id, estimate.id)}/regenerate-preview",
        headers=auth(token),
    )

    # DB must be unchanged
    await db_session.refresh(line_before)
    assert line_before.unit_price == price_before


async def test_c6_confirm_returns_changes(async_client: AsyncClient, db_session):
    """Confirm regeneration response includes structured changes list."""
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    surface = await _make_surface(db_session, room.id)
    item_a = await _make_price_item(db_session, owner.id, price="10.00")
    await _make_work_plan(db_session, project.id, room.id, surface.id, owner.id, [item_a])
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)

    # Replace plan with new item (new planned_work_id) → ADDED + REMOVED
    item_b = await _make_price_item(db_session, owner.id, price="20.00")
    await _make_work_plan(
        db_session, project.id, room.id, surface.id, owner.id, [item_b]
    )

    resp = await async_client.post(
        f"{_est_id(project.id, estimate.id)}/regenerate",
        headers=auth(token),
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["added"] == 1
    assert data["removed"] == 1
    assert "changes" in data
    change_types = {c["change_type"] for c in data["changes"]}
    assert "ADDED" in change_types
    assert "REMOVED" in change_types


# ===========================================================================
# Provenance enrichment tests (10G.2)
# ===========================================================================

@pytest.mark.asyncio
async def test_get_estimate_provenance_planned_line(async_client: AsyncClient, db_session):
    """GET /estimates/{id} returns room_name and surface_name for PLANNED_WORK lines."""
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    surface = await _make_surface(db_session, room.id)
    item = await _make_price_item(db_session, owner.id)
    await _make_work_plan(db_session, project.id, room.id, surface.id, owner.id, [item])
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)

    resp = await async_client.get(_est_id(project.id, estimate.id), headers=auth(token))
    assert resp.status_code == 200, resp.text
    line = resp.json()["lines"][0]
    assert line["room_name"] == "Salon"
    assert line["surface_name"] == "Ściana"
    assert line["surface_type_value"] == "WALL"
    assert line["opening_name"] is None
    assert line["opening_type_value"] is None


@pytest.mark.asyncio
async def test_get_estimate_provenance_reveal_line(async_client: AsyncClient, db_session):
    """GET /estimates/{id} returns opening_name and opening_type_value for reveal lines."""
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    surface = await _make_surface(db_session, room.id)
    item = await _make_reveal_item(db_session, owner.id)
    opening = await _make_opening(db_session, surface.id, reveal_enabled=True, reveal_depth="120.000")
    svc = EstimateService(db_session)

    from app.models.opening_reveal_planned_work import OpeningRevealPlannedWork
    reveal_work = OpeningRevealPlannedWork(
        opening_id=opening.id,
        price_item_id=item.id,
        position=0,
    )
    db_session.add(reveal_work)
    await db_session.commit()

    estimate = await svc.generate_estimate(project.id, owner.id)

    resp = await async_client.get(_est_id(project.id, estimate.id), headers=auth(token))
    assert resp.status_code == 200, resp.text
    reveal_lines = [l for l in resp.json()["lines"] if l["opening_id"] is not None]
    assert len(reveal_lines) >= 1
    line = reveal_lines[0]
    assert line["opening_name"] == "Drzwi"
    assert line["opening_type_value"] == "DOOR"
    assert line["room_name"] == "Salon"
    assert line["surface_name"] == "Ściana"


@pytest.mark.asyncio
async def test_get_estimate_provenance_manual_line_null(async_client: AsyncClient, db_session):
    """Manual lines have null provenance fields (no room/surface/opening)."""
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)

    resp = await async_client.post(
        f"{_est_id(project.id, estimate.id)}/lines",
        headers=auth(token),
        json={
            "description": "Manual pozycja",
            "scope": "LABOR",
            "unit": "M2",
            "quantity": "5.000",
            "unit_price": "10.00",
            "currency": "PLN",
        },
    )
    assert resp.status_code == 201, resp.text

    resp = await async_client.get(_est_id(project.id, estimate.id), headers=auth(token))
    assert resp.status_code == 200, resp.text
    manual_lines = [l for l in resp.json()["lines"] if l["origin"] == "MANUAL"]
    assert len(manual_lines) == 1
    line = manual_lines[0]
    assert line["room_name"] is None
    assert line["surface_name"] is None
    assert line["surface_type_value"] is None
    assert line["opening_name"] is None
    assert line["opening_type_value"] is None


async def test_regeneration_total_reflects_new_room_after_confirm(
    async_client: AsyncClient, db_session
):
    """Owner-reported real multi-room scenario: Estimate.total must be
    recalculated from the regenerated authoritative line set after confirm,
    not remain the pre-regeneration DB-persisted value.
    """
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room_a = await _make_room(db_session, project.id, name="pokój 1")
    surface_a = await _make_surface(db_session, room_a.id)
    item = await _make_price_item(db_session, owner.id, price="30.00")
    await _make_work_plan(db_session, project.id, room_a.id, surface_a.id, owner.id, [item])
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)
    total_before = estimate.total
    assert total_before is not None

    room_b = await _make_room(db_session, project.id, name="kuchnia")
    surface_b = await _make_surface(db_session, room_b.id)
    await _make_work_plan(db_session, project.id, room_b.id, surface_b.id, owner.id, [item])

    # Preview must not mutate the persisted total.
    preview_resp = await async_client.post(
        f"{_est_id(project.id, estimate.id)}/regenerate-preview", headers=auth(token)
    )
    assert preview_resp.status_code == 200, preview_resp.text
    unchanged_get = await async_client.get(_est_id(project.id, estimate.id), headers=auth(token))
    assert Decimal(unchanged_get.json()["total"]) == total_before

    confirm_resp = await async_client.post(
        f"{_est_id(project.id, estimate.id)}/regenerate", headers=auth(token)
    )
    assert confirm_resp.status_code == 200, confirm_resp.text

    get_resp = await async_client.get(_est_id(project.id, estimate.id), headers=auth(token))
    data = get_resp.json()
    line_amount_sum = sum(
        Decimal(ln["amount"]) for ln in data["lines"] if ln["amount"] is not None
    )
    new_total = Decimal(data["total"])
    assert new_total == line_amount_sum
    assert new_total == total_before * 2  # two identical rooms/work
    assert {ln["room_name"] for ln in data["lines"]} == {"pokój 1", "kuchnia"}


async def test_regeneration_total_preserves_overrides_null_and_zero_price(
    async_client: AsyncClient, db_session
):
    """Regeneration-triggered total recalculation must still honor the
    Stage 10D invariants: overridden quantity/price preserved and included,
    NULL price excluded from the resolved total (but the line remains),
    explicit 0.00 included as zero (never treated as NULL).
    """
    token = await get_token(async_client, VALID_USER)
    owner = (await db_session.execute(
        select(User).where(User.telegram_user_id == VALID_USER["id"])
    )).scalar_one()
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id, name="Salon")
    surface = await _make_surface(db_session, room.id)
    item = await _make_price_item(db_session, owner.id, price="10.00")
    await _make_work_plan(db_session, project.id, room.id, surface.id, owner.id, [item])
    svc = EstimateService(db_session)
    estimate = await svc.generate_estimate(project.id, owner.id)

    # Owner overrides quantity and price before regeneration.
    planned_line = estimate.lines[0]
    planned_line.quantity = Decimal("99.000")
    planned_line.quantity_overridden = True
    planned_line.unit_price = Decimal("77.00")
    planned_line.price_override = True
    planned_line.amount = Decimal("99.000") * Decimal("77.00")
    await db_session.commit()

    await svc.add_manual_line(
        estimate.id, owner.id, description="Do wyceny", scope=PriceScope.LABOR,
        unit=PriceUnit.FLAT, quantity=Decimal("1.000"), unit_price=None,
    )
    await svc.add_manual_line(
        estimate.id, owner.id, description="Gratis", scope=PriceScope.LABOR,
        unit=PriceUnit.FLAT, quantity=Decimal("1.000"), unit_price=Decimal("0.00"),
    )

    # A genuine source change so regeneration has something to do.
    room_b = await _make_room(db_session, project.id, name="kuchnia")
    surface_b = await _make_surface(db_session, room_b.id)
    item_b = await _make_price_item(db_session, owner.id, price="20.00")
    await _make_work_plan(db_session, project.id, room_b.id, surface_b.id, owner.id, [item_b])

    resp = await async_client.post(
        f"{_est_id(project.id, estimate.id)}/regenerate", headers=auth(token)
    )
    assert resp.status_code == 200, resp.text

    get_resp = await async_client.get(_est_id(project.id, estimate.id), headers=auth(token))
    data = get_resp.json()

    salon_line = next(ln for ln in data["lines"] if ln["room_name"] == "Salon")
    assert salon_line["quantity_overridden"] is True
    assert Decimal(salon_line["quantity"]) == Decimal("99.000")
    assert salon_line["price_override"] is True
    assert Decimal(salon_line["unit_price"]) == Decimal("77.00")
    assert Decimal(salon_line["amount"]) == Decimal("99.000") * Decimal("77.00")

    manual_lines = [ln for ln in data["lines"] if ln["origin"] == "MANUAL"]
    null_line = next(ln for ln in manual_lines if ln["unit_price"] is None)
    zero_line = next(ln for ln in manual_lines if ln["unit_price"] == "0.00")
    assert null_line["amount"] is None
    assert zero_line["amount"] == "0.00"

    expected_total = sum(
        Decimal(ln["amount"]) for ln in data["lines"] if ln["amount"] is not None
    )
    # The NULL-priced manual line contributes nothing to the resolved total,
    # while the explicit 0.00 line is included (as zero, not excluded).
    assert Decimal(data["total"]) == expected_total
