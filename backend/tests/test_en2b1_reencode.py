"""EN-2b-1 -- the re-encoding of the plain values and the strict read."""
import io
import uuid

import pytest
from pydantic import SecretStr
from sqlalchemy import select, text

from app.cli import reencode_data
from app.core import data_crypto as dc
from app.core.config import settings
from app.core.key_ring import ring, set_owner_key
from app.domain.services.data_reencode_service import (
    DataReencodeService,
    encrypted_columns,
)
from app.models.data_key import DataKey
from tests.conftest import TestingSessionLocal, fresh_kek
from tests.test_clients import OTHER_USER, VALID_USER, auth_header, get_token
from tests.test_en2a_encrypted_columns import CLIENT, CLIENT_COLUMNS, raw
from tests.test_projects import create_project


@pytest.fixture(autouse=True)
def strict_off():
    settings.DATA_STRICT_READ = False
    yield
    settings.DATA_STRICT_READ = False


async def plain_world(async_client, token) -> dict:
    """The data as it was before EN-2a: written with encryption off, so every value is plain in the database."""
    assert settings.DATA_KEK.get_secret_value() == ""
    headers = auth_header(token)
    client = (await async_client.post("/api/clients", json=CLIENT, headers=headers)).json()
    project = await create_project(async_client, token, name="Mieszkanie Mokotów")
    person = (await async_client.post(
        f"/api/projects/{project['id']}/representatives",
        json={"side": "SUPERVISION", "name": "Piotr Wiśniewski", "phone": "+48 600 100 200", "email": "p@example.pl"}, headers=headers)).json()
    note = (await async_client.post(f"/api/projects/{project['id']}/notes", json={"body": "Zadzwonić do klienta"}, headers=headers)).json()
    return {"client": client, "project": project, "person": person, "note": note}


def service(batch: int = 200) -> DataReencodeService:
    return DataReencodeService(TestingSessionLocal, batch_size=batch)


def by_column(stats):
    return {f"{s.table}.{s.column}": s for s in stats}


def turn_encryption_on():
    settings.DATA_KEK = fresh_kek()
    ring.disable()
    set_owner_key(None)


def test_the_columns_come_from_the_models():
    columns = encrypted_columns()
    names = {f"{c.table}.{c.column}" for c in columns}
    assert len(columns) == 64 and "clients.first_name" in names and "projects.name" in names and "project_notes.body" in names  # 20 of EN-2a + 37 of EN-2b-2 + 4 of EN-2b-3 + 3 of V2-8 (two words of a proposal, the name of a signer)
    assert {c.table for c in columns} == {
        "clients", "projects", "project_representatives", "project_notes",
        "contracts", "handover_protocols", "concealed_works_protocols", "acceptance_protocols", "decision_protocols", "downtime_episodes", "issued_documents", "project_payments",
        "client_proposals", "client_consents",
    }
    assert all(c.label == f"{c.table}.{c.column}" for c in columns)
    assert {c.owner_column for c in columns if c.table == "clients"} == {"owner_user_id"} and {c.owner_column for c in columns if c.table == "projects"} == {"owner_id"}


async def test_report_counts_the_plain_values_and_changes_nothing(async_client, db_session, encryption_on):
    settings.DATA_KEK = SecretStr("")
    token = await get_token(async_client, VALID_USER)
    await plain_world(async_client, token)
    turn_encryption_on()
    stats = by_column(await service().count())
    assert (stats["clients.first_name"].non_null, stats["clients.first_name"].encrypted, stats["clients.first_name"].plain) == (1, 0, 1)
    assert stats["clients.company_name"].non_null == 0  # a missing value is not counted
    assert stats["project_notes.body"].plain == 1 and stats["projects.name"].plain == 1
    assert sum(s.plain for s in stats.values()) == 10 + 5 + 3 + 1  # the client has no company_name; a job title of a person is not encrypted
    assert await raw(db_session, "clients", "first_name") == ["Jan"]
    assert (await db_session.execute(select(DataKey))).scalars().all() == []


