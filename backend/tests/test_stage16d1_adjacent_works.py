"""Stage 16D.1: the register of other contractors' works on an object (who, where, when, in which order, who answers)."""
import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from httpx import AsyncClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.models.adjacent_work import AdjacentWork
from tests.test_clients import OTHER_USER, VALID_USER, auth_header, get_token

BACKEND = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND / "alembic" / "versions" / "0042_adjacent_works.py"
PROJECT = {"name": "Obiekt", "address": "ul. Długa 1", "city": "Kraków", "postal_code": "30-001"}
WORK = {"work_name": "Instalacja elektryczna", "order_relation": "BEFORE_OURS"}


async def project_of(client: AsyncClient, headers: dict) -> str:
    created = await client.post("/api/projects", json=PROJECT, headers=headers)
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def room_of(client: AsyncClient, headers: dict, project: str, name="Salon") -> str:
    created = await client.post(f"/api/projects/{project}/rooms", json={"name": name}, headers=headers)
    assert created.status_code == 201, created.text
    return created.json()["id"]


def url(project_id: str, tail: str = "") -> str:
    return f"/api/projects/{project_id}/adjacent-works{tail}"


# --- migration -----------------------------------------------------------------------------------------------------------


def load_migration():
    spec = importlib.util.spec_from_file_location("m0042", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_migration(engine, direction: str):
    module = load_migration()
    with engine.begin() as conn:
        module.op = Operations(MigrationContext.configure(conn))
        getattr(module, direction)()


def old_engine():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.execute(text("CREATE TABLE users (id CHAR(32) PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE projects (id CHAR(32) PRIMARY KEY)"))
        conn.execute(text("INSERT INTO users (id) VALUES ('u1')"))
        conn.execute(text("INSERT INTO projects (id) VALUES ('p1')"))
    return engine


def test_revision_chain():
    module = load_migration()
    assert module.revision == "0042_adjacent_works" and module.down_revision == "0041_issued_documents_tech_card"


def test_upgrade_matches_the_model_and_downgrade_drops_only_the_table():
    engine = old_engine()
    before = set(inspect(engine).get_table_names())
    run_migration(engine, "upgrade")
    insp = inspect(engine)
    assert set(insp.get_table_names()) == before | {"adjacent_works"}
    columns = {c["name"]: c for c in insp.get_columns("adjacent_works")}
    assert set(columns) == {c.name for c in AdjacentWork.__table__.columns}
    assert {n for n, c in columns.items() if not c["nullable"]} == {
        "id", "owner_id", "project_id", "work_name", "order_relation", "position", "is_archived", "created_at", "updated_at"}
    assert {fk["referred_table"] for fk in insp.get_foreign_keys("adjacent_works")} == {"users", "projects"}
    assert {c["name"] for c in insp.get_check_constraints("adjacent_works")} == {
        "ck_adjacent_works_order", "ck_adjacent_works_name_not_empty", "ck_adjacent_works_period"}
    assert [i["name"] for i in insp.get_indexes("adjacent_works")] == ["ix_adjacent_works_project"]
    run_migration(engine, "downgrade")
    assert set(inspect(engine).get_table_names()) == before


def test_the_database_itself_refuses_a_wrong_order_an_empty_name_and_an_upside_down_period():
    engine = old_engine()
    run_migration(engine, "upgrade")
    sql = ("INSERT INTO adjacent_works (id, owner_id, project_id, work_name, order_relation, period_from, period_to, position, created_at, updated_at) "
           "VALUES (:id, 'u1', 'p1', :name, :order, :a, :b, 0, '2026-10-09', '2026-10-09')")
    good = {"id": "a", "name": "Elektryka", "order": "PARALLEL", "a": "2026-10-10", "b": "2026-10-12"}
    with engine.begin() as conn:
        conn.execute(text(sql), good)
        conn.execute(text(sql), {**good, "id": "n", "a": None, "b": "2026-10-01"})  # one end open is fine
    for bad in ({"id": "b", "order": "LATER"}, {"id": "c", "name": ""}, {"id": "d", "a": "2026-10-12", "b": "2026-10-10"}):
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(text(sql), {**good, **bad})


def test_a_project_takes_its_adjacent_works_with_it():
    engine = old_engine()
    run_migration(engine, "upgrade")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO adjacent_works (id, owner_id, project_id, work_name, order_relation, position, created_at, updated_at) "
                          "VALUES ('a', 'u1', 'p1', 'x', 'PARALLEL', 0, '2026-10-09', '2026-10-09')"))
        conn.execute(text("DELETE FROM projects WHERE id = 'p1'"))
        assert conn.execute(text("SELECT count(*) FROM adjacent_works")).scalar_one() == 0


