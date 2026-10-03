"""Stage 14D.2D.4 — opt-in real PostgreSQL 16 proof harness (shared helpers).

Gate: `TEST_REAL_POSTGRES=1`. Intended to run INSIDE the backup image on an
isolated Docker network next to a disposable `postgres:16` container (owner
runbook in docs/STAGE_14D_BACKUP_RESTORE_PLAN.md §16.6), so the image's own
pg_dump 16 / psql / age 1.3.2 are used; it also works from any host with
PostgreSQL 16 client tools.

Configuration (all required when the gate is on, validated before any
connection):

    TEST_PG16_HOST             scratch server host; must contain "proof" (never "postgres")
    TEST_PG16_PORT             default 5432
    TEST_PG16_SUPERUSER        scratch superuser (default "postgres")
    TEST_PG16_SUPERUSER_PASSFILE  absolute path to a 0600 pgpass file for the scratch superuser
    TEST_PG16_SSLMODE          default "disable"
    TEST_PG16_REPORT_DIR       optional: directory for the JSON proof report

Every database it creates is named `pe_scratch_test_14d2d4_*`, every role
`pe_scratch_role_*`; role passwords are random hex generated per run and
exist only in 0600 passfiles under the pytest temporary directory. Nothing
is written to any non-scratch object; databases are dropped at session end,
then the roles.
"""

import json
import os
import re
import secrets
import stat
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

GATE = "TEST_REAL_POSTGRES"
DB_PREFIX = "pe_scratch_test_14d2d4_"
ROLE_PREFIX = "pe_scratch_role_"
REQUIRED_MAJOR = 16
_NAME = re.compile(r"^[a-z0-9_]{1,63}$")
_HEX = re.compile(r"^[0-9a-f]{16,64}$")


class ProofConfigError(RuntimeError):
    """The proof environment is missing or unsafe; nothing was touched."""


def gate_enabled(env: Mapping[str, str] | None = None) -> bool:
    return (os.environ if env is None else env).get(GATE) == "1"


@dataclass(frozen=True)
class ProofServer:
    host: str
    port: int
    superuser: str
    superuser_passfile: Path
    sslmode: str
    report_dir: Path | None

    @classmethod
    def from_env(cls, env: Mapping[str, str]) -> "ProofServer":
        host = env.get("TEST_PG16_HOST", "")
        if not host or "proof" not in host or host in ("postgres", "plan_estimate_postgres"):
            raise ProofConfigError("TEST_PG16_HOST must name the disposable proof server (must contain 'proof')")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]{0,62}", host):
            raise ProofConfigError("TEST_PG16_HOST is not a plain host name")
        try:
            port = int(env.get("TEST_PG16_PORT", "5432"))
        except ValueError:
            raise ProofConfigError("TEST_PG16_PORT is not an integer") from None
        superuser = env.get("TEST_PG16_SUPERUSER", "postgres")
        if not _NAME.match(superuser):
            raise ProofConfigError("TEST_PG16_SUPERUSER is not a plain role name")
        passfile = Path(env.get("TEST_PG16_SUPERUSER_PASSFILE", ""))
        if not passfile.is_absolute():
            raise ProofConfigError("TEST_PG16_SUPERUSER_PASSFILE must be an absolute path")
        try:
            mode = stat.S_IMODE(os.stat(passfile).st_mode)
        except OSError:
            raise ProofConfigError("TEST_PG16_SUPERUSER_PASSFILE does not exist") from None
        if mode & 0o077:
            raise ProofConfigError("TEST_PG16_SUPERUSER_PASSFILE must not be group/other accessible")
        sslmode = env.get("TEST_PG16_SSLMODE", "disable")
        if sslmode not in ("disable", "allow", "prefer", "require", "verify-ca", "verify-full"):
            raise ProofConfigError("TEST_PG16_SSLMODE is not a libpq SSL mode")
        report = env.get("TEST_PG16_REPORT_DIR")
        return cls(host, port, superuser, passfile, sslmode, Path(report) if report else None)

    # --- connection helpers (no password ever leaves a passfile) ------------------------

    def dsn(self, database: str, *, user: str | None = None, passfile: Path | None = None) -> str:
        check_scratch_db(database, allow_maintenance=True)
        return (
            f"postgresql://{quote(user or self.superuser, safe='')}@{self.host}:{self.port}/{quote(database, safe='')}"
            f"?sslmode={self.sslmode}&passfile={quote(str(passfile or self.superuser_passfile), safe='')}"
        )

    def sqlalchemy_url(self, database: str) -> str:
        check_scratch_db(database)
        return f"postgresql+asyncpg://{self.superuser}@{self.host}:{self.port}/{database}"

    def libpq_env(self, database: str, *, user: str, passfile: Path) -> dict[str, str]:
        check_scratch_db(database)
        return {
            "PGHOST": self.host,
            "PGPORT": str(self.port),
            "PGDATABASE": database,
            "PGUSER": user,
            "PGPASSFILE": str(passfile),
            "PGSSLMODE": self.sslmode,
        }

    def superuser_env(self, database: str) -> dict[str, str]:
        """Scratch databases or the `postgres` maintenance database (CREATE / DROP DATABASE, versions)."""
        check_scratch_db(database, allow_maintenance=True)
        return {
            "PGHOST": self.host,
            "PGPORT": str(self.port),
            "PGDATABASE": database,
            "PGUSER": self.superuser,
            "PGPASSFILE": str(self.superuser_passfile),
            "PGSSLMODE": self.sslmode,
        }


