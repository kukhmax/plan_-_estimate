"""Local backup run evidence v1 (Stage 14D.2D.1).

`local-run.json` of a completed local run, or `<run_id>.failed.json` of a
handled failure (docs/STAGE_14D_BACKUP_RESTORE_PLAN.md §16.3). Both are
allowlisted, validated, size-capped records serialized as canonical JSON
(sorted keys, no whitespace, ASCII only, integers only, `\\n`-terminated), so
the bytes are deterministic and can later be hashed.

They never contain secrets, environment values, DSNs, paths, subprocess
output or free-form exception text: a failure is recorded only as a stage,
a stable error code and three booleans. Public age recipients are recorded
as a count only. `tool.source_sha256` is intentionally absent (owner
correction C1): build provenance needs its own contract.
"""

import asyncio
import enum
import hashlib
import itertools
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.backup.pg_connection import PassfileError, PgConnectionConfigError
from app.backup.run_id import validate_run_id
from app.backup.schema_revision import (
    ExpectedHeadError,
    ObservedRevisionError,
    SchemaRevisionMismatchError,
    validate_revision,
)
from app.core.db_dump_encryption import (
    ENCRYPTED_DUMP_NAME,
    AgeFailedError,
    AgeRecipientError,
    AgeToolError,
    ArtifactCollisionError,
    ArtifactFinalizeError,
    CompressionError,
    EncryptTimeoutError,
    InsufficientSpaceError,
    PlaintextCleanupError,
    PlaintextIntegrityError,
    UnsafeWorkPathError,
    parse_age_version,
)
from app.core.pg_snapshot_dump import (
    PgDumpFailedError,
    PgDumpTimeoutError,
    PgDumpVersionMismatchError,
    SnapshotDumpError,
)
from app.domain.services.media_backup_ready_set import (
    READY_SET_HEADER,
    ReadySetFormatError,
)

FORMAT_COMPLETE = "plan-estimate/local-db-backup/v1"
FORMAT_FAILED = "plan-estimate/local-db-backup-failure/v1"
READY_SET_FORMAT = READY_SET_HEADER.decode("ascii").rstrip("\n")
EMPTY_READY_SET_SHA256 = hashlib.sha256(READY_SET_HEADER).hexdigest()
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
MAX_TEXT = 200
MAX_COUNT = 2**53 - 1  # exact in every JSON implementation
MAX_RECIPIENTS = 32
PHOTO_ASSET_STATUSES = ("FAILED", "PENDING", "READY")

# Same forms the 14D.2A primitive accepts / generates.
SNAPSHOT_ID_PATTERN = re.compile(r"^[0-9A-F]{1,16}-[0-9A-F]{1,16}-[0-9]{1,10}$", re.ASCII)
SESSION_TAG_PATTERN = re.compile(r"^[a-z0-9-]{8,40}$", re.ASCII)
_SHA256 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_DB_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_$-]{0,62}$", re.ASCII)
_SERVER_VERSION = re.compile(r"^[0-9]{1,3}(\.[0-9]{1,4}){0,2}([ .~+-][\x20-\x7e]{0,60})?$", re.ASCII)
_PRINTABLE = re.compile(r"^[\x20-\x7e]+$", re.ASCII)
_PG_DUMP_VERSION_LINE = re.compile(r"^pg_dump \(PostgreSQL\) [0-9][\x20-\x7e]*$", re.ASCII)


class EvidenceError(ValueError):
    """An evidence value is invalid. Messages name the field, never the value."""


# --- field validators ------------------------------------------------------------------


def _text(value: object, field: str, pattern: re.Pattern[str] = _PRINTABLE, max_len: int = MAX_TEXT) -> str:
    if not isinstance(value, str) or not value or len(value) > max_len or not pattern.fullmatch(value):
        raise EvidenceError(f"{field} is not a valid value")
    return value


def _count(value: object, field: str, *, minimum: int = 0, maximum: int = MAX_COUNT) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise EvidenceError(f"{field} must be an integer in [{minimum}, {maximum}]")
    return value


