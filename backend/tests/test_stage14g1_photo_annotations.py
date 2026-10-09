"""Stage 14G.1 — point markers (annotations) on photo attachments: migration 0035, service rules and API.

A marker is only a place on the picture (x / y = fractions 0..1 of the display image) with an optional label of at
most 40 characters; at most 10 per attachment (owner decision Q1); changed only on an ACTIVE attachment of an ACTIVE
photo; never moved or reordered (Q5): the label is the only editable field and a wrong marker is deleted. Markers
belong to the ATTACHMENT, so the same image attached to two places has two independent sets; archive -> restore gives
the very same markers back; lists carry `annotation_count`, the detail carries every marker of the asset.
"""

import importlib.util
import math
import uuid
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, event, func, inspect, select, text
from sqlalchemy.exc import IntegrityError

import app.models
from app.core.database import Base
from app.domain.exceptions import PhotoAnnotationValidationError
from app.domain.services.photo_annotation_service import (
    normalize_coordinate,
    normalize_label,
)
from app.main import app
from app.models.photo_annotation import (
    MAX_ANNOTATIONS_PER_ATTACHMENT,
    MAX_LABEL_LENGTH,
    PhotoAnnotation,
    PhotoAnnotationKind,
)
from app.models.photo_asset import PhotoAsset
from app.models.photo_attachment import PhotoAttachment
from tests import test_stage14c4_photos_api as c4
from tests.test_stage14c4_photos_api import call, form, path_for

api = c4.api
BACKEND = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND / "alembic" / "versions" / "0035_photo_annotations.py"


# ===========================================================================
# A. Migration 0035
# ===========================================================================


def load_migration():
    spec = importlib.util.spec_from_file_location("m0035", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_op(engine, fn):
    with engine.begin() as conn:
        module = load_migration()
        module.op = Operations(MigrationContext.configure(conn))
        fn(module)


def fresh_engine():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_connection, _record):
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    tables = [t for t in Base.metadata.sorted_tables if t.name != "photo_annotations"]
    Base.metadata.create_all(engine, tables=tables)
    return engine


def test_revision_chain_and_single_head():
    module = load_migration()
    assert module.revision == "0035_photo_annotations"
    assert module.down_revision == "0034_finding_lineage"
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    assert ScriptDirectory.from_config(config).get_heads() == ["0040_project_representatives"]


def test_upgrade_creates_the_model_table_and_downgrade_removes_only_it():
    engine = fresh_engine()
    before = set(inspect(engine).get_table_names())
    run_op(engine, lambda m: m.upgrade())
    insp = inspect(engine)
    assert set(insp.get_table_names()) == before | {"photo_annotations"}
    columns = {c["name"]: c for c in insp.get_columns("photo_annotations")}
    # 0035 alone: the contour column (14G.4, migration 0036) is not there yet
    model_columns = {c.name: c for c in PhotoAnnotation.__table__.columns if c.name != "outline"}
    assert set(columns) == set(model_columns) == {
        "id", "attachment_id", "kind", "x", "y", "label", "position", "created_at", "updated_at",
    }
    assert all(not columns[name]["nullable"] for name in columns if name != "label")
    assert columns["label"]["nullable"]
    assert [fk["referred_table"] for fk in insp.get_foreign_keys("photo_annotations")] == ["photo_attachments"]
    assert insp.get_foreign_keys("photo_annotations")[0]["options"]["ondelete"] == "CASCADE"
    assert {i["name"]: i["column_names"] for i in insp.get_indexes("photo_annotations")} == {
        "ix_photo_annotations_attachment_position": ["attachment_id", "position"]
    }
    assert {c["name"] for c in insp.get_check_constraints("photo_annotations")} == {
        "ck_photo_annotations_x_range", "ck_photo_annotations_y_range", "ck_photo_annotations_position_nonneg",
    }
    run_op(engine, lambda m: m.downgrade())
    assert set(inspect(engine).get_table_names()) == before
    run_op(engine, lambda m: m.upgrade())  # up / down / up
    assert "photo_annotations" in inspect(engine).get_table_names()


