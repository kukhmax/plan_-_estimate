import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import make_telegram_init_data

VALID_USER = {
    "id": 888111222,
    "username": "segment_contractor",
    "first_name": "Segment",
    "last_name": "Contractor",
    "language_code": "pl",
}

OTHER_USER = {
    "id": 333444555,
    "username": "other_segment_contractor",
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
    name: str = "Projekt Segmentów",
) -> dict:
    response = await async_client.post(
        "/api/projects",
        json={
            "name": name,
            "address": "ul. Segmentowa 1",
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
    name: str = "Salon",
    length: str | None = None,
    width: str | None = None,
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


def segments_url(project_id: str, room_id: str) -> str:
    return f"/api/projects/{project_id}/rooms/{room_id}/area-segments"


def segment_url(project_id: str, room_id: str, segment_id: str) -> str:
    return f"{segments_url(project_id, room_id)}/{segment_id}"


async def create_segment(
    async_client: AsyncClient,
    token: str,
    project_id: str,
    room_id: str,
    *,
    plane: str = "FLOOR",
    operation: str = "ADD",
    width: str,
    height: str,
    position: int | None = None,
    label: str | None = None,
) -> dict:
    payload: dict = {
        "plane": plane,
        "operation": operation,
        "width": width,
        "height": height,
    }
    if position is not None:
        payload["position"] = position
    if label is not None:
        payload["label"] = label
    response = await async_client.post(
        segments_url(project_id, room_id),
        json=payload,
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def get_room_calcs(
    async_client: AsyncClient,
    token: str,
    project_id: str,
    room_id: str,
) -> dict | None:
    response = await async_client.get(
        f"/api/projects/{project_id}/rooms/{room_id}",
        headers=auth_header(token),
    )
    assert response.status_code == 200, response.text
    return response.json()["calculations"]


@pytest.mark.asyncio
async def test_create_floor_add_segment(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])

    created = await create_segment(
        async_client,
        token,
        project["id"],
        room["id"],
        plane="FLOOR",
        operation="ADD",
        width="3.000",
        height="2.000",
        position=0,
        label="Parkiet wejście",
    )
    assert created["plane"] == "FLOOR"
    assert created["operation"] == "ADD"
    assert created["width"] == "3.000"
    assert created["height"] == "2.000"
    assert created["area"] == "6.000"
    assert created["position"] == 0
    assert created["label"] == "Parkiet wejście"
    assert created["is_archived"] is False
    assert created["room_id"] == room["id"]

    # Verify GET single segment
    get_res = await async_client.get(
        segment_url(project["id"], room["id"], created["id"]),
        headers=auth_header(token),
    )
    assert get_res.status_code == 200
    assert get_res.json() == created


@pytest.mark.asyncio
async def test_create_ceiling_subtract_segment(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])

    await create_segment(
        async_client, token, project["id"], room["id"],
        plane="CEILING", operation="ADD", width="5.000", height="2.000",
    )  # 10.000
    created = await create_segment(
        async_client,
        token,
        project["id"],
        room["id"],
        plane="CEILING",
        operation="SUBTRACT",
        width="1.000",
        height="0.800",
    )  # 0.800, net 9.200
    assert created["plane"] == "CEILING"
    assert created["operation"] == "SUBTRACT"
    assert created["area"] == "0.800"
    assert created["position"] is None

    calcs = await get_room_calcs(async_client, token, project["id"], room["id"])
    assert calcs is not None
    assert calcs["ceiling_area"] == "9.200"
    assert calcs["floor_area"] is None


@pytest.mark.asyncio
async def test_area_quantized_to_three_decimals(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])

    # 1.234 x 1.234 = 1.522756 -> quantized to 1.523
    created = await create_segment(
        async_client,
        token,
        project["id"],
        room["id"],
        plane="FLOOR",
        operation="ADD",
        width="1.234",
        height="1.234",
    )
    assert created["area"] == "1.523"


