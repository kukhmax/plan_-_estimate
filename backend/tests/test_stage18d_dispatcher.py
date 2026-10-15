"""Stage 18D -- the loop that sends the queue: what is taken, what is sent, what happens when Telegram says no."""
import asyncio
import logging
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select

from app.core.config import Settings
from app.domain.documents.delivery import DisabledMessageSender
from app.domain.exceptions import (
    MessageChatUnavailableError,
    MessageRejectedError,
    MessageUnavailableError,
)
from app.domain.services import calendar_dispatcher as cd
from app.domain.services.calendar_dispatcher import (
    CalendarDispatcher,
    run_loop,
    start_dispatcher,
)
from app.domain.services.calendar_service import CalendarService
from app.models.project import Project
from app.models.reminder import Reminder
from app.models.room import Room
from app.models.surface import Surface, SurfaceType
from app.models.user import User
from tests.conftest import TestingSessionLocal

# 10:00 in Warsaw (CEST), a weekday: outside the quiet hours
NOW = datetime(2026, 10, 12, 8, 0, tzinfo=UTC)
URL = "https://plan-estimate.pl"


class FakeSender:
    def __init__(self, *outcomes):
        self.calls: list[tuple[int, str, str | None, str]] = []
        self.outcomes = list(outcomes)  # per call: None = accepted, or an exception to raise

    async def send_message(self, chat_id, text, *, open_url=None, button_text=""):
        self.calls.append((chat_id, text, open_url, button_text))
        outcome = self.outcomes.pop(0) if self.outcomes else None
        if outcome is not None:
            raise outcome


def dispatcher(sender, **kw):
    sleeps: list[float] = []

    async def sleep(seconds):
        sleeps.append(seconds)

    d = CalendarDispatcher(TestingSessionLocal, sender, web_app_url=URL, sleep=sleep, **kw)
    d.sleeps = sleeps
    return d


async def owner(db, telegram_id=900001, language="pl"):
    user = User(telegram_user_id=telegram_id, first_name="Test", language_code=language)
    db.add(user)
    await db.flush()
    project = Project(owner_id=user.id, name="Kowalski", address="ul. 1", city="Kraków", postal_code="30-001")
    db.add(project)
    await db.flush()
    room = Room(project_id=project.id, name="Łazienka")
    db.add(room)
    await db.flush()
    surface = Surface(room_id=room.id, name="Ściana A", surface_type=SurfaceType.WALL)
    db.add(surface)
    await db.commit()
    return user, project, room, surface


_n = iter(range(10**6))


def reminder(user, project, room, surface, *, origin="AUTO", kind="BREAK_END", send_at=NOW - timedelta(minutes=1), status="PENDING", on=None, lead=0, title=None, **kw):
    return Reminder(
        owner_id=user.id, project_id=project.id if project else None, room_id=room.id if room else None, surface_id=surface.id if surface else None,
        origin=origin, kind=kind, ref=kw.pop("ref", ""), title=title if origin == "USER" else None,
        title_key=None if origin == "USER" else kw.pop("title_key", f"calendar.event.{kind.lower()}"), params=kw.pop("params", {"hours": 24}),
        event_on=on, lead_days=lead, send_at=send_at, tz="Europe/Warsaw", status=status, dedupe_key=f"k{next(_n)}", **kw,
    )


async def rows(db) -> list[Reminder]:
    return list((await db.execute(select(Reminder).execution_options(populate_existing=True).order_by(Reminder.dedupe_key))).scalars())


def utc(value):
    return value if value.tzinfo else value.replace(tzinfo=UTC)


# --- the ordinary pass ---------------------------------------------------------------------------------------------------------------


