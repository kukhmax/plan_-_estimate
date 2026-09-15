"""Stage 9E.7 nullable-price tests: NULL = owner price not set (9E.7).

The owner-approved contract: ``price = null`` renders "Do ustalenia / Уточняется"
and ``price = 0.00`` renders "0,00 zł" — zero is a real price and is never reused
as a "not set" sentinel. Custom create still requires an explicit price; PATCH
sets a real price on a null seed row; an explicit null via PATCH is a no-op and
nothing ever converts NULL into 0.00.
"""
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.domain.exceptions import PriceBookValidationError
from app.domain.services.price_book_service import PriceBookService
from app.models.price_item import PriceCategory, PriceItem, PriceUnit
from tests.conftest import make_telegram_init_data

VALID_USER = {
    "id": 555555555,
    "username": "nullable",
    "first_name": "Nullable",
    "last_name": "Price",
    "language_code": "pl",
}


async def _make_user(db, telegram_id: int):
    from app.models import User

    user = User(telegram_user_id=telegram_id, username=f"user{telegram_id}")
    db.add(user)
    await db.commit()
    return user


async def _seed_item(db, service: PriceBookService, owner_id) -> PriceItem:
    await service.ensure_owner_catalog(owner_id)
    items = await service.list_owner_items(owner_id)
    return next(i for i in items if i.code == "CENNIK_PREP_WALLP-01")


# ---------------------------------------------------------------------------
# Service level
# ---------------------------------------------------------------------------

class TestNullablePriceService:
    async def test_seed_rows_persist_null_price(self, db_session):
        owner = await _make_user(db_session, 8101)
        service = PriceBookService(db_session)
        item = await _seed_item(db_session, service, owner.id)
        assert item.price is None
        fetched = (
            await db_session.execute(
                select(PriceItem).where(PriceItem.id == item.id)
            )
        ).scalar_one()
        assert fetched.price is None  # persisted as NULL, not 0

    async def test_explicit_zero_distinct_from_null(self, db_session):
        owner = await _make_user(db_session, 8102)
        service = PriceBookService(db_session)
        null_item = await _seed_item(db_session, service, owner.id)
        zero_item = await service.create_custom_item(
            owner.id,
            category=PriceCategory.PREPARATION,
            unit=PriceUnit.M2,
            price=Decimal("0.00"),
            display_name="Zero cenowe",
        )
        assert null_item.price is None
        assert zero_item.price == Decimal("0.00")
        assert (null_item.price is None) != (zero_item.price is None)

    async def test_positive_price(self, db_session):
        owner = await _make_user(db_session, 8103)
        service = PriceBookService(db_session)
        item = await service.create_custom_item(
            owner.id,
            category=PriceCategory.PAINTING,
            unit=PriceUnit.M2,
            price=Decimal("12.50"),
            display_name="Pozycja z ceną",
        )
        assert item.price == Decimal("12.50")

    async def test_seed_row_qualified_from_null_by_update(self, db_session):
        """update_item sets a real price on a NULL seed row (still no 0 conversion)."""
        owner = await _make_user(db_session, 8104)
        service = PriceBookService(db_session)
        item = await _seed_item(db_session, service, owner.id)
        updated = await service.update_item(owner.id, item.id, price=Decimal("25.00"))
        assert updated.price == Decimal("25.00")
        refetched = await service.get_owned_item(owner.id, item.id)
        assert refetched.price == Decimal("25.00")

    async def test_update_never_converts_null_to_zero(self, db_session):
        owner = await _make_user(db_session, 8105)
        service = PriceBookService(db_session)
        item = await _seed_item(db_session, service, owner.id)
        # price omitted (None == omitted on this path): must stay NULL, not become 0.00.
        untouched = await service.update_item(owner.id, item.id, display_name="Bez ceny")
        assert untouched.price is None
        # explicit None is a no-op, never a conversion.
        again = await service.update_item(owner.id, item.id, price=None)
        assert again.price is None

    async def test_custom_create_requires_explicit_price(self, db_session):
        """There is no way to create a custom row without an explicit price."""
        owner = await _make_user(db_session, 8106)
        service = PriceBookService(db_session)
        with pytest.raises(
            (TypeError, PriceBookValidationError), match="price"
        ):
            await service.create_custom_item(
                owner.id,
                category=PriceCategory.PAINTING,
                unit=PriceUnit.M2,
                display_name="Brak ceny",
            )


