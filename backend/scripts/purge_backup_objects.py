"""Remove the copies of deleted photos from the Oracle backup bucket (archive cleanup AC-3; operator tool, owner workstation).

The application deletes a photo for good from the working storage and records it in the purge ledger (AC-2). The backup bucket is versioned and the
backup identity can neither delete nor overwrite (Stage 14 decision), so the copies stay there until THIS tool -- run by the owner, off the
production VM, with a separate identity that has `OBJECT_DELETE` and `OBJECT_VERSION_DELETE` on the backup bucket only -- removes every version of
exactly the three objects of each file set the ledger names.

    python scripts/purge_backup_objects.py --ledger /abs/purge-ledger.jsonl --namespace <ns> --bucket plan-estimate-backup-drill \\
        --config ~/.oci-purge/config                                           # DRY RUN (default): lists what exists, deletes nothing
    python scripts/purge_backup_objects.py ... --execute --report /abs/new-report.jsonl      # asks for a typed confirmation, then deletes

What it can touch is fixed by construction: the ledger is parsed strictly (every key must be one of the three keys of its asset under
`photos/v1/<asset>/`), the bucket must be one of the two known backup buckets (a **drill** bucket for the rehearsal, the **production** one for
the real cleaning), `runs/` (manifests, seals) and `db/` (dumps) are never named by a ledger line and are never touched. Deleting an object
without a version id would only add a delete marker, so every version and every delete marker of the key is deleted by its version id, then the
key is listed again and must be gone. The report (canonical JSON lines, no keys, no secrets) is what `python -m app.cli.purge_ledger mark-done`
reads on the server; a report of the drill bucket marks nothing.

Never printed: key material, OCIDs, fingerprints, the namespace, object keys, exception messages.
Exit codes: 0 done (or a dry run), 1 a file set could not be cleaned (see the report), 2 cannot run, 3 declined at the confirmation.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.backup.purge_ledger import (
    LedgerEntry,
    PurgeLedgerError,
    parse_ledger,
)
from app.backup.purge_report import ReportEntry, serialize_report

EXIT_DONE, EXIT_FAILED, EXIT_CANNOT_RUN, EXIT_DECLINED = 0, 1, 2, 3
PROD_BUCKET = "plan-estimate-backup-prod"
DRILL_BUCKET = "plan-estimate-backup-drill"
CONFIRM_PHRASES = {"prod": "УДАЛИТЬ ИЗ БЭКАПА ДА", "drill": "РЕПЕТИЦИЯ ДА"}
DEFAULT_REGION = "eu-frankfurt-1"
MAX_ROUNDS = 20  # listing -> deleting rounds per key (a key has a handful of versions; this only stops a runaway)
MAX_LEDGER_BYTES = 64 * 1024 * 1024


def bucket_kind(name: str) -> str | None:
    return {PROD_BUCKET: "prod", DRILL_BUCKET: "drill"}.get(name)


@dataclass(frozen=True)
class SetOutcome:
    entry: LedgerEntry
    found: int  # versions (and delete markers) that existed before
    deleted: int
    failed: bool

    def report_entry(self) -> ReportEntry:
        if self.failed:
            return ReportEntry(self.entry.asset_id, "failed", self.deleted)
        return ReportEntry(self.entry.asset_id, "deleted" if self.deleted else "already_absent", self.deleted)


def versions_of(client: Any, namespace: str, bucket: str, key: str) -> list[Any]:
    """Every version and delete marker whose name is exactly `key` (a prefix listing may return longer names: they are ignored)."""
    items = client.list_object_versions(namespace, bucket, prefix=key).data.items or []
    return [item for item in items if item.name == key]


def clean_key(client: Any, namespace: str, bucket: str, key: str) -> tuple[int, int]:
    """(versions found, versions deleted); raises when a version is still there after the deletions."""
    found = deleted = 0
    for _ in range(MAX_ROUNDS):
        versions = versions_of(client, namespace, bucket, key)
        if not versions:
            return found, deleted
        found = max(found, deleted + len(versions))
        for version in versions:
            client.delete_object(namespace, bucket, key, version_id=version.version_id)
            deleted += 1
    raise RuntimeError("versions remain after the deletions")


def clean_set(client: Any, namespace: str, bucket: str, entry: LedgerEntry, *, execute: bool) -> SetOutcome:
    found = deleted = 0
    try:
        for key in entry.keys:
            if execute:
                key_found, key_deleted = clean_key(client, namespace, bucket, key)
                found, deleted = found + key_found, deleted + key_deleted
            else:
                found += len(versions_of(client, namespace, bucket, key))
    except Exception:  # noqa: BLE001 - provider errors never carry anything we print; the outcome is "failed"
        return SetOutcome(entry, found, deleted, True)
    return SetOutcome(entry, found, deleted, False)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--ledger", required=True, help="absolute path of the exported purge ledger")
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--bucket", required=True, help=f"{DRILL_BUCKET} (rehearsal) or {PROD_BUCKET}")
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--config", required=True, help="OCI API-key config file of the purge identity")
    parser.add_argument("--profile", default="DEFAULT")
    parser.add_argument("--execute", action="store_true", help="delete (default: a dry run that lists what exists)")
    parser.add_argument("--report", default=None, help="absolute path of a NEW file for the report (required with --execute)")
    return parser


def write_new(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view) :]
        os.fsync(fd)
    finally:
        os.close(fd)


def real_client(args: argparse.Namespace) -> Any:
    import oci

    config = oci.config.from_file(os.path.expanduser(args.config), args.profile)
    config["region"] = args.region
    return oci.object_storage.ObjectStorageClient(config, retry_strategy=oci.retry.NoneRetryStrategy())


def read_confirmation(prompt: str) -> str:
    with open("/dev/tty") as tty:
        print(prompt, end="", flush=True)
        return tty.readline().strip()


def main(
    argv: Sequence[str],
    out: TextIO = sys.stdout,
    *,
    make_client: Callable[[argparse.Namespace], Any] = real_client,
    confirm: Callable[[str], str] = read_confirmation,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> int:
    args = build_parser().parse_args(list(argv))
    kind = bucket_kind(args.bucket)
    if kind is None:
        print(f"refused: the bucket must be {DRILL_BUCKET} or {PROD_BUCKET}", file=out)
        return EXIT_CANNOT_RUN
    for name in ("ledger", "report"):
        value = getattr(args, name)
        if value is not None and not Path(value).is_absolute():
            print(f"refused: --{name} must be an absolute path", file=out)
            return EXIT_CANNOT_RUN
    if args.execute and not args.report:
        print("refused: --execute needs --report (the report is what marks the ledger on the server)", file=out)
        return EXIT_CANNOT_RUN
    if args.report and os.path.lexists(args.report):
        print("refused: the report file already exists", file=out)
        return EXIT_CANNOT_RUN
    try:
        ledger_path = Path(args.ledger)
        if ledger_path.stat().st_size > MAX_LEDGER_BYTES:
            raise PurgeLedgerError("too large")
        ledger = parse_ledger(ledger_path.read_bytes())
    except (OSError, PurgeLedgerError):
        print("refused: the ledger cannot be read or is not a valid purge ledger export", file=out)
        return EXIT_CANNOT_RUN
    if not ledger.entries:
        print("nothing to do: the ledger is empty", file=out)
        return EXIT_DONE
    try:
        client = make_client(args)
    except Exception as exc:  # noqa: BLE001 - the SDK or the config file is unusable; say which kind of failure, never why
        print(f"cannot run: the OCI client cannot be built ({type(exc).__name__})", file=out)
        return EXIT_CANNOT_RUN

    mode = "DELETE" if args.execute else "DRY RUN (nothing is deleted)"
    print(f"purge of backup copies: bucket_kind={kind} file_sets={len(ledger.entries)} mode={mode}", file=out)
    if args.execute:
        phrase = CONFIRM_PHRASES[kind]
        print(f"This removes EVERY version of {len(ledger.entries) * 3} objects from the {kind.upper()} backup bucket. It cannot be undone.", file=out)
        if confirm(f"Type exactly  {phrase}  to continue: ") != phrase:
            print("declined: nothing was deleted", file=out)
            return EXIT_DECLINED
    outcomes = [clean_set(client, args.namespace, args.bucket, entry, execute=args.execute) for entry in ledger.entries]
    for outcome in outcomes:
        state = "FAILED" if outcome.failed else ("clean" if outcome.found == 0 else ("removed" if args.execute else "present"))
        print(f"  {str(outcome.entry.asset_id)[:8]}…  versions found={outcome.found} deleted={outcome.deleted}  {state}", file=out)
    failed = [o for o in outcomes if o.failed]
    if args.execute:
        report = serialize_report([o.report_entry() for o in outcomes], bucket_kind=kind, finished_at=now().strftime("%Y-%m-%dT%H:%M:%SZ"))
        try:
            write_new(Path(args.report), report)
        except OSError as exc:
            print(f"the report could not be written ({type(exc).__name__}); the deletions above DID happen", file=out)
            return EXIT_FAILED
        print(f"report written; on the server: python -m app.cli.purge_ledger mark-done --report <file>{' (a rehearsal report marks nothing)' if kind == 'drill' else ''}", file=out)
    if failed:
        print(f"{len(failed)} file set(s) could not be cleaned: run again (it is safe to repeat)", file=out)
        return EXIT_FAILED
    return EXIT_DONE


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
