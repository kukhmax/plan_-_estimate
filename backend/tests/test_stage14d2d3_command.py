"""Stage 14D.2D.3 — `python -m app.backup db-dump` exit codes and signal handling."""

import asyncio
import io
import json
import os
import signal

import pytest

from app.backup.__main__ import main
from app.backup.db_dump_command import (
    EXIT_FAILED,
    EXIT_INTERRUPTED,
    EXIT_LOCK_HELD,
    EXIT_PREFLIGHT,
    EXIT_PROMOTION_UNCONFIRMED,
    EXIT_STALE_WORK,
    EXIT_SUCCESS,
    exit_code_for,
    run_cancellable,
    run_db_dump,
)
from app.backup.evidence import ErrorCode, FailureStage
from app.backup.orchestrator import BackupDependencies, BackupRunFailed
from app.backup.workspace import BackupDataRoot
from tests.test_stage14d2d3_orchestrator import (
    FAKE_PASSWORD,
    RECIPIENT,
    TAG,
    Clock,
    Harness,
)

RUN = "20261003T081500Z-3f9a1c2e"


@pytest.mark.parametrize(
    ("code", "run_id", "expected"),
    [
        (ErrorCode.LOCK_HELD, None, EXIT_LOCK_HELD),
        (ErrorCode.STALE_WORK, None, EXIT_STALE_WORK),
        (ErrorCode.CONFIGURATION_INVALID, None, EXIT_PREFLIGHT),
        (ErrorCode.PASSFILE_INVALID, None, EXIT_PREFLIGHT),
        (ErrorCode.SCHEMA_HEAD_UNRESOLVED, None, EXIT_PREFLIGHT),
        (ErrorCode.PG_DUMP_TOOL_UNUSABLE, None, EXIT_PREFLIGHT),
        (ErrorCode.WORKSPACE_UNSAFE, None, EXIT_PREFLIGHT),
        (ErrorCode.WORKSPACE_UNSAFE, RUN, EXIT_FAILED),
        (ErrorCode.PG_DUMP_FAILED, RUN, EXIT_FAILED),
        (ErrorCode.SCHEMA_REVISION_MISMATCH, RUN, EXIT_FAILED),
        (ErrorCode.PROMOTION_NOT_DURABLE, RUN, EXIT_FAILED),
        (ErrorCode.PROMOTION_DURABILITY_UNCONFIRMED, RUN, EXIT_PROMOTION_UNCONFIRMED),
        (ErrorCode.UNEXPECTED_ERROR, None, EXIT_FAILED),
    ],
)
def test_exit_code_mapping(code, run_id, expected):
    assert exit_code_for(BackupRunFailed(FailureStage.PREFLIGHT, code, run_id)) == expected


def env_for(tmp_path) -> dict[str, str]:
    passfile = tmp_path / "pgpass"
    passfile.write_text(f"postgres:5432:plan_estimate:pe_backup:{FAKE_PASSWORD}\n")
    passfile.chmod(0o600)
    return {
        "PGHOST": "postgres",
        "PGPORT": "5432",
        "PGDATABASE": "plan_estimate",
        "PGUSER": "pe_backup",
        "PGPASSFILE": str(passfile),
        "PGSSLMODE": "disable",
        "BACKUP_AGE_RECIPIENTS": RECIPIENT,
    }


def deps_for(harness: Harness, env: dict[str, str]) -> BackupDependencies:
    return BackupDependencies(
        snapshot_dump=harness.snapshot_dump,
        encrypt=harness.encrypt,
        read_metadata=harness.read_metadata,
        resolve_head=harness.resolve_head,
        pg_dump_version=harness.pg_dump_version,
        clock=Clock(),
        session_tag_factory=lambda: TAG,
        process_env={k: v for k, v in env.items() if k.startswith("PG")},
    )


@pytest.fixture
def root(tmp_path):
    path = tmp_path / "data"
    path.mkdir(mode=0o700)
    return path


def test_db_dump_success_exit_and_summary(tmp_path, root):
    env = env_for(tmp_path)
    out = io.StringIO()
    code = run_db_dump(env, out, data_root=root, deps=deps_for(Harness(root), env))
    assert code == EXIT_SUCCESS
    text = out.getvalue()
    assert text.startswith("backup complete: run_id=") and "ready_count=3" in text
    assert FAKE_PASSWORD not in text and RECIPIENT not in text and "pgpass" not in text


