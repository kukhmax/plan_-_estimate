"""Stage 14D.2C — backup image preflight entrypoint (no Docker, no database).

Stand-in `pg_dump` / `age` executables on a private PATH provide version
output; the real binaries are proven by the owner's image build.
"""

import io
import os
import sys
from pathlib import Path

import pytest

from app.backup.__main__ import main, run_preflight
from app.backup.layout import BackupLayout, private_dir_problem

R1 = "age1" + "q" * 58
SENTINEL = "PE_PREFLIGHT_SENTINEL_SECRET_VALUE"


def tool(bin_dir: Path, name: str, version_line: str, exit_code: int = 0) -> None:
    script = bin_dir / name
    script.write_text(f"#!{sys.executable}\nimport sys\nprint({version_line!r})\nsys.exit({exit_code})\n")
    script.chmod(0o700)


@pytest.fixture
def bin_dir(tmp_path) -> Path:
    directory = tmp_path / "bin"
    directory.mkdir()
    tool(directory, "pg_dump", "pg_dump (PostgreSQL) 16.15 (Debian 16.15-1.pgdg13+1)")
    tool(directory, "age", "v1.3.2")
    return directory


def workspace(tmp_path: Path) -> BackupLayout:
    layout = BackupLayout(work=tmp_path / "work", encrypted=tmp_path / "encrypted", evidence=tmp_path / "evidence")
    for path in layout.writable_dirs().values():
        path.mkdir(mode=0o700)
    return layout


def passfile(tmp_path: Path, mode: int = 0o600) -> Path:
    path = tmp_path / "pgpass"
    path.write_text(f"postgres:5432:plan_estimate:pe_backup:{SENTINEL}\n")
    path.chmod(mode)
    return path


def full_env(bin_dir: Path, pgpass: Path) -> dict[str, str]:
    return {
        "PATH": str(bin_dir),
        "PGHOST": "postgres",
        "PGPORT": "5432",
        "PGDATABASE": "plan_estimate",
        "PGUSER": "pe_backup",
        "PGPASSFILE": str(pgpass),
        "PGSSLMODE": "disable",
        "BACKUP_AGE_RECIPIENTS": R1,
        "MEDIA_S3_SECRET_ACCESS_KEY": SENTINEL,
        "JWT_SECRET_KEY": SENTINEL,
    }


def run(**kwargs) -> tuple[int, str]:
    out = io.StringIO()
    kwargs.setdefault("python_version", (3, 12))
    kwargs.setdefault("euid", 1000)
    kwargs.setdefault("egid", 1000)
    code = run_preflight(out=out, **kwargs)
    return code, out.getvalue()


def test_tools_preflight_reports_versions_and_identity(bin_dir):
    code, text = run(workspace=False, env={"PATH": str(bin_dir), "JWT_SECRET_KEY": SENTINEL})
    assert code == 0, text
    assert "pg_dump: pg_dump (PostgreSQL) 16.15" in text and str(bin_dir / "pg_dump") in text
    assert "age: v1.3.2" in text
    assert "python: " in text and "expected 3.12.x" in text
    assert "identity: uid=1000 gid=1000" in text
    assert "result: PASS" in text
    assert SENTINEL not in text


@pytest.mark.parametrize(
    ("name", "line"),
    [("pg_dump", "pg_dump (PostgreSQL) 17.6"), ("age", "v1.2.1"), ("age", "1.3.1"), ("age", "garbage")],
)
def test_wrong_tool_versions_fail(bin_dir, name, line):
    tool(bin_dir, name, line)
    code, text = run(workspace=False, env={"PATH": str(bin_dir)})
    assert code == 1 and "result: FAIL" in text


def test_missing_or_failing_tools_fail(bin_dir):
    (bin_dir / "age").unlink()
    tool(bin_dir, "pg_dump", "x", exit_code=3)
    code, text = run(workspace=False, env={"PATH": str(bin_dir)})
    assert code == 1
    assert "FAIL age: not found" in text and "FAIL pg_dump: unusable" in text


