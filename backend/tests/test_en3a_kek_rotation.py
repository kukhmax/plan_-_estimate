"""EN-3a -- the rotation of the key of the server: the data keys are re-wrapped, the data is not touched."""
import io
import uuid

import pytest
from pydantic import SecretStr
from sqlalchemy import select, text

from app.cli import rotate_keys
from app.core import data_crypto as dc
from app.core.config import settings
from app.core.key_ring import ring, set_owner_key
from app.domain.services.data_key_service import DataKeyService, unwrap_data_key
from app.domain.services.kek_rotation_service import KekRotationService
from app.models.client import Client
from app.models.data_key import DataKey, WrappedBy
from app.models.user import User
from tests.conftest import TestingSessionLocal


def text_of(raw: bytes) -> SecretStr:
    import base64

    return SecretStr(base64.b64encode(raw).decode())


@pytest.fixture
def keys():
    """An old and a new key of the server; the world starts with the OLD one (the version 1) and nothing else configured."""
    old, new = dc.new_key(), dc.new_key()
    settings.DATA_KEK, settings.DATA_KEK_VERSION, settings.DATA_KEK_PREVIOUS = text_of(old), 1, SecretStr("")
    ring.disable()
    set_owner_key(None)
    yield old, new
    settings.DATA_KEK, settings.DATA_KEK_VERSION, settings.DATA_KEK_PREVIOUS = SecretStr(""), 1, SecretStr("")
    ring.disable()
    set_owner_key(None)


def rotate_to(new: bytes, old: bytes | None, version: int = 2) -> None:
    """The configuration of the middle of a rotation: the new key, its version, the old key as the previous one."""
    settings.DATA_KEK, settings.DATA_KEK_VERSION = text_of(new), version
    settings.DATA_KEK_PREVIOUS = text_of(old) if old is not None else SecretStr("")
    ring.disable()
    set_owner_key(None)


async def an_owner(db, number: int) -> uuid.UUID:
    user = User(telegram_user_id=880000 + number, first_name=f"U{number}")
    db.add(user)
    await db.flush()
    return user.id


# --- reading while the keys are wrapped by either key ----------------------------------------------------------------------------------------


def test_a_data_key_opens_with_the_current_key_then_with_the_previous_one(keys):
    old, new = keys
    dek = dc.new_key()
    row = DataKey(owner_id=uuid.uuid4(), key_id="k1", wrapped_dek=dc.wrap_key(old, dek, "k1"), kek_version=1)
    rotate_to(new, old)
    assert unwrap_data_key(row, new, old) == dek  # version 1 row, current version 2: the previous key is tried first
    assert unwrap_data_key(row, old, None) == dek
    with pytest.raises(dc.DataDecryptError):
        unwrap_data_key(row, new, None)  # no previous key configured: the row is not readable
    with pytest.raises(dc.DataDecryptError):
        unwrap_data_key(row, new, dc.new_key())  # neither key opens it


def test_the_stamp_of_the_version_is_only_a_hint_the_wrapping_decides(keys):
    old, new = keys
    dek = dc.new_key()
    rotate_to(new, old)
    stamped_old_wrapped_new = DataKey(owner_id=uuid.uuid4(), key_id="a", wrapped_dek=dc.wrap_key(new, dek, "a"), kek_version=1)
    stamped_new_wrapped_old = DataKey(owner_id=uuid.uuid4(), key_id="b", wrapped_dek=dc.wrap_key(old, dek, "b"), kek_version=2)
    assert unwrap_data_key(stamped_old_wrapped_new, new, old) == dek and unwrap_data_key(stamped_new_wrapped_old, new, old) == dek


async def test_the_application_reads_what_was_written_before_the_rotation(db_session, keys):
    old, new = keys
    owner = await an_owner(db_session, 1)
    service = DataKeyService(db_session)
    await service.prepare()
    key = await service.owner_key(owner)
    await db_session.commit()
    set_owner_key(key)
    db_session.add(Client(owner_user_id=owner, client_type="PRIVATE_PERSON", first_name="Anna", last_name="Nowak", phone="500600700"))
    await db_session.commit()
    stored = (await db_session.execute(text("SELECT first_name FROM clients"))).scalar_one()
    assert stored.startswith("enc1:")

    rotate_to(new, old)  # the middle of the rotation: the keys are still wrapped by the old key
    db_session.expire_all()
    assert await DataKeyService(db_session).prepare()
    assert (await db_session.execute(select(Client.first_name))).scalar_one() == "Anna"

    rotate_to(new, None)  # the previous key is gone before the re-wrapping: the keys cannot be opened
    ring.disable()
    with pytest.raises(dc.DataDecryptError):
        await DataKeyService(db_session).prepare()