async def test_a_due_reminder_is_sent_once_to_the_chat_of_its_owner(db_session):
    u, p, r, s = await owner(db_session)
    db_session.add(reminder(u, p, r, s))
    await db_session.commit()
    sender = FakeSender()
    d = dispatcher(sender)
    report = await d.tick(NOW)
    assert (report.claimed, report.messages, report.sent) == (1, 1, 1)
    [(chat, text, url, button)] = sender.calls
    assert chat == 900001 and text.startswith("Koniec przerwy technologicznej") and url == f"{URL}?open=project:{p.id}" and button == "Otwórz"
    [row] = await rows(db_session)
    assert row.status == "SENT" and utc(row.sent_at) == NOW and row.locked_at is None and row.error_code is None and row.attempts == 1
    again = await d.tick(NOW + timedelta(minutes=1))
    assert again.claimed == 0 and len(sender.calls) == 1  # once


async def test_what_is_not_yet_due_waits(db_session):
    u, p, r, s = await owner(db_session)
    db_session.add(reminder(u, p, r, s, send_at=NOW + timedelta(minutes=5)))
    await db_session.commit()
    sender = FakeSender()
    assert (await dispatcher(sender).tick(NOW)).claimed == 0 and sender.calls == []
    assert [x.status for x in await rows(db_session)] == ["PENDING"]


async def test_the_language_is_the_owners_choice_or_that_of_their_telegram(db_session):
    ru, p, r, s = await owner(db_session, 900002, "ru")
    pl_chosen, p2, r2, s2 = await owner(db_session, 900003, "ru")
    await CalendarService(db_session).save_settings(
        pl_chosen.id, timezone="Europe/Warsaw", enabled=True, kind_overrides={}, quiet_from=time(21, 0), quiet_to=time(7, 0), digest_at=time(8, 0),
        language="pl", now=NOW,
    )
    db_session.add_all([reminder(ru, p, r, s), reminder(pl_chosen, p2, r2, s2)])  # after the settings: a reconciliation drops a row with no source
    await db_session.commit()
    sender = FakeSender()
    await dispatcher(sender).tick(NOW)
    texts = {chat: text for chat, text, *_ in sender.calls}
    assert texts[900002].startswith("Технологический перерыв закончился") and texts[900003].startswith("Koniec przerwy")


async def test_what_a_day_announces_goes_in_one_digest_and_the_ends_of_one_room_in_one_message(db_session):
    u, p, r, s = await owner(db_session)
    s2 = Surface(room_id=r.id, name="Ściana B", surface_type=SurfaceType.WALL)
    db_session.add(s2)
    await db_session.flush()
    db_session.add_all([
        reminder(u, p, None, None, kind="DELIVERY_DEADLINE", on=date(2026, 10, 15), lead=3, params={}),
        reminder(u, p, None, None, kind="OBJECT_START", on=date(2026, 10, 12), params={}),
        reminder(u, p, r, s), reminder(u, p, r, s2),
    ])
    await db_session.commit()
    sender = FakeSender()
    report = await dispatcher(sender).tick(NOW)
    assert (report.messages, report.sent) == (2, 4)
    digest, breaks = sender.calls
    assert digest[1].startswith("📅 Plan na dziś") and digest[1].count("•") == 2 and "powierzchnie: 2: Ściana A, Ściana B" in breaks[1]
    assert {x.status for x in await rows(db_session)} == {"SENT"}


async def test_the_owners_are_kept_apart(db_session):
    a = await owner(db_session, 900011)
    b = await owner(db_session, 900012)
    db_session.add_all([reminder(*a), reminder(*b)])
    await db_session.commit()
    sender = FakeSender()
    await dispatcher(sender).tick(NOW)
    assert sorted(chat for chat, *_ in sender.calls) == [900011, 900012]


async def test_there_is_a_pause_between_two_messages_to_one_chat_and_none_before_the_first(db_session):
    u, p, *_ = await owner(db_session)
    db_session.add_all([reminder(u, p, None, None, origin="USER", kind="USER", title="a", params={}), reminder(u, p, None, None, origin="USER", kind="USER", title="b", params={})])
    await db_session.commit()
    d = dispatcher(FakeSender(), pause_seconds=1.1)
    await d.tick(NOW)
    assert d.sleeps == [1.1]


# --- when Telegram says no -----------------------------------------------------------------------------------------------------------


