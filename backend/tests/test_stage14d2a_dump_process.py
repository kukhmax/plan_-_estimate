"""Stage 14D.2A — pg_dump command construction and subprocess handling.

Process-level behaviour of `run_dump_process` (exit status, completion
marker, timeout, cancellation, partial-file and child cleanup) is exercised
with small Python stand-in processes, so no PostgreSQL is needed here. The
real pg_dump / snapshot behaviour is proven in test_stage14d2a_postgres.py.
"""

import asyncio
import contextlib
import os
import stat
import sys
from pathlib import Path

import pytest

from app.core.pg_snapshot_dump import (
    DUMP_COMPLETE_MARKER,
    PgDumpCommand,
    PgDumpFailedError,
    PgDumpTimeoutError,
    PgDumpVersionMismatchError,
    SnapshotDumpError,
    parse_pg_dump_major,
    run_dump_process,
)

COMPLETE_DUMP = b"--\n-- PostgreSQL database dump\n--\nSELECT 1;\n--\n" + DUMP_COMPLETE_MARKER + b"\n--\n\n"


def py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def writes(data: bytes, exit_code: int = 0, stderr: str = "") -> list[str]:
    return py(
        f"import sys; sys.stdout.buffer.write({data!r}); sys.stdout.flush(); sys.stderr.write({stderr!r});"
        f" sys.exit({exit_code:d})"
    )


def child_pids() -> list[int]:
    """Direct children of this process (any state, zombies included)."""
    found = []
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/stat") as fh:
                fields = fh.read().rsplit(")", 1)[1].split()
        except OSError:
            continue
        if int(fields[1]) == os.getpid():
            found.append(int(entry))
    return found


def no_leftovers(out: Path) -> bool:
    return not out.exists() and not out.with_name(out.name + ".partial").exists()


# --- command construction -------------------------------------------------------------


def test_dump_argv_uses_prefix_tag_and_snapshot():
    cmd = PgDumpCommand(prefix=("docker", "exec", "-i", "pg"), username="pe", dbname="pe_db", lock_wait_timeout_ms=5000)
    assert cmd.dump_argv("00000003-0000001B-1", "pe-snapshot-abc123-dump") == [
        "docker", "exec", "-i", "pg", "env", "PGAPPNAME=pe-snapshot-abc123-dump", "pg_dump", "--format=plain",
        "--no-password", "--snapshot=00000003-0000001B-1", "--username=pe", "--dbname=pe_db",
        "--lock-wait-timeout=5000",
    ]
    assert cmd.version_argv() == ["docker", "exec", "-i", "pg", "pg_dump", "--version"]


@pytest.mark.parametrize("snapshot", ["", "x; rm -rf /", "00000003-0000001b-1", "1-2", "1-2-3 --help", "--help"])
def test_dump_argv_refuses_unexpected_snapshot_ids(snapshot):
    with pytest.raises(SnapshotDumpError):
        PgDumpCommand(prefix=(), username="pe", dbname="d").dump_argv(snapshot, "pe-snapshot-abc123-dump")


@pytest.mark.parametrize("app", ["", "UPPER-case-tag", "tag with space", "x" * 60])
def test_dump_argv_refuses_unexpected_application_names(app):
    with pytest.raises(SnapshotDumpError):
        PgDumpCommand(prefix=(), username="pe", dbname="d").dump_argv("1-2-3", app)


@pytest.mark.parametrize(
    ("output", "major"),
    [
        ("pg_dump (PostgreSQL) 16.4\n", 16),
        ("pg_dump (PostgreSQL) 16.10 (Debian 16.10-1.pgdg120+1)\n", 16),
        ("pg_dump (PostgreSQL) 17.0\n", 17),
        ("pg_dump (PostgreSQL) 18beta1\n", 18),
    ],
)
def test_parse_pg_dump_major(output, major):
    assert parse_pg_dump_major(output) == major


def test_parse_pg_dump_major_rejects_garbage():
    with pytest.raises(PgDumpVersionMismatchError):
        parse_pg_dump_major("something else")


# --- process handling -------------------------------------------------------------------


async def test_success_renames_partial_to_output(tmp_path):
    out = tmp_path / "db.sql"
    await run_dump_process(writes(COMPLETE_DUMP), out, timeout_seconds=30)
    assert out.read_bytes() == COMPLETE_DUMP
    assert not out.with_name("db.sql.partial").exists()
    assert child_pids() == []


async def test_nonzero_exit_is_a_controlled_error_and_leaves_nothing(tmp_path):
    out = tmp_path / "db.sql"
    with pytest.raises(PgDumpFailedError) as exc:
        await run_dump_process(writes(b"-- partial", 3, "pg_dump: error: boom"), out, timeout_seconds=30)
    assert exc.value.returncode == 3 and "boom" in exc.value.stderr_tail
    assert no_leftovers(out) and child_pids() == []


async def test_zero_exit_without_completion_marker_is_rejected(tmp_path):
    out = tmp_path / "db.sql"
    with pytest.raises(PgDumpFailedError):
        await run_dump_process(writes(b"--\n-- PostgreSQL database dump\nSELECT 1;\n"), out, timeout_seconds=30)
    assert no_leftovers(out)


async def test_empty_output_is_rejected(tmp_path):
    out = tmp_path / "db.sql"
    with pytest.raises(PgDumpFailedError):
        await run_dump_process(writes(b""), out, timeout_seconds=30)
    assert no_leftovers(out)


