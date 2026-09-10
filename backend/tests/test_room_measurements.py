from decimal import Decimal
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.rules.room_geometry import (
    calculate_room_geometry,
    calculate_surface_gross_area,
)
from app.models.room import Room
from app.models.surface import Surface, SurfaceType
from tests.conftest import make_telegram_init_data

OWNER_USER = {
    "id": 111222333,
    "username": "measure_owner",
    "first_name": "Measure",
    "last_name": "Owner",
    "language_code": "pl",
}

FOREIGN_USER = {
    "id": 444555666,
    "username": "foreign_user",
    "first_name": "Foreign",
    "last_name": "User",
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


async def create_project(async_client: AsyncClient, token: str) -> dict:
    response = await async_client.post(
        "/api/projects",
        json={
            "name": "Projekt z pomiarami",
            "address": "ul. Geodezyjna 5",
            "city": "Kraków",
            "postal_code": "30-001",
        },
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------------
# Unit tests: Pure domain rules (room_geometry)
# ---------------------------------------------------------------------------


def test_domain_geometry_calculation_canonical_room() -> None:
    length = Decimal("5.000")
    width = Decimal("4.000")
    height = Decimal("2.700")

    result = calculate_room_geometry(length, width, height)

    assert result is not None
    assert result.floor_area == Decimal("20.000")
    assert result.ceiling_area == Decimal("20.000")
    assert result.wall_area_length == Decimal("13.500")
    assert result.wall_area_width == Decimal("10.800")
    assert result.total_wall_area == Decimal("48.600")
    assert result.perimeter == Decimal("18.000")

    # Verify mathematical identity: total wall area equals 2 * (L*H + W*H)
    assert result.total_wall_area == (2 * (result.wall_area_length + result.wall_area_width))


@pytest.mark.parametrize(
    ("length", "width", "height"),
    [
        (None, Decimal("4.000"), Decimal("2.700")),
        (Decimal("5.000"), None, Decimal("2.700")),
        (Decimal("5.000"), Decimal("4.000"), None),
        (Decimal("0.000"), Decimal("4.000"), Decimal("2.700")),
        (Decimal("5.000"), Decimal("-1.000"), Decimal("2.700")),
        (Decimal("5.000"), Decimal("4.000"), Decimal("0.000")),
    ],
)
def test_domain_geometry_calculation_invalid_or_missing_inputs(
    length: Decimal | None,
    width: Decimal | None,
    height: Decimal | None,
) -> None:
    assert calculate_room_geometry(length, width, height) is None


def test_domain_surface_gross_area_wall() -> None:
    width = Decimal("5.000")
    height = Decimal("2.700")
    area = calculate_surface_gross_area(SurfaceType.WALL, width, height)
    assert area == Decimal("13.500")


def test_domain_surface_gross_area_floor_ceiling_fallback() -> None:
    room_l = Decimal("5.000")
    room_w = Decimal("4.000")

    floor_area = calculate_surface_gross_area(
        SurfaceType.FLOOR,
        None,
        None,
        room_length=room_l,
        room_width=room_w,
    )
    assert floor_area == Decimal("20.000")

    ceiling_area = calculate_surface_gross_area(
        SurfaceType.CEILING,
        None,
        None,
        room_length=room_l,
        room_width=room_w,
    )
    assert ceiling_area == Decimal("20.000")


# ---------------------------------------------------------------------------
# API Integration tests: Room & Surface measurements
# ---------------------------------------------------------------------------


async def test_create_room_with_canonical_measurements(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await get_token(async_client, OWNER_USER)
    project = await create_project(async_client, token)

    response = await async_client.post(
        f"/api/projects/{project['id']}/rooms",
        json={
            "name": "Salon Główny",
            "description": "Wymiary wzorcowe 5x4x2.7",
            "length": "5.000",
            "width": "4.000",
            "height": "2.700",
        },
        headers=auth_header(token),
    )

    assert response.status_code == 201, response.text
    data = response.json()

    assert Decimal(data["length"]) == Decimal("5.000")
    assert Decimal(data["width"]) == Decimal("4.000")
    assert Decimal(data["height"]) == Decimal("2.700")

    calcs = data["calculations"]
    assert calcs is not None
    assert Decimal(calcs["floor_area"]) == Decimal("20.000")
    assert Decimal(calcs["ceiling_area"]) == Decimal("20.000")
    assert Decimal(calcs["total_wall_area"]) == Decimal("48.600")
    assert Decimal(calcs["wall_area_length"]) == Decimal("13.500")
    assert Decimal(calcs["wall_area_width"]) == Decimal("10.800")
    assert Decimal(calcs["perimeter"]) == Decimal("18.000")

    # Verify database persistence
    result = await db_session.execute(
        select(Room).where(Room.id == uuid.UUID(data["id"]))
    )
    persisted = result.scalar_one()
    assert persisted.length == Decimal("5.000")
    assert persisted.width == Decimal("4.000")
    assert persisted.height == Decimal("2.700")


async def test_four_individual_wall_surfaces_sum_to_room_total_wall_area(
    async_client: AsyncClient,
) -> None:
    """Canonical test: 4 individual walls (two 5.000x2.700 and two 4.000x2.700)

    must produce gross areas of 13.500 m² and 10.800 m², whose sum equals
    the room's calculated total_wall_area of 48.600 m².
    """
    token = await get_token(async_client, OWNER_USER)
    project = await create_project(async_client, token)

    # 1. Create Room 5.000 x 4.000 x 2.700
    room_res = await async_client.post(
        f"/api/projects/{project['id']}/rooms",
        json={
            "name": "Salon z 4 ścianami",
            "length": "5.000",
            "width": "4.000",
            "height": "2.700",
        },
        headers=auth_header(token),
    )
    assert room_res.status_code == 201
    room = room_res.json()
    room_id = room["id"]

    # 2. Create 4 distinct physical WALL surfaces
    walls_payload = [
        {"name": "Ściana Północna (L)", "width": "5.000", "height": "2.700"},
        {"name": "Ściana Wschodnia (W)", "width": "4.000", "height": "2.700"},
        {"name": "Ściana Południowa (L)", "width": "5.000", "height": "2.700"},
        {"name": "Ściana Zachodnia (W)", "width": "4.000", "height": "2.700"},
    ]

    created_walls = []
    for wall in walls_payload:
        res = await async_client.post(
            f"/api/projects/{project['id']}/rooms/{room_id}/surfaces",
            json={
                "name": wall["name"],
                "surface_type": "WALL",
                "width": wall["width"],
                "height": wall["height"],
            },
            headers=auth_header(token),
        )
        assert res.status_code == 201, res.text
        created_walls.append(res.json())

    # Verify individual surface gross areas
    assert Decimal(created_walls[0]["gross_area"]) == Decimal("13.500")
    assert Decimal(created_walls[1]["gross_area"]) == Decimal("10.800")
    assert Decimal(created_walls[2]["gross_area"]) == Decimal("13.500")
    assert Decimal(created_walls[3]["gross_area"]) == Decimal("10.800")

    # Verify sum of 4 walls matches room total wall area independently
    wall_area_sum = sum(Decimal(w["gross_area"]) for w in created_walls)
    room_total_wall_area = Decimal(room["calculations"]["total_wall_area"])

    assert wall_area_sum == Decimal("48.600")
    assert room_total_wall_area == Decimal("48.600")
    assert wall_area_sum == room_total_wall_area

    # Also verify individual wall sizes match room length/width wall areas
    assert Decimal(created_walls[0]["gross_area"]) == Decimal(room["calculations"]["wall_area_length"])
    assert Decimal(created_walls[1]["gross_area"]) == Decimal(room["calculations"]["wall_area_width"])


async def test_update_room_and_surface_measurements(
    async_client: AsyncClient,
) -> None:
    token = await get_token(async_client, OWNER_USER)
    project = await create_project(async_client, token)

    # 1. Create room without measurements
    room_res = await async_client.post(
        f"/api/projects/{project['id']}/rooms",
        json={"name": "Pokój do pomiaru"},
        headers=auth_header(token),
    )
    room_id = room_res.json()["id"]
    assert room_res.json()["length"] is None
    assert room_res.json()["calculations"] is None

    # 2. Update room measurements
    patch_res = await async_client.patch(
        f"/api/projects/{project['id']}/rooms/{room_id}",
        json={
            "length": "6.000",
            "width": "3.500",
            "height": "3.000",
        },
        headers=auth_header(token),
    )
    assert patch_res.status_code == 200
    updated_room = patch_res.json()
    assert Decimal(updated_room["length"]) == Decimal("6.000")
    assert Decimal(updated_room["width"]) == Decimal("3.500")
    assert Decimal(updated_room["height"]) == Decimal("3.000")

    calcs = updated_room["calculations"]
    assert calcs is not None
    assert Decimal(calcs["floor_area"]) == Decimal("21.000")
    assert Decimal(calcs["ceiling_area"]) == Decimal("21.000")
    assert Decimal(calcs["total_wall_area"]) == Decimal("57.000")
    assert Decimal(calcs["perimeter"]) == Decimal("19.000")

    # 3. Create surface without measurements, then update
    surf_res = await async_client.post(
        f"/api/projects/{project['id']}/rooms/{room_id}/surfaces",
        json={"name": "Ściana A", "surface_type": "WALL"},
        headers=auth_header(token),
    )
    surface_id = surf_res.json()["id"]
    assert surf_res.json()["width"] is None
    assert surf_res.json()["gross_area"] is None

    patch_surf_res = await async_client.patch(
        f"/api/projects/{project['id']}/rooms/{room_id}/surfaces/{surface_id}",
        json={"width": "6.000", "height": "3.000"},
        headers=auth_header(token),
    )
    assert patch_surf_res.status_code == 200
    updated_surf = patch_surf_res.json()
    assert Decimal(updated_surf["width"]) == Decimal("6.000")
    assert Decimal(updated_surf["height"]) == Decimal("3.000")
    assert Decimal(updated_surf["gross_area"]) == Decimal("18.000")


@pytest.mark.parametrize(
    ("payload", "error_field"),
    [
        ({"name": "R", "length": "0"}, "length"),
        ({"name": "R", "length": "-1.5"}, "length"),
        ({"name": "R", "width": "0"}, "width"),
        ({"name": "R", "width": "-2.000"}, "width"),
        ({"name": "R", "height": "0"}, "height"),
        ({"name": "R", "height": "-0.5"}, "height"),
        ({"name": "R", "length": "5.1234"}, "length"),  # > 3 decimal places
    ],
)
async def test_room_dimension_validation_rejections(
    async_client: AsyncClient,
    payload: dict,
    error_field: str,
) -> None:
    token = await get_token(async_client, OWNER_USER)
    project = await create_project(async_client, token)

    response = await async_client.post(
        f"/api/projects/{project['id']}/rooms",
        json=payload,
        headers=auth_header(token),
    )
    assert response.status_code == 422, response.text
    errors = response.json().get("detail", [])
    assert any(error_field in e.get("loc", []) for e in errors)


@pytest.mark.parametrize(
    ("payload", "error_field"),
    [
        ({"name": "S", "surface_type": "WALL", "width": "0"}, "width"),
        ({"name": "S", "surface_type": "WALL", "width": "-3.000"}, "width"),
        ({"name": "S", "surface_type": "WALL", "height": "0"}, "height"),
        ({"name": "S", "surface_type": "WALL", "height": "-2.5"}, "height"),
        ({"name": "S", "surface_type": "WALL", "width": "3.1234"}, "width"),
    ],
)
async def test_surface_dimension_validation_rejections(
    async_client: AsyncClient,
    payload: dict,
    error_field: str,
) -> None:
    token = await get_token(async_client, OWNER_USER)
    project = await create_project(async_client, token)
    room_res = await async_client.post(
        f"/api/projects/{project['id']}/rooms",
        json={"name": "Pokój"},
        headers=auth_header(token),
    )
    room_id = room_res.json()["id"]

    response = await async_client.post(
        f"/api/projects/{project['id']}/rooms/{room_id}/surfaces",
        json=payload,
        headers=auth_header(token),
    )
    assert response.status_code == 422, response.text
    errors = response.json().get("detail", [])
    assert any(error_field in e.get("loc", []) for e in errors)


async def test_backward_compatibility_rooms_and_surfaces_without_measurements(
    async_client: AsyncClient,
) -> None:
    token = await get_token(async_client, OWNER_USER)
    project = await create_project(async_client, token)

    room_res = await async_client.post(
        f"/api/projects/{project['id']}/rooms",
        json={"name": "Stary pokój bez pomiarów"},
        headers=auth_header(token),
    )
    assert room_res.status_code == 201
    room = room_res.json()
    assert room["length"] is None
    assert room["width"] is None
    assert room["height"] is None
    assert room["calculations"] is None

    surf_res = await async_client.post(
        f"/api/projects/{project['id']}/rooms/{room['id']}/surfaces",
        json={"name": "Ściana bez wymiarów", "surface_type": "WALL"},
        headers=auth_header(token),
    )
    assert surf_res.status_code == 201
    surf = surf_res.json()
    assert surf["width"] is None
    assert surf["height"] is None
    assert surf["gross_area"] is None


async def test_security_owner_isolation_for_measurements(
    async_client: AsyncClient,
) -> None:
    owner_token = await get_token(async_client, OWNER_USER)
    foreign_token = await get_token(async_client, FOREIGN_USER)

    project = await create_project(async_client, owner_token)
    room_res = await async_client.post(
        f"/api/projects/{project['id']}/rooms",
        json={
            "name": "Prywatny pokój",
            "length": "5.000",
            "width": "4.000",
            "height": "2.700",
        },
        headers=auth_header(owner_token),
    )
    room_id = room_res.json()["id"]

    surf_res = await async_client.post(
        f"/api/projects/{project['id']}/rooms/{room_id}/surfaces",
        json={
            "name": "Prywatna ściana",
            "surface_type": "WALL",
            "width": "5.000",
            "height": "2.700",
        },
        headers=auth_header(owner_token),
    )
    surf_id = surf_res.json()["id"]

    # Foreign user cannot read room measurements
    foreign_get_room = await async_client.get(
        f"/api/projects/{project['id']}/rooms/{room_id}",
        headers=auth_header(foreign_token),
    )
    assert foreign_get_room.status_code == 404

    # Foreign user cannot patch room measurements
    foreign_patch_room = await async_client.patch(
        f"/api/projects/{project['id']}/rooms/{room_id}",
        json={"length": "10.000"},
        headers=auth_header(foreign_token),
    )
    assert foreign_patch_room.status_code == 404

    # Foreign user cannot read surface measurements
    foreign_get_surf = await async_client.get(
        f"/api/projects/{project['id']}/rooms/{room_id}/surfaces/{surf_id}",
        headers=auth_header(foreign_token),
    )
    assert foreign_get_surf.status_code == 404

    # Foreign user cannot patch surface measurements
    foreign_patch_surf = await async_client.patch(
        f"/api/projects/{project['id']}/rooms/{room_id}/surfaces/{surf_id}",
        json={"width": "10.000"},
        headers=auth_header(foreign_token),
    )
    assert foreign_patch_surf.status_code == 404

    # Unauthenticated access rejected
    unauth_get = await async_client.get(
        f"/api/projects/{project['id']}/rooms/{room_id}"
    )
    assert unauth_get.status_code == 401
