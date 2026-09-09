"""Tests for client management API — Stage 3."""
import uuid
import pytest
from httpx import AsyncClient

from tests.conftest import make_telegram_init_data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


async def get_token(async_client: AsyncClient, user_dict: dict) -> str:
    """Authenticate and return a JWT bearer token."""
    init_data = make_telegram_init_data(user_dict)
    resp = await async_client.post(
        "/api/auth/telegram", json={"init_data": init_data}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Test: create PRIVATE_PERSON
# ---------------------------------------------------------------------------

async def test_create_private_person(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    resp = await async_client.post(
        "/api/clients",
        json={"client_type": "PRIVATE_PERSON", "first_name": "Jan", "last_name": "Kowalski", "phone": "500600700"},
        headers=auth_header(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["client_type"] == "PRIVATE_PERSON"
    assert data["first_name"] == "Jan"
    assert data["last_name"] == "Kowalski"
    assert data["is_archived"] is False
    assert "id" in data


# ---------------------------------------------------------------------------
# Test: create COMPANY
# ---------------------------------------------------------------------------

async def test_create_company(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    resp = await async_client.post(
        "/api/clients",
        json={"client_type": "COMPANY", "company_name": "Remontex Sp. z o.o.", "nip": "1234567890"},
        headers=auth_header(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["client_type"] == "COMPANY"
    assert data["company_name"] == "Remontex Sp. z o.o."
    assert data["nip"] == "1234567890"


# ---------------------------------------------------------------------------
# Test: COMPANY validation — company_name required
# ---------------------------------------------------------------------------

async def test_create_company_missing_name_fails(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    resp = await async_client.post(
        "/api/clients",
        json={"client_type": "COMPANY"},
        headers=auth_header(token),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Test: PRIVATE_PERSON validation — at least first_name or last_name required
# ---------------------------------------------------------------------------

async def test_create_private_person_missing_name_fails(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    resp = await async_client.post(
        "/api/clients",
        json={"client_type": "PRIVATE_PERSON"},
        headers=auth_header(token),
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Test: edit client
# ---------------------------------------------------------------------------

async def test_update_client(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    create_resp = await async_client.post(
        "/api/clients",
        json={"client_type": "PRIVATE_PERSON", "first_name": "Anna"},
        headers=auth_header(token),
    )
    client_id = create_resp.json()["id"]

    patch_resp = await async_client.patch(
        f"/api/clients/{client_id}",
        json={"phone": "600700800", "email": "anna@example.pl"},
        headers=auth_header(token),
    )
    assert patch_resp.status_code == 200
    data = patch_resp.json()
    assert data["phone"] == "600700800"
    assert data["email"] == "anna@example.pl"
    assert data["first_name"] == "Anna"


# ---------------------------------------------------------------------------
# Test: archive client
# ---------------------------------------------------------------------------

async def test_archive_client(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    create_resp = await async_client.post(
        "/api/clients",
        json={"client_type": "PRIVATE_PERSON", "first_name": "Tomek"},
        headers=auth_header(token),
    )
    client_id = create_resp.json()["id"]

    archive_resp = await async_client.post(
        f"/api/clients/{client_id}/archive",
        headers=auth_header(token),
    )
    assert archive_resp.status_code == 200
    assert archive_resp.json()["is_archived"] is True

    # Should not appear in active list
    list_resp = await async_client.get("/api/clients", headers=auth_header(token))
    ids = [c["id"] for c in list_resp.json()["items"]]
    assert client_id not in ids

    # Should appear with include_archived=true
    list_resp2 = await async_client.get(
        "/api/clients?include_archived=true", headers=auth_header(token)
    )
    ids2 = [c["id"] for c in list_resp2.json()["items"]]
    assert client_id in ids2


# ---------------------------------------------------------------------------
# Test: restore client
# ---------------------------------------------------------------------------

async def test_restore_client(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    create_resp = await async_client.post(
        "/api/clients",
        json={"client_type": "PRIVATE_PERSON", "first_name": "Marek"},
        headers=auth_header(token),
    )
    client_id = create_resp.json()["id"]

    await async_client.post(f"/api/clients/{client_id}/archive", headers=auth_header(token))

    restore_resp = await async_client.post(
        f"/api/clients/{client_id}/restore",
        headers=auth_header(token),
    )
    assert restore_resp.status_code == 200
    assert restore_resp.json()["is_archived"] is False

    # Should appear in active list again
    list_resp = await async_client.get("/api/clients", headers=auth_header(token))
    ids = [c["id"] for c in list_resp.json()["items"]]
    assert client_id in ids


# ---------------------------------------------------------------------------
# Test: search
# ---------------------------------------------------------------------------

async def test_search_clients(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    await async_client.post(
        "/api/clients",
        json={"client_type": "PRIVATE_PERSON", "first_name": "Zbigniew", "last_name": "Nowak"},
        headers=auth_header(token),
    )
    await async_client.post(
        "/api/clients",
        json={"client_type": "COMPANY", "company_name": "BuildMaster Sp. z o.o."},
        headers=auth_header(token),
    )

    # Search by first name
    resp = await async_client.get("/api/clients?search=Zbigni", headers=auth_header(token))
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert len(items) == 1
    assert items[0]["first_name"] == "Zbigniew"

    # Search by company name
    resp2 = await async_client.get("/api/clients?search=BuildMaster", headers=auth_header(token))
    items2 = resp2.json()["items"]
    assert len(items2) == 1
    assert items2[0]["company_name"] == "BuildMaster Sp. z o.o."


# ---------------------------------------------------------------------------
# Test: owner isolation — cannot access another owner's client
# ---------------------------------------------------------------------------

async def test_owner_isolation(async_client: AsyncClient):
    owner_token = await get_token(async_client, VALID_USER)
    other_token = await get_token(async_client, OTHER_USER)

    # Owner creates a client
    create_resp = await async_client.post(
        "/api/clients",
        json={"client_type": "PRIVATE_PERSON", "first_name": "Secret", "last_name": "Client"},
        headers=auth_header(owner_token),
    )
    assert create_resp.status_code == 201
    client_id = create_resp.json()["id"]

    # Other user cannot retrieve it — must get 404, not 403
    get_resp = await async_client.get(
        f"/api/clients/{client_id}", headers=auth_header(other_token)
    )
    assert get_resp.status_code == 404

    # Other user's list must be empty
    list_resp = await async_client.get("/api/clients", headers=auth_header(other_token))
    assert list_resp.json()["total"] == 0

    # Other user cannot archive it — 404
    archive_resp = await async_client.post(
        f"/api/clients/{client_id}/archive", headers=auth_header(other_token)
    )
    assert archive_resp.status_code == 404


# ---------------------------------------------------------------------------
# Test: unauthenticated access is rejected
# ---------------------------------------------------------------------------

async def test_unauthenticated_access(async_client: AsyncClient):
    resp = await async_client.get("/api/clients")
    assert resp.status_code == 401
