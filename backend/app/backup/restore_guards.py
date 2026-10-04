"""Safety guards for restoring a backup (Stage 14D.2I).

Contract: docs/STAGE_14D_BACKUP_RESTORE_PLAN.md §9 (restore chain), §11 (drill), §12 (isolation: "tools refuse a
restore / drill target equal to a configured production bucket and refuse a non-scratch database"), §16.13.

Two independent guards, both checked before anything is read from the backup or written anywhere:

- `validate_restore_database` -- the database a dump is restored into must be recognisably scratch: its name
  contains `pe_restore_scratch`, its host is loopback or a name containing `scratch` (or an explicitly allowed
  host), and the pgpass file satisfies the 14D.2C contract. The *runtime* guard that matters most -- the database
  must be empty -- lives in `restore_db` (a production database is never empty).
- `validate_identity_file` -- the age private identity the restore operator supplies must be a private, regular,
  owner-only file that holds an age secret key. Its content is never returned, printed or logged.

Messages name fields and rules, never values (no host, database, path content or key material).
"""

import os
import re
import stat
from collections.abc import Collection
from pathlib import Path

from app.backup.pg_connection import PgConnectionConfig, validate_passfile

SCRATCH_DB_MARKER = "pe_restore_scratch"
SCRATCH_HOST_MARKER = "scratch"
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost"})
IDENTITY_MAX_BYTES = 64 * 1024
_SECRET_LINE = re.compile(rb"^AGE-SECRET-KEY-1[0-9A-Z]{50,}$")


class RestoreGuardError(RuntimeError):
    """A restore target or credential file is unsafe. Messages never contain a value."""


class UnsafeRestoreDatabaseError(RestoreGuardError):
    pass


class IdentityFileError(RestoreGuardError):
    pass


def validate_restore_database(config: PgConnectionConfig, *, allowed_hosts: Collection[str] = ()) -> None:
    """Refuse anything that is not recognisably a scratch database (see module docstring)."""
    if SCRATCH_DB_MARKER not in config.database:
        raise UnsafeRestoreDatabaseError(f"the database name must contain '{SCRATCH_DB_MARKER}'")
    host = config.host.lower()
    if host not in LOOPBACK_HOSTS and SCRATCH_HOST_MARKER not in host and config.host not in set(allowed_hosts):
        raise UnsafeRestoreDatabaseError(
            f"the database host must be loopback, contain '{SCRATCH_HOST_MARKER}' or be explicitly allowed"
        )
    try:
        validate_passfile(config)
    except ValueError as exc:  # PassfileError: value-free by design
        raise UnsafeRestoreDatabaseError(f"the pgpass file is not acceptable ({type(exc).__name__})") from None


def validate_identity_file(path: Path, *, euid: int | None = None) -> None:
    """Accept an age identity file only if it is an absolute, regular, non-symlink file owned by the effective
    user with no group / other permission bits, of sane size, containing an age secret key line."""
    expected_uid = os.geteuid() if euid is None else euid
    if not path.is_absolute():
        raise IdentityFileError("the identity path must be absolute")
    try:
        st = os.lstat(path)
    except OSError:
        raise IdentityFileError("the identity file does not exist or is not accessible") from None
    if stat.S_ISLNK(st.st_mode):
        raise IdentityFileError("the identity file must not be a symlink")
    if not stat.S_ISREG(st.st_mode):
        raise IdentityFileError("the identity file is not a regular file")
    if st.st_uid != expected_uid:
        raise IdentityFileError("the identity file is not owned by the effective user")
    if st.st_mode & 0o077:
        raise IdentityFileError("the identity file has group / other permissions (expected 0600 or 0400)")
    if st.st_size == 0 or st.st_size > IDENTITY_MAX_BYTES:
        raise IdentityFileError("the identity file is empty or unexpectedly large")
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as handle:
            raw = handle.read(IDENTITY_MAX_BYTES + 1)
    except OSError:
        raise IdentityFileError("the identity file could not be read") from None
    if not any(_SECRET_LINE.match(line.strip()) for line in raw.splitlines()):
        raise IdentityFileError("the identity file does not contain an age secret key")
