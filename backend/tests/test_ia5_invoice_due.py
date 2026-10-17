"""Invoices and advances IA-5 -- the due day of an invoice is an event of the calendar and a reminder (pure functions, then the real routes)."""
import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.domain.calendar.events import PUSH_BY_DEFAULT, EventKind, InvoiceDue, invoice_events, lead_days
from app.domain.calendar.messages import ReminderView, compose_messages
from app.domain.calendar.prefs import CalendarPrefs
from app.domain.calendar.reconcile import desired_reminders
from app.domain.services.calendar_service import CalendarService
from app.models.project import Project
from app.models.reminder import Reminder
from tests.test_clients import OTHER_USER, VALID_USER, auth_header, get_token
from tests.test_projects import create_project

WARSAW = ZoneInfo("Europe/Warsaw")
P = uuid.UUID("11111111-1111-1111-1111-111111111111")


def today() -> date:
    return datetime.now(UTC).date()


# ------------------------------------------------------------------ the pure part

def test_an_invoice_gives_its_due_day_with_a_key_of_its_own_and_its_name():
    first, second = uuid.uuid4(), uuid.uuid4()
    events = invoice_events([InvoiceDue(P, first, date(2026, 11, 20), "FV 1/2026"), InvoiceDue(P, second, date(2026, 11, 25), "Etap 2")])
    assert [(e.kind, e.on, e.params) for e in events] == [
        (EventKind.INVOICE_DUE, date(2026, 11, 20), {"what": "FV 1/2026"}),
        (EventKind.INVOICE_DUE, date(2026, 11, 25), {"what": "Etap 2"}),
    ]
    assert events[0].key != events[1].key and str(first) in events[0].key and events[0].title_key == "calendar.event.invoice_due"
    assert invoice_events([]) == []


def test_a_long_name_is_cut_so_that_a_message_stays_short():
    [event] = invoice_events([InvoiceDue(P, uuid.uuid4(), date(2026, 11, 20), "  " + "x" * 200)])
    assert event.params["what"] == "x" * 60


def test_the_due_day_is_announced_three_days_ahead_and_on_the_day_and_sends_by_default():
    assert lead_days(EventKind.INVOICE_DUE) == (3, 0) and EventKind.INVOICE_DUE in PUSH_BY_DEFAULT
    [event] = invoice_events([InvoiceDue(P, uuid.uuid4(), date(2026, 11, 20), "FV 1")])
    wanted = desired_reminders([event], CalendarPrefs())
    assert sorted(item.lead_days for item in wanted) == [0, 3]
    by_lead = {item.lead_days: item.send_at.astimezone(WARSAW) for item in wanted}
    assert by_lead[3] == datetime(2026, 11, 17, 8, 0, tzinfo=WARSAW) and by_lead[0] == datetime(2026, 11, 20, 8, 0, tzinfo=WARSAW)  # the morning digest


def test_the_owner_may_switch_it_off_in_the_settings():
    [event] = invoice_events([InvoiceDue(P, uuid.uuid4(), date(2026, 11, 20), "FV 1")])
    assert desired_reminders([event], CalendarPrefs(kind_overrides={"INVOICE_DUE": False})) == []
    assert desired_reminders([event], CalendarPrefs(enabled=False)) == []


def view(what: str, lead: int = 0, **over) -> ReminderView:
    return ReminderView(
        id=uuid.uuid4(), origin="AUTO", kind="INVOICE_DUE", ref="", title=None, title_key="calendar.event.invoice_due", params={"what": what},
        event_on=date(2026, 11, 20), lead_days=lead, send_at=datetime(2026, 11, 20 - lead, 7, 0, tzinfo=UTC), project_id=P, project_name="Mokotów", **over,
    )


@pytest.mark.parametrize(("lang", "line"), [
    ("pl", "• Mokotów — Termin zapłaty faktury: FV 1/2026, dziś"),
    ("ru", "• Mokotów — Срок оплаты фактуры: FV 1/2026, сегодня"),
])
def test_the_message_names_the_invoice_in_the_language_of_the_owner(lang, line):
    [message] = compose_messages([view("FV 1/2026")], lang=lang, now=datetime(2026, 11, 20, 7, 5, tzinfo=UTC))
    assert line in message.text


