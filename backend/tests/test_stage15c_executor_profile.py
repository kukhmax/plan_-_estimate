"""Stage 15C — the executor profile: migration 0037, the service, the API and the party block of a document."""

import importlib.util
import uuid
from datetime import date
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from httpx import AsyncClient
from sqlalchemy import create_engine, event, func, inspect, select, text
from sqlalchemy.exc import IntegrityError

import app.models  # noqa: F401
from app.core.database import Base
from app.domain.documents.layout import DocumentLayout, DocumentMeta
from app.domain.documents.parties import party_from_executor_profile
from app.domain.documents.registry import DocumentKind, get_template
from app.domain.documents.templating import render_html
from app.domain.exceptions import ExecutorProfileValidationError
from app.domain.services.executor_profile_service import ExecutorProfileService
from app.models.executor_profile import ExecutorProfile
from app.models.user import User
from app.schemas.executor_profile import ExecutorProfileWrite
from tests.test_clients import OTHER_USER, VALID_USER, auth_header, get_token

BACKEND = Path(__file__).resolve().parents[1]
MIGRATION = BACKEND / "alembic" / "versions" / "0037_executor_profiles.py"
URL = "/api/executor-profile"
FULL = {
    "name": "  Jan   Kowalski  Wykończenia ",
    "nip": "774-000-14-54",
    "street": " ul. Długa  1/2 ",
    "postal_code": "30001",
    "city": " Kraków ",
    "phone": "+48  600 100 200",
    "email": "Jan@Example.PL",
    "bank_account": "PL 61 1090 1014 0000 0712 1981 2874",
}


# --- migration ----------------------------------------------------------------------------------------------


def load_migration():
    spec = importlib.util.spec_from_file_location("m0037", MIGRATION)
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

    Base.metadata.create_all(engine, tables=[t for t in Base.metadata.sorted_tables if t.name != "executor_profiles"])
    return engine


def test_revision_chain_and_single_head():
    module = load_migration()
    assert module.revision == "0037_executor_profiles" and module.down_revision == "0036_photo_annotation_outline"
    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    assert ScriptDirectory.from_config(config).get_heads() == ["0049_concealed_works"]


def test_upgrade_matches_the_model_and_downgrade_removes_only_the_table():
    engine = fresh_engine()
    before = set(inspect(engine).get_table_names())
    run_op(engine, lambda m: m.upgrade())
    insp = inspect(engine)
    assert set(insp.get_table_names()) == before | {"executor_profiles"}
    columns = {c["name"]: c for c in insp.get_columns("executor_profiles")}
    assert set(columns) == {c.name for c in ExecutorProfile.__table__.columns}
    required = {name for name, c in columns.items() if not c["nullable"]}
    assert required == {"id", "owner_id", "name", "created_at", "updated_at"}
    assert [fk["referred_table"] for fk in insp.get_foreign_keys("executor_profiles")] == ["users"]
    assert insp.get_foreign_keys("executor_profiles")[0]["options"]["ondelete"] == "CASCADE"
    uniques = insp.get_unique_constraints("executor_profiles")
    assert any(u["column_names"] == ["owner_id"] for u in uniques)
    assert {c["name"] for c in insp.get_check_constraints("executor_profiles")} == {
        "ck_executor_profiles_nip_length", "ck_executor_profiles_account_length", "ck_executor_profiles_name_not_empty",
    }
    run_op(engine, lambda m: m.downgrade())
    assert set(inspect(engine).get_table_names()) == before
    run_op(engine, lambda m: m.upgrade())
    assert "executor_profiles" in inspect(engine).get_table_names()


def _insert(conn, owner_id, **over):
    values = {"id": uuid.uuid4().hex, "owner_id": owner_id, "name": "Jan", "nip": None, "bank_account": None,
              "created_at": "2026-10-08", "updated_at": "2026-10-08"}
    values.update(over)
    conn.execute(text("INSERT INTO executor_profiles (id, owner_id, name, nip, bank_account, created_at, updated_at) "
                      "VALUES (:id, :owner_id, :name, :nip, :bank_account, :created_at, :updated_at)"), values)


