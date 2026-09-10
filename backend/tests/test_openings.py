from decimal import Decimal
import uuid

import pytest
from httpx import AsyncClient

from app.models.opening import OpeningType
from tests.conftest import make_telegram_init_data

VALID_USER = {
    "id": 111222333,
    "username": "opening_contractor",
    "first_name": "Opening",
    "last_name": "Contractor",
    "language_code": "pl",
}

OTHER_USER = {
    "id": 444555666,
    "username": "other_opening_contractor",
    "first_name": "Other",
    "last_name": "Contractor",
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
    name: str = "Projekt Otworów",
) -> dict:
    response = await async_client.post(
        "/api/projects",
        json={
            "name": name,
            "address": "ul. Otworowa 1",
            "city": "Warszawa",
            "postal_code": "00-001",
        },
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def create_room(
    async_client: AsyncClient,
    token: str,
    project_id: str,
    name: str = "Salon Główny",
    length: str | None = "5.000",
    width: str | None = "4.000",
    height: str | None = "2.700",
) -> dict:
    payload: dict = {"name": name}
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


async def create_surface(
    async_client: AsyncClient,
    token: str,
    project_id: str,
    room_id: str,
    name: str = "Ściana 1",
    surface_type: str = "WALL",
    width: str | None = "5.000",
    height: str | None = "2.700",
) -> dict:
    payload: dict = {
        "name": name,
        "surface_type": surface_type,
    }
    if width is not None:
        payload["width"] = width
    if height is not None:
        payload["height"] = height
    response = await async_client.post(
        f"/api/projects/{project_id}/rooms/{room_id}/surfaces",
        json=payload,
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


def openings_url(project_id: str, room_id: str, surface_id: str) -> str:
    return f"/api/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}/openings"


def opening_url(
    project_id: str, room_id: str, surface_id: str, opening_id: str
) -> str:
    return f"{openings_url(project_id, room_id, surface_id)}/{opening_id}"


@pytest.mark.asyncio
async def test_create_and_get_opening(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    surface = await create_surface(
        async_client, token, project["id"], room["id"], width="5.000", height="2.700"
    )

    create_res = await async_client.post(
        openings_url(project["id"], room["id"], surface["id"]),
        json={
            "opening_type": "DOOR",
            "name": "Drzwi pokojowe",
            "width": "0.900",
            "height": "2.000",
            "quantity": 1,
            "description": "Standardowe skrzydło drzwiowe",
        },
        headers=auth_header(token),
    )
    assert create_res.status_code == 201, create_res.text
    created = create_res.json()
    assert created["opening_type"] == "DOOR"
    assert created["name"] == "Drzwi pokojowe"
    assert created["width"] == "0.900"
    assert created["height"] == "2.000"
    assert created["quantity"] == 1
    assert created["single_area"] == "1.800"
    assert created["total_area"] == "1.800"
    assert created["is_archived"] is False
    assert created["surface_id"] == surface["id"]

    # Verify get opening
    get_res = await async_client.get(
        opening_url(project["id"], room["id"], surface["id"], created["id"]),
        headers=auth_header(token),
    )
    assert get_res.status_code == 200
    assert get_res.json() == created


@pytest.mark.asyncio
async def test_create_opening_quantity_multiplication(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    surface = await create_surface(
        async_client, token, project["id"], room["id"], width="6.000", height="2.700"
    )

    create_res = await async_client.post(
        openings_url(project["id"], room["id"], surface["id"]),
        json={
            "opening_type": "WINDOW",
            "name": "Okna bliźniacze",
            "width": "1.200",
            "height": "1.500",
            "quantity": 2,
        },
        headers=auth_header(token),
    )
    assert create_res.status_code == 201, create_res.text
    created = create_res.json()
    assert created["single_area"] == "1.800"
    assert created["total_area"] == "3.600"
    assert created["quantity"] == 2


@pytest.mark.asyncio
async def test_opening_cannot_be_attached_to_non_wall_surface(
    async_client: AsyncClient,
):
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])

    # Test on FLOOR surface
    floor_surf = await create_surface(
        async_client,
        token,
        project["id"],
        room["id"],
        name="Podłoga",
        surface_type="FLOOR",
        width="5.000",
        height="4.000",
    )
    res_floor = await async_client.post(
        openings_url(project["id"], room["id"], floor_surf["id"]),
        json={
            "opening_type": "OTHER",
            "width": "1.000",
            "height": "1.000",
        },
        headers=auth_header(token),
    )
    assert res_floor.status_code == 422
    assert "Openings can only be attached to WALL surfaces" in res_floor.text

    # Test on CEILING surface
    ceil_surf = await create_surface(
        async_client,
        token,
        project["id"],
        room["id"],
        name="Sufit",
        surface_type="CEILING",
        width="5.000",
        height="4.000",
    )
    res_ceil = await async_client.post(
        openings_url(project["id"], room["id"], ceil_surf["id"]),
        json={
            "opening_type": "OTHER",
            "width": "1.000",
            "height": "1.000",
        },
        headers=auth_header(token),
    )
    assert res_ceil.status_code == 422
    assert "Openings can only be attached to WALL surfaces" in res_ceil.text


@pytest.mark.asyncio
async def test_over_deduction_blocked_on_create_update_restore(
    async_client: AsyncClient,
):
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    # Wall gross area: 3.000 x 2.500 = 7.500 m²
    surface = await create_surface(
        async_client, token, project["id"], room["id"], width="3.000", height="2.500"
    )

    # 1. Attempt create opening exceeding gross area (8.000 m² > 7.500 m²)
    exceed_res = await async_client.post(
        openings_url(project["id"], room["id"], surface["id"]),
        json={
            "opening_type": "WINDOW",
            "width": "4.000",
            "height": "2.000",
        },
        headers=auth_header(token),
    )
    assert exceed_res.status_code == 422
    assert "would exceed wall gross area" in exceed_res.text

    # 2. Create valid opening 1 (5.000 m²)
    op1_res = await async_client.post(
        openings_url(project["id"], room["id"], surface["id"]),
        json={
            "opening_type": "WINDOW",
            "width": "2.500",
            "height": "2.000",
        },
        headers=auth_header(token),
    )
    assert op1_res.status_code == 201
    op1 = op1_res.json()

    # 3. Attempt create second opening (3.000 m² + 5.000 m² = 8.000 m² > 7.500 m²)
    op2_fail = await async_client.post(
        openings_url(project["id"], room["id"], surface["id"]),
        json={
            "opening_type": "DOOR",
            "width": "1.500",
            "height": "2.000",
        },
        headers=auth_header(token),
    )
    assert op2_fail.status_code == 422
    assert "would exceed wall gross area" in op2_fail.text

    # 4. Create second opening that fits (2.000 m²; total 7.000 m² <= 7.500 m²)
    op2_res = await async_client.post(
        openings_url(project["id"], room["id"], surface["id"]),
        json={
            "opening_type": "DOOR",
            "width": "1.000",
            "height": "2.000",
        },
        headers=auth_header(token),
    )
    assert op2_res.status_code == 201
    op2 = op2_res.json()

    # 5. Attempt update op2 so total exceeds (e.g. increase width to 1.500 -> 3.000 m² + 5.000 m² = 8.000 m²)
    update_fail = await async_client.patch(
        opening_url(project["id"], room["id"], surface["id"], op2["id"]),
        json={"width": "1.500"},
        headers=auth_header(token),
    )
    assert update_fail.status_code == 422
    assert "would exceed wall gross area" in update_fail.text

    # 6. Archive op1 (5.000 m² freed). Now active deductions = 2.000 m²
    archive_res = await async_client.post(
        f"{opening_url(project['id'], room['id'], surface['id'], op1['id'])}/archive",
        headers=auth_header(token),
    )
    assert archive_res.status_code == 200
    assert archive_res.json()["is_archived"] is True

    # 7. Create op3 (4.000 m²). Total active = 2.000 + 4.000 = 6.000 m² <= 7.500 m²
    op3_res = await async_client.post(
        openings_url(project["id"], room["id"], surface["id"]),
        json={
            "opening_type": "WINDOW",
            "width": "2.000",
            "height": "2.000",
        },
        headers=auth_header(token),
    )
    assert op3_res.status_code == 201

    # 8. Attempt restore op1 (5.000 m²). Total active would be 6.000 + 5.000 = 11.000 m² > 7.500 m²
    restore_fail = await async_client.post(
        f"{opening_url(project['id'], room['id'], surface['id'], op1['id'])}/restore",
        headers=auth_header(token),
    )
    assert restore_fail.status_code == 422
    assert "would exceed wall gross area" in restore_fail.text

    # 9. Attempt shrink surface dimensions smaller than current active deductions (6.000 m²)
    shrink_fail = await async_client.patch(
        f"/api/projects/{project['id']}/rooms/{room['id']}/surfaces/{surface['id']}",
        json={"width": "2.000", "height": "2.500"},  # gross 5.000 m² < 6.000 m²
        headers=auth_header(token),
    )
    assert shrink_fail.status_code == 422
    assert "smaller than current active opening deductions" in shrink_fail.text


@pytest.mark.asyncio
async def test_canonical_room_scenario_openings_and_net_areas(
    async_client: AsyncClient,
):
    """
    Verifies canonical acceptance room:
    Room: 5.000 x 4.000 x 2.700 m
    Floor: 20.000 m²
    Ceiling: 20.000 m²
    Wall 1: 5.000 x 2.700 = 13.500 m² gross
      - Door 0.900 x 2.000 = 1.800 m² deduction
      - Net area: 11.700 m²
    Wall 2: 4.000 x 2.700 = 10.800 m² gross
      - Window 1.500 x 1.400 = 2.100 m² deduction
      - Net area: 8.700 m²
    Wall 3: 5.000 x 2.700 = 13.500 m² gross (0 deductions, net 13.500 m²)
    Wall 4: 4.000 x 2.700 = 10.800 m² gross (0 deductions, net 10.800 m²)

    Totals:
    - total gross wall area: 48.600 m²
    - total opening deductions: 3.900 m²
    - total net wall area: 44.700 m²
    """
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token, name="Kanoniczny Obiekt")
    room = await create_room(
        async_client,
        token,
        project["id"],
        name="Kanoniczny Salon",
        length="5.000",
        width="4.000",
        height="2.700",
    )

    # Create Wall 1 (5.000 x 2.700)
    w1 = await create_surface(
        async_client,
        token,
        project["id"],
        room["id"],
        name="Ściana 1",
        surface_type="WALL",
        width="5.000",
        height="2.700",
    )
    # Add Door to Wall 1: 0.900 x 2.000
    door_res = await async_client.post(
        openings_url(project["id"], room["id"], w1["id"]),
        json={
            "opening_type": "DOOR",
            "name": "Drzwi wejściowe",
            "width": "0.900",
            "height": "2.000",
            "quantity": 1,
        },
        headers=auth_header(token),
    )
    assert door_res.status_code == 201

    # Create Wall 2 (4.000 x 2.700)
    w2 = await create_surface(
        async_client,
        token,
        project["id"],
        room["id"],
        name="Ściana 2",
        surface_type="WALL",
        width="4.000",
        height="2.700",
    )
    # Add Window to Wall 2: 1.500 x 1.400
    win_res = await async_client.post(
        openings_url(project["id"], room["id"], w2["id"]),
        json={
            "opening_type": "WINDOW",
            "name": "Okno salonowe",
            "width": "1.500",
            "height": "1.400",
            "quantity": 1,
        },
        headers=auth_header(token),
    )
    assert win_res.status_code == 201

    # Create Wall 3 (5.000 x 2.700, no openings)
    w3 = await create_surface(
        async_client,
        token,
        project["id"],
        room["id"],
        name="Ściana 3",
        surface_type="WALL",
        width="5.000",
        height="2.700",
    )

    # Create Wall 4 (4.000 x 2.700, no openings)
    w4 = await create_surface(
        async_client,
        token,
        project["id"],
        room["id"],
        name="Ściana 4",
        surface_type="WALL",
        width="4.000",
        height="2.700",
    )

    # Verify individual surface net areas via GET surface
    w1_read = await async_client.get(
        f"/api/projects/{project['id']}/rooms/{room['id']}/surfaces/{w1['id']}",
        headers=auth_header(token),
    )
    assert w1_read.status_code == 200
    w1_data = w1_read.json()
    assert w1_data["gross_area"] == "13.500"
    assert w1_data["deduction_area"] == "1.800"
    assert w1_data["net_area"] == "11.700"

    w2_read = await async_client.get(
        f"/api/projects/{project['id']}/rooms/{room['id']}/surfaces/{w2['id']}",
        headers=auth_header(token),
    )
    assert w2_read.status_code == 200
    w2_data = w2_read.json()
    assert w2_data["gross_area"] == "10.800"
    assert w2_data["deduction_area"] == "2.100"
    assert w2_data["net_area"] == "8.700"

    w3_read = await async_client.get(
        f"/api/projects/{project['id']}/rooms/{room['id']}/surfaces/{w3['id']}",
        headers=auth_header(token),
    )
    assert w3_read.status_code == 200
    w3_data = w3_read.json()
    assert w3_data["gross_area"] == "13.500"
    assert w3_data["deduction_area"] == "0.000"
    assert w3_data["net_area"] == "13.500"

    w4_read = await async_client.get(
        f"/api/projects/{project['id']}/rooms/{room['id']}/surfaces/{w4['id']}",
        headers=auth_header(token),
    )
    assert w4_read.status_code == 200
    w4_data = w4_read.json()
    assert w4_data["gross_area"] == "10.800"
    assert w4_data["deduction_area"] == "0.000"
    assert w4_data["net_area"] == "10.800"

    # Verify list surfaces includes computed deductions and net areas
    list_surf_res = await async_client.get(
        f"/api/projects/{project['id']}/rooms/{room['id']}/surfaces",
        headers=auth_header(token),
    )
    assert list_surf_res.status_code == 200
    surfs_by_name = {s["name"]: s for s in list_surf_res.json()["items"]}
    assert surfs_by_name["Ściana 1"]["net_area"] == "11.700"
    assert surfs_by_name["Ściana 2"]["net_area"] == "8.700"
    assert surfs_by_name["Ściana 3"]["net_area"] == "13.500"
    assert surfs_by_name["Ściana 4"]["net_area"] == "10.800"

    # Verify room calculations on GET room
    room_get = await async_client.get(
        f"/api/projects/{project['id']}/rooms/{room['id']}",
        headers=auth_header(token),
    )
    assert room_get.status_code == 200
    calcs = room_get.json()["calculations"]
    assert calcs is not None
    assert calcs["floor_area"] == "20.000"
    assert calcs["ceiling_area"] == "20.000"
    assert calcs["total_wall_area"] == "48.600"
    assert calcs["wall_area_length"] == "13.500"
    assert calcs["wall_area_width"] == "10.800"
    assert calcs["perimeter"] == "18.000"
    assert calcs["total_deduction_area"] == "3.900"
    assert calcs["net_wall_area"] == "44.700"

    # Verify room calculations on list_rooms
    rooms_list = await async_client.get(
        f"/api/projects/{project['id']}/rooms",
        headers=auth_header(token),
    )
    assert rooms_list.status_code == 200
    listed_room = rooms_list.json()["items"][0]
    listed_calcs = listed_room["calculations"]
    assert listed_calcs["total_wall_area"] == "48.600"
    assert listed_calcs["total_deduction_area"] == "3.900"
    assert listed_calcs["net_wall_area"] == "44.700"


@pytest.mark.asyncio
async def test_owner_isolation_and_cross_tenant_access_denied(
    async_client: AsyncClient,
):
    token_a = await get_token(async_client, VALID_USER)
    token_b = await get_token(async_client, OTHER_USER)

    proj_a = await create_project(async_client, token_a, name="Projekt A")
    room_a = await create_room(async_client, token_a, proj_a["id"], name="Salon A")
    surf_a = await create_surface(
        async_client, token_a, proj_a["id"], room_a["id"], name="Ściana A"
    )

    # User A creates opening
    op_res = await async_client.post(
        openings_url(proj_a["id"], room_a["id"], surf_a["id"]),
        json={
            "opening_type": "DOOR",
            "name": "Drzwi A",
            "width": "0.900",
            "height": "2.000",
        },
        headers=auth_header(token_a),
    )
    assert op_res.status_code == 201
    opening_id = op_res.json()["id"]

    # User B cannot list openings of User A
    list_b = await async_client.get(
        openings_url(proj_a["id"], room_a["id"], surf_a["id"]),
        headers=auth_header(token_b),
    )
    assert list_b.status_code == 404

    # User B cannot get opening of User A
    get_b = await async_client.get(
        opening_url(proj_a["id"], room_a["id"], surf_a["id"], opening_id),
        headers=auth_header(token_b),
    )
    assert get_b.status_code == 404

    # User B cannot update opening of User A
    patch_b = await async_client.patch(
        opening_url(proj_a["id"], room_a["id"], surf_a["id"], opening_id),
        json={"name": "Przejęte Drzwi"},
        headers=auth_header(token_b),
    )
    assert patch_b.status_code == 404

    # User B cannot archive opening of User A
    arch_b = await async_client.post(
        f"{opening_url(proj_a['id'], room_a['id'], surf_a['id'], opening_id)}/archive",
        headers=auth_header(token_b),
    )
    assert arch_b.status_code == 404

    # User B cannot restore opening of User A
    rest_b = await async_client.post(
        f"{opening_url(proj_a['id'], room_a['id'], surf_a['id'], opening_id)}/restore",
        headers=auth_header(token_b),
    )
    assert rest_b.status_code == 404

    # User B cannot create opening inside User A's surface
    create_b = await async_client.post(
        openings_url(proj_a["id"], room_a["id"], surf_a["id"]),
        json={
            "opening_type": "WINDOW",
            "width": "1.000",
            "height": "1.000",
        },
        headers=auth_header(token_b),
    )
    assert create_b.status_code == 404


@pytest.mark.asyncio
async def test_mismatched_and_nonexistent_ids_return_404(
    async_client: AsyncClient,
):
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    surface = await create_surface(async_client, token, project["id"], room["id"])

    random_id = str(uuid.uuid4())

    # Random project_id
    res = await async_client.get(
        openings_url(random_id, room["id"], surface["id"]),
        headers=auth_header(token),
    )
    assert res.status_code == 404

    # Random room_id
    res = await async_client.get(
        openings_url(project["id"], random_id, surface["id"]),
        headers=auth_header(token),
    )
    assert res.status_code == 404

    # Random surface_id
    res = await async_client.get(
        openings_url(project["id"], room["id"], random_id),
        headers=auth_header(token),
    )
    assert res.status_code == 404

    # Random opening_id
    res = await async_client.get(
        opening_url(project["id"], room["id"], surface["id"], random_id),
        headers=auth_header(token),
    )
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# Edge Cases: Archive / Restore scenarios & Validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_archive_restore_scenario_a_deduction_and_net_area_toggle(
    async_client: AsyncClient,
):
    """Scenario A:
    - create valid Opening
    - archive it
    - deduction disappears, net area increases
    - restore it
    - deduction returns, net area returns to original value
    """
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    surface = await create_surface(
        async_client, token, project["id"], room["id"], width="5.000", height="2.700"
    )

    # 1. Create valid opening (0.900 x 2.000 = 1.800 m²)
    op_res = await async_client.post(
        openings_url(project["id"], room["id"], surface["id"]),
        json={"opening_type": "DOOR", "width": "0.900", "height": "2.000"},
        headers=auth_header(token),
    )
    assert op_res.status_code == 201
    opening_id = op_res.json()["id"]

    # Check wall deduction and net area
    w_res1 = await async_client.get(
        f"/api/projects/{project['id']}/rooms/{room['id']}/surfaces/{surface['id']}",
        headers=auth_header(token),
    )
    assert w_res1.json()["deduction_area"] == "1.800"
    assert w_res1.json()["net_area"] == "11.700"

    # 2. Archive opening
    arch_res = await async_client.post(
        f"{opening_url(project['id'], room['id'], surface['id'], opening_id)}/archive",
        headers=auth_header(token),
    )
    assert arch_res.status_code == 200

    # Deduction disappears, net area increases to gross area
    w_res2 = await async_client.get(
        f"/api/projects/{project['id']}/rooms/{room['id']}/surfaces/{surface['id']}",
        headers=auth_header(token),
    )
    assert w_res2.json()["deduction_area"] == "0.000"
    assert w_res2.json()["net_area"] == "13.500"

    # 3. Restore opening
    rest_res = await async_client.post(
        f"{opening_url(project['id'], room['id'], surface['id'], opening_id)}/restore",
        headers=auth_header(token),
    )
    assert rest_res.status_code == 200

    # Deduction returns, net area returns to original value
    w_res3 = await async_client.get(
        f"/api/projects/{project['id']}/rooms/{room['id']}/surfaces/{surface['id']}",
        headers=auth_header(token),
    )
    assert w_res3.json()["deduction_area"] == "1.800"
    assert w_res3.json()["net_area"] == "11.700"