def test_three_days_ahead_says_when_it_is_due():
    [message] = compose_messages([view("FV 1/2026", lead=3)], lang="pl", now=datetime(2026, 11, 17, 7, 5, tzinfo=UTC))
    assert "Termin zapłaty faktury: FV 1/2026, za 3 dn. (20.11.2026)" in message.text


def test_braces_in_a_name_and_a_missing_name_never_break_a_message():
    [odd] = compose_messages([view("{what} {0} {x}")], lang="pl", now=datetime(2026, 11, 20, 7, 5, tzinfo=UTC))
    assert "Termin zapłaty faktury: {what} {0} {x}" in odd.text
    nameless = ReminderView(**{**view("").__dict__, "params": {}})
    [message] = compose_messages([nameless], lang="pl", now=datetime(2026, 11, 20, 7, 5, tzinfo=UTC))
    assert "Termin zapłaty faktury: ," in message.text and "{" not in message.text


# ------------------------------------------------------------------ the real routes

async def owner(c) -> str:
    return await get_token(c, VALID_USER)


async def invoice(c, token, project, due: date | None, title="Prace malarskie", amount="1000.00", **over) -> dict:
    body = {"kind": "INVOICE", "title": title, "amount_gross": amount, "occurred_on": today().isoformat(), **over}
    if due is not None:
        body["due_on"] = due.isoformat()
    r = await c.post(f"/api/projects/{project}/payments", json=body, headers=auth_header(token))
    assert r.status_code == 201, r.text
    return r.json()


async def reminders(db, **where) -> list[Reminder]:
    stmt = select(Reminder).execution_options(populate_existing=True).where(Reminder.kind == "INVOICE_DUE").order_by(Reminder.lead_days.desc(), Reminder.dedupe_key)
    for name, value in where.items():
        stmt = stmt.where(getattr(Reminder, name) == value)
    return list((await db.execute(stmt)).scalars())


async def states(db) -> list[tuple[int, str]]:
    return [(r.lead_days, r.status) for r in await reminders(db)]


async def project_of(c, token) -> str:
    return (await create_project(c, token))["id"]


async def test_an_invoice_with_a_due_day_queues_its_two_reminders_at_once(async_client, db_session):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    made = await invoice(async_client, t, p, today() + timedelta(days=10), number="FV 1/2026")
    rows = await reminders(db_session)
    assert [(r.lead_days, r.status) for r in rows] == [(3, "PENDING"), (0, "PENDING")]
    assert {r.title_key for r in rows} == {"calendar.event.invoice_due"} and {r.params["what"] for r in rows} == {"FV 1/2026"}
    assert {r.event_on for r in rows} == {today() + timedelta(days=10)} and {str(r.project_id) for r in rows} == {p}
    assert made["id"] in rows[0].dedupe_key
    # the same invoice sent again (a lost answer, the offline queue) is no second reminder
    again = await async_client.post(f"/api/projects/{p}/payments", json={
        "id": made["id"], "kind": "INVOICE", "title": "Prace malarskie", "number": "FV 1/2026", "amount_gross": "1000.00", "occurred_on": today().isoformat(),
        "due_on": (today() + timedelta(days=10)).isoformat(),
    }, headers=auth_header(t))
    assert again.status_code in (200, 201)
    assert len(await reminders(db_session)) == 2


async def test_the_name_is_its_number_else_what_it_is_for(async_client, db_session):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    await invoice(async_client, t, p, today() + timedelta(days=10), title="Etap bez numeru")
    assert {r.params["what"] for r in await reminders(db_session)} == {"Etap bez numeru"}


@pytest.mark.parametrize("due_offset", [None, -2])
async def test_an_invoice_without_a_term_or_with_a_term_that_has_passed_queues_nothing_new(async_client, db_session, due_offset):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    await invoice(async_client, t, p, None if due_offset is None else today() + timedelta(days=due_offset), occurred_on=(today() - timedelta(days=5)).isoformat())
    assert await reminders(db_session) == []  # a late message would only be noise: the calendar shows an overdue invoice, no message is made for it


