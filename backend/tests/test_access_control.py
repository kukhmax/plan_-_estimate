"""Closed registration -- who may enter: the login, every request with a token, the screen of the administrator, the command line, the migration 0065."""
import io
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.cli import access as access_cli
from app.domain.exceptions import AccessDeniedError
from app.domain.services.access_service import CONTACT_MAX_LENGTH, PENDING_CAP, AccessService
from app.models.access_entry import AccessEntry, AccessSetting
from app.models.user import User
from tests.conftest import TestingSessionLocal, make_telegram_init_data
from tests.test_stage16e2_contract import run

NAME = "0065_access_control"


def person(number: int, **over) -> dict:
    data = {"id": 700000 + number, "first_name": f"Name{number}", "last_name": "Test", "username": f"user{number}", "language_code": "pl"}
    data.update(over)
    return data


async def login(client: AsyncClient, user: dict):
    return await client.post("/api/auth/telegram", json={"init_data": make_telegram_init_data(user)})


def header(response) -> dict:
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def settings_row(db, closed: bool, contact: str = "") -> None:
    db.add(AccessSetting(key="closed", value="1" if closed else "0"))
    db.add(AccessSetting(key="contact", value=contact))
    await db.commit()


async def entry_of(db, telegram_id: int) -> AccessEntry | None:
    return (await db.execute(select(AccessEntry).where(AccessEntry.telegram_user_id == telegram_id))).scalar_one_or_none()


async def admit(db, telegram_id: int, status: str = "ACTIVE", admin: bool = False) -> AccessEntry:
    row = AccessEntry(telegram_user_id=telegram_id, status=status, is_admin=admin)
    db.add(row)
    await db.commit()
    return row


# --- open registration (the way it was) -----------------------------------------------------------------------------------------------------


async def test_open_registration_admits_anyone_and_writes_the_list(async_client, db_session):
    response = await login(async_client, person(1))
    assert response.status_code == 200 and response.json()["user"]["is_admin"] is False
    row = await entry_of(db_session, 700001)
    assert row is not None and row.status == "ACTIVE" and row.decided_at is not None and row.username == "user1"
    assert (await async_client.get("/api/me", headers=header(response))).status_code == 200


async def test_open_registration_still_refuses_a_blocked_account(async_client, db_session):
    await admit(db_session, 700002, "BLOCKED")
    refused = await login(async_client, person(2))
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "ACCESS_BLOCKED"


async def test_open_registration_admits_a_pending_request_from_the_closed_time(async_client, db_session):
    await admit(db_session, 700003, "PENDING")
    assert (await login(async_client, person(3))).status_code == 200
    assert (await entry_of(db_session, 700003)).status == "ACTIVE"


# --- closed registration ---------------------------------------------------------------------------------------------------------------------


async def test_closed_registration_refuses_an_unknown_account_and_notes_the_request(async_client, db_session):
    await settings_row(db_session, True, "Jan Kowalski, @jan_k")
    refused = await login(async_client, person(4))
    assert refused.status_code == 403
    detail = refused.json()["detail"]
    assert detail["code"] == "ACCESS_DENIED" and detail["contact"] == "Jan Kowalski, @jan_k"
    assert "access_token" not in refused.text
    assert (await db_session.execute(select(func.count()).select_from(User))).scalar_one() == 0  # no user row, so no key, no data
    row = await entry_of(db_session, 700004)
    assert row.status == "PENDING" and row.first_name == "Name4" and row.username == "user4" and row.decided_at is None


async def test_a_second_attempt_does_not_duplicate_and_refreshes_the_profile(async_client, db_session):
    await settings_row(db_session, True)
    await login(async_client, person(5))
    await login(async_client, person(5, username="renamed"))
    rows = (await db_session.execute(select(AccessEntry).where(AccessEntry.telegram_user_id == 700005))).scalars().all()
    assert len(rows) == 1
    await db_session.refresh(rows[0])
    assert rows[0].username == "renamed"


async def test_closed_registration_admits_an_active_account_and_an_administrator(async_client, db_session):
    await settings_row(db_session, True)
    await admit(db_session, 700006, "ACTIVE")
    await admit(db_session, 700007, "ACTIVE", admin=True)
    ordinary, admin = await login(async_client, person(6)), await login(async_client, person(7))
    assert ordinary.status_code == 200 and ordinary.json()["user"]["is_admin"] is False
    assert admin.status_code == 200 and admin.json()["user"]["is_admin"] is True


