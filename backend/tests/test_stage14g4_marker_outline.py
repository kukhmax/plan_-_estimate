"""Stage 14G.4 — a freehand contour around the defect, stored on the marker (migration 0036).

Owner decisions 2026-10-08: freehand finger contour, ONE per marker, no editing (delete it and draw again), the data is
kept as a vector (fractions 0..1 like the marker's own x / y) so it fits any screen, the thumbnail and a later PDF.
Rules: 3..120 points, numbers 0..1, not all the same point; a new contour replaces the old one, `null` removes it; the
label and the contour are independent; written only on an active attachment of an active photo.
"""

import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, inspect, select, text

import app.models
from app.core.database import Base
from app.domain.exceptions import PhotoAnnotationValidationError
from app.domain.services.photo_annotation_service import normalize_outline
from app.main import app
from app.models.photo_annotation import (
    MAX_OUTLINE_POINTS,
    MIN_OUTLINE_POINTS,
    PhotoAnnotation,
)
from tests import test_stage14c4_photos_api as c4
from tests.test_stage14c4_photos_api import call, form, path_for

api = c4.api
BACKEND = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND / "alembic" / "versions" / "0036_photo_annotation_outline.py"


def square(n: int = 4) -> list[list[float]]:
    """A closed-ish loop of n points inside the picture."""
    return [[round(0.2 + 0.6 * i / (n - 1), 6), round(0.2 + 0.1 * (i % 2), 6)] for i in range(n)]


# ===========================================================================
# A. Migration 0036
# ===========================================================================