@pytest.mark.parametrize("kind", ["ADVANCE", "PAYMENT", "EXPENSE"])
async def test_only_an_invoice_has_a_due_day(async_client, db_session, kind):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    extra = {"counterparty": "Castorama", "document_kind": "RECEIPT"} if kind == "EXPENSE" else {}
    r = await async_client.post(f"/api/projects/{p}/payments", json={"kind": kind, "title": "x", "amount_gross": "10", "occurred_on": today().isoformat(), **extra}, headers=auth_header(t))
    assert r.status_code == 201
    assert await reminders(db_session) == []


async def test_a_payment_in_full_takes_the_reminders_away_and_a_part_does_not(async_client, db_session):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    inv = await invoice(async_client, t, p, today() + timedelta(days=10))
    part = await async_client.post(f"/api/projects/{p}/payments", json={
        "kind": "PAYMENT", "title": "Część", "amount_gross": "400", "occurred_on": today().isoformat(), "settles_id": inv["id"]}, headers=auth_header(t))
    assert part.status_code == 201
    assert await states(db_session) == [(3, "PENDING"), (0, "PENDING")]  # 600 are still to be paid
    rest = await async_client.post(f"/api/projects/{p}/payments", json={
        "kind": "PAYMENT", "title": "Reszta", "amount_gross": "600", "occurred_on": today().isoformat(), "settles_id": inv["id"]}, headers=auth_header(t))
    assert rest.status_code == 201
    assert await states(db_session) == [(3, "CANCELLED"), (0, "CANCELLED")]
    # taking the last payment back (archiving it) brings the same reminders back
    archived = await async_client.post(f"/api/projects/{p}/payments/{rest.json()['id']}/archive", headers=auth_header(t))
    assert archived.status_code == 200
    assert await states(db_session) == [(3, "PENDING"), (0, "PENDING")]
    assert len(await reminders(db_session)) == 2  # the same rows, not new ones


async def test_archiving_the_invoice_cancels_and_restoring_it_brings_the_reminders_back(async_client, db_session):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    inv = await invoice(async_client, t, p, today() + timedelta(days=10))
    assert (await async_client.post(f"/api/projects/{p}/payments/{inv['id']}/archive", headers=auth_header(t))).status_code == 200
    assert await states(db_session) == [(3, "CANCELLED"), (0, "CANCELLED")]
    assert (await async_client.post(f"/api/projects/{p}/payments/{inv['id']}/restore", headers=auth_header(t))).status_code == 200
    assert await states(db_session) == [(3, "PENDING"), (0, "PENDING")]


async def test_moving_the_due_day_moves_the_reminders_and_clearing_it_cancels_them(async_client, db_session):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    inv = await invoice(async_client, t, p, today() + timedelta(days=10))
    moved = today() + timedelta(days=20)
    r = await async_client.patch(f"/api/projects/{p}/payments/{inv['id']}", json={"due_on": moved.isoformat()}, headers=auth_header(t))
    assert r.status_code == 200
    pending = [row for row in await reminders(db_session) if row.status == "PENDING"]
    assert sorted(row.lead_days for row in pending) == [0, 3] and {row.event_on for row in pending} == {moved}
    assert len([row for row in await reminders(db_session) if row.status == "CANCELLED"]) == 2  # the old day's
    cleared = await async_client.patch(f"/api/projects/{p}/payments/{inv['id']}", json={"due_on": None}, headers=auth_header(t))
    assert cleared.status_code == 200
    assert {row.status for row in await reminders(db_session)} == {"CANCELLED"}


async def test_a_change_of_the_amount_that_a_payment_now_covers_closes_it(async_client, db_session):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    inv = await invoice(async_client, t, p, today() + timedelta(days=10), amount="1000.00")
    await async_client.post(f"/api/projects/{p}/payments", json={
        "kind": "PAYMENT", "title": "Wpłata", "amount_gross": "400", "occurred_on": today().isoformat(), "settles_id": inv["id"]}, headers=auth_header(t))
    await async_client.patch(f"/api/projects/{p}/payments/{inv['id']}", json={"amount_gross": "400.00"}, headers=auth_header(t))
    assert {row.status for row in await reminders(db_session)} == {"CANCELLED"}  # the invoice is now paid in full


