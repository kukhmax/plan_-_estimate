"""`python -m app.backup restore` (Stage 14D.2J.3) -- restore one sealed run into a scratch database and a drill bucket.

    python -m app.backup restore --run-id ID --identity-file /abs/age.key --scratch-dir /abs/dir --report-file /abs/new.json
                                 --forbidden-bucket NAME [--forbidden-bucket NAME ...] [--oci-config /abs/config
                                 [--oci-profile NAME]] [--allowed-host HOST ...] [--allow-non-drill]
                                 [--allow-foreign-objects] [--no-verify-destination] [--phase all|database|media]

This is the restore principal's command (the operator's workstation or a recovery host, never the production VM). It
builds the read-only Oracle reader, the destination bucket client and the scratch database connection from the
environment, validates every guard before touching anything, and calls `restore_run` (seal -> database -> READY set ->
media). The canonical, secret-free report is written to `--report-file` (new file, 0600) and a short summary is printed.
The integrity checker (`scripts/media_integrity_check.py --verify-sha256 --strict`) remains the operator's separate
final check against the restored database and bucket.

Environment (names only here; values never printed):
    PGHOST PGPORT PGDATABASE PGUSER PGPASSFILE PGSSLMODE      the SCRATCH database (name must carry the scratch marker)
    BACKUP_OCI_NAMESPACE BACKUP_OCI_BUCKET [BACKUP_OCI_REGION=eu-frankfurt-1]
                                                              the Oracle bucket to read; auth: --oci-config (API key of the
                                                              restore principal), else the instance principal
    RESTORE_S3_ENDPOINT_URL RESTORE_S3_BUCKET [RESTORE_S3_REGION=auto] RESTORE_S3_ACCESS_KEY_ID RESTORE_S3_SECRET_ACCESS_KEY
                                                              the DESTINATION media bucket (never the MEDIA_S3_* production names)

`--phase database` restores the seal and the database only; `--phase media` then restores the media into that ALREADY
restored database (refused unless the manifest describes it). The drill runs the two phases separately so that the
integrity checker can run between them (plan §11 step 5). The default `all` does both in one pass.

The Oracle backup bucket is always a forbidden destination; `--forbidden-bucket` (at least one: the production media
bucket) adds to that.

Exit codes:
    0  restored and verified (database and media)
    1  restore failed (see the report: step / failure); nothing was reported as restored that was not
    2  usage error (argparse)
    5  configuration / guard / principal failure (nothing was read or written)
    6  interrupted (SIGTERM / SIGINT); the scratch database and destination bucket hold whatever was completed
    7  the restore ran but the report file could not be written (the summary above was printed)
"""

import argparse
import asyncio
import os
import re
import shutil
import signal
import tempfile
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from app.backup.db_dump_command import (
    EXIT_FAILED,
    EXIT_INTERRUPTED,
    EXIT_PREFLIGHT,
    EXIT_SUCCESS,
    run_cancellable,
)
from app.backup.pg_connection import (
    PassfileError,
    PgConnectionConfig,
    PgConnectionConfigError,
    validate_passfile,
)
from app.backup.restore_guards import (
    RestoreGuardError,
    validate_identity_file,
    validate_restore_database,
    validate_restore_media_target,
)
from app.backup.restore_run import RestorePhase, RestoreRunReport, restore_run
from app.backup.run_id import RunIdError, validate_run_id
from app.backup.target import BackupReader
from app.domain.exceptions import MediaStorageError
from app.domain.services.media_storage import MediaStorageAdmin

EXIT_REPORT_NOT_WRITTEN = 7

DEFAULT_OCI_REGION = "eu-frankfurt-1"
_ENDPOINT = re.compile(r"^https://[A-Za-z0-9.-]+(:[0-9]{1,5})?/?$")
_BUCKET = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_NAMESPACE = re.compile(r"^[A-Za-z0-9]{1,64}$")
_REGION = re.compile(r"^[a-z]{2}-[a-z]+-[0-9]$")
_PROFILE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_HOST = re.compile(r"^[A-Za-z0-9.-]{1,253}$")
REPORT_FILE_MODE = 0o600


class RestoreConfigError(ValueError):
    """The environment or the arguments are unusable. The message names settings only, never values."""


@dataclass(frozen=True)
class RestoreSettings:
    database: PgConnectionConfig
    backup_namespace: str
    backup_bucket: str
    backup_region: str
    destination_endpoint: str
    destination_bucket: str
    destination_region: str


