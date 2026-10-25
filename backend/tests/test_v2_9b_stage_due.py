"""V2-9b -- the due day of a stage of the payment schedule is an event of the calendar and a reminder (pure functions, then the real routes)."""
import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from app.domain.calendar.events import (
    PUSH_BY_DEFAULT,
    EventKind,
    StageDue,
    lead_days,
    stage_events,
)
from app.domain.calendar.messages import ReminderView, compose_messages
from app.domain.calendar.prefs import CalendarPrefs
from app.domain.calendar.reconcile import desired_reminders
from app.domain.services.calendar_service import CalendarService
from app.models.project import Project
from app.models.reminder import Reminder
from sqlalchemy import select

from tests.test_clients import OTHER_USER, VALID_USER, auth_header, get_token
from tests.test_projects import create_project

WARSAW = ZoneInfo("Europe/Warsaw")
P = uuid.UUID("11111111-1111-1111-1111-111111111111")


def today() -> date:
    return datetime.now(UTC).date()


# ------------------------------------------------------------------ the pure part

def test_a_stage_gives_its_due_day_with_a_key_of_its_own_and_its_title():
    first, second = uuid.uuid4(), uuid.uuid4()
    events = stage_events([StageDue(P, first, date(2026, 11, 20), "Zaliczka"), StageDue(P, second, date(2026, 11, 25), "Po gładziach")])
    assert [(e.kind, e.on, e.params) for e in events] == [
        (EventKind.STAGE_DUE, date(2026, 11, 20), {"what": "Zaliczka"}),
        (EventKind.STAGE_DUE, date(2026, 11, 25), {"what": "Po gładziach"}),
    ]
    assert events[0].key != events[1].key and str(first) in events[0].key and events[0].title_key == "calendar.event.stage_due"
    assert stage_events([]) == []


def test_a_long_title_is_cut_so_that_a_message_stays_short():
    [event] = stage_events([StageDue(P, uuid.uuid4(), date(2026, 11, 20), "  " + "x" * 200)])
    assert event.params["what"] == "x" * 60


def test_the_due_day_is_announced_a_day_ahead_and_on_the_day_and_sends_by_default():
    assert lead_days(EventKind.STAGE_DUE) == (1, 0) and EventKind.STAGE_DUE in PUSH_BY_DEFAULT
    [event] = stage_events([StageDue(P, uuid.uuid4(), date(2026, 11, 20), "Odbiór")])
    wanted = desired_reminders([event], CalendarPrefs())
    by_lead = {item.lead_days: item.send_at.astimezone(WARSAW) for item in wanted}
    assert sorted(by_lead) == [0, 1]
    assert by_lead[1] == datetime(2026, 11, 19, 8, 0, tzinfo=WARSAW) and by_lead[0] == datetime(2026, 11, 20, 8, 0, tzinfo=WARSAW)  # the morning digest


def test_the_owner_may_switch_it_off_in_the_settings():
    [event] = stage_events([StageDue(P, uuid.uuid4(), date(2026, 11, 20), "Odbiór")])
    assert desired_reminders([event], CalendarPrefs(kind_overrides={"STAGE_DUE": False})) == []
    assert desired_reminders([event], CalendarPrefs(enabled=False)) == []
    assert desired_reminders([event], CalendarPrefs(kind_overrides={"INVOICE_DUE": False}))  # an invoice switch does not touch the stages


def view(what: str, lead: int = 0, **over) -> ReminderView:
    return ReminderView(
        id=uuid.uuid4(), origin="AUTO", kind="STAGE_DUE", ref="", title=None, title_key="calendar.event.stage_due", params={"what": what},
        event_on=date(2026, 11, 20), lead_days=lead, send_at=datetime(2026, 11, 20 - lead, 7, 0, tzinfo=UTC), project_id=P, project_name="Mokotów", **over,
    )