# ---------------------------------------------------------------------------
# API level
# ---------------------------------------------------------------------------

class TestNullablePriceApi:
    async def _headers(self, async_client: AsyncClient) -> dict:
        resp = await async_client.post(
            "/api/auth/telegram", json={"init_data": make_telegram_init_data(VALID_USER)}
        )
        assert resp.status_code == 200, resp.text
        return {"Authorization": f"Bearer {resp.json()['access_token']}"}

    async def test_seed_item_price_null_in_json(self, async_client: AsyncClient):
        headers = await self._headers(async_client)
        items = (
            await async_client.get("/api/price-items", headers=headers)
        ).json()["items"]
        prep = next(i for i in items if i["code"] == "CENNIK_PREP_WALLP-01")
        assert prep["price"] is None  # JSON null, never "0.00"

    async def test_patch_sets_price_on_null_seed_row(self, async_client: AsyncClient):
        headers = await self._headers(async_client)
        items = (
            await async_client.get("/api/price-items", headers=headers)
        ).json()["items"]
        prep = next(i for i in items if i["code"] == "CENNIK_PREP_WALLP-01")
        resp = await async_client.patch(
            f"/api/price-items/{prep['id']}",
            headers=headers,
            json={"price": "20.00"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["price"] == "20.00"

    async def test_patch_explicit_null_is_noop(self, async_client: AsyncClient):
        headers = await self._headers(async_client)
        items = (
            await async_client.get("/api/price-items", headers=headers)
        ).json()["items"]
        prep = next(i for i in items if i["code"] == "CENNIK_PREP_WALLP-01")
        await async_client.patch(
            f"/api/price-items/{prep['id']}", headers=headers, json={"price": "20.00"}
        )
        resp = await async_client.patch(
            f"/api/price-items/{prep['id']}", headers=headers, json={"price": None}
        )
        # Explicit null is a no-op: the set price survives, 0.00 is never injected.
        assert resp.status_code == 200, resp.text
        assert resp.json()["price"] == "20.00"

    async def test_custom_create_missing_price_422(self, async_client: AsyncClient):
        headers = await self._headers(async_client)
        resp = await async_client.post(
            "/api/price-items",
            headers=headers,
            json={
                "display_name": "Pozycja bez ceny",
                "category": "PAINTING",
                "unit": "M2",
            },
        )
        assert resp.status_code == 422, resp.text

    async def test_custom_create_explicit_zero_roundtrips(self, async_client: AsyncClient):
        headers = await self._headers(async_client)
        resp = await async_client.post(
            "/api/price-items",
            headers=headers,
            json={
                "display_name": "Zero cenowe",
                "category": "PAINTING",
                "unit": "M2",
                "price": "0.00",
            },
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["price"] == "0.00"

    async def test_custom_zero_cannot_collide_with_seed_null(self, async_client: AsyncClient):
        headers = await self._headers(async_client)
        items = (
            await async_client.get("/api/price-items", headers=headers)
        ).json()["items"]
        zero_item = (
            await async_client.post(
                "/api/price-items",
                headers=headers,
                json={
                    "display_name": "Promocyjne 0 zł",
                    "category": "MATERIAL",
                    "unit": "PCS",
                    "price": "0.00",
                },
            )
        ).json()
        assert zero_item["price"] == "0.00"
        # Seed rows stay NULL — a real 0.00 and an unset price are distinct.
        assert all(i["price"] is None for i in items)