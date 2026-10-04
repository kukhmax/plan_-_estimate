"""The whole restore of a sealed run: seal -> database -> READY set -> media -- Stage 14D.2I.3.

Contract: docs/STAGE_14D_BACKUP_RESTORE_PLAN.md §9-§11, §16.15.

`restore_run` composes the accepted pieces in the only order that makes sense and stops at the first step that did
not succeed, so a failed step is never followed by one that depends on it:

    seal       `runs/<run_id>/COMPLETE.json` + `manifest.jsonl` are read from the backup target and accepted by
               `verify_run` (the run is complete and consistent)                                        [14D.2E]
    database   `restore_database`: guards, artifact, age -> gunzip -> psql behind the commit gate, then the
               Alembic / READY-set / status-count checks                                              [14D.2I.1]
    ready set  the READY set is read back from the RESTORED database                                   [14D.2I.1]
    media      `restore_media` with that READY set: the manifest must describe it, then every object is copied
               from the backup, verified and never overwritten                                         [14D.2I.2]

`phase` splits the chain at the READY-set boundary so that the operator can run the integrity checker between the two
halves (plan §11 step 5: with the database restored and the destination still empty, exactly the expected objects are
missing): `database` = seal + database, `media` = seal + READY set of the ALREADY restored database + media (the media
step refuses a database that does not match the manifest), `all` = the whole chain (default).

The result is one canonical, secret-free report that embeds the reports of the steps that ran. The integrity checker
(`scripts/media_integrity_check.py --verify-sha256 --strict`, plan §10 / §11 step 5) is the operator's separate
final check against the restored database and bucket. This function holds no policy of its own: the scratch-database,
identity and destination-bucket guards are the ones of the steps it calls.
"""

import enum
import json
import logging
from collections.abc import Callable, Collection
from dataclasses import dataclass
from pathlib import Path

import asyncpg

from app.backup.manifest import canonical_line
from app.backup.media_sync import PriorRunError, load_prior_run
from app.backup.pg_connection import PgConnectionConfig
from app.backup.restore_db import (
    DEFAULT_MAX_PLAINTEXT_BYTES,
    DEFAULT_TIMEOUT_SECONDS,
    Connect,
    DbRestoreReport,
    ReadyAssetsUnreadableError,
    read_ready_assets,
    restore_database,
)
from app.backup.restore_guards import RestoreGuardError, validate_restore_database
from app.backup.restore_media import (
    MAX_CONSECUTIVE_UNAVAILABLE,
    MediaRestoreReport,
    restore_media,
)
from app.backup.run_id import validate_run_id
from app.backup.schema_revision import resolve_expected_head
from app.backup.target import DEFAULT_RETRY, BackupReader, RetryPolicy, Sleep
from app.domain.exceptions import MediaStorageError, MediaStorageUnavailable
from app.domain.services.media_storage import MediaStorageAdmin

logger = logging.getLogger(__name__)

REPORT_FORMAT = "plan-estimate/restore-run-report/v1"


class RestorePhase(enum.StrEnum):
    ALL = "all"
    DATABASE = "database"
    MEDIA = "media"


class RunStep(enum.StrEnum):
    SEAL = "seal"
    DATABASE = "database"
    READY_SET = "ready_set"
    MEDIA = "media"
    DONE = "done"


class ChainFailure(enum.StrEnum):
    SEAL_MISSING = "SEAL_MISSING"  # no COMPLETE.json / manifest: the run is incomplete by definition
    SEAL_INVALID = "SEAL_INVALID"  # the seal does not match the manifest, or the manifest is inconsistent
    STORAGE_UNAVAILABLE = "STORAGE_UNAVAILABLE"
    STORAGE_MISCONFIGURED = "STORAGE_MISCONFIGURED"
    READY_SET_UNREADABLE = "READY_SET_UNREADABLE"  # the restored database could not give its READY set back
    DATABASE_UNSAFE = "DATABASE_UNSAFE"  # phase media: the database is not recognisably a scratch database


@dataclass(frozen=True)
class RestoreRunReport:
    run_id: str
    step: RunStep  # the last step started (DONE after success)
    failure: ChainFailure | None
    database: DbRestoreReport | None
    media: MediaRestoreReport | None
    phase: RestorePhase = RestorePhase.ALL

    @property
    def ok(self) -> bool:
        if self.step is not RunStep.DONE or self.failure is not None:
            return False
        # A phase that runs a half must have it succeed; a phase that skips a half must not carry its report.
        database_good = self.database is None if self.phase is RestorePhase.MEDIA else self.database is not None and self.database.ok
        media_good = self.media is None if self.phase is RestorePhase.DATABASE else self.media is not None and self.media.ok
        return database_good and media_good

    def report_bytes(self) -> bytes:
        """Canonical one-line JSON embedding the step reports (themselves secret-free)."""
        document: dict[str, object] = {
            "format": REPORT_FORMAT,
            "run_id": self.run_id,
            "ok": self.ok,
            "phase": self.phase.value,
            "step": self.step.value,
            "failure": None if self.failure is None else self.failure.value,
            "database": None if self.database is None else json.loads(self.database.report_bytes()),
            "media": None if self.media is None else json.loads(self.media.report_bytes()),
        }
        return canonical_line(document)