async def test_apply_turns_every_plain_value_into_ciphertext_and_the_reads_do_not_change(async_client, db_session, encryption_on):
    settings.DATA_KEK = SecretStr("")
    token = await get_token(async_client, VALID_USER)
    world = await plain_world(async_client, token)
    before = (await db_session.execute(text("SELECT updated_at FROM clients"))).scalar_one()
    turn_encryption_on()

    stats = by_column(await service().apply())
    assert all(s.plain == 0 for s in stats.values())
    assert stats["clients.last_name"].converted == 1 and stats["projects.address"].converted == 1 and stats["project_representatives.email"].converted == 1
    assert sum(s.converted for s in stats.values()) == 19
    for column in CLIENT_COLUMNS:
        [stored] = await raw(db_session, "clients", column)
        assert stored.startswith("enc1:") and CLIENT[column] not in stored
    assert (await db_session.execute(text("SELECT updated_at FROM clients"))).scalar_one() == before  # a re-encoding is not an edit

    again = by_column(await service().apply())
    assert sum(s.converted for s in again.values()) == 0  # idempotent
    headers = auth_header(token)
    got = (await async_client.get(f"/api/clients/{world['client']['id']}", headers=headers)).json()
    assert {c: got[c] for c in CLIENT_COLUMNS} == {c: CLIENT[c] for c in CLIENT_COLUMNS}
    assert (await async_client.get(f"/api/projects/{world['project']['id']}", headers=headers)).json()["name"] == "Mieszkanie Mokotów"
    notes = (await async_client.get(f"/api/projects/{world['project']['id']}/notes", headers=headers)).json()
    assert [n["body"] for n in notes["items"]] == ["Zadzwonić do klienta"]
    assert len((await db_session.execute(select(DataKey))).scalars().all()) == 1  # the key of the owner was made on the way


async def test_a_run_can_be_stopped_and_started_again(async_client, db_session, encryption_on):
    settings.DATA_KEK = SecretStr("")
    token = await get_token(async_client, VALID_USER)
    for name in ("Anna", "Beata", "Celina", "Dorota"):
        await async_client.post("/api/clients", json={"client_type": "PRIVATE_PERSON", "first_name": name, "last_name": "Test"}, headers=auth_header(token))
    turn_encryption_on()
    first = by_column(await service(batch=2).apply(limit=3))
    assert sum(s.converted for s in first.values()) == 3
    assert by_column(await service().count())["clients.first_name"].plain == 1
    rest = by_column(await service(batch=2).apply())
    assert sum(s.converted for s in rest.values()) == 5  # the last first_name and the four last_name
    assert sum(s.plain for s in rest.values()) == 0


async def test_a_value_changed_in_the_meantime_is_skipped_and_never_overwritten(async_client, db_session, encryption_on, monkeypatch):
    settings.DATA_KEK = SecretStr("")
    token = await get_token(async_client, VALID_USER)
    await async_client.post("/api/clients", json={"client_type": "PRIVATE_PERSON", "first_name": "Stare"}, headers=auth_header(token))
    turn_encryption_on()
    original = DataReencodeService._batch_of
    done = []

    async def changing(self, db, col, *, encrypted, after):
        rows = await original(self, db, col, encrypted=encrypted, after=after)
        if rows and not encrypted and col.column == "first_name" and not done:
            done.append(1)
            async with TestingSessionLocal() as other:  # the owner saves the client between the read and the write of the command
                await other.execute(text("UPDATE clients SET first_name = 'Nowe'"))
                await other.commit()
        return rows

    monkeypatch.setattr(DataReencodeService, "_batch_of", changing)
    stats = by_column(await service().apply())
    assert stats["clients.first_name"].skipped_changed == 1 and stats["clients.first_name"].converted == 0
    assert await raw(db_session, "clients", "first_name") == ["Nowe"]  # the owner's value stays
    monkeypatch.undo()
    assert by_column(await service().apply())["clients.first_name"].converted == 1


