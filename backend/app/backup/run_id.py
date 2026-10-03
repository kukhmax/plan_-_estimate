"""Backup run identifier contract (Stage 14D.2D.1).

`run_id` = `<UTC YYYYMMDDTHHMMSSZ>-<8 lowercase hex>`, e.g.
`20261003T081500Z-3f9a1c2e` (docs/STAGE_14D_BACKUP_RESTORE_PLAN.md §5).
It is generated internally -- never taken from argv, environment or any
other user input -- and validated strictly wherever it is read back (for
example from a directory listing), so it is always safe as a single path
component.
"""

import re
import secrets
from collections.abc import Callable
from datetime import UTC, datetime

# ASCII-only classes: `\d` would also match non-ASCII digits, which strptime accepts.
RUN_ID_PATTERN = re.compile(r"^(?P<ts>[0-9]{8}T[0-9]{6}Z)-(?P<suffix>[0-9a-f]{8})$", re.ASCII)
RUN_ID_TIMESTAMP_FORMAT = "%Y%m%dT%H%M%SZ"
RUN_ID_SUFFIX_BYTES = 4


class RunIdError(ValueError):
    """A value is not a valid backup run_id. The message never echoes it."""


def new_run_id(now: datetime | None = None, token_hex: Callable[[int], str] = secrets.token_hex) -> str:
    """A fresh run_id from the current UTC time and a random suffix.
    `now` must be timezone-aware (tests may pass a fixed instant)."""
    moment = datetime.now(UTC) if now is None else now
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise RunIdError("run_id time must be timezone-aware")
    run_id = f"{moment.astimezone(UTC).strftime(RUN_ID_TIMESTAMP_FORMAT)}-{token_hex(RUN_ID_SUFFIX_BYTES)}"
    return validate_run_id(run_id)


def validate_run_id(value: object) -> str:
    """Return `value` if it is exactly a canonical run_id with a real
    calendar timestamp; raise RunIdError otherwise."""
    if not isinstance(value, str):
        raise RunIdError("run_id must be a string")
    match = RUN_ID_PATTERN.fullmatch(value)
    if match is None:
        raise RunIdError("run_id is not in the canonical form YYYYMMDDTHHMMSSZ-xxxxxxxx")
    try:
        datetime.strptime(match.group("ts"), RUN_ID_TIMESTAMP_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        raise RunIdError("run_id timestamp is not a valid UTC date/time") from None
    return value


def run_id_timestamp(run_id: str) -> datetime:
    """The UTC instant encoded in a valid run_id."""
    match = RUN_ID_PATTERN.fullmatch(validate_run_id(run_id))
    assert match is not None
    return datetime.strptime(match.group("ts"), RUN_ID_TIMESTAMP_FORMAT).replace(tzinfo=UTC)