@pytest.mark.asyncio
async def test_plane_net_area_aggregation_and_room_calculation(
    async_client: AsyncClient,
):
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    # CUSTOM room: no length/width so geometry is None
    room = await create_room(async_client, token, project["id"])

    await create_segment(
        async_client, token, project["id"], room["id"],
        plane="FLOOR", operation="ADD", width="4.000", height="2.000",
    )  # 8.000
    await create_segment(
        async_client, token, project["id"], room["id"],
        plane="FLOOR", operation="ADD", width="2.000", height="1.000",
    )  # 2.000
    await create_segment(
        async_client, token, project["id"], room["id"],
        plane="FLOOR", operation="SUBTRACT", width="1.000", height="1.000",
    )  # 1.000

    calcs = await get_room_calcs(async_client, token, project["id"], room["id"])
    assert calcs is not None
    # additive 10.000 - subtractive 1.000 = net 9.000
    assert calcs["floor_area"] == "9.000"
    # no ceiling segments, no geometry -> None
    assert calcs["ceiling_area"] is None


@pytest.mark.asyncio
async def test_negative_net_blocked_on_create(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])

    # SUBTRACT 25.000 m² with no additions -> negative net
    res = await async_client.post(
        segments_url(project["id"], room["id"]),
        json={"plane": "FLOOR", "operation": "SUBTRACT", "width": "5.000", "height": "5.000"},
        headers=auth_header(token),
    )
    assert res.status_code == 422
    assert "cannot be negative" in res.text


@pytest.mark.asyncio
async def test_negative_net_blocked_on_update_and_persisted_unchanged(
    async_client: AsyncClient,
):
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])

    await create_segment(
        async_client, token, project["id"], room["id"],
        plane="FLOOR", operation="ADD", width="2.000", height="2.000",
    )  # 4.000
    sub = await create_segment(
        async_client, token, project["id"], room["id"],
        plane="FLOOR", operation="SUBTRACT", width="1.000", height="1.000",
    )  # 1.000, net 3.000

    # Raise subtraction to 5.000 -> net -1.000 -> 422
    fail = await async_client.patch(
        segment_url(project["id"], room["id"], sub["id"]),
        json={"height": "5.000"},
        headers=auth_header(token),
    )
    assert fail.status_code == 422
    assert "cannot be negative" in fail.text

    # Persisted segment unchanged
    get_res = await async_client.get(
        segment_url(project["id"], room["id"], sub["id"]),
        headers=auth_header(token),
    )
    assert get_res.json()["height"] == "1.000"
    assert get_res.json()["area"] == "1.000"


@pytest.mark.asyncio
async def test_negative_net_blocked_on_restore(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])

    await create_segment(
        async_client, token, project["id"], room["id"],
        plane="FLOOR", operation="ADD", width="4.000", height="1.000",
    )  # 4.000
    sub = await create_segment(
        async_client, token, project["id"], room["id"],
        plane="FLOOR", operation="SUBTRACT", width="3.000", height="1.000",
    )  # 3.000, net 1.000

    # Archive SUBTRACT -> net 4.000
    arch = await async_client.post(
        f"{segment_url(project['id'], room['id'], sub['id'])}/archive",
        headers=auth_header(token),
    )
    assert arch.status_code == 200
    assert arch.json()["is_archived"] is True

    # Grow the archived SUBTRACT (archived segments skip net validation)
    grow = await async_client.patch(
        segment_url(project["id"], room["id"], sub["id"]),
        json={"height": "6.000"},
        headers=auth_header(token),
    )
    assert grow.status_code == 200

    # Restore -> net would be 4.000 - 6.000 = -2.000 -> 422
    restore_fail = await async_client.post(
        f"{segment_url(project['id'], room['id'], sub['id'])}/restore",
        headers=auth_header(token),
    )
    assert restore_fail.status_code == 422
    assert "cannot be negative" in restore_fail.text

    # Segment remains archived after failed restore
    get_res = await async_client.get(
        segment_url(project["id"], room["id"], sub["id"]),
        headers=auth_header(token),
    )
    assert get_res.json()["is_archived"] is True


@pytest.mark.asyncio
async def test_zero_net_allowed(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])

    await create_segment(
        async_client, token, project["id"], room["id"],
        plane="FLOOR", operation="ADD", width="2.000", height="2.000",
    )  # 4.000
    await create_segment(
        async_client, token, project["id"], room["id"],
        plane="FLOOR", operation="SUBTRACT", width="2.000", height="2.000",
    )  # 4.000, net 0.000

    calcs = await get_room_calcs(async_client, token, project["id"], room["id"])
    assert calcs is not None
    assert calcs["floor_area"] == "0.000"