@pytest.mark.parametrize(("lang", "line"), [
    ("pl", "• Mokotów — Termin płatności etapu: Zaliczka, dziś"),
    ("ru", "• Mokotów — Срок оплаты этапа: Zaliczka, сегодня"),
    ("uk", "• Mokotów — Строк оплати етапу: Zaliczka, сьогодні"),
    ("en", "• Mokotów — Payment stage due: Zaliczka, today"),
])
def test_the_message_names_the_stage_in_the_language_of_the_owner(lang, line):
    [message] = compose_messages([view("Zaliczka")], lang=lang, now=datetime(2026, 11, 20, 7, 5, tzinfo=UTC))
    assert line in message.text


def test_a_day_ahead_says_when_it_is_due():
    [message] = compose_messages([view("Zaliczka", lead=1)], lang="pl", now=datetime(2026, 11, 19, 7, 5, tzinfo=UTC))
    assert "Termin płatności etapu: Zaliczka, za 1 dn. (20.11.2026)" in message.text


def test_braces_in_a_title_and_a_missing_title_never_break_a_message():
    [odd] = compose_messages([view("{what} {0} {x}")], lang="pl", now=datetime(2026, 11, 20, 7, 5, tzinfo=UTC))
    assert "Termin płatności etapu: {what} {0} {x}" in odd.text
    nameless = ReminderView(**{**view("").__dict__, "params": {}})
    [message] = compose_messages([nameless], lang="pl", now=datetime(2026, 11, 20, 7, 5, tzinfo=UTC))
    assert "{" not in message.text


# ------------------------------------------------------------------ the real routes

async def owner(c) -> str:
    return await get_token(c, VALID_USER)


async def project_of(c, token) -> str:
    return (await create_project(c, token))["id"]


async def stage(c, token, project, due: date | None, title="Zaliczka", **money) -> dict:
    body = {"title": title, **(money or {"amount": "1000.00"})}
    if due is not None:
        body["due_on"] = due.isoformat()
    r = await c.post(f"/api/projects/{project}/payment-stages", json=body, headers=auth_header(token))
    assert r.status_code == 201, r.text
    return r.json()


async def reminders(db) -> list[Reminder]:
    stmt = select(Reminder).execution_options(populate_existing=True).where(Reminder.kind == "STAGE_DUE").order_by(Reminder.lead_days.desc(), Reminder.dedupe_key)
    return list((await db.execute(stmt)).scalars())


async def states(db) -> list[tuple[int, str]]:
    return [(r.lead_days, r.status) for r in await reminders(db)]


async def pay(c, token, project, stage_id: str, amount: str) -> dict:
    r = await c.post(f"/api/projects/{project}/payments", json={
        "kind": "PAYMENT", "title": "Wpłata", "amount_gross": amount, "occurred_on": today().isoformat(), "stage_id": stage_id}, headers=auth_header(token))
    assert r.status_code == 201, r.text
    return r.json()


async def test_a_stage_with_a_due_day_queues_its_two_reminders_at_once(async_client, db_session):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    made = await stage(async_client, t, p, today() + timedelta(days=10), title="Po gładziach")
    rows = await reminders(db_session)
    assert [(r.lead_days, r.status) for r in rows] == [(1, "PENDING"), (0, "PENDING")]
    assert {r.title_key for r in rows} == {"calendar.event.stage_due"} and {r.params["what"] for r in rows} == {"Po gładziach"}
    assert {r.event_on for r in rows} == {today() + timedelta(days=10)} and {str(r.project_id) for r in rows} == {p}
    assert made["id"] in rows[0].dedupe_key


@pytest.mark.parametrize("due_offset", [None, -2])
async def test_a_stage_without_a_day_or_with_a_day_that_has_passed_queues_nothing(async_client, db_session, due_offset):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    await stage(async_client, t, p, None if due_offset is None else today() + timedelta(days=due_offset))
    assert await reminders(db_session) == []  # a late message would only be noise: the screen shows an overdue stage


async def test_a_stage_that_is_a_share_of_an_unknown_agreed_amount_is_still_reminded(async_client, db_session):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    await stage(async_client, t, p, today() + timedelta(days=10), percent="30")
    assert await states(db_session) == [(1, "PENDING"), (0, "PENDING")]


