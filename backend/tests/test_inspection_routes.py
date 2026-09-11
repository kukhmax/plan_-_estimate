"""Regression guard for the inspection checklist route contract (Stage 6).

The inspection engine endpoints must stay mounted under the exact canonical
paths and HTTP methods; if the family is ever unmounted, renamed, or mounted
under a wrong prefix every inspection request returns HTTP 404. These tests pin
the registered route family via the authoritative OpenAPI schema (which also
materializes the lazily-included routers).
"""

from app.main import app

INSPECTIONS_PATH = "/api/projects/{project_id}/rooms/{room_id}/inspections"
INSPECTION_PATH = (
    "/api/projects/{project_id}/rooms/{room_id}/inspections/{inspection_id}"
)
TEMPLATES_PATH = "/api/checklist-templates"
TEMPLATE_PATH = "/api/checklist-templates/{template_id}"


def _paths() -> dict[str, dict]:
    return app.openapi()["paths"]


def test_checklist_route_family_registered() -> None:
    assert {p for p in _paths() if "checklist-templates" in p} == {
        TEMPLATES_PATH,
        TEMPLATE_PATH,
    }


def test_checklist_methods() -> None:
    schema = _paths()
    assert set(schema[TEMPLATES_PATH]) == {"get"}
    assert set(schema[TEMPLATE_PATH]) == {"get"}


def test_checklist_templates_are_read_only() -> None:
    """Template, section, question and option rows must not be mutatable over the API.

    Released templates are immutable snapshots: inspection rows reference the
    exact template/question selected at start, so no update or delete route may
    exist for the checklist catalog in Stage 6 (admin CRUD is deferred).
    """
    mutation_methods = {"post", "patch", "put", "delete"}
    schema = _paths()
    for path in (TEMPLATES_PATH, TEMPLATE_PATH):
        methods = set(schema[path])
        assert not (methods & mutation_methods), f"{path} exposes mutation methods"


def test_inspection_route_family_registered_under_api_prefix() -> None:
    expected = {
        INSPECTIONS_PATH,
        INSPECTION_PATH,
        f"{INSPECTION_PATH}/answers",
        f"{INSPECTION_PATH}/archive",
        f"{INSPECTION_PATH}/complete",
        f"{INSPECTION_PATH}/findings",
        f"{INSPECTION_PATH}/reopen",
        f"{INSPECTION_PATH}/restore",
    }
    assert {p for p in _paths() if "/inspections" in p} == expected


def test_inspection_route_family_has_no_duplicate_endpoints() -> None:
    assert len([p for p in _paths() if "/inspections" in p]) == 8


def test_inspection_methods_match_frontend_contract() -> None:
    schema = _paths()
    assert set(schema[INSPECTIONS_PATH]) == {"get", "post"}
    assert set(schema[INSPECTION_PATH]) == {"get", "patch"}
    assert set(schema[f"{INSPECTION_PATH}/answers"]) == {"get", "put"}
    assert set(schema[f"{INSPECTION_PATH}/archive"]) == {"post"}
    assert set(schema[f"{INSPECTION_PATH}/complete"]) == {"post"}
    assert set(schema[f"{INSPECTION_PATH}/findings"]) == {"get"}
    assert set(schema[f"{INSPECTION_PATH}/reopen"]) == {"post"}
    assert set(schema[f"{INSPECTION_PATH}/restore"]) == {"post"}


def test_inspection_engine_routes_require_auth() -> None:
    schema = _paths()
    for path in _paths():
        if "checklist-templates" in path or "/inspections" in path:
            for method in schema[path]:
                operation = schema[path][method]
                assert "security" in operation, f"{method} {path} lacks security"