@pytest.mark.asyncio
async def test_archive_restore_scenario_b_restore_blocked_if_wall_shrunk(
    async_client: AsyncClient,
):
    """Scenario B:
    - create Opening
    - archive it
    - reduce wall dimensions
    - attempt restore
    - restore must fail if it would cause over-deduction
    - Opening must remain archived after failed restore
    """
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    # Wall gross area: 3.000 x 2.000 = 6.000 m²
    surface = await create_surface(
        async_client, token, project["id"], room["id"], width="3.000", height="2.000"
    )

    # 1. Create opening: 2.000 x 2.000 = 4.000 m²
    op_res = await async_client.post(
        openings_url(project["id"], room["id"], surface["id"]),
        json={"opening_type": "WINDOW", "width": "2.000", "height": "2.000"},
        headers=auth_header(token),
    )
    assert op_res.status_code == 201
    opening_id = op_res.json()["id"]

    # 2. Archive opening
    await async_client.post(
        f"{opening_url(project['id'], room['id'], surface['id'], opening_id)}/archive",
        headers=auth_header(token),
    )

    # 3. Reduce wall dimensions: 1.500 x 2.000 = 3.000 m²
    shrink_res = await async_client.patch(
        f"/api/projects/{project['id']}/rooms/{room['id']}/surfaces/{surface['id']}",
        json={"width": "1.500"},
        headers=auth_header(token),
    )
    assert shrink_res.status_code == 200

    # 4. Attempt restore (4.000 m² > 3.000 m²) -> must fail with 422
    rest_res = await async_client.post(
        f"{opening_url(project['id'], room['id'], surface['id'], opening_id)}/restore",
        headers=auth_header(token),
    )
    assert rest_res.status_code == 422
    assert "would exceed wall gross area" in rest_res.text

    # 5. Verify opening remains archived
    get_op = await async_client.get(
        opening_url(project["id"], room["id"], surface["id"], opening_id),
        headers=auth_header(token),
    )
    assert get_op.status_code == 200
    assert get_op.json()["is_archived"] is True