def _insert_marker(conn, attachment_id, **overrides):
    values = {
        "id": uuid.uuid4().hex, "attachment_id": attachment_id, "kind": "POINT", "x": 0.5, "y": 0.5, "label": None,
        "position": 0, "created_at": "2026-10-08", "updated_at": "2026-10-08",
    }
    values.update(overrides)
    conn.execute(
        text(
            "INSERT INTO photo_annotations (id, attachment_id, kind, x, y, label, position, created_at, updated_at) "
            "VALUES (:id, :attachment_id, :kind, :x, :y, :label, :position, :created_at, :updated_at)"
        ),
        values,
    )


@pytest.mark.parametrize(
    "overrides",
    [{"x": 1.0001}, {"x": -0.0001}, {"y": 1.5}, {"y": -1}, {"position": -1}],
)
def test_database_rejects_out_of_range_values(overrides):
    engine = fresh_engine()
    run_op(engine, lambda m: m.upgrade())
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=OFF"))
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        _insert_marker(conn, uuid.uuid4().hex, **overrides)


@pytest.mark.parametrize("edge", [{"x": 0, "y": 0}, {"x": 1, "y": 1}, {"x": 0.000001, "y": 0.999999}])
def test_database_accepts_the_edges(edge):
    engine = fresh_engine()
    run_op(engine, lambda m: m.upgrade())
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        _insert_marker(conn, uuid.uuid4().hex, **edge)


@pytest.mark.parametrize(
    "overrides",
    [{"x": 1.0001}, {"x": -0.0001}, {"y": 1.5}, {"y": -1}, {"position": -1}],
)
def test_model_metadata_enforces_the_same_checks_as_the_migration(overrides):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[PhotoAnnotation.__table__])
    with pytest.raises(IntegrityError), engine.begin() as conn:
        _insert_marker(conn, uuid.uuid4().hex, **overrides)


# ===========================================================================
# B. Pure validation
# ===========================================================================


@pytest.mark.parametrize("value", [0, 1, 0.0, 1.0, 0.5, 0.123456, 1e-6])
def test_coordinate_accepts_numbers_in_range(value):
    assert 0.0 <= normalize_coordinate(value, "x") <= 1.0


def test_coordinate_is_rounded_to_six_decimals():
    assert normalize_coordinate(0.12345678, "x") == 0.123457
    assert normalize_coordinate(0.9999996, "x") == 1.0


@pytest.mark.parametrize(
    "value", [-0.000001, 1.000001, 2, -1, math.nan, math.inf, -math.inf, True, False, "0.5", None, [0.5], {"v": 1}]
)
def test_coordinate_rejects_everything_else(value):
    with pytest.raises(PhotoAnnotationValidationError):
        normalize_coordinate(value, "x")


def test_label_rules():
    assert normalize_label(None) is None
    assert normalize_label("   ") is None
    assert normalize_label("  rysa  ") == "rysa"
    assert normalize_label("a" * MAX_LABEL_LENGTH) == "a" * MAX_LABEL_LENGTH
    assert normalize_label("ł" * MAX_LABEL_LENGTH) == "ł" * MAX_LABEL_LENGTH  # characters, not bytes
    for bad in ("a" * (MAX_LABEL_LENGTH + 1), 5, ["a"], True):
        with pytest.raises(PhotoAnnotationValidationError):
            normalize_label(bad)


def test_limit_is_ten():
    assert MAX_ANNOTATIONS_PER_ATTACHMENT == 10  # owner decision Q1 (2026-10-08)
    assert MAX_LABEL_LENGTH == 40


# ===========================================================================
# C. API
# ===========================================================================


@pytest.fixture
async def http(api):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {api.token}"
        yield client


async def upload_surface_photo(a, **kw) -> dict:
    c = await call(
        path_for(kw.pop("project", a.project)), token=kw.pop("token", a.token),
        body=form(a, context="SURFACE", target=("surface_id", str(a.surface))),
    )
    assert c.status == 201, c.body
    return c.json()


@pytest.fixture
async def photo(api):
    body = await upload_surface_photo(api)
    return body["attachment"]["id"], body["asset"]["id"]


def base(project, attachment) -> str:
    return f"/api/projects/{project}/photo-attachments/{attachment}/annotations"