def test_root_and_wrong_python_fail(bin_dir):
    assert run(workspace=False, env={"PATH": str(bin_dir)}, euid=0)[0] == 1
    assert run(workspace=False, env={"PATH": str(bin_dir)}, python_version=(3, 14))[0] == 1


def test_workspace_preflight_passes_with_private_mounts_and_valid_passfile(tmp_path, bin_dir):
    layout = workspace(tmp_path)
    env = full_env(bin_dir, passfile(tmp_path))
    code, text = run(workspace=True, env=env, layout=layout, euid=os.geteuid(), egid=os.getegid())
    assert code == 0, text
    assert "connection: host=postgres port=5432 database=plan_estimate user=pe_backup sslmode=disable" in text
    assert "passfile:" in text and "valid" in text
    assert "age recipients: 1 valid public recipient(s)" in text
    assert SENTINEL not in text and R1 not in text  # neither secrets nor recipient values are printed


def test_workspace_preflight_fails_closed_without_leaking(tmp_path, bin_dir):
    layout = workspace(tmp_path)
    layout.evidence.chmod(0o755)
    env = full_env(bin_dir, passfile(tmp_path, mode=0o644))
    env["BACKUP_AGE_RECIPIENTS"] = "AGE-SECRET-KEY-1" + "Q" * 58
    code, text = run(workspace=True, env=env, layout=layout, euid=os.geteuid(), egid=os.getegid())
    assert code == 1
    assert "FAIL mount evidence" in text and "mode broader than 0700" in text
    assert "FAIL passfile" in text and "FAIL age recipients" in text
    assert SENTINEL not in text and "Q" * 20 not in text


def test_workspace_preflight_refuses_password_in_environment(tmp_path, bin_dir):
    layout = workspace(tmp_path)
    env = {**full_env(bin_dir, passfile(tmp_path)), "PGPASSWORD": SENTINEL}
    code, text = run(workspace=True, env=env, layout=layout, euid=os.geteuid(), egid=os.getegid())
    assert code == 1 and "PGPASSWORD" in text and SENTINEL not in text


def test_missing_mounts_are_reported(tmp_path, bin_dir):
    layout = BackupLayout(work=tmp_path / "w", encrypted=tmp_path / "e", evidence=tmp_path / "v")
    code, text = run(workspace=True, env=full_env(bin_dir, passfile(tmp_path)), layout=layout,
                     euid=os.geteuid(), egid=os.getegid())
    assert code == 1 and text.count("missing (not mounted?)") == 3


def test_private_dir_problem(tmp_path):
    good = tmp_path / "good"
    good.mkdir(mode=0o700)
    assert private_dir_problem(good) is None
    link = tmp_path / "link"
    link.symlink_to(good)
    assert private_dir_problem(link) == "is a symlink"
    assert private_dir_problem(good, euid=os.geteuid() + 1) == "not owned by the effective user"
    file = tmp_path / "file"
    file.write_text("")
    assert private_dir_problem(file) == "is not a directory"


def test_default_layout_paths_are_host_independent():
    layout = BackupLayout()
    assert {str(p) for p in layout.writable_dirs().values()} == {
        "/backup/work", "/backup/encrypted", "/backup/evidence"
    }


def test_cli_requires_a_command_and_never_dumps_environment(bin_dir, capsys, monkeypatch):
    with pytest.raises(SystemExit) as exc:
        main([], env={})
    assert exc.value.code == 2
    out = io.StringIO()
    code = main(["preflight"], env={"PATH": str(bin_dir), "SECRET_X": SENTINEL}, out=out)
    assert code in (0, 1)  # python / uid of the test runner decide; output content is what matters
    assert SENTINEL not in out.getvalue() and "SECRET_X" not in out.getvalue()
    assert "PATH" not in out.getvalue()


def test_backup_package_does_not_import_the_web_app():
    import app.backup.__main__ as entry

    source = Path(entry.__file__).read_text()
    for forbidden in ("app.main", "uvicorn", "alembic", "fastapi"):
        assert forbidden not in source
