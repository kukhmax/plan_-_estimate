"""Stage 5F: Opening Reveals / Ościeża — focused backend tests."""
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.domain.rules.room_geometry import calculate_reveal
from tests.conftest import make_telegram_init_data

VALID_USER = {
    "id": 991122334,
    "username": "reveal_contractor",
    "first_name": "Reveal",
    "last_name": "Contractor",
    "language_code": "pl",
}


async def get_token(async_client: AsyncClient) -> str:
    resp = await async_client.post(
        "/api/auth/telegram",
        json={"init_data": make_telegram_init_data(VALID_USER)},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def setup_wall(async_client: AsyncClient, token: str) -> tuple[str, str, str]:
    """Create project → room → WALL surface. Returns (project_id, room_id, surface_id)."""
    proj = await async_client.post(
        "/api/projects",
        json={"name": "Reveal Proj", "address": "ul. A 1", "city": "Kraków", "postal_code": "31-001"},
        headers=auth(token),
    )
    assert proj.status_code == 201
    project_id = proj.json()["id"]

    room = await async_client.post(
        f"/api/projects/{project_id}/rooms",
        json={"name": "Salon", "length": "5.000", "width": "4.000", "height": "2.700"},
        headers=auth(token),
    )
    assert room.status_code == 201
    room_id = room.json()["id"]

    surface = await async_client.post(
        f"/api/projects/{project_id}/rooms/{room_id}/surfaces",
        json={"name": "Ściana A", "surface_type": "WALL", "width": "5.000", "height": "2.700"},
        headers=auth(token),
    )
    assert surface.status_code == 201
    surface_id = surface.json()["id"]

    return project_id, room_id, surface_id


def openings_url(p: str, r: str, s: str) -> str:
    return f"/api/projects/{p}/rooms/{r}/surfaces/{s}/openings"


def opening_url(p: str, r: str, s: str, o: str) -> str:
    return f"{openings_url(p, r, s)}/{o}"


# ---------------------------------------------------------------------------
# Unit tests for calculate_reveal()
# ---------------------------------------------------------------------------

class TestCalculateReveal:
    def test_three_side_window_quantity_1(self):
        # width=1.50, height=1.40, depth=0.30, left+right+top
        result = calculate_reveal(
            Decimal("1.500"), Decimal("1.400"), Decimal("0.300"),
            left=True, right=True, top=True, bottom=False, quantity=1,
        )
        assert result is not None
        # length = 1.40 + 1.40 + 1.50 = 4.30
        assert result.single_length == Decimal("4.300")
        # area = 4.30 * 0.30 = 1.29
        assert result.single_area == Decimal("1.290")
        assert result.total_length == Decimal("4.300")
        assert result.total_area == Decimal("1.290")

    def test_three_side_door(self):
        # width=0.90, height=2.00, depth=0.15, left+right+top
        result = calculate_reveal(
            Decimal("0.900"), Decimal("2.000"), Decimal("0.150"),
            left=True, right=True, top=True, bottom=False, quantity=1,
        )
        assert result is not None
        # length = 2.00 + 2.00 + 0.90 = 4.90
        assert result.single_length == Decimal("4.900")
        # area = 4.90 * 0.15 = 0.735
        assert result.single_area == Decimal("0.735")

    def test_all_four_sides(self):
        result = calculate_reveal(
            Decimal("1.200"), Decimal("1.500"), Decimal("0.200"),
            left=True, right=True, top=True, bottom=True, quantity=1,
        )
        assert result is not None
        # length = 1.50 + 1.50 + 1.20 + 1.20 = 5.40
        assert result.single_length == Decimal("5.400")

    def test_quantity_multiplies_totals(self):
        result = calculate_reveal(
            Decimal("1.500"), Decimal("1.400"), Decimal("0.300"),
            left=True, right=True, top=True, bottom=False, quantity=3,
        )
        assert result is not None
        assert result.single_length == Decimal("4.300")
        assert result.total_length == Decimal("12.900")   # 4.30 * 3
        assert result.single_area == Decimal("1.290")
        assert result.total_area == Decimal("3.870")      # 1.29 * 3

    def test_depth_precision(self):
        result = calculate_reveal(
            Decimal("1.000"), Decimal("1.000"), Decimal("0.135"),
            left=True, right=True, top=False, bottom=False, quantity=1,
        )
        assert result is not None
        # length = 1.000 + 1.000 = 2.000
        # area = 2.000 * 0.135 = 0.270
        assert result.single_area == Decimal("0.270")

    def test_disabled_reveals_returns_none_for_zero_sides(self):
        result = calculate_reveal(
            Decimal("1.000"), Decimal("1.000"), Decimal("0.300"),
            left=False, right=False, top=False, bottom=False, quantity=1,
        )
        assert result is None

    def test_zero_depth_returns_none(self):
        assert calculate_reveal(
            Decimal("1.000"), Decimal("1.000"), Decimal("0.000"),
            left=True, right=True, top=True, bottom=False, quantity=1,
        ) is None

    def test_negative_dimensions_return_none(self):
        assert calculate_reveal(
            Decimal("-1.000"), Decimal("1.000"), Decimal("0.300"),
            left=True, right=True, top=True, bottom=False, quantity=1,
        ) is None


# ---------------------------------------------------------------------------
# Integration tests via HTTP
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_disabled_reveals_default(async_client: AsyncClient):
    """New opening has reveal_enabled=False and null totals."""
    token = await get_token(async_client)
    p, r, s = await setup_wall(async_client, token)

    resp = await async_client.post(
        openings_url(p, r, s),
        json={"opening_type": "WINDOW", "width": "1.500", "height": "1.400", "quantity": 1},
        headers=auth(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["reveal_enabled"] is False
    assert data["reveal_depth"] is None
    assert data["reveal_total_length"] is None
    assert data["reveal_total_area"] is None


@pytest.mark.asyncio
async def test_three_side_window_reveal(async_client: AsyncClient):
    token = await get_token(async_client)
    p, r, s = await setup_wall(async_client, token)

    resp = await async_client.post(
        openings_url(p, r, s),
        json={
            "opening_type": "WINDOW",
            "width": "1.500",
            "height": "1.400",
            "quantity": 1,
            "reveal_enabled": True,
            "reveal_depth": "0.300",
            "reveal_left": True,
            "reveal_right": True,
            "reveal_top": True,
            "reveal_bottom": False,
        },
        headers=auth(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["reveal_enabled"] is True
    assert data["reveal_total_length"] == "4.300"
    assert data["reveal_total_area"] == "1.290"


@pytest.mark.asyncio
async def test_three_side_door_reveal(async_client: AsyncClient):
    token = await get_token(async_client)
    p, r, s = await setup_wall(async_client, token)

    resp = await async_client.post(
        openings_url(p, r, s),
        json={
            "opening_type": "DOOR",
            "width": "0.900",
            "height": "2.000",
            "quantity": 1,
            "reveal_enabled": True,
            "reveal_depth": "0.150",
        },
        headers=auth(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["reveal_total_length"] == "4.900"
    assert data["reveal_total_area"] == "0.735"


@pytest.mark.asyncio
async def test_optional_bottom_reveal(async_client: AsyncClient):
    """All four sides enabled."""
    token = await get_token(async_client)
    p, r, s = await setup_wall(async_client, token)

    resp = await async_client.post(
        openings_url(p, r, s),
        json={
            "opening_type": "WINDOW",
            "width": "1.200",
            "height": "1.500",
            "quantity": 1,
            "reveal_enabled": True,
            "reveal_depth": "0.200",
            "reveal_left": True,
            "reveal_right": True,
            "reveal_top": True,
            "reveal_bottom": True,
        },
        headers=auth(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["reveal_total_length"] == "5.400"


@pytest.mark.asyncio
async def test_quantity_multiplies_reveal_totals(async_client: AsyncClient):
    token = await get_token(async_client)
    p, r, s = await setup_wall(async_client, token)

    surface = await async_client.post(
        f"/api/projects/{p}/rooms/{r}/surfaces",
        json={"name": "Ściana B", "surface_type": "WALL", "width": "10.000", "height": "2.700"},
        headers=auth(token),
    )
    s2 = surface.json()["id"]

    resp = await async_client.post(
        openings_url(p, r, s2),
        json={
            "opening_type": "WINDOW",
            "width": "1.500",
            "height": "1.400",
            "quantity": 3,
            "reveal_enabled": True,
            "reveal_depth": "0.300",
        },
        headers=auth(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["reveal_total_length"] == "12.900"
    assert data["reveal_total_area"] == "3.870"


@pytest.mark.asyncio
async def test_zero_depth_rejected(async_client: AsyncClient):
    """reveal_depth > 0 is required; 0 should be rejected by field validation."""
    token = await get_token(async_client)
    p, r, s = await setup_wall(async_client, token)

    resp = await async_client.post(
        openings_url(p, r, s),
        json={
            "opening_type": "WINDOW",
            "width": "1.000",
            "height": "1.000",
            "reveal_enabled": True,
            "reveal_depth": "0.000",
        },
        headers=auth(token),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_reveal_enabled_without_depth_rejected(async_client: AsyncClient):
    token = await get_token(async_client)
    p, r, s = await setup_wall(async_client, token)

    resp = await async_client.post(
        openings_url(p, r, s),
        json={
            "opening_type": "WINDOW",
            "width": "1.000",
            "height": "1.000",
            "reveal_enabled": True,
        },
        headers=auth(token),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_other_type_reveal_rejected(async_client: AsyncClient):
    """OTHER opening type cannot have reveal_enabled=True."""
    token = await get_token(async_client)
    p, r, s = await setup_wall(async_client, token)

    resp = await async_client.post(
        openings_url(p, r, s),
        json={
            "opening_type": "OTHER",
            "width": "0.600",
            "height": "0.600",
            "reveal_enabled": True,
            "reveal_depth": "0.150",
        },
        headers=auth(token),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_update_opening_adds_reveal(async_client: AsyncClient):
    """PATCH can enable reveals on an existing opening."""
    token = await get_token(async_client)
    p, r, s = await setup_wall(async_client, token)

    create_resp = await async_client.post(
        openings_url(p, r, s),
        json={"opening_type": "DOOR", "width": "0.900", "height": "2.000"},
        headers=auth(token),
    )
    assert create_resp.status_code == 201
    o_id = create_resp.json()["id"]

    patch_resp = await async_client.patch(
        opening_url(p, r, s, o_id),
        json={"reveal_enabled": True, "reveal_depth": "0.150"},
        headers=auth(token),
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["reveal_enabled"] is True
    assert data["reveal_total_length"] == "4.900"


@pytest.mark.asyncio
async def test_archive_restore_reveal_not_counted_when_archived(async_client: AsyncClient):
    """Archived opening reveals must not appear in room aggregates."""
    token = await get_token(async_client)
    p, r, s = await setup_wall(async_client, token)

    create_resp = await async_client.post(
        openings_url(p, r, s),
        json={
            "opening_type": "WINDOW",
            "width": "1.500",
            "height": "1.400",
            "reveal_enabled": True,
            "reveal_depth": "0.300",
        },
        headers=auth(token),
    )
    o_id = create_resp.json()["id"]

    archive_resp = await async_client.post(
        f"{opening_url(p, r, s, o_id)}/archive",
        headers=auth(token),
    )
    assert archive_resp.status_code == 200

    room_resp = await async_client.get(
        f"/api/projects/{p}/rooms/{r}",
        headers=auth(token),
    )
    assert room_resp.status_code == 200
    calc = room_resp.json()["calculations"]
    assert calc.get("window_reveal_total_length") is None

    restore_resp = await async_client.post(
        f"{opening_url(p, r, s, o_id)}/restore",
        headers=auth(token),
    )
    assert restore_resp.status_code == 200

    room_resp2 = await async_client.get(
        f"/api/projects/{p}/rooms/{r}",
        headers=auth(token),
    )
    calc2 = room_resp2.json()["calculations"]
    assert calc2["window_reveal_total_length"] == "4.300"


@pytest.mark.asyncio
async def test_room_window_reveal_aggregate(async_client: AsyncClient):
    """Two windows with reveals sum correctly in room calculations."""
    token = await get_token(async_client)
    p, r, s = await setup_wall(async_client, token)

    surface2 = await async_client.post(
        f"/api/projects/{p}/rooms/{r}/surfaces",
        json={"name": "Ściana B", "surface_type": "WALL", "width": "4.000", "height": "2.700"},
        headers=auth(token),
    )
    s2 = surface2.json()["id"]

    for surface_id in [s, s2]:
        resp = await async_client.post(
            openings_url(p, r, surface_id),
            json={
                "opening_type": "WINDOW",
                "width": "1.500",
                "height": "1.400",
                "quantity": 1,
                "reveal_enabled": True,
                "reveal_depth": "0.300",
            },
            headers=auth(token),
        )
        assert resp.status_code == 201

    room_resp = await async_client.get(f"/api/projects/{p}/rooms/{r}", headers=auth(token))
    calc = room_resp.json()["calculations"]
    # Each window: length=4.300, area=1.290; two windows: 8.600 / 2.580
    assert calc["window_reveal_total_length"] == "8.600"
    assert calc["window_reveal_total_area"] == "2.580"
    assert calc.get("door_reveal_total_length") is None


@pytest.mark.asyncio
async def test_room_door_reveal_aggregate(async_client: AsyncClient):
    token = await get_token(async_client)
    p, r, s = await setup_wall(async_client, token)

    await async_client.post(
        openings_url(p, r, s),
        json={
            "opening_type": "DOOR",
            "width": "0.900",
            "height": "2.000",
            "quantity": 1,
            "reveal_enabled": True,
            "reveal_depth": "0.150",
        },
        headers=auth(token),
    )

    room_resp = await async_client.get(f"/api/projects/{p}/rooms/{r}", headers=auth(token))
    calc = room_resp.json()["calculations"]
    assert calc["door_reveal_total_length"] == "4.900"
    assert calc["door_reveal_total_area"] == "0.735"
    assert calc.get("window_reveal_total_length") is None


@pytest.mark.asyncio
async def test_room_combined_reveal_aggregate(async_client: AsyncClient):
    """Both window and door reveals produce combined totals."""
    token = await get_token(async_client)
    p, r, s = await setup_wall(async_client, token)

    surface2 = await async_client.post(
        f"/api/projects/{p}/rooms/{r}/surfaces",
        json={"name": "Ściana B", "surface_type": "WALL", "width": "4.000", "height": "2.700"},
        headers=auth(token),
    )
    s2 = surface2.json()["id"]

    await async_client.post(
        openings_url(p, r, s),
        json={"opening_type": "WINDOW", "width": "1.500", "height": "1.400",
              "reveal_enabled": True, "reveal_depth": "0.300"},
        headers=auth(token),
    )
    await async_client.post(
        openings_url(p, r, s2),
        json={"opening_type": "DOOR", "width": "0.900", "height": "2.000",
              "reveal_enabled": True, "reveal_depth": "0.150"},
        headers=auth(token),
    )

    room_resp = await async_client.get(f"/api/projects/{p}/rooms/{r}", headers=auth(token))
    calc = room_resp.json()["calculations"]
    # window: 4.300 + door: 4.900 = 9.200
    assert calc["reveal_total_length"] == "9.200"
    # window: 1.290 + door: 0.735 = 2.025
    assert calc["reveal_total_area"] == "2.025"


@pytest.mark.asyncio
async def test_reveal_does_not_alter_wall_deduction_or_net_area(async_client: AsyncClient):
    """Enabling reveals must not change single_area, total_area, or room net_wall_area."""
    token = await get_token(async_client)
    p, r, s = await setup_wall(async_client, token)

    no_reveal = await async_client.post(
        openings_url(p, r, s),
        json={"opening_type": "WINDOW", "width": "1.500", "height": "1.400"},
        headers=auth(token),
    )
    assert no_reveal.status_code == 201
    opening_id = no_reveal.json()["id"]
    assert no_reveal.json()["single_area"] == "2.100"
    assert no_reveal.json()["total_area"] == "2.100"

    patch_resp = await async_client.patch(
        opening_url(p, r, s, opening_id),
        json={"reveal_enabled": True, "reveal_depth": "0.300"},
        headers=auth(token),
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["single_area"] == "2.100"
    assert patch_resp.json()["total_area"] == "2.100"

    room_resp = await async_client.get(f"/api/projects/{p}/rooms/{r}", headers=auth(token))
    calc = room_resp.json()["calculations"]
    # net_wall_area = gross - deduction; deduction is 2.100 regardless of reveal
    gross = float(calc["total_wall_area"])
    deduction = float(calc["total_deduction_area"])
    net = float(calc["net_wall_area"])
    assert abs(gross - deduction - net) < 0.001
    # Reveal area must not be deducted
    reveal_area = float(calc["window_reveal_total_area"])
    assert deduction == pytest.approx(2.100, abs=0.001)
    assert reveal_area == pytest.approx(1.290, abs=0.001)