def load_migration():
    spec = importlib.util.spec_from_file_location("m0036", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_op(engine, fn):
    with engine.begin() as conn:
        module = load_migration()
        module.op = Operations(MigrationContext.configure(conn))
        fn(module)


def engine_at_0035():
    """Every table of the metadata, with photo_annotations as migration 0035 created it (no contour column)."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE photo_annotations DROP COLUMN outline"))
    return engine


def test_revision_chain_and_single_head():
    module = load_migration()
    assert module.revision == "0036_photo_annotation_outline"
    assert module.down_revision == "0035_photo_annotations"
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["0046_contract_signed"]
    assert scripts.get_revision("0035_photo_annotations").down_revision == "0034_finding_lineage"


def test_upgrade_adds_only_the_nullable_outline_column_and_downgrade_removes_it():
    engine = engine_at_0035()
    before = {c["name"] for c in inspect(engine).get_columns("photo_annotations")}
    assert "outline" not in before
    with engine.begin() as conn:  # a marker that exists before the migration keeps its data
        conn.execute(
            text(
                "INSERT INTO photo_annotations (id, attachment_id, kind, x, y, label, position, created_at, updated_at) "
                "VALUES ('00000000000000000000000000000001', '00000000000000000000000000000002', 'POINT', 0.5, 0.5, 'old', 0, "
                "'2026-10-08', '2026-10-08')"
            )
        )
    run_op(engine, lambda m: m.upgrade())
    columns = {c["name"]: c for c in inspect(engine).get_columns("photo_annotations")}
    assert set(columns) == before | {"outline"}
    assert columns["outline"]["nullable"] is True
    with engine.connect() as conn:
        row = conn.execute(text("SELECT label, outline FROM photo_annotations")).one()
    assert row[0] == "old" and row[1] is None
    run_op(engine, lambda m: m.downgrade())
    assert {c["name"] for c in inspect(engine).get_columns("photo_annotations")} == before
    run_op(engine, lambda m: m.upgrade())  # up / down / up
    assert "outline" in {c["name"] for c in inspect(engine).get_columns("photo_annotations")}


def test_the_model_has_the_same_column_as_the_migration():
    engine = engine_at_0035()
    run_op(engine, lambda m: m.upgrade())
    migrated = {c["name"] for c in inspect(engine).get_columns("photo_annotations")}
    assert migrated == {c.name for c in PhotoAnnotation.__table__.columns}


# ===========================================================================
# B. Pure validation
# ===========================================================================


def test_limits_are_three_to_one_hundred_twenty():
    assert (MIN_OUTLINE_POINTS, MAX_OUTLINE_POINTS) == (3, 120)


def test_none_means_no_contour():
    assert normalize_outline(None) is None


@pytest.mark.parametrize("count", [3, 4, 60, 120])
def test_accepts_three_to_one_hundred_twenty_points(count):
    points = [[i / 200, (i % 7) / 10] for i in range(count)]
    assert len(normalize_outline(points)) == count


@pytest.mark.parametrize("count", [0, 1, 2, 121, 500])
def test_rejects_too_few_or_too_many_points(count):
    with pytest.raises(PhotoAnnotationValidationError):
        normalize_outline([[i / 1000, 0.5 + i % 2 / 10] for i in range(count)])


def test_points_are_rounded_and_accept_tuples_and_integers():
    assert normalize_outline([(0, 0), (1, 1), [0.12345678, 0.9999996]]) == [[0.0, 0.0], [1.0, 1.0], [0.123457, 1.0]]


@pytest.mark.parametrize(
    "bad",
    [
        [[0, 0], [1, 1], [1.000001, 0.5]],
        [[0, 0], [1, 1], [0.5, -0.000001]],
        [[0, 0], [1, 1], [float("nan"), 0.5]],
        [[0, 0], [1, 1], [float("inf"), 0.5]],
        [[0, 0], [1, 1], [True, 0.5]],
        [[0, 0], [1, 1], ["0.5", 0.5]],
        [[0, 0], [1, 1], [None, 0.5]],
        [[0, 0], [1, 1], [0.5]],
        [[0, 0], [1, 1], [0.5, 0.5, 0.5]],
        [[0, 0], [1, 1], 0.5],
        [[0, 0], [1, 1], {"x": 0.5, "y": 0.5}],
        "abc",
        {"points": []},
        5,
    ],
)
def test_rejects_bad_points_and_shapes(bad):
    with pytest.raises(PhotoAnnotationValidationError):
        normalize_outline(bad)


def test_rejects_a_contour_that_is_one_point():
    with pytest.raises(PhotoAnnotationValidationError):
        normalize_outline([[0.5, 0.5]] * 10)
    assert normalize_outline([[0.5, 0.5], [0.5, 0.5], [0.6, 0.5]]) is not None  # two distinct points are enough


# ===========================================================================
# C. API
# ===========================================================================


@pytest.fixture
async def http(api):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {api.token}"
        yield client


@pytest.fixture
async def photo(api):
    c = await call(
        path_for(api.project), token=api.token,
        body=form(api, context="SURFACE", target=("surface_id", str(api.surface))),
    )
    assert c.status == 201, c.body
    return c.json()["attachment"]["id"], c.json()["asset"]["id"]


def base(project, attachment) -> str:
    return f"/api/projects/{project}/photo-attachments/{attachment}/annotations"


async def marker_of(http, api, attachment, **payload):
    r = await http.post(base(api.project, attachment), json={"x": 0.5, "y": 0.5, **payload})
    assert r.status_code == 201, r.text
    return r.json()


def code(r) -> str:
    return r.json()["detail"]["code"]


async def test_a_new_marker_has_no_contour(http, api, photo):
    attachment, _ = photo
    assert (await marker_of(http, api, attachment))["outline"] is None


async def test_setting_a_contour_returns_it_and_leaves_the_rest_alone(http, api, photo):
    attachment, _ = photo
    marker = await marker_of(http, api, attachment, label="rysa")
    r = await http.patch(f"{base(api.project, attachment)}/{marker['id']}", json={"outline": square(5)})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["outline"] == square(5)
    assert (body["x"], body["y"], body["position"], body["label"]) == (0.5, 0.5, 0, "rysa")
    listing = (await http.get(base(api.project, attachment))).json()["items"]
    assert listing[0]["outline"] == square(5)


async def test_a_new_contour_replaces_the_old_one_and_null_removes_it(http, api, photo):
    attachment, _ = photo
    marker = await marker_of(http, api, attachment)
    url = f"{base(api.project, attachment)}/{marker['id']}"
    await http.patch(url, json={"outline": square(4)})
    second = (await http.patch(url, json={"outline": square(6)})).json()
    assert second["outline"] == square(6)
    removed = (await http.patch(url, json={"outline": None})).json()
    assert removed["outline"] is None
    again = (await http.patch(url, json={"outline": None})).json()  # removing nothing is fine
    assert again["outline"] is None


async def test_label_and_contour_are_independent(http, api, photo):
    attachment, _ = photo
    marker = await marker_of(http, api, attachment, label="a")
    url = f"{base(api.project, attachment)}/{marker['id']}"
    await http.patch(url, json={"outline": square(4)})
    only_label = (await http.patch(url, json={"label": "b"})).json()
    assert (only_label["label"], only_label["outline"]) == ("b", square(4))  # the contour survives a label change
    both = (await http.patch(url, json={"label": None, "outline": square(5)})).json()
    assert (both["label"], both["outline"]) == (None, square(5))
    empty = (await http.patch(url, json={})).json()  # nothing to change
    assert empty["outline"] == square(5)


@pytest.mark.parametrize("count", [0, 1, 2, 121])
async def test_point_count_outside_three_to_one_twenty_is_the_photo_error(http, api, photo, count):
    attachment, _ = photo
    marker = await marker_of(http, api, attachment)
    points = [[i / 500, 0.2 + (i % 2) / 10] for i in range(count)]
    r = await http.patch(f"{base(api.project, attachment)}/{marker['id']}", json={"outline": points})
    assert r.status_code == 422 and code(r) == "PHOTO_ANNOTATION_INVALID"


@pytest.mark.parametrize("count", [3, 120])
async def test_the_limits_themselves_are_accepted(http, api, photo, count):
    attachment, _ = photo
    marker = await marker_of(http, api, attachment)
    points = [[i / 500, 0.2 + (i % 2) / 10] for i in range(count)]
    r = await http.patch(f"{base(api.project, attachment)}/{marker['id']}", json={"outline": points})
    assert r.status_code == 200 and len(r.json()["outline"]) == count


@pytest.mark.parametrize(
    "outline",
    [
        [[0, 0], [1, 1], [1.5, 0.5]],
        [[0, 0], [1, 1], [0.5, -0.1]],
        [[0.5, 0.5]] * 5,
        [[0, 0], [1, 1], [0.5]],
        [[0, 0], [1, 1], [0.5, 0.5, 0.5]],
    ],
)
async def test_bad_points_are_the_photo_error_and_change_nothing(http, api, photo, outline):
    attachment, _ = photo
    marker = await marker_of(http, api, attachment)
    url = f"{base(api.project, attachment)}/{marker['id']}"
    await http.patch(url, json={"outline": square(4)})
    r = await http.patch(url, json={"outline": outline})
    assert r.status_code == 422 and code(r) == "PHOTO_ANNOTATION_INVALID"
    assert (await http.get(base(api.project, attachment))).json()["items"][0]["outline"] == square(4)


@pytest.mark.parametrize(
    "outline",
    [[[0, 0], [1, 1], ["0.5", 0.5]], [[0, 0], [1, 1], [True, 0.5]], "abc", 5, [[0, 0], [1, 1], 0.5], {"a": 1}],
)
async def test_wrong_types_are_rejected_by_the_schema(http, api, photo, outline):
    attachment, _ = photo
    marker = await marker_of(http, api, attachment)
    r = await http.patch(f"{base(api.project, attachment)}/{marker['id']}", json={"outline": outline})
    assert r.status_code == 422


async def test_a_huge_contour_is_refused_in_the_photo_error_envelope(http, api, photo):
    attachment, _ = photo
    marker = await marker_of(http, api, attachment)
    r = await http.patch(f"{base(api.project, attachment)}/{marker['id']}", json={"outline": [[0.1, 0.2]] * 1001})
    assert r.status_code == 422 and code(r) == "PHOTO_ANNOTATION_INVALID"


async def test_position_x_y_and_kind_still_cannot_be_changed(http, api, photo):
    attachment, _ = photo
    marker = await marker_of(http, api, attachment)
    for extra in ({"x": 0.9}, {"y": 0.9}, {"position": 3}, {"kind": "POINT"}):
        r = await http.patch(f"{base(api.project, attachment)}/{marker['id']}", json={"outline": square(4), **extra})
        assert r.status_code == 422
    assert (await http.get(base(api.project, attachment))).json()["items"][0]["outline"] is None


async def test_the_contour_is_in_the_photo_detail_with_the_server_limit(http, api, photo):
    attachment, asset = photo
    marker = await marker_of(http, api, attachment)
    await http.patch(f"{base(api.project, attachment)}/{marker['id']}", json={"outline": square(4)})
    detail = (await http.get(f"/api/projects/{api.project}/photos/{asset}")).json()
    assert detail["annotations"][0]["outline"] == square(4)
    assert detail["outline_max_points"] == 120


async def test_each_attachment_keeps_its_own_contours(http, api, photo):
    attachment, asset = photo
    second = (await http.post(
        f"/api/projects/{api.project}/photos/{asset}/attachments", json={"context": "ROOM", "room_id": str(api.room)}
    )).json()["id"]
    first_marker = await marker_of(http, api, attachment)
    second_marker = await marker_of(http, api, second)
    await http.patch(f"{base(api.project, attachment)}/{first_marker['id']}", json={"outline": square(4)})
    assert (await http.get(base(api.project, second))).json()["items"][0]["outline"] is None
    # a marker id of one attachment does not exist on the other
    r = await http.patch(f"{base(api.project, second)}/{first_marker['id']}", json={"outline": square(5)})
    assert r.status_code == 404 and code(r) == "PHOTO_ANNOTATION_NOT_FOUND"
    assert second_marker["outline"] is None


async def test_archived_attachment_keeps_the_contour_and_refuses_changes(http, api, photo):
    attachment, _ = photo
    marker = await marker_of(http, api, attachment)
    url = f"{base(api.project, attachment)}/{marker['id']}"
    await http.patch(url, json={"outline": square(4)})
    await http.post(f"/api/projects/{api.project}/photo-attachments/{attachment}/archive")
    assert (await http.get(base(api.project, attachment))).json()["items"][0]["outline"] == square(4)  # readable
    for body in ({"outline": square(5)}, {"outline": None}):
        r = await http.patch(url, json=body)
        assert r.status_code == 409 and code(r) == "PHOTO_ANNOTATION_READ_ONLY"
    await http.post(f"/api/projects/{api.project}/photo-attachments/{attachment}/restore")
    assert (await http.get(base(api.project, attachment))).json()["items"][0]["outline"] == square(4)  # same after restore
    assert (await http.patch(url, json={"outline": None})).status_code == 200


async def test_archived_asset_refuses_too(http, api, photo):
    attachment, asset = photo
    marker = await marker_of(http, api, attachment)
    await http.post(f"/api/projects/{api.project}/photos/{asset}/archive")
    r = await http.patch(f"{base(api.project, attachment)}/{marker['id']}", json={"outline": square(4)})
    assert r.status_code == 409 and code(r) == "PHOTO_ANNOTATION_READ_ONLY"


async def test_ownership_and_missing_ids(http, api, photo):
    attachment, _ = photo
    marker = await marker_of(http, api, attachment)
    url = f"{base(api.project, attachment)}/{marker['id']}"
    foreign = {"Authorization": f"Bearer {api.other_token}"}
    r = await http.patch(url, json={"outline": square(4)}, headers=foreign)
    assert r.status_code == 404 and code(r) == "PROJECT_NOT_FOUND"
    r = await http.patch(f"{base(api.project2, attachment)}/{marker['id']}", json={"outline": square(4)})
    assert r.status_code == 404 and code(r) == "PHOTO_ATTACHMENT_NOT_FOUND"
    r = await http.patch(f"{base(api.project, attachment)}/{uuid.uuid4()}", json={"outline": square(4)})
    assert r.status_code == 404 and code(r) == "PHOTO_ANNOTATION_NOT_FOUND"
    assert (await http.get(base(api.project, attachment))).json()["items"][0]["outline"] is None


async def test_deleting_the_marker_deletes_its_contour(http, api, photo):
    attachment, _ = photo
    marker = await marker_of(http, api, attachment)
    url = f"{base(api.project, attachment)}/{marker['id']}"
    await http.patch(url, json={"outline": square(4)})
    assert (await http.delete(url)).status_code == 204
    assert (await api.db.execute(select(PhotoAnnotation))).first() is None


async def test_the_contour_does_not_count_as_a_marker_and_changes_no_counts(http, api, photo):
    attachment, _ = photo
    before = (await http.get(f"/api/projects/{api.project}/photos/counts")).json()
    marker = await marker_of(http, api, attachment)
    await http.patch(f"{base(api.project, attachment)}/{marker['id']}", json={"outline": square(4)})
    items = (await http.get(f"/api/projects/{api.project}/photos")).json()["items"]
    assert items[0]["annotation_count"] == 1
    assert (await http.get(f"/api/projects/{api.project}/photos/counts")).json() == before
