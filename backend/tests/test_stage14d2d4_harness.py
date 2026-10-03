"""Stage 14D.2D.4 — the PostgreSQL 16 proof harness itself (no PostgreSQL, no Docker).

Proves the gating, scratch-only guards, passfile writing and report
redaction. It does NOT prove any PostgreSQL behaviour.
"""

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from tests.pg16_proof_support import (
    DB_PREFIX,
    ProofConfigError,
    ProofServer,
    check_scratch_db,
    check_scratch_role,
    gate_enabled,
    major_of_tool_line,
    new_db_name,
    new_password,
    new_role_name,
    redact,
    run_tool,
    write_passfile,
    write_report,
)

BACKEND = Path(__file__).resolve().parents[1]
PROOF_MODULES = (
    "tests/test_stage14d2d4_pg16_snapshot.py",
    "tests/test_stage14d2d4_pg16_roles.py",
    "tests/test_stage14d2d4_pg16_orchestrator.py",
)


def superuser_passfile(tmp_path: Path, mode: int = 0o600, name: str = "superuser.pgpass") -> Path:
    path = tmp_path / name
    path.write_text("pe14d-proof-pg:5432:*:postgres:" + "a" * 48 + "\n")
    path.chmod(mode)
    return path


def env(tmp_path: Path, **overrides: str) -> dict[str, str]:
    values = {"TEST_PG16_HOST": "pe14d-proof-pg", "TEST_PG16_SUPERUSER_PASSFILE": str(superuser_passfile(tmp_path))}
    values.update(overrides)
    return values


def test_gate_is_off_by_default():
    assert gate_enabled({}) is False
    assert gate_enabled({"TEST_REAL_POSTGRES": "true"}) is False
    assert gate_enabled({"TEST_REAL_POSTGRES": "1"}) is True


def test_valid_proof_configuration(tmp_path):
    server = ProofServer.from_env(env(tmp_path))
    assert (server.host, server.port, server.superuser, server.sslmode) == ("pe14d-proof-pg", 5432, "postgres", "disable")
    dsn = server.dsn("postgres")
    assert dsn.startswith("postgresql://postgres@pe14d-proof-pg:5432/postgres?sslmode=disable&passfile=")
    assert "a" * 48 not in dsn


@pytest.mark.parametrize(
    "overrides",
    [
        {"TEST_PG16_HOST": ""},
        {"TEST_PG16_HOST": "postgres"},
        {"TEST_PG16_HOST": "plan_estimate_postgres"},
        {"TEST_PG16_HOST": "db.example.com"},
        {"TEST_PG16_HOST": "proof host"},
        {"TEST_PG16_HOST": "proof;rm"},
        {"TEST_PG16_PORT": "x"},
        {"TEST_PG16_SUPERUSER": "Postgres; DROP"},
        {"TEST_PG16_SUPERUSER_PASSFILE": "relative/pgpass"},
        {"TEST_PG16_SUPERUSER_PASSFILE": "/nonexistent/pgpass"},
        {"TEST_PG16_SSLMODE": "off"},
    ],
)
def test_unsafe_or_incomplete_configuration_is_refused(tmp_path, overrides):
    with pytest.raises(ProofConfigError):
        ProofServer.from_env(env(tmp_path, **overrides))


def test_group_readable_superuser_passfile_is_refused(tmp_path):
    with pytest.raises(ProofConfigError):
        broad = superuser_passfile(tmp_path, 0o640, name="broad.pgpass")
        ProofServer.from_env(env(tmp_path, TEST_PG16_SUPERUSER_PASSFILE=str(broad)))


def test_scratch_name_guards():
    assert check_scratch_db(f"{DB_PREFIX}db_00ff00ff") and new_db_name("x").startswith(DB_PREFIX)
    assert check_scratch_db("postgres", allow_maintenance=True) == "postgres"
    for bad in ("postgres", "plan_estimate", "pe_scratch_test_other", f"{DB_PREFIX}X", f'{DB_PREFIX}a"b'):
        with pytest.raises(ProofConfigError):
            check_scratch_db(bad)
    assert new_role_name("case").startswith("pe_scratch_role_case_")
    for bad in ("postgres", "pe_backup", "pe_scratch_role_A", "pe_scratch_role_x;drop"):
        with pytest.raises(ProofConfigError):
            check_scratch_role(bad)


