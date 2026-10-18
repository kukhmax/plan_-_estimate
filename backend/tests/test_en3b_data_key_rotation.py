"""EN-3b -- the change of the data key of an owner: a new key, every value sealed anew, the old key retired only when nothing is sealed with it."""
import io
import uuid

import pytest
from sqlalchemy import select, text

from app.cli import rotate_data_keys
from app.core import data_crypto as dc
from app.core.key_ring import ring, set_owner_key
from app.domain.services.data_key_service import DataKeyService
from app.domain.services.data_reencode_service import DataReencodeService
from app.domain.services.dek_rotation_service import DataKeyRotationRefusedError, DekRotationService
from app.models.client import Client
from app.models.data_key import DataKey
from app.models.project import Project
from app.models.user import User
from tests.conftest import TestingSessionLocal


async def an_owner(db, number: int, first_name: str) -> tuple[uuid.UUID, str]:
    """An owner with a data key, one client and one object, all sealed; returns the owner and the id of the first key."""
    user = User(telegram_user_id=870000 + number, first_name=f"U{number}")
    db.add(user)
    await db.flush()
    await DataKeyService(db).prepare()  # switches the ring on
    key = await DataKeyService(db).owner_key(user.id)
    set_owner_key(key)
    db.add(Client(owner_user_id=user.id, client_type="PRIVATE_PERSON", first_name=first_name, last_name="Nowak", phone=f"50060070{number}"))
    db.add(Project(owner_id=user.id, name=f"Dom {first_name}", address="ul. Lipowa 1", city="Kraków", postal_code="30-001"))
    await db.commit()
    return user.id, key.key_id


def service() -> DekRotationService:
    return DekRotationService(TestingSessionLocal, batch_size=2)


async def sealed_with(db, table: str, column: str, key_id: str) -> int:
    return int((await db.execute(text(f"SELECT count(*) FROM {table} WHERE {column} LIKE :p"), {"p": f"enc1:{key_id}:%"})).scalar_one())


async def test_status_shows_which_key_seals_how_many_values(db_session, encryption_on):
    owner, key_id = await an_owner(db_session, 1, "Anna")
    [entry] = await service().status()
    assert entry.owner_id == owner and entry.active and entry.active.key_id == key_id and entry.active.values > 0 and entry.done


async def test_start_makes_a_new_active_key_and_keeps_the_old_one_inactive(db_session, encryption_on):
    owner, old_id = await an_owner(db_session, 2, "Jan")
    new_id = await service().start(owner)
    assert new_id != old_id
    db_session.expire_all()
    rows = {row.key_id: row for row in (await db_session.execute(select(DataKey).where(DataKey.owner_id == owner))).scalars()}
    assert rows[new_id].active and not rows[old_id].active
    [entry] = await service().status()
    assert entry.active.key_id == new_id and entry.to_reseal > 0 and not entry.done  # the old values still wait for the new key


async def test_after_start_this_process_writes_with_the_new_key_not_the_cached_old_one(db_session, encryption_on):
    owner, old_id = await an_owner(db_session, 20, "Pamiec")
    new_id = await service().start(owner)
    assert (await DataKeyService(db_session).owner_key(owner)).key_id == new_id  # the cached old key was dropped


async def test_the_new_key_is_wrapped_like_every_new_key_and_opens_with_the_key_of_the_server(db_session, encryption_on):
    from app.core.config import settings
    from app.domain.services.data_key_service import server_kek

    owner, _ = await an_owner(db_session, 21, "Okno")
    new_id = await service().start(owner)
    db_session.expire_all()
    row = (await db_session.execute(select(DataKey).where(DataKey.key_id == new_id))).scalar_one()
    assert row.kek_version == settings.DATA_KEK_VERSION and row.wrapped_by == "SERVER_KEK" and row.active
    assert len(dc.unwrap_key(server_kek(), row.wrapped_dek, row.key_id)) == 32


