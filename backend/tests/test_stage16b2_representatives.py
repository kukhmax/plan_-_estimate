"""Stage 16B.2: persons of an object - who acts for each side and who may accept the work and sign the protocols."""
import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from httpx import AsyncClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.models.project_representative import ProjectRepresentative
from tests.test_clients import OTHER_USER, VALID_USER, auth_header, get_token

BACKEND = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND / "alembic" / "versions" / "0040_project_representatives.py"
PROJECT = {"name": "Obiekt", "address": "ul. Długa 1", "city": "Kraków", "postal_code": "30-001"}
PERSON = {"side": "CUSTOMER_REPRESENTATIVE", "name": "Anna Nowak"}


async def project_of(client: AsyncClient, headers: dict) -> str:
    created = await client.post("/api/projects", json=PROJECT, headers=headers)
    assert created.status_code == 201, created.text
    return created.json()["id"]


def url(project_id: str, tail: str = "") -> str:
    return f"/api/projects/{project_id}/representatives{tail}"


# --- migration ---------------------------------------------------------------------------------------------


def load_migration():
    spec = importlib.util.spec_from_file_location("m0040", MIGRATION)
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
    assert module.revision == "0040_project_representatives" and module.down_revision == "0039_client_address"


def test_upgrade_matches_the_model_and_downgrade_drops_only_the_table():
    engine = old_engine()
    before = set(inspect(engine).get_table_names())
    run_migration(engine, "upgrade")
    insp = inspect(engine)
    assert set(insp.get_table_names()) == before | {"project_representatives"}
    columns = {c["name"]: c for c in insp.get_columns("project_representatives")}
    assert set(columns) == {c.name for c in ProjectRepresentative.__table__.columns}
    assert {n for n, c in columns.items() if not c["nullable"]} == {
        "id", "owner_id", "project_id", "side", "name", "may_accept_and_sign", "is_archived", "created_at", "updated_at"}
    assert {fk["referred_table"] for fk in insp.get_foreign_keys("project_representatives")} == {"users", "projects"}
    assert {c["name"] for c in insp.get_check_constraints("project_representatives")} == {
        "ck_project_representatives_side", "ck_project_representatives_name_not_empty"}
    assert [i["name"] for i in insp.get_indexes("project_representatives")] == ["ix_project_representatives_project"]
    run_migration(engine, "downgrade")
    assert set(inspect(engine).get_table_names()) == before


def test_the_database_itself_refuses_a_wrong_side_and_an_empty_name():
    engine = old_engine()
    run_migration(engine, "upgrade")
    sql = ("INSERT INTO project_representatives (id, owner_id, project_id, side, name, created_at, updated_at) "
           "VALUES (:id, 'u1', 'p1', :side, :name, '2026-10-09', '2026-10-09')")
    with engine.begin() as conn:
        conn.execute(text(sql), {"id": "a", "side": "SUPERVISION", "name": "Jan"})  # a good row
    for bad in ({"id": "b", "side": "BOSS", "name": "Jan"}, {"id": "c", "side": "SUPERVISION", "name": ""}):
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(text(sql), bad)


def test_a_project_takes_its_people_with_it():
    engine = old_engine()
    run_migration(engine, "upgrade")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO project_representatives (id, owner_id, project_id, side, name, created_at, updated_at) "
                          "VALUES ('a', 'u1', 'p1', 'CONTRACTOR', 'Jan', '2026-10-09', '2026-10-09')"))
        conn.execute(text("DELETE FROM projects WHERE id = 'p1'"))
        assert conn.execute(text("SELECT count(*) FROM project_representatives")).scalar_one() == 0


# --- API ---------------------------------------------------------------------------------------------------