@pytest.mark.asyncio
async def test_archived_segments_excluded_from_net(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])

    await create_segment(
        async_client, token, project["id"], room["id"],
        plane="FLOOR", operation="ADD", width="4.000", height="2.000",
    )  # 8.000
    sub = await create_segment(
        async_client, token, project["id"], room["id"],
        plane="FLOOR", operation="SUBTRACT", width="2.000", height="1.000",
    )  # 2.000, net 6.000

    calcs_before = await get_room_calcs(async_client, token, project["id"], room["id"])
    assert calcs_before["floor_area"] == "6.000"

    # Archive SUBTRACT -> net back to 8.000
    await async_client.post(
        f"{segment_url(project['id'], room['id'], sub['id'])}/archive",
        headers=auth_header(token),
    )
    calcs_archived = await get_room_calcs(async_client, token, project["id"], room["id"])
    assert calcs_archived["floor_area"] == "8.000"

    # Restore SUBTRACT -> net returns to 6.000
    await async_client.post(
        f"{segment_url(project['id'], room['id'], sub['id'])}/restore",
        headers=auth_header(token),
    )
    calcs_restored = await get_room_calcs(async_client, token, project["id"], room["id"])
    assert calcs_restored["floor_area"] == "6.000"


@pytest.mark.asyncio
async def test_rectangle_room_keeps_formula_without_segments_and_planes_independent(
    async_client: AsyncClient,
):
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(
        async_client, token, project["id"],
        length="5.000", width="4.000", height="2.700",
    )

    # No segments -> existing L x W formula behavior
    calcs_none = await get_room_calcs(async_client, token, project["id"], room["id"])
    assert calcs_none is not None
    assert calcs_none["floor_area"] == "20.000"
    assert calcs_none["ceiling_area"] == "20.000"

    # Add only a FLOOR segment -> floor becomes base + segment, ceiling stays L x W
    await create_segment(
        async_client, token, project["id"], room["id"],
        plane="FLOOR", operation="ADD", width="3.000", height="2.000",
    )  # 6.000
    calcs_floor = await get_room_calcs(async_client, token, project["id"], room["id"])
    assert calcs_floor["floor_area"] == "26.000"  # 20.000 base + 6.000 adjustment
    assert calcs_floor["ceiling_area"] == "20.000"


@pytest.mark.asyncio
async def test_custom_room_segment_planes_independent(
    async_client: AsyncClient,
):
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    # CUSTOM room: no length/width -> geometry None
    room = await create_room(async_client, token, project["id"])

    # No segments -> no fabricated L x W (calculations stay null like pre-segment
    # custom rooms without measured walls)
    calcs_none = await get_room_calcs(async_client, token, project["id"], room["id"])
    assert calcs_none is None

    # Add CEILING segment -> ceiling derived, floor stays None
    await create_segment(
        async_client, token, project["id"], room["id"],
        plane="CEILING", operation="ADD", width="5.000", height="2.000",
    )  # 10.000
    calcs_ceiling = await get_room_calcs(async_client, token, project["id"], room["id"])
    assert calcs_ceiling["floor_area"] is None
    assert calcs_ceiling["ceiling_area"] == "10.000"


@pytest.mark.asyncio
async def test_list_filter_by_plane_and_total(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])

    await create_segment(
        async_client, token, project["id"], room["id"],
        plane="FLOOR", operation="ADD", width="2.000", height="1.000",
    )
    await create_segment(
        async_client, token, project["id"], room["id"],
        plane="FLOOR", operation="SUBTRACT", width="0.500", height="0.500",
    )
    await create_segment(
        async_client, token, project["id"], room["id"],
        plane="CEILING", operation="ADD", width="3.000", height="2.000",
    )

    # All segments
    all_res = await async_client.get(
        segments_url(project["id"], room["id"]),
        headers=auth_header(token),
    )
    assert all_res.status_code == 200
    assert all_res.json()["total"] == 3
    assert len(all_res.json()["items"]) == 3

    # Filter FLOOR
    floor_res = await async_client.get(
        segments_url(project["id"], room["id"]),
        params={"plane": "FLOOR"},
        headers=auth_header(token),
    )
    assert floor_res.status_code == 200
    assert floor_res.json()["total"] == 2
    assert all(item["plane"] == "FLOOR" for item in floor_res.json()["items"])

    # Filter CEILING
    ceiling_res = await async_client.get(
        segments_url(project["id"], room["id"]),
        params={"plane": "CEILING"},
        headers=auth_header(token),
    )
    assert ceiling_res.status_code == 200
    assert ceiling_res.json()["total"] == 1


