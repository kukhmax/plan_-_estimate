"""Stage 18D -- the rules of the delivery loop (pure), the texts, and what goes into one message."""
import json
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest

from app.domain.calendar import events as ev
from app.domain.calendar import messages as msg
from app.domain.calendar import policy
from app.domain.calendar.messages import (
    CalendarTextsError,
    ReminderView,
    compose_messages,
    load_texts,
)
from app.models.work_execution import WorkExecutionStatus as S

P, P2, ROOM, ROOM2 = (uuid.uuid4() for _ in range(4))
NOW = datetime(2026, 10, 12, 6, 0, tzinfo=UTC)  # 08:00 in Warsaw
URL = "https://plan-estimate.pl"


def at(minutes=0):
    return NOW - timedelta(minutes=minutes)


# --- the rules of the loop -----------------------------------------------------------------------------------------------------------


def test_lateness_has_three_bands():
    assert policy.lateness(NOW, NOW) == policy.ON_TIME and policy.lateness(NOW + timedelta(minutes=5), NOW) == policy.ON_TIME
    assert policy.lateness(at(15), NOW) == policy.ON_TIME and policy.lateness(at(16), NOW) == policy.LATE
    assert policy.lateness(at(24 * 60), NOW) == policy.LATE and policy.lateness(at(24 * 60 + 1), NOW) == policy.MISSED


def test_the_retry_delays_are_one_five_fifteen_fifteen_and_then_the_end():
    assert [policy.retry_delay(n) for n in range(1, 6)] == [timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=15), timedelta(minutes=15), None]
    assert policy.retry_delay(0) == timedelta(minutes=1) and policy.MAX_ATTEMPTS == 5


def test_a_slow_down_answer_waits_at_least_as_long_as_asked():
    assert policy.retry_delay(1, 90) == timedelta(seconds=90)  # longer than the backoff
    assert policy.retry_delay(2, 10) == timedelta(minutes=5)  # shorter: the backoff stays
    assert policy.retry_delay(5, 90) is None


# --- the texts -----------------------------------------------------------------------------------------------------------------------


def all_title_keys() -> set[str]:
    """Every title key the event builders can produce, found by running them on data that makes each of them produce."""
    day, instant = date(2026, 11, 20), datetime(2026, 10, 12, 8, 0, tzinfo=UTC)
    built = (
        ev.break_events([ev.BreakInput(P, uuid.uuid4(), S.COMPLETED, instant, 24)])
        + ev.schedule_events([ev.PlannedWork(P, uuid.uuid4(), day, ROOM), ev.PlannedWork(P, uuid.uuid4(), day + timedelta(days=3), ROOM)])
        + ev.contract_events(ev.ContractDates(P, day, day, day, 30, consumer=True))
        + ev.acceptance_events(ev.AcceptanceDates(P, 3, day, day))
        + ev.concealed_events([ev.ConcealedDates(P, "a", day)])
        + ev.downtime_events(ev.DowntimeDates(P, day, day))
        + ev.adjacent_events([ev.AdjacentPeriod(P, "x", day, day)])
    )
    return {event.title_key for event in built}


def test_every_event_the_application_makes_has_its_words_in_both_languages_and_there_is_no_orphan():
    texts = load_texts()
    assert all_title_keys() == set(texts.titles)  # nothing missing, nothing left over
    for entry in (*texts.titles.values(), *texts.frame.values()):
        assert entry["pl"].strip() and entry["ru"].strip() and "{" not in entry["pl"].replace("{n}", "") and "{" not in entry["ru"].replace("{n}", "")


def test_the_placeholders_are_the_same_in_both_languages():
    frame = load_texts().frame
    for key in ("in_days", "more", "break_hours", "surfaces"):
        assert "{n}" in frame[key]["pl"] and "{n}" in frame[key]["ru"]


def test_a_missing_language_or_key_stops_the_start(tmp_path, monkeypatch):
    good = json.loads(msg.TEXTS_FILE.read_text(encoding="utf-8"))
    for broken in (
        {**good, "titles": {**good["titles"], "calendar.event.break_end": {"pl": "x"}}},
        {**good, "frame": {k: v for k, v in good["frame"].items() if k != "late"}},
        {**good, "frame": {**good["frame"], "late": {"pl": "x", "ru": "  "}}},
    ):
        path = tmp_path / "texts.json"
        path.write_text(json.dumps(broken), encoding="utf-8")
        monkeypatch.setattr(msg, "TEXTS_FILE", path)
        load_texts.cache_clear()
        with pytest.raises(CalendarTextsError):
            load_texts()
    monkeypatch.undo()
    load_texts.cache_clear()
    assert load_texts().titles  # and the real file is fine again


# --- what goes into a message ----------------------------------------------------------------------------------------------------------


def view(kind="BREAK_END", *, origin="AUTO", title_key=None, title=None, ref="", on=None, lead=0, send_at=None, project=P, project_name="Kowalski, ul. Kwiatowa 1",
         room=ROOM, room_name="Łazienka", surface="Ściana A", params=None):
    title_key = title_key or f"calendar.event.{kind.lower()}"
    return ReminderView(uuid.uuid4(), origin, kind, ref, title, None if origin == "USER" else title_key, params if params is not None else {},
                        on, lead, send_at or NOW, project, project_name, room, room_name, surface)


def one(v, lang="pl", base=URL, now=NOW):
    [m] = compose_messages([v], lang=lang, now=now, base_url=base)
    return m