async def test_an_administrator_enters_even_when_the_row_says_otherwise(async_client, db_session):
    await settings_row(db_session, True)
    await admit(db_session, 700008, "BLOCKED", admin=True)  # cannot happen through the screen; the guard against a lock-out
    assert (await login(async_client, person(8))).status_code == 200


async def test_closed_registration_refuses_a_blocked_account_with_its_own_code(async_client, db_session):
    await settings_row(db_session, True)
    await admit(db_session, 700009, "BLOCKED")
    refused = await login(async_client, person(9))
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "ACCESS_BLOCKED"


async def test_the_flood_of_requests_is_capped(async_client, db_session):
    await settings_row(db_session, True)
    for index in range(PENDING_CAP):
        db_session.add(AccessEntry(telegram_user_id=10_000 + index, status="PENDING"))
    await db_session.commit()
    refused = await login(async_client, person(10))
    assert refused.status_code == 403 and await entry_of(db_session, 700010) is None


async def test_two_sign_ins_at_once_leave_one_row(db_session):
    service = AccessService(db_session)
    first = await service._create(700011, {"username": "a"}, "PENDING", None)
    second = await service._create(700011, {"username": "b"}, "PENDING", None)
    assert first.id == second.id
    assert (await db_session.execute(select(func.count()).select_from(AccessEntry))).scalar_one() == 1


# --- every request with a token --------------------------------------------------------------------------------------------------------------


async def test_a_block_takes_effect_at_once_on_a_token_already_issued(async_client, db_session):
    token = await login(async_client, person(12))
    assert (await async_client.get("/api/me", headers=header(token))).status_code == 200
    (await entry_of(db_session, 700012)).status = "BLOCKED"
    await db_session.commit()
    refused = await async_client.get("/api/clients", headers=header(token))
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "ACCESS_BLOCKED"


async def test_closing_the_registration_stops_an_account_that_is_not_admitted(async_client, db_session):
    token = await login(async_client, person(13))
    await db_session.execute(text("DELETE FROM access_entries"))  # as if it never was in the list
    await settings_row(db_session, True, "ask me")
    refused = await async_client.get("/api/me", headers=header(token))
    assert refused.status_code == 403 and refused.json()["detail"] == {
        "code": "ACCESS_DENIED", "message": "Access to the application is closed for this account", "contact": "ask me",
    }


async def test_the_check_of_a_request_costs_no_statement_of_its_own(async_client, db_session):
    from tests import test_stage14c5_followup as fu

    token = await login(async_client, person(15))
    with fu.captured_sql() as statements:
        assert (await async_client.get("/api/me", headers=header(token))).status_code == 200
    with_access = [s for s in statements if "access_entries" in s or "access_settings" in s]
    assert len(with_access) == 1 and "FROM users" in with_access[0]  # the facts are read inside the statement that reads the user


async def test_the_check_of_a_request_writes_nothing(async_client, db_session):
    token = await login(async_client, person(14))
    await db_session.execute(text("DELETE FROM access_entries"))
    await db_session.commit()
    assert (await async_client.get("/api/me", headers=header(token))).status_code == 200  # open registration, no row: allowed
    assert (await db_session.execute(select(func.count()).select_from(AccessEntry))).scalar_one() == 0


# --- the screen of the administrator ---------------------------------------------------------------------------------------------------------


async def an_admin(client, db) -> dict:
    await admit(db, 700020, "ACTIVE", admin=True)
    return header(await login(client, person(20)))


async def test_the_screen_is_for_the_administrator_only(async_client, db_session):
    ordinary = header(await login(async_client, person(21)))
    for method, url, body in (
        ("get", "/api/access", None),
        ("patch", f"/api/access/entries/{uuid.uuid4()}", {"status": "ACTIVE"}),
        ("delete", f"/api/access/entries/{uuid.uuid4()}", None),
        ("put", "/api/access/settings", {"closed": True}),
    ):
        response = await getattr(async_client, method)(url, headers=ordinary, **({"json": body} if body else {}))
        assert response.status_code == 403 and response.json()["detail"]["code"] == "ACCESS_ADMIN_ONLY", url
    assert (await async_client.get("/api/access")).status_code == 401


async def test_the_list_shows_pending_first_then_active_then_blocked(async_client, db_session):
    admin = await an_admin(async_client, db_session)
    old = datetime.now(UTC) - timedelta(days=1)
    db_session.add_all([
        AccessEntry(telegram_user_id=1, status="BLOCKED", created_at=old),
        AccessEntry(telegram_user_id=2, status="PENDING", created_at=old),
        AccessEntry(telegram_user_id=3, status="ACTIVE", created_at=old),
    ])
    await db_session.commit()
    body = (await async_client.get("/api/access", headers=admin)).json()
    assert [row["status"] for row in body["entries"]] == ["PENDING", "ACTIVE", "ACTIVE", "BLOCKED"]
    assert body["settings"] == {"closed": False, "contact": ""}