def check_scratch_db(name: str, *, allow_maintenance: bool = False) -> str:
    if allow_maintenance and name == "postgres":
        return name
    if not name.startswith(DB_PREFIX) or not _NAME.match(name):
        raise ProofConfigError("refusing a database that is not a 14D.2D.4 scratch database")
    return name


def check_scratch_role(name: str) -> str:
    if not name.startswith(ROLE_PREFIX) or not _NAME.match(name):
        raise ProofConfigError("refusing a role that is not a 14D.2D.4 scratch role")
    return name


def new_db_name(kind: str) -> str:
    return check_scratch_db(f"{DB_PREFIX}{kind}_{secrets.token_hex(4)}")


def new_role_name(kind: str) -> str:
    return check_scratch_role(f"{ROLE_PREFIX}{kind}_{secrets.token_hex(3)}")


def new_password() -> str:
    """Random hex only: safe as a SQL literal and in a pgpass line (no ':' or '\\')."""
    return secrets.token_hex(24)


def write_passfile(path: Path, server: ProofServer, *, database: str, user: str, password: str) -> Path:
    """Exactly one entry, no wildcard, 0600 -- the 14D.2C passfile contract."""
    if not _HEX.match(password):
        raise ProofConfigError("proof passwords must be random hex")
    check_scratch_db(database)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as fh:
        os.fchmod(fh.fileno(), 0o600)
        fh.write(f"{server.host}:{server.port}:{database}:{user}:{password}\n")
    return path


# --- psql / pg_dump subprocess helpers ----------------------------------------------------


def run_tool(argv: list[str], env: Mapping[str, str], *, stdin: Any = None, timeout: float = 300.0,
             check: bool = True) -> subprocess.CompletedProcess[bytes]:
    """argv list, no shell; the environment is the minimal PATH + the libpq variables."""
    clean = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C", **env}
    return subprocess.run(argv, env=clean, stdin=stdin, capture_output=True, timeout=timeout, check=check)


def psql(server: ProofServer, database: str, *args: str, stdin: Any = None, check: bool = True,
         ) -> subprocess.CompletedProcess[bytes]:
    return run_tool(["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1", "-At", *args], server.superuser_env(database),
                    stdin=stdin, check=check)


def restore_file(server: "ProofServer", database: str, sql_file: Path) -> None:
    """Restore a plain SQL dump into a scratch database as the scratch superuser."""
    with open(sql_file, "rb") as fh:
        run_tool(["psql", "-X", "-q", "-v", "ON_ERROR_STOP=1"], server.superuser_env(database), stdin=fh, timeout=600)


def tool_versions() -> dict[str, str]:
    versions = {}
    for tool in ("pg_dump", "psql", "age", "age-keygen"):
        try:
            out = run_tool([tool, "--version"], {}, timeout=30)
            versions[tool] = out.stdout.decode("ascii", "replace").strip().splitlines()[0]
        except (OSError, subprocess.SubprocessError, IndexError):
            versions[tool] = "unavailable"
    return versions


def major_of_tool_line(line: str) -> int | None:
    match = re.search(r"\(PostgreSQL\)\s+(\d+)", line)
    return int(match.group(1)) if match else None


# --- report -------------------------------------------------------------------------------

# Proof passwords are exactly 48 lowercase hex characters (secrets.token_hex(24));
# SHA-256 digests (64) and other values are not touched.
_PASSWORD_SHAPE = re.compile(r"(?<![0-9a-f])[0-9a-f]{48}(?![0-9a-f])")


def redact(value: str) -> str:
    """Belt and braces: a proof password can never reach a report."""
    return _PASSWORD_SHAPE.sub("<redacted>", value)


def write_report(server: ProofServer | None, name: str, payload: dict[str, Any]) -> str:
    """Print (for `pytest -s`) and optionally store a JSON section; returns the text."""
    text = redact(json.dumps({"section": name, **payload}, sort_keys=True, indent=2))
    print(f"\n===== 14D.2D.4 PROOF: {name} =====\n{text}")
    if server is not None and server.report_dir is not None:
        server.report_dir.mkdir(parents=True, exist_ok=True)
        (server.report_dir / f"{name}.json").write_text(text + "\n")
    return text
