"""Stage 18B -- working days and the public holidays of Poland (pure functions)."""
from datetime import date

import pytest

from app.domain.calendar.working_days import (
    add_working_days,
    easter_sunday,
    holiday_key,
    holidays,
    is_working_day,
    working_day_on_or_after,
)

EASTER = {
    2024: date(2024, 3, 31), 2025: date(2025, 4, 20), 2026: date(2026, 4, 5), 2027: date(2027, 3, 28), 2028: date(2028, 4, 16),
    2029: date(2029, 4, 1), 2030: date(2030, 4, 21), 2031: date(2031, 4, 13), 2032: date(2032, 3, 28),
}
CORPUS_CHRISTI = {
    2024: date(2024, 5, 30), 2025: date(2025, 6, 19), 2026: date(2026, 6, 4), 2027: date(2027, 5, 27), 2028: date(2028, 6, 15),
    2029: date(2029, 5, 31), 2030: date(2030, 6, 20), 2031: date(2031, 6, 12), 2032: date(2032, 5, 27),
}


@pytest.mark.parametrize("year", sorted(EASTER))
def test_easter_and_the_days_counted_from_it_for_nine_years(year):
    assert easter_sunday(year) == EASTER[year]
    assert easter_sunday(year).weekday() == 6  # always a Sunday
    assert holidays(year)[date.fromordinal(EASTER[year].toordinal() + 1)] == "EASTER_MONDAY"
    assert holidays(year)[CORPUS_CHRISTI[year]] == "CORPUS_CHRISTI"
    assert CORPUS_CHRISTI[year].weekday() == 3  # always a Thursday


def test_the_holidays_of_2026_are_exactly_these():
    expected = {
        date(2026, 1, 1): "NEW_YEAR", date(2026, 1, 6): "EPIPHANY", date(2026, 4, 5): "EASTER", date(2026, 4, 6): "EASTER_MONDAY",
        date(2026, 5, 1): "LABOUR_DAY", date(2026, 5, 3): "CONSTITUTION_DAY", date(2026, 5, 24): "PENTECOST",
        date(2026, 6, 4): "CORPUS_CHRISTI", date(2026, 8, 15): "ASSUMPTION", date(2026, 11, 1): "ALL_SAINTS",
        date(2026, 11, 11): "INDEPENDENCE_DAY", date(2026, 12, 24): "CHRISTMAS_EVE", date(2026, 12, 25): "CHRISTMAS",
        date(2026, 12, 26): "SECOND_DAY_OF_CHRISTMAS",
    }
    assert holidays(2026) == expected


def test_epiphany_is_a_day_off_since_2011_and_christmas_eve_since_2025():
    assert holiday_key(date(2010, 1, 6)) is None and holiday_key(date(2011, 1, 6)) == "EPIPHANY"
    assert holiday_key(date(2024, 12, 24)) is None and holiday_key(date(2025, 12, 24)) == "CHRISTMAS_EVE"


def test_a_working_day_is_monday_to_friday_without_the_holidays():
    assert is_working_day(date(2026, 10, 12))  # an ordinary Monday
    assert not is_working_day(date(2026, 10, 10)) and not is_working_day(date(2026, 10, 11))  # Saturday, Sunday
    assert not is_working_day(date(2026, 4, 6))  # Easter Monday
    assert not is_working_day(date(2026, 6, 4))  # Corpus Christi, a Thursday
    assert not is_working_day(date(2026, 11, 11))  # a Wednesday
    assert not is_working_day(date(2025, 12, 24))  # Christmas Eve, a Wednesday, a day off since 2025
    assert is_working_day(date(2024, 12, 24))  # and not yet in 2024


def test_a_working_day_on_or_after():
    assert working_day_on_or_after(date(2026, 10, 12)) == date(2026, 10, 12)
    assert working_day_on_or_after(date(2026, 10, 10)) == date(2026, 10, 12)  # Saturday -> Monday
    assert working_day_on_or_after(date(2026, 4, 4)) == date(2026, 4, 7)  # the Saturday before Easter -> after Easter Monday


def test_adding_working_days_skips_weekends_and_holidays():
    assert add_working_days(date(2026, 10, 9), 1) == date(2026, 10, 12)  # Friday + 1 = Monday
    assert add_working_days(date(2026, 10, 10), 1) == date(2026, 10, 12)  # from a Saturday
    assert add_working_days(date(2026, 4, 2), 1) == date(2026, 4, 3)  # Thursday before Easter -> Friday
    assert add_working_days(date(2026, 4, 2), 2) == date(2026, 4, 7)  # ... and the next one is after Easter Monday
    assert add_working_days(date(2026, 11, 9), 3) == date(2026, 11, 13)  # Tue 10, [Wed 11 holiday], Thu 12, Fri 13
    assert add_working_days(date(2025, 12, 22), 2) == date(2025, 12, 29)  # Tue 23, [24, 25, 26 holidays, weekend], Mon 29
    assert add_working_days(date(2026, 10, 10), 0) == date(2026, 10, 10)  # zero: the day itself


def test_a_negative_count_is_an_error():
    with pytest.raises(ValueError):
        add_working_days(date(2026, 10, 12), -1)


def test_the_result_of_adding_is_always_a_working_day_after_the_start():
    day = date(2025, 12, 1)
    for _ in range(400):
        for count in (1, 2, 3, 14):
            result = add_working_days(day, count)
            assert is_working_day(result) and result > day
        day = date.fromordinal(day.toordinal() + 1)