def test_a_break_end_message_says_what_ended_where_and_opens_the_object():
    m = one(view(params={"hours": 24}))
    assert m.text.splitlines() == ["Koniec przerwy technologicznej — można kontynuować prace", "Kowalski, ul. Kwiatowa 1 · Łazienka · Ściana A", "przerwa: 24 h"]
    assert m.open_url == f"{URL}?open=project:{P}" and m.button == "Otwórz"


def test_the_same_in_russian_and_an_unknown_language_is_polish():
    m = one(view(params={"hours": 24}), "ru")
    assert m.text.splitlines()[0] == "Технологический перерыв закончился — можно продолжать работы" and m.text.splitlines()[2] == "перерыв: 24 ч" and m.button == "Открыть"
    assert one(view(), "de").text.startswith("Koniec przerwy")


def test_an_own_reminder_carries_the_owners_words_and_without_an_object_opens_the_calendar():
    m = one(view("USER", origin="USER", title="Zadzwonić do klienta", project=None, project_name=None, room=None, room_name=None, surface=None))
    assert m.text == "🔔 Zadzwonić do klienta" and m.open_url == f"{URL}?open=calendar"
    with_project = one(view("USER", origin="USER", title="Odebrać klucze", room=None, room_name=None, surface=None))
    assert with_project.text == "🔔 Odebrać klucze\nKowalski, ul. Kwiatowa 1" and with_project.open_url == f"{URL}?open=project:{P}"


def test_no_address_no_button_address():
    assert one(view(), base="").open_url is None


def test_a_message_that_is_late_says_so_in_each_language_and_one_on_time_does_not():
    assert "(z opóźnieniem)" in one(view(send_at=at(30))).text.splitlines()[0]
    assert "(с опозданием)" in one(view(send_at=at(30)), "ru").text.splitlines()[0]
    assert "opóźnieniem" not in one(view(send_at=at(10))).text


def test_what_a_day_announces_goes_into_one_digest_with_today_first():
    items = [
        view("DELIVERY_DEADLINE", on=date(2026, 10, 12), lead=0),
        view("DELIVERY_DEADLINE", on=date(2026, 10, 15), lead=3, project=P2, project_name="Nowak"),
        view("ACCEPTANCE_TERM", ref="appearance", title_key="calendar.event.acceptance_term.appearance", on=date(2026, 10, 12)),
    ]
    messages = compose_messages(items, lang="pl", now=NOW, base_url=URL)
    assert len(messages) == 1 and set(messages[0].reminder_ids) == {i.id for i in items}
    lines = messages[0].text.splitlines()
    assert lines[:3] == ["📅 Plan na dziś", "12.10.2026", ""]
    assert lines[3:] == [  # by days ahead, then the object, then the kind: the same order whatever the order they were taken in
        "• Kowalski, ul. Kwiatowa 1 — Upływa termin stawienia się Zamawiającego do odbioru (§ 14), dziś",
        "• Kowalski, ul. Kwiatowa 1 — Termin oddania prac, dziś",
        "• Nowak — Termin oddania prac, za 3 dn. (15.10.2026)",
    ]
    assert messages[0].open_url == f"{URL}?open=calendar"  # two objects: the calendar


def test_a_digest_about_one_object_opens_that_object_and_a_late_digest_is_not_marked_late():
    [m] = compose_messages([view("DELIVERY_DEADLINE", on=date(2026, 10, 12), send_at=at(120))], lang="ru", now=NOW, base_url=URL)
    assert m.open_url == f"{URL}?open=project:{P}" and "опозданием" not in m.text and m.text.startswith("📅 План на сегодня")


def test_a_long_digest_is_cut_and_counts_the_rest():
    items = [view("PAYMENT_TERM", ref="advance", title_key="calendar.event.payment_term.advance", on=date(2026, 10, 12), project_name=f"Obiekt {n:02d}") for n in range(30)]
    [m] = compose_messages(items, lang="pl", now=NOW, base_url=URL)
    assert m.text.count("•") == msg.DIGEST_LIMIT and m.text.splitlines()[-1] == "… i jeszcze 5" and len(m.reminder_ids) == 30


def test_the_ends_of_breaks_of_one_room_go_together_and_other_rooms_and_the_starts_stay_apart():
    a, b = view(surface="Ściana A"), view(surface="Ściana B")
    other_room = view(room=ROOM2, room_name="Kuchnia", surface="Ściana C")
    start = view("BREAK_START")
    messages = compose_messages([a, b, other_room, start], lang="pl", now=NOW, base_url=URL)
    assert len(messages) == 3
    merged = next(m for m in messages if len(m.reminder_ids) == 2)
    assert set(merged.reminder_ids) == {a.id, b.id}
    assert merged.text.splitlines() == ["Koniec przerwy technologicznej — można kontynuować prace", "Kowalski, ul. Kwiatowa 1 · Łazienka", "powierzchnie: 2: Ściana A, Ściana B"]
    assert {m.reminder_ids for m in messages} == {merged.reminder_ids, (other_room.id,), (start.id,)}


def test_every_reminder_lands_in_exactly_one_message():
    items = [view("DELIVERY_DEADLINE", on=date(2026, 10, 12)), view(), view(surface="B"), view(room=ROOM2), view("BREAK_START"),
             view("USER", origin="USER", title="x", project=None, project_name=None, room=None, room_name=None, surface=None),
             view("WORK_START", on=date(2026, 10, 12))]
    messages = compose_messages(items, lang="ru", now=NOW, base_url=URL)
    ids = [rid for m in messages for rid in m.reminder_ids]
    assert sorted(map(str, ids)) == sorted(str(i.id) for i in items) and len(ids) == len(set(ids))
    assert all("{" not in m.text for m in messages)