async def put(http, api, attachment, *, x=0.25, y=0.75, label=None, project=None):
    payload = {"x": x, "y": y}
    if label is not None:
        payload["label"] = label
    return await http.post(base(project or api.project, attachment), json=payload)


def code(r) -> str:
    return r.json()["detail"]["code"]


async def test_create_returns_the_marker(http, api, photo):
    attachment, _ = photo
    r = await put(http, api, attachment, x=0.25, y=0.75, label="  rysa przy oknie ")
    assert r.status_code == 201, r.text
    marker = r.json()
    assert set(marker) == {"id", "attachment_id", "kind", "x", "y", "label", "outline", "position", "created_at", "updated_at"}
    assert marker["outline"] is None
    assert marker["attachment_id"] == attachment and marker["kind"] == "POINT"
    assert (marker["x"], marker["y"]) == (0.25, 0.75)
    assert marker["label"] == "rysa przy oknie" and marker["position"] == 0


async def test_positions_follow_creation_and_survive_deletes(http, api, photo):
    attachment, _ = photo
    created = [(await put(http, api, attachment, x=i / 10)).json() for i in range(3)]
    assert [m["position"] for m in created] == [0, 1, 2]
    assert (await http.delete(f"{base(api.project, attachment)}/{created[1]['id']}")).status_code == 204
    again = (await put(http, api, attachment, x=0.9)).json()
    assert again["position"] == 3  # after the last one, never reusing a gap
    listing = (await http.get(base(api.project, attachment))).json()
    assert [m["id"] for m in listing["items"]] == [created[0]["id"], created[2]["id"], again["id"]]
    assert listing["max_per_photo"] == 10


async def test_integers_zero_and_one_are_accepted(http, api, photo):
    attachment, _ = photo
    r = await http.post(base(api.project, attachment), json={"x": 0, "y": 1})
    assert r.status_code == 201 and (r.json()["x"], r.json()["y"]) == (0.0, 1.0)


async def test_coordinates_are_stored_with_six_decimals(http, api, photo):
    attachment, _ = photo
    r = await put(http, api, attachment, x=0.12345678, y=0.9999996)
    assert (r.json()["x"], r.json()["y"]) == (0.123457, 1.0)


@pytest.mark.parametrize("coords", [(1.000001, 0.5), (0.5, -0.1), (-1, 0), (2, 2)])
async def test_out_of_range_is_the_photo_error_envelope(http, api, photo, coords):
    attachment, _ = photo
    r = await put(http, api, attachment, x=coords[0], y=coords[1])
    assert r.status_code == 422 and code(r) == "PHOTO_ANNOTATION_INVALID"


@pytest.mark.parametrize("payload", [{"x": "0.5", "y": 0.5}, {"x": True, "y": 0.5}, {"x": None, "y": 0.5}, {"y": 0.5}, {"x": 0.5}, {}])
async def test_non_numbers_and_missing_coordinates_are_rejected(http, api, photo, payload):
    attachment, _ = photo
    assert (await http.post(base(api.project, attachment), json=payload)).status_code == 422


@pytest.mark.parametrize("extra", [{"finding_id": str(uuid.uuid4())}, {"position": 5}, {"kind": "POINT"}, {"severity": "HIGH"}, {"id": str(uuid.uuid4())}])
async def test_no_defect_data_position_or_identity_can_be_sent(http, api, photo, extra):
    attachment, _ = photo
    r = await http.post(base(api.project, attachment), json={"x": 0.5, "y": 0.5, **extra})
    assert r.status_code == 422
    assert (await http.get(base(api.project, attachment))).json()["items"] == []


async def test_label_length_is_checked_in_characters(http, api, photo):
    attachment, _ = photo
    assert (await put(http, api, attachment, label="ł" * 40)).status_code == 201
    r = await put(http, api, attachment, label="ł" * 41)
    assert r.status_code == 422 and code(r) == "PHOTO_ANNOTATION_INVALID"
    blank = await put(http, api, attachment, label="   ")
    assert blank.status_code == 201 and blank.json()["label"] is None


