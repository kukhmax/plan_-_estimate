"""Safety guard for the Stage 14C.6B opt-in PostgreSQL verification.

The PostgreSQL tests and the list benchmark run ONLY against an explicitly
supplied, disposable scratch database:

1. `TEST_PG_URL` must be set (otherwise the tests are skipped);
2. driver `postgresql+asyncpg`, host on the loopback interface only;
3. the database name must contain the marker `pe_scratch_test`.

Anything else raises before a single connection is opened, so the harness
cannot run against production or any shared database by accident.
"""

import os

from sqlalchemy.engine import URL, make_url

ENV_VAR = "TEST_PG_URL"
DB_MARKER = "pe_scratch_test"
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


class UnsafeScratchDatabaseError(RuntimeError):
    pass


def scratch_url(raw: str | None = None) -> URL | None:
    """The validated scratch URL, or None when TEST_PG_URL is unset."""
    raw = os.environ.get(ENV_VAR) if raw is None else raw
    if not raw:
        return None
    try:
        url = make_url(raw)
    except Exception as exc:  # noqa: BLE001 - re-raised as a safety error without echoing the URL
        raise UnsafeScratchDatabaseError(f"{ENV_VAR} is not a valid database URL") from exc
    if url.drivername != "postgresql+asyncpg":
        raise UnsafeScratchDatabaseError(f"{ENV_VAR} must use postgresql+asyncpg")
    if url.host not in LOOPBACK_HOSTS:
        raise UnsafeScratchDatabaseError(f"{ENV_VAR} host must be loopback ({sorted(LOOPBACK_HOSTS)})")
    if not url.database or DB_MARKER not in url.database:
        raise UnsafeScratchDatabaseError(f"{ENV_VAR} database name must contain '{DB_MARKER}'")
    return url
