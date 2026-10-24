"""V2-7 -- Ukrainian and English: the messages of the calendar and the language of an owner who did not choose one."""
import json
import re
from datetime import UTC, datetime

import pytest

from app.domain.calendar import messages
from app.domain.calendar.messages import (
    LANGUAGES,
    TEXTS_FILE,
    language_of_telegram,
    load_texts,
)
from tests.test_stage13h_bulk_execution import _ctx
from tests.test_stage18d_dispatcher import NOW, FakeSender, dispatcher, owner, reminder
from tests.test_stage18e_api import get, put

FOUR = ("pl", "ru", "uk", "en")


def test_the_calendar_speaks_four_languages():
    assert LANGUAGES == FOUR


def test_every_text_exists_in_all_four_languages_with_the_same_places_to_fill():
    raw = json.loads(TEXTS_FILE.read_text(encoding="utf-8"))
    for group in ("titles", "frame"):
        for key, entry in raw[group].items():
            assert set(entry) >= set(FOUR), key
            marks = {lang: sorted(re.findall(r"\{[^}]*\}", entry[lang])) for lang in FOUR}
            assert len({tuple(m) for m in marks.values()}) == 1, (key, marks)
            assert all(entry[lang].strip() for lang in FOUR), key
    load_texts()  # the loader of the application accepts the file


def test_the_texts_are_in_the_language_asked_for():
    texts = load_texts()
    assert texts.frame["button"]["uk"] == "Відкрити" and texts.frame["button"]["en"] == "Open"
    assert texts.titles["calendar.event.break_end"]["en"].startswith("The technological pause is over")
    assert re.search("[іїєґ]", texts.titles["calendar.event.invoice_due"]["uk"] + texts.titles["calendar.event.work_start"]["uk"])
    assert not re.search("[а-яА-Я]", " ".join(entry["en"] for entry in texts.titles.values()))


@pytest.mark.parametrize(
    ("code", "expected"),
    [("uk", "uk"), ("uk-UA", "uk"), ("UK", "uk"), ("en", "en"), ("en-GB", "en"), ("en_US", "en"), ("ru", "ru"), ("pl", "pl"), ("de", "pl"), ("", "pl"), (None, "pl")],
)
def test_the_language_of_telegram_gives_the_language_of_the_messages(code, expected):
    assert language_of_telegram(code) == expected


async def test_an_owner_without_a_choice_gets_the_messages_in_the_language_of_their_telegram(db_session):
    uk, p1, r1, s1 = await owner(db_session, 910001, "uk")
    en, p2, r2, s2 = await owner(db_session, 910002, "en-GB")
    de, p3, r3, s3 = await owner(db_session, 910003, "de")
    db_session.add_all([reminder(uk, p1, r1, s1), reminder(en, p2, r2, s2), reminder(de, p3, r3, s3)])
    await db_session.commit()
    sender = FakeSender()
    await dispatcher(sender).tick(NOW)
    by_chat = {chat: (text, button) for chat, text, _url, button in sender.calls}
    assert by_chat[910001][0].startswith("Технологічна перерва закінчилася") and by_chat[910001][1] == "Відкрити"
    assert by_chat[910002][0].startswith("The technological pause is over") and by_chat[910002][1] == "Open"
    assert by_chat[910003][0].startswith("Koniec przerwy") and by_chat[910003][1] == "Otwórz"


def test_the_digest_and_the_late_marker_speak_the_chosen_language():
    from tests.test_stage18d_messages import at, one, view

    assert "(late)" in one(view(send_at=at(30)), "en").text.splitlines()[0]
    assert "(із запізненням)" in one(view(send_at=at(30)), "uk").text.splitlines()[0]
    assert "(late)" not in one(view(send_at=at(10)), "en").text
    assert messages.compose_messages([], lang="uk", now=datetime(2026, 10, 12, 8, 0, tzinfo=UTC)) == []


@pytest.mark.parametrize("language", ["uk", "en", "pl", "ru"])
async def test_the_settings_keep_every_language(async_client, db_session, language):
    c = await _ctx(async_client, db_session)
    saved = await put(c, "/api/calendar/settings", {"timezone": "Europe/Warsaw", "language": language})
    assert saved.status_code == 200, saved.text
    assert saved.json()["language"] == language
    assert (await get(c, "/api/calendar/settings")).json()["language"] == language


async def test_a_language_that_does_not_exist_is_still_refused(async_client, db_session):
    c = await _ctx(async_client, db_session)
    resp = await put(c, "/api/calendar/settings", {"timezone": "Europe/Warsaw", "language": "de"})
    assert resp.status_code == 422 and resp.json()["detail"]["code"] == "LANGUAGE_UNKNOWN"