@pytest.mark.asyncio
async def test_archive_restore_scenario_c_multiple_openings_archive_one(
    async_client: AsyncClient,
):
    """Scenario C:
    - multiple active Openings
    - archive one
    - aggregate deduction updates correctly
    """
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    # Wall gross: 5.000 x 2.500 = 12.500 m²
    surface = await create_surface(
        async_client, token, project["id"], room["id"], width="5.000", height="2.500"
    )

    # Op 1: 1.000 x 2.000 = 2.000 m²
    op1 = (
        await async_client.post(
            openings_url(project["id"], room["id"], surface["id"]),
            json={"opening_type": "DOOR", "width": "1.000", "height": "2.000"},
            headers=auth_header(token),
        )
    ).json()

    # Op 2: 1.500 x 2.000 = 3.000 m²
    op2 = (
        await async_client.post(
            openings_url(project["id"], room["id"], surface["id"]),
            json={"opening_type": "WINDOW", "width": "1.500", "height": "2.000"},
            headers=auth_header(token),
        )
    ).json()

    # Op 3: 1.000 x 1.500 = 1.500 m²
    op3 = (
        await async_client.post(
            openings_url(project["id"], room["id"], surface["id"]),
            json={"opening_type": "OTHER", "width": "1.000", "height": "1.500"},
            headers=auth_header(token),
        )
    ).json()

    # Total deduction: 2.000 + 3.000 + 1.500 = 6.500 m²; net = 6.000 m²
    surf_res = await async_client.get(
        f"/api/projects/{project['id']}/rooms/{room['id']}/surfaces/{surface['id']}",
        headers=auth_header(token),
    )
    assert surf_res.json()["deduction_area"] == "6.500"
    assert surf_res.json()["net_area"] == "6.000"

    # Archive Op 2 (3.000 m²)
    await async_client.post(
        f"{opening_url(project['id'], room['id'], surface['id'], op2['id'])}/archive",
        headers=auth_header(token),
    )

    # Deduction becomes 3.500 m², net becomes 9.000 m²
    surf_after = await async_client.get(
        f"/api/projects/{project['id']}/rooms/{room['id']}/surfaces/{surface['id']}",
        headers=auth_header(token),
    )
    assert surf_after.json()["deduction_area"] == "3.500"
    assert surf_after.json()["net_area"] == "9.000"


