"""Backup image entrypoint: `python -m app.backup <command>`.

Nothing here starts a server, runs migrations or prints the environment:
every reported value is selected explicitly and non-secret.

    preflight              (14D.2C) tool versions (Python 3.12, pg_dump 16, age 1.3.2) and effective
                           UID/GID (non-root); never connects to a database
    preflight --workspace  additionally: data root and work/encrypted/evidence, connection settings,
                           pgpass file and age recipients (validated, never printed)
    db-dump                (14D.2D.3) one local database backup run -- see app.backup.db_dump_command
                           for its exit codes

preflight exits 0 when every check passes, 1 otherwise; 2 on usage errors.
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from typing import TextIO

from app.backup.layout import BackupLayout, private_dir_problem
from app.backup.pg_connection import (
    PassfileError,
    PgConnectionConfig,
    PgConnectionConfigError,
    validate_passfile,
)
from app.core.db_dump_encryption import (
    AgeRecipientError,
    AgeToolError,
    parse_age_recipients,
    parse_age_version,
)
from app.core.pg_snapshot_dump import PgDumpVersionMismatchError, parse_pg_dump_major

EXPECTED_PYTHON = (3, 12)
EXPECTED_PG_DUMP_MAJOR = 16
EXPECTED_AGE_VERSION = "1.3.2"
TOOL_TIMEOUT_SECONDS = 30


def _tool_version(name: str, path_env: str) -> tuple[str | None, str]:
    """(resolved path, first line of `<tool> --version`) with a minimal
    environment; raises OSError / CalledProcessError / TimeoutExpired."""
    resolved = shutil.which(name, path=path_env)
    if resolved is None:
        return None, ""
    completed = subprocess.run(
        [resolved, "--version"],
        env={"PATH": path_env, "LC_ALL": "C"},
        capture_output=True,
        text=True,
        timeout=TOOL_TIMEOUT_SECONDS,
        check=True,
    )
    lines = completed.stdout.strip().splitlines()
    return resolved, lines[0].strip() if lines else ""


class _Report:
    def __init__(self, out: TextIO) -> None:
        self.out = out
        self.failed = False

    def line(self, key: str, value: str, ok: bool = True) -> None:
        status = "ok" if ok else "FAIL"
        self.failed |= not ok
        print(f"{status:4} {key}: {value}", file=self.out)


def run_preflight(
    *,
    workspace: bool,
    env: Mapping[str, str],
    out: TextIO,
    layout: BackupLayout | None = None,
    python_version: tuple[int, int] | None = None,
    euid: int | None = None,
    egid: int | None = None,
) -> int:
    report = _Report(out)
    path_env = env.get("PATH", os.defpath)

    version = python_version or (sys.version_info.major, sys.version_info.minor)
    report.line("python", f"{platform.python_version()} (expected {EXPECTED_PYTHON[0]}.{EXPECTED_PYTHON[1]}.x)",
                ok=version == EXPECTED_PYTHON)

    try:
        resolved, first = _tool_version("pg_dump", path_env)
        if resolved is None:
            report.line("pg_dump", "not found", ok=False)
        else:
            major = parse_pg_dump_major(first)
            report.line("pg_dump", f"{first} at {resolved} (expected major {EXPECTED_PG_DUMP_MAJOR})",
                        ok=major == EXPECTED_PG_DUMP_MAJOR)
    except (OSError, subprocess.SubprocessError, PgDumpVersionMismatchError) as exc:
        report.line("pg_dump", f"unusable ({type(exc).__name__})", ok=False)

    try:
        resolved, first = _tool_version("age", path_env)
        if resolved is None:
            report.line("age", "not found", ok=False)
        else:
            age_version = parse_age_version(first)
            report.line("age", f"{age_version} at {resolved} (expected {EXPECTED_AGE_VERSION})",
                        ok=age_version.removeprefix("v") == EXPECTED_AGE_VERSION)
    except (OSError, subprocess.SubprocessError, AgeToolError) as exc:
        report.line("age", f"unusable ({type(exc).__name__})", ok=False)

    uid = os.geteuid() if euid is None else euid
    gid = os.getegid() if egid is None else egid
    report.line("identity", f"uid={uid} gid={gid}", ok=uid != 0)

    if workspace:
        for name, path in (layout or BackupLayout()).writable_dirs().items():
            problem = private_dir_problem(path, euid=uid)
            report.line(f"mount {name}", f"{path} {problem or 'private, writable'}", ok=problem is None)
        try:
            config = PgConnectionConfig.from_env(env)
            report.line(
                "connection",
                f"host={config.host} port={config.port} database={config.database} user={config.user}"
                f" sslmode={config.sslmode}",
            )
            try:
                validate_passfile(config, euid=uid)
                report.line("passfile", f"{config.passfile} valid (exactly one matching entry)")
            except PassfileError as exc:
                report.line("passfile", str(exc), ok=False)
        except PgConnectionConfigError as exc:
            report.line("connection", str(exc), ok=False)
        try:
            recipients = parse_age_recipients(env.get("BACKUP_AGE_RECIPIENTS", ""))
            report.line("age recipients", f"{len(recipients)} valid public recipient(s)")
        except AgeRecipientError as exc:
            report.line("age recipients", str(exc), ok=False)

    report.line("result", "PASS" if not report.failed else "FAIL", ok=not report.failed)
    return 1 if report.failed else 0


def main(argv: Sequence[str] | None = None, *, env: Mapping[str, str] | None = None, out: TextIO | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.backup", description="Plan & Estimate backup image")
    commands = parser.add_subparsers(dest="command", required=True)
    preflight = commands.add_parser("preflight", help="report tool versions and identity; never prints secrets")
    preflight.add_argument("--workspace", action="store_true", help="also check mounts, connection and passfile")
    commands.add_parser("db-dump", help="run one local encrypted database backup into the data root")
    args = parser.parse_args(argv)
    if args.command == "db-dump":
        from app.backup.db_dump_command import run_db_dump

        return run_db_dump(os.environ if env is None else env, sys.stdout if out is None else out)
    return run_preflight(
        workspace=args.workspace, env=os.environ if env is None else env, out=sys.stdout if out is None else out
    )


if __name__ == "__main__":
    sys.exit(main())
