"""Stage 5D.1A: rectangular wall generation + custom sequential wall workflow.

Covers canonical 4-wall generation rules (422/409/idempotent), language-neutral
names, surface-derived room totals (including the canonical 44.700 net case and
the custom 5-wall irregular room), deterministic ordering, and owner isolation.
"""
from decimal import Decimal
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.rules.room_geometry import (
    calculate_room_geometry,
    calculate_wall_derived_totals,
    generate_canonical_walls,
    matches_canonical_wall_set,
    resolve_room_totals,
)
from app.models.surface import Surface, SurfaceType
from tests.conftest import make_telegram_init_data

OWNER_USER = {
    "id": 555666777,
    "username": "wallgen_owner",
    "first_name": "Wallgen",
    "last_name": "Owner",
    "language_code": "pl",
}

FOREIGN_USER = {
    "id": 888999000,
    "username": "wallgen_foreign",
    "first_name": "Wallgen",
    "last_name": "Foreign",
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
            "name": "Projekt 5D.1A",
            "address": "ul. Wymiarowa 9",
            "city": "Warszawa",
            "postal_code": "00-001",
        },
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_room(async_client: AsyncClient, token: str, project_id: str, payload: dict) -> dict:
    response = await async_client.post(
        f"/api/projects/{project_id}/rooms",
        json=payload,
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_wall(
    async_client: AsyncClient,
    token: str,
    project_id: str,
    room_id: str,
    *,
    name: str,
    width: str,
    height: str,
    position: int | None = None,
) -> dict:
    payload: dict = {
        "name": name,
        "surface_type": "WALL",
        "width": width,
        "height": height,
    }
    if position is not None:
        payload["position"] = position
    response = await async_client.post(
        f"/api/projects/{project_id}/rooms/{room_id}/surfaces",
        json=payload,
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_opening(
    async_client: AsyncClient,
    token: str,
    project_id: str,
    room_id: str,
    surface_id: str,
    *,
    opening_type: str,
    width: str,
    height: str,
) -> dict:
    response = await async_client.post(
        f"/api/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}/openings",
        json={
            "opening_type": opening_type,
            "width": width,
            "height": height,
        },
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def generate_url(project_id: str, room_id: str) -> str:
    return f"/api/projects/{project_id}/rooms/{room_id}/surfaces/generate"


def walls_url(project_id: str, room_id: str) -> str:
    return f"/api/projects/{project_id}/rooms/{room_id}/surfaces"


# ---------------------------------------------------------------------------
# Unit tests: pure domain rules
# ---------------------------------------------------------------------------


def test_domain_generate_canonical_walls_returns_language_neutral_4_walls() -> None:
    walls = generate_canonical_walls(Decimal("5.000"), Decimal("4.000"), Decimal("2.700"))

    assert [(p, n, w, h) for p, n, w, h in walls] == [
        (0, "Wall 1", Decimal("5.000"), Decimal("2.700")),
        (1, "Wall 2", Decimal("4.000"), Decimal("2.700")),
        (2, "Wall 3", Decimal("5.000"), Decimal("2.700")),
        (3, "Wall 4", Decimal("4.000"), Decimal("2.700")),
    ]
    # Language-neutral names must not carry Polish or Russian grammar.
    for _, name, _, _ in walls:
        assert name in ("Wall 1", "Wall 2", "Wall 3", "Wall 4")


def test_domain_matches_canonical_wall_set() -> None:
    length = Decimal("5.000")
    width = Decimal("4.000")
    height = Decimal("2.700")

    canonical = [
        (0, SurfaceType.WALL, length, height),
        (1, SurfaceType.WALL, width, height),
        (2, SurfaceType.WALL, length, height),
        (3, SurfaceType.WALL, width, height),
    ]
    assert matches_canonical_wall_set(length, width, height, canonical) is True

    # Reordered set still matches (matcher is set-based on positions).
    reordered = [canonical[1], canonical[0], canonical[3], canonical[2]]
    assert matches_canonical_wall_set(length, width, height, reordered) is True

    # Wrong dimensions on one wall.
    bad_dim = list(canonical)
    bad_dim[0] = (0, SurfaceType.WALL, Decimal("6.000"), height)
    assert matches_canonical_wall_set(length, width, height, bad_dim) is False

    # Missing position (legacy manual wall).
    no_position = [(None, SurfaceType.WALL, length, height), canonical[1], canonical[2], canonical[3]]
    assert matches_canonical_wall_set(length, width, height, no_position) is False

    # Only 3 walls.
    assert matches_canonical_wall_set(length, width, height, canonical[:3]) is False

    # Non-WALL surface cannot be part of the canonical set.
    mixed = [(0, SurfaceType.CEILING, length, height), canonical[1], canonical[2], canonical[3]]
    assert matches_canonical_wall_set(length, width, height, mixed) is False

    # Duplicate position.
    duplicate = [(0, SurfaceType.WALL, length, height), (0, SurfaceType.WALL, width, height), canonical[2], canonical[3]]
    assert matches_canonical_wall_set(length, width, height, duplicate) is False


def test_domain_calculate_wall_derived_totals() -> None:
    walls = [
        (Decimal("5.000"), Decimal("2.700")),
        (Decimal("4.000"), Decimal("2.700")),
        (Decimal("5.000"), Decimal("2.700")),
        (Decimal("4.000"), Decimal("2.700")),
    ]
    totals = calculate_wall_derived_totals(walls, Decimal("3.900"))
    assert totals is not None
    assert totals.wall_count == 4
    assert totals.perimeter == Decimal("18.000")
    assert totals.total_wall_area == Decimal("48.600")
    assert totals.total_deduction_area == Decimal("3.900")
    assert totals.net_wall_area == Decimal("44.700")

    # No measured walls -> None.
    assert calculate_wall_derived_totals([(None, Decimal("2.700"))]) is None
    assert calculate_wall_derived_totals([]) is None

    # Deduction cannot exceed measured gross.
    with pytest.raises(ValueError, match="cannot exceed measured wall area"):
        calculate_wall_derived_totals(walls, Decimal("50.000"))


def test_domain_resolve_room_totals_wall_derived_takes_precedence() -> None:
    geometry = calculate_room_geometry(Decimal("5.000"), Decimal("4.000"), Decimal("2.700"))
    assert geometry is not None
    wall_totals = calculate_wall_derived_totals(
        [
            (Decimal("5.000"), Decimal("2.700")),
            (Decimal("4.000"), Decimal("2.700")),
            (Decimal("5.000"), Decimal("2.700")),
            (Decimal("4.000"), Decimal("2.700")),
        ],
        Decimal("3.900"),
    )

    resolved = resolve_room_totals(geometry, wall_totals, Decimal("3.900"))
    assert resolved is not None
    assert resolved.floor_area == Decimal("20.000")
    assert resolved.ceiling_area == Decimal("20.000")
    assert resolved.total_wall_area == Decimal("48.600")
    assert resolved.perimeter == Decimal("18.000")
    assert resolved.net_wall_area == Decimal("44.700")
    assert resolved.wall_count == 4
    # Formula direction areas remain available for a rectangular room.
    assert resolved.wall_area_length == Decimal("13.500")
    assert resolved.wall_area_width == Decimal("10.800")


def test_domain_resolve_room_totals_custom_room_floor_ceiling_none() -> None:
    # Irregular room without physical dimensions: floor/ceiling must stay None.
    wall_totals = calculate_wall_derived_totals(
        [
            (Decimal("5.000"), Decimal("3.800")),
            (Decimal("4.000"), Decimal("1.250")),
            (Decimal("3.500"), Decimal("4.100")),
            (Decimal("6.000"), Decimal("2.200")),
            (Decimal("2.500"), Decimal("3.000")),
        ],
        Decimal("1.800"),
    )
    assert wall_totals is not None
    assert wall_totals.wall_count == 5
    assert wall_totals.perimeter == Decimal("21.000")
    assert wall_totals.total_wall_area == Decimal("59.050")
    assert wall_totals.total_deduction_area == Decimal("1.800")
    assert wall_totals.net_wall_area == Decimal("57.250")

    resolved = resolve_room_totals(None, wall_totals, Decimal("1.800"))
    assert resolved is not None
    assert resolved.floor_area is None
    assert resolved.ceiling_area is None
    assert resolved.total_wall_area == Decimal("59.050")
    assert resolved.wall_count == 5


def test_domain_resolve_room_totals_no_walls_keeps_formula() -> None:
    geometry = calculate_room_geometry(Decimal("5.000"), Decimal("4.000"), Decimal("2.700"))
    assert geometry is not None
    resolved = resolve_room_totals(geometry, None, Decimal("0.000"))
    assert resolved is not None
    assert resolved.wall_count == 0
    assert resolved.total_wall_area == Decimal("48.600")
    assert resolved.perimeter == Decimal("18.000")
    assert resolved.floor_area == Decimal("20.000")

    # No geometry and no walls -> nothing to report.
    assert resolve_room_totals(None, None) is None


# ---------------------------------------------------------------------------
# API integration: wall generation
# ---------------------------------------------------------------------------


async def test_generate_walls_creates_four_canonical_walls(
    async_client: AsyncClient,
) -> None:
    token = await get_token(async_client, OWNER_USER)
    project = await create_project(async_client, token)
    room = await create_room(
        async_client,
        token,
        project["id"],
        {"name": "Salon", "length": "5.000", "width": "4.000", "height": "2.700"},
    )

    response = await async_client.post(
        generate_url(project["id"], room["id"]),
        headers=auth_header(token),
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["total"] == 4

    walls = data["items"]
    assert [w["position"] for w in walls] == [0, 1, 2, 3]
    assert [Decimal(w["width"]) for w in walls] == [
        Decimal("5.000"),
        Decimal("4.000"),
        Decimal("5.000"),
        Decimal("4.000"),
    ]
    assert all(Decimal(w["height"]) == Decimal("2.700") for w in walls)
    assert all(w["surface_type"] == "WALL" for w in walls)
    assert [Decimal(w["gross_area"]) for w in walls] == [
        Decimal("13.500"),
        Decimal("10.800"),
        Decimal("13.500"),
        Decimal("10.800"),
    ]
    assert all(Decimal(w["deduction_area"]) == Decimal("0.000") for w in walls)


async def test_generate_walls_does_not_create_floor_or_ceiling(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await get_token(async_client, OWNER_USER)
    project = await create_project(async_client, token)
    room = await create_room(
        async_client,
        token,
        project["id"],
        {"name": "Pokój", "length": "5.000", "width": "4.000", "height": "2.700"},
    )

    await async_client.post(generate_url(project["id"], room["id"]), headers=auth_header(token))

    result = await db_session.execute(
        select(Surface.surface_type).where(Surface.room_id == uuid.UUID(room["id"]))
    )
    types = [row[0] for row in result.all()]
    assert types == [SurfaceType.WALL] * 4


async def test_generate_walls_idempotent_noop_returns_existing_walls(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await get_token(async_client, OWNER_USER)
    project = await create_project(async_client, token)
    room = await create_room(
        async_client,
        token,
        project["id"],
        {"name": "Salon", "length": "5.000", "width": "4.000", "height": "2.700"},
    )

    first = await async_client.post(generate_url(project["id"], room["id"]), headers=auth_header(token))
    assert first.status_code == 200
    first_ids = {w["id"] for w in first.json()["items"]}

    second = await async_client.post(generate_url(project["id"], room["id"]), headers=auth_header(token))
    assert second.status_code == 200
    second_ids = {w["id"] for w in second.json()["items"]}

    assert second_ids == first_ids

    count_result = await db_session.execute(
        select(func.count())
        .select_from(Surface)
        .where(
            Surface.room_id == uuid.UUID(room["id"]),
            Surface.is_archived.is_(False),
        )
    )
    assert count_result.scalar_one() == 4


async def test_generate_walls_422_when_dimensions_missing(
    async_client: AsyncClient,
) -> None:
    token = await get_token(async_client, OWNER_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"], {"name": "Bez wymiarów"})

    response = await async_client.post(
        generate_url(project["id"], room["id"]),
        headers=auth_header(token),
    )
    assert response.status_code == 422
    assert "length, width and height" in response.json()["detail"]


async def test_generate_walls_409_when_walls_do_not_match_canonical(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await get_token(async_client, OWNER_USER)
    project = await create_project(async_client, token)
    room = await create_room(
        async_client,
        token,
        project["id"],
        {"name": "Salon", "length": "5.000", "width": "4.000", "height": "2.700"},
    )

    await create_wall(
        async_client,
        token,
        project["id"],
        room["id"],
        name="Ściana niestandardowa",
        width="6.000",
        height="3.500",
        position=0,
    )

    response = await async_client.post(
        generate_url(project["id"], room["id"]),
        headers=auth_header(token),
    )
    assert response.status_code == 409
    assert "do not match" in response.json()["detail"]

    # Nothing was created or modified.
    count_result = await db_session.execute(
        select(func.count())
        .select_from(Surface)
        .where(
            Surface.room_id == uuid.UUID(room["id"]),
            Surface.is_archived.is_(False),
        )
    )
    assert count_result.scalar_one() == 1


async def test_generate_walls_409_when_manual_walls_without_position(
    async_client: AsyncClient,
) -> None:
    token = await get_token(async_client, OWNER_USER)
    project = await create_project(async_client, token)
    room = await create_room(
        async_client,
        token,
        project["id"],
        {"name": "Salon", "length": "5.000", "width": "4.000", "height": "2.700"},
    )

    # Legacy manually created walls have position=None and cannot confirm the
    # canonical contract, so generation must conflict without touching them.
    for name, width, height in [
        ("Ściana 1", "5.000", "2.700"),
        ("Ściana 2", "4.000", "2.700"),
        ("Ściana 3", "5.000", "2.700"),
        ("Ściana 4", "4.000", "2.700"),
    ]:
        await create_wall(
            async_client,
            token,
            project["id"],
            room["id"],
            name=name,
            width=width,
            height=height,
        )

    response = await async_client.post(
        generate_url(project["id"], room["id"]),
        headers=auth_header(token),
    )
    assert response.status_code == 409


async def test_generate_walls_ignores_archived_walls(
    async_client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    token = await get_token(async_client, OWNER_USER)
    project = await create_project(async_client, token)
    room = await create_room(
        async_client,
        token,
        project["id"],
        {"name": "Salon", "length": "5.000", "width": "4.000", "height": "2.700"},
    )

    wall = await create_wall(
        async_client,
        token,
        project["id"],
        room["id"],
        name="Zużyta ściana",
        width="7.000",
        height="2.700",
        position=0,
    )
    archive_resp = await async_client.post(
        f"{walls_url(project['id'], room['id'])}/{wall['id']}/archive",
        headers=auth_header(token),
    )
    assert archive_resp.status_code == 200

    response = await async_client.post(
        generate_url(project["id"], room["id"]),
        headers=auth_header(token),
    )
    assert response.status_code == 200
    assert response.json()["total"] == 4

    # Archived wall is untouched; total surface count is now 5.
    count_result = await db_session.execute(
        select(func.count())
        .select_from(Surface)
        .where(Surface.room_id == uuid.UUID(room["id"]))
    )
    assert count_result.scalar_one() == 5


async def test_generate_walls_owner_isolation(
    async_client: AsyncClient,
) -> None:
    owner_token = await get_token(async_client, OWNER_USER)
    foreign_token = await get_token(async_client, FOREIGN_USER)
    project = await create_project(async_client, owner_token)
    room = await create_room(
        async_client,
        owner_token,
        project["id"],
        {"name": "Salon", "length": "5.000", "width": "4.000", "height": "2.700"},
    )

    response = await async_client.post(
        generate_url(project["id"], room["id"]),
        headers=auth_header(foreign_token),
    )
    assert response.status_code == 404

    # Unauthenticated access rejected.
    unauth = await async_client.post(generate_url(project["id"], room["id"]))
    assert unauth.status_code == 401


# ---------------------------------------------------------------------------
# API integration: surface-derived room totals
# ---------------------------------------------------------------------------


async def test_canonical_rectangle_surface_derived_totals(
    async_client: AsyncClient,
) -> None:
    """Canonical acceptance (Section 8): generated rectangle room with a door and
    window must produce surface-derived totals exactly equal to the formula.

    door 0.9x2.0 -> 1.800, window 1.5x1.4 -> 2.100, deductions 3.900,
    gross 48.600, net 44.700, perimeter 18.000, wall_count 4.
    """
    token = await get_token(async_client, OWNER_USER)
    project = await create_project(async_client, token)
    room = await create_room(
        async_client,
        token,
        project["id"],
        {"name": "Salon wzorcowy", "length": "5.000", "width": "4.000", "height": "2.700"},
    )

    gen = await async_client.post(generate_url(project["id"], room["id"]), headers=auth_header(token))
    assert gen.status_code == 200
    walls = gen.json()["items"]

    await create_opening(
        async_client,
        token,
        project["id"],
        room["id"],
        walls[0]["id"],
        opening_type="DOOR",
        width="0.900",
        height="2.000",
    )
    await create_opening(
        async_client,
        token,
        project["id"],
        room["id"],
        walls[1]["id"],
        opening_type="WINDOW",
        width="1.500",
        height="1.400",
    )

    room_resp = await async_client.get(
        f"/api/projects/{project['id']}/rooms/{room['id']}",
        headers=auth_header(token),
    )
    assert room_resp.status_code == 200
    calcs = room_resp.json()["calculations"]
    assert calcs is not None
    assert calcs["wall_count"] == 4
    assert Decimal(calcs["perimeter"]) == Decimal("18.000")
    assert Decimal(calcs["total_wall_area"]) == Decimal("48.600")
    assert Decimal(calcs["total_deduction_area"]) == Decimal("3.900")
    assert Decimal(calcs["net_wall_area"]) == Decimal("44.700")
    assert Decimal(calcs["floor_area"]) == Decimal("20.000")
    assert Decimal(calcs["ceiling_area"]) == Decimal("20.000")

    # Surface-derived values must equal the pure formula independently.
    geom = calculate_room_geometry(Decimal("5.000"), Decimal("4.000"), Decimal("2.700"))
    assert geom is not None
    assert Decimal(calcs["total_wall_area"]) == geom.total_wall_area
    assert Decimal(calcs["perimeter"]) == geom.perimeter
    assert Decimal(calcs["net_wall_area"]) == geom.total_wall_area - Decimal("3.900")


async def test_custom_irregular_room_surface_derived_totals(
    async_client: AsyncClient,
) -> None:
    """Custom 5-wall room without physical dimensions: floor/ceiling None and all
    wall totals derived strictly from the measured walls."""
    token = await get_token(async_client, OWNER_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"], {"name": "Dach poddasze"})
    assert room["length"] is None
    assert room["width"] is None

    specs = [
        ("5.000", "3.800"),
        ("4.000", "1.250"),
        ("3.500", "4.100"),
        ("6.000", "2.200"),
        ("2.500", "3.000"),
    ]
    walls = []
    for index, (width, height) in enumerate(specs):
        walls.append(
            await create_wall(
                async_client,
                token,
                project["id"],
                room["id"],
                name=f"Skos {index + 1}",
                width=width,
                height=height,
                position=index,
            )
        )

    await create_opening(
        async_client,
        token,
        project["id"],
        room["id"],
        walls[3]["id"],
        opening_type="DOOR",
        width="0.900",
        height="2.000",
    )

    room_resp = await async_client.get(
        f"/api/projects/{project['id']}/rooms/{room['id']}",
        headers=auth_header(token),
    )
    assert room_resp.status_code == 200
    calcs = room_resp.json()["calculations"]
    assert calcs is not None
    assert calcs["wall_count"] == 5
    assert calcs["floor_area"] is None
    assert calcs["ceiling_area"] is None
    assert Decimal(calcs["perimeter"]) == Decimal("21.000")
    assert Decimal(calcs["total_wall_area"]) == Decimal("59.050")
    assert Decimal(calcs["total_deduction_area"]) == Decimal("1.800")
    assert Decimal(calcs["net_wall_area"]) == Decimal("57.250")


async def test_rectangle_room_without_walls_keeps_formula_totals(
    async_client: AsyncClient,
) -> None:
    token = await get_token(async_client, OWNER_USER)
    project = await create_project(async_client, token)
    room = await create_room(
        async_client,
        token,
        project["id"],
        {"name": "Pusty prostokąt", "length": "5.000", "width": "4.000", "height": "2.700"},
    )

    calcs = room["calculations"]
    assert calcs is not None
    assert calcs["wall_count"] == 0
    assert Decimal(calcs["total_wall_area"]) == Decimal("48.600")
    assert Decimal(calcs["perimeter"]) == Decimal("18.000")
    assert Decimal(calcs["floor_area"]) == Decimal("20.000")


async def test_room_list_surface_derived_totals(
    async_client: AsyncClient,
) -> None:
    token = await get_token(async_client, OWNER_USER)
    project = await create_project(async_client, token)
    room = await create_room(
        async_client,
        token,
        project["id"],
        {"name": "Salon", "length": "5.000", "width": "4.000", "height": "2.700"},
    )

    await async_client.post(generate_url(project["id"], room["id"]), headers=auth_header(token))

    listing = await async_client.get(
        f"/api/projects/{project['id']}/rooms",
        headers=auth_header(token),
    )
    assert listing.status_code == 200
    calcs = next(item["calculations"] for item in listing.json()["items"] if item["id"] == room["id"])
    assert calcs is not None
    assert calcs["wall_count"] == 4
    assert Decimal(calcs["total_wall_area"]) == Decimal("48.600")
    assert Decimal(calcs["wall_area_length"]) == Decimal("13.500")
    assert Decimal(calcs["wall_area_width"]) == Decimal("10.800")


# ---------------------------------------------------------------------------
# API integration: deterministic ordering
# ---------------------------------------------------------------------------


async def test_surfaces_ordered_by_position_and_null_last(
    async_client: AsyncClient,
) -> None:
    token = await get_token(async_client, OWNER_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"], {"name": "Pokój"})

    legacy = await create_wall(
        async_client, token, project["id"], room["id"], name="Starsza", width="3.000", height="2.500"
    )
    w2 = await create_wall(
        async_client, token, project["id"], room["id"], name="Druga", width="4.000", height="2.500", position=1
    )
    w0 = await create_wall(
        async_client, token, project["id"], room["id"], name="Pierwsza", width="5.000", height="2.500", position=0
    )

    listing = await async_client.get(
        walls_url(project["id"], room["id"]),
        headers=auth_header(token),
    )
    assert listing.status_code == 200
    ids = [item["id"] for item in listing.json()["items"]]
    # Positioned walls first (ascending), then legacy null-position wall.
    assert ids == [w0["id"], w2["id"], legacy["id"]]


async def test_generate_endpoint_response_shape(
    async_client: AsyncClient,
) -> None:
    token = await get_token(async_client, OWNER_USER)
    project = await create_project(async_client, token)
    room = await create_room(
        async_client,
        token,
        project["id"],
        {"name": "Pokój", "length": "5.000", "width": "4.000", "height": "2.700"},
    )

    response = await async_client.post(
        generate_url(project["id"], room["id"]),
        headers=auth_header(token),
    )
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert set(item) == {
        "id",
        "room_id",
        "name",
        "surface_type",
        "description",
        "position",
        "width",
        "height",
        "gross_area",
        "deduction_area",
        "net_area",
        "is_archived",
        "created_at",
        "updated_at",
    }