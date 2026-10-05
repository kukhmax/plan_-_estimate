"""`python -m app.backup verify` (Stage 14D.6A) -- check a sealed run in the backup target, read-only.

    python -m app.backup verify --run-id ID [--mode quick|full] [--expect-recipient age1... ...]
                                [--oci-config /abs/config [--oci-profile NAME]] [--report-file /abs/new.json]

Wraps `verify_run_in_target` (14D.2H) for the operator: it needs no database, no age identity and no write
authority. QUICK reads the seal, the manifest, the dump's size and one HEAD per object; FULL (default) also re-hashes the
dump and every object, one at a time. Authentication: the instance principal (on the VM, inside the uploader) or, with
`--oci-config`, the restore principal's API key (on the workstation). Recipients to expect: `--expect-recipient`
(repeatable) or, when none is given, the public `BACKUP_AGE_RECIPIENTS` of the backup environment -- the run must have been
encrypted for each of them. Output is a short summary; the canonical secret-free report goes to `--report-file` (new file,
0600).

Environment: BACKUP_OCI_NAMESPACE BACKUP_OCI_BUCKET [BACKUP_OCI_REGION=eu-frankfurt-1] [BACKUP_AGE_RECIPIENTS]

Exit codes:
    0  the run verified (every check of the chosen mode passed)
    1  the run has problems (see the codes in the summary / report)
    2  usage error (argparse)
    5  configuration / principal failure (nothing was read)
    6  interrupted (SIGTERM / SIGINT)
    7  verified, but the report file could not be written
"""

import argparse
import asyncio
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
from app.backup.restore_command import (
    EXIT_REPORT_NOT_WRITTEN,
    check_report_target,
    write_report_file,
)
from app.backup.run_id import RunIdError, validate_run_id
from app.backup.target import BackupReader
from app.backup.verify import VerifyMode, VerifyReport, verify_run_in_target
from app.core.db_dump_encryption import AgeRecipientError, parse_age_recipients
from app.domain.exceptions import MediaStorageError

DEFAULT_OCI_REGION = "eu-frankfurt-1"
DEFAULT_SCRATCH = "/tmp"
_BUCKET = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_NAMESPACE = re.compile(r"^[A-Za-z0-9]{1,64}$")
_REGION = re.compile(r"^[a-z]{2}-[a-z]+-[0-9]$")
_PROFILE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


class VerifyConfigError(ValueError):
    """The environment or the arguments are unusable. The message names settings only, never values."""


@dataclass(frozen=True)
class VerifySettings:
    namespace: str
    bucket: str
    region: str
    recipients: tuple[str, ...]


@dataclass
class VerifyDependencies:
    """Injection seam: the default builds the real Oracle reader (imported lazily)."""

    make_reader: Callable[[VerifySettings, argparse.Namespace], BackupReader]
    verify: Callable[..., Awaitable[VerifyReport]] = verify_run_in_target


def _real_reader(settings: VerifySettings, args: argparse.Namespace) -> BackupReader:
    from app.backup.oci_target import OciBackupReader

    if args.oci_config:
        return OciBackupReader.from_api_key_config(
            namespace=settings.namespace,
            bucket=settings.bucket,
            config_file=Path(args.oci_config),
            profile=args.oci_profile,
            region=settings.region,
        )
    return OciBackupReader.from_instance_principal(
        namespace=settings.namespace, bucket=settings.bucket, region=settings.region
    )


DEFAULT_DEPENDENCIES = VerifyDependencies(make_reader=_real_reader)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.backup verify", description="Verify a sealed run in the target")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--mode", choices=[mode.value for mode in VerifyMode], default=VerifyMode.FULL.value)
    parser.add_argument("--expect-recipient", action="append", default=[], help="a public age recipient the run must include")
    parser.add_argument("--oci-config", default=None, help="OCI API-key config file (restore principal); else the instance principal")
    parser.add_argument("--oci-profile", default="DEFAULT")
    parser.add_argument("--report-file", default=None, help="absolute path of a NEW file for the canonical report")
    parser.add_argument("--scratch-dir", default=None, help="private scratch directory (default /tmp)")
    return parser