@pytest.mark.asyncio
async def test_net_area_can_equal_zero_when_deductions_equal_gross(
    async_client: AsyncClient,
):
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    # Wall gross: 2.000 x 2.000 = 4.000 m²
    surface = await create_surface(
        async_client, token, project["id"], room["id"], width="2.000", height="2.000"
    )

    # Opening exact same size: 2.000 x 2.000 = 4.000 m²
    op_res = await async_client.post(
        openings_url(project["id"], room["id"], surface["id"]),
        json={"opening_type": "WINDOW", "width": "2.000", "height": "2.000"},
        headers=auth_header(token),
    )
    assert op_res.status_code == 201

    surf_res = await async_client.get(
        f"/api/projects/{project['id']}/rooms/{room['id']}/surfaces/{surface['id']}",
        headers=auth_header(token),
    )
    data = surf_res.json()
    assert data["gross_area"] == "4.000"
    assert data["deduction_area"] == "4.000"
    assert data["net_area"] == "0.000"


@pytest.mark.parametrize(
    ("payload", "error_field"),
    [
        ({"opening_type": "DOOR", "width": "0", "height": "2.000"}, "width"),
        ({"opening_type": "DOOR", "width": "-1.000", "height": "2.000"}, "width"),
        ({"opening_type": "DOOR", "width": "1.000", "height": "0"}, "height"),
        ({"opening_type": "DOOR", "width": "1.000", "height": "-2.000"}, "height"),
        ({"opening_type": "DOOR", "width": "1.000", "height": "2.000", "quantity": 0}, "quantity"),
        ({"opening_type": "DOOR", "width": "1.000", "height": "2.000", "quantity": -1}, "quantity"),
        ({"opening_type": "DOOR", "width": "1.1234", "height": "2.000"}, "width"),  # > 3 decimals
        ({"opening_type": "DOOR", "width": "1.000", "height": "2.1234"}, "height"),  # > 3 decimals
    ],
)
@pytest.mark.asyncio
async def test_opening_dimension_and_quantity_validation_rejections(
    async_client: AsyncClient,
    payload: dict,
    error_field: str,
):
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    surface = await create_surface(
        async_client, token, project["id"], room["id"], width="5.000", height="2.700"
    )

    res = await async_client.post(
        openings_url(project["id"], room["id"], surface["id"]),
        json=payload,
        headers=auth_header(token),
    )
    assert res.status_code == 422
    errors = res.json().get("detail", [])
    assert any(error_field in e.get("loc", []) for e in errors)


