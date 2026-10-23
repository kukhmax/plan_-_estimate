"""V2-1 -- sign in with an e-mail and a password (docs/V2_1_PLAN_RU.md)."""
import io
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.cli import users as users_cli
from app.core.config import settings
from app.domain.exceptions import WebAccountError
from app.domain.services.access_service import AccessService
from app.domain.services.password_login_service import (
    MAX_FAILURES,
    PasswordLoginService,
    hash_password,
    verify_password,
)
from app.models.access_entry import AccessEntry, AccessStatus
from app.models.user import User
from app.models.user_credential import UserCredential
from tests.test_clients import auth_header

PASSWORD = "correct horse battery"


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_PASSWORD_ENABLED", True)


async def _account(db, email="Jan@Example.PL", password=PASSWORD, name="Jan"):
    user, _ = await PasswordLoginService(db).create_account(email, name, password)
    return user


async def _login(client: AsyncClient, email="jan@example.pl", password=PASSWORD):
    return await client.post("/api/auth/password", json={"email": email, "password": password})


# --- the hash ----------------------------------------------------------------------------------------------------------------------------


def test_a_hash_checks_the_password_that_made_it_and_nothing_else():
    stored = hash_password(PASSWORD, n=2**10)
    assert stored.startswith("scrypt$1024$8$1$") and PASSWORD not in stored
    assert verify_password(PASSWORD, stored) and not verify_password(PASSWORD + "x", stored)
    assert hash_password(PASSWORD, n=2**10) != stored  # a salt each time


@pytest.mark.parametrize("stored", ["", "garbage", "scrypt$x$8$1$a$b", "bcrypt$1$2$3$4$5", "scrypt$1024$8$1$!!$!!"])
def test_a_broken_hash_is_a_refusal_not_an_error(stored):
    assert verify_password(PASSWORD, stored) is False


# --- the sign-in -------------------------------------------------------------------------------------------------------------------------


async def test_it_is_switched_off_by_default(async_client: AsyncClient, db_session):
    await _account(db_session)
    config = (await async_client.get("/api/auth/config")).json()
    assert config == {"password_login": False}
    response = await _login(async_client)
    assert response.status_code == 403 and response.json()["detail"]["code"] == "PASSWORD_LOGIN_DISABLED"


async def test_the_screen_is_told_when_it_is_on(async_client: AsyncClient, enabled):
    assert (await async_client.get("/api/auth/config")).json() == {"password_login": True}


async def test_a_right_password_gives_a_token_that_works_everywhere(async_client: AsyncClient, db_session, enabled):
    user = await _account(db_session)
    response = await _login(async_client, email="  JAN@example.pl ")  # the e-mail is not case sensitive
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "bearer" and body["user"]["id"] == str(user.id) and body["user"]["telegram_user_id"] < 0
    me = await async_client.get("/api/me", headers=auth_header(body["access_token"]))
    assert me.status_code == 200 and me.json()["id"] == str(user.id)
    clients = await async_client.get("/api/clients", headers=auth_header(body["access_token"]))
    assert clients.status_code == 200


async def test_a_wrong_password_and_an_unknown_e_mail_get_the_same_answer(async_client: AsyncClient, db_session, enabled):
    await _account(db_session)
    wrong = await _login(async_client, password="not the password")
    unknown = await _login(async_client, email="nobody@example.pl")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() and wrong.json()["detail"]["code"] == "INVALID_CREDENTIALS"


async def test_five_wrong_passwords_lock_the_account_for_a_while(async_client: AsyncClient, db_session, enabled):
    await _account(db_session)
    for _ in range(MAX_FAILURES):
        assert (await _login(async_client, password="nope nope nope")).status_code == 401
    locked = await _login(async_client)  # even the right password is refused during the lock
    assert locked.status_code == 429 and locked.json()["detail"]["code"] == "ACCOUNT_LOCKED"
    assert 0 < locked.json()["detail"]["retry_after_seconds"] <= 15 * 60 and "Retry-After" in locked.headers
    credential = (await db_session.execute(select(UserCredential))).scalar_one()
    credential.locked_until = datetime.now(UTC) - timedelta(seconds=1)  # the lock is over
    await db_session.commit()
    assert (await _login(async_client)).status_code == 200


async def test_a_right_password_clears_the_count_of_mistakes(async_client: AsyncClient, db_session, enabled):
    await _account(db_session)
    for _ in range(MAX_FAILURES - 1):
        await _login(async_client, password="nope nope nope")
    assert (await _login(async_client)).status_code == 200
    for _ in range(MAX_FAILURES - 1):
        await _login(async_client, password="nope nope nope")
    assert (await _login(async_client)).status_code == 200  # four mistakes again did not lock it


async def test_a_blocked_account_does_not_enter_and_a_block_stops_a_token_at_once(async_client: AsyncClient, db_session, enabled):
    user = await _account(db_session)
    token = (await _login(async_client)).json()["access_token"]
    entry = (await db_session.execute(select(AccessEntry).where(AccessEntry.telegram_user_id == user.telegram_user_id))).scalar_one()
    assert entry.status == AccessStatus.ACTIVE.value  # the list of access knows the web account
    entry.status = AccessStatus.BLOCKED.value
    await db_session.commit()
    assert (await _login(async_client)).status_code == 403
    assert (await async_client.get("/api/me", headers=auth_header(token))).status_code == 403


