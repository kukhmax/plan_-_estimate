"""Stage 18E.1 -- the calendar API: the agenda, the settings, the Remind button, the planned dates."""
import uuid
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select, update

from app.domain.services.project_service import ProjectService
from app.models.price_item import PriceItem
from app.models.reminder import Reminder
from tests.test_apply_template import _login
from tests.test_stage13h_bulk_execution import IP, NS, C, _ctx, _plan, _wall
from tests.test_stage13h_execution_api import OTHER_USER

WARSAW = ZoneInfo("Europe/Warsaw")


def today() -> date:
    return datetime.now(WARSAW).date()


async def scene(client, db, items=2, waits=None):
    c = await _ctx(client, db)
    c.wall = await _wall(c, "Ściana A", 0)
    await db.execute(update(PriceItem).where(PriceItem.id.in_([c.p1, c.p2, c.p3])).values(display_name="Gładź"))
    await db.commit()
    c.keys = await _plan(c, c.wall, [c.p1, c.p2, c.p3][:items], waits=waits if waits is not None else {0: 24})
    return c


async def get(c, url, **params):
    return await c.client.get(url, headers=c.headers, params=params)


async def put(c, url, body):
    return await c.client.put(url, headers=c.headers, json=body)


async def post(c, url, body):
    return await c.client.post(url, headers=c.headers, json=body)


# --- the agenda ----------------------------------------------------------------------------------------------------------------------


async def test_an_empty_agenda_names_today_and_the_period(async_client, db_session):
    c = await _ctx(async_client, db_session)
    body = (await get(c, "/api/calendar")).json()
    assert body["items"] == [] and body["works"] == [] and body["overdue"] == []
    assert date.fromisoformat(body["end"]) - date.fromisoformat(body["start"]) == timedelta(days=60) and body["start"] == body["today"]


async def test_the_agenda_needs_a_login_and_a_sane_period(async_client, db_session):
    c = await _ctx(async_client, db_session)
    assert (await async_client.get("/api/calendar")).status_code in (401, 403)
    for params in ({"start": "2026-10-10", "end": "2026-10-01"}, {"start": "2026-01-01", "end": "2028-01-01"}):
        resp = await get(c, "/api/calendar", **params)
        assert resp.status_code == 422 and resp.json()["detail"]["code"] == "PERIOD_INVALID"


async def test_a_completed_work_with_a_break_shows_its_start_and_its_end_with_the_names(async_client, db_session):
    c = await scene(async_client, db_session)
    await c.exec.transition(c.project, c.room, c.wall, c.user, c.keys[0], status=C, expected_status=NS)
    body = (await get(c, "/api/calendar", start=str(today() - timedelta(days=1)), end=str(today() + timedelta(days=3)))).json()
    by_kind = {i["kind"]: i for i in body["items"]}
    assert set(by_kind) == {"BREAK_START", "BREAK_END"}
    end = by_kind["BREAK_END"]
    assert end["source"] == "EVENT" and end["sends"] is True and by_kind["BREAK_START"]["sends"] is False
    assert end["title_key"] == "calendar.event.break_end" and end["params"] == {"hours": 24}
    assert (end["project_name"], end["surface_name"], end["occurrence_key"]) == ("Obiekt testowy", "Ściana A", str(c.keys[0])) and end["room_name"]
    assert (end["project_id"], end["room_id"], end["surface_id"]) == (str(c.project), str(c.room), str(c.wall))
    assert end["day"] in (str(today() + timedelta(days=1)), str(today()), str(today() + timedelta(days=2)))


# --- planned dates -------------------------------------------------------------------------------------------------------------------


async def test_a_planned_date_is_saved_listed_checked_and_cleared(async_client, db_session):
    c = await scene(async_client, db_session)
    monday = today() + timedelta(days=(7 - today().weekday()) % 7 or 7)
    url = f"/api/projects/{c.project}/schedule"
    assert (await get(c, url)).json() == {"planned": [], "warnings": [], "window_start": None, "window_end": None}
    r1 = await put(c, f"{url}/{c.keys[0]}", {"planned_date": str(monday)})
    r2 = await put(c, f"{url}/{c.keys[1]}", {"planned_date": str(monday), "note": "po schnięciu"})
    assert r1.status_code == 200 and r2.status_code == 200
    body = r2.json()
    assert {p["occurrence_key"]: p["planned_date"] for p in body["planned"]} == {str(c.keys[0]): str(monday), str(c.keys[1]): str(monday)}
    assert body["warnings"] == [{"occurrence_key": str(c.keys[1]), "code": "BEFORE_BREAK_END", "date": str(monday + timedelta(days=1))}]
    cleared = await put(c, f"{url}/{c.keys[1]}", {"planned_date": None})
    assert [p["occurrence_key"] for p in cleared.json()["planned"]] == [str(c.keys[0])] and cleared.json()["warnings"] == []


