"""V2-12a -- the hidden utilities on photo markers: the type and the distances of a marker, the service rules, the API and migration 0080 (docs/V2_12A_PLAN_RU.md)."""
import importlib.util
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from app.domain.exceptions import PhotoAnnotationValidationError
from app.domain.services.photo_annotation_service import normalize_distance, normalize_utility
from app.main import app
from app.models.photo_annotation import UTILITY_VALUES, PhotoAnnotation, PhotoUtility
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from tests import test_stage14c4_photos_api as c4
from tests.test_stage14c4_photos_api import call, form, path_for

api = c4.api
BACKEND = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND / "alembic" / "versions" / "0080_photo_utilities.py"
NEW_COLUMNS = {"utility", "depth_cm", "from_floor_cm", "from_corner_cm"}


# ------------------------------------------------------------------ the rules

def test_the_types_are_the_six_the_owner_asked_for():
    assert UTILITY_VALUES == ("CABLE", "WATER_COLD", "WATER_HOT", "SEWER", "HEATING", "GAS")
    assert normalize_utility(None) is None
    assert normalize_utility("SEWER") == "SEWER"
    for bad in ("", "cable", "WATER", 1, True, ["CABLE"]):
        with pytest.raises(PhotoAnnotationValidationError):
            normalize_utility(bad)


def test_a_distance_is_centimetres_to_one_decimal_between_zero_and_a_thousand():
    assert normalize_distance(None, "depth_cm") is None
    assert normalize_distance(0, "depth_cm") == 0.0
    assert normalize_distance(30, "depth_cm") == 30.0
    assert normalize_distance(2.56, "depth_cm") == 2.6
    assert normalize_distance(1000, "depth_cm") == 1000.0
    for bad in (-0.1, 1000.1, float("nan"), float("inf"), "3", True):
        with pytest.raises(PhotoAnnotationValidationError):
            normalize_distance(bad, "depth_cm")


# ------------------------------------------------------------------ the migration

