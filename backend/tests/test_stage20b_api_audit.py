"""Stage 20B -- audit of the whole API contract: every operation is guarded, and no operation answers 5xx to a wrong request.

The operations are read from the OpenAPI contract of the application, so a route added later is covered without touching this file.
"""
import re
import uuid

import pytest
from httpx import AsyncClient

from app.main import app
from tests.conftest import make_telegram_init_data

# V2-1: the two entrances of a browser without Telegram are open as well: the answer of the configuration and the password login itself.
OPEN_OPERATIONS = {
    ("GET", "/api/health"),
    ("POST", "/api/auth/telegram"),
    ("GET", "/api/auth/config"),
    ("POST", "/api/auth/password"),
    # V2-8: the page of the client; the secret of the link in the header is the only door (tests/test_v2_8_client_link.py)
    ("GET", "/api/public/client"),
    ("POST", "/api/public/client/estimate/decide"),
    ("POST", "/api/public/client/proposals/{proposal_id}/decide"),
    # owner 2026-10-31: "why these works" on the client's page -- the same secret of the link (tests/test_client_why.py)
    ("GET", "/api/public/client/why"),
    # owner 2026-10-31: the PDF of a share / download -- a signed five-minute ticket in the path (tests/test_document_file_links.py)
    ("GET", "/api/public/files/{token}"),
    # V2-14: the page of the electrician and the plumber, built the same way (tests/test_v2_14_trade_links.py)
    ("GET", "/api/public/trade"),
    ("PUT", "/api/public/trade/rooms/{room_id}"),
    ("POST", "/api/public/trade/submit"),
}
METHODS = ("get", "post", "put", "patch", "delete")
CONTRACT = app.openapi()


def operations():
    for path, ops in sorted(CONTRACT["paths"].items()):
        for method, op in ops.items():
            if method in METHODS:
                yield method.upper(), path, op


def resolve(schema: dict) -> dict:
    ref = schema.get("$ref")
    if ref:
        node = CONTRACT
        for part in ref.removeprefix("#/").split("/"):
            node = node[part]
        return node
    return schema


def path_value(parameter: dict) -> str:
    schema = resolve(parameter.get("schema", {}))
    if "enum" in schema:
        return str(schema["enum"][0])
    if schema.get("format") == "uuid":
        return str(uuid.uuid4())
    return "x1"


def fill(path: str, op: dict) -> str:
    values = {p["name"]: path_value(p) for p in op.get("parameters", []) if p["in"] == "path"}
    return re.sub(r"\{(\w+)\}", lambda m: values.get(m.group(1), str(uuid.uuid4())), path)


ALL = [pytest.param(m, p, op, id=f"{m} {p}") for m, p, op in operations()]
GUARDED = [pytest.param(m, p, op, id=f"{m} {p}") for m, p, op in operations() if (m, p) not in OPEN_OPERATIONS]


def test_the_contract_is_read_and_is_big():
    assert len(ALL) > 200


def test_only_the_known_operations_are_open_in_the_contract():
    open_ones = {(m, p) for m, p, op in operations() if not op.get("security")}
    assert open_ones == OPEN_OPERATIONS


@pytest.mark.parametrize("method,path,op", GUARDED)
async def test_every_other_operation_refuses_a_request_without_a_token(async_client: AsyncClient, method, path, op):
    response = await async_client.request(method, fill(path, op))
    assert response.status_code == 401, response.text[:200]
    assert response.json()["detail"]["code"] == "MISSING_TOKEN"


@pytest.mark.parametrize("method,path,op", GUARDED)
async def test_a_bad_token_is_refused_too(async_client: AsyncClient, method, path, op):
    response = await async_client.request(method, fill(path, op), headers={"Authorization": "Bearer not-a-token"})
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "INVALID_TOKEN"


# --- no operation answers 5xx ---------------------------------------------------------------------------------------------------------------

JUNK = [
    None,
    {},
    {"x": [1, 2, {"a": None}]},
    {"id": "not-a-uuid", "name": 5, "title": [], "status": {}, "amount": "abc", "quantity": -1, "items": "x"},
]


async def token_of(client: AsyncClient) -> dict:
    user = {"id": 810001, "first_name": "Audit", "username": "audit", "language_code": "pl"}
    response = await client.post("/api/auth/telegram", json={"init_data": make_telegram_init_data(user)})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.mark.parametrize("junk", JUNK)
async def test_the_open_password_login_answers_no_5xx_to_a_wrong_request(async_client: AsyncClient, junk):
    response = await async_client.post("/api/auth/password", json=junk)
    assert response.status_code < 500, response.text[:300]


# A 5xx is a defect, except the answers that are the design: a feature that the configuration has switched off.
BY_DESIGN_503 = {"PHOTO_UPLOADS_DISABLED", "MEDIA_STORAGE_DISABLED", "MEDIA_STORAGE_UNAVAILABLE", "DOCUMENT_DELIVERY_DISABLED"}


def acceptable(response) -> bool:
    if response.status_code < 500:
        return True
    try:
        code = response.json()["detail"]["code"]
    except (ValueError, KeyError, TypeError):
        return False
    if response.status_code == 502:  # the preview of a document is sent to the owner's chat: no Telegram in the test environment
        return code == "TELEGRAM_UNAVAILABLE"
    return response.status_code == 503 and code in BY_DESIGN_503


def has_body(op: dict) -> bool:
    return "requestBody" in op


@pytest.mark.parametrize("method,path,op", GUARDED)
async def test_no_operation_answers_5xx_to_a_wrong_request(async_client: AsyncClient, method, path, op):
    headers = await token_of(async_client)
    url = fill(path, op)
    attempts = [{}]
    if has_body(op):
        content = op["requestBody"].get("content", {})
        if "application/json" in content:
            attempts = [{"json": junk} for junk in JUNK[1:]] + [{"content": b"{not json", "headers": {"Content-Type": "application/json"}}]
        else:
            attempts = [{"data": {"x": "y"}}, {}]
    for kwargs in attempts:
        merged = {**headers, **kwargs.get("headers", {})}
        extra = {k: v for k, v in kwargs.items() if k != "headers"}
        response = await async_client.request(method, url, headers=merged, **extra)
        assert acceptable(response), f"{method} {path} {kwargs!r} -> {response.status_code} {response.text[:300]}"


@pytest.mark.parametrize("method,path,op", [p for p in GUARDED if p.values[0] == "GET"])
async def test_every_read_with_unknown_ids_is_a_4xx_or_an_empty_answer(async_client: AsyncClient, method, path, op):
    headers = await token_of(async_client)
    response = await async_client.get(fill(path, op), headers=headers)
    assert acceptable(response), response.text[:300]
    if response.status_code >= 400:
        body = response.json()
        assert isinstance(body.get("detail"), (dict, list, str)), body
