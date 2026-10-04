"""Stage 14D.2I.1 — restore guards: scratch database and age identity file."""

import os
from pathlib import Path

import pytest

from app.backup.pg_connection import PgConnectionConfig
from app.backup.restore_guards import (
    IdentityFileError,
    UnsafeRestoreDatabaseError,
    validate_identity_file,
    validate_restore_database,
)

KEY_LINE = "AGE-SECRET-KEY-1" + "Q" * 58


def passfile(tmp_path: Path, host: str, database: str, user: str = "pe_user", mode: int = 0o600) -> Path:
    path = tmp_path / "pgpass"
    path.write_text(f"{host}:5432:{database}:{user}:s3cretpassword\n")
    path.chmod(mode)
    return path


def config(tmp_path: Path, *, host: str = "127.0.0.1", database: str = "pe_restore_scratch_01", **kw: object) -> PgConnectionConfig:
    pf = passfile(tmp_path, host, database)
    return PgConnectionConfig(host=host, port=5432, database=database, user="pe_user", passfile=pf, sslmode="disable", **kw)  # type: ignore[arg-type]


# --- scratch database ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("host", ["127.0.0.1", "localhost", "pe-restore-scratch-pg", "SCRATCH-DB"])
def test_a_scratch_database_on_an_acceptable_host_is_accepted(tmp_path: Path, host: str):
    validate_restore_database(config(tmp_path, host=host))


@pytest.mark.parametrize("database", ["plan_estimate", "postgres", "pe_scratch_test_x", "restore_scratch", "PE_RESTORE_SCRATCH"])
def test_a_database_without_the_marker_is_refused(tmp_path: Path, database: str):
    with pytest.raises(UnsafeRestoreDatabaseError, match="pe_restore_scratch"):
        validate_restore_database(config(tmp_path, database=database))


@pytest.mark.parametrize("host", ["postgres", "plan-estimate-postgres", "db.example.com", "10.0.0.5", "pe-proof-pg"])
def test_a_host_that_is_not_loopback_or_scratch_is_refused(tmp_path: Path, host: str):
    with pytest.raises(UnsafeRestoreDatabaseError, match="host"):
        validate_restore_database(config(tmp_path, host=host))


def test_an_explicitly_allowed_host_is_accepted(tmp_path: Path):
    cfg = config(tmp_path, host="pe14d-proof-pg")
    validate_restore_database(cfg, allowed_hosts=["pe14d-proof-pg"])
    with pytest.raises(UnsafeRestoreDatabaseError):
        validate_restore_database(cfg, allowed_hosts=["another-host"])


def test_an_unsafe_pgpass_is_refused_without_its_content(tmp_path: Path):
    cfg = config(tmp_path)
    cfg.passfile.chmod(0o644)
    with pytest.raises(UnsafeRestoreDatabaseError) as excinfo:
        validate_restore_database(cfg)
    assert "s3cretpassword" not in str(excinfo.value) and str(cfg.passfile) not in str(excinfo.value)


def test_messages_never_echo_the_host_or_database(tmp_path: Path):
    with pytest.raises(UnsafeRestoreDatabaseError) as excinfo:
        validate_restore_database(config(tmp_path, host="db.example.com", database="plan_estimate"))
    assert "db.example.com" not in str(excinfo.value) and "plan_estimate" not in str(excinfo.value)


# --- identity file ---------------------------------------------------------------------------------------------


def identity(tmp_path: Path, content: str = KEY_LINE + "\n", mode: int = 0o600, name: str = "identity.txt") -> Path:
    path = tmp_path / name
    path.write_text(content)
    path.chmod(mode)
    return path


def test_a_private_identity_file_is_accepted(tmp_path: Path):
    validate_identity_file(identity(tmp_path))
    validate_identity_file(identity(tmp_path, "# created: 2026-10-04\n# public key: age1xyz\n" + KEY_LINE + "\n", 0o400, "b.txt"))
    validate_identity_file(identity(tmp_path, KEY_LINE + "\r\n", 0o600, "c.txt"))


@pytest.mark.parametrize("mode", [0o640, 0o644, 0o660, 0o604, 0o666])
def test_group_or_other_permissions_are_refused(tmp_path: Path, mode: int):
    with pytest.raises(IdentityFileError, match="permissions"):
        validate_identity_file(identity(tmp_path, mode=mode))


def test_a_relative_path_is_refused():
    with pytest.raises(IdentityFileError, match="absolute"):
        validate_identity_file(Path("identity.txt"))


def test_a_missing_file_is_refused(tmp_path: Path):
    with pytest.raises(IdentityFileError, match="exist"):
        validate_identity_file(tmp_path / "nope.txt")


def test_a_symlink_is_refused(tmp_path: Path):
    real = identity(tmp_path)
    link = tmp_path / "link.txt"
    link.symlink_to(real)
    with pytest.raises(IdentityFileError, match="symlink"):
        validate_identity_file(link)


def test_a_directory_is_refused(tmp_path: Path):
    directory = tmp_path / "dir"
    directory.mkdir(mode=0o700)
    with pytest.raises(IdentityFileError, match="regular"):
        validate_identity_file(directory)


def test_a_file_of_another_owner_is_refused(tmp_path: Path):
    with pytest.raises(IdentityFileError, match="owned"):
        validate_identity_file(identity(tmp_path), euid=os.geteuid() + 1)


@pytest.mark.parametrize(
    "content",
    [
        "",
        "age1" + "q" * 58 + "\n",
        "AGE-SECRET-KEY-1SHORT\n",
        "just some text\n",
        "AGE-SECRET-KEY-1" + "q" * 58 + "\n",  # lower case is not the age secret key alphabet
        "ssh-ed25519 AAAA...\n",
    ],
)
def test_a_file_without_an_age_secret_key_is_refused(tmp_path: Path, content: str):
    with pytest.raises(IdentityFileError):
        validate_identity_file(identity(tmp_path, content))


def test_an_oversized_file_is_refused(tmp_path: Path):
    with pytest.raises(IdentityFileError, match="large"):
        validate_identity_file(identity(tmp_path, KEY_LINE + "\n" + "#" * 70_000))


def test_errors_never_contain_the_key_or_the_path(tmp_path: Path):
    path = identity(tmp_path, "not a key but " + KEY_LINE[:30] + "\n")
    with pytest.raises(IdentityFileError) as excinfo:
        validate_identity_file(path)
    assert KEY_LINE[:20] not in str(excinfo.value) and str(path) not in str(excinfo.value)