def test_server_helpers_refuse_non_scratch_databases(tmp_path):
    server = ProofServer.from_env(env(tmp_path))
    for call in (lambda: server.dsn("plan_estimate"), lambda: server.sqlalchemy_url("postgres"),
                 lambda: server.libpq_env("plan_estimate", user="x", passfile=tmp_path / "p"),
                 lambda: server.superuser_env("plan_estimate")):
        with pytest.raises(ProofConfigError):
            call()


def test_passwords_are_random_hex():
    first, second = new_password(), new_password()
    assert first != second and len(first) == 48 and set(first) <= set("0123456789abcdef")


def test_role_passfile_matches_the_14d2c_contract(tmp_path):
    from app.backup.pg_connection import PgConnectionConfig, validate_passfile

    server = ProofServer.from_env(env(tmp_path))
    db, password = new_db_name("db"), new_password()
    old = os.umask(0)
    try:
        path = write_passfile(tmp_path / "role.pgpass", server, database=db, user="pe_scratch_role_x_00aa00", password=password)
    finally:
        os.umask(old)
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert path.read_text() == f"pe14d-proof-pg:5432:{db}:pe_scratch_role_x_00aa00:{password}\n"
    validate_passfile(PgConnectionConfig(host="pe14d-proof-pg", port=5432, database=db, user="pe_scratch_role_x_00aa00",
                                         passfile=path, sslmode="disable"))
    with pytest.raises(FileExistsError):
        write_passfile(path, server, database=db, user="u", password=password)
    with pytest.raises(ProofConfigError):
        write_passfile(tmp_path / "bad", server, database=db, user="u", password="has:colon-not-hex")
    with pytest.raises(ProofConfigError):
        write_passfile(tmp_path / "bad2", server, database="plan_estimate", user="u", password=password)


def test_report_redacts_passwords_but_keeps_digests(tmp_path, capsys):
    password, digest = new_password(), "f" * 64
    assert redact(f"pw={password} sha={digest}") == f"pw=<redacted> sha={digest}"
    server = ProofServer.from_env(env(tmp_path, TEST_PG16_REPORT_DIR=str(tmp_path / "report")))
    text = write_report(server, "unit", {"note": f"leak {password}", "digest": digest})
    assert password not in text and password not in capsys.readouterr().out
    assert password not in (tmp_path / "report" / "unit.json").read_text()


def test_tool_major_parsing():
    assert major_of_tool_line("pg_dump (PostgreSQL) 16.15 (Debian 16.15-1.pgdg13+2)") == 16
    assert major_of_tool_line("pg_dump (PostgreSQL) 17.2") == 17
    assert major_of_tool_line("unavailable") is None


def test_run_tool_uses_a_minimal_environment(monkeypatch):
    monkeypatch.setenv("PE_PROOF_SECRET_SENTINEL", "x")
    out = run_tool([sys.executable, "-c", "import os, json; print(json.dumps(sorted(os.environ)))"], {"PGHOST": "h"})
    names = out.stdout.decode()
    assert "PE_PROOF_SECRET_SENTINEL" not in names and "PGHOST" in names


def test_proof_modules_skip_without_the_gate():
    clean_env = {k: v for k, v in os.environ.items() if not k.startswith(("TEST_REAL_POSTGRES", "TEST_PG16_"))}
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", *PROOF_MODULES],
        cwd=BACKEND, env=clean_env, capture_output=True, text=True, timeout=300, check=False,
    )
    assert completed.returncode == 0, completed.stdout[-2000:]
    assert " skipped" in completed.stdout and "passed" not in completed.stdout.split("skipped")[0].splitlines()[-1]
    assert "failed" not in completed.stdout and "error" not in completed.stdout.lower()