async def restore_run(
    reader: BackupReader,
    run_id: str,
    *,
    database: PgConnectionConfig,
    identity_file: Path,
    destination: MediaStorageAdmin,
    destination_bucket: str,
    forbidden_buckets: Collection[str],
    scratch_dir: Path,
    allowed_hosts: Collection[str] = (),
    allow_non_drill: bool = False,
    allow_foreign_objects: bool = False,
    verify_destination: bool = True,
    age_path: str = "age",
    age_keygen_path: str = "age-keygen",
    psql_path: str = "psql",
    connect: Connect = asyncpg.connect,
    retry: RetryPolicy = DEFAULT_RETRY,
    sleep: Sleep | None = None,
    db_timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_plaintext_bytes: int = DEFAULT_MAX_PLAINTEXT_BYTES,
    repository_head: Callable[[], str] = resolve_expected_head,
    max_consecutive_unavailable: int = MAX_CONSECUTIVE_UNAVAILABLE,
    phase: RestorePhase = RestorePhase.ALL,
) -> RestoreRunReport:
    """Restore the sealed run `run_id` into the scratch database and the destination bucket (module docstring)."""
    validate_run_id(run_id)

    def failed(step: RunStep, failure: ChainFailure, database_report: DbRestoreReport | None = None) -> RestoreRunReport:
        logger.info("restore stopped: run=%s step=%s failure=%s", run_id, step.value, failure.value)
        return RestoreRunReport(run_id, step, failure, database_report, None, phase)

    # -- seal ---------------------------------------------------------------------------------------------
    try:
        run = await load_prior_run(reader, run_id, scratch_dir=scratch_dir, retry=retry, sleep=sleep)
    except PriorRunError as exc:
        return failed(RunStep.SEAL, ChainFailure.SEAL_MISSING if exc.missing else ChainFailure.SEAL_INVALID)
    except MediaStorageUnavailable:
        return failed(RunStep.SEAL, ChainFailure.STORAGE_UNAVAILABLE)
    except MediaStorageError:
        return failed(RunStep.SEAL, ChainFailure.STORAGE_MISCONFIGURED)

    # -- database -----------------------------------------------------------------------------------------
    db_report: DbRestoreReport | None = None
    if phase is RestorePhase.MEDIA:
        try:
            validate_restore_database(database, allowed_hosts=allowed_hosts)
        except RestoreGuardError:
            return failed(RunStep.DATABASE, ChainFailure.DATABASE_UNSAFE)
    else:
        db_report = await restore_database(
            reader,
            run,
            database=database,
            identity_file=identity_file,
            scratch_dir=scratch_dir,
            allowed_hosts=allowed_hosts,
            age_path=age_path,
            age_keygen_path=age_keygen_path,
            psql_path=psql_path,
            connect=connect,
            retry=retry,
            sleep=sleep,
            timeout_seconds=db_timeout_seconds,
            max_plaintext_bytes=max_plaintext_bytes,
            repository_head=repository_head,
        )
        if not db_report.ok:
            return RestoreRunReport(run_id, RunStep.DATABASE, None, db_report, None, phase)
        if phase is RestorePhase.DATABASE:
            return RestoreRunReport(run_id, RunStep.DONE, None, db_report, None, phase)

    # -- READY set of the restored database ---------------------------------------------------------------
    try:
        ready_assets = await read_ready_assets(database, connect=connect)
    except ReadyAssetsUnreadableError:
        return failed(RunStep.READY_SET, ChainFailure.READY_SET_UNREADABLE, db_report)

    # -- media --------------------------------------------------------------------------------------------
    media_report = await restore_media(
        reader,
        run,
        destination,
        destination_bucket=destination_bucket,
        forbidden_buckets=forbidden_buckets,
        ready_assets=ready_assets,
        scratch_dir=scratch_dir,
        allow_non_drill=allow_non_drill,
        allow_foreign_objects=allow_foreign_objects,
        verify_destination=verify_destination,
        retry=retry,
        sleep=sleep,
        max_consecutive_unavailable=max_consecutive_unavailable,
    )
    step = RunStep.DONE if media_report.ok else RunStep.MEDIA
    return RestoreRunReport(run_id, step, None, db_report, media_report, phase)