async def test_add_and_read_a_person_with_everything_normalized(async_client: AsyncClient):
    headers = auth_header(await get_token(async_client, VALID_USER))
    project = await project_of(async_client, headers)
    created = await async_client.post(
        url(project),
        json={"side": "SUPERVISION", "name": "  Piotr   Wiśniewski ", "role_title": " Inspektor  nadzoru ", "phone": "+48  600 100 200",
              "email": "Piotr@Example.PL", "may_accept_and_sign": True},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert (body["side"], body["name"], body["role_title"], body["phone"], body["email"], body["may_accept_and_sign"], body["is_archived"]) == (
        "SUPERVISION", "Piotr Wiśniewski", "Inspektor nadzoru", "+48 600 100 200", "Piotr@example.pl", True, False)
    listed = (await async_client.get(url(project), headers=headers)).json()
    assert listed["total"] == 1 and listed["items"][0]["id"] == body["id"]


async def test_a_person_needs_only_a_side_and_a_name_and_may_not_sign_by_default(async_client: AsyncClient):
    headers = auth_header(await get_token(async_client, VALID_USER))
    project = await project_of(async_client, headers)
    body = (await async_client.post(url(project), json=PERSON, headers=headers)).json()
    assert (body["role_title"], body["phone"], body["email"], body["may_accept_and_sign"]) == (None, None, None, False)
    blank = (await async_client.post(url(project), json={**PERSON, "role_title": "  ", "phone": "", "email": ""}, headers=headers)).json()
    assert (blank["role_title"], blank["phone"], blank["email"]) == (None, None, None)


@pytest.mark.parametrize(
    "bad, field",
    [
        ({"side": "BOSS"}, "side"),
        ({"name": "   "}, "name"),
        ({"name": ""}, "name"),
        ({"email": "not-an-email"}, "email"),
        ({"phone": "12-34"}, "phone"),
        ({"unknown": 1}, "unknown"),
    ],
)
async def test_a_wrong_value_is_refused_naming_the_field(async_client: AsyncClient, bad, field):
    headers = auth_header(await get_token(async_client, VALID_USER))
    project = await project_of(async_client, headers)
    resp = await async_client.post(url(project), json={**PERSON, **bad}, headers=headers)
    assert resp.status_code == 422 and field in resp.text
    assert (await async_client.get(url(project), headers=headers)).json()["total"] == 0


async def test_the_list_keeps_the_order_of_adding_and_hides_archived_ones(async_client: AsyncClient):
    headers = auth_header(await get_token(async_client, VALID_USER))
    project = await project_of(async_client, headers)
    ids = []
    for name in ("Anna", "Bartek", "Celina"):
        ids.append((await async_client.post(url(project), json={**PERSON, "name": name}, headers=headers)).json()["id"])
    archived = await async_client.post(url(project, f"/{ids[1]}/archive"), headers=headers)
    assert archived.status_code == 200 and archived.json()["is_archived"] is True
    visible = (await async_client.get(url(project), headers=headers)).json()
    assert [i["name"] for i in visible["items"]] == ["Anna", "Celina"] and visible["total"] == 2
    everyone = (await async_client.get(url(project) + "?include_archived=true", headers=headers)).json()
    assert [i["name"] for i in everyone["items"]] == ["Anna", "Bartek", "Celina"]
    restored = await async_client.post(url(project, f"/{ids[1]}/restore"), headers=headers)
    assert restored.json()["is_archived"] is False
    assert (await async_client.get(url(project), headers=headers)).json()["total"] == 3


async def test_patch_changes_only_what_is_sent_and_null_clears_an_optional_field(async_client: AsyncClient):
    headers = auth_header(await get_token(async_client, VALID_USER))
    project = await project_of(async_client, headers)
    created = (await async_client.post(
        url(project), json={**PERSON, "role_title": "Kierownik", "phone": "600 100 200", "email": "a@b.pl"}, headers=headers)).json()
    target = url(project, f"/{created['id']}")
    sign = (await async_client.patch(target, json={"may_accept_and_sign": True}, headers=headers)).json()
    assert sign["may_accept_and_sign"] is True and (sign["name"], sign["role_title"], sign["phone"], sign["email"]) == ("Anna Nowak", "Kierownik", "600 100 200", "a@b.pl")
    cleared = (await async_client.patch(target, json={"phone": None, "role_title": None, "side": "CONTRACTOR"}, headers=headers)).json()
    assert (cleared["phone"], cleared["role_title"], cleared["side"], cleared["email"]) == (None, None, "CONTRACTOR", "a@b.pl")
    for body in ({"name": None}, {"side": None}, {"may_accept_and_sign": None}, {"email": "wrong"}, {"name": " "}):
        assert (await async_client.patch(target, json=body, headers=headers)).status_code == 422
    assert (await async_client.get(url(project), headers=headers)).json()["items"][0]["name"] == "Anna Nowak"


async def test_another_owner_sees_nothing_and_changes_nothing(async_client: AsyncClient):
    owner = auth_header(await get_token(async_client, VALID_USER))
    other = auth_header(await get_token(async_client, OTHER_USER))
    project = await project_of(async_client, owner)
    person = (await async_client.post(url(project), json=PERSON, headers=owner)).json()["id"]
    assert (await async_client.get(url(project), headers=other)).status_code == 404
    assert (await async_client.post(url(project), json=PERSON, headers=other)).status_code == 404
    for call in (
        async_client.patch(url(project, f"/{person}"), json={"name": "X"}, headers=other),
        async_client.post(url(project, f"/{person}/archive"), headers=other),
        async_client.post(url(project, f"/{person}/restore"), headers=other),
    ):
        assert (await call).status_code == 404
    assert (await async_client.get(url(project), headers=owner)).json()["items"][0]["name"] == "Anna Nowak"


async def test_a_person_of_one_object_cannot_be_reached_through_another_object(async_client: AsyncClient):
    headers = auth_header(await get_token(async_client, VALID_USER))
    first = await project_of(async_client, headers)
    second = await project_of(async_client, headers)
    person = (await async_client.post(url(first), json=PERSON, headers=headers)).json()["id"]
    assert (await async_client.patch(url(second, f"/{person}"), json={"name": "X"}, headers=headers)).status_code == 404
    assert (await async_client.get(url(second), headers=headers)).json()["total"] == 0
    assert (await async_client.get(url(str(uuid.uuid4())), headers=headers)).status_code == 404
