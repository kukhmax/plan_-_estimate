"""Regression guard for the risk engine route contract (Stage 7B).

The risk engine endpoints must stay mounted under the exact canonical paths and
HTTP methods; if the family is ever unmounted, renamed, or mounted under a wrong
prefix every risk request returns HTTP 404. These tests pin the registered route
family via the authoritative OpenAPI schema (which also materializes the
lazily-included routers).
"""

from app.main import app

RISKS_PATH = "/api/projects/{project_id}/rooms/{room_id}/risks"
RISK_PATH = f"{RISKS_PATH}/{{risk_id}}"
EVALUATE_PATH = f"{RISKS_PATH}/evaluate"


def _paths() -> dict[str, dict]:
    return app.openapi()["paths"]


def test_risk_route_family_registered() -> None:
    expected = {RISKS_PATH, RISK_PATH, EVALUATE_PATH}
    assert {p for p in _paths() if "/risks" in p} == expected


def test_risk_methods_match_frontend_contract() -> None:
    schema = _paths()
    assert set(schema[RISKS_PATH]) == {"get"}
    assert set(schema[RISK_PATH]) == {"get"}
    assert set(schema[EVALUATE_PATH]) == {"post"}


def test_risk_engine_routes_require_auth() -> None:
    schema = _paths()
    for path in (RISKS_PATH, RISK_PATH, EVALUATE_PATH):
        for method in schema[path]:
            assert "security" in schema[path][method], f"{method} {path} lacks security"