async def test_reseal_moves_every_value_to_the_new_key_and_the_text_reads_the_same(db_session, encryption_on):
    owner, old_id = await an_owner(db_session, 3, "Ewa")
    new_id = await service().start(owner)
    stats = await service().reseal()
    assert stats.resealed > 0 and stats.skipped_changed == 0 and stats.undecryptable == 0
    assert await sealed_with(db_session, "clients", "first_name", old_id) == 0 and await sealed_with(db_session, "clients", "first_name", new_id) == 1
    assert await sealed_with(db_session, "projects", "name", old_id) == 0
    [entry] = await service().status()
    assert entry.done
    db_session.expire_all()
    set_owner_key(await DataKeyService(db_session).owner_key(owner))
    assert (await db_session.execute(select(Client.first_name, Client.phone))).one() == ("Ewa", "500600703")
    assert (await db_session.execute(select(Project.name))).scalar_one() == "Dom Ewa"


async def test_reseal_does_not_move_updated_at(db_session, encryption_on):
    owner, _ = await an_owner(db_session, 4, "Ola")
    before = (await db_session.execute(text("SELECT updated_at FROM clients"))).scalar_one()
    await service().start(owner)
    await service().reseal()
    assert (await db_session.execute(text("SELECT updated_at FROM clients"))).scalar_one() == before


async def test_reseal_is_repeatable_and_can_be_stopped(db_session, encryption_on):
    owner, old_id = await an_owner(db_session, 5, "Iga")
    await service().start(owner)
    first = await service().reseal(limit=2)
    assert first.resealed == 2
    [entry] = await service().status()
    assert not entry.done
    rest = await service().reseal()
    assert rest.resealed > 0
    assert (await service().reseal()).resealed == 0 and (await service().status())[0].done


async def test_only_the_values_of_this_owner_are_touched(db_session, encryption_on):
    one, one_old = await an_owner(db_session, 6, "Pierwszy")
    two, two_old = await an_owner(db_session, 7, "Drugi")
    before = (await db_session.execute(text("SELECT first_name FROM clients WHERE first_name LIKE :p"), {"p": f"enc1:{two_old}:%"})).scalar_one()
    await service().start(one)
    await service().reseal(owner_id=one)
    assert await sealed_with(db_session, "clients", "first_name", one_old) == 0
    assert (await db_session.execute(text("SELECT first_name FROM clients WHERE first_name LIKE :p"), {"p": f"enc1:{two_old}:%"})).scalar_one() == before
    keys = {entry.owner_id: entry for entry in await service().status()}
    assert keys[two].active.key_id == two_old and keys[two].done


async def test_a_value_that_does_not_open_is_counted_and_left_alone(db_session, encryption_on):
    owner, old_id = await an_owner(db_session, 8, "Zła")
    await service().start(owner)
    await db_session.execute(text("UPDATE clients SET last_name = :v"), {"v": f"enc1:{old_id}:AAAA:BBBB"})  # damaged
    await db_session.commit()
    stats = await service().reseal()
    assert stats.undecryptable == 1
    assert (await db_session.execute(text("SELECT last_name FROM clients"))).scalar_one() == f"enc1:{old_id}:AAAA:BBBB"
    assert not (await service().status())[0].done


async def test_a_plain_value_is_not_this_commands_business(db_session, encryption_on):
    owner, _ = await an_owner(db_session, 9, "Jawna")
    await db_session.execute(text("UPDATE clients SET notes = 'jawna notatka'"))
    await db_session.commit()
    await service().start(owner)
    await service().reseal()
    assert (await db_session.execute(text("SELECT notes FROM clients"))).scalar_one() == "jawna notatka"


async def test_retire_refuses_while_the_old_key_still_seals_a_value_and_then_deletes_it(db_session, encryption_on):
    owner, old_id = await an_owner(db_session, 10, "Kasia")
    new_id = await service().start(owner)
    with pytest.raises(DataKeyRotationRefusedError):
        await service().retire()
    db_session.expire_all()
    assert {row.key_id for row in (await db_session.execute(select(DataKey))).scalars()} == {old_id, new_id}  # nothing was deleted
    await service().reseal()
    assert await service().retire() == 1
    db_session.expire_all()
    assert {row.key_id for row in (await db_session.execute(select(DataKey))).scalars()} == {new_id}
    # the data is still read, with the new key alone
    ring.disable()
    set_owner_key(None)
    await DataKeyService(db_session).prepare()
    assert (await db_session.execute(select(Client.first_name))).scalar_one() == "Kasia"


