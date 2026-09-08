from datetime import datetime, timezone
import pytest
from httpx import AsyncClient

from app.core.config import settings
from tests.conftest import TEST_BOT_TOKEN, make_telegram_init_data


@pytest.mark.asyncio
async def test_telegram_auth_valid_signature(async_client: AsyncClient):
    """Verifies that a valid Telegram signature creates/retrieves user and returns JWT."""
    user_payload = {
        "id": 123456789,
        "first_name": "Marek",
        "last_name": "Nowak",
        "username": "marek_contractor",
        "language_code": "pl",
    }
    init_data = make_telegram_init_data(user_payload)

    response = await async_client.post("/api/auth/telegram", json={"init_data": init_data})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["is_dev_auth"] is False
    assert data["user"]["telegram_user_id"] == 123456789
    assert data["user"]["username"] == "marek_contractor"
    assert data["user"]["first_name"] == "Marek"
    assert data["user"]["last_name"] == "Nowak"
    assert data["user"]["language_code"] == "pl"
    assert "id" in data["user"]


@pytest.mark.asyncio
async def test_telegram_auth_relogin_reuses_same_user(async_client: AsyncClient):
    """Verifies that subsequent logins with the same Telegram user reuse the existing record."""
    user_payload = {
        "id": 777888999,
        "first_name": "Piotr",
        "last_name": "Zieliński",
        "username": "piotr_z",
        "language_code": "pl",
    }
    init_data = make_telegram_init_data(user_payload)

    # First login
    res1 = await async_client.post("/api/auth/telegram", json={"init_data": init_data})
    assert res1.status_code == 200
    user1_id = res1.json()["user"]["id"]

    # Reload / second login
    res2 = await async_client.post("/api/auth/telegram", json={"init_data": init_data})
    assert res2.status_code == 200
    user2_id = res2.json()["user"]["id"]

    # Same UUID must be reused
    assert user1_id == user2_id


@pytest.mark.asyncio
async def test_telegram_auth_invalid_signature(async_client: AsyncClient):
    """Verifies that tampered or invalid signatures are rejected with 401."""
    user_payload = {"id": 123456789, "username": "fraud"}
    init_data = make_telegram_init_data(user_payload, tamper_hash=True)

    response = await async_client.post("/api/auth/telegram", json={"init_data": init_data})
    assert response.status_code == 401
    detail = response.json().get("detail", {})
    assert detail.get("code") == "INVALID_TELEGRAM_SIGNATURE"


@pytest.mark.asyncio
async def test_telegram_auth_expired_data(async_client: AsyncClient):
    """Verifies that initData older than max_age is rejected with 401."""
    old_timestamp = int(datetime.now(timezone.utc).timestamp()) - (settings.TELEGRAM_AUTH_MAX_AGE_SECONDS + 500)
    user_payload = {"id": 123456789, "username": "expired_user"}
    init_data = make_telegram_init_data(user_payload, auth_date=old_timestamp)

    response = await async_client.post("/api/auth/telegram", json={"init_data": init_data})
    assert response.status_code == 401
    detail = response.json().get("detail", {})
    assert detail.get("code") == "TELEGRAM_AUTH_EXPIRED"


@pytest.mark.asyncio
async def test_telegram_auth_missing_data(async_client: AsyncClient):
    """Verifies that requests missing required fields fail with 400 or 422."""
    # Empty string
    res1 = await async_client.post("/api/auth/telegram", json={"init_data": ""})
    assert res1.status_code == 400
    assert res1.json().get("detail", {}).get("code") == "MISSING_TELEGRAM_DATA"

    # Missing hash
    user_payload = {"id": 123456789}
    init_data_no_hash = make_telegram_init_data(user_payload, omit_hash=True)
    res2 = await async_client.post("/api/auth/telegram", json={"init_data": init_data_no_hash})
    assert res2.status_code == 400
    assert res2.json().get("detail", {}).get("code") == "MISSING_TELEGRAM_DATA"


@pytest.mark.asyncio
async def test_telegram_auth_dev_mock_login(async_client: AsyncClient):
    """Verifies that mock auth works in development when MOCK_TELEGRAM_AUTH is True."""
    settings.APP_ENV = "development"
    settings.ENVIRONMENT = "development"
    settings.MOCK_TELEGRAM_AUTH = True

    # 1. First login
    response1 = await async_client.post("/api/auth/telegram", json={"init_data": "mock"})
    assert response1.status_code == 200
    data1 = response1.json()
    assert data1["is_dev_auth"] is True
    assert data1["user"]["telegram_user_id"] == 999999999
    assert data1["user"]["username"] == "dev_contractor"
    assert "access_token" in data1
    user1_id = data1["user"]["id"]

    # 2. Reload / second login -> same user reused
    response2 = await async_client.post("/api/auth/telegram", json={"init_data": "mock"})
    assert response2.status_code == 200
    data2 = response2.json()
    assert data2["user"]["id"] == user1_id


@pytest.mark.asyncio
async def test_telegram_auth_production_rejects_mock(async_client: AsyncClient):
    """Verifies that production environments strictly reject mock authentication."""
    settings.APP_ENV = "production"
    settings.ENVIRONMENT = "production"
    settings.MOCK_TELEGRAM_AUTH = True  # Even if set to true accidentally

    response = await async_client.post("/api/auth/telegram", json={"init_data": "mock"})
    assert response.status_code == 403
    detail = response.json().get("detail", {})
    assert detail.get("code") == "MOCK_AUTH_DISALLOWED_IN_PRODUCTION"


@pytest.mark.asyncio
async def test_get_me_flow(async_client: AsyncClient):
    """Verifies that GET /api/me requires a valid token and returns the current user."""
    # 1. Unauthorized request
    res_unauth = await async_client.get("/api/me")
    assert res_unauth.status_code == 401

    # 2. Login to get token
    user_payload = {"id": 555555, "first_name": "Anna", "username": "anna_pl"}
    init_data = make_telegram_init_data(user_payload)
    login_res = await async_client.post("/api/auth/telegram", json={"init_data": init_data})
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]

    # 3. Call GET /api/me with Bearer token
    res_me = await async_client.get(
        "/api/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_me.status_code == 200
    me_data = res_me.json()
    assert me_data["telegram_user_id"] == 555555
    assert me_data["username"] == "anna_pl"
    assert me_data["first_name"] == "Anna"
