"""Stage 16B.1: the address of the customer (street, postal code, city) for contracts and protocols."""
import importlib.util
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from httpx import AsyncClient
from sqlalchemy import create_engine, inspect, text

from app.models.client import Client
from tests.test_clients import OTHER_USER, VALID_USER, auth_header, get_token

BACKEND = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND / "alembic" / "versions" / "0039_client_address.py"
PERSON = {"client_type": "PRIVATE_PERSON", "first_name": "Jan", "last_name": "Kowalski"}


# --- migration ---------------------------------------------------------------------------------------------


def run_migration(engine, direction: str):
    spec = importlib.util.spec_from_file_location("m0039", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with engine.begin() as conn:
        module.op = Operations(MigrationContext.configure(conn))
        getattr(module, direction)()
    return module


def test_revision_chain_and_single_head():
    spec = importlib.util.spec_from_file_location("m0039", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.revision == "0039_client_address" and module.down_revision == "0038_issued_documents"
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    assert ScriptDirectory.from_config(config).get_heads() == ["0039_client_address"]


def test_upgrade_adds_three_nullable_columns_and_downgrade_removes_only_them():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE clients (id CHAR(32) PRIMARY KEY, client_type VARCHAR(20), first_name VARCHAR(255))"))
        conn.execute(text("INSERT INTO clients (id, client_type, first_name) VALUES ('a', 'PRIVATE_PERSON', 'Jan')"))
    run_migration(engine, "upgrade")
    columns = {c["name"]: c for c in inspect(engine).get_columns("clients")}
    assert {"street", "postal_code", "city"} <= set(columns) and all(columns[n]["nullable"] for n in ("street", "postal_code", "city"))
    assert columns["postal_code"]["type"].length == 10 and columns["street"]["type"].length == 255 and columns["city"]["type"].length == 128
    with engine.begin() as conn:
        assert conn.execute(text("SELECT street, postal_code, city FROM clients")).one() == (None, None, None)  # old rows keep NULL
    run_migration(engine, "downgrade")
    assert {c["name"] for c in inspect(engine).get_columns("clients")} == {"id", "client_type", "first_name"}
    assert {"street", "postal_code", "city"} <= {c.name for c in Client.__table__.columns}  # the model carries the new columns


# --- API ---------------------------------------------------------------------------------------------------


async def test_create_keeps_the_address_and_normalizes_it(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    resp = await async_client.post(
        "/api/clients",
        json={**PERSON, "street": "  ul.  Długa   1/2 ", "postal_code": "30001", "city": " Kraków "},
        headers=auth_header(token),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert (body["street"], body["postal_code"], body["city"]) == ("ul. Długa 1/2", "30-001", "Kraków")
    listed = (await async_client.get("/api/clients", headers=auth_header(token))).json()["items"]
    assert (listed[0]["street"], listed[0]["postal_code"], listed[0]["city"]) == ("ul. Długa 1/2", "30-001", "Kraków")


async def test_a_client_without_an_address_still_works(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    body = (await async_client.post("/api/clients", json=PERSON, headers=auth_header(token))).json()
    assert (body["street"], body["postal_code"], body["city"]) == (None, None, None)
    blank = (await async_client.post("/api/clients", json={**PERSON, "street": "  ", "postal_code": "", "city": ""}, headers=auth_header(token))).json()
    assert (blank["street"], blank["postal_code"], blank["city"]) == (None, None, None)


@pytest.mark.parametrize("bad", ["3001", "30-0011", "ab-cde", "30 00", "३०-००१"])
async def test_a_wrong_postal_code_is_refused(async_client: AsyncClient, bad):
    token = await get_token(async_client, VALID_USER)
    resp = await async_client.post("/api/clients", json={**PERSON, "postal_code": bad}, headers=auth_header(token))
    assert resp.status_code == 422
    assert "postal_code" in resp.text


async def test_update_changes_only_what_is_sent_and_null_clears(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    created = (await async_client.post(
        "/api/clients", json={**PERSON, "street": "Długa 1", "postal_code": "30-001", "city": "Kraków"}, headers=auth_header(token))).json()
    url = f"/api/clients/{created['id']}"
    only_city = (await async_client.patch(url, json={"city": "Warszawa"}, headers=auth_header(token))).json()
    assert (only_city["street"], only_city["postal_code"], only_city["city"]) == ("Długa 1", "30-001", "Warszawa")
    cleared = (await async_client.patch(url, json={"street": None, "postal_code": None}, headers=auth_header(token))).json()
    assert (cleared["street"], cleared["postal_code"], cleared["city"]) == (None, None, "Warszawa")
    bad = await async_client.patch(url, json={"postal_code": "12"}, headers=auth_header(token))
    assert bad.status_code == 422
    assert (await async_client.get(url, headers=auth_header(token))).json()["city"] == "Warszawa"  # the refused update changed nothing


async def test_the_address_of_one_owner_is_not_visible_to_another(async_client: AsyncClient):
    owner = await get_token(async_client, VALID_USER)
    other = await get_token(async_client, OTHER_USER)
    created = (await async_client.post("/api/clients", json={**PERSON, "street": "Długa 1"}, headers=auth_header(owner))).json()
    assert (await async_client.get(f"/api/clients/{created['id']}", headers=auth_header(other))).status_code == 404
    assert (await async_client.get("/api/clients", headers=auth_header(other))).json()["items"] == []