async def test_a_blocked_bot_is_final_and_the_rest_of_that_chat_is_not_tried(db_session):
    u, p, *_ = await owner(db_session)
    db_session.add_all([reminder(u, p, None, None, origin="USER", kind="USER", title="a", params={}, send_at=NOW - timedelta(minutes=3)),
                        reminder(u, p, None, None, origin="USER", kind="USER", title="b", params={}, send_at=NOW - timedelta(minutes=2))])
    await db_session.commit()
    sender = FakeSender(MessageChatUnavailableError("blocked"))
    report = await dispatcher(sender).tick(NOW)
    assert len(sender.calls) == 1 and report.failed == 2
    assert {(x.status, x.error_code) for x in await rows(db_session)} == {("FAILED", "BOT_BLOCKED")}


async def test_a_refused_message_is_final(db_session):
    u, p, r, s = await owner(db_session)
    db_session.add(reminder(u, p, r, s))
    await db_session.commit()
    await dispatcher(FakeSender(MessageRejectedError("bad button"))).tick(NOW)
    [row] = await rows(db_session)
    assert (row.status, row.error_code) == ("FAILED", "REJECTED")


async def test_slow_down_waits_as_long_as_telegram_asked_and_the_untried_rest_waits_without_spending_an_attempt(db_session):
    u, p, *_ = await owner(db_session)
    db_session.add_all([reminder(u, p, None, None, origin="USER", kind="USER", title="a", params={}, send_at=NOW - timedelta(minutes=3)),
                        reminder(u, p, None, None, origin="USER", kind="USER", title="b", params={}, send_at=NOW - timedelta(minutes=2))])
    await db_session.commit()
    sender = FakeSender(MessageUnavailableError("slow", retry_after=120))
    report = await dispatcher(sender).tick(NOW)
    first, second = await rows(db_session)
    first, second = sorted([first, second], key=lambda x: x.title)
    assert len(sender.calls) == 1 and report.retried == 1
    assert (first.status, first.attempts, first.error_code, utc(first.send_at)) == ("PENDING", 1, "UNAVAILABLE", NOW + timedelta(seconds=120))
    assert (second.status, second.attempts, utc(second.send_at)) == ("PENDING", 0, NOW + timedelta(seconds=120))  # the flood control is the bot's: all wait
    later = FakeSender()
    await dispatcher(later).tick(NOW + timedelta(seconds=121))
    assert len(later.calls) == 2 and {x.status for x in await rows(db_session)} == {"SENT"}


async def test_five_failures_give_up_with_the_backoff_one_five_fifteen_fifteen_minutes(db_session):
    u, p, r, s = await owner(db_session)
    db_session.add(reminder(u, p, r, s))
    await db_session.commit()
    sender = FakeSender(*[MessageUnavailableError("down") for _ in range(5)])
    d = dispatcher(sender)
    clock, waits = NOW, []
    for _ in range(5):
        await d.tick(clock)
        [row] = await rows(db_session)
        if row.status != "PENDING":
            break
        waits.append(utc(row.send_at) - clock)
        clock = utc(row.send_at)
    [row] = await rows(db_session)
    assert waits == [timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=15), timedelta(minutes=15)]
    assert (row.status, row.error_code, row.attempts) == ("FAILED", "GIVE_UP", 5) and len(sender.calls) == 5


async def test_a_fault_in_one_owners_delivery_is_logged_and_does_not_stop_the_others(db_session, caplog):
    a = await owner(db_session, 900021)
    b = await owner(db_session, 900022)
    db_session.add_all([reminder(*a), reminder(*b)])
    await db_session.commit()

    class Broken(FakeSender):
        async def send_message(self, chat_id, text, **kw):
            if chat_id == 900021:
                raise RuntimeError("a bug")
            await super().send_message(chat_id, text, **kw)

    sender = Broken()
    with caplog.at_level(logging.ERROR):
        report = await dispatcher(sender).tick(NOW)
    assert report.errors == ["RuntimeError"] and [chat for chat, *_ in sender.calls] == [900022]
    status = {x.owner_id: x.status for x in await rows(db_session)}
    assert status[a[0].id] == "PENDING" and status[b[0].id] == "SENT" and "calendar delivery failed" in caplog.text


