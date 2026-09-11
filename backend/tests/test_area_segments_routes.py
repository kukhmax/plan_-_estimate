"""Regression guard for the area-segments route contract.

The browser's Podłoga / Sufit panels call
``/api/projects/{p}/rooms/{r}/area-segments``; if the endpoint family is ever
unmounted, renamed, or mounted under a wrong prefix, every AreaSegment request
returns HTTP 404. These tests pin the exact registered route family (via the
authoritative OpenAPI schema, which also materializes lazily-included routers)
so that regression fails loudly instead of surfacing as a runtime 404.
"""

from app.main import app

LIST_PATH = "/api/projects/{project_id}/rooms/{room_id}/area-segments"
SEGMENT_PATH = "/api/projects/{project_id}/rooms/{room_id}/area-segments/{segment_id}"


def _paths() -> dict[str, dict]:
    return app.openapi()["paths"]


def test_area_segments_route_family_registered_under_api_prefix() -> None:
    assert {p for p in _paths() if "area-segments" in p} == {
        LIST_PATH,
        SEGMENT_PATH,
        f"{SEGMENT_PATH}/archive",
        f"{SEGMENT_PATH}/restore",
    }


def test_area_segments_route_family_has_no_duplicate_endpoints() -> None:
    assert len([p for p in _paths() if "area-segments" in p]) == 4


def test_area_segments_methods_match_frontend_client() -> None:
    schema = _paths()
    assert set(schema[LIST_PATH]) == {"get", "post"}
    assert set(schema[SEGMENT_PATH]) == {"get", "patch"}
    assert set(schema[f"{SEGMENT_PATH}/archive"]) == {"post"}
    assert set(schema[f"{SEGMENT_PATH}/restore"]) == {"post"}