def _sha256(value: object, field: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise EvidenceError(f"{field} must be 64 lowercase hex characters")
    return value


def _flag(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise EvidenceError(f"{field} must be a boolean")
    return value


def format_timestamp(value: object, field: str = "timestamp") -> str:
    """UTC `YYYY-MM-DDTHH:MM:SSZ` from a timezone-aware datetime."""
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise EvidenceError(f"{field} must be a timezone-aware datetime")
    return value.astimezone(UTC).strftime(TIMESTAMP_FORMAT)


def validate_snapshot_id(value: object) -> str:
    """Strict exported-snapshot id (`pg_export_snapshot()` form). Also the
    gate for the later metadata connection's `SET TRANSACTION SNAPSHOT`."""
    return _text(value, "snapshot_id", SNAPSHOT_ID_PATTERN, 64)


def canonical_json(document: dict[str, Any]) -> bytes:
    """Deterministic bytes: sorted keys, compact separators, ASCII, no NaN, trailing newline."""
    return (
        json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n"
    ).encode("ascii")


# --- complete-run evidence ---------------------------------------------------------------


@dataclass(frozen=True)
class DatabaseFacts:
    name: str
    server_version: str
    server_version_num: int
    alembic_revision: str
    expected_alembic_head: str
    photo_asset_status_counts: dict[str, int]

    def __post_init__(self) -> None:
        _text(self.name, "database.name", _DB_NAME, 63)
        _text(self.server_version, "database.server_version", _SERVER_VERSION, 64)
        _count(self.server_version_num, "database.server_version_num", minimum=100000, maximum=9999999)
        try:
            validate_revision(self.alembic_revision, "database.alembic_revision")
            validate_revision(self.expected_alembic_head, "database.expected_alembic_head")
        except ObservedRevisionError:
            raise EvidenceError("database revision fields must be valid Alembic revision ids") from None
        if self.alembic_revision != self.expected_alembic_head:
            raise EvidenceError("a complete run requires alembic_revision == expected_alembic_head")
        counts = self.photo_asset_status_counts
        if not isinstance(counts, dict) or tuple(sorted(counts)) != PHOTO_ASSET_STATUSES:
            raise EvidenceError(f"database.photo_asset_status_counts must have exactly {PHOTO_ASSET_STATUSES}")
        for status, value in counts.items():
            _count(value, f"database.photo_asset_status_counts.{status}")


@dataclass(frozen=True)
class SnapshotFacts:
    ready_count: int
    ready_set_sha256: str

    def __post_init__(self) -> None:
        _count(self.ready_count, "snapshot.ready_count")
        _sha256(self.ready_set_sha256, "snapshot.ready_set_sha256")
        if (self.ready_count == 0) != (self.ready_set_sha256 == EMPTY_READY_SET_SHA256):
            raise EvidenceError("snapshot.ready_set_sha256 is inconsistent with snapshot.ready_count")


@dataclass(frozen=True)
class DumpFacts:
    pg_dump_version: str
    plaintext_sha256: str
    plaintext_size: int

    def __post_init__(self) -> None:
        _text(self.pg_dump_version, "dump.pg_dump_version", _PG_DUMP_VERSION_LINE)
        _sha256(self.plaintext_sha256, "dump.plaintext_sha256")
        _count(self.plaintext_size, "dump.plaintext_size", minimum=1)


@dataclass(frozen=True)
class ArtifactFacts:
    sha256: str
    size: int
    age_version: str
    recipient_count: int

    def __post_init__(self) -> None:
        _sha256(self.sha256, "artifact.sha256")
        _count(self.size, "artifact.size", minimum=1)
        try:
            if parse_age_version(_text(self.age_version, "artifact.age_version", max_len=64)) != self.age_version:
                raise AgeToolError("not canonical")
        except AgeToolError:
            raise EvidenceError("artifact.age_version is not an age version") from None
        _count(self.recipient_count, "artifact.recipient_count", minimum=1, maximum=MAX_RECIPIENTS)


@dataclass(frozen=True)
class Diagnostics:
    """Diagnostic only: the snapshot id is meaningless after the exporter
    ends (no restore value) but correlates with server logs."""

    snapshot_id: str
    session_tag: str

    def __post_init__(self) -> None:
        validate_snapshot_id(self.snapshot_id)
        _text(self.session_tag, "diagnostics.session_tag", SESSION_TAG_PATTERN, 40)


@dataclass(frozen=True)
class CompleteRunEvidence:
    run_id: str
    started_at: datetime
    snapshot_exported_at: datetime
    dump_completed_at: datetime
    completed_at: datetime
    database: DatabaseFacts
    snapshot: SnapshotFacts
    dump: DumpFacts
    artifact: ArtifactFacts
    diagnostics: Diagnostics

    def __post_init__(self) -> None:
        try:
            validate_run_id(self.run_id)
        except ValueError:
            raise EvidenceError("run_id is not a valid run id") from None
        moments = [
            (name, getattr(self, name))
            for name in ("started_at", "snapshot_exported_at", "dump_completed_at", "completed_at")
        ]
        for name, value in moments:
            format_timestamp(value, name)
        if any(earlier[1] > later[1] for earlier, later in itertools.pairwise(moments)):
            raise EvidenceError("timestamps must be non-decreasing: started <= exported <= dumped <= completed")
        for name, kind in (
            ("database", DatabaseFacts),
            ("snapshot", SnapshotFacts),
            ("dump", DumpFacts),
            ("artifact", ArtifactFacts),
            ("diagnostics", Diagnostics),
        ):
            if not isinstance(getattr(self, name), kind):
                raise EvidenceError(f"{name} must be a {kind.__name__}")
        if self.database.photo_asset_status_counts["READY"] != self.snapshot.ready_count:
            raise EvidenceError("READY status count and snapshot.ready_count differ (same snapshot required)")

    def to_document(self) -> dict[str, Any]:
        db, snap, dump, art, diag = self.database, self.snapshot, self.dump, self.artifact, self.diagnostics
        return {
            "format": FORMAT_COMPLETE,
            "status": "complete",
            "run_id": self.run_id,
            "started_at": format_timestamp(self.started_at),
            "snapshot_exported_at": format_timestamp(self.snapshot_exported_at),
            "dump_completed_at": format_timestamp(self.dump_completed_at),
            "completed_at": format_timestamp(self.completed_at),
            "database": {
                "name": db.name,
                "server_version": db.server_version,
                "server_version_num": db.server_version_num,
                "alembic_revision": db.alembic_revision,
                "expected_alembic_head": db.expected_alembic_head,
                "photo_asset_status_counts": dict(db.photo_asset_status_counts),
            },
            "snapshot": {
                "method": "exported-snapshot",
                "ready_set_format": READY_SET_FORMAT,
                "ready_count": snap.ready_count,
                "ready_set_sha256": snap.ready_set_sha256,
            },
            "dump": {
                "format": "plain",
                "pg_dump_version": dump.pg_dump_version,
                # Local evidence only (owner decision D5); not part of any remote manifest by default.
                "plaintext_sha256": dump.plaintext_sha256,
                "plaintext_size": dump.plaintext_size,
            },
            "artifact": {
                "name": ENCRYPTED_DUMP_NAME,
                "encryption": "age",
                "age_version": art.age_version,
                "recipient_count": art.recipient_count,
                "sha256": art.sha256,
                "size": art.size,
            },
            "diagnostics": {"snapshot_id": diag.snapshot_id, "session_tag": diag.session_tag},
        }

    def to_canonical_json(self) -> bytes:
        return canonical_json(self.to_document())


# --- failure evidence ----------------------------------------------------------------------


class FailureStage(enum.StrEnum):
    PREFLIGHT = "preflight"
    CONNECT = "connect"
    SCHEMA_REVISION = "schema_revision"
    SNAPSHOT = "snapshot"
    DUMP = "dump"
    ENCRYPT = "encrypt"
    EVIDENCE = "evidence"
    PROMOTE = "promote"


class ErrorCode(enum.StrEnum):
    CONFIGURATION_INVALID = "CONFIGURATION_INVALID"
    PASSFILE_INVALID = "PASSFILE_INVALID"
    SCHEMA_HEAD_UNRESOLVED = "SCHEMA_HEAD_UNRESOLVED"
    SCHEMA_REVISION_INVALID = "SCHEMA_REVISION_INVALID"
    SCHEMA_REVISION_MISMATCH = "SCHEMA_REVISION_MISMATCH"
    READY_SET_INVALID = "READY_SET_INVALID"
    PG_DUMP_VERSION_MISMATCH = "PG_DUMP_VERSION_MISMATCH"
    PG_DUMP_FAILED = "PG_DUMP_FAILED"
    PG_DUMP_TIMEOUT = "PG_DUMP_TIMEOUT"
    SNAPSHOT_FAILED = "SNAPSHOT_FAILED"
    AGE_RECIPIENT_INVALID = "AGE_RECIPIENT_INVALID"
    AGE_TOOL_UNUSABLE = "AGE_TOOL_UNUSABLE"
    AGE_FAILED = "AGE_FAILED"
    ENCRYPT_TIMEOUT = "ENCRYPT_TIMEOUT"
    ARTIFACT_COLLISION = "ARTIFACT_COLLISION"
    UNSAFE_WORK_PATH = "UNSAFE_WORK_PATH"
    INSUFFICIENT_SPACE = "INSUFFICIENT_SPACE"
    PLAINTEXT_INTEGRITY = "PLAINTEXT_INTEGRITY"
    COMPRESSION_FAILED = "COMPRESSION_FAILED"
    ARTIFACT_FINALIZE_FAILED = "ARTIFACT_FINALIZE_FAILED"
    PLAINTEXT_CLEANUP_FAILED = "PLAINTEXT_CLEANUP_FAILED"
    CANCELLED = "CANCELLED"
    UNEXPECTED_ERROR = "UNEXPECTED_ERROR"


# Most specific classes first (isinstance order matters).
_ERROR_CODES: tuple[tuple[type[BaseException], ErrorCode], ...] = (
    (PassfileError, ErrorCode.PASSFILE_INVALID),
    (PgConnectionConfigError, ErrorCode.CONFIGURATION_INVALID),
    (ExpectedHeadError, ErrorCode.SCHEMA_HEAD_UNRESOLVED),
    (SchemaRevisionMismatchError, ErrorCode.SCHEMA_REVISION_MISMATCH),
    (ObservedRevisionError, ErrorCode.SCHEMA_REVISION_INVALID),
    (ReadySetFormatError, ErrorCode.READY_SET_INVALID),
    (PgDumpVersionMismatchError, ErrorCode.PG_DUMP_VERSION_MISMATCH),
    (PgDumpTimeoutError, ErrorCode.PG_DUMP_TIMEOUT),
    (PgDumpFailedError, ErrorCode.PG_DUMP_FAILED),
    (SnapshotDumpError, ErrorCode.SNAPSHOT_FAILED),
    (AgeRecipientError, ErrorCode.AGE_RECIPIENT_INVALID),
    (AgeToolError, ErrorCode.AGE_TOOL_UNUSABLE),
    (AgeFailedError, ErrorCode.AGE_FAILED),
    (EncryptTimeoutError, ErrorCode.ENCRYPT_TIMEOUT),
    (ArtifactCollisionError, ErrorCode.ARTIFACT_COLLISION),
    (UnsafeWorkPathError, ErrorCode.UNSAFE_WORK_PATH),
    (InsufficientSpaceError, ErrorCode.INSUFFICIENT_SPACE),
    (PlaintextIntegrityError, ErrorCode.PLAINTEXT_INTEGRITY),
    (CompressionError, ErrorCode.COMPRESSION_FAILED),
    (ArtifactFinalizeError, ErrorCode.ARTIFACT_FINALIZE_FAILED),
    (PlaintextCleanupError, ErrorCode.PLAINTEXT_CLEANUP_FAILED),
)


def error_code_for(exc: BaseException) -> ErrorCode:
    """Stable code for an exception -- by type only; the message is never used."""
    if isinstance(exc, asyncio.CancelledError):
        return ErrorCode.CANCELLED
    for kind, code in _ERROR_CODES:
        if isinstance(exc, kind):
            return code
    return ErrorCode.UNEXPECTED_ERROR


@dataclass(frozen=True)
class FailedRunEvidence:
    """Allowlisted failure record: no message, stderr, path or environment field exists."""

    run_id: str
    started_at: datetime
    failed_at: datetime
    stage: FailureStage
    error_code: ErrorCode
    plaintext_retained: bool
    artifact_valid: bool
    partials_present: bool

    def __post_init__(self) -> None:
        try:
            validate_run_id(self.run_id)
        except ValueError:
            raise EvidenceError("run_id is not a valid run id") from None
        format_timestamp(self.started_at, "started_at")
        format_timestamp(self.failed_at, "failed_at")
        if self.started_at > self.failed_at:
            raise EvidenceError("failed_at must not precede started_at")
        if not isinstance(self.stage, FailureStage):
            raise EvidenceError("stage must be a FailureStage")
        if not isinstance(self.error_code, ErrorCode):
            raise EvidenceError("error_code must be an ErrorCode")
        _flag(self.plaintext_retained, "plaintext_retained")
        _flag(self.artifact_valid, "artifact_valid")
        _flag(self.partials_present, "partials_present")

    def to_document(self) -> dict[str, Any]:
        return {
            "format": FORMAT_FAILED,
            "status": "failed",
            "run_id": self.run_id,
            "started_at": format_timestamp(self.started_at),
            "failed_at": format_timestamp(self.failed_at),
            "failure": {
                "stage": self.stage.value,
                "error_code": self.error_code.value,
                "plaintext_retained": self.plaintext_retained,
                "artifact_valid": self.artifact_valid,
                "partials_present": self.partials_present,
            },
        }

    def to_canonical_json(self) -> bytes:
        return canonical_json(self.to_document())