async def test_every_owner_is_sealed_with_their_own_key(async_client, db_session, encryption_on):
    settings.DATA_KEK = SecretStr("")
    token, stranger = await get_token(async_client, VALID_USER), await get_token(async_client, OTHER_USER)
    await async_client.post("/api/clients", json={**CLIENT, "first_name": "Jan"}, headers=auth_header(token))
    await async_client.post("/api/clients", json={**CLIENT, "first_name": "Ewa"}, headers=auth_header(stranger))
    turn_encryption_on()
    await service().apply()
    keys = {k.owner_id: k.key_id for k in (await db_session.execute(select(DataKey))).scalars()}
    assert len(keys) == 2
    rows = (await db_session.execute(text("SELECT owner_user_id, first_name FROM clients"))).all()
    for owner, value in rows:
        assert value.split(":")[1] == keys[uuid.UUID(str(owner))]


async def test_an_empty_text_is_ciphertext_too(async_client, db_session, encryption_on):
    settings.DATA_KEK = SecretStr("")
    token = await get_token(async_client, VALID_USER)
    created = await async_client.post("/api/clients", json={"client_type": "PRIVATE_PERSON", "first_name": "Jan"}, headers=auth_header(token))
    await db_session.execute(text("UPDATE clients SET notes = ''"))
    await db_session.commit()
    turn_encryption_on()
    await service().apply()
    assert (await raw(db_session, "clients", "notes"))[0].startswith("enc1:")
    assert (await async_client.get(f"/api/clients/{created.json()['id']}", headers=auth_header(token))).json()["notes"] == ""


async def test_verify_decrypts_every_ciphertext_and_counts_the_bad_ones(async_client, db_session, encryption_on):
    token = await get_token(async_client, VALID_USER)
    await async_client.post("/api/clients", json=CLIENT, headers=auth_header(token))
    clean = by_column(await service().count(verify=True))
    assert sum(s.undecryptable for s in clean.values()) == 0
    await db_session.execute(text("UPDATE clients SET last_name = first_name"))  # a ciphertext moved to another column
    await db_session.commit()
    bad = by_column(await service().count(verify=True))
    assert bad["clients.last_name"].undecryptable == 1 and sum(s.undecryptable for s in bad.values()) == 1


async def test_without_the_key_of_the_server_nothing_is_done(async_client):
    with pytest.raises(dc.DataKeyConfigurationError):
        await service().apply()
    with pytest.raises(dc.DataKeyConfigurationError):
        await service().count()


# --- the strict read ---------------------------------------------------------------------------------------------------------------------


async def test_the_strict_read_refuses_a_plain_value_and_accepts_the_re_encoded_one(async_client, db_session, encryption_on):
    settings.DATA_KEK = SecretStr("")
    token = await get_token(async_client, VALID_USER)
    created = await async_client.post("/api/clients", json=CLIENT, headers=auth_header(token))
    url = f"/api/clients/{created.json()['id']}"
    turn_encryption_on()
    assert (await async_client.get(url, headers=auth_header(token))).status_code == 200  # soft: the plain value is read
    settings.DATA_STRICT_READ = True
    refused = await async_client.get(url, headers=auth_header(token))
    assert refused.status_code == 500 and refused.json()["detail"]["code"] == "DATA_PLAIN_VALUE_REFUSED" and "Kowalski" not in refused.text
    await service().apply()
    ok = await async_client.get(url, headers=auth_header(token))
    assert ok.status_code == 200 and ok.json()["last_name"] == "Kowalski"


async def test_the_strict_read_does_not_touch_a_missing_value_nor_a_new_write(async_client, encryption_on):
    settings.DATA_STRICT_READ = True
    token = await get_token(async_client, VALID_USER)
    created = await async_client.post("/api/clients", json={"client_type": "COMPANY", "company_name": "Remontex"}, headers=auth_header(token))
    assert created.status_code == 201
    got = await async_client.get(f"/api/clients/{created.json()['id']}", headers=auth_header(token))
    assert got.status_code == 200 and got.json()["phone"] is None and got.json()["company_name"] == "Remontex"


async def test_the_strict_flag_does_nothing_while_encryption_is_off(async_client):
    settings.DATA_STRICT_READ = True
    token = await get_token(async_client, VALID_USER)
    created = await async_client.post("/api/clients", json=CLIENT, headers=auth_header(token))
    assert created.status_code == 201 and (await async_client.get("/api/clients", headers=auth_header(token))).status_code == 200


# --- the command ---------------------------------------------------------------------------------------------------------------------------