def settings_from_env(env: Mapping[str, str], args: argparse.Namespace) -> VerifySettings:
    def value(name: str, default: str = "") -> str:
        return env.get(name, default).strip()

    def required(name: str, pattern: re.Pattern[str]) -> str:
        found = value(name)
        if not found:
            raise VerifyConfigError(f"{name} is required")
        if not pattern.fullmatch(found):
            raise VerifyConfigError(f"{name} is not a valid value")
        return found

    region = value("BACKUP_OCI_REGION", DEFAULT_OCI_REGION)
    if not _REGION.fullmatch(region):
        raise VerifyConfigError("BACKUP_OCI_REGION is not a valid value")
    try:
        if args.expect_recipient:
            recipients = parse_age_recipients(list(args.expect_recipient))
        elif value("BACKUP_AGE_RECIPIENTS"):
            recipients = parse_age_recipients(value("BACKUP_AGE_RECIPIENTS"))  # comma / whitespace separated, as for db-dump
        else:
            recipients = ()
    except AgeRecipientError as exc:
        raise VerifyConfigError(str(exc)) from None
    return VerifySettings(
        namespace=required("BACKUP_OCI_NAMESPACE", _NAMESPACE),
        bucket=required("BACKUP_OCI_BUCKET", _BUCKET),
        region=region,
        recipients=recipients,
    )


def summary_line(report: VerifyReport) -> str:
    if report.ok:
        return f"verify ok: run_id={report.run_id} mode={report.mode.value} dump={report.dump_checked} {counts_text(report)}"
    parts = [f"verify failed: run_id={report.run_id} mode={report.mode.value}"]
    if report.run_problems:
        parts.append("run_problems=" + ",".join(problem.value for problem in report.run_problems))
    if report.object_problems:
        totals: dict[str, int] = {}
        for problem in report.object_problems:
            totals[problem.code.value] = totals.get(problem.code.value, 0) + 1
        parts.append("object_problems=" + ",".join(f"{code}:{n}" for code, n in sorted(totals.items())))
    if report.aborted is not None:
        parts.append(f"aborted={report.aborted.value}")
    return " ".join(parts)


def counts_text(report: VerifyReport) -> str:
    return " ".join(f"{name}={value}" for name, value in report.counts.to_dict().items())


def run_verify(
    env: Mapping[str, str],
    argv: Sequence[str],
    out: TextIO,
    *,
    deps: VerifyDependencies | None = None,
    signals: tuple[int, ...] = (signal.SIGTERM, signal.SIGINT),
) -> int:
    args = build_parser().parse_args(list(argv))
    deps = deps or DEFAULT_DEPENDENCIES
    try:
        run_id = validate_run_id(args.run_id)
        settings = settings_from_env(env, args)
        if not _PROFILE.fullmatch(args.oci_profile):
            raise VerifyConfigError("--oci-profile is not a valid profile name")
        for name in ("oci_config", "report_file", "scratch_dir"):
            value = getattr(args, name)
            if value is not None and not Path(value).is_absolute():
                raise VerifyConfigError(f"--{name.replace('_', '-')} must be an absolute path")
        report_file = Path(args.report_file) if args.report_file else None
        if report_file is not None:
            try:
                check_report_target(report_file)
            except ValueError as exc:
                raise VerifyConfigError(str(exc)) from None
        scratch_parent = Path(args.scratch_dir or DEFAULT_SCRATCH)
        if not scratch_parent.is_dir():
            raise VerifyConfigError("the scratch directory does not exist")
    except (VerifyConfigError, RunIdError) as exc:
        print(f"verify preflight failed: {exc}", file=out)
        return EXIT_PREFLIGHT
    try:
        reader = deps.make_reader(settings, args)
    except MediaStorageError as exc:
        print(f"verify preflight failed: the storage client cannot be built ({type(exc).__name__})", file=out)
        return EXIT_PREFLIGHT
    try:
        scratch = Path(tempfile.mkdtemp(prefix="pe-verify-", dir=scratch_parent))
    except OSError as exc:
        print(f"verify preflight failed: the scratch directory is unusable ({type(exc).__name__})", file=out)
        return EXIT_PREFLIGHT
    try:
        try:
            report = asyncio.run(
                run_cancellable(
                    lambda: deps.verify(
                        reader,
                        run_id,
                        scratch_dir=scratch,
                        mode=VerifyMode(args.mode),
                        expected_recipients=settings.recipients,
                    ),
                    signals,
                )
            )
        except asyncio.CancelledError:
            print("verify interrupted: nothing was changed (verification only reads)", file=out)
            return EXIT_INTERRUPTED
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    print(summary_line(report), file=out)
    if report_file is not None:
        try:
            write_report_file(report_file, report.report_bytes())
        except OSError as exc:
            print(f"the report file could not be written ({type(exc).__name__})", file=out)
            return EXIT_REPORT_NOT_WRITTEN
    return EXIT_SUCCESS if report.ok else EXIT_FAILED
