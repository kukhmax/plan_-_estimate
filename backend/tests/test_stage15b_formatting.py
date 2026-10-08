"""Stage 15B — Polish number / money / date formatting of documents (formatting only, never arithmetic)."""

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domain.documents import formatting as f

NB = " "


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal(0), f"0,00{NB}zł"),
        (Decimal(5), f"5,00{NB}zł"),
        (Decimal("999.99"), f"999,99{NB}zł"),
        (Decimal(1000), f"1{NB}000,00{NB}zł"),
        (Decimal("1234.5"), f"1{NB}234,50{NB}zł"),
        (Decimal("1234567.891"), f"1{NB}234{NB}567,89{NB}zł"),
        (Decimal(12345678), f"12{NB}345{NB}678,00{NB}zł"),
        (Decimal("-1234.5"), f"-1{NB}234,50{NB}zł"),
        (Decimal("-0.004"), f"0,00{NB}zł"),  # a negative zero is not printed with a sign
        (7, f"7,00{NB}zł"),
        ("12.345", f"12,35{NB}zł"),
    ],
)
def test_money(value, expected):
    assert f.format_money(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(Decimal("0.005"), "0,01"), (Decimal("0.015"), "0,02"), (Decimal("0.025"), "0,03"), (Decimal("2.675"), "2,68"),
     (Decimal("-0.005"), "-0,01"), (Decimal("1.004"), "1,00"), (Decimal("1.005"), "1,01")],
)
def test_rounding_is_half_up_not_bankers(value, expected):
    assert f.format_decimal(value, 2) == expected


def test_other_currencies_keep_their_code():
    assert f.format_money(Decimal(10), "EUR") == f"10,00{NB}EUR"


def test_quantity_area_percent():
    assert f.format_quantity(Decimal("12.5")) == "12,50"
    assert f.format_quantity(Decimal("12.5"), 3) == "12,500"
    assert f.format_quantity(Decimal(12), 0) == "12"
    assert f.format_area(Decimal("1234.567")) == f"1{NB}234,57{NB}m²"
    assert f.format_percent(Decimal(23)) == f"23{NB}%"
    assert f.format_percent(Decimal("8.5"), 1) == f"8,5{NB}%"


@pytest.mark.parametrize("bad", [1.5, 0.1, True, False])
def test_floats_and_booleans_are_refused_with_the_reason(bad):
    with pytest.raises(TypeError, match="binary rounding"):
        f.format_money(bad)


@pytest.mark.parametrize("bad", [None, [], {}, object()])
def test_other_types_are_not_numbers(bad):
    with pytest.raises(TypeError, match="not a number"):
        f.format_money(bad)


@pytest.mark.parametrize("bad", ["abc", "", "1,5", "NaN", "Infinity", Decimal("NaN"), Decimal("Infinity")])
def test_text_that_is_not_a_finite_number_is_refused(bad):
    with pytest.raises(ValueError):
        f.format_money(bad)


def test_negative_places_are_refused():
    with pytest.raises(ValueError):
        f.format_decimal(Decimal(1), -1)


def test_grouping_can_be_switched_off():
    assert f.format_decimal(Decimal("12345.5"), 1, grouping=False) == "12345,5"


def test_dates_are_day_month_year():
    assert f.format_date(date(2026, 1, 5)) == "05.01.2026"
    assert f.format_date(date(2026, 12, 31)) == "31.12.2026"


def test_a_stored_utc_moment_is_shown_in_polish_local_time():
    winter = datetime(2026, 1, 15, 23, 30, tzinfo=UTC)  # CET = UTC+1 -> already the next day
    assert f.format_date(winter) == "16.01.2026"
    assert f.format_datetime(winter) == "16.01.2026 00:30"
    summer = datetime(2026, 7, 15, 21, 59, tzinfo=UTC)  # CEST = UTC+2 -> 23:59 the same day
    assert f.format_datetime(summer) == "15.07.2026 23:59"
    assert f.format_date(datetime(2026, 7, 15, 22, 0, tzinfo=UTC)) == "16.07.2026"


def test_a_naive_database_value_is_taken_as_utc():
    assert f.format_datetime(datetime(2026, 1, 15, 23, 30)) == "16.01.2026 00:30"  # noqa: DTZ001 (naive on purpose)


def test_another_offset_is_converted():
    zone = timezone(timedelta(hours=-5))
    assert f.format_datetime(datetime(2026, 1, 15, 18, 30, tzinfo=zone)) == "16.01.2026 00:30"