async def test_dated_works_and_overdue_works_are_told_apart(async_client, db_session):
    c = await scene(async_client, db_session)
    url = f"/api/projects/{c.project}/schedule"
    await put(c, f"{url}/{c.keys[0]}", {"planned_date": str(today() - timedelta(days=2))})
    await put(c, f"{url}/{c.keys[1]}", {"planned_date": str(today() + timedelta(days=3))})
    body = (await get(c, "/api/calendar")).json()
    assert [w["occurrence_key"] for w in body["overdue"]] == [str(c.keys[0])] and [w["occurrence_key"] for w in body["works"]] == [str(c.keys[1])]
    work = body["works"][0]
    assert (work["work_display_name"], work["surface_name"], work["status"], work["project_name"]) == ("Gładź", "Ściana A", "NOT_STARTED", "Obiekt testowy")
    assert (work["project_id"], work["room_id"], work["surface_id"]) == (str(c.project), str(c.room), str(c.wall))
    await c.exec.transition(c.project, c.room, c.wall, c.user, c.keys[0], status=C, expected_status=NS)
    assert (await get(c, "/api/calendar")).json()["overdue"] == []  # done is not overdue
    kinds = {i["kind"] for i in (await get(c, "/api/calendar")).json()["items"]}
    assert "WORK_END" in kinds and "WORK_START" not in kinds  # the first day of the room is in the past: not in the agenda from today


async def test_a_proposal_is_not_saved_until_it_is_accepted_and_is_accepted_whole(async_client, db_session):
    c = await scene(async_client, db_session)
    url = f"/api/projects/{c.project}/schedule"
    monday = today() + timedelta(days=(7 - today().weekday()) % 7 or 7)
    proposal = (await post(c, f"{url}/suggest", {"start": str(monday)})).json()
    assert {p["occurrence_key"]: p["planned_date"] for p in proposal} == {str(c.keys[0]): str(monday), str(c.keys[1]): str(monday + timedelta(days=1))}
    assert (await get(c, url)).json()["planned"] == []
    applied = await post(c, f"{url}/apply", {"dates": proposal})
    assert applied.status_code == 200 and len(applied.json()["planned"]) == 2 and applied.json()["warnings"] == []
    stranger = await post(c, f"{url}/apply", {"dates": [{"occurrence_key": str(uuid.uuid4()), "planned_date": str(monday)}]})
    assert stranger.status_code == 404
    assert len((await get(c, url)).json()["planned"]) == 2  # all or nothing


async def test_the_schedule_is_the_owners_own(async_client, db_session):
    c = await scene(async_client, db_session)
    stranger_headers, _ = await _login(async_client, db_session, OTHER_USER)
    base = f"/api/projects/{c.project}/schedule"
    for method, url, body in (("GET", base, None), ("PUT", f"{base}/{c.keys[0]}", {"planned_date": "2030-01-07"}),
                              ("POST", f"{base}/suggest", {"start": "2030-01-07"}), ("POST", f"{base}/apply", {"dates": []})):
        resp = await async_client.request(method, url, headers=stranger_headers, json=body)
        assert resp.status_code == 404, (method, url)
    assert (await async_client.get("/api/calendar", headers=stranger_headers, params={"project_id": str(c.project)})).status_code == 404
    assert (await async_client.get("/api/calendar", headers=stranger_headers)).json()["items"] == []


# --- the Remind button ---------------------------------------------------------------------------------------------------------------