async def test_the_administrator_admits_and_blocks_and_the_account_follows(async_client, db_session):
    await settings_row(db_session, True)
    admin = await an_admin(async_client, db_session)
    assert (await login(async_client, person(22))).status_code == 403
    pending = await entry_of(db_session, 700022)
    allowed = await async_client.patch(f"/api/access/entries/{pending.id}", headers=admin, json={"status": "ACTIVE"})
    assert allowed.status_code == 200 and allowed.json()["status"] == "ACTIVE" and allowed.json()["decided_at"]
    token = await login(async_client, person(22))
    assert token.status_code == 200
    blocked = await async_client.patch(f"/api/access/entries/{pending.id}", headers=admin, json={"status": "BLOCKED"})
    assert blocked.json()["status"] == "BLOCKED"
    assert (await async_client.get("/api/me", headers=header(token))).status_code == 403


async def test_an_administrator_cannot_be_blocked_or_removed_through_the_screen(async_client, db_session):
    admin = await an_admin(async_client, db_session)
    mine = (await entry_of(db_session, 700020)).id
    for response in (
        await async_client.patch(f"/api/access/entries/{mine}", headers=admin, json={"status": "BLOCKED"}),
        await async_client.delete(f"/api/access/entries/{mine}", headers=admin),
    ):
        assert response.status_code == 409 and response.json()["detail"]["code"] == "ACCESS_ADMIN_PROTECTED"
    assert (await entry_of(db_session, 700020)).status == "ACTIVE"


async def test_removing_a_row_and_an_unknown_row(async_client, db_session):
    admin = await an_admin(async_client, db_session)
    db_session.add(AccessEntry(telegram_user_id=5, status="PENDING"))
    await db_session.commit()
    row = await entry_of(db_session, 5)
    assert (await async_client.delete(f"/api/access/entries/{row.id}", headers=admin)).status_code == 204
    assert await entry_of(db_session, 5) is None
    for response in (
        await async_client.delete(f"/api/access/entries/{uuid.uuid4()}", headers=admin),
        await async_client.patch(f"/api/access/entries/{uuid.uuid4()}", headers=admin, json={"status": "ACTIVE"}),
    ):
        assert response.status_code == 404 and response.json()["detail"]["code"] == "ACCESS_ENTRY_NOT_FOUND"


async def test_the_decision_accepts_only_active_or_blocked(async_client, db_session):
    admin = await an_admin(async_client, db_session)
    db_session.add(AccessEntry(telegram_user_id=6, status="PENDING"))
    await db_session.commit()
    row = await entry_of(db_session, 6)
    assert (await async_client.patch(f"/api/access/entries/{row.id}", headers=admin, json={"status": "PENDING"})).status_code == 422


async def test_the_settings_close_open_and_keep_the_contact(async_client, db_session):
    admin = await an_admin(async_client, db_session)
    first = await async_client.put("/api/access/settings", headers=admin, json={"closed": True, "contact": "  @owner  "})
    assert first.status_code == 200 and first.json() == {"closed": True, "contact": "@owner"}
    only_switch = await async_client.put("/api/access/settings", headers=admin, json={"closed": False})
    assert only_switch.json() == {"closed": False, "contact": "@owner"}  # the contact is not touched when it is not sent
    only_contact = await async_client.put("/api/access/settings", headers=admin, json={"contact": ""})
    assert only_contact.json() == {"closed": False, "contact": ""}
    assert (await async_client.get("/api/access", headers=admin)).json()["settings"] == {"closed": False, "contact": ""}


async def test_a_long_contact_is_refused_and_nothing_is_saved(async_client, db_session):
    admin = await an_admin(async_client, db_session)
    too_long = "x" * (CONTACT_MAX_LENGTH + 1)
    assert (await async_client.put("/api/access/settings", headers=admin, json={"contact": too_long})).status_code == 422
    assert (await async_client.put("/api/access/settings", headers=admin, json={"closed": True, "contact": "y" * CONTACT_MAX_LENGTH})).status_code == 200
    assert await AccessService(db_session).contact() == "y" * CONTACT_MAX_LENGTH