@pytest.mark.asyncio
async def test_rejected_write_leaves_persisted_data_unchanged(
    async_client: AsyncClient,
):
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    surface = await create_surface(
        async_client, token, project["id"], room["id"], width="5.000", height="2.700"
    )

    # Valid opening: 0.900 x 2.000 = 1.800 m²
    op = (
        await async_client.post(
            openings_url(project["id"], room["id"], surface["id"]),
            json={"opening_type": "DOOR", "width": "0.900", "height": "2.000"},
            headers=auth_header(token),
        )
    ).json()

    # Attempt rejected update: width 10.000 x height 2.000 = 20.000 m² > 13.500 m²
    fail_res = await async_client.patch(
        opening_url(project["id"], room["id"], surface["id"], op["id"]),
        json={"width": "10.000"},
        headers=auth_header(token),
    )
    assert fail_res.status_code == 422

    # Verify persisted opening unchanged
    get_op = await async_client.get(
        opening_url(project["id"], room["id"], surface["id"], op["id"]),
        headers=auth_header(token),
    )
    assert get_op.json()["width"] == "0.900"
    assert get_op.json()["height"] == "2.000"

    # Verify persisted wall surface deductions unchanged
    get_surf = await async_client.get(
        f"/api/projects/{project['id']}/rooms/{room['id']}/surfaces/{surface['id']}",
        headers=auth_header(token),
    )
    assert get_surf.json()["deduction_area"] == "1.800"
    assert get_surf.json()["net_area"] == "11.700"