async def test_in_an_hour_and_in_three_hours(async_client, db_session):
    c = await scene(async_client, db_session)
    for preset, hours in (("IN_1H", 1), ("IN_3H", 3)):
        before = datetime.now(UTC)
        resp = await post(c, "/api/calendar/reminders", {"preset": preset, "title": "Zadzwonić do klienta"})
        assert resp.status_code == 201, resp.text
        body = resp.json()
        send_at = datetime.fromisoformat(body["send_at"]).replace(tzinfo=UTC) if datetime.fromisoformat(body["send_at"]).tzinfo is None else datetime.fromisoformat(body["send_at"])
        assert abs((send_at - (before + timedelta(hours=hours))).total_seconds()) < 5
        assert (body["origin"], body["kind"], body["status"], body["title"], body["close_on_status"]) == ("USER", "USER", "PENDING", "Zadzwonić do klienta", None)


async def test_tomorrow_morning_is_eight_in_warsaw(async_client, db_session):
    c = await scene(async_client, db_session)
    body = (await post(c, "/api/calendar/reminders", {"preset": "TOMORROW", "title": "x"})).json()
    moment = datetime.fromisoformat(body["send_at"])
    moment = moment if moment.tzinfo else moment.replace(tzinfo=UTC)
    local = moment.astimezone(WARSAW)
    assert (local.date(), local.hour, local.minute) == (today() + timedelta(days=1), 8, 0)


async def test_a_reminder_about_a_work_takes_its_name_and_the_morning_of_its_day_and_closes_when_the_work_starts(async_client, db_session):
    c = await scene(async_client, db_session)
    day = today() + timedelta(days=10)
    await put(c, f"/api/projects/{c.project}/schedule/{c.keys[0]}", {"planned_date": str(day)})
    common = {"project_id": str(c.project), "occurrence_key": str(c.keys[0])}
    morning = (await post(c, "/api/calendar/reminders", {"preset": "WORK_DAY", **common})).json()
    before = (await post(c, "/api/calendar/reminders", {"preset": "DAY_BEFORE", **common})).json()
    for body, expected_day, hour in ((morning, day, 8), (before, day - timedelta(days=1), 18)):
        moment = datetime.fromisoformat(body["send_at"])
        local = (moment if moment.tzinfo else moment.replace(tzinfo=UTC)).astimezone(WARSAW)
        assert (local.date(), local.hour) == (expected_day, hour)
        assert body["close_on_status"] == "IN_PROGRESS" and body["title"] == "Gładź — Ściana A"
        assert (body["room_id"], body["surface_id"], body["occurrence_key"]) == (str(c.room), str(c.wall), str(c.keys[0]))
    await c.exec.transition(c.project, c.room, c.wall, c.user, c.keys[0], status=IP, expected_status=NS)
    rows = (await db_session.execute(select(Reminder).execution_options(populate_existing=True).where(Reminder.origin == "USER"))).scalars().all()
    assert {r.status for r in rows} == {"DONE"}


async def test_the_end_of_a_break_needs_a_completed_work_with_a_break(async_client, db_session):
    c = await scene(async_client, db_session)
    common = {"project_id": str(c.project), "occurrence_key": str(c.keys[0])}
    refused = await post(c, "/api/calendar/reminders", {"preset": "BREAK_END", **common})
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "NO_BREAK"
    await c.exec.transition(c.project, c.room, c.wall, c.user, c.keys[0], status=C, expected_status=NS)
    ok = await post(c, "/api/calendar/reminders", {"preset": "BREAK_END", **common})
    assert ok.status_code == 201 and ok.json()["close_on_status"] is None


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"preset": "WORK_DAY"}, "WORK_REQUIRED"),
        ({"preset": "CUSTOM", "title": "x"}, "CUSTOM_TIME_REQUIRED"),
        ({"preset": "CUSTOM", "title": "x", "send_at": "2020-01-01T10:00:00+00:00"}, "IN_THE_PAST"),
        ({"preset": "IN_1H"}, "TITLE_REQUIRED"),
        ({"preset": "IN_1H", "title": "x" * 121}, "TITLE_TOO_LONG"),
    ],
)
async def test_a_reminder_that_cannot_be_made_says_why(async_client, db_session, body, code):
    c = await scene(async_client, db_session)
    resp = await post(c, "/api/calendar/reminders", body)
    assert resp.status_code == 422 and resp.json()["detail"]["code"] == code


