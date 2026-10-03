"""Canonical PostgreSQL connection contract for backups (Stage 14D.2C).

One non-secret structure -- host, port, database, user, passfile path, SSL
mode -- from which BOTH the asyncpg exporter DSN and the libpq environment
of `pg_dump` are derived, so the two clients reach the same server and
database (PostgreSQL itself additionally refuses a snapshot imported on
another server or database).

The password exists only in the pgpass file (`PGPASSFILE`): never in argv,
DSNs, `PGPASSWORD`, logs or evidence. `validate_passfile` checks the file
before use and accepts only the part of the pgpass format that libpq and
asyncpg parse identically (no `\\` escapes, no `:` inside values, no
surrounding whitespace) -- so the future password must not contain `:`,
`\\` or whitespace (14D.3 owner action). Errors name the line / field, never
the content.
`docs/STAGE_14D_BACKUP_RESTORE_PLAN.md` §16.1.
"""

import os
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from app.core.pg_snapshot_dump import PgDumpCommand

SSL_MODES = ("disable", "allow", "prefer", "require", "verify-ca", "verify-full")
# Variables a backup process must never receive: a password outside the
# pgpass file, or a service / connection file that would bypass this
# contract.
FORBIDDEN_ENV = ("PGPASSWORD", "PGSERVICE", "PGSERVICEFILE")
PASSFILE_MAX_BYTES = 64 * 1024

_HOST = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9.-]{0,251}[A-Za-z0-9])?$")


class PgConnectionConfigError(ValueError):
    """The connection configuration is incomplete or unsafe."""


class PassfileError(ValueError):
    """The pgpass file is unsafe or does not hold exactly the expected entry.
    Messages never contain the file content."""


def _name(value: str, field: str) -> str:
    if not value or any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        raise PgConnectionConfigError(f"{field} must be a non-empty name without control characters")
    return value


@dataclass(frozen=True)
class PgConnectionConfig:
    """Non-secret connection parameters (there is no password field)."""

    host: str
    port: int
    database: str
    user: str
    passfile: Path
    sslmode: str

    def __post_init__(self) -> None:
        if not _HOST.match(self.host):
            raise PgConnectionConfigError("host must be a TCP host name or IPv4 address (no socket path)")
        if not 1 <= self.port <= 65535:
            raise PgConnectionConfigError("port is out of range")
        _name(self.database, "database")
        _name(self.user, "user")
        if not self.passfile.is_absolute():
            raise PgConnectionConfigError("passfile must be an absolute path")
        if self.sslmode not in SSL_MODES:
            raise PgConnectionConfigError("sslmode must be set explicitly to a libpq SSL mode")

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "PgConnectionConfig":
        """Read PGHOST / PGPORT / PGDATABASE / PGUSER / PGPASSFILE /
        PGSSLMODE (all required, SSL mode explicit). A password, service or
        service file in the environment is refused."""
        present = [name for name in FORBIDDEN_ENV if name in env]
        if present:
            raise PgConnectionConfigError(f"refusing {', '.join(present)} in the environment; use PGPASSFILE only")
        missing = [
            name
            for name in ("PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSFILE", "PGSSLMODE")
            if not env.get(name)
        ]
        if missing:
            raise PgConnectionConfigError(f"missing connection setting(s): {', '.join(missing)}")
        try:
            port = int(env["PGPORT"])
        except ValueError:
            raise PgConnectionConfigError("PGPORT is not an integer") from None
        return cls(
            host=env["PGHOST"],
            port=port,
            database=env["PGDATABASE"],
            user=env["PGUSER"],
            passfile=Path(env["PGPASSFILE"]),
            sslmode=env["PGSSLMODE"],
        )

    def asyncpg_dsn(self) -> str:
        """DSN for the asyncpg exporter: no password; asyncpg reads it from
        the same passfile."""
        return (
            f"postgresql://{quote(self.user, safe='')}@{self.host}:{self.port}/{quote(self.database, safe='')}"
            f"?sslmode={self.sslmode}&passfile={quote(str(self.passfile), safe='')}"
        )

    def libpq_env(self) -> dict[str, str]:
        """The libpq environment `pg_dump` must run with."""
        return {
            "PGHOST": self.host,
            "PGPORT": str(self.port),
            "PGDATABASE": self.database,
            "PGUSER": self.user,
            "PGPASSFILE": str(self.passfile),
            "PGSSLMODE": self.sslmode,
        }

    def check_process_env(self, env: Mapping[str, str]) -> None:
        """14D.2A's pg_dump inherits the process environment: it must carry
        exactly this connection (and no password)."""
        if any(name in env for name in FORBIDDEN_ENV):
            raise PgConnectionConfigError("process environment carries a forbidden libpq variable")
        mismatched = [name for name, value in self.libpq_env().items() if env.get(name) != value]
        if mismatched:
            raise PgConnectionConfigError(f"process environment differs from the connection in: {', '.join(mismatched)}")

    def pg_dump_command(self, lock_wait_timeout_ms: int | None = None) -> PgDumpCommand:
        """14D.2A command for a local (in-image) pg_dump reaching the server
        over the network: no tool prefix, host / port / SSL mode / passfile
        from `libpq_env`."""
        return PgDumpCommand(
            prefix=(), username=self.user, dbname=self.database, lock_wait_timeout_ms=lock_wait_timeout_ms
        )