async def test_the_data_of_two_accounts_do_not_meet(async_client: AsyncClient, db_session, enabled):
    await _account(db_session, "a@example.pl")
    await _account(db_session, "b@example.pl")
    token_a = (await _login(async_client, "a@example.pl")).json()["access_token"]
    token_b = (await _login(async_client, "b@example.pl")).json()["access_token"]
    created = await async_client.post(
        "/api/clients", headers=auth_header(token_a), json={"id": "11111111-1111-4111-8111-111111111111", "client_type": "PRIVATE_PERSON", "first_name": "Anna", "last_name": "Nowak"}
    )
    assert created.status_code in (200, 201), created.text
    assert (await async_client.get("/api/clients", headers=auth_header(token_b))).json()["total"] == 0


# --- the accounts ------------------------------------------------------------------------------------------------------------------------


async def test_an_account_gets_a_negative_id_and_a_place_in_the_list(db_session):
    first = await _account(db_session, "a@example.pl")
    second = await _account(db_session, "b@example.pl")
    assert (first.telegram_user_id, second.telegram_user_id) == (-1, -2)
    real = User(telegram_user_id=777_000_111, first_name="Telegram")
    db_session.add(real)
    await db_session.commit()
    third = await _account(db_session, "c@example.pl")
    assert third.telegram_user_id == -3  # a real Telegram id never takes part
    assert await AccessService(db_session).ensure_allowed(first.telegram_user_id) is False  # allowed, not an administrator


@pytest.mark.parametrize(
    "email,password,code",
    [("not-an-email", PASSWORD, "EMAIL_INVALID"), ("a@example.pl", "short", "PASSWORD_TOO_SHORT")],
)
async def test_a_bad_account_is_refused(db_session, email, password, code):
    with pytest.raises(WebAccountError) as error:
        await PasswordLoginService(db_session).create_account(email, "Jan", password)
    assert error.value.code == code


async def test_an_e_mail_is_taken_once(db_session):
    await _account(db_session, "jan@example.pl")
    with pytest.raises(WebAccountError) as error:
        await _account(db_session, "JAN@example.pl")
    assert error.value.code == "EMAIL_TAKEN"


async def test_the_command_line_makes_lists_and_changes(db_session, monkeypatch):
    from tests.conftest import TestingSessionLocal  # noqa: PLC0415

    monkeypatch.setattr(users_cli, "async_session_maker", TestingSessionLocal)
    out = io.StringIO()
    assert await users_cli.run(["create", "--email", "Mistrz@example.pl", "--name", "Mistrz"], out=out) == 0
    text = out.getvalue()
    assert "account made: mistrz@example.pl" in text and "password (shown once" in text
    generated = text.split(": ")[-1].strip()
    assert len(generated) >= 12
    credential = (await db_session.execute(select(UserCredential))).scalar_one()
    assert credential.password_hash.startswith("scrypt$") and generated not in credential.password_hash

    out = io.StringIO()
    assert await users_cli.run(["create", "--email", "mistrz@example.pl"], out=out) == 1 and "EMAIL_TAKEN" in out.getvalue()

    out = io.StringIO()
    assert await users_cli.run(["set-password", "--email", "mistrz@example.pl", "--password-stdin"], out=out, stdin=io.StringIO("a longer password 123\n")) == 0
    assert "password (shown once" not in out.getvalue()  # a typed password is not printed back
    await db_session.refresh(credential)
    assert verify_password("a longer password 123", credential.password_hash)

    out = io.StringIO()
    assert await users_cli.run(["list"], out=out) == 0
    assert out.getvalue().startswith("mistrz@example.pl\tMistrz\tnever signed in") and "password" not in out.getvalue().lower()


async def test_set_password_clears_a_lock(db_session):
    await _account(db_session)
    credential = (await db_session.execute(select(UserCredential))).scalar_one()
    credential.failed_attempts, credential.locked_until = 3, datetime.now(UTC) + timedelta(minutes=10)
    await db_session.commit()
    await PasswordLoginService(db_session).set_password("jan@example.pl", "another long password")
    await db_session.refresh(credential)
    assert credential.failed_attempts == 0 and credential.locked_until is None
    with pytest.raises(WebAccountError):
        await PasswordLoginService(db_session).set_password("nobody@example.pl")


# --- what an account without Telegram cannot get -----------------------------------------------------------------------------------------


async def test_a_document_is_not_sent_to_a_chat_that_does_not_exist():
    from app.domain.documents.delivery import TelegramBotApiDelivery  # noqa: PLC0415
    from app.domain.exceptions import DocumentChatUnavailableError  # noqa: PLC0415

    delivery = TelegramBotApiDelivery("123:abc")  # no transport: a call would reach for the network
    with pytest.raises(DocumentChatUnavailableError):
        await delivery.send_document(-1, "x.pdf", b"%PDF", "caption")
