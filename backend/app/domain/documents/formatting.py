"""Polish number / money / date formatting for documents (Stage 15B).

Formatting only -- no business arithmetic. Values come from snapshots as Decimal (or int / str); a float is refused because
it would silently reintroduce binary rounding into a legal document. Rounding is half-up (the usual commercial rule),
the decimal separator is a comma and thousands are separated by a no-break space: `1 234,50 zł`.
"""

from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from zoneinfo import ZoneInfo

NBSP = "\u00a0"
POLAND = ZoneInfo("Europe/Warsaw")

Number = Decimal | int | str


def to_decimal(value: Number) -> Decimal:
    if isinstance(value, bool | float):
        raise TypeError("documents format Decimal, int or str values only (a float would bring binary rounding in)")
    if isinstance(value, Decimal):
        number = value
    elif isinstance(value, int | str):
        try:
            number = Decimal(value)
        except InvalidOperation:
            raise ValueError(f"not a number: {value!r}") from None
    else:
        raise TypeError(f"not a number: {type(value).__name__}")
    if not number.is_finite():
        raise ValueError("a document number must be finite")
    return number


def format_decimal(value: Number, places: int, *, grouping: bool = True) -> str:
    if places < 0:
        raise ValueError("places must not be negative")
    number = to_decimal(value).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    sign = "-" if number < 0 else ""
    whole, _, fraction = f"{abs(number):f}".partition(".")
    if grouping and len(whole) > 3:
        head = len(whole) % 3
        groups = ([whole[:head]] if head else []) + [whole[i : i + 3] for i in range(head, len(whole), 3)]
        whole = NBSP.join(groups)
    return sign + whole + ("," + fraction if fraction else "")


def format_money(value: Number, currency: str = "PLN") -> str:
    amount = format_decimal(value, 2)
    return f"{amount}{NBSP}zł" if currency == "PLN" else f"{amount}{NBSP}{currency}"


def format_quantity(value: Number, places: int = 2) -> str:
    return format_decimal(value, places)


def format_quantity_exact(value: Number) -> str:
    """A snapshot quantity (three decimal places in the database) as it was typed: `12,50` but `12,345` -- never rounded
    away, because the amount of the line was computed from the exact value."""
    number = to_decimal(value)
    return format_decimal(number, 2 if number == number.quantize(Decimal("0.01")) else 3)


def format_area(value: Number, places: int = 2) -> str:
    return f"{format_decimal(value, places)}{NBSP}m²"


def format_percent(value: Number, places: int = 0) -> str:
    return f"{format_decimal(value, places)}{NBSP}%"


def local_datetime(value: datetime) -> datetime:
    """A stored UTC moment as Polish local time (a naive value is taken as UTC, which is how the database keeps it)."""
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value
    return aware.astimezone(POLAND)


def format_date(value: date | datetime) -> str:
    day = local_datetime(value).date() if isinstance(value, datetime) else value
    return f"{day.day:02d}.{day.month:02d}.{day.year:04d}"


def format_datetime(value: datetime) -> str:
    local = local_datetime(value)
    return f"{format_date(local)} {local.hour:02d}:{local.minute:02d}"
