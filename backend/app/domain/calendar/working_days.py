"""Working days and public holidays of Poland (Stage 18B).

The contract defines "Dni robocze" as the days from Monday to Friday excluding the statutory days off (definitions.10), so a term
counted in working days (§ 10, 13, 14) needs the holidays. Rules known to the code: the fixed holidays, Easter Monday and Corpus
Christi (counted from Easter Sunday), Epiphany (a day off since 2011) and Christmas Eve (a day off since 2025). Pentecost Sunday and
Easter Sunday fall on Sunday anyway. Correct for the years from 2011 on; the dates before are not a case of this application.
"""
from datetime import date, timedelta
from functools import lru_cache

EPIPHANY_FROM = 2011
CHRISTMAS_EVE_FROM = 2025


def easter_sunday(year: int) -> date:
    """Easter Sunday of the Gregorian calendar (the anonymous algorithm of Meeus / Jones / Butcher)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


@lru_cache(maxsize=64)
def holidays(year: int) -> dict[date, str]:
    """The public holidays of the year: date -> a stable key (the name is a text of the locale dictionaries, not of the code)."""
    easter = easter_sunday(year)
    found = {
        date(year, 1, 1): "NEW_YEAR",
        date(year, 5, 1): "LABOUR_DAY",
        date(year, 5, 3): "CONSTITUTION_DAY",
        date(year, 8, 15): "ASSUMPTION",
        date(year, 11, 1): "ALL_SAINTS",
        date(year, 11, 11): "INDEPENDENCE_DAY",
        date(year, 12, 25): "CHRISTMAS",
        date(year, 12, 26): "SECOND_DAY_OF_CHRISTMAS",
        easter: "EASTER",
        easter + timedelta(days=1): "EASTER_MONDAY",
        easter + timedelta(days=49): "PENTECOST",
        easter + timedelta(days=60): "CORPUS_CHRISTI",
    }
    if year >= EPIPHANY_FROM:
        found[date(year, 1, 6)] = "EPIPHANY"
    if year >= CHRISTMAS_EVE_FROM:
        found[date(year, 12, 24)] = "CHRISTMAS_EVE"
    return found


def holiday_key(day: date) -> str | None:
    return holidays(day.year).get(day)


def is_working_day(day: date) -> bool:
    """Monday to Friday, not a public holiday (the contract's definition of "Dzień roboczy")."""
    return day.weekday() < 5 and day not in holidays(day.year)


def working_day_on_or_after(day: date) -> date:
    while not is_working_day(day):
        day += timedelta(days=1)
    return day


def add_working_days(start: date, count: int) -> date:
    """The day that is `count` working days after `start` (the day itself is not counted, it need not be a working day).

    `count` 1 from a Friday is the next Monday; from the eve of a holiday it is the first working day after it. Zero returns `start`.
    """
    if count < 0:
        raise ValueError("count must not be negative")
    day = start
    left = count
    while left:
        day += timedelta(days=1)
        if is_working_day(day):
            left -= 1
    return day
