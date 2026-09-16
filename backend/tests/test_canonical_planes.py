"""Stage 10C.1A canonical FLOOR/CEILING surface tests.

Owner acceptance matrix:
A new room provisions one FLOOR            I  ADD math unchanged
B new room provisions one CEILING          J  SUBTRACT math unchanged
C stable IDs survive room update           K  cross-room association rejected
D no duplicates on repeated provisioning   L  WALL association rejected
E existing WALL generation unchanged       M  plane/type mismatch rejected
F FLOOR segment -> FLOOR Surface           N  owner isolation preserved
G CEILING segment -> CEILING Surface       O  response exposes surface_id
H plane calculations unchanged             P/Q/R WorkPlan on canonical planes
T/U/V legacy-provision and backfill semantics across a reuse lifecycle
"""
from decimal import Decimal
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import CanonicalPlaneConflictError
from app.domain.services.canonical_planes import ensure_canonical_plane_surfaces
from app.models.area_segment import AreaPlane, AreaSegment
from app.models.price_item import PriceCategory, PriceItem, PriceUnit
from app.models.surface import Surface, SurfaceType
from app.models.user import User
from tests.conftest import make_telegram_init_data

VALID_USER = {
    "id": 555555555,
    "username": "canonical_owner",
    "first_name": "Canonical",
    "last_name": "Owner",
    "language_code": "pl",
}

OTHER_USER = {
    "id": 666666666,
    "username": "canonical_other",
    "first_name": "Other",
    "last_name": "Owner",
    "language_code": "pl",
}