# ---------------------------------------------------------------------------
# Unit tests: Pure domain rules (room_geometry)
# ---------------------------------------------------------------------------


def test_domain_calculate_opening_area():
    from app.domain.rules.room_geometry import calculate_opening_area

    res = calculate_opening_area(Decimal("0.900"), Decimal("2.000"), quantity=1)
    assert res is not None
    assert res.single_area == Decimal("1.800")
    assert res.total_area == Decimal("1.800")

    res_multi = calculate_opening_area(Decimal("1.200"), Decimal("1.500"), quantity=3)
    assert res_multi is not None
    assert res_multi.single_area == Decimal("1.800")
    assert res_multi.total_area == Decimal("5.400")

    assert calculate_opening_area(None, Decimal("2.000")) is None
    assert calculate_opening_area(Decimal("1.000"), None) is None
    assert calculate_opening_area(Decimal("0.000"), Decimal("2.000")) is None
    assert calculate_opening_area(Decimal("-1.000"), Decimal("2.000")) is None
    assert calculate_opening_area(Decimal("1.000"), Decimal("2.000"), quantity=0) is None


def test_domain_calculate_wall_net_area():
    from app.domain.rules.room_geometry import calculate_wall_net_area

    assert calculate_wall_net_area(Decimal("13.500"), Decimal("1.800")) == Decimal("11.700")
    assert calculate_wall_net_area(Decimal("10.800"), Decimal("0.000")) == Decimal("10.800")
    assert calculate_wall_net_area(Decimal("10.800"), None) == Decimal("10.800")
    assert calculate_wall_net_area(None, Decimal("1.800")) is None

    with pytest.raises(ValueError, match="cannot exceed wall gross area"):
        calculate_wall_net_area(Decimal("10.000"), Decimal("12.000"))


def test_domain_calculate_room_aggregate_totals():
    from app.domain.rules.room_geometry import (
        calculate_room_aggregate_totals,
        calculate_room_geometry,
    )

    geom = calculate_room_geometry(Decimal("5.000"), Decimal("4.000"), Decimal("2.700"))
    assert geom is not None

    totals = calculate_room_aggregate_totals(geom, Decimal("3.900"))
    assert totals is not None
    assert totals.floor_gross_area == Decimal("20.000")
    assert totals.ceiling_gross_area == Decimal("20.000")
    assert totals.total_wall_gross_area == Decimal("48.600")
    assert totals.total_opening_deduction_area == Decimal("3.900")
    assert totals.total_wall_net_area == Decimal("44.700")
    assert totals.perimeter == Decimal("18.000")

    with pytest.raises(ValueError, match="cannot exceed room total wall area"):
        calculate_room_aggregate_totals(geom, Decimal("50.000"))
