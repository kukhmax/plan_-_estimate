"""Local database backup orchestration (Stage 14D.2D.3).

Sequences the accepted primitives; it reimplements none of them
(docs/STAGE_14D_BACKUP_RESTORE_PLAN.md §16.5):

  A  preflight      connection env == config, passfile valid, pg_dump version probe
  B  lock           RunLock.acquire -- validates the data root (O_NOFOLLOW + fstat)
                    BEFORE opening run.lock inside it
  C  prepare        work/ encrypted/ evidence/ validated / created under the lock
  D  stale check    any entry in work/ -> fail closed, nothing touched
  E  expected head  Alembic ScriptDirectory, offline
  F  run            run_id + private work/<run_id>/            (failure evidence from here on)
  G  snapshot/dump  14D.2A snapshot_bound_dump; its after_export hook imports the
                    exported snapshot on a second connection, reads metadata and
                    enforces observed == expected head BEFORE pg_dump starts
  H  encrypt        14D.2B encrypt_dump_artifact (plaintext unlinked only when durable)
  I  evidence       CompleteRunEvidence -> work/<run_id>/local-run.json (0600, fsynced)
  J  promote        atomic renameat2 work/<run_id> -> encrypted/<run_id>
  K  success

A failure before F has no run_id and therefore no failure evidence. From F
on, any failure (including cancellation) writes best-effort
evidence/<run_id>.failed.json (stage, stable code, three booleans -- never
exception text); a failure to write it never replaces the original failure.
Nothing is retried, cleaned up or moved back; a remaining work/<run_id> is
stale work for the operator. DurabilityError(promoted=True) is reported as
PROMOTION_DURABILITY_UNCONFIRMED (operator inspection), never retried.
"""

import asyncio
import logging
import os
import secrets
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.backup.evidence import (
    ArtifactFacts,
    CompleteRunEvidence,
    DatabaseFacts,
    Diagnostics,
    DumpFacts,
    ErrorCode,
    EvidenceError,
    FailedRunEvidence,
    FailureStage,
    SnapshotFacts,
    error_code_for,
)
from app.backup.pg_connection import PgConnectionConfig, validate_passfile
from app.backup.run_id import new_run_id
from app.backup.schema_revision import (
    DEFAULT_SCRIPT_LOCATION,
    check_revision,
    resolve_expected_head,
)
from app.backup.snapshot_metadata import (
    SnapshotMetadata,
    SnapshotMetadataError,
    read_snapshot_metadata,
)
from app.backup.workspace import (
    PLAINTEXT_DUMP_NAME,
    BackupDataRoot,
    CrossFilesystemError,
    DurabilityError,
    EvidenceWriteError,
    LockHeldError,
    PromotionError,
    RunDirectoryExistsError,
    RunLock,
    RunWorkspace,
    StaleWorkError,
    UnsafeBackupPathError,
)
from app.core.db_dump_encryption import (
    ENCRYPTED_DUMP_NAME,
    PARTIAL_SUFFIX,
    EncryptedDumpResult,
    PlaintextCleanupError,
    encrypt_dump_artifact,
    parse_age_recipients,
)
from app.core.pg_snapshot_dump import (
    PgDumpCommand,
    PgDumpFailedError,
    PgDumpTimeoutError,
    SnapshotDumpResult,
    snapshot_bound_dump,
)
from app.domain.services.media_backup_ready_set import ReadySetFormatError

logger = logging.getLogger(__name__)

TOOL_PROBE_TIMEOUT_SECONDS = 30.0
VERSION_LINE_MAX = 200


class BackupRunFailed(RuntimeError):
    """The backup did not complete. Carries only structured, non-secret facts;
    the original exception is chained as __cause__ (never serialized)."""

    def __init__(self, stage: FailureStage, code: ErrorCode, run_id: str | None) -> None:
        where = f" (run {run_id})" if run_id else ""
        super().__init__(f"backup failed at stage {stage.value}: {code.value}{where}")
        self.stage = stage
        self.code = code
        self.run_id = run_id