async def test_the_service_refuses_a_long_contact_even_without_the_schema(db_session):
    from app.domain.exceptions import AccessSettingsInvalidError

    with pytest.raises(AccessSettingsInvalidError):
        await AccessService(db_session).update_settings(None, "z" * (CONTACT_MAX_LENGTH + 1))


# --- the service and the command line --------------------------------------------------------------------------------------------------------


async def test_the_denial_carries_the_contact_and_the_kind(db_session):
    await settings_row(db_session, True, "call me")
    with pytest.raises(AccessDeniedError) as caught:
        await AccessService(db_session).ensure_allowed(123)
    assert caught.value.contact == "call me" and caught.value.blocked is False


async def test_set_admin_makes_one_administrator_and_admits_a_new_account(db_session):
    await admit(db_session, 1, "ACTIVE", admin=True)
    service = AccessService(db_session)
    await service.set_admin(2)  # not in the list yet
    admins = (await db_session.execute(select(AccessEntry).where(AccessEntry.is_admin.is_(True)))).scalars().all()
    assert [row.telegram_user_id for row in admins] == [2] and admins[0].status == "ACTIVE"
    assert (await entry_of(db_session, 1)).status == "ACTIVE" and not (await entry_of(db_session, 1)).is_admin


async def run_cli(monkeypatch, *argv: str) -> str:
    monkeypatch.setattr(access_cli, "async_session_maker", TestingSessionLocal)
    out = io.StringIO()
    assert await access_cli.run(list(argv), out) == 0
    return out.getvalue()


async def test_the_command_line_status_open_close_and_set_admin(db_session, monkeypatch):
    await admit(db_session, 1, "ACTIVE", admin=True)
    await admit(db_session, 2, "PENDING")
    await admit(db_session, 3, "BLOCKED")
    text_out = await run_cli(monkeypatch, "status")
    assert "OPEN" in text_out and "ACTIVE: 1  PENDING: 1  BLOCKED: 1  administrators: 1" in text_out
    assert "CLOSED" in await run_cli(monkeypatch, "close")
    assert "OPEN" in await run_cli(monkeypatch, "open")
    after = await run_cli(monkeypatch, "set-admin", "--telegram-id", "2")
    assert "ACTIVE: 2  PENDING: 0  BLOCKED: 1  administrators: 1" in after
    assert "Name" not in text_out and "user" not in text_out  # counts only


# --- the migration ---------------------------------------------------------------------------------------------------------------------------


def users_engine():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id CHAR(32) PRIMARY KEY, telegram_user_id BIGINT, username VARCHAR(255), first_name VARCHAR(255), last_name VARCHAR(255), created_at DATETIME)"))
        conn.execute(text("INSERT INTO users VALUES ('b', 222, 'second', 'Two', 'T', '2026-10-02 10:00:00')"))
        conn.execute(text("INSERT INTO users VALUES ('a', 111, 'first', 'One', 'O', '2026-10-01 10:00:00')"))
    return engine


def test_the_migration_admits_everybody_makes_the_first_user_the_administrator_and_closes():
    engine = users_engine()
    run(engine, NAME, "upgrade")
    with engine.begin() as conn:
        rows = conn.execute(text("SELECT telegram_user_id, status, is_admin, username FROM access_entries ORDER BY telegram_user_id")).all()
        assert [tuple(row) for row in rows] == [(111, "ACTIVE", 1, "first"), (222, "ACTIVE", 0, "second")]
        assert dict(conn.execute(text("SELECT key, value FROM access_settings")).all()) == {"closed": "1", "contact": ""}
        assert conn.execute(text("SELECT count(*) FROM users")).scalar_one() == 2  # no user is touched


def test_the_migration_on_an_empty_users_table_makes_an_empty_closed_list():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id CHAR(32) PRIMARY KEY, telegram_user_id BIGINT, username VARCHAR(255), first_name VARCHAR(255), last_name VARCHAR(255), created_at DATETIME)"))
    run(engine, NAME, "upgrade")
    with engine.begin() as conn:
        assert conn.execute(text("SELECT count(*) FROM access_entries")).scalar_one() == 0


def test_the_status_is_checked_and_the_downgrade_drops_both_tables():
    engine = users_engine()
    run(engine, NAME, "upgrade")
    with engine.begin() as conn, pytest.raises(IntegrityError):
        conn.execute(text("INSERT INTO access_entries (id, telegram_user_id, status, is_admin, created_at) VALUES ('x', 9, 'WHATEVER', 0, '2026-10-01')"))
    run(engine, NAME, "downgrade")
    assert not {"access_entries", "access_settings"} & set(inspect(engine).get_table_names())