async def test_stderr_tail_is_bounded(tmp_path):
    out = tmp_path / "db.sql"
    with pytest.raises(PgDumpFailedError) as exc:
        await run_dump_process(writes(b"", 1, "e" * 10_000 + "END"), out, timeout_seconds=30)
    assert len(exc.value.stderr_tail) == 2000 and exc.value.stderr_tail.endswith("END")


async def test_timeout_kills_and_reaps_the_child(tmp_path):
    out = tmp_path / "db.sql"
    argv = py("import sys, time; sys.stdout.write('-- started'); sys.stdout.flush(); time.sleep(60)")
    with pytest.raises(PgDumpTimeoutError):
        await run_dump_process(argv, out, timeout_seconds=0.5)
    assert no_leftovers(out)
    assert child_pids() == []  # killed and reaped: no zombie


async def test_cancellation_kills_and_reaps_the_child(tmp_path):
    out = tmp_path / "db.sql"
    task = asyncio.create_task(run_dump_process(py("import time; time.sleep(60)"), out, timeout_seconds=60))
    await asyncio.sleep(0.5)
    assert len(child_pids()) == 1
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert no_leftovers(out) and child_pids() == []


async def test_refuses_to_overwrite_existing_output_or_partial(tmp_path):
    out = tmp_path / "db.sql"
    out.write_bytes(b"old")
    with pytest.raises(SnapshotDumpError):
        await run_dump_process(writes(COMPLETE_DUMP), out, timeout_seconds=30)
    assert out.read_bytes() == b"old"
    other = tmp_path / "db2.sql"
    other.with_name("db2.sql.partial").write_bytes(b"stale")
    with pytest.raises(SnapshotDumpError):
        await run_dump_process(writes(COMPLETE_DUMP), other, timeout_seconds=30)
    assert not other.exists()


async def test_missing_executable_is_an_error_without_leftovers(tmp_path):
    out = tmp_path / "db.sql"
    with pytest.raises(FileNotFoundError):
        await run_dump_process(["/nonexistent/pg_dump"], out, timeout_seconds=30)
    assert no_leftovers(out)


# --- private file mode (0600 regardless of umask) -----------------------------------------


@contextlib.contextmanager
def process_umask(value: int):
    """Test-only: run with a given umask and restore it afterwards."""
    previous = os.umask(value)
    try:
        yield
    finally:
        os.umask(previous)


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


@pytest.mark.parametrize("umask", [0o000, 0o002, 0o022, 0o277])
async def test_final_dump_is_0600_whatever_the_umask(tmp_path, umask):
    out = tmp_path / "db.sql"
    with process_umask(umask):
        await run_dump_process(writes(COMPLETE_DUMP), out, timeout_seconds=30)
    assert mode(out) == 0o600
    assert out.read_bytes() == COMPLETE_DUMP


async def test_partial_dump_is_0600_while_being_written_under_a_permissive_umask(tmp_path):
    out = tmp_path / "db.sql"
    partial = tmp_path / "db.sql.partial"
    argv = py(
        "import sys, time; sys.stdout.buffer.write(b'-- started\\n'); sys.stdout.flush(); time.sleep(1.0);"
        f" sys.stdout.buffer.write({COMPLETE_DUMP!r}); sys.stdout.flush()"
    )
    with process_umask(0o000):
        task = asyncio.create_task(run_dump_process(argv, out, timeout_seconds=30))
        observed = None
        for _ in range(100):
            if partial.exists() and partial.stat().st_size > 0:
                observed = mode(partial)
                break
            await asyncio.sleep(0.01)
        await task
    assert observed == 0o600  # never group/world readable, even mid-write
    assert mode(out) == 0o600 and not partial.exists()


async def test_failure_under_a_permissive_umask_still_leaves_nothing(tmp_path):
    out = tmp_path / "db.sql"
    with process_umask(0o000), pytest.raises(PgDumpFailedError):
        await run_dump_process(writes(b"-- partial", 2), out, timeout_seconds=30)
    assert no_leftovers(out)


async def test_existing_file_refusal_unchanged_under_a_permissive_umask(tmp_path):
    out = tmp_path / "db.sql"
    out.write_bytes(b"old")
    with process_umask(0o000), pytest.raises(SnapshotDumpError):
        await run_dump_process(writes(COMPLETE_DUMP), out, timeout_seconds=30)
    assert out.read_bytes() == b"old"


# --- scratch tool-prefix guard (used by the opt-in PostgreSQL proof) --------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("docker exec -i pe-scratch-14d2a", ("docker", "exec", "-i", "pe-scratch-14d2a")),
        ("docker exec pe-scratch-x", ("docker", "exec", "pe-scratch-x")),
    ],
)
def test_scratch_tool_prefix_accepts_docker_exec_into_a_scratch_container(raw, expected):
    from tests.pg_scratch_guard import scratch_tool_prefix

    assert scratch_tool_prefix(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "docker exec -i plan_estimate_postgres",  # the production container
        "docker run -i pe-scratch",
        "docker exec -u root pe-scratch",
        "ssh host docker exec -i pe-scratch",
        "docker exec",
        "docker exec -i -scratch",
    ],
)
def test_scratch_tool_prefix_rejects_anything_else(raw):
    from tests.pg_scratch_guard import UnsafeScratchDatabaseError, scratch_tool_prefix

    with pytest.raises(UnsafeScratchDatabaseError):
        scratch_tool_prefix(raw)


def test_scratch_tool_prefix_unset_means_opt_out(monkeypatch):
    from tests.pg_scratch_guard import scratch_tool_prefix

    monkeypatch.delenv("TEST_PG_TOOL_PREFIX", raising=False)
    assert scratch_tool_prefix() is None