# --- API -----------------------------------------------------------------------------------------------------------------


async def test_add_and_read_an_entry_with_everything_trimmed(async_client: AsyncClient):
    headers = auth_header(await get_token(async_client, VALID_USER))
    project = await project_of(async_client, headers)
    salon = await room_of(async_client, headers, project)
    created = await async_client.post(
        url(project),
        json={"work_name": "  Instalacja   elektryczna ", "performer": " Firma  Prąd ", "room_ids": [salon, salon],
              "period_from": "2026-10-12", "period_to": "2026-10-14", "order_relation": "BEFORE_OURS",
              "order_note": " elektryka przed tynkiem ", "responsibility_note": "sprząta wykonawca instalacji",
              "coordination_note": "  "},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert (body["work_name"], body["performer"], body["room_ids"], body["period_from"], body["period_to"], body["order_relation"]) == (
        "Instalacja elektryczna", "Firma Prąd", [salon], "2026-10-12", "2026-10-14", "BEFORE_OURS")
    assert (body["order_note"], body["responsibility_note"], body["coordination_note"], body["is_archived"]) == (
        "elektryka przed tynkiem", "sprząta wykonawca instalacji", None, False)
    listed = (await async_client.get(url(project), headers=headers)).json()
    assert listed["total"] == 1 and listed["items"][0]["id"] == body["id"]


async def test_an_entry_needs_only_a_name_and_an_order_and_covers_the_whole_object_by_default(async_client: AsyncClient):
    headers = auth_header(await get_token(async_client, VALID_USER))
    project = await project_of(async_client, headers)
    body = (await async_client.post(url(project), json=WORK, headers=headers)).json()
    assert (body["performer"], body["room_ids"], body["period_from"], body["period_to"]) == (None, None, None, None)


@pytest.mark.parametrize(
    "bad, field",
    [
        ({"order_relation": "LATER"}, "order_relation"),
        ({"work_name": "   "}, "work_name"),
        ({"room_ids": []}, "room_ids"),
        ({"period_from": "2026-10-14", "period_to": "2026-10-12"}, "period_to"),
        ({"period_from": "tomorrow"}, "period_from"),
        ({"unknown": 1}, "unknown"),
    ],
)
async def test_a_wrong_value_is_refused_naming_the_field(async_client: AsyncClient, bad, field):
    headers = auth_header(await get_token(async_client, VALID_USER))
    project = await project_of(async_client, headers)
    resp = await async_client.post(url(project), json={**WORK, **bad}, headers=headers)
    assert resp.status_code == 422 and field in resp.text
    assert (await async_client.get(url(project), headers=headers)).json()["total"] == 0


async def test_a_room_of_another_object_or_an_archived_room_is_refused(async_client: AsyncClient):
    headers = auth_header(await get_token(async_client, VALID_USER))
    first = await project_of(async_client, headers)
    second = await project_of(async_client, headers)
    foreign = await room_of(async_client, headers, second)
    own = await room_of(async_client, headers, first)
    for rooms in ([foreign], [own, foreign], [str(uuid.uuid4())]):
        resp = await async_client.post(url(first), json={**WORK, "room_ids": rooms}, headers=headers)
        assert resp.status_code == 422 and resp.json()["detail"]["code"] == "ADJACENT_WORK_ROOM_INVALID"
    ok = (await async_client.post(url(first), json={**WORK, "room_ids": [own]}, headers=headers)).json()
    archived = await async_client.post(f"/api/projects/{first}/rooms/{own}/archive", headers=headers)
    assert archived.status_code == 200, archived.text
    # a room archived after the entry stays in the entry, but a new entry cannot name it
    resp = await async_client.post(url(first), json={**WORK, "room_ids": [own]}, headers=headers)
    assert resp.status_code == 422 and resp.json()["detail"]["code"] == "ADJACENT_WORK_ROOM_INVALID"
    assert ok["room_ids"] == [own]
    assert (await async_client.get(url(first), headers=headers)).json()["items"][0]["room_ids"] == [own]


async def test_the_list_keeps_the_order_of_adding_and_hides_archived_ones(async_client: AsyncClient):
    headers = auth_header(await get_token(async_client, VALID_USER))
    project = await project_of(async_client, headers)
    ids = []
    for name in ("Elektryka", "Hydraulika", "Płytki"):
        ids.append((await async_client.post(url(project), json={**WORK, "work_name": name}, headers=headers)).json()["id"])
    archived = await async_client.post(url(project, f"/{ids[1]}/archive"), headers=headers)
    assert archived.status_code == 200 and archived.json()["is_archived"] is True
    visible = (await async_client.get(url(project), headers=headers)).json()
    assert [i["work_name"] for i in visible["items"]] == ["Elektryka", "Płytki"] and visible["total"] == 2
    everyone = (await async_client.get(url(project) + "?include_archived=true", headers=headers)).json()
    assert [i["work_name"] for i in everyone["items"]] == ["Elektryka", "Hydraulika", "Płytki"]
    assert (await async_client.post(url(project, f"/{ids[1]}/restore"), headers=headers)).json()["is_archived"] is False
    assert (await async_client.get(url(project), headers=headers)).json()["total"] == 3


async def test_patch_changes_only_what_is_sent_and_null_clears_an_optional_field(async_client: AsyncClient):
    headers = auth_header(await get_token(async_client, VALID_USER))
    project = await project_of(async_client, headers)
    salon = await room_of(async_client, headers, project)
    created = (await async_client.post(
        url(project), json={**WORK, "performer": "Firma Prąd", "room_ids": [salon], "period_from": "2026-10-12", "order_note": "przed tynkiem"},
        headers=headers)).json()
    target = url(project, f"/{created['id']}")
    moved = (await async_client.patch(target, json={"order_relation": "PARALLEL"}, headers=headers)).json()
    assert moved["order_relation"] == "PARALLEL" and (moved["performer"], moved["room_ids"], moved["order_note"]) == ("Firma Prąd", [salon], "przed tynkiem")
    cleared = (await async_client.patch(target, json={"performer": None, "room_ids": None, "period_from": None}, headers=headers)).json()
    assert (cleared["performer"], cleared["room_ids"], cleared["period_from"], cleared["order_note"]) == (None, None, None, "przed tynkiem")
    for body in ({"work_name": None}, {"order_relation": None}, {"work_name": " "}, {"room_ids": []}):
        assert (await async_client.patch(target, json=body, headers=headers)).status_code == 422
    # a change that alone would turn the stored period upside down is refused too
    assert (await async_client.patch(target, json={"period_from": "2026-10-12", "period_to": "2026-10-13"}, headers=headers)).status_code == 200
    upside_down = await async_client.patch(target, json={"period_to": "2026-10-01"}, headers=headers)
    assert upside_down.status_code == 422 and upside_down.json()["detail"]["code"] == "ADJACENT_WORK_PERIOD_INVALID"
    assert (await async_client.get(url(project), headers=headers)).json()["items"][0]["period_to"] == "2026-10-13"


async def test_another_owner_sees_nothing_and_changes_nothing(async_client: AsyncClient):
    owner = auth_header(await get_token(async_client, VALID_USER))
    other = auth_header(await get_token(async_client, OTHER_USER))
    project = await project_of(async_client, owner)
    entry = (await async_client.post(url(project), json=WORK, headers=owner)).json()["id"]
    assert (await async_client.get(url(project), headers=other)).status_code == 404
    assert (await async_client.post(url(project), json=WORK, headers=other)).status_code == 404
    for call in (
        async_client.patch(url(project, f"/{entry}"), json={"work_name": "X"}, headers=other),
        async_client.post(url(project, f"/{entry}/archive"), headers=other),
        async_client.post(url(project, f"/{entry}/restore"), headers=other),
    ):
        assert (await call).status_code == 404
    assert (await async_client.get(url(project), headers=owner)).json()["items"][0]["work_name"] == "Instalacja elektryczna"


async def test_an_entry_of_one_object_cannot_be_reached_through_another_object(async_client: AsyncClient):
    headers = auth_header(await get_token(async_client, VALID_USER))
    first = await project_of(async_client, headers)
    second = await project_of(async_client, headers)
    entry = (await async_client.post(url(first), json=WORK, headers=headers)).json()["id"]
    assert (await async_client.patch(url(second, f"/{entry}"), json={"work_name": "X"}, headers=headers)).status_code == 404
    assert (await async_client.get(url(second), headers=headers)).json()["total"] == 0
    assert (await async_client.get(url(str(uuid.uuid4())), headers=headers)).status_code == 404


async def test_every_route_needs_a_token(async_client: AsyncClient):
    pid, wid = uuid.uuid4(), uuid.uuid4()
    for method, path in (("GET", url(str(pid))), ("POST", url(str(pid))), ("PATCH", url(str(pid), f"/{wid}")),
                         ("POST", url(str(pid), f"/{wid}/archive")), ("POST", url(str(pid), f"/{wid}/restore"))):
        assert (await async_client.request(method, path, json={})).status_code == 401, (method, path)
