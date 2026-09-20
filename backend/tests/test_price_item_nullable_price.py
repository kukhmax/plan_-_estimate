"""Stage 9E.7 nullable-price tests, corrected by Stage 10G.4.

The owner-approved contract: ``price = null`` renders "Do ustalenia / Уточняется"
and ``price = 0.00`` renders "0,00 zł" — zero is a real price and is never reused
as a "not set" sentinel.

Stage 10G.4 correction (owner-directed, supersedes the original Stage 9E.7
restriction below): on-site inline Price Book creation requires that a custom
item CAN be created with an unresolved price, and that an existing price CAN
be explicitly cleared back to NULL via PATCH. The two behaviors this replaces
were, until this stage, deliberately the opposite:
- custom create used to REQUIRE an explicit price (no NULL allowed on create);
- an explicit ``"price": null`` via PATCH used to be a no-op (could never
  re-null an already-priced row).
Both restrictions are lifted here. Nothing ever converts NULL into 0.00 or
vice versa; zero and "unresolved" remain fully distinct in both directions.
"""
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select

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

    async def test_update_omission_leaves_price_unchanged(self, db_session):
        owner = await _make_user(db_session, 8105)
        service = PriceBookService(db_session)
        item = await _seed_item(db_session, service, owner.id)
        # price kwarg omitted entirely (sentinel default): must stay NULL.
        untouched = await service.update_item(owner.id, item.id, display_name="Bez ceny")
        assert untouched.price is None

    async def test_update_explicit_null_clears_an_existing_price(self, db_session):
        """Stage 10G.4: explicit price=None now actually re-nulls a priced row,
        rather than being a silent no-op — the owner must be able to walk back
        an inline-agreed price to "Do ustalenia" if it turns out unresolved."""
        owner = await _make_user(db_session, 8107)
        service = PriceBookService(db_session)
        item = await service.create_custom_item(
            owner.id,
            category=PriceCategory.PAINTING,
            unit=PriceUnit.M2,
            price=Decimal("15.00"),
            display_name="Do skorygowania",
        )
        assert item.price == Decimal("15.00")

        cleared = await service.update_item(owner.id, item.id, price=None)
        assert cleared.price is None

        refetched = await service.get_owned_item(owner.id, item.id)
        assert refetched.price is None

    async def test_custom_create_allows_null_price(self, db_session):
        """Stage 10G.4: a custom row may be created with an unresolved price —
        an on-site owner cannot always agree a price before creating the row."""
        owner = await _make_user(db_session, 8106)
        service = PriceBookService(db_session)
        item = await service.create_custom_item(
            owner.id,
            category=PriceCategory.PAINTING,
            unit=PriceUnit.M2,
            price=None,
            display_name="Cena do ustalenia",
        )
        assert item.price is None
        refetched = await service.get_owned_item(owner.id, item.id)
        assert refetched.price is None


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

    async def test_patch_explicit_null_clears_an_existing_price(self, async_client: AsyncClient):
        """Stage 10G.4: explicit "price": null now actually re-nulls a priced
        row via the API, distinct from simply omitting the field."""
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
        assert resp.status_code == 200, resp.text
        assert resp.json()["price"] is None

    async def test_patch_omitting_price_leaves_it_unchanged(self, async_client: AsyncClient):
        """Omission (the field absent from the JSON body) must remain distinct
        from an explicit "price": null — omission never mutates the price."""
        headers = await self._headers(async_client)
        items = (
            await async_client.get("/api/price-items", headers=headers)
        ).json()["items"]
        prep = next(i for i in items if i["code"] == "CENNIK_PREP_WALLP-01")
        await async_client.patch(
            f"/api/price-items/{prep['id']}", headers=headers, json={"price": "20.00"}
        )
        resp = await async_client.patch(
            f"/api/price-items/{prep['id']}", headers=headers, json={"display_name": "Bez zmiany ceny"}
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["price"] == "20.00"

    async def test_custom_create_omitted_price_is_null(self, async_client: AsyncClient):
        """Stage 10G.4: omitting price on create is now a valid "Do ustalenia"
        row — required-price-on-create was the original Stage 9E.7 restriction,
        lifted for on-site inline creation."""
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
        assert resp.status_code == 201, resp.text
        assert resp.json()["price"] is None

    async def test_custom_create_explicit_null_price(self, async_client: AsyncClient):
        headers = await self._headers(async_client)
        resp = await async_client.post(
            "/api/price-items",
            headers=headers,
            json={
                "display_name": "Cena do ustalenia",
                "category": "PAINTING",
                "unit": "M2",
                "price": None,
            },
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["price"] is None

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