def load_migration():
    spec = importlib.util.spec_from_file_location("m0080", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_op(engine, fn):
    with engine.begin() as conn:
        module = load_migration()
        module.op = Operations(MigrationContext.configure(conn))
        fn(module)


def engine_at_0079():
    """photo_annotations as it was (without the new columns), one marker in it."""
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE photo_annotations (id CHAR(32) PRIMARY KEY, attachment_id CHAR(32) NOT NULL, label VARCHAR(40), x NUMERIC(7, 6) NOT NULL, y NUMERIC(7, 6) NOT NULL, position INTEGER NOT NULL DEFAULT 0)"))
        conn.execute(text("INSERT INTO photo_annotations (id, attachment_id, label, x, y, position) VALUES ('m1', 'a1', 'rura', 0.5, 0.5, 0)"))
    return engine


def test_revision_chain_and_single_head():
    module = load_migration()
    assert module.revision == "0080_photo_utilities" and module.down_revision == "0079_material_packages" and len(module.revision) <= 32
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    assert ScriptDirectory.from_config(config).get_heads() == ["0081_installation_map_doc"]


def test_upgrade_adds_four_nullable_columns_and_leaves_the_marker_alone():
    engine = engine_at_0079()
    run_op(engine, lambda m: m.upgrade())
    columns = {c["name"]: c for c in inspect(engine).get_columns("photo_annotations")}
    assert NEW_COLUMNS <= set(columns) and all(columns[name]["nullable"] for name in NEW_COLUMNS)
    with engine.begin() as conn:
        row = conn.execute(text("SELECT label, utility, depth_cm, from_floor_cm, from_corner_cm FROM photo_annotations")).one()
    assert tuple(row) == ("rura", None, None, None, None)


def test_the_database_refuses_an_unknown_type_and_a_distance_out_of_range():
    engine = engine_at_0079()
    run_op(engine, lambda m: m.upgrade())
    with engine.begin() as conn:
        conn.execute(text("UPDATE photo_annotations SET utility = 'GAS', depth_cm = 1000, from_floor_cm = 0, from_corner_cm = 12.5"))
    for sql in ("utility = 'WATER'", "depth_cm = -1", "depth_cm = 1000.1", "from_floor_cm = 1001", "from_corner_cm = -0.5"):
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(text(f"UPDATE photo_annotations SET {sql}"))


def test_the_downgrade_refuses_while_a_marker_carries_a_type_or_a_distance():
    engine = engine_at_0079()
    run_op(engine, lambda m: m.upgrade())
    with engine.begin() as conn:
        conn.execute(text("UPDATE photo_annotations SET from_corner_cm = 20"))
    with pytest.raises(RuntimeError, match="never dropped silently"):
        run_op(engine, lambda m: m.downgrade())
    with engine.begin() as conn:
        conn.execute(text("UPDATE photo_annotations SET from_corner_cm = NULL"))
    run_op(engine, lambda m: m.downgrade())
    assert not NEW_COLUMNS & {c["name"] for c in inspect(engine).get_columns("photo_annotations")}
    run_op(engine, lambda m: m.upgrade())


def test_the_model_has_the_same_columns_as_the_migration():
    engine = engine_at_0079()
    run_op(engine, lambda m: m.upgrade())
    migrated = {c["name"] for c in inspect(engine).get_columns("photo_annotations")}
    assert NEW_COLUMNS <= {c.name for c in PhotoAnnotation.__table__.columns}
    assert NEW_COLUMNS <= migrated
    assert [item.value for item in PhotoUtility] == list(UTILITY_VALUES)


# ------------------------------------------------------------------ the API

@pytest.fixture
async def http(api):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {api.token}"
        yield client


@pytest.fixture
async def photo(api):
    c = await call(path_for(api.project), token=api.token, body=form(api, context="SURFACE", target=("surface_id", str(api.surface))))
    assert c.status == 201, c.body
    return c.json()["attachment"]["id"]


def base(project, attachment) -> str:
    return f"/api/projects/{project}/photo-attachments/{attachment}/annotations"


async def marker_of(http, api, attachment, **payload):
    r = await http.post(base(api.project, attachment), json={"x": 0.4, "y": 0.6, **payload})
    assert r.status_code == 201, r.text
    return r.json()


async def test_a_new_marker_is_an_ordinary_one(http, api, photo):
    marker = await marker_of(http, api, photo)
    assert (marker["utility"], marker["depth_cm"], marker["from_floor_cm"], marker["from_corner_cm"]) == (None, None, None, None)


async def test_the_type_and_the_distances_are_set_and_read_back(http, api, photo):
    marker = await marker_of(http, api, photo, label="rura")
    url = f"{base(api.project, photo)}/{marker['id']}"
    r = await http.patch(url, json={"utility": "WATER_HOT", "depth_cm": 3, "from_floor_cm": 30.25, "from_corner_cm": 120})
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["utility"], body["depth_cm"], body["from_floor_cm"], body["from_corner_cm"]) == ("WATER_HOT", 3.0, 30.2, 120.0)  # one decimal
    assert (body["x"], body["y"], body["label"], body["position"]) == (0.4, 0.6, "rura", 0)
    listed = (await http.get(base(api.project, photo))).json()["items"][0]
    assert listed["utility"] == "WATER_HOT" and listed["from_floor_cm"] == 30.2


async def test_what_is_not_sent_stays_and_null_clears(http, api, photo):
    marker = await marker_of(http, api, photo)
    url = f"{base(api.project, photo)}/{marker['id']}"
    await http.patch(url, json={"utility": "CABLE", "depth_cm": 2, "from_floor_cm": 40})
    r = await http.patch(url, json={"label": "kabel"})  # nothing about the utility
    assert (r.json()["utility"], r.json()["depth_cm"], r.json()["from_floor_cm"], r.json()["label"]) == ("CABLE", 2.0, 40.0, "kabel")
    r = await http.patch(url, json={"depth_cm": None, "utility": None})
    assert (r.json()["utility"], r.json()["depth_cm"], r.json()["from_floor_cm"]) == (None, None, 40.0)


@pytest.mark.parametrize("payload", [{"utility": "WATER"}, {"utility": ""}, {"depth_cm": -1}, {"from_floor_cm": 1000.5}, {"from_corner_cm": 5000}])
async def test_a_bad_type_or_distance_is_the_photo_error_and_changes_nothing(http, api, photo, payload):
    marker = await marker_of(http, api, photo)
    url = f"{base(api.project, photo)}/{marker['id']}"
    await http.patch(url, json={"utility": "GAS", "depth_cm": 5})
    r = await http.patch(url, json=payload)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "PHOTO_ANNOTATION_INVALID"
    kept = (await http.get(base(api.project, photo))).json()["items"][0]
    assert (kept["utility"], kept["depth_cm"]) == ("GAS", 5.0)


@pytest.mark.parametrize("payload", [{"depth_cm": "3"}, {"depth_cm": True}, {"from_floor_cm": [1]}, {"nope": 1}])
async def test_wrong_types_are_refused_by_the_schema(http, api, photo, payload):
    marker = await marker_of(http, api, photo)
    r = await http.patch(f"{base(api.project, photo)}/{marker['id']}", json=payload)
    assert r.status_code == 422
