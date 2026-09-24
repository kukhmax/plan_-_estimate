"""Focused Stage 12C API tests: owner-scoped price coefficient endpoints.

Covers unauthenticated 401s, group CRUD, option CRUD nested under a group,
the nested active-catalog read model, ordering, validation, immutable codes,
duplicate-code rejection, owner isolation with uniform 404s, and the
base-option invariant through the HTTP layer. No planned-work assignment
endpoint exists yet (Stage 12D).
"""
from decimal import Decimal

import pytest
from httpx import AsyncClient

from tests.conftest import make_telegram_init_data

VALID_USER = {
    "id": 121111111,
    "username": "owner",
    "first_name": "Owner",
    "last_name": "User",
    "language_code": "pl",
}

OTHER_USER = {
    "id": 122222222,
    "username": "other",
    "first_name": "Other",
    "last_name": "Person",
    "language_code": "pl",
}


async def get_token(async_client: AsyncClient, user_dict: dict) -> str:
    init_data = make_telegram_init_data(user_dict)
    resp = await async_client.post("/api/auth/telegram", json={"init_data": init_data})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Unauthenticated access
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/price-coefficient-groups"),
        ("POST", "/api/price-coefficient-groups"),
        ("GET", "/api/price-coefficient-groups/00000000-0000-0000-0000-000000000000"),
        ("PATCH", "/api/price-coefficient-groups/00000000-0000-0000-0000-000000000000"),
        ("POST", "/api/price-coefficient-groups/00000000-0000-0000-0000-000000000000/archive"),
        ("POST", "/api/price-coefficient-groups/00000000-0000-0000-0000-000000000000/restore"),
        ("POST", "/api/price-coefficient-groups/00000000-0000-0000-0000-000000000000/options"),
        ("PATCH", "/api/price-coefficient-options/00000000-0000-0000-0000-000000000000"),
        ("POST", "/api/price-coefficient-options/00000000-0000-0000-0000-000000000000/archive"),
        ("POST", "/api/price-coefficient-options/00000000-0000-0000-0000-000000000000/restore"),
    ],
)
async def test_unauthenticated_401(async_client: AsyncClient, method: str, path: str):
    resp = await async_client.request(method, path, json={} if method != "GET" else None)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Bootstrap-on-list (currently a no-op -- production baseline is empty)
# ---------------------------------------------------------------------------