async def test_a_work_without_a_planned_date_cannot_be_reminded_by_its_day(async_client, db_session):
    c = await scene(async_client, db_session)
    resp = await post(c, "/api/calendar/reminders", {"preset": "WORK_DAY", "project_id": str(c.project), "occurrence_key": str(c.keys[0])})
    assert resp.status_code == 422 and resp.json()["detail"]["code"] == "NO_PLANNED_DATE"
    missing = await post(c, "/api/calendar/reminders", {"preset": "IN_1H", "title": "x", "project_id": str(c.project), "occurrence_key": str(uuid.uuid4())})
    assert missing.status_code == 404


async def test_an_unknown_preset_and_a_foreign_object_are_refused(async_client, db_session):
    c = await scene(async_client, db_session)
    assert (await post(c, "/api/calendar/reminders", {"preset": "NEXT_WEEK", "title": "x"})).status_code == 422
    stranger_headers, _ = await _login(async_client, db_session, OTHER_USER)
    resp = await async_client.post("/api/calendar/reminders", headers=stranger_headers, json={"preset": "IN_1H", "title": "x", "project_id": str(c.project)})
    assert resp.status_code == 404


async def test_an_own_reminder_is_in_the_agenda_listed_and_can_be_cancelled(async_client, db_session):
    c = await scene(async_client, db_session)
    made = (await post(c, "/api/calendar/reminders", {"preset": "TOMORROW", "title": "Odebrać klucze", "project_id": str(c.project)})).json()
    items = (await get(c, "/api/calendar")).json()["items"]
    [own] = [i for i in items if i["source"] == "REMINDER"]
    assert (own["reminder_id"], own["title"], own["project_name"], own["sends"], own["kind"]) == (made["id"], "Odebrać klucze", "Obiekt testowy", True, "USER")
    assert (await get(c, "/api/calendar/reminders")).json()["total"] == 1 and (await get(c, "/api/calendar/reminders", project_id=str(uuid.uuid4()))).json()["total"] == 0
    stranger_headers, _ = await _login(async_client, db_session, OTHER_USER)
    assert (await async_client.delete(f"/api/calendar/reminders/{made['id']}", headers=stranger_headers)).status_code == 404
    cancelled = await async_client.delete(f"/api/calendar/reminders/{made['id']}", headers=c.headers)
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELLED"
    assert (await get(c, "/api/calendar")).json()["items"] == [] and (await get(c, "/api/calendar/reminders")).json()["total"] == 0


# --- the settings --------------------------------------------------------------------------------------------------------------------


async def test_the_settings_start_as_the_defaults_and_are_saved(async_client, db_session):
    c = await _ctx(async_client, db_session)
    body = (await get(c, "/api/calendar/settings")).json()
    assert (body["timezone"], body["enabled"], body["kind_overrides"], body["quiet_from"], body["quiet_to"], body["digest_at"], body["language"]) == (
        "Europe/Warsaw", True, {}, "21:00:00", "07:00:00", "08:00:00", None)
    kinds = {k["kind"]: k for k in body["kinds"]}
    assert "USER" not in kinds and kinds["BREAK_END"]["sends"] is True and kinds["PAYMENT_TERM"]["sends"] is False and kinds["PAYMENT_TERM"]["default_push"] is False
    assert "Europe/Warsaw" in body["timezones"]
    saved = await put(c, "/api/calendar/settings", {"timezone": "Europe/Berlin", "kind_overrides": {"PAYMENT_TERM": True, "BREAK_END": False}, "quiet_from": "22:00", "quiet_to": "06:30", "digest_at": "09:00", "language": "ru"})
    assert saved.status_code == 200, saved.text
    after = saved.json()
    assert (after["timezone"], after["language"], after["digest_at"]) == ("Europe/Berlin", "ru", "09:00:00")
    kinds = {k["kind"]: k for k in after["kinds"]}
    assert kinds["PAYMENT_TERM"]["sends"] is True and kinds["BREAK_END"]["sends"] is False
    assert (await get(c, "/api/calendar/settings")).json()["timezone"] == "Europe/Berlin"