def test_the_database_itself_refuses_wrong_lengths_an_empty_name_and_a_second_profile():
    engine = fresh_engine()
    run_op(engine, lambda m: m.upgrade())
    owner, other = uuid.uuid4().hex, uuid.uuid4().hex
    with engine.begin() as conn:
        for user in (owner, other):
            conn.execute(text("INSERT INTO users (id, telegram_user_id, created_at, updated_at) VALUES (:i, :t, '2026-10-08', '2026-10-08')"),
                         {"i": user, "t": int(user[:8], 16)})
        _insert(conn, owner, nip="7740001454", bank_account="61109010140000071219812874")
    for bad in ({"nip": "123"}, {"bank_account": "123"}, {"name": ""}, {"owner_id": owner}):
        with pytest.raises(IntegrityError), engine.begin() as conn:
            _insert(conn, bad.pop("owner_id", other), **bad)
    with engine.begin() as conn:  # the profile goes with its user
        conn.execute(text("DELETE FROM users WHERE id = :i"), {"i": owner})
        assert conn.execute(text("SELECT count(*) FROM executor_profiles")).scalar_one() == 0


# --- service -------------------------------------------------------------------------------------------------------


async def make_user(db, telegram_id: int) -> User:
    user = User(telegram_user_id=telegram_id, username=f"u{telegram_id}")
    db.add(user)
    await db.commit()
    return user


async def test_save_creates_then_replaces_one_profile_with_canonical_values(db_session):
    owner = await make_user(db_session, 9301)
    service = ExecutorProfileService(db_session)
    assert await service.get(owner.id) is None
    created = await service.save(owner.id, ExecutorProfileWrite(**FULL))
    assert (created.name, created.nip, created.street, created.postal_code, created.city) == (
        "Jan Kowalski Wykończenia", "7740001454", "ul. Długa 1/2", "30-001", "Kraków")
    assert (created.phone, created.email, created.bank_account) == ("+48 600 100 200", "Jan@example.pl", "61109010140000071219812874")
    first_id, first_created = created.id, created.created_at
    replaced = await service.save(owner.id, ExecutorProfileWrite(name="Firma Nowa"))
    assert replaced.id == first_id and replaced.created_at == first_created and replaced.name == "Firma Nowa"
    assert (replaced.nip, replaced.street, replaced.postal_code, replaced.city, replaced.phone, replaced.email, replaced.bank_account) == (None,) * 7
    assert (await db_session.execute(select(func.count()).select_from(ExecutorProfile))).scalar_one() == 1


async def test_blank_optional_fields_are_stored_as_nothing(db_session):
    owner = await make_user(db_session, 9302)
    profile = await ExecutorProfileService(db_session).save(
        owner.id, ExecutorProfileWrite(name="Jan", nip="  ", street="", city="   ", phone="", email=" ", bank_account="", postal_code=""))
    assert (profile.nip, profile.street, profile.city, profile.phone, profile.email, profile.bank_account, profile.postal_code) == (None,) * 7


async def test_every_wrong_field_is_reported_at_once_and_nothing_is_saved(db_session):
    owner = await make_user(db_session, 9303)
    service = ExecutorProfileService(db_session)
    with pytest.raises(ExecutorProfileValidationError) as caught:
        await service.save(owner.id, ExecutorProfileWrite(
            name="   ", nip="1234567890", postal_code="12", phone="abc", email="not-an-email", bank_account="123"))
    assert caught.value.fields == {
        "name": "NAME_REQUIRED", "nip": "NIP_INVALID", "postal_code": "POSTAL_CODE_INVALID", "phone": "PHONE_INVALID",
        "email": "EMAIL_INVALID", "bank_account": "BANK_ACCOUNT_INVALID",
    }
    assert caught.value.code == "EXECUTOR_PROFILE_INVALID"
    assert await service.get(owner.id) is None