def settings_from_env(env: Mapping[str, str]) -> RestoreSettings:
    def value(name: str, default: str = "") -> str:
        return env.get(name, default).strip()

    def required(name: str, pattern: re.Pattern[str]) -> str:
        found = value(name)
        if not found:
            raise RestoreConfigError(f"{name} is required")
        if not pattern.fullmatch(found):
            raise RestoreConfigError(f"{name} is not a valid value")
        return found

    for name in ("RESTORE_S3_ACCESS_KEY_ID", "RESTORE_S3_SECRET_ACCESS_KEY"):
        if not value(name):
            raise RestoreConfigError(f"{name} is required")
    try:
        database = PgConnectionConfig.from_env(env)
    except PgConnectionConfigError as exc:
        raise RestoreConfigError(str(exc)) from None
    settings = RestoreSettings(
        database=database,
        backup_namespace=required("BACKUP_OCI_NAMESPACE", _NAMESPACE),
        backup_bucket=required("BACKUP_OCI_BUCKET", _BUCKET),
        backup_region=value("BACKUP_OCI_REGION", DEFAULT_OCI_REGION),
        destination_endpoint=required("RESTORE_S3_ENDPOINT_URL", _ENDPOINT),
        destination_bucket=required("RESTORE_S3_BUCKET", _BUCKET),
        destination_region=value("RESTORE_S3_REGION", "auto") or "auto",
    )
    if not _REGION.fullmatch(settings.backup_region):
        raise RestoreConfigError("BACKUP_OCI_REGION is not a valid value")
    return settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.backup restore", description="Restore one sealed run")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--identity-file", required=True, help="absolute path of the age identity (private key) file")
    parser.add_argument("--scratch-dir", required=True, help="absolute path of an existing private scratch directory")
    parser.add_argument("--report-file", required=True, help="absolute path of a NEW file for the restore report")
    parser.add_argument(
        "--phase", choices=[phase.value for phase in RestorePhase], default=RestorePhase.ALL.value,
        help="all (default), database (seal + database), or media (seal + media into the ALREADY restored database)",
    )  # fmt: skip
    parser.add_argument("--forbidden-bucket", action="append", default=[], help="a bucket that must never be the destination")
    parser.add_argument("--oci-config", default=None, help="OCI API-key config file of the restore principal")
    parser.add_argument("--oci-profile", default="DEFAULT")
    parser.add_argument("--allowed-host", action="append", default=[], help="a non-loopback scratch database host to accept")
    parser.add_argument("--allow-non-drill", action="store_true", help="accept a destination bucket without 'drill' in its name")
    parser.add_argument("--allow-foreign-objects", action="store_true", help="accept destination objects outside the run")
    parser.add_argument("--no-verify-destination", action="store_true", help="skip the final read-back of the destination")
    return parser


@dataclass
class RestoreDependencies:
    """Injection seams: the defaults build the real Oracle reader and R2 destination (imported lazily)."""

    make_reader: Callable[[RestoreSettings, argparse.Namespace], BackupReader]
    make_destination: Callable[[RestoreSettings, Mapping[str, str]], MediaStorageAdmin]
    restore: Callable[..., Awaitable[RestoreRunReport]] = restore_run


def _real_reader(settings: RestoreSettings, args: argparse.Namespace) -> BackupReader:
    from app.backup.oci_target import OciBackupReader

    if args.oci_config:
        return OciBackupReader.from_api_key_config(
            namespace=settings.backup_namespace,
            bucket=settings.backup_bucket,
            config_file=Path(args.oci_config),
            profile=args.oci_profile,
            region=settings.backup_region,
        )
    return OciBackupReader.from_instance_principal(
        namespace=settings.backup_namespace, bucket=settings.backup_bucket, region=settings.backup_region
    )


def _real_destination(settings: RestoreSettings, env: Mapping[str, str]) -> MediaStorageAdmin:
    from app.core.s3_media_storage import S3MediaStorage

    return S3MediaStorage(
        endpoint_url=settings.destination_endpoint,
        bucket=settings.destination_bucket,
        region=settings.destination_region,
        access_key_id=env["RESTORE_S3_ACCESS_KEY_ID"].strip(),
        secret_access_key=env["RESTORE_S3_SECRET_ACCESS_KEY"].strip(),
    )


DEFAULT_DEPENDENCIES = RestoreDependencies(make_reader=_real_reader, make_destination=_real_destination)


def _absolute(value: str, what: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        raise RestoreConfigError(f"{what} must be an absolute path")
    return path


def check_report_target(path: Path) -> None:
    """Fail before the long restore, not after it: the report file must be creatable."""
    if not path.parent.is_dir():
        raise RestoreConfigError("the report file's directory does not exist")
    if os.path.lexists(path):
        raise RestoreConfigError("the report file already exists; refusing to overwrite it")


def write_report_file(path: Path, data: bytes) -> None:
    """Exclusive create (never overwrite, never follow a symlink), 0600, full write, fsync."""
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, REPORT_FILE_MODE)
    try:
        os.fchmod(fd, REPORT_FILE_MODE)
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view) :]
        os.fsync(fd)
    finally:
        os.close(fd)