# --- when a reminder is not sent, or sent late ------------------------------------------------------------------------------------------


async def test_a_stale_taken_reminder_goes_back_and_one_out_of_attempts_is_given_up(db_session):
    u, p, r, s = await owner(db_session)
    db_session.add_all([reminder(u, p, r, s, status="SENDING", locked_at=NOW - timedelta(minutes=6), attempts=1),
                        reminder(u, p, None, None, origin="USER", kind="USER", title="x", params={}, status="SENDING", locked_at=NOW - timedelta(minutes=6), attempts=5),
                        reminder(u, p, None, None, origin="USER", kind="USER", title="y", params={}, status="SENDING", locked_at=NOW - timedelta(minutes=1), attempts=1)])
    await db_session.commit()
    sender = FakeSender()
    report = await dispatcher(sender).tick(NOW)
    assert report.recovered == 2 and len(sender.calls) == 1  # the first came back and went; the third is still being sent by someone
    by_title = {x.title: x for x in await rows(db_session)}
    assert by_title[None].status == "SENT" and (by_title["x"].status, by_title["x"].error_code) == ("FAILED", "GIVE_UP") and by_title["y"].status == "SENDING"


async def test_older_than_a_day_is_missed_and_older_than_a_quarter_of_an_hour_says_it_is_late(db_session):
    u, p, *_ = await owner(db_session)
    db_session.add_all([reminder(u, p, None, None, origin="USER", kind="USER", title="old", params={}, send_at=NOW - timedelta(hours=25)),
                        reminder(u, p, None, None, origin="USER", kind="USER", title="late", params={}, send_at=NOW - timedelta(minutes=30))])
    await db_session.commit()
    sender = FakeSender()
    report = await dispatcher(sender).tick(NOW)
    assert report.missed == 1 and len(sender.calls) == 1 and sender.calls[0][1].startswith("🔔 late (z opóźnieniem)")
    assert {x.title: x.status for x in await rows(db_session)} == {"old": "MISSED", "late": "SENT"}


async def test_in_the_quiet_hours_an_automatic_reminder_waits_for_the_morning_and_the_owners_own_goes(db_session):
    u, p, r, s = await owner(db_session)
    night = datetime(2026, 10, 12, 23, 30, tzinfo=UTC)  # 01:30 in Warsaw
    db_session.add_all([reminder(u, p, r, s, send_at=night - timedelta(minutes=5)),
                        reminder(u, p, None, None, origin="USER", kind="USER", title="own", params={}, send_at=night - timedelta(minutes=5))])
    await db_session.commit()
    sender = FakeSender()
    report = await dispatcher(sender).tick(night)
    assert report.deferred_quiet == 1 and [c[1] for c in sender.calls] == ["🔔 own\nKowalski"]
    assert {x.kind: x.status for x in await rows(db_session)} == {"BREAK_END": "PENDING", "USER": "SENT"}
    morning = FakeSender()
    await dispatcher(morning).tick(night + timedelta(hours=6))  # 07:30 in Warsaw
    assert len(morning.calls) == 1 and "latest" not in morning.calls[0][1]


async def test_a_guard_against_a_flood_skips_the_reminders_over_the_daily_limit(db_session):
    u, p, *_ = await owner(db_session)
    db_session.add_all([reminder(u, p, None, None, origin="USER", kind="USER", title=str(n), params={}, send_at=NOW - timedelta(minutes=10 - n)) for n in range(5)])
    await db_session.commit()
    sender = FakeSender()
    report = await dispatcher(sender, max_per_day=3).tick(NOW)
    assert (report.sent, report.skipped) == (3, 2)
    assert sorted((x.status, x.error_code) for x in await rows(db_session)) == [("SENT", None)] * 3 + [("SKIPPED", "DAILY_LIMIT")] * 2
    assert len(sender.calls) == 3


# --- the periodic reconciliation, the loop, the start --------------------------------------------------------------------------------