class PgDumpToolError(RuntimeError):
    """`pg_dump --version` could not be run or understood."""


@dataclass(frozen=True)
class BackupRunSettings:
    data_root: Path
    connection: PgConnectionConfig
    recipients: tuple[str, ...]
    age_binary: str = "age"
    dump_timeout_seconds: float = 3600.0
    encrypt_timeout_seconds: float = 3600.0
    script_location: Path = DEFAULT_SCRIPT_LOCATION


def settings_from_env(env: Mapping[str, str], data_root: Path) -> BackupRunSettings:
    """Connection from PG* (14D.2C contract), public recipients from
    BACKUP_AGE_RECIPIENTS. Raises the typed configuration errors."""
    return BackupRunSettings(
        data_root=data_root,
        connection=PgConnectionConfig.from_env(env),
        recipients=parse_age_recipients(env.get("BACKUP_AGE_RECIPIENTS", "")),
    )


@dataclass(frozen=True)
class BackupRunResult:
    run_id: str
    run_directory: Path
    evidence: CompleteRunEvidence


def utc_now() -> datetime:
    return datetime.now(UTC)


def new_session_tag() -> str:
    return f"pe-snapshot-{secrets.token_hex(6)}"


async def probe_pg_dump_version(command: PgDumpCommand) -> str:
    """First line of `pg_dump --version` (same tool / environment as the dump)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            *command.version_argv(),
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except OSError:
        raise PgDumpToolError("pg_dump could not be started") from None
    try:
        async with asyncio.timeout(TOOL_PROBE_TIMEOUT_SECONDS):
            stdout, _ = await proc.communicate()
    except BaseException:
        if proc.returncode is None:
            proc.kill()
        await asyncio.shield(proc.wait())
        raise
    lines = stdout.decode("ascii", errors="replace").strip().splitlines()
    if proc.returncode != 0 or not lines or len(lines[0]) > VERSION_LINE_MAX:
        raise PgDumpToolError("pg_dump --version failed or was not understood")
    return lines[0].strip()


@dataclass
class BackupDependencies:
    """Injection seams (tests replace them); defaults are the real primitives."""

    snapshot_dump: Callable[..., Awaitable[SnapshotDumpResult]] = snapshot_bound_dump
    encrypt: Callable[..., Awaitable[EncryptedDumpResult]] = encrypt_dump_artifact
    read_metadata: Callable[..., Awaitable[SnapshotMetadata]] = read_snapshot_metadata
    resolve_head: Callable[[Path], str] = resolve_expected_head
    pg_dump_version: Callable[[PgDumpCommand], Awaitable[str]] = probe_pg_dump_version
    validate_passfile: Callable[[PgConnectionConfig], None] = validate_passfile
    clock: Callable[[], datetime] = utc_now
    run_id_factory: Callable[[datetime], str] = new_run_id
    session_tag_factory: Callable[[], str] = new_session_tag
    process_env: Mapping[str, str] = field(default_factory=lambda: os.environ)


@dataclass
class _RunState:
    stage: FailureStage = FailureStage.PREFLIGHT
    run_id: str | None = None
    started_at: datetime | None = None
    snapshot_id: str | None = None
    snapshot_exported_at: datetime | None = None
    metadata: SnapshotMetadata | None = None
    encrypted: EncryptedDumpResult | None = None
    promoted: bool = False


def failure_code(exc: BaseException) -> ErrorCode:
    """Stable code by exception type (and the typed `promoted` flag) -- never by message."""
    if isinstance(exc, DurabilityError):
        return ErrorCode.PROMOTION_DURABILITY_UNCONFIRMED if exc.promoted else ErrorCode.PROMOTION_NOT_DURABLE
    for kind, code in (
        (LockHeldError, ErrorCode.LOCK_HELD),
        (StaleWorkError, ErrorCode.STALE_WORK),
        (RunDirectoryExistsError, ErrorCode.RUN_DIRECTORY_EXISTS),
        (CrossFilesystemError, ErrorCode.CROSS_FILESYSTEM),
        (PromotionError, ErrorCode.PROMOTION_FAILED),
        (EvidenceWriteError, ErrorCode.EVIDENCE_WRITE_FAILED),
        (UnsafeBackupPathError, ErrorCode.WORKSPACE_UNSAFE),
        (SnapshotMetadataError, ErrorCode.SNAPSHOT_METADATA_INVALID),
        (PgDumpToolError, ErrorCode.PG_DUMP_TOOL_UNUSABLE),
        (EvidenceError, ErrorCode.EVIDENCE_INVALID),
    ):
        if isinstance(exc, kind):
            return code
    return error_code_for(exc)


def _failure_stage(state: _RunState, exc: BaseException) -> FailureStage:
    if isinstance(exc, PgDumpFailedError | PgDumpTimeoutError):
        return FailureStage.DUMP
    if isinstance(exc, ReadySetFormatError):
        return FailureStage.SNAPSHOT
    return state.stage


class BackupOrchestrator:
    def __init__(self, settings: BackupRunSettings, deps: BackupDependencies | None = None) -> None:
        self.settings = settings
        self.deps = deps or BackupDependencies()
        self.data_root = BackupDataRoot(settings.data_root)

    async def run(self) -> BackupRunResult:
        state = _RunState()
        try:
            # A -- preflight (no run_id yet)
            connection = self.settings.connection
            connection.check_process_env(self.deps.process_env)
            self.deps.validate_passfile(connection)
            command = connection.pg_dump_command()
            pg_dump_version = await self.deps.pg_dump_version(command)
            # B -- lock (the root is validated before run.lock is opened in it);
            # released by the context manager on every exit, including cancellation
            with RunLock.acquire(self.data_root):
                return await self._locked_run(state, connection, command, pg_dump_version)
        except (BackupRunFailed, asyncio.CancelledError):
            raise
        except Exception as exc:  # before a run exists: structured failure, no evidence
            raise BackupRunFailed(FailureStage.PREFLIGHT, failure_code(exc), None) from exc

    async def _locked_run(
        self, state: _RunState, connection: PgConnectionConfig, command: PgDumpCommand, pg_dump_version: str
    ) -> BackupRunResult:
        # C, D, E -- still no run_id: failures here leave no evidence
        self.data_root.prepare()
        self.data_root.assert_no_stale_work()
        expected_head = self.deps.resolve_head(self.settings.script_location)

        # F -- the run exists from here on
        state.started_at = self.deps.clock()
        run_id = self.deps.run_id_factory(state.started_at)
        workspace = self.data_root.create_run(run_id)
        state.run_id = run_id
        try:
            return await self._run(state, workspace, connection, command, pg_dump_version, expected_head)
        except BaseException as exc:
            stage = _failure_stage(state, exc)
            code = ErrorCode.CANCELLED if isinstance(exc, asyncio.CancelledError) else failure_code(exc)
            self._record_failure(state, stage, code)
            if isinstance(exc, asyncio.CancelledError):
                raise
            raise BackupRunFailed(stage, code, run_id) from exc

    async def _run(
        self,
        state: _RunState,
        workspace: RunWorkspace,
        connection: PgConnectionConfig,
        command: PgDumpCommand,
        pg_dump_version: str,
        expected_head: str,
    ) -> BackupRunResult:
        deps, dsn = self.deps, connection.asyncpg_dsn()
        session_tag = deps.session_tag_factory()

        async def after_export(snapshot_id: str) -> None:
            # Runs inside 14D.2A while the exporter transaction is open, before
            # the READY inventory and before pg_dump.
            state.snapshot_exported_at = deps.clock()
            state.snapshot_id = snapshot_id
            state.metadata = await deps.read_metadata(dsn, snapshot_id, session_tag)
            state.stage = FailureStage.SCHEMA_REVISION
            check_revision(state.metadata.alembic_revision, expected_head)
            state.stage = FailureStage.SNAPSHOT

        # G -- snapshot-bound dump
        state.stage = FailureStage.SNAPSHOT
        dump = await deps.snapshot_dump(
            dsn,
            command,
            workspace.plaintext_dump,
            timeout_seconds=self.settings.dump_timeout_seconds,
            session_tag=session_tag,
            after_export=after_export,
        )
        dump_completed_at = deps.clock()
        metadata = state.metadata
        if metadata is None or state.snapshot_id is None or state.snapshot_exported_at is None:
            raise SnapshotMetadataError("the snapshot metadata hook did not run")
        if metadata.server_version_num // 10000 != dump.server_major_version:
            raise SnapshotMetadataError("metadata and exporter report different server major versions")

        # H -- encrypt (14D.2B); PlaintextCleanupError = artifact valid, plaintext present -> run fails
        state.stage = FailureStage.ENCRYPT
        try:
            encrypted = await deps.encrypt(
                dump,
                self.settings.recipients,
                age_binary=self.settings.age_binary,
                timeout_seconds=self.settings.encrypt_timeout_seconds,
            )
        except PlaintextCleanupError as exc:
            state.encrypted = exc.result
            raise
        state.encrypted = encrypted

        # I -- complete evidence, written durably BEFORE promotion
        state.stage = FailureStage.EVIDENCE
        assert state.started_at is not None
        evidence = CompleteRunEvidence(
            run_id=workspace.run_id,
            started_at=state.started_at,
            snapshot_exported_at=state.snapshot_exported_at,
            dump_completed_at=dump_completed_at,
            completed_at=deps.clock(),
            database=DatabaseFacts(
                name=metadata.database_name,
                server_version=metadata.server_version,
                server_version_num=metadata.server_version_num,
                alembic_revision=metadata.alembic_revision,
                expected_alembic_head=expected_head,
                photo_asset_status_counts=dict(metadata.photo_asset_status_counts),
            ),
            snapshot=SnapshotFacts(ready_count=dump.ready.ready_count, ready_set_sha256=dump.ready.ready_set_sha256),
            dump=DumpFacts(
                pg_dump_version=pg_dump_version, plaintext_sha256=dump.dump_sha256, plaintext_size=dump.dump_size
            ),
            artifact=ArtifactFacts(
                sha256=encrypted.artifact_sha256,
                size=encrypted.artifact_size,
                age_version=encrypted.age_version,
                recipient_count=len(encrypted.recipients),
            ),
            diagnostics=Diagnostics(snapshot_id=state.snapshot_id, session_tag=session_tag),
        )
        self.data_root.write_run_evidence(workspace.run_id, evidence.to_canonical_json())

        # J -- promotion is the last step
        state.stage = FailureStage.PROMOTE
        try:
            destination = self.data_root.promote(workspace.run_id)
        except DurabilityError as exc:
            state.promoted = exc.promoted
            raise
        state.promoted = True
        return BackupRunResult(run_id=workspace.run_id, run_directory=destination, evidence=evidence)

    def _record_failure(self, state: _RunState, stage: FailureStage, code: ErrorCode) -> None:
        """Best effort: evidence/<run_id>.failed.json. Never raises; never
        replaces the original failure."""
        assert state.run_id is not None and state.started_at is not None
        try:
            names = self.data_root.run_entry_names(state.run_id, promoted=state.promoted)
            record = FailedRunEvidence(
                run_id=state.run_id,
                started_at=state.started_at,
                failed_at=max(self.deps.clock(), state.started_at),
                stage=stage,
                error_code=code,
                plaintext_retained=PLAINTEXT_DUMP_NAME in names,
                artifact_valid=state.encrypted is not None and ENCRYPTED_DUMP_NAME in names,
                partials_present=any(name.endswith(PARTIAL_SUFFIX) for name in names),
            )
            self.data_root.write_failure_evidence(state.run_id, record.to_canonical_json())
        except Exception as exc:  # noqa: BLE001 - best effort: the backup failure stays primary; type logged
            logger.error("failure evidence for run %s could not be written: %s", state.run_id, type(exc).__name__)