async def test_a_second_start_is_refused_while_the_first_change_is_unfinished(db_session, encryption_on):
    owner, _ = await an_owner(db_session, 11, "Marta")
    await service().start(owner)
    with pytest.raises(DataKeyRotationRefusedError, match="not finished"):
        await service().start(owner)
    await service().reseal()
    await service().start(owner)  # finished: a further change is allowed


async def test_start_for_an_owner_without_a_key_is_refused(db_session, encryption_on):
    with pytest.raises(DataKeyRotationRefusedError):
        await service().start(uuid.uuid4())


async def test_a_value_written_with_the_old_key_after_the_start_is_found_by_the_next_reseal(db_session, encryption_on):
    owner, old_id = await an_owner(db_session, 12, "Stary")
    await service().start(owner)
    old_key = OwnerKey_of(old_id)
    set_owner_key(old_key)  # a backend that has not been recreated yet still writes with the key it holds
    db_session.add(Client(owner_user_id=owner, client_type="PRIVATE_PERSON", first_name="Pozno", last_name="Dodany", phone="1"))
    await db_session.commit()
    assert await sealed_with(db_session, "clients", "first_name", old_id) == 2
    await service().reseal()
    assert await sealed_with(db_session, "clients", "first_name", old_id) == 0 and (await service().status())[0].done


def OwnerKey_of(key_id: str):
    from app.core.key_ring import OwnerKey

    return OwnerKey(key_id, ring.get(key_id))


async def test_the_reencode_command_still_sees_every_value_after_the_change(db_session, encryption_on):
    owner, _ = await an_owner(db_session, 13, "Raport")
    await service().start(owner)
    await service().reseal()
    report = await DataReencodeService(TestingSessionLocal).count(verify=True)
    assert sum(s.plain for s in report) == 0 and sum(s.undecryptable for s in report) == 0 and sum(s.encrypted for s in report) > 0


# --- the command line ------------------------------------------------------------------------------------------------------------------------


async def cli(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    return await rotate_data_keys.run(list(argv), out), out.getvalue()


async def test_the_command_walks_the_whole_change(db_session, encryption_on, monkeypatch):
    monkeypatch.setattr(rotate_data_keys, "async_session_maker", TestingSessionLocal)
    owner, old_id = await an_owner(db_session, 14, "Cli")
    code, report = await cli("status")
    assert code == 0 and "STILL SEALED WITH AN OLD KEY: 0" in report
    code, report = await cli("start", "--all")
    assert code == 0 and "new active data key" in report and "recreate the backend" in report
    code, report = await cli("status")
    assert code == 3 and "inactive" in report and "ACTIVE" in report
    assert (await cli("retire"))[0] == 6  # refused: still sealing
    code, report = await cli("reseal")
    assert code == 0 and "STILL SEALED WITH AN OLD KEY: 0" in report
    code, report = await cli("retire")
    assert code == 0 and "deleted 1 inactive data key" in report
    assert old_id not in report and "enc1:" not in report


async def test_the_command_reports_a_missing_server_key(monkeypatch):
    from pydantic import SecretStr

    from app.core.config import settings

    monkeypatch.setattr(rotate_data_keys, "async_session_maker", TestingSessionLocal)
    monkeypatch.setattr(settings, "DATA_KEK", SecretStr(""))
    assert (await cli("status"))[0] == 4
    assert (await cli("reseal", "--batch-size", "0"))[0] == 2


def test_the_ring_forgets_a_cached_owner_key_but_keeps_the_key_to_read_old_values():
    from app.core.key_ring import KeyRing, OwnerKey

    local = KeyRing()
    owner = uuid.uuid4()
    local.set_owner(owner, OwnerKey("k1", dc.new_key()))
    local.forget_owner(owner)
    assert local.owner(owner) is None and local.get("k1") is not None
