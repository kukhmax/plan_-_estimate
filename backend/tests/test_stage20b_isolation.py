"""Stage 20B -- owner isolation over the WHOLE contract: a second owner puts the ids of the first owner's data into every route, in every place a route
takes an id, and never gets a 2xx; the lists of the second owner never show the first owner's data; and the ids of the first owner inside a BODY are refused.
"""
import re
import uuid
from collections import Counter

import pytest

from tests.stage20_world import World, build_world, login
from tests.test_stage20b_api_audit import CONTRACT, METHODS, acceptable, resolve

GLOBAL_PREFIXES = ("/api/knowledge", "/api/checklist-templates", "/api/contract-catalog", "/api/health", "/api/auth", "/api/access", "/api/me")
SECRETS = ("Nowak", "Anna", "Długa", "Klucze", "Mieszkanie Nowaków", "Zaliczka", "Wilgoć", "Elektryka", "Ela-Mont", "Wejście od podwórza", "Zadzwonić")
PARAM_FROM_WORLD = {"kind": "CONTRACT", "code": "x1", "occurrence_key": "x1", "document_id": None, "entry_id": None}


def fake(schema: dict, depth: int = 0):
    """A minimal value that satisfies a schema of the contract (so the request reaches the ownership check instead of stopping at the validation)."""
    schema = resolve(schema)
    if "anyOf" in schema:
        options = [o for o in schema["anyOf"] if resolve(o).get("type") != "null"]
        return fake(options[0], depth) if options else None
    if "allOf" in schema:
        return fake(schema["allOf"][0], depth)
    if "enum" in schema:
        return schema["enum"][0]
    kind = schema.get("type")
    if kind == "object" or "properties" in schema:
        if depth > 4:
            return {}
        required = set(schema.get("required", []))
        return {k: fake(v, depth + 1) for k, v in schema.get("properties", {}).items() if k in required}
    if kind == "array":
        return []
    if kind == "integer":
        return max(1, int(schema.get("minimum", 1)))
    if kind == "number":
        return max(1, float(schema.get("minimum", 1)))
    if kind == "boolean":
        return True
    fmt = schema.get("format")
    if fmt == "uuid":
        return str(uuid.uuid4())
    if fmt == "date":
        return "2026-10-10"
    if fmt == "date-time":
        return "2026-10-10T10:00:00Z"
    return "x1"


def body_of(op: dict):
    content = op.get("requestBody", {}).get("content", {})
    if "application/json" in content:
        return {"json": fake(content["application/json"]["schema"])}
    if content:
        return {"data": {"x": "y"}}
    return {}


def url_for(path: str, op: dict, ids: dict, project_override: str | None, protocol_index: int) -> str:
    def value(name: str) -> str:
        if name == "project_id" and project_override:
            return project_override
        if name == "protocol_id":
            return ids["protocol_id"][protocol_index % len(ids["protocol_id"])]
        if name == "record_id":
            return ids["contract_id"][0]
        if name in PARAM_FROM_WORLD and PARAM_FROM_WORLD[name]:
            return PARAM_FROM_WORLD[name]
        if name in ids and ids[name]:
            return ids[name][0]
        return str(uuid.uuid4())
    return re.sub(r"\{(\w+)\}", lambda m: value(m.group(1)), path)


def operations():
    for path, ops in sorted(CONTRACT["paths"].items()):
        if path.startswith(GLOBAL_PREFIXES):
            continue
        for method, op in ops.items():
            if method in METHODS:
                yield method.upper(), path, op


@pytest.fixture
async def two_owners(async_client, db_session):
    a = await build_world(async_client, db_session, telegram_id=20001)
    b_token = await login(async_client, 20003, "Other")
    project = await async_client.post("/api/projects", headers=b_token, json={"name": "Obcy projekt", "address": "ul. B 2", "city": "Gdańsk", "postal_code": "80-001"})
    assert project.status_code == 201
    return a, b_token, project.json()["id"]


