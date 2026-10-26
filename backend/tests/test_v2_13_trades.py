"""V2-13: the packages of professions of an owner -- the rules, the catalogue, the API and the migration (docs/V2_13_PLAN_RU.md)."""
import pytest
from app.domain.rules import trades as T
from app.models.price_item import PriceCategory
from httpx import AsyncClient
from sqlalchemy import inspect

from tests.test_clients import OTHER_USER, VALID_USER
from tests.test_stage15f2_api import login
from tests.test_stage16e2_contract import contract_engine, load_migration, run


def test_the_trades_are_the_six_of_the_owner_with_microcement_before_the_tile():
    assert T.TRADE_KEYS == ("FINISHING", "DRYWALL", "MICROCEMENT", "TILE", "ELECTRIC", "PLUMBING")


def test_every_price_category_belongs_to_exactly_one_trade_or_to_all():
    owned = [c for t in T.TRADES for c in t.price_categories]
    assert len(owned) == len(set(owned)), "a category belongs to two trades"
    assert not set(owned) & set(T.ALWAYS_CATEGORIES)
    assert set(owned) | set(T.ALWAYS_CATEGORIES) == {c.value for c in PriceCategory}  # a new category must be placed on purpose


def test_the_material_packages_are_the_ones_the_database_knows_and_each_belongs_to_one_trade():
    from app.models.material import MaterialCalc

    check = next(c for c in MaterialCalc.__table__.constraints if getattr(c, "name", None) == "ck_material_calcs_package")
    known = {p.strip(" '") for p in str(check.sqltext).split("(", 1)[1].rstrip(")").split(",")}
    owned = [p for t in T.TRADES for p in t.material_packages]
    assert sorted(owned) == sorted(known) == sorted(set(owned))


def test_a_choice_is_canonical_known_and_may_be_empty():
    assert T.validate_enabled(["PLUMBING", "TILE", "TILE", "FINISHING"]) == ("FINISHING", "TILE", "PLUMBING")
    assert T.validate_enabled([]) == ()
    assert T.validate_enabled(T.TRADE_KEYS) == T.TRADE_KEYS


@pytest.mark.parametrize("bad,reason,key", [(["WELDING"], "UNKNOWN_TRADE", "WELDING"), (["tile"], "UNKNOWN_TRADE", "tile"), ([1], "WRONG_TYPE", None), ([None], "WRONG_TYPE", None)])
def test_an_unknown_or_wrong_entry_is_refused_with_its_reason(bad, reason, key):
    with pytest.raises(T.TradesError) as err:
        T.validate_enabled(bad)
    assert (err.value.reason, err.value.key) == (reason, key)


def test_nothing_chosen_means_every_trade_and_a_trade_that_no_longer_exists_is_ignored():
    assert T.enabled_of(None) == T.TRADE_KEYS
    assert T.enabled_of("junk") == T.TRADE_KEYS
    assert T.enabled_of([]) == ()
    assert T.enabled_of(["TILE", "WELDING", "FINISHING"]) == ("FINISHING", "TILE")


async def test_the_routes_need_a_token(async_client: AsyncClient):
    assert (await async_client.get("/api/trades")).status_code == 401
    assert (await async_client.put("/api/trades", json={"enabled": []})).status_code == 401


async def test_a_new_owner_has_every_trade_and_the_catalogue_comes_with_it(async_client: AsyncClient):
    headers = await login(async_client)
    body = (await async_client.get("/api/trades", headers=headers)).json()
    assert body["enabled"] == list(T.TRADE_KEYS)
    assert [t["key"] for t in body["trades"]] == list(T.TRADE_KEYS)
    tile = next(t for t in body["trades"] if t["key"] == "TILE")
    assert tile == {"key": "TILE", "price_categories": ["TILE"], "material_packages": ["TILE"], "room_points": True}
    assert [t["key"] for t in body["trades"] if t["room_points"]] == ["DRYWALL", "TILE", "ELECTRIC", "PLUMBING"]  # the finisher and the microcement do not work in points and routes
    assert body["always_categories"] == ["POINTS_ROUTES", "MATERIAL", "OTHER"]


async def test_the_choice_is_saved_in_the_canonical_order_per_owner_and_an_empty_one_is_kept(async_client: AsyncClient):
    mine = await login(async_client)
    other = await login(async_client, OTHER_USER)
    saved = await async_client.put("/api/trades", json={"enabled": ["TILE", "ELECTRIC", "TILE"]}, headers=mine)
    assert saved.status_code == 200 and saved.json()["enabled"] == ["TILE", "ELECTRIC"]
    assert (await async_client.get("/api/trades", headers=mine)).json()["enabled"] == ["TILE", "ELECTRIC"]
    assert (await async_client.get("/api/trades", headers=other)).json()["enabled"] == list(T.TRADE_KEYS)  # the other owner is untouched
    assert (await async_client.put("/api/trades", json={"enabled": []}, headers=mine)).json()["enabled"] == []
    assert (await async_client.get("/api/trades", headers=mine)).json()["enabled"] == []  # an empty choice is a choice, not "never chosen"
    assert VALID_USER["id"] != OTHER_USER["id"]


async def test_a_wrong_choice_is_refused_and_changes_nothing(async_client: AsyncClient):
    headers = await login(async_client)
    await async_client.put("/api/trades", json={"enabled": ["TILE"]}, headers=headers)
    bad = await async_client.put("/api/trades", json={"enabled": ["TILE", "WELDING"]}, headers=headers)
    assert bad.status_code == 422 and bad.json()["detail"] == {"code": "TRADES_INVALID", "message": "trades: UNKNOWN_TRADE ('WELDING')",
                                                              "details": {"reason": "UNKNOWN_TRADE", "key": "WELDING"}}
    assert (await async_client.put("/api/trades", json={"enabled": [5]}, headers=headers)).json()["detail"]["details"]["reason"] == "WRONG_TYPE"
    assert (await async_client.put("/api/trades", json={"enabled": "TILE"}, headers=headers)).status_code == 422
    assert (await async_client.put("/api/trades", json={"enabled": [], "extra": 1}, headers=headers)).status_code == 422
    assert (await async_client.get("/api/trades", headers=headers)).json()["enabled"] == ["TILE"]


def test_the_migration_adds_one_nullable_column_and_goes_back():
    module = load_migration("0084_user_trades")
    assert module.revision == "0084_user_trades" and module.down_revision == "0083_pressure_encrypted_text" and len(module.revision) <= 32
    engine = contract_engine()
    run(engine, "0084_user_trades", "upgrade")
    column = next(c for c in inspect(engine).get_columns("users") if c["name"] == "trades")
    assert column["nullable"] is True
    run(engine, "0084_user_trades", "downgrade")
    assert "trades" not in {c["name"] for c in inspect(engine).get_columns("users")}
    run(engine, "0084_user_trades", "upgrade")