async def test_a_key_made_during_the_rotation_is_wrapped_by_the_new_key(db_session, keys):
    old, new = keys
    rotate_to(new, old)
    owner = await an_owner(db_session, 2)
    await DataKeyService(db_session).owner_key(owner)
    row = (await db_session.execute(select(DataKey).where(DataKey.owner_id == owner))).scalar_one()
    assert row.kek_version == 2
    dc.unwrap_key(new, row.wrapped_dek, row.key_id)  # opens with the new key alone


async def test_an_invalid_previous_key_is_an_error_not_a_silent_ignore(db_session, keys):
    old, new = keys
    rotate_to(new, old)
    settings.DATA_KEK_PREVIOUS = SecretStr("not-a-key")
    with pytest.raises(dc.DataKeyConfigurationError):
        await DataKeyService(db_session).prepare()


# --- the command ------------------------------------------------------------------------------------------------------------------------------


async def two_owners_under_the_old_key(db_session, old: bytes) -> tuple[bytes, bytes]:
    """Two owners whose data keys were wrapped by the old key; returns their data keys."""
    deks = []
    for number in (10, 11):
        owner = await an_owner(db_session, number)
        dek = dc.new_key()
        db_session.add(DataKey(owner_id=owner, key_id=f"key{number}", wrapped_dek=dc.wrap_key(old, dek, f"key{number}"), kek_version=1, active=True))
        deks.append(dek)
    await db_session.commit()
    return deks[0], deks[1]


async def test_status_counts_the_keys_by_which_key_opens_them(db_session, keys):
    old, new = keys
    await two_owners_under_the_old_key(db_session, old)
    rotate_to(new, old)
    status = await KekRotationService(TestingSessionLocal).status()
    assert (status.total, status.current, status.previous_only, status.unreadable) == (2, 0, 2, 0) and status.versions == {1: 2} and not status.done


async def test_rewrap_changes_the_wrapping_and_never_the_data_key(db_session, keys):
    old, new = keys
    deks = await two_owners_under_the_old_key(db_session, old)
    rotate_to(new, old)
    status = await KekRotationService(TestingSessionLocal).rewrap()
    assert status.rewrapped == 2 and status.done and status.versions == {2: 2}
    db_session.expire_all()
    rows = (await db_session.execute(select(DataKey).order_by(DataKey.key_id))).scalars().all()
    assert [dc.unwrap_key(new, row.wrapped_dek, row.key_id) for row in rows] == list(deks)  # the same data keys, wrapped anew
    assert all(row.kek_version == 2 for row in rows)
    for row in rows:
        with pytest.raises(dc.DataDecryptError):
            dc.unwrap_key(old, row.wrapped_dek, row.key_id)  # the old key no longer opens them


async def test_the_data_stays_readable_after_the_previous_key_is_removed(db_session, keys):
    old, new = keys
    owner = await an_owner(db_session, 3)
    service = DataKeyService(db_session)
    await service.prepare()
    set_owner_key(await service.owner_key(owner))
    db_session.add(Client(owner_user_id=owner, client_type="PRIVATE_PERSON", first_name="Jan", last_name="Kowalski", phone="111222333"))
    await db_session.commit()
    before = (await db_session.execute(text("SELECT first_name, phone FROM clients"))).one()

    rotate_to(new, old)
    assert (await KekRotationService(TestingSessionLocal).rewrap()).done
    rotate_to(new, None)  # the previous key removed
    db_session.expire_all()
    await DataKeyService(db_session).prepare()
    assert (await db_session.execute(select(Client.first_name, Client.phone))).one() == ("Jan", "111222333")
    assert (await db_session.execute(text("SELECT first_name, phone FROM clients"))).one() == tuple(before)  # the stored text did not change at all


async def test_a_second_rewrap_changes_nothing(db_session, keys):
    old, new = keys
    await two_owners_under_the_old_key(db_session, old)
    rotate_to(new, old)
    await KekRotationService(TestingSessionLocal).rewrap()
    first = (await db_session.execute(select(DataKey.wrapped_dek).order_by(DataKey.key_id))).scalars().all()
    again = await KekRotationService(TestingSessionLocal).rewrap()
    db_session.expire_all()
    assert again.rewrapped == 0 and again.done
    assert (await db_session.execute(select(DataKey.wrapped_dek).order_by(DataKey.key_id))).scalars().all() == first