@pytest.mark.parametrize(
    ("change", "code"),
    [({"timezone": "Mars/Olympus"}, "TIMEZONE_UNKNOWN"), ({"language": "de"}, "LANGUAGE_UNKNOWN"), ({"kind_overrides": {"NOPE": True}}, "KIND_UNKNOWN"),
     ({"digest_at": "22:00"}, "DIGEST_IN_QUIET_HOURS")],
)
async def test_wrong_settings_say_why(async_client, db_session, change, code):
    c = await _ctx(async_client, db_session)
    resp = await put(c, "/api/calendar/settings", {"timezone": "Europe/Warsaw", **change})
    assert resp.status_code == 422 and resp.json()["detail"]["code"] == code
    assert (await put(c, "/api/calendar/settings", {"timezone": "Europe/Warsaw", "surprise": 1})).status_code == 422


async def test_a_work_planned_for_today_is_not_yet_overdue(async_client, db_session):
    c = await scene(async_client, db_session)
    await put(c, f"/api/projects/{c.project}/schedule/{c.keys[0]}", {"planned_date": str(today())})
    body = (await get(c, "/api/calendar")).json()
    assert [w["occurrence_key"] for w in body["works"]] == [str(c.keys[0])] and body["overdue"] == []


async def test_an_archived_object_leaves_the_agenda_with_its_works_and_reminders(async_client, db_session):
    c = await scene(async_client, db_session)
    await put(c, f"/api/projects/{c.project}/schedule/{c.keys[0]}", {"planned_date": str(today() + timedelta(days=2))})
    await post(c, "/api/calendar/reminders", {"preset": "TOMORROW", "title": "x", "project_id": str(c.project)})
    assert len((await get(c, "/api/calendar")).json()["items"]) >= 2
    await ProjectService(db_session).archive_project(c.project, c.user)
    body = (await get(c, "/api/calendar")).json()
    assert body["items"] == [] and body["works"] == [] and body["overdue"] == []
    assert (await get(c, "/api/calendar/reminders")).json()["total"] == 0


async def test_another_owners_reminders_are_never_in_my_agenda_or_list(async_client, db_session):
    c = await scene(async_client, db_session)
    await post(c, "/api/calendar/reminders", {"preset": "TOMORROW", "title": "mine"})
    stranger_headers, _ = await _login(async_client, db_session, OTHER_USER)
    made = await async_client.post("/api/calendar/reminders", headers=stranger_headers, json={"preset": "TOMORROW", "title": "theirs"})
    assert made.status_code == 201
    mine = [i["title"] for i in (await get(c, "/api/calendar")).json()["items"]]
    theirs = [i["title"] for i in (await async_client.get("/api/calendar", headers=stranger_headers)).json()["items"]]
    assert mine == ["mine"] and theirs == ["theirs"]
    assert [r["title"] for r in (await get(c, "/api/calendar/reminders")).json()["items"]] == ["mine"]


async def test_a_custom_time_is_a_day_and_an_hour_in_the_owners_zone_or_an_instant(async_client, db_session):
    c = await scene(async_client, db_session)
    day = today() + timedelta(days=5)
    made = (await post(c, "/api/calendar/reminders", {"preset": "CUSTOM", "title": "x", "local_date": str(day), "local_time": "14:30"})).json()
    moment = datetime.fromisoformat(made["send_at"])
    local = (moment if moment.tzinfo else moment.replace(tzinfo=UTC)).astimezone(WARSAW)
    assert (local.date(), local.hour, local.minute) == (day, 14, 30)
    await put(c, "/api/calendar/settings", {"timezone": "Europe/London"})
    london = (await post(c, "/api/calendar/reminders", {"preset": "CUSTOM", "title": "y", "local_date": str(day), "local_time": "14:30"})).json()
    moment = datetime.fromisoformat(london["send_at"])
    assert (moment if moment.tzinfo else moment.replace(tzinfo=UTC)).astimezone(ZoneInfo("Europe/London")).hour == 14  # the zone of the settings, not of the server
    instant = (datetime.now(UTC) + timedelta(hours=9)).replace(microsecond=0)
    ok = await post(c, "/api/calendar/reminders", {"preset": "CUSTOM", "title": "z", "send_at": instant.isoformat()})
    assert ok.status_code == 201
    half = await post(c, "/api/calendar/reminders", {"preset": "CUSTOM", "title": "w", "local_date": str(day)})
    assert half.status_code == 422 and half.json()["detail"]["code"] == "CUSTOM_TIME_REQUIRED"