@pytest.mark.asyncio
async def test_owner_isolation_and_404s(async_client: AsyncClient):
    token_a = await get_token(async_client, VALID_USER)
    token_b = await get_token(async_client, OTHER_USER)

    proj_a = await create_project(async_client, token_a, name="Projekt A")
    room_a = await create_room(async_client, token_a, proj_a["id"])
    seg = await create_segment(
        async_client, token_a, proj_a["id"], room_a["id"],
        plane="FLOOR", operation="ADD", width="2.000", height="2.000",
    )

    # User B cannot list, get, create, update, archive, or restore A's segments
    assert (
        await async_client.get(
            segments_url(proj_a["id"], room_a["id"]), headers=auth_header(token_b)
        )
    ).status_code == 404
    assert (
        await async_client.get(
            segment_url(proj_a["id"], room_a["id"], seg["id"]),
            headers=auth_header(token_b),
        )
    ).status_code == 404
    assert (
        await async_client.post(
            segments_url(proj_a["id"], room_a["id"]),
            json={"plane": "FLOOR", "operation": "ADD", "width": "1.000", "height": "1.000"},
            headers=auth_header(token_b),
        )
    ).status_code == 404
    assert (
        await async_client.patch(
            segment_url(proj_a["id"], room_a["id"], seg["id"]),
            json={"height": "3.000"},
            headers=auth_header(token_b),
        )
    ).status_code == 404
    assert (
        await async_client.post(
            f"{segment_url(proj_a['id'], room_a['id'], seg['id'])}/archive",
            headers=auth_header(token_b),
        )
    ).status_code == 404
    assert (
        await async_client.post(
            f"{segment_url(proj_a['id'], room_a['id'], seg['id'])}/restore",
            headers=auth_header(token_b),
        )
    ).status_code == 404

    # Random segment id under A's own room -> 404
    random_id = str(uuid.uuid4())
    assert (
        await async_client.get(
            segment_url(proj_a["id"], room_a["id"], random_id),
            headers=auth_header(token_a),
        )
    ).status_code == 404

    # Random room id under A's own project -> 404
    assert (
        await async_client.get(
            segments_url(proj_a["id"], str(uuid.uuid4())),
            headers=auth_header(token_a),
        )
    ).status_code == 404

    # Random project id -> 404
    assert (
        await async_client.get(
            segments_url(str(uuid.uuid4()), room_a["id"]),
            headers=auth_header(token_a),
        )
    ).status_code == 404


@pytest.mark.parametrize(
    ("payload", "error_field"),
    [
        ({"plane": "FLOOR", "operation": "ADD", "width": "0.000", "height": "1.000"}, "width"),
        ({"plane": "FLOOR", "operation": "ADD", "width": "-1.000", "height": "1.000"}, "width"),
        ({"plane": "FLOOR", "operation": "ADD", "width": "1.000", "height": "0.000"}, "height"),
        ({"plane": "FLOOR", "operation": "ADD", "width": "1.000", "height": "-2.000"}, "height"),
        ({"plane": "FLOOR", "operation": "ADD", "width": "1.1234", "height": "1.000"}, "width"),
        ({"plane": "FLOOR", "operation": "ADD", "width": "1.000", "height": "1.1234"}, "height"),
        ({"plane": "FLOOR", "operation": "ADD", "width": "1.000", "height": "1.000", "position": -1}, "position"),
    ],
)
@pytest.mark.asyncio
async def test_segment_dimension_validation_rejections(
    async_client: AsyncClient,
    payload: dict,
    error_field: str,
):
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])

    res = await async_client.post(
        segments_url(project["id"], room["id"]),
        json=payload,
        headers=auth_header(token),
    )
    assert res.status_code == 422
    errors = res.json().get("detail", [])
    assert any(error_field in e.get("loc", []) for e in errors)