def _parse_entry(line: str, line_no: int) -> list[str]:
    """Split one entry into its five fields, accepting only the subset that
    libpq and asyncpg read identically. They diverge on `\\` escapes (libpq
    de-escapes, asyncpg keeps the backslash), on `:` inside the password
    (libpq ends the password there, asyncpg keeps the rest) and on
    surrounding whitespace (asyncpg strips it): all three are refused, so
    both clients always derive the same password."""
    if "\\" in line:
        raise PassfileError(
            f"pgpass line {line_no}: backslash escapes are not accepted (libpq and asyncpg interpret them differently)"
        )
    if line != line.strip():
        raise PassfileError(f"pgpass line {line_no}: leading or trailing whitespace")
    fields = line.split(":")
    if len(fields) != 5:
        raise PassfileError(
            f"pgpass line {line_no}: expected exactly 5 fields host:port:database:user:password"
            " (':' is not allowed inside values)"
        )
    return fields


def validate_passfile(config: PgConnectionConfig, *, euid: int | None = None) -> None:
    """Accept the passfile only if it is an absolute, regular, non-symlink
    file owned by the effective user with no group / other permission bits,
    containing exactly one entry -- no wildcard -- whose host, port, database
    and user equal `config`, with a non-empty password. Never returns or
    reports the password."""
    path = config.passfile
    expected_uid = os.geteuid() if euid is None else euid
    if not path.is_absolute():
        raise PassfileError("pgpass path must be absolute")
    try:
        st = os.lstat(path)
    except OSError:
        raise PassfileError("pgpass file does not exist or is not accessible") from None
    if stat.S_ISLNK(st.st_mode):
        raise PassfileError("pgpass file must not be a symlink")
    if not stat.S_ISREG(st.st_mode):
        raise PassfileError("pgpass file is not a regular file")
    if st.st_uid != expected_uid:
        raise PassfileError("pgpass file is not owned by the effective user")
    if st.st_mode & 0o077:
        raise PassfileError("pgpass file has group / other permissions (expected 0600 or 0400)")
    if st.st_size > PASSFILE_MAX_BYTES:
        raise PassfileError("pgpass file is unexpectedly large")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as fh:
            raw = fh.read(PASSFILE_MAX_BYTES + 1)
    except OSError:
        raise PassfileError("pgpass file could not be read") from None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise PassfileError("pgpass file is not valid UTF-8") from None

    entries: list[tuple[int, list[str]]] = []
    for line_no, line in enumerate(text.split("\n"), start=1):
        if line == "" or line.startswith("#"):  # empty lines and '#' at column 1 (both parsers)
            continue
        if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in line):
            raise PassfileError(f"pgpass line {line_no}: control character")
        entries.append((line_no, _parse_entry(line, line_no)))
    if len(entries) != 1:
        raise PassfileError(f"pgpass file must contain exactly one entry (found {len(entries)})")

    line_no, fields = entries[0]
    names = ("host", "port", "database", "user", "password")
    for name, value in zip(names, fields, strict=True):
        if value == "*":
            raise PassfileError(f"pgpass line {line_no}: wildcard in {name} is not allowed")
    expected = (config.host, str(config.port), config.database, config.user)
    for name, actual, wanted in zip(names, fields, expected, strict=False):
        if actual != wanted:
            raise PassfileError(f"pgpass line {line_no}: {name} does not match the configured connection")
    if not fields[4]:
        raise PassfileError(f"pgpass line {line_no}: empty password")
