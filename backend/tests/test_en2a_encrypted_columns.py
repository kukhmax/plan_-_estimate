"""EN-2a -- the personal data of the clients is stored as ciphertext and served as it was: clients, objects, persons of an object, notes."""
import base64
import os
import uuid

import pytest
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.exc import StatementError

from app.core import data_crypto as dc
from app.core.config import settings
from app.core.key_ring import owner_key_in_force, ring, set_owner_key
from app.domain.services.data_key_service import DataKeyService
from app.models.client import Client, ClientType
from app.models.data_key import DataKey
from tests.test_ac4a_archive_structure_and_ac5a_client_delete import archive, structure
from tests.test_clients import OTHER_USER, VALID_USER, auth_header, get_token
from tests.test_projects import create_project, project_payload
from tests.test_rooms import create_room


def fresh_kek() -> SecretStr:
    return SecretStr(base64.b64encode(os.urandom(32)).decode())


@pytest.fixture
def encryption_on():
    settings.DATA_KEK = fresh_kek()
    ring.disable()
    set_owner_key(None)
    yield
    settings.DATA_KEK = SecretStr("")
    ring.disable()
    set_owner_key(None)


async def raw(db, table: str, column: str) -> list[str | None]:
    """The value as the database holds it (a text query: the encrypted type does not touch it)."""
    return [row[0] for row in (await db.execute(text(f"SELECT {column} FROM {table} ORDER BY created_at, id"))).all()]


CLIENT = {
    "client_type": "PRIVATE_PERSON", "first_name": "Jan", "last_name": "Kowalski", "phone": "500 600 700", "email": "jan@example.pl",
    "nip": "1234567890", "street": "ul. Długa 1", "postal_code": "30-001", "city": "Kraków", "telegram_username": "@jankowalski", "notes": "klucz u sąsiada",
}
CLIENT_COLUMNS = ("first_name", "last_name", "phone", "email", "nip", "street", "postal_code", "city", "telegram_username", "notes")


async def test_a_client_is_stored_as_ciphertext_and_served_as_it_was(async_client, db_session, encryption_on):
    token = await get_token(async_client, VALID_USER)
    created = await async_client.post("/api/clients", json=CLIENT, headers=auth_header(token))
    assert created.status_code == 201, created.text
    for column in CLIENT_COLUMNS:
        assert created.json()[column] == CLIENT[column]
        [stored] = await raw(db_session, "clients", column)
        assert stored.startswith("enc1:") and CLIENT[column] not in stored, column
    got = await async_client.get(f"/api/clients/{created.json()['id']}", headers=auth_header(token))
    assert {column: got.json()[column] for column in CLIENT_COLUMNS} == {column: CLIENT[column] for column in CLIENT_COLUMNS}


async def test_a_missing_value_stays_null_and_is_never_encrypted(async_client, db_session, encryption_on):
    token = await get_token(async_client, VALID_USER)
    await async_client.post("/api/clients", json={"client_type": "COMPANY", "company_name": "Remontex"}, headers=auth_header(token))
    assert await raw(db_session, "clients", "phone") == [None]
    assert (await raw(db_session, "clients", "company_name"))[0].startswith("enc1:")


async def test_the_search_runs_on_the_decrypted_values(async_client, encryption_on):
    token = await get_token(async_client, VALID_USER)
    for payload in (
        {"client_type": "PRIVATE_PERSON", "first_name": "Łukasz", "last_name": "Żółć", "phone": "500111222"},
        {"client_type": "COMPANY", "company_name": "Remontex Sp. z o.o.", "phone": "600333444"},
        {"client_type": "PRIVATE_PERSON", "first_name": "Иван", "last_name": "Петров"},
    ):
        assert (await async_client.post("/api/clients", json=payload, headers=auth_header(token))).status_code == 201

    async def found(term: str) -> list[str]:
        body = (await async_client.get("/api/clients", params={"search": term}, headers=auth_header(token))).json()
        assert body["total"] == len(body["items"])
        return sorted(item["first_name"] or item["company_name"] for item in body["items"])

    assert await found("łuk") == ["Łukasz"]
    assert await found("ŻÓŁĆ") == ["Łukasz"]
    assert await found("remontex") == ["Remontex Sp. z o.o."]
    assert await found("333") == ["Remontex Sp. z o.o."]
    assert await found("петр") == ["Иван"]
    assert await found("nobody") == []
    assert (await async_client.get("/api/clients", headers=auth_header(token))).json()["total"] == 3