async def test_the_eleventh_marker_is_refused_and_a_delete_frees_a_place(http, api, photo):
    attachment, _ = photo
    ids = []
    for i in range(10):
        r = await put(http, api, attachment, x=i / 10)
        assert r.status_code == 201, (i, r.text)
        ids.append(r.json()["id"])
    r = await put(http, api, attachment)
    assert r.status_code == 409 and code(r) == "PHOTO_ANNOTATION_LIMIT_REACHED"
    assert len((await http.get(base(api.project, attachment))).json()["items"]) == 10
    assert (await http.delete(f"{base(api.project, attachment)}/{ids[4]}")).status_code == 204
    assert (await put(http, api, attachment)).status_code == 201
    assert (await put(http, api, attachment)).status_code == 409


async def test_label_is_the_only_editable_field(http, api, photo):
    attachment, _ = photo
    marker = (await put(http, api, attachment, x=0.1, y=0.2, label="1")).json()
    url = f"{base(api.project, attachment)}/{marker['id']}"
    r = await http.patch(url, json={"label": "pęknięcie"})
    assert r.status_code == 200 and r.json()["label"] == "pęknięcie"
    assert (r.json()["x"], r.json()["y"], r.json()["position"]) == (0.1, 0.2, 0)
    assert (await http.patch(url, json={"label": None})).json()["label"] is None
    assert (await http.patch(url, json={})).status_code == 200  # nothing to change
    for payload in ({"x": 0.9}, {"y": 0.9}, {"position": 3}, {"label": "a", "x": 0.3}, {"kind": "POINT"}, {"outline": [[0, 0], [1, 1]], "x": 0.3}):
        assert (await http.patch(url, json=payload)).status_code == 422
    too_long = await http.patch(url, json={"label": "a" * 41})
    assert too_long.status_code == 422 and code(too_long) == "PHOTO_ANNOTATION_INVALID"
    final = (await http.get(base(api.project, attachment))).json()["items"][0]
    assert (final["x"], final["y"], final["position"], final["label"]) == (0.1, 0.2, 0, None)


async def test_delete_removes_only_the_marker(http, api, photo):
    attachment, asset = photo
    marker = (await put(http, api, attachment)).json()
    url = f"{base(api.project, attachment)}/{marker['id']}"
    assert (await http.delete(url)).status_code == 204
    gone = await http.delete(url)
    assert gone.status_code == 404 and code(gone) == "PHOTO_ANNOTATION_NOT_FOUND"
    assert (await http.patch(url, json={"label": "x"})).status_code == 404
    db = api.db
    assert (await db.execute(select(func.count()).select_from(PhotoAnnotation))).scalar_one() == 0
    assert (await db.execute(select(func.count()).select_from(PhotoAttachment))).scalar_one() == 1
    assert (await db.execute(select(func.count()).select_from(PhotoAsset))).scalar_one() == 1
    assert (await http.get(f"/api/projects/{api.project}/photos/{asset}")).status_code == 200


async def test_markers_belong_to_the_attachment_not_to_the_file(http, api, photo):
    attachment, asset = photo
    second = await http.post(
        f"/api/projects/{api.project}/photos/{asset}/attachments", json={"context": "ROOM", "room_id": str(api.room)}
    )
    assert second.status_code == 201, second.text
    other = second.json()["id"]
    first_marker = (await put(http, api, attachment, label="on the surface")).json()
    assert (await http.get(base(api.project, other))).json()["items"] == []
    other_marker = (await put(http, api, other, x=0.9, label="in the room")).json()
    # a marker id of one attachment does not exist on the other
    for verb, kwargs in ((http.patch, {"json": {"label": "x"}}), (http.delete, {})):
        r = await verb(f"{base(api.project, other)}/{first_marker['id']}", **kwargs)
        assert r.status_code == 404 and code(r) == "PHOTO_ANNOTATION_NOT_FOUND"
    assert [m["id"] for m in (await http.get(base(api.project, attachment))).json()["items"]] == [first_marker["id"]]
    assert [m["id"] for m in (await http.get(base(api.project, other))).json()["items"]] == [other_marker["id"]]
    # each attachment has its own limit
    for _ in range(9):
        assert (await put(http, api, attachment)).status_code == 201
    assert (await put(http, api, attachment)).status_code == 409
    assert (await put(http, api, other)).status_code == 201