async def run_cli(monkeypatch, *argv) -> tuple[int, str]:
    monkeypatch.setattr(reencode_data, "async_session_maker", TestingSessionLocal)
    out = io.StringIO()
    code = await reencode_data.run(list(argv), out)
    return code, out.getvalue()


async def test_the_command_reports_applies_and_verifies_with_counts_only(async_client, db_session, encryption_on, monkeypatch):
    settings.DATA_KEK = SecretStr("")
    token = await get_token(async_client, VALID_USER)
    await plain_world(async_client, token)
    turn_encryption_on()

    code, text_out = await run_cli(monkeypatch, "report")
    assert code == 0 and "TOTAL plain=19 ciphertext=0" in text_out and "clients.first_name" in text_out
    code, text_out = await run_cli(monkeypatch, "verify")
    assert code == 3 and "plain=19" in text_out  # something is still plain: not done
    code, text_out = await run_cli(monkeypatch, "apply", "--limit", "5")
    assert code == 0 and "plain=14" in text_out
    code, text_out = await run_cli(monkeypatch, "apply")
    assert code == 0 and "TOTAL plain=0 ciphertext=19" in text_out
    code, text_out = await run_cli(monkeypatch, "verify")
    assert code == 0 and "TOTAL plain=0 ciphertext=19 undecryptable=0" in text_out
    for secret in ("Kowalski", "Mokotów", "Wiśniewski", "Zadzwonić", "enc1:"):
        assert secret not in text_out


async def test_the_command_exit_codes(async_client, db_session, encryption_on, monkeypatch):
    assert (await run_cli(monkeypatch, "apply", "--limit", "0"))[0] == 2
    assert (await run_cli(monkeypatch, "report", "--batch-size", "0"))[0] == 2
    settings.DATA_KEK = SecretStr("")
    code, text_out = await run_cli(monkeypatch, "report")
    assert code == 4 and "DATA_KEK" in text_out
    turn_encryption_on()
    token = await get_token(async_client, VALID_USER)
    await async_client.post("/api/clients", json=CLIENT, headers=auth_header(token))
    await db_session.execute(text("UPDATE clients SET last_name = first_name"))
    await db_session.commit()
    code, text_out = await run_cli(monkeypatch, "verify")
    assert code == 3 and "undecryptable=1" in text_out


async def test_the_command_says_so_when_a_value_was_skipped_because_it_changed(async_client, db_session, encryption_on, monkeypatch):
    settings.DATA_KEK = SecretStr("")
    token = await get_token(async_client, VALID_USER)
    await async_client.post("/api/clients", json={"client_type": "PRIVATE_PERSON", "first_name": "Stare"}, headers=auth_header(token))
    turn_encryption_on()
    original = DataReencodeService._batch_of
    done = []

    async def changing(self, db, col, *, encrypted, after):
        rows = await original(self, db, col, encrypted=encrypted, after=after)
        if rows and not encrypted and col.column == "first_name" and not done:
            done.append(1)
            async with TestingSessionLocal() as other:
                await other.execute(text("UPDATE clients SET first_name = 'Nowe'"))
                await other.commit()
        return rows

    monkeypatch.setattr(DataReencodeService, "_batch_of", changing)
    code, text_out = await run_cli(monkeypatch, "apply")
    assert code == 5 and "TOTAL plain=1" in text_out
    monkeypatch.undo()
    code, _ = await run_cli(monkeypatch, "apply")
    assert code == 0


async def test_the_command_does_not_say_done_when_plain_values_are_still_there_after_a_full_run(async_client, db_session, encryption_on, monkeypatch):
    token = await get_token(async_client, VALID_USER)
    await async_client.post("/api/clients", json=CLIENT, headers=auth_header(token))
    original = DataReencodeService.count

    async def one_more_plain(self, verify=False):
        stats = await original(self, verify=verify)
        stats[0].non_null += 1  # a plain value appeared behind the command's back
        return stats

    monkeypatch.setattr(DataReencodeService, "count", one_more_plain)
    code, text_out = await run_cli(monkeypatch, "apply")
    assert code == 3 and "TOTAL plain=1" in text_out