async def test_the_search_never_crosses_to_another_owner(async_client, encryption_on):
    token, stranger = await get_token(async_client, VALID_USER), await get_token(async_client, OTHER_USER)
    await async_client.post("/api/clients", json=CLIENT, headers=auth_header(token))
    body = (await async_client.get("/api/clients", params={"search": "kowalski"}, headers=auth_header(stranger))).json()
    assert body["total"] == 0 and body["items"] == []


async def test_an_object_is_stored_as_ciphertext(async_client, db_session, encryption_on):
    token = await get_token(async_client, VALID_USER)
    payload = project_payload("Mieszkanie Mokotów")
    created = await async_client.post("/api/projects", json=payload, headers=auth_header(token))
    assert created.status_code == 201, created.text
    for column in ("name", "address", "city", "postal_code", "description"):
        assert created.json()[column] == payload[column]
        [stored] = await raw(db_session, "projects", column)
        assert stored.startswith("enc1:") and payload[column] not in stored, column
    listed = (await async_client.get("/api/projects", headers=auth_header(token))).json()
    assert [item["name"] for item in listed["items"]] == ["Mieszkanie Mokotów"]


async def test_a_person_of_an_object_and_a_note_are_stored_as_ciphertext(async_client, db_session, encryption_on):
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token, name="Dom")
    person = await async_client.post(
        f"/api/projects/{project['id']}/representatives",
        json={"side": "SUPERVISION", "name": "Piotr Wiśniewski", "role_title": "Inspektor", "phone": "600100200", "email": "p@example.pl"},
        headers=auth_header(token),
    )
    assert person.status_code == 201, person.text
    for column, value in (("name", "Piotr Wiśniewski"), ("phone", "600100200"), ("email", "p@example.pl")):
        assert person.json()[column] == value
        [stored] = await raw(db_session, "project_representatives", column)
        assert stored.startswith("enc1:") and value not in stored, column
    assert await raw(db_session, "project_representatives", "role_title") == ["Inspektor"]  # a job title identifies nobody: not encrypted

    note = await async_client.post(f"/api/projects/{project['id']}/notes", json={"body": "Zadzwonić do klienta"}, headers=auth_header(token))
    assert note.status_code == 201, note.text
    [stored] = await raw(db_session, "project_notes", "body")
    assert stored.startswith("enc1:") and "Zadzwonić" not in stored
    listed = (await async_client.get(f"/api/projects/{project['id']}/notes", headers=auth_header(token))).json()
    assert [item["body"] for item in listed["items"]] == ["Zadzwonić do klienta"]


async def test_an_old_plain_row_is_read_as_it_is_and_the_next_save_encrypts_what_it_writes(async_client, db_session, encryption_on):
    token = await get_token(async_client, VALID_USER)
    created = await async_client.post("/api/clients", json={"client_type": "PRIVATE_PERSON", "first_name": "Jan", "last_name": "Stary"}, headers=auth_header(token))
    client_id = created.json()["id"]
    await db_session.execute(text("UPDATE clients SET first_name = 'Jan', last_name = 'Stary', notes = NULL"))
    await db_session.commit()
    assert await raw(db_session, "clients", "last_name") == ["Stary"]

    got = await async_client.get(f"/api/clients/{client_id}", headers=auth_header(token))
    assert got.json()["last_name"] == "Stary"
    patched = await async_client.patch(f"/api/clients/{client_id}", json={"notes": "nowa notatka"}, headers=auth_header(token))
    assert patched.status_code == 200, patched.text
    assert (await raw(db_session, "clients", "notes"))[0].startswith("enc1:")
    assert await raw(db_session, "clients", "last_name") == ["Stary"]  # not written, so not changed: EN-2b turns the rest
    assert (await async_client.get(f"/api/clients/{client_id}", headers=auth_header(token))).json()["last_name"] == "Stary"


async def test_every_owner_has_a_key_of_their_own(async_client, db_session, encryption_on):
    token, stranger = await get_token(async_client, VALID_USER), await get_token(async_client, OTHER_USER)
    await async_client.post("/api/clients", json=CLIENT, headers=auth_header(token))
    await async_client.post("/api/clients", json={**CLIENT, "first_name": "Ewa"}, headers=auth_header(stranger))
    keys = (await db_session.execute(select(DataKey))).scalars().all()
    assert len(keys) == 2 and len({k.owner_id for k in keys}) == 2 and all(k.active and k.wrapped_by == "SERVER_KEK" for k in keys)
    used = {value.split(":")[1] for value in await raw(db_session, "clients", "first_name")}
    assert used == {k.key_id for k in keys}
    assert all(k.wrapped_dek and "enc1" not in k.wrapped_dek for k in keys)


