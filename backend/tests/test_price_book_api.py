"""Focused Stage 9C API tests: owner-scoped Price Book endpoints.

Covers unauthenticated 401s, bootstrap-on-list, HTTP-level seed regression
(owner edits survive re-bootstrap), all list filters, the custom-item
lifecycle, money/currency/display-name/enum/code validation, and A/B owner
isolation with uniform 404s.
"""
import pytest
from httpx import AsyncClient

from tests.conftest import make_telegram_init_data

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

SEED_CODES = {
    "CENNIK_PREP_GENERIC_M2",
    "CENNIK_PAINT_GENERIC_M2",
    "CENNIK_REVEAL_GENERIC_M2",
    "CENNIK_REVEAL_GENERIC_LM",
}


async def get_token(async_client: AsyncClient, user_dict: dict) -> str:
    init_data = make_telegram_init_data(user_dict)
    resp = await async_client.post("/api/auth/telegram", json={"init_data": init_data})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def custom_payload(**overrides) -> dict:
    payload = dict(
        display_name="Malowanie lateksowe dwukrotnie",
        category="PAINTING",
        unit="M2",
        price="9.99",
    )
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Unauthenticated access
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/api/price-items"),
        ("POST", "/api/price-items"),
        ("GET", "/api/price-items/00000000-0000-0000-0000-000000000000"),
        ("PATCH", "/api/price-items/00000000-0000-0000-0000-000000000000"),
        ("POST", "/api/price-items/00000000-0000-0000-0000-000000000000/archive"),
        ("POST", "/api/price-items/00000000-0000-0000-0000-000000000000/restore"),
    ],
)
async def test_unauthenticated_401(async_client: AsyncClient, method: str, path: str):
    resp = await async_client.request(method, path)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Bootstrap-on-access + seed regression (critical invariant)
# ---------------------------------------------------------------------------

