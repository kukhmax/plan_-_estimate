"""`python -m app.backup db-dump` (Stage 14D.2D.3).

Runs the local database backup orchestration once, with SIGTERM / SIGINT
cancelling the top-level task so the 14D.2A / 14D.2B protected cleanup runs
(no os._exit). Output is a short structured summary: no environment, DSN,
password, recipients or exception text.

Exit codes:
    0  success (run promoted to encrypted/<run_id>)
    1  backup failed (see stage / code; failure evidence if a run existed)
    2  usage error (argparse)
    3  lock held (another run is active; nothing touched)
    4  stale work present in work/ (manual inspection; nothing touched)
    5  preflight / configuration failure (no run started)
    6  interrupted (SIGTERM / SIGINT); remaining work stays for the operator
    7  promotion durability unconfirmed: encrypted/<run_id> may exist -- operator
       inspection required, never re-promote or re-run blindly
"""

import asyncio
import signal
from collections.abc import Awaitable, Callable, Mapping
from pathlib import Path
from typing import TextIO, TypeVar

from app.backup.evidence import ErrorCode
from app.backup.layout import CONTAINER_DATA_ROOT
from app.backup.orchestrator import (
    BackupDependencies,
    BackupOrchestrator,
    BackupRunFailed,
    BackupRunResult,
    settings_from_env,
)
from app.backup.pg_connection import PgConnectionConfigError
from app.core.db_dump_encryption import AgeRecipientError

EXIT_SUCCESS = 0
EXIT_FAILED = 1
EXIT_USAGE = 2
EXIT_LOCK_HELD = 3
EXIT_STALE_WORK = 4
EXIT_PREFLIGHT = 5
EXIT_INTERRUPTED = 6
EXIT_PROMOTION_UNCONFIRMED = 7

PREFLIGHT_CODES = frozenset(
    {
        ErrorCode.CONFIGURATION_INVALID,
        ErrorCode.PASSFILE_INVALID,
        ErrorCode.AGE_RECIPIENT_INVALID,
        ErrorCode.WORKSPACE_UNSAFE,
        ErrorCode.SCHEMA_HEAD_UNRESOLVED,
        ErrorCode.PG_DUMP_TOOL_UNUSABLE,
    }
)

T = TypeVar("T")


def exit_code_for(failure: BackupRunFailed) -> int:
    if failure.code is ErrorCode.LOCK_HELD:
        return EXIT_LOCK_HELD
    if failure.code is ErrorCode.STALE_WORK:
        return EXIT_STALE_WORK
    if failure.code is ErrorCode.PROMOTION_DURABILITY_UNCONFIRMED:
        return EXIT_PROMOTION_UNCONFIRMED
    if failure.run_id is None and failure.code in PREFLIGHT_CODES:
        return EXIT_PREFLIGHT
    return EXIT_FAILED


async def run_cancellable(make: Callable[[], Awaitable[T]], signals: tuple[int, ...]) -> T:
    """Run `make()` as a task that SIGTERM / SIGINT cancel (handlers removed afterwards)."""
    loop = asyncio.get_running_loop()
    task = asyncio.ensure_future(make())
    installed = []
    for sig in signals:
        loop.add_signal_handler(sig, task.cancel)
        installed.append(sig)
    try:
        return await task
    finally:
        for sig in installed:
            loop.remove_signal_handler(sig)


def _report_success(result: BackupRunResult, out: TextIO) -> None:
    artifact = result.evidence.artifact
    print(
        f"backup complete: run_id={result.run_id} ready_count={result.evidence.snapshot.ready_count}"
        f" artifact_sha256={artifact.sha256} artifact_size={artifact.size}",
        file=out,
    )


def _report_failure(failure: BackupRunFailed, out: TextIO) -> None:
    print(f"backup failed: stage={failure.stage.value} code={failure.code.value} run_id={failure.run_id or '-'}", file=out)
    if failure.code is ErrorCode.PROMOTION_DURABILITY_UNCONFIRMED:
        print(
            "operator inspection required: encrypted/<run_id> may exist but durable promotion is unconfirmed;"
            " do not re-promote or re-run blindly",
            file=out,
        )


def run_db_dump(
    env: Mapping[str, str],
    out: TextIO,
    *,
    data_root: Path = CONTAINER_DATA_ROOT,
    deps: BackupDependencies | None = None,
    signals: tuple[int, ...] = (signal.SIGTERM, signal.SIGINT),
) -> int:
    try:
        settings = settings_from_env(env, data_root)
    except (PgConnectionConfigError, AgeRecipientError) as exc:
        # These messages are value-free by design (names / positions only).
        print(f"backup preflight failed: {exc}", file=out)
        return EXIT_PREFLIGHT
    orchestrator = BackupOrchestrator(settings, deps)
    try:
        result = asyncio.run(run_cancellable(orchestrator.run, signals))
    except asyncio.CancelledError:
        print("backup interrupted: remaining work (if any) is left in work/ for the operator", file=out)
        return EXIT_INTERRUPTED
    except BackupRunFailed as failure:
        _report_failure(failure, out)
        return exit_code_for(failure)
    _report_success(result, out)
    return EXIT_SUCCESS
