"""Stage 14D.2C — backup connection / pgpass contract (fake credentials only)."""

import os
import stat
from pathlib import Path

import pytest

from app.backup.pg_connection import (
    PassfileError,
    PgConnectionConfig,
    PgConnectionConfigError,
    validate_passfile,
)

FAKE_PASSWORD = "fakePw0123456789abcdefABCDEF"
ENTRY = "postgres:5432:plan_estimate:pe_backup:" + FAKE_PASSWORD


def config(passfile: Path, **overrides) -> PgConnectionConfig:
    values: dict = {
        "host": "postgres",
        "port": 5432,
        "database": "plan_estimate",
        "user": "pe_backup",
        "passfile": passfile,
        "sslmode": "disable",
    }
    values.update(overrides)
    return PgConnectionConfig(**values)


def write_passfile(tmp_path: Path, content: str, mode: int = 0o600) -> Path:
    path = tmp_path / "pgpass"
    path.write_text(content)
    path.chmod(mode)
    return path


def env_for(passfile: Path, **overrides) -> dict[str, str]:
    env = {
        "PGHOST": "postgres",
        "PGPORT": "5432",
        "PGDATABASE": "plan_estimate",
        "PGUSER": "pe_backup",
        "PGPASSFILE": str(passfile),
        "PGSSLMODE": "disable",
    }
    env.update(overrides)
    return env


# --- configuration --------------------------------------------------------------------------


def test_from_env_round_trips_to_libpq_env(tmp_path):
    passfile = tmp_path / "pgpass"
    cfg = PgConnectionConfig.from_env(env_for(passfile))
    assert cfg == config(passfile)
    assert cfg.libpq_env() == env_for(passfile)


def test_asyncpg_dsn_and_libpq_env_describe_the_same_connection(tmp_path):
    cfg = config(tmp_path / "pg pass")
    dsn = cfg.asyncpg_dsn()
    assert dsn.startswith("postgresql://pe_backup@postgres:5432/plan_estimate?")
    assert "sslmode=disable" in dsn and "passfile=" in dsn
    assert ":" not in dsn.split("://", 1)[1].split("@", 1)[0]  # no user:password


def test_asyncpg_dsn_is_parsed_identically_by_asyncpg(tmp_path):
    from asyncpg.connect_utils import (
        _parse_connect_dsn_and_args,  # type: ignore[attr-defined]
    )

    passfile = write_passfile(tmp_path, ENTRY + "\n")
    cfg = config(passfile)
    addrs, params = _parse_connect_dsn_and_args(
        dsn=cfg.asyncpg_dsn(), host=None, port=None, user=None, password=None, passfile=None, database=None,
        ssl=None, direct_tls=None, server_settings=None, target_session_attrs=None, krbsrvname=None,
        gsslib=None, service=None, servicefile=None,
    )
    assert addrs == [("postgres", 5432)]
    assert params.user == "pe_backup" and params.database == "plan_estimate"
    # asyncpg reads the password from the same passfile named in the DSN
    assert params.password == FAKE_PASSWORD


@pytest.mark.parametrize("name", ["PGPASSWORD", "PGSERVICE", "PGSERVICEFILE"])
def test_password_or_service_in_env_is_refused(tmp_path, name):
    with pytest.raises(PgConnectionConfigError) as exc:
        PgConnectionConfig.from_env(env_for(tmp_path / "p", **{name: "secret-value-xyz"}))
    assert "secret-value-xyz" not in str(exc.value)


@pytest.mark.parametrize("missing", ["PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSFILE", "PGSSLMODE"])
def test_every_setting_is_required(tmp_path, missing):
    env = env_for(tmp_path / "p")
    del env[missing]
    with pytest.raises(PgConnectionConfigError):
        PgConnectionConfig.from_env(env)