async def test_archived_attachment_is_read_only_and_restore_returns_the_same_markers(http, api, photo):
    attachment, _ = photo
    marker = (await put(http, api, attachment, label="keep")).json()
    assert (await http.post(f"/api/projects/{api.project}/photo-attachments/{attachment}/archive")).status_code == 200
    url = base(api.project, attachment)
    assert [m["id"] for m in (await http.get(url)).json()["items"]] == [marker["id"]]  # readable
    for r in (
        await put(http, api, attachment),
        await http.patch(f"{url}/{marker['id']}", json={"label": "x"}),
        await http.delete(f"{url}/{marker['id']}"),
    ):
        assert r.status_code == 409 and code(r) == "PHOTO_ANNOTATION_READ_ONLY"
    assert (await http.post(f"/api/projects/{api.project}/photo-attachments/{attachment}/restore")).status_code == 200
    assert [(m["id"], m["label"]) for m in (await http.get(url)).json()["items"]] == [(marker["id"], "keep")]
    assert (await put(http, api, attachment)).status_code == 201


async def test_archived_asset_makes_every_attachment_read_only(http, api, photo):
    attachment, asset = photo
    marker = (await put(http, api, attachment)).json()
    assert (await http.post(f"/api/projects/{api.project}/photos/{asset}/archive")).status_code == 200
    assert (await http.get(base(api.project, attachment))).status_code == 200
    r = await http.delete(f"{base(api.project, attachment)}/{marker['id']}")
    assert r.status_code == 409 and code(r) == "PHOTO_ANNOTATION_READ_ONLY"
    assert (await http.post(f"/api/projects/{api.project}/photos/{asset}/restore")).status_code == 200
    assert (await http.delete(f"{base(api.project, attachment)}/{marker['id']}")).status_code == 204


async def test_foreign_missing_and_cross_project_ids_are_one_not_found(http, api, photo):
    attachment, _ = photo
    marker = (await put(http, api, attachment)).json()
    foreign = {"Authorization": f"Bearer {api.other_token}"}
    url = f"{base(api.project, attachment)}"
    for r in (
        await http.get(url, headers=foreign),
        await http.post(url, json={"x": 0.5, "y": 0.5}, headers=foreign),
        await http.patch(f"{url}/{marker['id']}", json={"label": "x"}, headers=foreign),
        await http.delete(f"{url}/{marker['id']}", headers=foreign),
    ):
        assert r.status_code == 404 and code(r) == "PROJECT_NOT_FOUND"
    for r in (  # the owner's other project does not know the attachment
        await http.get(base(api.project2, attachment)),
        await http.post(base(api.project2, attachment), json={"x": 0.5, "y": 0.5}),
        await http.delete(f"{base(api.project2, attachment)}/{marker['id']}"),
    ):
        assert r.status_code == 404 and code(r) == "PHOTO_ATTACHMENT_NOT_FOUND"
    random_attachment = base(api.project, uuid.uuid4())
    assert (await http.get(random_attachment)).status_code == 404
    assert (await http.post(random_attachment, json={"x": 0.5, "y": 0.5})).status_code == 404
    unknown = await http.delete(f"{url}/{uuid.uuid4()}")
    assert unknown.status_code == 404 and code(unknown) == "PHOTO_ANNOTATION_NOT_FOUND"
    assert (await http.get(url)).json()["items"][0]["id"] == marker["id"]  # nothing changed


async def test_unauthenticated_calls_are_rejected(api, photo):
    attachment, _ = photo
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anonymous:
        assert (await anonymous.get(base(api.project, attachment))).status_code in (401, 403)
        assert (await anonymous.post(base(api.project, attachment), json={"x": 0.5, "y": 0.5})).status_code in (401, 403)


# -- reads: list count, detail markers ----------------------------------------


async def test_list_items_carry_the_marker_count(http, api, photo):
    attachment, asset = photo
    second = (await http.post(
        f"/api/projects/{api.project}/photos/{asset}/attachments", json={"context": "ROOM", "room_id": str(api.room)}
    )).json()["id"]
    for _ in range(3):
        await put(http, api, attachment)
    await put(http, api, second)
    items = (await http.get(f"/api/projects/{api.project}/photos")).json()["items"]
    assert {i["attachment"]["id"]: i["annotation_count"] for i in items} == {attachment: 3, second: 1}
    plain = await upload_surface_photo(api)
    items = (await http.get(f"/api/projects/{api.project}/photos?context=SURFACE&surface_id={api.surface}")).json()["items"]
    counts = {i["attachment"]["id"]: i["annotation_count"] for i in items}
    assert counts[plain["attachment"]["id"]] == (3 if plain["attachment"]["id"] == attachment else 0)