async def test_a_wrong_save_leaves_the_saved_profile_untouched(db_session):
    owner = await make_user(db_session, 9304)
    service = ExecutorProfileService(db_session)
    await service.save(owner.id, ExecutorProfileWrite(name="Jan", nip="7740001454"))
    with pytest.raises(ExecutorProfileValidationError):
        await service.save(owner.id, ExecutorProfileWrite(name="Zmiana", nip="1"))
    kept = await service.get(owner.id)
    assert (kept.name, kept.nip) == ("Jan", "7740001454")


async def test_the_unique_owner_race_is_resolved_by_replacing(db_session, monkeypatch):
    # The truly simultaneous version of this race runs on PostgreSQL: tests/test_stage15c_postgres.py (opt-in).
    owner = await make_user(db_session, 9306)
    service = ExecutorProfileService(db_session)
    await service.save(owner.id, ExecutorProfileWrite(name="Pierwszy"))
    original, calls = service.get, {"n": 0}

    async def blind_first(owner_id):  # the first read does not see the row another request has just created
        calls["n"] += 1
        return None if calls["n"] == 1 else await original(owner_id)

    monkeypatch.setattr(service, "get", blind_first)
    saved = await service.save(owner.id, ExecutorProfileWrite(name="Drugi"))
    assert saved.name == "Drugi" and calls["n"] == 2
    assert (await db_session.execute(select(func.count()).select_from(ExecutorProfile))).scalar_one() == 1


# --- API ---------------------------------------------------------------------------------------------------------


async def test_the_api_needs_a_token(async_client: AsyncClient):
    assert (await async_client.get(URL)).status_code == 401
    assert (await async_client.put(URL, json={"name": "x"})).status_code == 401


async def test_the_api_starts_empty_then_saves_and_reads_back(async_client: AsyncClient):
    headers = auth_header(await get_token(async_client, VALID_USER))
    empty = await async_client.get(URL, headers=headers)
    assert empty.status_code == 200 and empty.json() == {"profile": None}
    saved = await async_client.put(URL, json=FULL, headers=headers)
    assert saved.status_code == 200, saved.text
    data = saved.json()
    assert data["name"] == "Jan Kowalski Wykończenia" and data["nip"] == "7740001454" and data["postal_code"] == "30-001"
    assert data["email"] == "Jan@example.pl" and data["bank_account"] == "61109010140000071219812874"
    assert set(data) == {"id", "name", "nip", "street", "postal_code", "city", "phone", "email", "bank_account", "created_at", "updated_at"}
    assert (await async_client.get(URL, headers=headers)).json() == {"profile": data}


async def test_a_second_put_replaces_and_clears_what_it_leaves_out(async_client: AsyncClient):
    headers = auth_header(await get_token(async_client, VALID_USER))
    first = (await async_client.put(URL, json=FULL, headers=headers)).json()
    second = (await async_client.put(URL, json={"name": "Tylko nazwa"}, headers=headers)).json()
    assert second["id"] == first["id"] and second["name"] == "Tylko nazwa"
    assert all(second[f] is None for f in ("nip", "street", "postal_code", "city", "phone", "email", "bank_account"))


async def test_every_owner_has_a_profile_of_their_own(async_client: AsyncClient):
    mine = auth_header(await get_token(async_client, VALID_USER))
    theirs = auth_header(await get_token(async_client, OTHER_USER))
    await async_client.put(URL, json={"name": "Moja firma", "nip": "7740001454"}, headers=mine)
    assert (await async_client.get(URL, headers=theirs)).json() == {"profile": None}
    other = await async_client.put(URL, json={"name": "Cudza firma"}, headers=theirs)
    assert other.json()["name"] == "Cudza firma"
    assert (await async_client.get(URL, headers=mine)).json()["profile"]["name"] == "Moja firma"
    assert (await async_client.get(URL, headers=theirs)).json()["profile"]["nip"] is None