async def get_token(async_client: AsyncClient, user_dict: dict) -> str:
    response = await async_client.post(
        "/api/auth/telegram",
        json={"init_data": make_telegram_init_data(user_dict)},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def create_project(
    async_client: AsyncClient,
    token: str,
    name: str = "Projekt kanoniczny",
) -> dict:
    response = await async_client.post(
        "/api/projects",
        json={
            "name": name,
            "address": "ul. Płaszczyznowa 11",
            "city": "Warszawa",
            "postal_code": "00-003",
            "description": "Projekt do testów kanonicznych płaszczyzn",
        },
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_room(
    async_client: AsyncClient,
    token: str,
    project_id: str,
    *,
    name: str = "Salon",
    length: str | None = "5.000",
    width: str | None = "4.000",
    height: str | None = "2.700",
) -> dict:
    payload: dict = {"name": name, "description": "Pomieszczenie testowe"}
    if length is not None:
        payload["length"] = length
    if width is not None:
        payload["width"] = width
    if height is not None:
        payload["height"] = height
    response = await async_client.post(
        f"/api/projects/{project_id}/rooms",
        json=payload,
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def surfaces_url(project_id: str, room_id: str) -> str:
    return f"/api/projects/{project_id}/rooms/{room_id}/surfaces"


async def canonical_planes(
    async_client: AsyncClient,
    token: str,
    project_id: str,
    room_id: str,
) -> dict[str, dict]:
    """Return the room's canonical FLOOR and CEILING surface dicts keyed by type."""
    response = await async_client.get(
        surfaces_url(project_id, room_id), headers=auth_header(token)
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    by_type: dict[str, dict] = {}
    for item in items:
        if item["surface_type"] in {"FLOOR", "CEILING"}:
            by_type[item["surface_type"]] = item
    assert set(by_type) == {"FLOOR", "CEILING"}
    return by_type


def segments_url(project_id: str, room_id: str) -> str:
    return f"/api/projects/{project_id}/rooms/{room_id}/area-segments"


async def create_segment(
    async_client: AsyncClient,
    token: str,
    project_id: str,
    room_id: str,
    *,
    plane: str,
    operation: str = "ADD",
    width: str,
    height: str,
    surface_id: str | None = None,
) -> dict:
    payload: dict = {
        "plane": plane,
        "operation": operation,
        "width": width,
        "height": height,
    }
    if surface_id is not None:
        payload["surface_id"] = surface_id
    response = await async_client.post(
        segments_url(project_id, room_id),
        json=payload,
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def work_plan_url(project_id: str, room_id: str, surface_id: str) -> str:
    return f"{surfaces_url(project_id, room_id)}/{surface_id}/work-plan"


def upsert_plan(
    substrate: str,
    quality_target: str,
    price_item_ids: list[str],
) -> dict:
    return {
        "substrate": substrate,
        "quality_target": quality_target,
        "price_item_ids": price_item_ids,
    }


async def _make_price_item(
    db: AsyncSession,
    owner_id: uuid.UUID,
    *,
    code: str | None = None,
) -> PriceItem:
    item = PriceItem(
        owner_id=owner_id,
        code=code or f"ITEM_{uuid.uuid4().hex[:8].upper()}",
        category=PriceCategory.PAINTING,
        unit=PriceUnit.M2,
        price=Decimal("12.50"),
        is_archived=False,
    )
    db.add(item)
    await db.commit()
    return item


# ---------------------------------------------------------------------------
# A, B, D — provisioning
# ---------------------------------------------------------------------------

async def test_new_room_provisions_one_floor_and_one_ceiling(
    async_client: AsyncClient,
) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])

    planes = await canonical_planes(async_client, token, project["id"], room["id"])
    assert planes["FLOOR"]["name"] == "Floor"
    assert planes["FLOOR"]["position"] == 100
    assert planes["FLOOR"]["is_archived"] is False
    assert planes["CEILING"]["name"] == "Ceiling"
    assert planes["CEILING"]["position"] == 101
    assert planes["CEILING"]["is_archived"] is False


async def test_no_duplicate_planes_on_repeated_provisioning(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    room_id = uuid.UUID(room["id"])

    first = await canonical_planes(async_client, token, project["id"], room["id"])
    await ensure_canonical_plane_surfaces(db_session, room_id)
    await ensure_canonical_plane_surfaces(db_session, room_id)

    result = await db_session.execute(
        select(Surface)
        .where(
            Surface.room_id == room_id,
            Surface.is_archived.is_(False),
            Surface.surface_type.in_((SurfaceType.FLOOR, SurfaceType.CEILING)),
        )
    )
    rows = {row.surface_type: row for row in list(result.scalars().all())}
    assert set(rows) == {SurfaceType.FLOOR, SurfaceType.CEILING}
    assert str(rows[SurfaceType.FLOOR].id) == first["FLOOR"]["id"]
    assert str(rows[SurfaceType.CEILING].id) == first["CEILING"]["id"]


async def test_database_index_rejects_duplicate_active_plane(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])

    with pytest.raises(IntegrityError):
        db_session.add(
            Surface(
                room_id=uuid.UUID(room["id"]),
                name="Druga podłoga",
                surface_type=SurfaceType.FLOOR,
                position=5,
            )
        )
        await db_session.flush()
        await db_session.rollback()


# ---------------------------------------------------------------------------
# C — identity stability
# ---------------------------------------------------------------------------

async def test_canonical_plane_ids_stable_across_room_update(
    async_client: AsyncClient,
) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    before = await canonical_planes(async_client, token, project["id"], room["id"])

    response = await async_client.patch(
        f"/api/projects/{project['id']}/rooms/{room['id']}",
        json={"length": "6.000", "width": "5.000", "height": "3.000"},
        headers=auth_header(token),
    )
    assert response.status_code == 200, response.text

    after = await canonical_planes(async_client, token, project["id"], room["id"])
    assert after["FLOOR"]["id"] == before["FLOOR"]["id"]
    assert after["CEILING"]["id"] == before["CEILING"]["id"]


# ---------------------------------------------------------------------------
# E — WALL generation unaffected
# ---------------------------------------------------------------------------

async def test_wall_generation_keeps_canonical_planes_intact(
    async_client: AsyncClient,
) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    before = await canonical_planes(async_client, token, project["id"], room["id"])

    response = await async_client.post(
        f"{surfaces_url(project['id'], room['id'])}/generate",
        headers=auth_header(token),
    )
    assert response.status_code == 200, response.text
    assert response.json()["total"] == 4

    after = await canonical_planes(async_client, token, project["id"], room["id"])
    assert after["FLOOR"]["id"] == before["FLOOR"]["id"]
    assert after["CEILING"]["id"] == before["CEILING"]["id"]


# ---------------------------------------------------------------------------
# F, G, O — segment-to-surface resolution
# ---------------------------------------------------------------------------

async def test_floor_segment_resolves_and_exposes_canonical_floor(
    async_client: AsyncClient,
) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    floor = (await canonical_planes(async_client, token, project["id"], room["id"]))[
        "FLOOR"
    ]

    segment = await create_segment(
        async_client,
        token,
        project["id"],
        room["id"],
        plane="FLOOR",
        width="2.000",
        height="1.000",
    )
    assert segment["surface_id"] == floor["id"]
    assert segment["plane"] == "FLOOR"


async def test_ceiling_segment_resolves_and_exposes_canonical_ceiling(
    async_client: AsyncClient,
) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    ceiling = (await canonical_planes(async_client, token, project["id"], room["id"]))[
        "CEILING"
    ]

    segment = await create_segment(
        async_client,
        token,
        project["id"],
        room["id"],
        plane="CEILING",
        operation="SUBTRACT",
        width="1.000",
        height="1.000",
    )
    assert segment["surface_id"] == ceiling["id"]
    assert segment["plane"] == "CEILING"


async def test_explicit_valid_surface_id_is_accepted(
    async_client: AsyncClient,
) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    floor = (await canonical_planes(async_client, token, project["id"], room["id"]))[
        "FLOOR"
    ]

    segment = await create_segment(
        async_client,
        token,
        project["id"],
        room["id"],
        plane="FLOOR",
        width="1.000",
        height="0.500",
        surface_id=floor["id"],
    )
    assert segment["surface_id"] == floor["id"]


# ---------------------------------------------------------------------------
# H, I, J, W — measurements identical
# ---------------------------------------------------------------------------

async def test_canonical_planes_do_not_change_measurements(
    async_client: AsyncClient,
) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])

    floor_planes = await canonical_planes(
        async_client, token, project["id"], room["id"]
    )
    await create_segment(
        async_client, token, project["id"], room["id"],
        plane="FLOOR", width="2.000", height="2.000",
    )
    await create_segment(
        async_client, token, project["id"], room["id"],
        plane="FLOOR", operation="SUBTRACT", width="1.000", height="1.000",
    )
    await create_segment(
        async_client, token, project["id"], room["id"],
        plane="CEILING", width="3.000", height="2.000",
    )

    seg_resp = await async_client.get(
        segments_url(project["id"], room["id"]), headers=auth_header(token)
    )
    assert seg_resp.status_code == 200
    planes = seg_resp.json()["planes"]
    assert planes["FLOOR"]["base_area"] == "20.000"
    assert planes["FLOOR"]["adjustment_area"] == "3.000"
    assert planes["FLOOR"]["net_area"] == "23.000"
    assert planes["CEILING"]["base_area"] == "20.000"
    assert planes["CEILING"]["adjustment_area"] == "6.000"
    assert planes["CEILING"]["net_area"] == "26.000"

    room_resp = await async_client.get(
        f"/api/projects/{project['id']}/rooms/{room['id']}",
        headers=auth_header(token),
    )
    assert room_resp.status_code == 200
    calcs = room_resp.json()["calculations"]
    assert Decimal(calcs["floor_area"]) == Decimal("23.000")
    assert Decimal(calcs["ceiling_area"]) == Decimal("26.000")
    assert calcs["wall_count"] == 0


# ---------------------------------------------------------------------------
# K, L, M — surface association rejections
# ---------------------------------------------------------------------------

async def test_cross_room_surface_association_rejected(
    async_client: AsyncClient,
) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room_a = await create_room(async_client, token, project["id"], name="Pokój A")
    room_b = await create_room(async_client, token, project["id"], name="Pokój B")
    floor_a = (await canonical_planes(async_client, token, project["id"], room_a["id"]))[
        "FLOOR"
    ]

    response = await async_client.post(
        segments_url(project["id"], room_b["id"]),
        json={
            "plane": "FLOOR",
            "operation": "ADD",
            "width": "1.000",
            "height": "1.000",
            "surface_id": floor_a["id"],
        },
        headers=auth_header(token),
    )
    assert response.status_code == 409
    assert "does not belong to room" in response.json()["detail"]


async def test_wall_surface_association_rejected(
    async_client: AsyncClient,
) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    wall_resp = await async_client.post(
        surfaces_url(project["id"], room["id"]),
        json={"name": "Ściana", "surface_type": "WALL"},
        headers=auth_header(token),
    )
    assert wall_resp.status_code == 201
    wall = wall_resp.json()

    response = await async_client.post(
        segments_url(project["id"], room["id"]),
        json={
            "plane": "FLOOR",
            "operation": "ADD",
            "width": "1.000",
            "height": "1.000",
            "surface_id": wall["id"],
        },
        headers=auth_header(token),
    )
    assert response.status_code == 409
    assert "does not match" in response.json()["detail"]


async def test_plane_type_mismatch_rejected(
    async_client: AsyncClient,
) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    floor = (await canonical_planes(async_client, token, project["id"], room["id"]))[
        "FLOOR"
    ]

    # FLOOR segment must never attach to the CEILING surface.
    response = await async_client.post(
        segments_url(project["id"], room["id"]),
        json={
            "plane": "CEILING",
            "operation": "ADD",
            "width": "1.000",
            "height": "1.000",
            "surface_id": floor["id"],
        },
        headers=auth_header(token),
    )
    assert response.status_code == 409
    assert "does not match" in response.json()["detail"]


# ---------------------------------------------------------------------------
# N — owner isolation
# ---------------------------------------------------------------------------

async def test_cross_owner_segment_isolated(
    async_client: AsyncClient,
) -> None:
    owner_token = await get_token(async_client, VALID_USER)
    foreign_token = await get_token(async_client, OTHER_USER)
    project = await create_project(async_client, owner_token)

    response = await async_client.post(
        segments_url(project["id"], uuid.uuid4()),
        json={
            "plane": "FLOOR",
            "operation": "ADD",
            "width": "1.000",
            "height": "1.000",
        },
        headers=auth_header(foreign_token),
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# T, U, V — legacy provision / reuse / backfill semantics
# ---------------------------------------------------------------------------

async def test_room_without_planes_is_provisioned_like_backfill(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    room_id = uuid.UUID(room["id"])

    # Simulate a pre-10C.1A room: remove the canonical plane rows entirely.
    await db_session.execute(
        delete(Surface).where(
            Surface.room_id == room_id,
            Surface.surface_type.in_((SurfaceType.FLOOR, SurfaceType.CEILING)),
        )
    )
    await db_session.commit()

    await ensure_canonical_plane_surfaces(db_session, room_id)

    count_res = await db_session.execute(
        select(Surface).where(
            Surface.room_id == room_id,
            Surface.is_archived.is_(False),
            Surface.surface_type.in_((SurfaceType.FLOOR, SurfaceType.CEILING)),
        )
    )
    planes = list(count_res.scalars().all())
    assert [p.surface_type for p in planes] == [SurfaceType.FLOOR, SurfaceType.CEILING]
    assert all(p.name in ("Floor", "Ceiling") for p in planes)


async def test_legitimate_existing_plane_is_reused_not_duplicated(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    room_id = uuid.UUID(room["id"])

    # Rename/reposition the canonical planes to look like manually created rows.
    result = await db_session.execute(
        select(Surface).where(
            Surface.room_id == room_id,
            Surface.surface_type.in_((SurfaceType.FLOOR, SurfaceType.CEILING)),
        )
    )
    for surface in result.scalars().all():
        surface.name = "Moja podłoga" if surface.surface_type is SurfaceType.FLOOR else "Mój sufit"
        surface.position = 5
    await db_session.commit()

    before = {
        s.surface_type: s.id
        for s in (
            await db_session.execute(
                select(Surface).where(Surface.room_id == room_id)
            )
        ).scalars().all()
    }
    await ensure_canonical_plane_surfaces(db_session, room_id)

    after = {
        s.surface_type: s.id
        for s in (
            await db_session.execute(
                select(Surface).where(Surface.room_id == room_id)
            )
        ).scalars().all()
    }
    assert len(after) == 2
    assert after[SurfaceType.FLOOR] == before[SurfaceType.FLOOR]
    assert after[SurfaceType.CEILING] == before[SurfaceType.CEILING]


async def test_segments_reference_the_physical_plane_surface(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    room_id = uuid.UUID(room["id"])

    await create_segment(
        async_client, token, project["id"], room["id"],
        plane="FLOOR", width="1.000", height="1.000",
    )
    await create_segment(
        async_client, token, project["id"], room["id"],
        plane="CEILING", operation="SUBTRACT", width="0.500", height="0.500",
    )

    floor = (
        await db_session.execute(
            select(Surface).where(
                Surface.room_id == room_id,
                Surface.surface_type == SurfaceType.FLOOR,
            )
        )
    ).scalar_one()
    ceiling = (
        await db_session.execute(
            select(Surface).where(
                Surface.room_id == room_id,
                Surface.surface_type == SurfaceType.CEILING,
            )
        )
    ).scalar_one()
    stored = {
        plane: surface_id
        for surface_id, plane in (
            await db_session.execute(
                select(AreaSegment.surface_id, AreaSegment.plane).where(
                    AreaSegment.room_id == room_id
                )
            )
        ).all()
    }
    assert stored == {AreaPlane.FLOOR: floor.id, AreaPlane.CEILING: ceiling.id}


# ---------------------------------------------------------------------------
# Surface lifecycle guards
# ---------------------------------------------------------------------------

async def test_create_duplicate_plane_surface_rejected(
    async_client: AsyncClient,
) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])

    for surface_type in ("FLOOR", "CEILING"):
        response = await async_client.post(
            surfaces_url(project["id"], room["id"]),
            json={"name": f"Druga {surface_type.lower()}", "surface_type": surface_type},
            headers=auth_header(token),
        )
        assert response.status_code == 409
        assert "active" in response.json()["detail"]


async def test_wall_cannot_retype_onto_canonical_plane(
    async_client: AsyncClient,
) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    wall_resp = await async_client.post(
        surfaces_url(project["id"], room["id"]),
        json={"name": "Ściana", "surface_type": "WALL"},
        headers=auth_header(token),
    )
    assert wall_resp.status_code == 201

    response = await async_client.patch(
        f"{surfaces_url(project['id'], room['id'])}/{wall_resp.json()['id']}",
        json={"surface_type": "CEILING"},
        headers=auth_header(token),
    )
    assert response.status_code == 409


async def test_canonical_plane_cannot_change_type(
    async_client: AsyncClient,
) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    floor = (await canonical_planes(async_client, token, project["id"], room["id"]))[
        "FLOOR"
    ]

    response = await async_client.patch(
        f"{surfaces_url(project['id'], room['id'])}/{floor['id']}",
        json={"surface_type": "OTHER"},
        headers=auth_header(token),
    )
    assert response.status_code == 409
    assert "cannot change" in response.json()["detail"]


async def test_canonical_plane_cannot_be_archived(
    async_client: AsyncClient,
) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    ceiling = (await canonical_planes(async_client, token, project["id"], room["id"]))[
        "CEILING"
    ]

    response = await async_client.post(
        f"{surfaces_url(project['id'], room['id'])}/{ceiling['id']}/archive",
        headers=auth_header(token),
    )
    assert response.status_code == 409


async def test_restoring_duplicate_legacy_archived_plane_rejected(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    room_id = uuid.UUID(room["id"])

    # A pre-10C.1A archived plane sitting next to the reinstated canonical one.
    archived = Surface(
        room_id=room_id,
        name="Stara podłoga",
        surface_type=SurfaceType.FLOOR,
        position=None,
        is_archived=True,
    )
    db_session.add(archived)
    await db_session.commit()
    await db_session.refresh(archived)

    response = await async_client.post(
        f"{surfaces_url(project['id'], room['id'])}/{archived.id}/restore",
        headers=auth_header(token),
    )
    assert response.status_code == 409


# ---------------------------------------------------------------------------
# P, Q, R — WorkPlan directly on canonical FLOOR/CEILING
# ---------------------------------------------------------------------------

async def test_work_plan_on_canonical_floor_and_ceiling(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    planes = await canonical_planes(async_client, token, project["id"], room["id"])
    owner = (
        await db_session.execute(
            select(User).where(User.telegram_user_id == VALID_USER["id"])
        )
    ).scalar_one()
    floor_item = await _make_price_item(db_session, owner.id, code="FLOOR")
    ceiling_item = await _make_price_item(db_session, owner.id, code="CEIL")

    floor_resp = await async_client.put(
        work_plan_url(project["id"], room["id"], planes["FLOOR"]["id"]),
        headers=headers,
        json=upsert_plan(
            "GYPSUM_PLASTER",
            "S3",
            [str(floor_item.id)],
        ),
    )
    assert floor_resp.status_code == 200, floor_resp.text
    floor_plan = floor_resp.json()
    assert floor_plan["surface_id"] == planes["FLOOR"]["id"]
    assert floor_plan["substrate"] == "GYPSUM_PLASTER"
    assert floor_plan["quality_target"] == "S3"

    ceiling_resp = await async_client.put(
        work_plan_url(project["id"], room["id"], planes["CEILING"]["id"]),
        headers=headers,
        json=upsert_plan(
            "CONCRETE",
            "S2",
            [str(ceiling_item.id)],
        ),
    )
    assert ceiling_resp.status_code == 200, ceiling_resp.text
    ceiling_plan = ceiling_resp.json()
    assert ceiling_plan["surface_id"] == planes["CEILING"]["id"]
    assert ceiling_plan["substrate"] == "CONCRETE"
    assert ceiling_plan["quality_target"] == "S2"


async def test_floor_and_ceiling_work_plans_remain_independent(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    planes = await canonical_planes(async_client, token, project["id"], room["id"])
    owner = (
        await db_session.execute(
            select(User).where(User.telegram_user_id == VALID_USER["id"])
        )
    ).scalar_one()
    item = await _make_price_item(db_session, owner.id)

    for surface_id, substrate, quality in (
        (planes["FLOOR"]["id"], "GYPSUM_PLASTER", "S3"),
        (planes["CEILING"]["id"], "CONCRETE", "S2"),
    ):
        resp = await async_client.put(
            work_plan_url(project["id"], room["id"], surface_id),
            headers=headers,
            json=upsert_plan(substrate, quality, [str(item.id)]),
        )
        assert resp.status_code == 200, resp.text

    floor_get = await async_client.get(
        work_plan_url(project["id"], room["id"], planes["FLOOR"]["id"]),
        headers=headers,
    )
    ceiling_get = await async_client.get(
        work_plan_url(project["id"], room["id"], planes["CEILING"]["id"]),
        headers=headers,
    )
    assert floor_get.status_code == 200
    assert ceiling_get.status_code == 200
    assert floor_get.json()["substrate"] == "GYPSUM_PLASTER"
    assert ceiling_get.json()["substrate"] == "CONCRETE"
    assert floor_get.json()["quality_target"] == "S3"
    assert ceiling_get.json()["quality_target"] == "S2"