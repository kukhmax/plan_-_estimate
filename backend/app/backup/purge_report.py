"""The report of the owner's backup cleaning (archive cleanup AC-3): what the purge tool did to which file set.

Written by `scripts/purge_backup_objects.py` (on the owner's workstation) and read by `python -m app.cli.purge_ledger mark-done` (on the server) to
mark the ledger rows whose copies are gone from the backup bucket. Canonical JSON lines, secret-free and content-free:

    {"format":"plan-estimate/purge-backup-report/v1","count":N,"bucket_kind":"prod|drill","finished_at":"..."}
    {"asset_id":"<uuid>","outcome":"deleted|already_absent|failed","versions_deleted":n}
"""
import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from app.backup.manifest import canonical_line
from app.backup.purge_ledger import PurgeLedgerError

REPORT_FORMAT = "plan-estimate/purge-backup-report/v1"
OUTCOMES = ("deleted", "already_absent", "failed")


@dataclass(frozen=True, slots=True)
class ReportEntry:
    asset_id: uuid.UUID
    outcome: str
    versions_deleted: int

    @property
    def clean(self) -> bool:
        """The copies of this file set are gone from the bucket (now or before)."""
        return self.outcome in ("deleted", "already_absent")


@dataclass(frozen=True, slots=True)
class PurgeBackupReport:
    entries: tuple[ReportEntry, ...]
    bucket_kind: str
    finished_at: str


def serialize_report(entries: Sequence[ReportEntry], *, bucket_kind: str, finished_at: str) -> bytes:
    header = canonical_line({"format": REPORT_FORMAT, "count": len(entries), "bucket_kind": bucket_kind, "finished_at": finished_at})
    return header + b"".join(
        canonical_line({"asset_id": str(e.asset_id), "outcome": e.outcome, "versions_deleted": e.versions_deleted}) for e in entries
    )


def parse_report(data: bytes) -> PurgeBackupReport:
    try:
        documents = [json.loads(line) for line in data.decode("ascii").splitlines() if line.strip()]
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise PurgeLedgerError("the report is not JSON lines") from None
    if not documents or not isinstance(documents[0], dict) or documents[0].get("format") != REPORT_FORMAT:
        raise PurgeLedgerError("the report has no valid header")
    header, rows = documents[0], documents[1:]
    if header.get("count") != len(rows) or header.get("bucket_kind") not in ("prod", "drill") or not isinstance(header.get("finished_at"), str):
        raise PurgeLedgerError("the report header does not match the lines")
    entries = []
    for row in rows:
        if not isinstance(row, dict) or row.get("outcome") not in OUTCOMES:
            raise PurgeLedgerError("a report line is malformed")
        versions = row.get("versions_deleted")
        if isinstance(versions, bool) or not isinstance(versions, int) or versions < 0:
            raise PurgeLedgerError("a report line is malformed")
        try:
            asset_id = uuid.UUID(str(row.get("asset_id")))
        except ValueError:
            raise PurgeLedgerError("a report line is malformed") from None
        entries.append(ReportEntry(asset_id, row["outcome"], versions))
    return PurgeBackupReport(tuple(entries), header["bucket_kind"], header["finished_at"])