async def test_wrong_fields_come_back_in_one_fixed_envelope(async_client: AsyncClient):
    headers = auth_header(await get_token(async_client, VALID_USER))
    response = await async_client.put(
        URL, json={"name": " ", "nip": "123", "email": "x", "phone": "1", "postal_code": "1", "bank_account": "1"}, headers=headers)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "EXECUTOR_PROFILE_INVALID" and isinstance(detail["message"], str)
    assert detail["fields"] == {"name": "NAME_REQUIRED", "nip": "NIP_INVALID", "email": "EMAIL_INVALID", "phone": "PHONE_INVALID",
                                "postal_code": "POSTAL_CODE_INVALID", "bank_account": "BANK_ACCOUNT_INVALID"}
    assert (await async_client.get(URL, headers=headers)).json() == {"profile": None}


@pytest.mark.parametrize(
    "body",
    [{}, {"nip": "7740001454"}, {"name": "x", "owner_id": str(uuid.uuid4())}, {"name": "x", "id": str(uuid.uuid4())},
     {"name": "x" * 256}, {"name": "x", "nip": "1" * 33}, {"name": "x", "email": "e" * 256}, {"name": 5}, {"name": None},
     {"name": "x", "phone": ["600"]}],
)
async def test_a_malformed_body_is_a_plain_422(async_client: AsyncClient, body):
    headers = auth_header(await get_token(async_client, VALID_USER))
    assert (await async_client.put(URL, json=body, headers=headers)).status_code == 422


async def test_markup_in_a_name_is_kept_as_text(async_client: AsyncClient):
    headers = auth_header(await get_token(async_client, VALID_USER))
    saved = await async_client.put(URL, json={"name": "<b>Firma</b> & Syn"}, headers=headers)
    assert saved.json()["name"] == "<b>Firma</b> & Syn"  # escaping is the template's job (tested with the documents)


# --- the party block of a document ----------------------------------------------------------------------------------


async def test_the_party_block_is_built_from_the_profile(db_session):
    owner = await make_user(db_session, 9307)
    profile = await ExecutorProfileService(db_session).save(owner.id, ExecutorProfileWrite(**FULL))
    party = party_from_executor_profile(profile)
    assert party.name == "Jan Kowalski Wykończenia" and party.tax_id == "774-000-14-54"
    assert party.address_lines == ("ul. Długa 1/2", "30-001 Kraków")
    assert (party.phone, party.email) == ("+48 600 100 200", "Jan@example.pl")


async def test_missing_parts_leave_no_empty_lines(db_session):
    owner = await make_user(db_session, 9308)
    service = ExecutorProfileService(db_session)
    only_city = party_from_executor_profile(await service.save(owner.id, ExecutorProfileWrite(name="Jan", city="Kraków")))
    assert only_city.address_lines == ("Kraków",) and only_city.tax_id is None and only_city.phone is None
    only_name = party_from_executor_profile(await service.save(owner.id, ExecutorProfileWrite(name="Jan")))
    assert only_name.address_lines == () and only_name.email is None
    postal_only = party_from_executor_profile(await service.save(owner.id, ExecutorProfileWrite(name="Jan", postal_code="30001")))
    assert postal_only.address_lines == ("30-001",)


async def test_the_executor_appears_in_the_document_header_escaped(db_session):
    owner = await make_user(db_session, 9309)
    profile = await ExecutorProfileService(db_session).save(owner.id, ExecutorProfileWrite(**{**FULL, "name": "<i>Firma</i> & Syn"}))
    layout = DocumentLayout(DocumentMeta("Dokument", date(2026, 10, 8)), executor=party_from_executor_profile(profile))
    html = render_html(get_template(DocumentKind.DIAGNOSTIC), {"layout": layout, "rows": [], "image": None})
    assert "774-000-14-54" in html and "30-001 Kraków" in html and "ul. Długa 1/2" in html
    assert "&lt;i&gt;Firma&lt;/i&gt; &amp; Syn" in html and "<i>Firma</i>" not in html