async def test_money_in_full_takes_the_reminders_away_and_a_part_does_not(async_client, db_session):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    made = await stage(async_client, t, p, today() + timedelta(days=10), amount="1000.00")
    await pay(async_client, t, p, made["id"], "400")
    assert await states(db_session) == [(1, "PENDING"), (0, "PENDING")]  # 600 are still to be received
    rest = await pay(async_client, t, p, made["id"], "600")
    assert await states(db_session) == [(1, "CANCELLED"), (0, "CANCELLED")]
    # taking the last payment back (archiving it) brings the same reminders back
    assert (await async_client.post(f"/api/projects/{p}/payments/{rest['id']}/archive", headers=auth_header(t))).status_code == 200
    assert await states(db_session) == [(1, "PENDING"), (0, "PENDING")]
    assert len(await reminders(db_session)) == 2  # the same rows, not new ones


async def test_the_one_tap_received_closes_the_stage_and_its_reminders(async_client, db_session):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    made = await stage(async_client, t, p, today() + timedelta(days=10))
    r = await async_client.post(f"/api/projects/{p}/payment-stages/{made['id']}/receive", headers=auth_header(t))
    assert r.status_code in (200, 201), r.text
    assert await states(db_session) == [(1, "CANCELLED"), (0, "CANCELLED")]


async def test_moving_the_day_moves_the_reminders_and_clearing_it_cancels_them(async_client, db_session):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    made = await stage(async_client, t, p, today() + timedelta(days=10))
    moved = today() + timedelta(days=20)
    r = await async_client.patch(f"/api/projects/{p}/payment-stages/{made['id']}", json={"due_on": moved.isoformat()}, headers=auth_header(t))
    assert r.status_code == 200
    rows = await reminders(db_session)
    assert sorted(row.lead_days for row in rows if row.status == "PENDING") == [0, 1] and {row.event_on for row in rows if row.status == "PENDING"} == {moved}
    assert len([row for row in rows if row.status == "CANCELLED"]) == 2  # the old day's
    cleared = await async_client.patch(f"/api/projects/{p}/payment-stages/{made['id']}", json={"due_on": None}, headers=auth_header(t))
    assert cleared.status_code == 200
    assert {row.status for row in await reminders(db_session)} == {"CANCELLED"}


async def test_a_renamed_stage_keeps_its_reminders_and_a_deleted_one_loses_them(async_client, db_session):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    made = await stage(async_client, t, p, today() + timedelta(days=10), title="Stary")
    assert (await async_client.patch(f"/api/projects/{p}/payment-stages/{made['id']}", json={"title": "Nowy"}, headers=auth_header(t))).status_code == 200
    assert await states(db_session) == [(1, "PENDING"), (0, "PENDING")] and len(await reminders(db_session)) == 2
    assert (await async_client.delete(f"/api/projects/{p}/payment-stages/{made['id']}", headers=auth_header(t))).status_code in (200, 204)
    assert {row.status for row in await reminders(db_session)} == {"CANCELLED"}


async def test_a_change_of_the_agreed_amount_that_money_now_covers_closes_a_share(async_client, db_session):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    assert (await async_client.put(f"/api/projects/{p}/finance", json={"agreed_amount": "10000"}, headers=auth_header(t))).status_code == 200
    made = await stage(async_client, t, p, today() + timedelta(days=10), percent="30")  # 3000
    await pay(async_client, t, p, made["id"], "1000")
    assert await states(db_session) == [(1, "PENDING"), (0, "PENDING")]
    assert (await async_client.put(f"/api/projects/{p}/finance", json={"agreed_amount": "3000"}, headers=auth_header(t))).status_code == 200  # 30% is now 900
    assert {row.status for row in await reminders(db_session)} == {"CANCELLED"}
    assert (await async_client.put(f"/api/projects/{p}/finance", json={"agreed_amount": "10000"}, headers=auth_header(t))).status_code == 200
    assert await states(db_session) == [(1, "PENDING"), (0, "PENDING")]