async def test_archived_view_counts_markers_too(http, api, photo):
    attachment, _ = photo
    await put(http, api, attachment)
    await http.post(f"/api/projects/{api.project}/photo-attachments/{attachment}/archive")
    items = (await http.get(f"/api/projects/{api.project}/photos?archived=true")).json()["items"]
    assert [i["annotation_count"] for i in items] == [1]
    assert (await http.get(f"/api/projects/{api.project}/photos")).json()["items"] == []


async def test_detail_returns_every_marker_of_the_asset_in_display_order(http, api, photo):
    attachment, asset = photo
    second = (await http.post(
        f"/api/projects/{api.project}/photos/{asset}/attachments", json={"context": "ROOM", "room_id": str(api.room)}
    )).json()["id"]
    a1 = (await put(http, api, attachment, label="a1")).json()
    b1 = (await put(http, api, second, label="b1")).json()
    a2 = (await put(http, api, attachment, label="a2")).json()
    detail = (await http.get(f"/api/projects/{api.project}/photos/{asset}")).json()
    assert detail["annotation_limit"] == 10
    by_attachment: dict[str, list[str]] = {}
    for marker in detail["annotations"]:
        by_attachment.setdefault(marker["attachment_id"], []).append(marker["label"])
    assert by_attachment == {attachment: ["a1", "a2"], second: ["b1"]}
    assert {m["id"] for m in detail["annotations"]} == {a1["id"], b1["id"], a2["id"]}


async def test_attachment_payloads_are_unchanged(http, api, photo):
    attachment, _ = photo
    await put(http, api, attachment)
    items = (await http.get(f"/api/projects/{api.project}/photos")).json()["items"]
    assert not any("annotation" in key for key in items[0]["attachment"])
    assert not any("annotation" in key for key in items[0]["asset"])


async def test_markers_do_not_change_counts_or_the_photo(http, api, photo):
    attachment, _ = photo
    before = (await http.get(f"/api/projects/{api.project}/photos/counts")).json()
    for _ in range(3):
        await put(http, api, attachment)
    assert (await http.get(f"/api/projects/{api.project}/photos/counts")).json() == before
    row = (await api.db.execute(select(PhotoAttachment))).scalar_one()
    assert row.archived_at is None and row.caption is None


async def test_every_marker_is_a_point(http, api, photo):
    attachment, _ = photo
    await put(http, api, attachment)
    kinds = (await api.db.execute(select(PhotoAnnotation.kind))).scalars().all()
    assert kinds == [PhotoAnnotationKind.POINT]


async def test_detail_of_one_photo_never_shows_the_markers_of_another(http, api, photo):
    attachment, asset = photo
    other_photo = await call(
        path_for(api.project), token=api.token,
        body=form(api, context="SURFACE", target=("surface_id", str(api.surface)),
                  file=("IMG_2.JPG", "image/jpeg", c4.image_bytes(color=(10, 200, 30)))),
    )
    assert other_photo.status == 201, other_photo.body
    other_attachment = other_photo.json()["attachment"]["id"]
    other_asset = other_photo.json()["asset"]["id"]
    assert other_asset != asset
    mine = (await put(http, api, attachment, label="mine")).json()
    await put(http, api, other_attachment, label="theirs")
    detail = (await http.get(f"/api/projects/{api.project}/photos/{asset}")).json()
    assert [m["id"] for m in detail["annotations"]] == [mine["id"]]


async def test_a_refused_marker_releases_the_transaction(http, api, photo):
    """The limit check runs under the attachment's row lock; the refusal must end the transaction so the lock is released."""
    attachment, _ = photo
    for _ in range(10):
        assert (await put(http, api, attachment)).status_code == 201
    assert (await put(http, api, attachment)).status_code == 409
    assert not api.db.in_transaction()