async def test_first_list_bootstraps_owner_catalog(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    resp = await async_client.get("/api/price-items", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 4
    assert {i["code"] for i in data["items"]} == SEED_CODES
    # Seed rows localize via name_key; placeholders never marked as market data.
    for item in data["items"]:
        assert item["name_key"] is not None
        assert item["display_name"] is None
        assert item["is_archived"] is False


async def test_seeded_edit_survives_rebootstrap(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)

    resp = await async_client.get("/api/price-items", headers=headers)
    prep = next(
        i for i in resp.json()["items"] if i["code"] == "CENNIK_PREP_GENERIC_M2"
    )

    resp = await async_client.patch(
        f"/api/price-items/{prep['id']}",
        headers=headers,
        json={"price": "12.50", "display_name": "Gruntowanie (własna cena)"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["price"] == "12.50"

    # Second list re-bootstraps; the owner edit must be untouched and the
    # catalog must not have grown.
    resp = await async_client.get("/api/price-items", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 4
    by_code = {i["code"]: i for i in data["items"]}
    assert by_code["CENNIK_PREP_GENERIC_M2"]["price"] == "12.50"
    assert by_code["CENNIK_PREP_GENERIC_M2"]["display_name"] == "Gruntowanie (własna cena)"


# ---------------------------------------------------------------------------
# List filters
# ---------------------------------------------------------------------------

async def _bootstrap_and_seed_catalog(async_client: AsyncClient, headers: dict) -> dict:
    """Bootstrap, add one custom PAINTING/Q3 item, archive one REVEAL seed."""
    await async_client.get("/api/price-items", headers=headers)
    created = await async_client.post(
        "/api/price-items",
        headers=headers,
        json=custom_payload(price_scope="LABOR", quality_level="Q3"),
    )
    custom_id = created.json()["id"]
    items = (
        await async_client.get(
            "/api/price-items", headers=headers, params={"archived": "all"}
        )
    ).json()["items"]
    lm = next(i for i in items if i["code"] == "CENNIK_REVEAL_GENERIC_LM")
    await async_client.post(f"/api/price-items/{lm['id']}/archive", headers=headers)
    return {"custom_id": custom_id, "archived_id": lm["id"]}


async def test_list_archived_filter(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    await _bootstrap_and_seed_catalog(async_client, headers)

    active = (
        await async_client.get("/api/price-items", headers=headers)
    ).json()
    assert active["total"] == 4  # 3 active seeds + 1 custom
    assert all(not i["is_archived"] for i in active["items"])

    archived = (
        await async_client.get(
            "/api/price-items", headers=headers, params={"archived": "archived"}
        )
    ).json()
    assert archived["total"] == 1
    assert archived["items"][0]["code"] == "CENNIK_REVEAL_GENERIC_LM"

    all_items = (
        await async_client.get(
            "/api/price-items", headers=headers, params={"archived": "all"}
        )
    ).json()
    assert all_items["total"] == 5


async def test_list_entity_filters(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    ids = await _bootstrap_and_seed_catalog(async_client, headers)

    resp = await async_client.get(
        "/api/price-items", headers=headers, params={"category": "PAINTING"}
    )
    data = resp.json()
    assert data["total"] == 2  # CENNIK_PAINT_GENERIC_M2 + custom
    assert {i["category"] for i in data["items"]} == {"PAINTING"}

    resp = await async_client.get(
        "/api/price-items", headers=headers, params={"unit": "M2"}
    )
    assert all(i["unit"] == "M2" for i in resp.json()["items"])

    resp = await async_client.get(
        "/api/price-items", headers=headers, params={"price_scope": "LABOR"}
    )
    assert all(i["price_scope"] == "LABOR" for i in resp.json()["items"])

    resp = await async_client.get(
        "/api/price-items", headers=headers, params={"quality_level": "Q3"}
    )
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["id"] == ids["custom_id"]


async def test_list_search(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    ids = await _bootstrap_and_seed_catalog(async_client, headers)

    # display_name match
    resp = await async_client.get(
        "/api/price-items", headers=headers, params={"search": "lateksowe"}
    )
    assert resp.json()["total"] == 1
    assert resp.json()["items"][0]["id"] == ids["custom_id"]

    # code match
    resp = await async_client.get(
        "/api/price-items", headers=headers, params={"search": "CENNIK_PAINT"}
    )
    assert {i["code"] for i in resp.json()["items"]} == {"CENNIK_PAINT_GENERIC_M2"}

    # name_key match (seeded identity, localized client-side)
    resp = await async_client.get(
        "/api/price-items",
        headers=headers,
        params={"search": "pricebook.seed.paint"},
    )
    assert resp.json()["total"] == 1


async def test_list_stable_ordering(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    await _bootstrap_and_seed_catalog(async_client, headers)

    async def ids() -> list[str]:
        return [
            i["id"]
            for i in (
                await async_client.get(
                    "/api/price-items",
                    headers=headers,
                    params={"archived": "all"},
                )
            ).json()["items"]
        ]

    first, second = await ids(), await ids()
    assert first == second
    # Archived rows sort strictly after active rows in the "all" view.
    active_flags = [
        i["is_archived"]
        for i in (
            await async_client.get(
                "/api/price-items", headers=headers, params={"archived": "all"}
            )
        ).json()["items"]
    ]
    assert active_flags == sorted(active_flags)


# ---------------------------------------------------------------------------
# Custom item lifecycle
# ---------------------------------------------------------------------------

async def test_custom_item_full_lifecycle(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)

    resp = await async_client.post(
        "/api/price-items", headers=headers, json=custom_payload()
    )
    assert resp.status_code == 201, resp.text
    item = resp.json()
    item_id = item["id"]
    code = item["code"]
    assert code.startswith("CUSTOM_")
    assert item["name_key"] is None
    assert item["currency"] == "PLN"
    assert item["price_scope"] == "LABOR"
    assert item["quality_level"] is None
    assert item["is_archived"] is False

    detail = (
        await async_client.get(f"/api/price-items/{item_id}", headers=headers)
    ).json()
    assert detail["code"] == code

    updated = (
        await async_client.patch(
            f"/api/price-items/{item_id}",
            headers=headers,
            json={"price": "49.99", "display_name": "Malowanie lateksowe, 2 warstwy"},
        )
    ).json()
    assert updated["price"] == "49.99"
    assert updated["display_name"] == "Malowanie lateksowe, 2 warstwy"
    assert updated["code"] == code

    archived = (
        await async_client.post(f"/api/price-items/{item_id}/archive", headers=headers)
    ).json()
    assert archived["is_archived"] is True

    active_ids = {
        i["id"] for i in (await async_client.get("/api/price-items", headers=headers)).json()["items"]
    }
    assert item_id not in active_ids

    archived_ids = {
        i["id"]
        for i in (
            await async_client.get(
                "/api/price-items", headers=headers, params={"archived": "archived"}
            )
        ).json()["items"]
    }
    assert item_id in archived_ids

    restored = (
        await async_client.post(f"/api/price-items/{item_id}/restore", headers=headers)
    ).json()
    assert restored["is_archived"] is False

    active_ids = {
        i["id"] for i in (await async_client.get("/api/price-items", headers=headers)).json()["items"]
    }
    assert item_id in active_ids

    final = (
        await async_client.get(f"/api/price-items/{item_id}", headers=headers)
    ).json()
    assert final["code"] == code  # semantic code immutable across the whole flow


async def test_archive_restore_idempotent(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    item_id = (
        await async_client.post(
            "/api/price-items", headers=headers, json=custom_payload()
        )
    ).json()["id"]

    first = await async_client.post(f"/api/price-items/{item_id}/archive", headers=headers)
    second = await async_client.post(f"/api/price-items/{item_id}/archive", headers=headers)
    assert first.status_code == second.status_code == 200
    assert second.json()["is_archived"] is True

    first = await async_client.post(f"/api/price-items/{item_id}/restore", headers=headers)
    second = await async_client.post(f"/api/price-items/{item_id}/restore", headers=headers)
    assert first.status_code == second.status_code == 200
    assert second.json()["is_archived"] is False


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "price,expected",
    [
        ("0", "0"),
        ("0.00", "0.00"),
        ("45", "45"),
        ("45.5", "45.5"),
        ("45.50", "45.50"),
    ],
)
async def test_price_accepted_and_canonical(
    async_client: AsyncClient, price: str, expected: str
):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    resp = await async_client.post(
        "/api/price-items", headers=headers, json=custom_payload(price=price)
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["price"] == expected


@pytest.mark.parametrize("price", ["-1", "-0.01", "1.234", "45.500", "NaN", "Infinity", "-Infinity"])
async def test_price_invalid_rejected(async_client: AsyncClient, price: str):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    resp = await async_client.post(
        "/api/price-items", headers=headers, json=custom_payload(price=price)
    )
    assert resp.status_code == 422, resp.text


async def test_currency_euro_rejected(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    resp = await async_client.post(
        "/api/price-items", headers=headers, json=custom_payload(currency="EUR")
    )
    assert resp.status_code == 422


async def test_blank_custom_display_name_rejected(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    for name in ("", "   "):
        resp = await async_client.post(
            "/api/price-items",
            headers=headers,
            json=custom_payload(display_name=name),
        )
        assert resp.status_code == 422, resp.text


@pytest.mark.parametrize(
    "field,value",
    [
        ("category", "NOT_A_CATEGORY"),
        ("unit", "M3"),
        ("price_scope", "BOTH"),
        ("quality_level", "S5"),
    ],
)
async def test_unknown_enum_rejected(async_client: AsyncClient, field: str, value: str):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    resp = await async_client.post(
        "/api/price-items", headers=headers, json=custom_payload(**{field: value})
    )
    assert resp.status_code == 422, resp.text


async def test_client_cannot_supply_semantic_code(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)

    resp = await async_client.post(
        "/api/price-items",
        headers=headers,
        json={**custom_payload(), "code": "CUSTOM_EVIL00001"},
    )
    assert resp.status_code == 422, resp.text  # extra field forbidden

    item_id = (
        await async_client.post(
            "/api/price-items", headers=headers, json=custom_payload()
        )
    ).json()["id"]
    resp = await async_client.patch(
        f"/api/price-items/{item_id}",
        headers=headers,
        json={"code": "CUSTOM_EVIL00001"},
    )
    assert resp.status_code == 422, resp.text
    detail = (
        await async_client.get(f"/api/price-items/{item_id}", headers=headers)
    ).json()
    assert detail["code"].startswith("CUSTOM_")


async def test_patch_preserves_omitted_fields(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    item = (
        await async_client.post(
            "/api/price-items",
            headers=headers,
            json=custom_payload(quality_level="Q3", price_scope="LABOR_AND_MATERIAL"),
        )
    ).json()
    resp = await async_client.patch(
        f"/api/price-items/{item['id']}",
        headers=headers,
        json={"price": "11.11"},  # only price changes
    )
    body = resp.json()
    assert body["price"] == "11.11"
    assert body["display_name"] == item["display_name"]
    assert body["category"] == item["category"]
    assert body["unit"] == item["unit"]
    assert body["price_scope"] == "LABOR_AND_MATERIAL"
    assert body["quality_level"] == "Q3"
    assert body["code"] == item["code"]


async def test_quality_level_clear_to_null(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    item = (
        await async_client.post(
            "/api/price-items", headers=headers, json=custom_payload(quality_level="Q3")
        )
    ).json()
    resp = await async_client.patch(
        f"/api/price-items/{item['id']}", headers=headers, json={"quality_level": None}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["quality_level"] is None


async def test_seeded_display_override_and_clear(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    seed = (
        await async_client.get("/api/price-items", headers=headers)
    ).json()["items"][0]

    overridden = (
        await async_client.patch(
            f"/api/price-items/{seed['id']}",
            headers=headers,
            json={"display_name": "Własna nazwa pozycji"},
        )
    ).json()
    assert overridden["display_name"] == "Własna nazwa pozycji"
    assert overridden["name_key"] == seed["name_key"]
    assert overridden["code"] == seed["code"]

    cleared = (
        await async_client.patch(
            f"/api/price-items/{seed['id']}", headers=headers, json={"display_name": ""}
        )
    ).json()
    assert cleared["display_name"] is None  # reverts to the name_key identity
    assert cleared["name_key"] == seed["name_key"]


# ---------------------------------------------------------------------------
# Ownership isolation
# ---------------------------------------------------------------------------

async def test_ownership_isolation(async_client: AsyncClient):
    token_a = await get_token(async_client, VALID_USER)
    token_b = await get_token(async_client, OTHER_USER)
    headers_a = auth_header(token_a)
    headers_b = auth_header(token_b)

    # A bootstraps its own catalog (4 seed rows).
    resp = await async_client.get("/api/price-items", headers=headers_a)
    assert resp.json()["total"] == 4
    a_seed_ids = {i["id"] for i in resp.json()["items"]}

    # B's first list bootstraps B's OWN editable copies (same codes, distinct
    # rows) — it must never contain any of A's row ids.
    resp = await async_client.get("/api/price-items", headers=headers_b)
    assert resp.status_code == 200
    b_ids = {i["id"] for i in resp.json()["items"]}
    assert b_ids.isdisjoint(a_seed_ids)

    created = (
        await async_client.post(
            "/api/price-items", headers=headers_a, json=custom_payload(price="8.88")
        )
    ).json()
    a_item_id = created["id"]
    a_code = created["code"]

    # A sees only its own rows (4 seeds + 1 custom).
    assert (
        await async_client.get("/api/price-items", headers=headers_a)
    ).json()["total"] == 5
    # B never gains visibility of A's custom or seeded rows.
    resp = await async_client.get("/api/price-items", headers=headers_b)
    b_ids = {i["id"] for i in resp.json()["items"]}
    assert b_ids.isdisjoint(a_seed_ids)
    assert a_item_id not in b_ids

    # A get → 200
    assert (
        await async_client.get(f"/api/price-items/{a_item_id}", headers=headers_a)
    ).status_code == 200

    # B attempts against A's item — uniform 404, no existence leak.
    assert (
        await async_client.get(f"/api/price-items/{a_item_id}", headers=headers_b)
    ).status_code == 404
    assert (
        await async_client.patch(
            f"/api/price-items/{a_item_id}", headers=headers_b, json={"price": "0.01"}
        )
    ).status_code == 404
    assert (
        await async_client.post(f"/api/price-items/{a_item_id}/archive", headers=headers_b)
    ).status_code == 404
    assert (
        await async_client.post(f"/api/price-items/{a_item_id}/restore", headers=headers_b)
    ).status_code == 404

    # A's item is unchanged by B's attempts.
    fresh = (
        await async_client.get(f"/api/price-items/{a_item_id}", headers=headers_a)
    ).json()
    assert fresh["price"] == "8.88"
    assert fresh["is_archived"] is False
    assert fresh["code"] == a_code


# ---------------------------------------------------------------------------
# Missing / foreign id
# ---------------------------------------------------------------------------

async def test_unknown_item_404(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    headers = auth_header(token)
    missing = "00000000-0000-0000-0000-000000000000"
    assert (
        await async_client.get(f"/api/price-items/{missing}", headers=headers)
    ).status_code == 404
    assert (
        await async_client.patch(f"/api/price-items/{missing}", headers=headers, json={"price": "1.00"})
    ).status_code == 404
    assert (
        await async_client.post(f"/api/price-items/{missing}/archive", headers=headers)
    ).status_code == 404
    assert (
        await async_client.post(f"/api/price-items/{missing}/restore", headers=headers)
    ).status_code == 404