async def test_the_settings_switch_the_kind_and_it_is_listed_with_its_default(async_client, db_session):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    listed = (await async_client.get("/api/calendar/settings", headers=auth_header(t))).json()
    assert {"kind": "STAGE_DUE", "default_push": True, "sends": True} in listed["kinds"]
    await stage(async_client, t, p, today() + timedelta(days=10))
    off = await async_client.put("/api/calendar/settings", json={
        "timezone": "Europe/Warsaw", "enabled": True, "kind_overrides": {"STAGE_DUE": False}, "quiet_from": "21:00", "quiet_to": "07:00",
        "digest_at": "08:00", "language": None}, headers=auth_header(t))
    assert off.status_code == 200, off.text
    assert {row.status for row in await reminders(db_session)} == {"CANCELLED"}
    agenda = (await async_client.get("/api/calendar", params={"start": today().isoformat(), "end": (today() + timedelta(days=30)).isoformat()}, headers=auth_header(t))).json()
    item = next(i for i in agenda["items"] if i["kind"] == "STAGE_DUE")  # the calendar still shows the day, only the message is off
    assert item["sends"] is False and item["title_key"] == "calendar.event.stage_due" and item["project_id"] == p


async def test_the_agenda_shows_the_due_day_with_the_title_of_the_stage(async_client, db_session):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    await stage(async_client, t, p, today() + timedelta(days=10), title="Odbiór")
    agenda = (await async_client.get("/api/calendar", params={"start": today().isoformat(), "end": (today() + timedelta(days=30)).isoformat()}, headers=auth_header(t))).json()
    [item] = [i for i in agenda["items"] if i["kind"] == "STAGE_DUE"]
    assert (item["on"], item["params"], item["sends"]) == ((today() + timedelta(days=10)).isoformat(), {"what": "Odbiór"}, True)


async def test_an_archived_object_keeps_no_stage_reminder_and_gets_them_back(async_client, db_session):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    await stage(async_client, t, p, today() + timedelta(days=10))
    assert (await async_client.post(f"/api/projects/{p}/archive", headers=auth_header(t))).status_code == 200
    assert {row.status for row in await reminders(db_session)} == {"CANCELLED"}
    assert (await async_client.post(f"/api/projects/{p}/restore", headers=auth_header(t))).status_code == 200
    assert await states(db_session) == [(1, "PENDING"), (0, "PENDING")]


async def test_a_fault_of_the_calendar_never_stops_a_stage_from_being_saved(async_client, db_session, monkeypatch, caplog):
    t = await owner(async_client)
    p = await project_of(async_client, t)

    async def broken(self, owner_id, project_id, **kwargs):
        raise RuntimeError("calendar is down")

    monkeypatch.setattr(CalendarService, "reconcile_project", broken)
    made = await stage(async_client, t, p, today() + timedelta(days=10), title="Odbiór")
    assert made["title"] == "Odbiór"
    assert await reminders(db_session) == []  # the periodic pass brings them later
    assert "calendar reconciliation after archiving failed" in caplog.text


async def test_the_periodic_pass_finds_a_stage_the_hook_missed(async_client, db_session, monkeypatch):
    t = await owner(async_client)
    p = await project_of(async_client, t)

    async def broken(self, owner_id, project_id):
        return None

    monkeypatch.setattr(CalendarService, "reconcile_project_guarded", broken)
    await stage(async_client, t, p, today() + timedelta(days=10))
    assert await reminders(db_session) == []
    monkeypatch.undo()
    owner_id = (await db_session.execute(select(Project.owner_id).where(Project.id == uuid.UUID(p)))).scalar_one()
    await CalendarService(db_session).reconcile_owner(owner_id)
    await db_session.commit()
    assert await states(db_session) == [(1, "PENDING"), (0, "PENDING")]


async def test_nothing_of_another_owner_is_reachable(async_client, db_session):
    t = await owner(async_client)
    other = await get_token(async_client, OTHER_USER)
    p = await project_of(async_client, t)
    await stage(async_client, t, p, today() + timedelta(days=10))
    agenda = (await async_client.get("/api/calendar", params={"start": today().isoformat(), "end": (today() + timedelta(days=30)).isoformat()}, headers=auth_header(other))).json()
    assert [i for i in agenda["items"] if i["kind"] == "STAGE_DUE"] == []
