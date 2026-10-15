"""Stage 18E -- the times the presets of the Remind button mean (pure functions): all in the owner's zone, none in the screen."""
from datetime import UTC, date, datetime, time, timedelta

import pytest

from app.domain.calendar import agenda as ag
from app.domain.calendar.prefs import CalendarPrefs, parse_timezone

PREFS = CalendarPrefs()
NOW = datetime(2026, 10, 12, 8, 0, tzinfo=UTC)  # 10:00 in Warsaw (summer time)


def utc(*args):
    return datetime(*args, tzinfo=UTC)


def test_in_an_hour_and_in_three():
    assert ag.preset_instant(ag.PRESET_IN_1H, PREFS, NOW) == NOW + timedelta(hours=1)
    assert ag.preset_instant(ag.PRESET_IN_3H, PREFS, NOW) == NOW + timedelta(hours=3)


def test_tomorrow_is_the_digest_time_of_the_next_local_day_in_summer_and_in_winter():
    assert ag.preset_instant(ag.PRESET_TOMORROW, PREFS, NOW) == utc(2026, 10, 13, 6, 0)  # 08:00 CEST
    assert ag.preset_instant(ag.PRESET_TOMORROW, PREFS, utc(2026, 12, 10, 9, 0)) == utc(2026, 12, 11, 7, 0)  # 08:00 CET
    late = utc(2026, 10, 12, 22, 30)  # 00:30 on the 13th in Warsaw: "tomorrow" is the 14th
    assert ag.preset_instant(ag.PRESET_TOMORROW, PREFS, late) == utc(2026, 10, 14, 6, 0)
    assert ag.preset_instant(ag.PRESET_TOMORROW, CalendarPrefs(digest_at=time(9, 30)), NOW) == utc(2026, 10, 13, 7, 30)


def test_the_planned_day_is_announced_in_the_morning_and_the_evening_before_at_six():
    day = date(2026, 11, 20)
    assert ag.preset_instant(ag.PRESET_WORK_DAY, PREFS, NOW, planned_date=day) == utc(2026, 11, 20, 7, 0)
    assert ag.preset_instant(ag.PRESET_DAY_BEFORE, PREFS, NOW, planned_date=day) == utc(2026, 11, 19, 17, 0)
    zone = CalendarPrefs(tz=parse_timezone("Europe/London"), tz_name="Europe/London")
    assert ag.preset_instant(ag.PRESET_WORK_DAY, zone, NOW, planned_date=day) == utc(2026, 11, 20, 8, 0)


def test_the_end_of_a_break_is_the_real_one():
    ready = utc(2026, 10, 14, 10, 0)
    assert ag.preset_instant(ag.PRESET_BREAK_END, PREFS, NOW, ready_after=ready) == ready


def test_a_custom_time_must_be_an_aware_instant():
    when = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
    assert ag.preset_instant(ag.PRESET_CUSTOM, PREFS, NOW, custom=when) == when
    for bad in (None, datetime(2026, 10, 15, 12, 0)):  # noqa: DTZ001 - naive on purpose
        with pytest.raises(ag.PresetUnavailableError) as caught:
            ag.preset_instant(ag.PRESET_CUSTOM, PREFS, NOW, custom=bad)
        assert caught.value.code == "CUSTOM_TIME_REQUIRED"


@pytest.mark.parametrize(
    ("preset", "code"),
    [(ag.PRESET_BREAK_END, "NO_BREAK"), (ag.PRESET_WORK_DAY, "NO_PLANNED_DATE"), (ag.PRESET_DAY_BEFORE, "NO_PLANNED_DATE"), ("NEXT_WEEK", "UNKNOWN_PRESET")],
)
def test_a_preset_without_what_it_needs_says_what_is_missing(preset, code):
    with pytest.raises(ag.PresetUnavailableError) as caught:
        ag.preset_instant(preset, PREFS, NOW)
    assert caught.value.code == code


def test_which_presets_need_a_work_and_which_close_when_the_work_starts():
    assert set(ag.NEEDS_WORK) == {"BREAK_END", "WORK_DAY", "DAY_BEFORE"}
    assert ag.CLOSE_ON == {"WORK_DAY": "IN_PROGRESS", "DAY_BEFORE": "IN_PROGRESS"}