@pytest.mark.asyncio
async def test_archived_segments_still_listed_with_include_archived(
    async_client: AsyncClient,
):
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])

    seg = await create_segment(
        async_client, token, project["id"], room["id"],
        plane="FLOOR", operation="ADD", width="2.000", height="2.000",
    )
    await async_client.post(
        f"{segment_url(project['id'], room['id'], seg['id'])}/archive",
        headers=auth_header(token),
    )

    # Archived excluded by default
    default_res = await async_client.get(
        segments_url(project["id"], room["id"]),
        headers=auth_header(token),
    )
    assert default_res.json()["total"] == 0

    # Included with include_archived
    incl_res = await async_client.get(
        segments_url(project["id"], room["id"]),
        params={"include_archived": "true"},
        headers=auth_header(token),
    )
    assert incl_res.status_code == 200
    assert incl_res.json()["total"] == 1
    assert incl_res.json()["items"][0]["is_archived"] is True


# --- Hotfix 5D.1B.2: rectangle floor/ceiling base-area semantics ---
#
# For a RECTANGLE room the effective plane area is base (L x W) plus active
# ADD segments minus active SUBTRACT segments. The negative-net guard uses the
# same effective calculation, so subtractions may deduct from the room base.


async def get_planes_summary(
    async_client: AsyncClient, token: str, project_id: str, room_id: str
) -> dict:
    res = await async_client.get(
        segments_url(project_id, room_id), headers=auth_header(token)
    )
    assert res.status_code == 200, res.text
    return res.json()["planes"]