async def test_the_settings_switch_the_kind_and_it_is_listed_with_its_default(async_client, db_session):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    listed = (await async_client.get("/api/calendar/settings", headers=auth_header(t))).json()
    assert {"kind": "INVOICE_DUE", "default_push": True, "sends": True} in listed["kinds"]
    await invoice(async_client, t, p, today() + timedelta(days=10))
    off = await async_client.put("/api/calendar/settings", json={
        "timezone": "Europe/Warsaw", "enabled": True, "kind_overrides": {"INVOICE_DUE": False}, "quiet_from": "21:00", "quiet_to": "07:00",
        "digest_at": "08:00", "language": None}, headers=auth_header(t))
    assert off.status_code == 200, off.text
    assert {row.status for row in await reminders(db_session)} == {"CANCELLED"}
    agenda = (await async_client.get("/api/calendar", params={"start": today().isoformat(), "end": (today() + timedelta(days=30)).isoformat()}, headers=auth_header(t))).json()
    item = next(i for i in agenda["items"] if i["kind"] == "INVOICE_DUE")  # the calendar still shows the day, only the message is off
    assert item["sends"] is False and item["title_key"] == "calendar.event.invoice_due" and item["project_id"] == p


async def test_the_agenda_shows_the_due_day_with_the_name_of_the_invoice(async_client, db_session):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    await invoice(async_client, t, p, today() + timedelta(days=10), number="FV 7/2026")
    agenda = (await async_client.get("/api/calendar", params={"start": today().isoformat(), "end": (today() + timedelta(days=30)).isoformat()}, headers=auth_header(t))).json()
    [item] = [i for i in agenda["items"] if i["kind"] == "INVOICE_DUE"]
    assert (item["on"], item["params"], item["sends"]) == ((today() + timedelta(days=10)).isoformat(), {"what": "FV 7/2026"}, True)


async def test_an_archived_object_keeps_no_invoice_reminder_and_gets_them_back(async_client, db_session):
    t = await owner(async_client)
    p = await project_of(async_client, t)
    await invoice(async_client, t, p, today() + timedelta(days=10))
    assert (await async_client.post(f"/api/projects/{p}/archive", headers=auth_header(t))).status_code == 200
    assert {row.status for row in await reminders(db_session)} == {"CANCELLED"}
    assert (await async_client.post(f"/api/projects/{p}/restore", headers=auth_header(t))).status_code == 200
    assert await states(db_session) == [(3, "PENDING"), (0, "PENDING")]


async def test_a_fault_of_the_calendar_never_stops_a_record_from_being_saved(async_client, db_session, monkeypatch, caplog):
    t = await owner(async_client)
    p = await project_of(async_client, t)

    async def broken(self, owner_id, project_id, **kwargs):
        raise RuntimeError("calendar is down")

    monkeypatch.setattr(CalendarService, "reconcile_project", broken)
    made = await invoice(async_client, t, p, today() + timedelta(days=10))
    assert made["title"] == "Prace malarskie"
    assert await reminders(db_session) == []  # the periodic pass brings them later
    assert "calendar reconciliation after archiving failed" in caplog.text


async def test_the_periodic_pass_finds_an_invoice_the_hook_missed(async_client, db_session, monkeypatch):
    t = await owner(async_client)
    p = await project_of(async_client, t)

    async def broken(self, owner_id, project_id):
        return None

    monkeypatch.setattr(CalendarService, "reconcile_project_guarded", broken)
    await invoice(async_client, t, p, today() + timedelta(days=10))
    assert await reminders(db_session) == []
    monkeypatch.undo()
    owner_id = (await db_session.execute(select(Project.owner_id).where(Project.id == uuid.UUID(p)))).scalar_one()
    await CalendarService(db_session).reconcile_owner(owner_id)
    await db_session.commit()
    assert await states(db_session) == [(3, "PENDING"), (0, "PENDING")]


async def test_nothing_of_another_owner_is_reachable(async_client, db_session):
    t = await owner(async_client)
    other = await get_token(async_client, OTHER_USER)
    p = await project_of(async_client, t)
    await invoice(async_client, t, p, today() + timedelta(days=10))
    agenda = (await async_client.get("/api/calendar", params={"start": today().isoformat(), "end": (today() + timedelta(days=30)).isoformat()}, headers=auth_header(other))).json()
    assert [i for i in agenda["items"] if i["kind"] == "INVOICE_DUE"] == []