def summary_line(report: RestoreRunReport) -> str:
    if report.ok:
        counts = report.media.counts if report.media else None
        detail = f" restored={counts.restored} already_present={counts.already_present} total={counts.objects_total}" if counts else ""
        ready = f" ready_count={report.database.ready_count}" if report.database else ""
        return f"restore ok: run_id={report.run_id} phase={report.phase.value}{ready}{detail}"
    parts = [f"restore failed: run_id={report.run_id} step={report.step.value}"]
    if report.failure is not None:
        parts.append(f"failure={report.failure.value}")
    if report.database is not None and not report.database.ok:
        parts.append(f"database_step={report.database.step.value}")
        if report.database.failure is not None:
            parts.append(f"database_failure={report.database.failure.value}")
    if report.media is not None and not report.media.ok:
        if report.media.preflight is not None:
            parts.append(f"media_preflight={report.media.preflight.value}")
        if report.media.aborted is not None:
            parts.append(f"media_aborted={report.media.aborted.value}")
        parts.append(f"media_problems={len(report.media.object_problems)}")
    return " ".join(parts)


def run_restore(
    env: Mapping[str, str],
    argv: Sequence[str],
    out: TextIO,
    *,
    deps: RestoreDependencies | None = None,
    signals: tuple[int, ...] = (signal.SIGTERM, signal.SIGINT),
) -> int:
    args = build_parser().parse_args(list(argv))
    deps = deps or DEFAULT_DEPENDENCIES
    try:
        run_id = validate_run_id(args.run_id)
        identity = _absolute(args.identity_file, "--identity-file")
        scratch_parent = _absolute(args.scratch_dir, "--scratch-dir")
        report_file = _absolute(args.report_file, "--report-file")
        if not args.forbidden_bucket:
            raise RestoreConfigError("at least one --forbidden-bucket is required (the production media bucket)")
        for bucket in args.forbidden_bucket:
            if not _BUCKET.fullmatch(bucket):
                raise RestoreConfigError("--forbidden-bucket is not a valid bucket name")
        for host in args.allowed_host:
            if not _HOST.fullmatch(host):
                raise RestoreConfigError("--allowed-host is not a valid host name")
        if args.oci_config:
            _absolute(args.oci_config, "--oci-config")
        if not _PROFILE.fullmatch(args.oci_profile):
            raise RestoreConfigError("--oci-profile is not a valid profile name")
        settings = settings_from_env(env)
        forbidden = tuple(dict.fromkeys([*args.forbidden_bucket, settings.backup_bucket]))
        validate_restore_database(settings.database, allowed_hosts=args.allowed_host)
        validate_passfile(settings.database)
        validate_identity_file(identity)
        validate_restore_media_target(
            settings.destination_bucket, forbidden_buckets=forbidden, allow_non_drill=args.allow_non_drill
        )
        if not scratch_parent.is_dir():
            raise RestoreConfigError("the scratch directory does not exist")
        check_report_target(report_file)
    except (RestoreConfigError, RunIdError, RestoreGuardError, PassfileError) as exc:
        print(f"restore preflight failed: {exc}", file=out)
        return EXIT_PREFLIGHT
    try:
        reader = deps.make_reader(settings, args)
        destination = deps.make_destination(settings, env)
    except MediaStorageError as exc:
        print(f"restore preflight failed: the storage clients cannot be built ({type(exc).__name__})", file=out)
        return EXIT_PREFLIGHT
    try:
        scratch = Path(tempfile.mkdtemp(prefix="pe-restore-", dir=scratch_parent))
    except OSError as exc:
        print(f"restore preflight failed: the scratch directory is unusable ({type(exc).__name__})", file=out)
        return EXIT_PREFLIGHT
    try:
        try:
            report = asyncio.run(
                run_cancellable(
                    lambda: deps.restore(
                        reader,
                        run_id,
                        database=settings.database,
                        identity_file=identity,
                        destination=destination,
                        destination_bucket=settings.destination_bucket,
                        forbidden_buckets=forbidden,
                        scratch_dir=scratch,
                        allowed_hosts=tuple(args.allowed_host),
                        allow_non_drill=args.allow_non_drill,
                        allow_foreign_objects=args.allow_foreign_objects,
                        verify_destination=not args.no_verify_destination,
                        phase=RestorePhase(args.phase),
                    ),
                    signals,
                )
            )
        except asyncio.CancelledError:
            print("restore interrupted: the scratch database and destination bucket hold what was completed", file=out)
            return EXIT_INTERRUPTED
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    print(summary_line(report), file=out)
    try:
        write_report_file(report_file, report.report_bytes())
    except OSError as exc:
        print(f"the report file could not be written ({type(exc).__name__})", file=out)
        return EXIT_REPORT_NOT_WRITTEN
    return EXIT_SUCCESS if report.ok else EXIT_FAILED
