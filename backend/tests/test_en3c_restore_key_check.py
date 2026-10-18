"""EN-3c -- the rehearsal of a restore with the key: a restored backup is read with the saved key, and with nothing else."""
import io
import uuid

import pytest
from pydantic import SecretStr
from sqlalchemy import text

from app.cli import restore_key_check
from app.core import data_crypto as dc
from app.core.config import settings
from app.core.key_ring import ring, set_owner_key
from app.domain.services.data_key_service import DataKeyService
from app.domain.services.restore_key_check_service import (
    RestoreKeyCheckService,
    UnsafeRestoreCheckTargetError,
    fingerprint,
    validate_scratch_url,
)
from app.models.client import Client
from app.models.data_key import DataKey
from app.models.project import Project
from app.models.user import User
from tests.conftest import TestingSessionLocal

SCRATCH = "postgresql+asyncpg://u:p@127.0.0.1:5432/pe_restore_scratch_drill"


def b64(raw: bytes) -> SecretStr:
    import base64

    return SecretStr(base64.b64encode(raw).decode())


@pytest.fixture
def keys():
    old, new = dc.new_key(), dc.new_key()
    settings.DATA_KEK, settings.DATA_KEK_VERSION, settings.DATA_KEK_PREVIOUS = b64(old), 1, SecretStr("")
    ring.disable()
    set_owner_key(None)
    yield old, new
    settings.DATA_KEK, settings.DATA_KEK_VERSION, settings.DATA_KEK_PREVIOUS = SecretStr(""), 1, SecretStr("")
    ring.disable()
    set_owner_key(None)


def use_keys(current: bytes, previous: bytes | None = None) -> None:
    settings.DATA_KEK, settings.DATA_KEK_PREVIOUS = b64(current), (b64(previous) if previous else SecretStr(""))
    ring.disable()
    set_owner_key(None)


@pytest.fixture(autouse=True)
async def _no_leftover_alembic_table():
    """The restored backup brings its own `alembic_version`; a table made by DDL is not rolled back by the test, so it is dropped here."""
    yield
    async with TestingSessionLocal() as db:
        await db.execute(text("DROP TABLE IF EXISTS alembic_version"))
        await db.commit()


async def a_backup(db) -> uuid.UUID:
    """What a restored backup holds: an owner with a data key, a client and an object, sealed; plus the alembic table the restore brings."""
    await db.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)"))
    await db.execute(text("DELETE FROM alembic_version"))
    await db.execute(text("INSERT INTO alembic_version VALUES ('0064_encrypted_payments')"))
    user = User(telegram_user_id=860001, first_name="Owner")
    db.add(user)
    await db.flush()
    await DataKeyService(db).prepare()
    set_owner_key(await DataKeyService(db).owner_key(user.id))
    db.add(Client(owner_user_id=user.id, client_type="PRIVATE_PERSON", first_name="Anna", last_name="Nowak", phone="500600700"))
    db.add(Project(owner_id=user.id, name="Dom Nowaków", address="ul. Lipowa 1", city="Kraków", postal_code="30-001"))
    await db.commit()
    return user.id


def check(**kw):
    return RestoreKeyCheckService(TestingSessionLocal).run(**kw)


# --- the guard --------------------------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("url", [SCRATCH, "postgresql+asyncpg://u:p@pe-scratch-pg:5432/pe_restore_scratch_x", "postgresql+asyncpg://u:p@localhost/pe_restore_scratch"])
def test_a_scratch_database_is_accepted(url):
    validate_scratch_url(url)


@pytest.mark.parametrize("url", [
    "postgresql+asyncpg://u:p@127.0.0.1:5432/plan_estimate",  # the name of the real database
    "postgresql+asyncpg://u:p@db.prod.example/pe_restore_scratch_x",  # a scratch name on a real host
    "postgresql+asyncpg://u:p@127.0.0.1:5432/",
])
def test_anything_else_is_refused_with_no_value_in_the_message(url):
    with pytest.raises(UnsafeRestoreCheckTargetError) as caught:
        validate_scratch_url(url)
    assert "prod.example" not in str(caught.value) and "plan_estimate" not in str(caught.value)


def test_the_fingerprint_is_the_one_the_deployment_scripts_print():
    import hashlib

    assert fingerprint("abc\n") == hashlib.sha256(b"abc").hexdigest()[:8]


# --- the check --------------------------------------------------------------------------------------------------------------------------------


async def test_a_backup_is_read_with_the_saved_key(db_session, keys):
    await a_backup(db_session)
    report = await check()
    assert report.passed and report.keys.total == 1 and report.keys.current == 1 and report.undecryptable == 0 and report.plain == 0 and report.ciphertext > 0
    assert report.wrong_key_opens is False and report.revision == "0064_encrypted_payments"


async def test_a_wrong_key_opens_nothing_and_the_check_fails(db_session, keys):
    old, new = keys
    await a_backup(db_session)
    use_keys(new)
    report = await check()
    assert not report.passed and "DATA_KEYS_DO_NOT_OPEN_WITH_THIS_KEY" in report.reasons and report.keys.unreadable == 1
    assert report.ciphertext == 0  # the values were not even counted: they cannot be opened