async def test_a_restarted_process_loads_the_keys_from_the_database(async_client, db_session, encryption_on):
    token = await get_token(async_client, VALID_USER)
    await async_client.post("/api/clients", json=CLIENT, headers=auth_header(token))
    ring.disable()  # a new process: the ring is empty, the keys are only in the database
    got = await async_client.get("/api/clients", headers=auth_header(token))
    assert got.status_code == 200 and got.json()["items"][0]["last_name"] == "Kowalski"


async def test_a_wrong_key_of_the_server_is_a_typed_error_that_shows_no_data(async_client, encryption_on):
    token = await get_token(async_client, VALID_USER)
    await async_client.post("/api/clients", json=CLIENT, headers=auth_header(token))
    settings.DATA_KEK, _ = fresh_kek(), ring.disable()
    response = await async_client.get("/api/clients", headers=auth_header(token))
    assert response.status_code == 500
    assert response.json() == {"detail": {"code": "DATA_DECRYPT_FAILED", "message": "DATA_DECRYPT_FAILED"}}


async def test_a_ciphertext_moved_into_another_column_or_damaged_is_refused(async_client, db_session, encryption_on):
    token = await get_token(async_client, VALID_USER)
    created = await async_client.post("/api/clients", json=CLIENT, headers=auth_header(token))
    url = f"/api/clients/{created.json()['id']}"
    await db_session.execute(text("UPDATE clients SET last_name = first_name"))
    await db_session.commit()
    moved = await async_client.get(url, headers=auth_header(token))
    assert moved.status_code == 500 and moved.json()["detail"]["code"] == "DATA_DECRYPT_FAILED" and "Jan" not in moved.text

    await db_session.execute(text("UPDATE clients SET last_name = substr(last_name, 1, length(last_name) - 3) || 'AAA'"))
    await db_session.commit()
    damaged = await async_client.get(url, headers=auth_header(token))
    assert damaged.status_code == 500 and damaged.json()["detail"]["code"] == "DATA_DECRYPT_FAILED"


async def test_a_write_with_no_owner_key_in_force_is_refused_and_never_stored_in_the_open(async_client, db_session, encryption_on):
    token = await get_token(async_client, VALID_USER)
    await async_client.get("/api/clients", headers=auth_header(token))  # puts the ring on
    owner_id = (await db_session.execute(text("SELECT id FROM users"))).scalar_one()
    set_owner_key(None)
    db_session.add(Client(owner_user_id=uuid.UUID(str(owner_id)), client_type=ClientType.PRIVATE_PERSON, first_name="Bez klucza"))
    with pytest.raises(StatementError) as caught:
        await db_session.flush()
    assert isinstance(caught.value.orig, dc.DataEncryptionContextMissingError)
    await db_session.rollback()
    assert await raw(db_session, "clients", "first_name") == []


async def test_a_job_of_an_owner_can_write_with_the_key_in_force(async_client, db_session, encryption_on):
    token = await get_token(async_client, VALID_USER)
    await async_client.get("/api/clients", headers=auth_header(token))
    owner_id = uuid.UUID(str((await db_session.execute(text("SELECT id FROM users"))).scalar_one()))
    key = await DataKeyService(db_session).owner_key(owner_id)
    with owner_key_in_force(key):
        db_session.add(Client(owner_user_id=owner_id, client_type=ClientType.PRIVATE_PERSON, first_name="Zadanie"))
        await db_session.commit()
    [stored] = await raw(db_session, "clients", "first_name")
    assert stored.startswith(f"enc1:{key.key_id}:")


async def test_two_requests_that_make_the_first_key_at_once_end_with_one_key(async_client, db_session, encryption_on, monkeypatch):
    token = await get_token(async_client, VALID_USER)
    owner_id = uuid.UUID(str((await db_session.execute(text("SELECT id FROM users"))).scalar_one()))
    await DataKeyService(db_session).owner_key(owner_id)  # the other request has made it
    ring.disable()
    real = DataKeyService._active_row
    calls = []

    async def blind_first(self, owner):
        calls.append(owner)
        return None if len(calls) == 1 else await real(self, owner)

    monkeypatch.setattr(DataKeyService, "_active_row", blind_first)
    assert (await async_client.post("/api/clients", json=CLIENT, headers=auth_header(token))).status_code == 201
    assert len((await db_session.execute(select(DataKey))).scalars().all()) == 1 and len(calls) == 2


async def test_with_no_key_of_the_server_nothing_is_encrypted_and_no_key_is_made(async_client, db_session):
    assert settings.DATA_KEK.get_secret_value() == ""
    token = await get_token(async_client, VALID_USER)
    await async_client.post("/api/clients", json=CLIENT, headers=auth_header(token))
    assert await raw(db_session, "clients", "last_name") == ["Kowalski"]
    assert (await db_session.execute(select(DataKey))).scalars().all() == []