def test_db_dump_failure_exit_and_summary(tmp_path, root):
    env = env_for(tmp_path)
    harness = Harness(root)
    harness.observed_revision = "0031_photo_assets"
    out = io.StringIO()
    assert run_db_dump(env, out, data_root=root, deps=deps_for(harness, env)) == EXIT_FAILED
    assert "backup failed: stage=schema_revision code=SCHEMA_REVISION_MISMATCH run_id=" in out.getvalue()


def test_db_dump_lock_and_stale_exits(tmp_path, root):
    env = env_for(tmp_path)
    data = BackupDataRoot(root)
    data.prepare()
    with data.acquire_lock():
        assert run_db_dump(env, io.StringIO(), data_root=root, deps=deps_for(Harness(root), env)) == EXIT_LOCK_HELD
    (root / "work" / RUN).mkdir(mode=0o700)
    assert run_db_dump(env, io.StringIO(), data_root=root, deps=deps_for(Harness(root), env)) == EXIT_STALE_WORK
    assert (root / "work" / RUN).is_dir()


@pytest.mark.parametrize(
    "change",
    [{"PGHOST": None}, {"BACKUP_AGE_RECIPIENTS": None}, {"PGPASSWORD": FAKE_PASSWORD},
     {"BACKUP_AGE_RECIPIENTS": "AGE-SECRET-KEY-1" + "Q" * 58}],
    ids=["missing-host", "missing-recipients", "password-in-env", "secret-key-as-recipient"],
)
def test_db_dump_configuration_errors_exit_preflight_without_leaking(tmp_path, root, change):
    env = env_for(tmp_path)
    for key, value in change.items():
        if value is None:
            del env[key]
        else:
            env[key] = value
    out = io.StringIO()
    assert run_db_dump(env, out, data_root=root, deps=deps_for(Harness(root), env)) == EXIT_PREFLIGHT
    assert FAKE_PASSWORD not in out.getvalue() and "Q" * 20 not in out.getvalue()
    assert not (root / "run.lock").exists()


def test_db_dump_promotion_unconfirmed_exit(tmp_path, root, monkeypatch):
    import app.backup.workspace as ws

    env = env_for(tmp_path)
    real = ws.BackupDataRoot.promote

    def promote(self, run_id):
        real(self, run_id)
        raise ws.DurabilityError("simulated", promoted=True)

    monkeypatch.setattr(ws.BackupDataRoot, "promote", promote)
    out = io.StringIO()
    assert run_db_dump(env, out, data_root=root, deps=deps_for(Harness(root), env)) == EXIT_PROMOTION_UNCONFIRMED
    assert "operator inspection required" in out.getvalue()


def test_sigterm_cancels_the_run_cleanly(tmp_path, root):
    env = env_for(tmp_path)
    harness = Harness(root)
    original = harness.snapshot_dump

    async def dump_then_sigterm(*args, **kwargs):
        async def send():
            await asyncio.sleep(0.05)
            os.kill(os.getpid(), signal.SIGTERM)

        asyncio.get_running_loop().create_task(send())
        harness.block_dump = True
        return await original(*args, **kwargs)

    deps = deps_for(harness, env)
    deps.snapshot_dump = dump_then_sigterm
    previous = signal.getsignal(signal.SIGTERM)
    out = io.StringIO()
    assert run_db_dump(env, out, data_root=root, deps=deps) == EXIT_INTERRUPTED
    assert signal.getsignal(signal.SIGTERM) == previous  # handler removed again
    assert "backup interrupted" in out.getvalue()
    (evidence,) = list((root / "evidence").iterdir())
    assert json.loads(evidence.read_bytes())["failure"]["error_code"] == "CANCELLED"
    assert list((root / "encrypted").iterdir()) == []
    with BackupDataRoot(root).acquire_lock():  # lock released
        pass


async def test_run_cancellable_returns_results_and_removes_handlers():
    async def work():
        return 42

    assert await run_cancellable(work, (signal.SIGUSR1,)) == 42
    assert signal.getsignal(signal.SIGUSR1) in (signal.SIG_DFL, signal.default_int_handler)


def test_main_dispatches_db_dump_and_keeps_preflight(tmp_path, root):
    out = io.StringIO()
    assert main(["db-dump"], env={}, out=out) == EXIT_PREFLIGHT  # no configuration -> no run
    assert "backup preflight failed" in out.getvalue()
    out = io.StringIO()
    assert main(["preflight"], env={"PATH": "/nonexistent"}, out=out) in (0, 1)
    assert "pg_dump" in out.getvalue()
    with pytest.raises(SystemExit) as exc:
        main(["db-dump", "--unknown"], env={})
    assert exc.value.code == 2
