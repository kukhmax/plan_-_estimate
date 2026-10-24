"""V2-3 -- the starter prices and the example object of an account (docs/V2_3_PLAN_RU.md)."""
import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select, text

from app.core.config import settings
from app.core.data_crypto import is_encrypted
from app.domain.data.demo_data import DEMO_PROJECT_NAME
from app.domain.data.onboarding_data import STARTER_PRICE_CODES
from app.domain.services.password_login_service import PasswordLoginService
from app.models.client import Client
from app.models.price_item import PriceItem
from app.models.project import Project
from app.models.room import Room

PASSWORD = "correct horse battery"


@pytest.fixture
def web(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_PASSWORD_ENABLED", True)


async def _signed_in(client: AsyncClient, db, email="jan@example.pl") -> dict:
    await PasswordLoginService(db).create_account(email, "Jan", PASSWORD)
    token = (await client.post("/api/auth/password", json={"email": email, "password": PASSWORD})).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


async def _count(db, model, *conditions) -> int:
    return int((await db.execute(select(func.count()).select_from(model).where(*conditions))).scalar_one())


def test_the_starter_rows_are_five_distinct_catalog_codes():
    from app.domain.data.price_book_seed import (
        build_approved_price_book_items,
    )

    assert len(STARTER_PRICE_CODES) == 5 == len(set(STARTER_PRICE_CODES))
    assert set(STARTER_PRICE_CODES) <= {seed.code for seed in build_approved_price_book_items()}


async def test_the_starter_prices_are_the_five_rows_in_order_without_a_price(async_client: AsyncClient, db_session, web):
    headers = await _signed_in(async_client, db_session)
    response = await async_client.get("/api/onboarding/starter-prices", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["code"] for item in body["items"]] == list(STARTER_PRICE_CODES) and body["total"] == 5
    assert all(item["price"] is None for item in body["items"])  # nothing is filled in for the owner


async def test_a_price_set_by_the_owner_shows_in_the_starter_rows(async_client: AsyncClient, db_session, web):
    headers = await _signed_in(async_client, db_session)
    first = (await async_client.get("/api/onboarding/starter-prices", headers=headers)).json()["items"][2]
    saved = await async_client.patch(f"/api/price-items/{first['id']}", json={"price": "48.00"}, headers=headers)
    assert saved.status_code == 200, saved.text
    again = (await async_client.get("/api/onboarding/starter-prices", headers=headers)).json()["items"]
    assert [item["price"] for item in again] == [None, None, "48.00", None, None]


async def test_the_example_is_made_once_listed_and_deleted(async_client: AsyncClient, db_session, web):
    headers = await _signed_in(async_client, db_session)
    empty = (await async_client.get("/api/onboarding/example", headers=headers)).json()
    assert empty == {"project_id": None, "client_id": None}

    made = await async_client.post("/api/onboarding/example", headers=headers)
    assert made.status_code == 200, made.text
    body = made.json()
    assert body["created"] is True and body["project_id"] and body["client_id"]
    assert await _count(db_session, Room, Room.project_id == uuid.UUID(body["project_id"])) == 5
    assert await _count(db_session, PriceItem) == 0  # the example sets no price (not even the catalog is made)

    again = (await async_client.post("/api/onboarding/example", headers=headers)).json()
    assert again["created"] is False and again["project_id"] == body["project_id"]
    assert await _count(db_session, Project) == 1 and await _count(db_session, Client) == 1
    projects = (await async_client.get("/api/projects", headers=headers)).json()["items"]
    assert [p["name"] for p in projects] == [DEMO_PROJECT_NAME]
    assert (await async_client.get("/api/onboarding/example", headers=headers)).json()["project_id"] == body["project_id"]

    removed = await async_client.delete("/api/onboarding/example", headers=headers)
    assert removed.status_code == 200 and removed.json() == {"removed_project": True, "removed_client": True}
    assert await _count(db_session, Project) == 0 and await _count(db_session, Client) == 0
    assert (await async_client.get("/api/onboarding/example", headers=headers)).json()["project_id"] is None


async def test_deleting_the_example_leaves_the_prices_the_owner_set(async_client: AsyncClient, db_session, web):
    headers = await _signed_in(async_client, db_session)
    item = (await async_client.get("/api/onboarding/starter-prices", headers=headers)).json()["items"][0]
    await async_client.patch(f"/api/price-items/{item['id']}", json={"price": "3.00"}, headers=headers)  # the same as the demo value on purpose
    await async_client.post("/api/onboarding/example", headers=headers)
    await async_client.delete("/api/onboarding/example", headers=headers)
    price = (await db_session.execute(select(PriceItem.price).where(PriceItem.code == STARTER_PRICE_CODES[0]))).scalar_one()
    assert price == Decimal("3.00")


async def test_the_example_of_one_account_is_not_the_example_of_another(async_client: AsyncClient, db_session, web):
    first = await _signed_in(async_client, db_session)
    second = await _signed_in(async_client, db_session, "ola@example.pl")
    await async_client.post("/api/onboarding/example", headers=first)
    assert (await async_client.get("/api/onboarding/example", headers=second)).json()["project_id"] is None
    await async_client.delete("/api/onboarding/example", headers=second)  # nothing to delete: the other account's example stays
    assert await _count(db_session, Project) == 1


async def test_the_example_is_ciphertext_in_the_database_and_readable_in_strict_mode(async_client: AsyncClient, db_session, web, encryption_on, monkeypatch):
    monkeypatch.setattr(settings, "DATA_STRICT_READ", True)
    headers = await _signed_in(async_client, db_session)
    made = await async_client.post("/api/onboarding/example", headers=headers)
    assert made.status_code == 200, made.text
    assert is_encrypted((await db_session.execute(text("select name from projects"))).scalar_one())
    assert (await async_client.get("/api/projects", headers=headers)).status_code == 200
    assert (await async_client.get("/api/clients", headers=headers)).status_code == 200
    assert (await async_client.delete("/api/onboarding/example", headers=headers)).json()["removed_project"] is True


@pytest.mark.parametrize("method,path", [("get", "/api/onboarding/starter-prices"), ("get", "/api/onboarding/example"), ("post", "/api/onboarding/example"), ("delete", "/api/onboarding/example")])
async def test_every_onboarding_route_needs_a_token(async_client: AsyncClient, method, path):
    assert (await getattr(async_client, method)(path)).status_code == 401