async def test_no_route_gives_a_second_owner_anything_of_the_first_owners_data(async_client, two_owners):
    a, b_token, b_project = two_owners
    outcomes, statuses = Counter(), Counter()
    violations, leaks, errors = [], [], []
    for mode, override in (("A-ids", None), ("own-project", b_project)):
        for method, path, op in operations():
            for index in range(3 if "{protocol_id}" in path else 1):
                url = url_for(path, op, a.ids, override, index)
                response = await async_client.request(method, url, headers=b_token, **body_of(op))
                outcomes[(mode, response.status_code // 100 if response.status_code < 500 else 5)] += 1
                if re.search(r"\{\w+\}", path):
                    statuses[(mode, response.status_code)] += 1
                params = re.findall(r"\{(\w+)\}", path)
                foreign = [p for p in params if not (mode == "own-project" and p == "project_id")]
                if 200 <= response.status_code < 300 and foreign:  # a route with no id of the first owner in it works on the caller's own scope
                    violations.append(f"{mode} {method} {path} -> {response.status_code}")
                if not acceptable(response):
                    errors.append(f"{mode} {method} {path} -> {response.status_code} {response.text[:160]}")
                if any(secret in response.text for secret in SECRETS):
                    leaks.append(f"{mode} {method} {path}")
    print("OUTCOMES", dict(outcomes), "STATUSES", dict(statuses))
    for mode in ("A-ids", "own-project"):
        total = sum(n for (m, _), n in statuses.items() if m == mode)
        refused_as_foreign = sum(n for (m, code), n in statuses.items() if m == mode and code in (403, 404))
        assert refused_as_foreign / total > 0.6, (mode, refused_as_foreign, total)  # the ownership check itself is what answers, not the validation
    assert not errors, errors[:10]
    assert not leaks, leaks[:10]
    assert not violations, violations[:20]


async def test_the_lists_of_a_second_owner_show_nothing_of_the_first(async_client, two_owners):
    a, b_token, b_project = two_owners
    a_ids = {value for values in a.ids.values() for value in values}
    for method, path, op in operations():
        if method != "GET" or "{" in path:
            continue
        response = await async_client.get(path, headers=b_token)
        assert response.status_code < 500, path
        leaked = [i for i in a_ids if i in response.text]
        assert not leaked, f"{path} shows ids of another owner: {leaked[:3]}"
        assert not any(secret in response.text for secret in SECRETS), path


# --- the ids of the first owner inside a body -------------------------------------------------------------------------------------------------


@pytest.fixture
async def b_side(async_client, two_owners):
    a, b_token, b_project = two_owners
    P = f"/api/projects/{b_project}"
    room = (await async_client.post(f"{P}/rooms", headers=b_token, json={"name": "Pokój B"})).json()
    await async_client.patch(f"{P}/rooms/{room['id']}", headers=b_token, json={"length": "3", "width": "3", "height": "2.5"})
    await async_client.post(f"{P}/rooms/{room['id']}/surfaces/generate", headers=b_token)
    surfaces = (await async_client.get(f"{P}/rooms/{room['id']}/surfaces", headers=b_token)).json()["items"]
    handover = (await async_client.post(f"{P}/handovers", headers=b_token)).json()
    acceptance = (await async_client.post(f"{P}/acceptances", headers=b_token)).json()
    downtime = (await async_client.post(f"{P}/downtimes", headers=b_token)).json()
    return a, b_token, b_project, room["id"], surfaces[0]["id"], handover["id"], acceptance["id"], downtime["id"]


def refused(response) -> bool:
    return 400 <= response.status_code < 500


async def test_a_second_owner_cannot_attach_the_first_owners_records_by_putting_their_ids_in_a_body(async_client, b_side):
    a, h, project, room, surface, handover, acceptance, downtime = b_side
    P, R = f"/api/projects/{project}", f"/api/projects/{project}/rooms/{room}"
    other = {k: v[0] for k, v in a.ids.items()}
    calls = {
        "project of B points at the client of A": ("PATCH", P, {"client_id": other["client_id"]}),
        "a new project points at the client of A": ("POST", "/api/projects", {"name": "X", "address": "a", "city": "c", "postal_code": "00-001", "client_id": other["client_id"]}),
        "the plan of B uses a price item of A": ("PUT", f"{R}/surfaces/{surface}/work-plan", {"substrate": "CONCRETE", "price_item_ids": [other["price_item_id"]]}),
        "a payment of B settles a payment of A": ("POST", f"{P}/payments", {"kind": "PAYMENT", "title": "p", "amount_gross": "1", "occurred_on": "2026-10-10", "settles_id": other["payment_id"]}),
        "an adjacent work of B names a room of A": ("POST", f"{P}/adjacent-works", {"work_name": "w", "order_relation": "PARALLEL", "room_ids": [other["room_id"]]}),
        "a reminder of B points at a project of A": ("POST", "/api/calendar/reminders", {"preset": "TOMORROW", "title": "t", "project_id": other["project_id"]}),
        "a reminder of B points at a room of A": ("POST", "/api/calendar/reminders", {"preset": "TOMORROW", "title": "t", "project_id": project, "room_id": other["room_id"]}),
        "an inspection of B uses a surface of A": ("POST", f"{R}/inspections", {"template_id": other["template_id"], "substrate": "CONCRETE", "surface_id": other["surface_id"]}),
        "a handover of B records a room of A": ("PATCH", f"{P}/handovers/{handover}", {"rooms": {other["room_id"]: {"decision": "HANDED_OVER"}}}),
        "an acceptance of B names a room of A": ("PATCH", f"{P}/acceptances/{acceptance}", {"room_ids": [other["room_id"]]}),
        "a downtime of B names a room of A": ("PATCH", f"{P}/downtimes/{downtime}", {"room_ids": [other["room_id"]]}),
        "B attaches the photo of A": ("POST", f"{P}/photos/{other['asset_id']}/attachments", {"context": "PROJECT", "category": "GENERAL"}),
        "B puts a marker on the photo of A": ("POST", f"{P}/photo-attachments/{other['attachment_id']}/annotations", {"x": 0.1, "y": 0.1}),
    }
    failures = []
    for label, (method, path, body) in calls.items():
        response = await async_client.request(method, path, headers=h, json=body)
        if not refused(response):
            failures.append(f"{label}: {method} {path} -> {response.status_code} {response.text[:200]}")
    assert not failures, failures