@pytest.mark.asyncio
async def test_rectangle_room_no_segments_keeps_base_12_210(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(
        async_client, token, project["id"],
        length="3.700", width="3.300", height="2.700",
    )

    calcs = await get_room_calcs(async_client, token, project["id"], room["id"])
    assert calcs is not None
    assert calcs["floor_area"] == "12.210"
    assert calcs["ceiling_area"] == "12.210"

    # The segment list exposes an effective total even with zero segments.
    planes = await get_planes_summary(async_client, token, project["id"], room["id"])
    assert planes["FLOOR"]["base_area"] == "12.210"
    assert planes["FLOOR"]["adjustment_area"] == "0.000"
    assert planes["FLOOR"]["net_area"] == "12.210"


@pytest.mark.asyncio
async def test_rectangle_room_subtract_deducts_from_base(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(
        async_client, token, project["id"],
        length="3.700", width="3.300", height="2.700",
    )  # base 12.210

    # SUBTRACT 0.700 x 0.800 = 0.560 is allowed against the room base.
    await create_segment(
        async_client, token, project["id"], room["id"],
        plane="FLOOR", operation="SUBTRACT", width="0.700", height="0.800",
    )

    calcs = await get_room_calcs(async_client, token, project["id"], room["id"])
    assert calcs["floor_area"] == "11.650"  # 12.210 - 0.560
    assert calcs["ceiling_area"] == "12.210"

    planes = await get_planes_summary(async_client, token, project["id"], room["id"])
    assert planes["FLOOR"]["base_area"] == "12.210"
    assert planes["FLOOR"]["adjustment_area"] == "-0.560"
    assert planes["FLOOR"]["net_area"] == "11.650"


@pytest.mark.asyncio
async def test_rectangle_room_add_combines_with_base(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(
        async_client, token, project["id"],
        length="3.700", width="3.300", height="2.700",
    )  # base 12.210

    await create_segment(
        async_client, token, project["id"], room["id"],
        plane="FLOOR", operation="ADD", width="1.000", height="0.500",
    )  # +0.500

    calcs = await get_room_calcs(async_client, token, project["id"], room["id"])
    assert calcs["floor_area"] == "12.710"  # 12.210 + 0.500

    planes = await get_planes_summary(async_client, token, project["id"], room["id"])
    assert planes["FLOOR"]["adjustment_area"] == "0.500"
    assert planes["FLOOR"]["net_area"] == "12.710"


@pytest.mark.asyncio
async def test_rectangle_negative_guard_uses_base_area(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(
        async_client, token, project["id"],
        length="3.700", width="3.300", height="2.700",
    )  # base 12.210

    # SUBTRACT 4.000 x 4.000 = 16.000 exceeds the 12.210 base -> 422
    res = await async_client.post(
        segments_url(project["id"], room["id"]),
        json={"plane": "FLOOR", "operation": "SUBTRACT", "width": "4.000", "height": "4.000"},
        headers=auth_header(token),
    )
    assert res.status_code == 422
    assert "cannot be negative" in res.text


@pytest.mark.asyncio
async def test_floor_adjustment_does_not_affect_ceiling(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(
        async_client, token, project["id"],
        length="3.700", width="3.300", height="2.700",
    )  # both planes base 12.210

    await create_segment(
        async_client, token, project["id"], room["id"],
        plane="FLOOR", operation="SUBTRACT", width="0.700", height="0.800",
    )  # floor -> 11.650

    calcs = await get_room_calcs(async_client, token, project["id"], room["id"])
    assert calcs["floor_area"] == "11.650"
    assert calcs["ceiling_area"] == "12.210"

    planes = await get_planes_summary(async_client, token, project["id"], room["id"])
    assert planes["FLOOR"]["net_area"] == "11.650"
    assert planes["CEILING"]["net_area"] == "12.210"


@pytest.mark.asyncio
async def test_custom_room_unchanged_no_base_no_fabricated_area(
    async_client: AsyncClient,
):
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])

    # No segments -> no L x W fabrication, list summary shows no base.
    calcs = await get_room_calcs(async_client, token, project["id"], room["id"])
    assert calcs is None
    planes = await get_planes_summary(async_client, token, project["id"], room["id"])
    assert planes["FLOOR"]["base_area"] is None
    assert planes["FLOOR"]["net_area"] == "0.000"
    assert planes["CEILING"]["base_area"] is None

    # ADD 8.000 + SUBTRACT 1.000 -> segment-derived 7.000, no base involved.
    await create_segment(
        async_client, token, project["id"], room["id"],
        plane="FLOOR", operation="ADD", width="4.000", height="2.000",
    )  # 8.000
    await create_segment(
        async_client, token, project["id"], room["id"],
        plane="FLOOR", operation="SUBTRACT", width="1.000", height="1.000",
    )  # 1.000
    calcs = await get_room_calcs(async_client, token, project["id"], room["id"])
    assert calcs["floor_area"] == "7.000"
    planes = await get_planes_summary(async_client, token, project["id"], room["id"])
    assert planes["FLOOR"]["base_area"] is None
    assert planes["FLOOR"]["adjustment_area"] == "7.000"
    assert planes["FLOOR"]["net_area"] == "7.000"


@pytest.mark.asyncio
async def test_archive_and_restore_recalculate_against_base(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(
        async_client, token, project["id"],
        length="3.700", width="3.300", height="2.700",
    )  # base 12.210

    sub = await create_segment(
        async_client, token, project["id"], room["id"],
        plane="FLOOR", operation="SUBTRACT", width="0.700", height="0.800",
    )  # 0.560, floor 11.650

    calcs = await get_room_calcs(async_client, token, project["id"], room["id"])
    assert calcs["floor_area"] == "11.650"

    # Archive -> base restored
    arch = await async_client.post(
        f"{segment_url(project['id'], room['id'], sub['id'])}/archive",
        headers=auth_header(token),
    )
    assert arch.status_code == 200
    calcs = await get_room_calcs(async_client, token, project["id"], room["id"])
    assert calcs["floor_area"] == "12.210"

    # Restore -> deduction reapplied
    rest = await async_client.post(
        f"{segment_url(project['id'], room['id'], sub['id'])}/restore",
        headers=auth_header(token),
    )
    assert rest.status_code == 200
    calcs = await get_room_calcs(async_client, token, project["id"], room["id"])
    assert calcs["floor_area"] == "11.650"