@pytest.mark.parametrize(
    "overrides",
    [
        {"host": "/var/run/postgresql"},
        {"host": ""},
        {"host": "postgres;rm"},
        {"port": 0},
        {"port": 70000},
        {"database": ""},
        {"user": "pe\nbackup"},
        {"sslmode": "off"},
        {"sslmode": ""},
        {"passfile": Path("relative/pgpass")},
    ],
)
def test_invalid_configuration_is_refused(tmp_path, overrides):
    values = {"passfile": tmp_path / "p", **overrides}
    with pytest.raises(PgConnectionConfigError):
        config(**values)


def test_sslmode_is_configurable_not_fixed(tmp_path):
    for mode in ("disable", "require", "verify-full"):
        assert config(tmp_path / "p", sslmode=mode).libpq_env()["PGSSLMODE"] == mode


def test_representation_has_no_password_field(tmp_path):
    cfg = config(write_passfile(tmp_path, ENTRY + "\n"))
    assert not hasattr(cfg, "password")
    for text in (repr(cfg), cfg.asyncpg_dsn(), str(cfg.libpq_env())):
        assert FAKE_PASSWORD not in text and "fake-Pw" not in text


def test_pg_dump_command_and_env_carry_no_password(tmp_path):
    cfg = config(write_passfile(tmp_path, ENTRY + "\n"))
    argv = cfg.pg_dump_command(lock_wait_timeout_ms=5000).dump_argv("00000003-0000001B-1", "pe-snapshot-abc123-dump")
    assert argv[:3] == ["env", "PGAPPNAME=pe-snapshot-abc123-dump", "pg_dump"]  # no docker exec prefix
    assert "--no-password" in argv and "--username=pe_backup" in argv and "--dbname=plan_estimate" in argv
    assert not any("fake-Pw" in a or "password=" in a.lower() for a in argv)
    assert "PGPASSWORD" not in cfg.libpq_env()


def test_process_env_must_match_the_connection(tmp_path):
    cfg = config(tmp_path / "p")
    cfg.check_process_env({**env_for(tmp_path / "p"), "PATH": "/usr/bin"})
    with pytest.raises(PgConnectionConfigError) as exc:
        cfg.check_process_env(env_for(tmp_path / "p", PGHOST="other-host"))
    assert "PGHOST" in str(exc.value)
    with pytest.raises(PgConnectionConfigError):
        cfg.check_process_env({**env_for(tmp_path / "p"), "PGPASSWORD": "x"})


# --- passfile --------------------------------------------------------------------------------


def test_valid_passfile_is_accepted(tmp_path):
    validate_passfile(config(write_passfile(tmp_path, ENTRY + "\n")))


def test_valid_passfile_with_comments_blank_lines_and_0400(tmp_path):
    path = write_passfile(tmp_path, "# backup role\n\n" + ENTRY + "\n", mode=0o400)
    validate_passfile(config(path))


def test_asyncpg_keeps_backslashes_that_libpq_would_remove(tmp_path):
    """Why escapes are refused: for `pw\\:x` libpq reads `pw:x`, asyncpg reads
    `pw\\:x` -- the two clients would use different passwords."""
    from asyncpg.connect_utils import _read_password_file  # type: ignore[attr-defined]

    path = write_passfile(tmp_path, "postgres:5432:plan_estimate:pe_backup:pw\\:x\n")
    assert _read_password_file(path)[0][4] == "pw\\:x"
    with pytest.raises(PassfileError) as exc:
        validate_passfile(config(path))
    assert "backslash" in str(exc.value)


@pytest.mark.parametrize("mode", [0o640, 0o604, 0o660, 0o644, 0o666, 0o700 | 0o004])
def test_broad_mode_is_refused(tmp_path, mode):
    with pytest.raises(PassfileError):
        validate_passfile(config(write_passfile(tmp_path, ENTRY + "\n", mode=mode)))


def test_symlink_is_refused(tmp_path):
    real = write_passfile(tmp_path, ENTRY + "\n")
    link = tmp_path / "link"
    link.symlink_to(real)
    with pytest.raises(PassfileError):
        validate_passfile(config(link))