async def test_first_list_bootstraps_without_error(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    resp = await async_client.get(
        "/api/price-coefficient-groups", headers=auth_header(token)
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Stage 12G: the first list lazily installs the four v1 default groups.
    assert body["total"] == 4
    assert [g["code"] for g in body["items"]] == [
        "WYSOKOSC_PRACY",
        "DOSTEP_DO_POWIERZCHNI",
        "ZLOZONOSC_POWIERZCHNI",
        "ORGANIZACJA_PRACY",
    ]


# ---------------------------------------------------------------------------
# Group CRUD
# ---------------------------------------------------------------------------

async def test_create_group_generates_code(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    resp = await async_client.post(
        "/api/price-coefficient-groups", headers=headers, json={"display_name": "Wysokość"}
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["code"].startswith("CUSTOM_")
    assert body["display_name"] == "Wysokość"
    assert body["selection_mode"] == "SINGLE_SELECT"
    assert body["is_archived"] is False
    assert body["options"] == []


async def test_client_cannot_supply_semantic_code(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    resp = await async_client.post(
        "/api/price-coefficient-groups",
        headers=auth_header(token),
        json={"display_name": "A", "code": "HACKED"},
    )
    assert resp.status_code == 422  # extra="forbid" rejects the unknown field


async def test_create_group_requires_display_name(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    resp = await async_client.post(
        "/api/price-coefficient-groups", headers=auth_header(token), json={"display_name": ""}
    )
    assert resp.status_code == 422


async def test_full_group_lifecycle(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)

    created = (
        await async_client.post(
            "/api/price-coefficient-groups", headers=headers, json={"display_name": "A"}
        )
    ).json()
    group_id = created["id"]
    code = created["code"]

    updated = (
        await async_client.patch(
            f"/api/price-coefficient-groups/{group_id}",
            headers=headers,
            json={"display_name": "Renamed"},
        )
    ).json()
    assert updated["display_name"] == "Renamed"
    assert updated["code"] == code

    archived = (
        await async_client.post(
            f"/api/price-coefficient-groups/{group_id}/archive", headers=headers
        )
    ).json()
    assert archived["is_archived"] is True

    active = (
        await async_client.get("/api/price-coefficient-groups", headers=headers)
    ).json()
    assert group_id not in {g["id"] for g in active["items"]}

    all_groups = (
        await async_client.get(
            "/api/price-coefficient-groups", headers=headers, params={"archived": "all"}
        )
    ).json()
    assert group_id in {g["id"] for g in all_groups["items"]}

    restored = (
        await async_client.post(
            f"/api/price-coefficient-groups/{group_id}/restore", headers=headers
        )
    ).json()
    assert restored["is_archived"] is False
    assert restored["code"] == code


async def test_group_not_found_404(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    resp = await async_client.get(
        "/api/price-coefficient-groups/00000000-0000-0000-0000-000000000000",
        headers=auth_header(token),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Option CRUD, nested read model, ordering
# ---------------------------------------------------------------------------

async def test_create_option_and_nested_read_model(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    group_id = (
        await async_client.post(
            "/api/price-coefficient-groups", headers=headers, json={"display_name": "Wysokość"}
        )
    ).json()["id"]

    first = (
        await async_client.post(
            f"/api/price-coefficient-groups/{group_id}/options",
            headers=headers,
            json={"display_name": "Normalna", "percentage": "0", "is_base": True},
        )
    ).json()
    second = (
        await async_client.post(
            f"/api/price-coefficient-groups/{group_id}/options",
            headers=headers,
            json={"display_name": "Wysoka", "percentage": "20"},
        )
    ).json()
    assert first["code"].startswith("CUSTOM_")
    # Exact decimal (as a JSON string, never a float); the SQLite test
    # backend does not pad to the Numeric(6,3) column scale the way
    # PostgreSQL does in production, so compare by value, not padded string.
    assert isinstance(first["percentage"], str)
    assert Decimal(first["percentage"]) == Decimal("0")
    assert Decimal(second["percentage"]) == Decimal("20")

    detail = (
        await async_client.get(
            f"/api/price-coefficient-groups/{group_id}", headers=headers
        )
    ).json()
    assert [o["id"] for o in detail["options"]] == [first["id"], second["id"]]

    # Nested-catalog list endpoint also carries options, no N+1 fan-out needed.
    listed = (
        await async_client.get("/api/price-coefficient-groups", headers=headers)
    ).json()
    listed_group = next(g for g in listed["items"] if g["id"] == group_id)
    assert {o["id"] for o in listed_group["options"]} == {first["id"], second["id"]}


async def test_option_percentage_is_exact_decimal_string_never_float(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    group_id = (
        await async_client.post(
            "/api/price-coefficient-groups", headers=headers, json={"display_name": "A"}
        )
    ).json()["id"]
    option = (
        await async_client.post(
            f"/api/price-coefficient-groups/{group_id}/options",
            headers=headers,
            json={"display_name": "X", "percentage": "12.5"},
        )
    ).json()
    assert isinstance(option["percentage"], str)
    assert Decimal(option["percentage"]) == Decimal("12.5")


@pytest.mark.parametrize("bad_percentage", ["-100", "-150", "501", "abc"])
async def test_invalid_percentage_rejected(async_client: AsyncClient, bad_percentage: str):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    group_id = (
        await async_client.post(
            "/api/price-coefficient-groups", headers=headers, json={"display_name": "A"}
        )
    ).json()["id"]
    resp = await async_client.post(
        f"/api/price-coefficient-groups/{group_id}/options",
        headers=headers,
        json={"display_name": "X", "percentage": bad_percentage},
    )
    assert resp.status_code == 422


async def test_client_cannot_supply_option_semantic_code(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    group_id = (
        await async_client.post(
            "/api/price-coefficient-groups", headers=headers, json={"display_name": "A"}
        )
    ).json()["id"]
    resp = await async_client.post(
        f"/api/price-coefficient-groups/{group_id}/options",
        headers=headers,
        json={"display_name": "X", "percentage": "0", "code": "HACKED"},
    )
    assert resp.status_code == 422


async def test_option_not_found_404(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    resp = await async_client.patch(
        "/api/price-coefficient-options/00000000-0000-0000-0000-000000000000",
        headers=auth_header(token),
        json={"percentage": "10"},
    )
    assert resp.status_code == 404


async def test_option_full_lifecycle(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    group_id = (
        await async_client.post(
            "/api/price-coefficient-groups", headers=headers, json={"display_name": "A"}
        )
    ).json()["id"]
    option_id = (
        await async_client.post(
            f"/api/price-coefficient-groups/{group_id}/options",
            headers=headers,
            json={"display_name": "X", "percentage": "10"},
        )
    ).json()["id"]

    updated = (
        await async_client.patch(
            f"/api/price-coefficient-options/{option_id}",
            headers=headers,
            json={"percentage": "15", "display_name": "Y"},
        )
    ).json()
    assert Decimal(updated["percentage"]) == Decimal("15")
    assert updated["display_name"] == "Y"

    archived = (
        await async_client.post(
            f"/api/price-coefficient-options/{option_id}/archive", headers=headers
        )
    ).json()
    assert archived["is_archived"] is True

    default_view = (
        await async_client.get(
            f"/api/price-coefficient-groups/{group_id}", headers=headers
        )
    ).json()
    assert option_id not in {o["id"] for o in default_view["options"]}

    with_archived = (
        await async_client.get(
            f"/api/price-coefficient-groups/{group_id}",
            headers=headers,
            params={"include_archived_options": "true"},
        )
    ).json()
    assert option_id in {o["id"] for o in with_archived["options"]}

    restored = (
        await async_client.post(
            f"/api/price-coefficient-options/{option_id}/restore", headers=headers
        )
    ).json()
    assert restored["is_archived"] is False


async def test_base_option_replacement_via_api(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    group_id = (
        await async_client.post(
            "/api/price-coefficient-groups", headers=headers, json={"display_name": "A"}
        )
    ).json()["id"]
    first = (
        await async_client.post(
            f"/api/price-coefficient-groups/{group_id}/options",
            headers=headers,
            json={"display_name": "First", "percentage": "0", "is_base": True},
        )
    ).json()
    second = (
        await async_client.post(
            f"/api/price-coefficient-groups/{group_id}/options",
            headers=headers,
            json={"display_name": "Second", "percentage": "10", "is_base": True},
        )
    ).json()

    group = (
        await async_client.get(
            f"/api/price-coefficient-groups/{group_id}", headers=headers
        )
    ).json()
    base_options = [o for o in group["options"] if o["is_base"]]
    assert len(base_options) == 1
    assert base_options[0]["id"] == second["id"]
    assert first["id"] != second["id"]


# ---------------------------------------------------------------------------
# Ownership isolation
# ---------------------------------------------------------------------------

async def test_ownership_isolation(async_client: AsyncClient):
    owner_token = await get_token(async_client, VALID_USER)
    other_token = await get_token(async_client, OTHER_USER)
    owner_headers = auth_header(owner_token)
    other_headers = auth_header(other_token)

    group_id = (
        await async_client.post(
            "/api/price-coefficient-groups", headers=owner_headers, json={"display_name": "A"}
        )
    ).json()["id"]
    option_id = (
        await async_client.post(
            f"/api/price-coefficient-groups/{group_id}/options",
            headers=owner_headers,
            json={"display_name": "X", "percentage": "10"},
        )
    ).json()["id"]

    assert (
        await async_client.get(
            f"/api/price-coefficient-groups/{group_id}", headers=other_headers
        )
    ).status_code == 404
    assert (
        await async_client.patch(
            f"/api/price-coefficient-groups/{group_id}",
            headers=other_headers,
            json={"display_name": "Hacked"},
        )
    ).status_code == 404
    assert (
        await async_client.post(
            f"/api/price-coefficient-groups/{group_id}/archive", headers=other_headers
        )
    ).status_code == 404
    assert (
        await async_client.post(
            f"/api/price-coefficient-groups/{group_id}/options",
            headers=other_headers,
            json={"display_name": "Intrusion", "percentage": "0"},
        )
    ).status_code == 404
    assert (
        await async_client.patch(
            f"/api/price-coefficient-options/{option_id}",
            headers=other_headers,
            json={"percentage": "99"},
        )
    ).status_code == 404
    assert (
        await async_client.post(
            f"/api/price-coefficient-options/{option_id}/archive", headers=other_headers
        )
    ).status_code == 404

    # Owner's own catalog is untouched by the other user's rejected attempts.
    owner_group = (
        await async_client.get(
            f"/api/price-coefficient-groups/{group_id}", headers=owner_headers
        )
    ).json()
    assert owner_group["display_name"] == "A"
    assert owner_group["is_archived"] is False


async def test_second_owners_list_is_independent(async_client: AsyncClient):
    owner_token = await get_token(async_client, VALID_USER)
    other_token = await get_token(async_client, OTHER_USER)
    await async_client.post(
        "/api/price-coefficient-groups",
        headers=auth_header(owner_token),
        json={"display_name": "Owner Group"},
    )
    other_list = (
        await async_client.get(
            "/api/price-coefficient-groups", headers=auth_header(other_token)
        )
    ).json()
    # The other owner sees only their own four program defaults.
    assert other_list["total"] == 4
    assert "Owner Group" not in [g["display_name"] for g in other_list["items"]]
    assert all(not g["code"].startswith("CUSTOM_") for g in other_list["items"])