async def test_the_periodic_reconciliation_covers_every_owner_and_one_fault_does_not_stop_it(db_session, monkeypatch, caplog):
    a = await owner(db_session, 900031)
    b = await owner(db_session, 900032)
    real = CalendarService.reconcile_owner
    seen = []

    async def reconcile(self, owner_id, **kw):
        seen.append(owner_id)
        if owner_id == a[0].id:
            raise RuntimeError("broken for one owner")
        return await real(self, owner_id, **kw)

    monkeypatch.setattr(CalendarService, "reconcile_owner", reconcile)
    with caplog.at_level(logging.ERROR):
        done = await dispatcher(FakeSender()).reconcile_all(NOW)
    assert sorted(map(str, seen)) == sorted(map(str, [a[0].id, b[0].id])) and done == 1 and "reconciliation failed" in caplog.text


async def test_the_loop_runs_passes_until_it_is_stopped_and_survives_a_fault():
    class Fake:
        def __init__(self):
            self.ticks = 0
            self.reconciles = 0

        async def reconcile_all(self):
            self.reconciles += 1

        async def tick(self):
            self.ticks += 1
            if self.ticks == 1:
                raise RuntimeError("the first pass fails")

    fake, stop = Fake(), asyncio.Event()
    task = asyncio.create_task(run_loop(fake, interval=0.01, reconcile_every=3600, stop=stop))
    await asyncio.sleep(0.15)
    stop.set()
    await asyncio.wait_for(task, timeout=2)
    assert fake.ticks >= 3 and fake.reconciles == 1  # went on after the fault; reconciled once, the next one is an hour away


def settings(**values) -> Settings:
    return Settings(_env_file=None, **values)


async def test_the_loop_is_off_by_default_and_not_started_without_a_token(caplog):
    assert start_dispatcher(settings(TELEGRAM_BOT_TOKEN="123:abc"), TestingSessionLocal, FakeSender()) is None  # a working sender, the flag is off
    assert start_dispatcher(settings(), TestingSessionLocal) is None
    with caplog.at_level(logging.ERROR):
        assert start_dispatcher(settings(CALENDAR_DISPATCHER_ENABLED=True, TELEGRAM_BOT_TOKEN=""), TestingSessionLocal) is None
    assert "no bot token" in caplog.text
    assert start_dispatcher(settings(CALENDAR_DISPATCHER_ENABLED=True), TestingSessionLocal, DisabledMessageSender()) is None


async def test_the_loop_starts_when_switched_on_and_stops_cleanly():
    running = start_dispatcher(settings(CALENDAR_DISPATCHER_ENABLED=True, CALENDAR_DISPATCH_INTERVAL_SECONDS=0.05), TestingSessionLocal, FakeSender())
    assert running is not None and not running.task.done()
    await running.stop()
    assert running.task.done() and not running.task.cancelled()


async def test_the_application_starts_and_stops_with_the_loop_off():
    from app.main import app

    async with app.router.lifespan_context(app):
        pass
    assert cd.logger  # imported and wired; nothing was started


def test_the_production_templates_carry_the_calendar_settings_with_the_loop_off():
    from pathlib import Path

    import yaml

    root = Path(__file__).resolve().parents[2]
    env = yaml.safe_load((root / "docker-compose.prod.yml").read_text(encoding="utf-8"))["services"]["backend"]["environment"]
    calendar = {name: value for name, value in env.items() if name.startswith("CALENDAR_")}
    assert calendar["CALENDAR_DISPATCHER_ENABLED"] == "${CALENDAR_DISPATCHER_ENABLED:-false}"  # off unless the owner says so
    assert calendar["CALENDAR_WEB_APP_URL"].startswith("${CALENDAR_WEB_APP_URL:-https://")  # the button opens the Mini App over https
    assert all(name in Settings.model_fields for name in calendar)  # no name the application would silently ignore
    example = (root / ".env.production.example").read_text(encoding="utf-8")
    assert "\nCALENDAR_DISPATCHER_ENABLED=false\n" in example