def test_non_regular_file_is_refused(tmp_path):
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo, 0o600)
    with pytest.raises(PassfileError):
        validate_passfile(config(fifo))
    directory = tmp_path / "dir"
    directory.mkdir(mode=0o700)
    with pytest.raises(PassfileError):
        validate_passfile(config(directory))


def test_missing_file_is_refused(tmp_path):
    with pytest.raises(PassfileError):
        validate_passfile(config(tmp_path / "absent"))


def test_foreign_owner_is_refused(tmp_path):
    path = write_passfile(tmp_path, ENTRY + "\n")
    with pytest.raises(PassfileError):
        validate_passfile(config(path), euid=os.geteuid() + 1)


@pytest.mark.parametrize(
    ("field", "line"),
    [
        ("host", "otherhost:5432:plan_estimate:pe_backup:pw"),
        ("port", "postgres:5433:plan_estimate:pe_backup:pw"),
        ("database", "postgres:5432:other_db:pe_backup:pw"),
        ("user", "postgres:5432:plan_estimate:postgres:pw"),
    ],
)
def test_entry_mismatch_is_refused(tmp_path, field, line):
    with pytest.raises(PassfileError) as exc:
        validate_passfile(config(write_passfile(tmp_path, line + "\n")))
    assert field in str(exc.value)


@pytest.mark.parametrize(
    "line",
    [
        "*:5432:plan_estimate:pe_backup:pw",
        "postgres:*:plan_estimate:pe_backup:pw",
        "postgres:5432:*:pe_backup:pw",
        "postgres:5432:plan_estimate:*:pw",
        "postgres:5432:plan_estimate:pe_backup:*",
    ],
)
def test_wildcards_are_refused(tmp_path, line):
    with pytest.raises(PassfileError) as exc:
        validate_passfile(config(write_passfile(tmp_path, line + "\n")))
    assert "wildcard" in str(exc.value)


@pytest.mark.parametrize(
    "content",
    [
        "",
        "# only a comment\n",
        "postgres:5432:plan_estimate:pe_backup\n",  # 4 fields
        "postgres:5432:plan_estimate:pe_backup:pw:extra\n",  # unescaped ':' in the password
        "postgres:5432:plan_estimate:pe_backup:\n",  # empty password
        "postgres:5432:plan_estimate:pe_backup:pw\\\n",  # backslash
        "postgres:5432:plan_estimate:pe_backup:\\*\n",  # escaped star
        "postgres:5432:plan_estimate:pe_backup:pw \n",  # trailing space (asyncpg strips it)
        "postgres:5432:plan_estimate:pe_backup:p w\tx\n",  # tab
        "postgres:5432:plan_estimate:pe_backup:pw\r\n",  # CR
        ENTRY + "\n" + ENTRY + "\n",  # two entries
        " " + ENTRY + "\n",  # leading space: libpq would not match this host
    ],
)
def test_malformed_passfile_is_refused(tmp_path, content):
    with pytest.raises(PassfileError):
        validate_passfile(config(write_passfile(tmp_path, content)))


def test_password_and_line_are_never_echoed(tmp_path, caplog):
    secret = "Sup3rSecretFakeValue"
    cases = [
        f"postgres:5432:plan_estimate:pe_backup:{secret}:x\n",
        f"otherhost:5432:plan_estimate:pe_backup:{secret}\n",
        f"postgres:5432:plan_estimate:pe_backup:{secret}\n" * 2,
        f"postgres:5432:plan_estimate:pe_backup:{secret}\r\n",
    ]
    for content in cases:
        path = write_passfile(tmp_path, content)
        with pytest.raises(PassfileError) as exc:
            validate_passfile(config(path))
        message = str(exc.value)
        assert secret not in message and "otherhost" not in message and "pe_backup:" not in message
    path = write_passfile(tmp_path, f"postgres:5432:plan_estimate:pe_backup:{secret}\n", mode=0o644)
    with pytest.raises(PassfileError) as exc:
        validate_passfile(config(path))
    assert secret not in str(exc.value)
    assert secret not in caplog.text
    assert stat.S_IMODE(path.stat().st_mode) == 0o644  # validation never changes the file