async def test_a_backup_made_before_a_rotation_needs_the_old_key_as_the_previous_one(db_session, keys):
    old, new = keys
    await a_backup(db_session)  # its data key is wrapped by the OLD key of the server
    use_keys(new)
    assert not (await check()).passed  # the new key alone: the lesson of the runbook, the old key must be kept
    use_keys(new, old)
    report = await check()
    assert report.passed and report.keys.previous_only == 1 and report.undecryptable == 0


async def test_a_backup_made_after_a_rotation_opens_with_the_new_key_alone(db_session, keys):
    old, new = keys
    await a_backup(db_session)
    use_keys(new, old)
    from app.domain.services.kek_rotation_service import KekRotationService

    settings.DATA_KEK_VERSION = 2
    assert (await KekRotationService(TestingSessionLocal).rewrap()).done
    use_keys(new)
    assert (await check()).passed
    use_keys(old)
    assert not (await check()).passed  # and the old key no longer opens it


async def test_a_value_that_does_not_decrypt_fails_the_check(db_session, keys):
    await a_backup(db_session)
    key_id = (await db_session.execute(text("SELECT key_id FROM data_keys"))).scalar_one()
    await db_session.execute(text("UPDATE clients SET last_name = :v"), {"v": f"enc1:{key_id}:AAAA:BBBB"})
    await db_session.commit()
    report = await check()
    assert not report.passed and report.undecryptable == 1 and "VALUES_DO_NOT_DECRYPT" in report.reasons


async def test_a_plain_value_fails_unless_the_older_backup_is_allowed(db_session, keys):
    await a_backup(db_session)
    await db_session.execute(text("UPDATE clients SET notes = 'jawna notatka'"))
    await db_session.commit()
    strict = await check()
    assert not strict.passed and strict.plain == 1 and "PLAIN_VALUES_REMAIN" in strict.reasons
    lenient = await check(allow_plain=True)
    assert lenient.passed and lenient.plain == 1


async def test_a_backup_with_keys_but_no_encrypted_value_fails_it_proves_nothing(db_session, keys):
    user = User(telegram_user_id=860002, first_name="Empty")
    db_session.add(user)
    await db_session.flush()
    await DataKeyService(db_session).prepare()
    await DataKeyService(db_session).owner_key(user.id)
    await db_session.commit()
    report = await check()
    assert not report.passed and report.keys.total == 1 and "NO_ENCRYPTED_VALUES" in report.reasons


async def test_a_database_with_no_data_keys_fails(db_session, keys):
    report = await check()
    assert not report.passed and "NO_DATA_KEYS" in report.reasons and "NO_ALEMBIC_VERSION" in report.reasons


async def test_a_random_key_that_opened_a_data_key_would_be_reported(db_session, keys, monkeypatch):
    await a_backup(db_session)
    monkeypatch.setattr(dc, "unwrap_key", lambda *a, **k: dc.new_key())  # simulates a broken wrapping that opens with anything
    report = await check()
    assert "A_RANDOM_KEY_OPENED_A_DATA_KEY" in report.reasons and not report.passed


async def test_the_check_changes_nothing(db_session, keys):
    await a_backup(db_session)
    before = (await db_session.execute(text("SELECT first_name, wrapped_dek, kek_version FROM clients, data_keys"))).all()
    await check()
    await check(allow_plain=True)
    db_session.expire_all()
    assert (await db_session.execute(text("SELECT first_name, wrapped_dek, kek_version FROM clients, data_keys"))).all() == before


# --- the command line -------------------------------------------------------------------------------------------------------------------------


async def cli(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    return await restore_key_check.run(list(argv), out), out.getvalue()


async def test_the_command_refuses_a_database_that_is_not_scratch(db_session, keys, monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql+asyncpg://u:p@127.0.0.1:5432/plan_estimate")
    code, report = await cli()
    assert code == 2 and "refused, nothing was opened" in report and "plan_estimate" not in report


async def test_the_command_prints_pass_with_fingerprints_and_no_key(db_session, keys, monkeypatch):
    old, new = keys
    monkeypatch.setattr(settings, "DATABASE_URL", SCRATCH)
    monkeypatch.setattr(restore_key_check, "async_session_maker", TestingSessionLocal)
    await a_backup(db_session)
    code, report = await cli()
    assert code == 0 and "RESTORE KEY CHECK: PASS" in report and f"fingerprint {fingerprint(settings.DATA_KEK.get_secret_value())}" in report
    assert settings.DATA_KEK.get_secret_value() not in report and old.hex() not in report and "Anna" not in report
    use_keys(new)
    code, report = await cli()
    assert code == 3 and "RESTORE KEY CHECK: FAIL (DATA_KEYS_DO_NOT_OPEN_WITH_THIS_KEY)" in report


async def test_the_command_reports_a_missing_key(db_session, keys, monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_URL", SCRATCH)
    monkeypatch.setattr(restore_key_check, "async_session_maker", TestingSessionLocal)
    settings.DATA_KEK = SecretStr("")
    assert (await cli())[0] == 4


async def test_the_command_says_when_a_backup_needs_the_previous_key(db_session, keys, monkeypatch):
    old, new = keys
    monkeypatch.setattr(settings, "DATABASE_URL", SCRATCH)
    monkeypatch.setattr(restore_key_check, "async_session_maker", TestingSessionLocal)
    await a_backup(db_session)
    use_keys(new, old)
    code, report = await cli()
    assert code == 0 and "only with DATA_KEK_PREVIOUS: 1" in report and "keep the old key" in report