async def test_encrypted_data_is_not_readable_while_the_server_has_no_key(async_client, db_session, encryption_on):
    token = await get_token(async_client, VALID_USER)
    await async_client.post("/api/clients", json=CLIENT, headers=auth_header(token))
    settings.DATA_KEK = SecretStr("")
    response = await async_client.get("/api/clients", headers=auth_header(token))
    assert response.status_code == 500 and response.json()["detail"]["code"] == "DATA_KEY_UNAVAILABLE"


async def test_the_archive_is_ordered_by_the_name_of_the_object_after_the_decryption(async_client, encryption_on):
    token = await get_token(async_client, VALID_USER)
    for name, room_name in (("Zeta", "Salon A"), ("Alfa", "Salon C"), ("Mikołajki", "Salon B")):  # the room names run against the object names
        project = await create_project(async_client, token, name=name)
        room = await create_room(async_client, token, project["id"], name=room_name)
        await archive(async_client, token, f"/api/projects/{project['id']}/rooms/{room['id']}")
    body = await structure(async_client, token)
    assert [row["project_name"] for row in body["rooms"]] == ["Alfa", "Mikołajki", "Zeta"] and body["rooms_total"] == 3


async def test_production_does_not_start_without_the_key_of_the_server(monkeypatch):
    from app.main import app, lifespan

    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "DATA_KEK", SecretStr(""))
    with pytest.raises(RuntimeError, match="DATA_KEK"):
        async with lifespan(app):
            pass


async def test_the_calendar_loop_reads_the_encrypted_names_in_a_fresh_process(db_session, encryption_on):
    from app.models.room import Room
    from app.models.surface import Surface, SurfaceType
    from app.models.user import User
    from tests.test_stage18d_dispatcher import NOW, FakeSender, dispatcher, reminder

    user = User(telegram_user_id=900777, first_name="Test", language_code="pl")
    db_session.add(user)
    await db_session.flush()
    service = DataKeyService(db_session)
    assert await service.prepare()
    with owner_key_in_force(await service.owner_key(user.id)):
        from app.models.project import Project

        project = Project(owner_id=user.id, name="Kowalski", address="ul. 1", city="Kraków", postal_code="30-001")
        db_session.add(project)
        await db_session.flush()
        room = Room(project_id=project.id, name="Łazienka")
        db_session.add(room)
        await db_session.flush()
        surface = Surface(room_id=room.id, name="Ściana A", surface_type=SurfaceType.WALL)
        db_session.add(surface)
        await db_session.commit()
    assert (await raw(db_session, "projects", "name"))[0].startswith("enc1:")
    db_session.add(reminder(user, project, room, surface))
    await db_session.commit()

    ring.disable()  # a new process: nothing in the ring yet
    set_owner_key(None)
    sender = FakeSender()
    report = await dispatcher(sender).tick(NOW)
    assert report.sent == 1 and "Kowalski" in sender.calls[0][1]

    ring.disable()
    assert await dispatcher(FakeSender()).reconcile_all(NOW) == 1 and ring.enabled


async def test_the_key_of_an_owner_is_found_once_and_then_kept(async_client, encryption_on, monkeypatch):
    token = await get_token(async_client, VALID_USER)
    real = DataKeyService._active_row
    calls = []

    async def spy(self, owner):
        calls.append(owner)
        return await real(self, owner)

    monkeypatch.setattr(DataKeyService, "_active_row", spy)
    for _ in range(3):
        assert (await async_client.get("/api/clients", headers=auth_header(token))).status_code == 200
    assert len(calls) == 1  # only the first request looks for the key (and makes it); the next two take it from the ring


async def test_a_key_made_by_another_process_is_loaded_by_the_next_request(db_session, encryption_on):
    from app.models.user import User

    service = DataKeyService(db_session)
    assert await service.prepare()
    first, other = User(telegram_user_id=900887, first_name="Pierwszy"), User(telegram_user_id=900888, first_name="Inny")
    db_session.add_all([first, other])
    await db_session.flush()
    await service.owner_key(first.id)  # the ring already knows a key
    kek = dc.parse_kek(settings.DATA_KEK.get_secret_value())
    dek = dc.new_key()
    db_session.add(DataKey(owner_id=other.id, key_id="made-elsewhere", wrapped_dek=dc.wrap_key(kek, dek, "made-elsewhere"), active=True))
    await db_session.commit()
    assert "made-elsewhere" not in ring.known()
    await service.prepare()
    assert ring.get("made-elsewhere") == dek
