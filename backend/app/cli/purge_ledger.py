"""`python -m app.cli.purge_ledger` -- the two server-side commands of the backup cleaning (archive cleanup AC-3).

    export [--pending-only] [--out /abs/new/file]   write the purge ledger as a file (stdout when no --out): the input of the owner's purge tool and of
                                                    `verify` / `restore --purge-ledger`. Content-free and secret-free.
    mark-done --report /abs/report                  read the report the owner's purge tool wrote and mark the rows whose copies are gone from the
                                                    PRODUCTION backup bucket (a drill report marks nothing)

Run inside the backend container: `docker exec plan_estimate_backend python -m app.cli.purge_ledger export --out /tmp/purge-ledger.jsonl`.
Exit codes: 0 done, 2 usage, 5 the file cannot be used.
"""
import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.backup.purge_ledger import PurgeLedgerError, serialize_ledger
from app.backup.purge_ledger_db import export_entries, mark_backup_done
from app.backup.purge_report import parse_report
from app.core.database import async_session_maker

EXIT_OK, EXIT_UNUSABLE = 0, 5


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli.purge_ledger")
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export")
    export.add_argument("--pending-only", action="store_true", help="only the rows whose backup copies are not yet removed")
    export.add_argument("--out", default=None, help="absolute path of a NEW file (0600); stdout when omitted")
    mark = commands.add_parser("mark-done")
    mark.add_argument("--report", required=True, help="absolute path of the report written by scripts/purge_backup_objects.py")
    return parser


def _write_new(path: Path, data: bytes) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        os.fchmod(fd, 0o600)
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view) :]
        os.fsync(fd)
    finally:
        os.close(fd)


async def run(argv: list[str], out) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "export":
        target = Path(args.out) if args.out else None
        if target is not None and (not target.is_absolute() or os.path.lexists(target) or not target.parent.is_dir()):
            print("export refused: --out must be an absolute path of a new file in an existing directory", file=out)
            return EXIT_UNUSABLE
        async with async_session_maker() as db:
            entries = await export_entries(db, pending_only=args.pending_only)
        data = serialize_ledger(entries, exported_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
        if target is None:
            out.write(data.decode("ascii"))
        else:
            _write_new(target, data)
            print(f"purge ledger exported: entries={len(entries)}", file=out)
        return EXIT_OK
    path = Path(args.report)
    try:
        if not path.is_absolute():
            raise PurgeLedgerError("the path is not absolute")
        report = parse_report(path.read_bytes())
    except (OSError, PurgeLedgerError):
        print("mark-done refused: the report cannot be read or is not a valid report", file=out)
        return EXIT_UNUSABLE
    async with async_session_maker() as db:
        marked = await mark_backup_done(db, report)
    print(f"purge ledger updated: bucket={report.bucket_kind} marked={marked}", file=out)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(asyncio.run(run(sys.argv[1:], sys.stdout)))