async def test_one_unreadable_key_stops_everything_and_changes_nothing(db_session, keys):
    old, new = keys
    await two_owners_under_the_old_key(db_session, old)
    stranger = await an_owner(db_session, 12)
    db_session.add(DataKey(owner_id=stranger, key_id="lost", wrapped_dek=dc.wrap_key(dc.new_key(), dc.new_key(), "lost"), kek_version=1, active=True))
    await db_session.commit()
    before = (await db_session.execute(select(DataKey.key_id, DataKey.wrapped_dek, DataKey.kek_version).order_by(DataKey.key_id))).all()
    rotate_to(new, old)
    status = await KekRotationService(TestingSessionLocal).rewrap()
    assert status.unreadable == 1 and status.rewrapped == 0 and not status.done
    db_session.expire_all()
    assert (await db_session.execute(select(DataKey.key_id, DataKey.wrapped_dek, DataKey.kek_version).order_by(DataKey.key_id))).all() == before


async def test_the_keys_of_the_owners_themselves_are_left_alone(db_session, keys):
    old, new = keys
    owner = await an_owner(db_session, 13)
    db_session.add(DataKey(owner_id=owner, key_id="v2", wrapped_dek="wrapped-by-the-owner", wrapped_by=WrappedBy.OWNER_KEY.value, kek_version=1, active=True))
    await db_session.commit()
    rotate_to(new, old)
    status = await KekRotationService(TestingSessionLocal).rewrap()
    assert status.total == 0 and status.owner_wrapped == 1 and status.done
    db_session.expire_all()
    assert (await db_session.execute(select(DataKey.wrapped_dek))).scalar_one() == "wrapped-by-the-owner"


async def test_rewrap_without_the_previous_key_is_refused_while_a_key_needs_it(db_session, keys):
    old, new = keys
    await two_owners_under_the_old_key(db_session, old)
    rotate_to(new, None)
    status = await KekRotationService(TestingSessionLocal).status()
    assert status.unreadable == 2  # with no previous key they are simply unreadable: the order of the runbook prevents this
    rotate_to(new, new)
    with pytest.raises(dc.DataKeyConfigurationError, match="same key"):
        await KekRotationService(TestingSessionLocal).status()


async def test_nothing_runs_without_the_key_of_the_server(keys):
    settings.DATA_KEK = SecretStr("")
    with pytest.raises(dc.DataKeyConfigurationError):
        await KekRotationService(TestingSessionLocal).status()


# --- the command line ------------------------------------------------------------------------------------------------------------------------


async def cli(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    code = await rotate_keys.run(list(argv), out)
    return code, out.getvalue()


async def test_new_key_prints_a_usable_key_of_the_server():
    code, printed = await cli("new-key")
    assert code == 0 and len(dc.parse_kek(printed.strip())) == 32


async def test_the_command_walks_the_whole_rotation(db_session, keys, monkeypatch):
    old, new = keys
    monkeypatch.setattr(rotate_keys, "async_session_maker", TestingSessionLocal)
    await two_owners_under_the_old_key(db_session, old)
    rotate_to(new, old)
    code, report = await cli("status")
    assert code == 0 and "open only with DATA_KEK_PREVIOUS (still to be re-wrapped): 2" in report and "ROTATION NOT DONE" in report
    assert (await cli("verify"))[0] == 3  # not done: the previous key must stay
    code, report = await cli("rewrap")
    assert code == 0 and "re-wrapped in this run: 2" in report and "ROTATION DONE" in report
    rotate_to(new, None)
    code, report = await cli("verify")
    assert code == 0 and "open with DATA_KEK (version 2) alone: 2" in report and old.hex() not in report and new.hex() not in report


async def test_the_command_reports_a_missing_key_and_an_unreadable_one(db_session, keys, monkeypatch):
    old, new = keys
    monkeypatch.setattr(rotate_keys, "async_session_maker", TestingSessionLocal)
    settings.DATA_KEK = SecretStr("")
    assert (await cli("status"))[0] == 4
    rotate_to(new, old)
    stranger = await an_owner(db_session, 14)
    db_session.add(DataKey(owner_id=stranger, key_id="lost", wrapped_dek=dc.wrap_key(dc.new_key(), dc.new_key(), "lost"), kek_version=1, active=True))
    await db_session.commit()
    code, report = await cli("status")
    assert code == 3 and "unreadable): 1" in report
