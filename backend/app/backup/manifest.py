"""Backup manifest v1, COMPLETE.json and SHA-256 provenance (Stage 14D.2E, pure).

Contract: docs/STAGE_14D_BACKUP_RESTORE_PLAN.md §6 (manifest v1), §7 (DB /
media completeness invariant), §8 (SHA-256 provenance), §10 (integrity model).
No I/O, no network, no clock, no randomness: every function takes bytes or
plain values and returns bytes or plain values, so the later uploader, verify
and restore tooling share one definition of "a valid backup run".

A manifest describes exactly one backup run that is complete for the READY
photo assets of one database snapshot:

  * `manifest.jsonl` -- JSON Lines, canonical form (sorted keys, compact
    separators, ASCII, one `\\n`-terminated line each): one `header`, then one
    `object` line per required object sorted by key, then one `summary`. Parsing
    accepts only exactly the bytes the builder would produce, so
    `sha256(manifest bytes)` is well defined.
  * every READY asset has exactly three object lines (original, display,
    thumbnail) whose keys, sizes and original SHA-256 reproduce the header's
    `ready_set_sha256` (the 14D.2A READY-set digest) -- the manifest is
    self-verifying against the snapshot it claims.
  * `COMPLETE.json` seals the run: it repeats the manifest SHA-256 and the
    headline numbers. A manifest without a COMPLETE.json that matches it is
    incomplete by definition and is never a restore source or SHA provenance.

Object failures are not representable: a run with a missing, mismatching or
unreachable object produces no manifest and no COMPLETE.json at all (plan §15);
its error report is a separate artifact.

Provider ETags are diagnostic only (`target_etag`, nullable) and never part of
any decision here (plan §8). Error messages name fields and counts, never
values (no key, hash or recipient is echoed).
"""

import enum
import hashlib
import json
import re
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.backup.run_id import RunIdError, validate_run_id
from app.domain.photos.keys import (
    DERIVATIVE_CONTENT_TYPE,
    ORIGINAL_CONTENT_TYPES,
    ORIGINAL_EXTENSIONS,
    PHOTO_KEY_PREFIX,
)
from app.domain.services.media_backup_ready_set import (
    ReadyAsset,
    ReadySetFormatError,
    ready_set_digest,
)

MANIFEST_VERSION = 1
MANIFEST_NAME = "manifest.jsonl"
COMPLETE_NAME = "COMPLETE.json"
DB_DUMP_NAME = "plan-estimate.sql.gz.age"  # equals app.core.db_dump_encryption.ENCRYPTED_DUMP_NAME (tested)
ENCRYPTION = "age"
SNAPSHOT_METHOD = "exported-snapshot"
TIMESTAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
MAX_COUNT = 2**53 - 1  # exact in every JSON implementation
MAX_LINE_BYTES = 4096
MAX_RECIPIENTS = 32
OBJECTS_PER_ASSET = 3

_RUNS_PREFIX = "runs/"
_DB_PREFIX = "db/"
_TIMESTAMP = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$", re.ASCII)
_SHA256 = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_COMMIT = re.compile(r"^[0-9a-f]{40}$", re.ASCII)
_BUCKET = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", re.ASCII)
_STORAGE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,62}$", re.ASCII)
_RECIPIENT = re.compile(r"^age1[02-9ac-hj-np-z]{58}$", re.ASCII)  # native X25519 only (db_dump_encryption)
_REVISION = re.compile(r"^[0-9A-Za-z_]{1,64}$", re.ASCII)
_ETAG = re.compile(r"^[\x21-\x7e]{1,200}$", re.ASCII)  # opaque, printable, no whitespace
_ORIGINAL_CONTENT_TYPE_BY_EXTENSION = {
    ORIGINAL_EXTENSIONS[fmt]: ORIGINAL_CONTENT_TYPES[fmt] for fmt in ORIGINAL_EXTENSIONS
}


class ManifestError(ValueError):
    """Base class. Messages name fields and counts, never values."""


class ManifestFormatError(ManifestError):
    """A byte stream or a field is not a valid manifest / COMPLETE.json value."""


class ManifestInvariantError(ManifestError):
    """Individually valid lines that violate a completeness invariant (plan §7)."""


class CompleteMismatchError(ManifestError):
    """COMPLETE.json does not seal the given manifest."""


class Role(enum.StrEnum):
    ORIGINAL = "original"
    DISPLAY = "display"
    THUMBNAIL = "thumbnail"


class Action(enum.StrEnum):
    COPIED = "copied"
    ALREADY_PRESENT = "already_present"


# --- keys ----------------------------------------------------------------------------


def manifest_key(run_id: str) -> str:
    return f"{_RUNS_PREFIX}{validate_run_id(run_id)}/{MANIFEST_NAME}"


def complete_key(run_id: str) -> str:
    return f"{_RUNS_PREFIX}{validate_run_id(run_id)}/{COMPLETE_NAME}"


def db_dump_key(run_id: str) -> str:
    return f"{_DB_PREFIX}{validate_run_id(run_id)}/{DB_DUMP_NAME}"


# --- field validators ----------------------------------------------------------------


def _text(value: object, field_name: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise ManifestFormatError(f"{field_name} is not a valid value")
    return value


def _count(value: object, field_name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= MAX_COUNT:
        raise ManifestFormatError(f"{field_name} must be an integer in [{minimum}, {MAX_COUNT}]")
    return value


def _sha256(value: object, field_name: str) -> str:
    return _text(value, field_name, _SHA256)


def _timestamp(value: object, field_name: str) -> str:
    text = _text(value, field_name, _TIMESTAMP)
    try:
        datetime.strptime(text, TIMESTAMP_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        raise ManifestFormatError(f"{field_name} is not a real UTC date/time") from None
    return text


def _run_id(value: object, field_name: str) -> str:
    try:
        return validate_run_id(value)
    except RunIdError:
        raise ManifestFormatError(f"{field_name} is not a valid run_id") from None


def _asset_id(value: object, field_name: str) -> str:
    if isinstance(value, str):
        try:
            parsed = uuid.UUID(value)
        except ValueError:
            parsed = None
        if parsed is not None and parsed.version == 4 and str(parsed) == value:
            return value
    raise ManifestFormatError(f"{field_name} must be a canonical UUIDv4 text")


def _exact_keys(document: Mapping[str, Any], expected: Iterable[str], where: str) -> None:
    if sorted(document) != sorted(expected):
        raise ManifestFormatError(f"{where} does not have exactly the expected fields")


def format_timestamp(value: datetime) -> str:
    """UTC `YYYY-MM-DDTHH:MM:SSZ` from a timezone-aware datetime."""
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ManifestFormatError("timestamp must be a timezone-aware datetime")
    return value.astimezone(UTC).strftime(TIMESTAMP_FORMAT)


def canonical_line(document: Mapping[str, Any]) -> bytes:
    """Deterministic bytes: sorted keys, compact separators, ASCII, no NaN, trailing newline."""
    return (
        json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n"
    ).encode("ascii")


# --- header --------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceInfo:
    storage_name: str
    bucket: str

    def __post_init__(self) -> None:
        _text(self.storage_name, "source.storage_name", _STORAGE_NAME)
        _text(self.bucket, "source.bucket", _BUCKET)

    def to_dict(self) -> dict[str, Any]:
        return {"storage_name": self.storage_name, "bucket": self.bucket}


@dataclass(frozen=True)
class TargetInfo:
    bucket: str

    def __post_init__(self) -> None:
        _text(self.bucket, "target.bucket", _BUCKET)

    def to_dict(self) -> dict[str, Any]:
        return {"bucket": self.bucket}


@dataclass(frozen=True)
class DbDumpInfo:
    key: str
    recipients: tuple[str, ...]
    encrypted_sha256: str
    encrypted_size: int
    alembic_head: str
    dumped_at: str
    encryption: str = ENCRYPTION

    def __post_init__(self) -> None:
        if self.encryption != ENCRYPTION:
            raise ManifestFormatError("db_dump.encryption must be 'age'")
        if not isinstance(self.key, str):
            raise ManifestFormatError("db_dump.key is not a valid value")
        if not isinstance(self.recipients, tuple) or not 1 <= len(self.recipients) <= MAX_RECIPIENTS:
            raise ManifestFormatError(f"db_dump.recipients must hold 1..{MAX_RECIPIENTS} public recipients")
        for recipient in self.recipients:
            _text(recipient, "db_dump.recipients[]", _RECIPIENT)
        if len(set(self.recipients)) != len(self.recipients):
            raise ManifestFormatError("db_dump.recipients contains duplicates")
        _sha256(self.encrypted_sha256, "db_dump.encrypted_sha256")
        _count(self.encrypted_size, "db_dump.encrypted_size", minimum=1)
        _text(self.alembic_head, "db_dump.alembic_head", _REVISION)
        _timestamp(self.dumped_at, "db_dump.dumped_at")

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "encryption": self.encryption,
            "recipients": list(self.recipients),
            "encrypted_sha256": self.encrypted_sha256,
            "encrypted_size": self.encrypted_size,
            "alembic_head": self.alembic_head,
            "dumped_at": self.dumped_at,
        }


@dataclass(frozen=True)
class SnapshotInfo:
    ready_count: int
    ready_set_sha256: str
    method: str = SNAPSHOT_METHOD

    def __post_init__(self) -> None:
        if self.method != SNAPSHOT_METHOD:
            raise ManifestFormatError("snapshot.method must be 'exported-snapshot'")
        _count(self.ready_count, "snapshot.ready_count")
        _sha256(self.ready_set_sha256, "snapshot.ready_set_sha256")

    def to_dict(self) -> dict[str, Any]:
        return {"method": self.method, "ready_count": self.ready_count, "ready_set_sha256": self.ready_set_sha256}


@dataclass(frozen=True)
class ManifestHeader:
    run_id: str
    started_at: str
    tool_commit: str
    source: SourceInfo
    target: TargetInfo
    db_dump: DbDumpInfo
    snapshot: SnapshotInfo
    manifest_version: int = MANIFEST_VERSION

    def __post_init__(self) -> None:
        if self.manifest_version != MANIFEST_VERSION or isinstance(self.manifest_version, bool):
            raise ManifestFormatError("manifest_version must be 1")
        _run_id(self.run_id, "run_id")
        _timestamp(self.started_at, "started_at")
        _text(self.tool_commit, "tool_commit", _COMMIT)
        if self.source.bucket == self.target.bucket:
            raise ManifestInvariantError("source and target bucket must differ (independent backup target)")
        if self.db_dump.key != db_dump_key(self.run_id):
            raise ManifestInvariantError("db_dump.key does not match the run_id")

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "header",
            "manifest_version": self.manifest_version,
            "run_id": self.run_id,
            "started_at": self.started_at,
            "tool_commit": self.tool_commit,
            "source": self.source.to_dict(),
            "target": self.target.to_dict(),
            "db_dump": self.db_dump.to_dict(),
            "snapshot": self.snapshot.to_dict(),
        }


# --- object lines --------------------------------------------------------------------

DOWNLOADED = "downloaded"
_INHERITED_PREFIX = "inherited:"


def inherited_provenance(run_id: str) -> str:
    return f"{_INHERITED_PREFIX}{validate_run_id(run_id)}"


def inherited_run_id(provenance: str) -> str | None:
    """The run a provenance string was inherited from, None for `downloaded`."""
    if provenance == DOWNLOADED:
        return None
    if provenance.startswith(_INHERITED_PREFIX):
        return _run_id(provenance[len(_INHERITED_PREFIX) :], "sha_provenance")
    raise ManifestFormatError("sha_provenance must be 'downloaded' or 'inherited:<run_id>'")


@dataclass(frozen=True)
class ManifestObject:
    asset_id: str
    role: Role
    key: str
    size: int
    sha256: str
    content_type: str
    action: Action
    sha_provenance: str
    verified_at: str
    target_etag: str | None = None

    def __post_init__(self) -> None:
        _asset_id(self.asset_id, "asset_id")
        if not isinstance(self.role, Role):
            raise ManifestFormatError("role is not a valid value")
        if not isinstance(self.action, Action):
            raise ManifestFormatError("action is not a valid value")
        _count(self.size, "size", minimum=1)
        _sha256(self.sha256, "sha256")
        _timestamp(self.verified_at, "verified_at")
        if self.target_etag is not None:
            _text(self.target_etag, "target_etag", _ETAG)
        self._check_key_and_content_type()
        if not isinstance(self.sha_provenance, str):
            raise ManifestFormatError("sha_provenance is not a valid value")
        source_run = inherited_run_id(self.sha_provenance)
        if self.action is Action.COPIED and source_run is not None:
            raise ManifestFormatError("a copied object is always verified by download (sha_provenance 'downloaded')")

    def _check_key_and_content_type(self) -> None:
        base = f"{PHOTO_KEY_PREFIX}{self.asset_id}/"
        if not isinstance(self.key, str) or not self.key.startswith(base):
            raise ManifestFormatError("key does not belong to asset_id")
        name = self.key[len(base) :]
        if self.role is Role.ORIGINAL:
            stem, _, extension = name.partition(".")
            expected_type = _ORIGINAL_CONTENT_TYPE_BY_EXTENSION.get(extension)
            if stem != "original" or expected_type is None:
                raise ManifestFormatError("key is not a valid original key")
        elif self.role is Role.DISPLAY:
            expected_type = DERIVATIVE_CONTENT_TYPE
            if name != "display.jpg":
                raise ManifestFormatError("key is not the display key")
        else:
            expected_type = DERIVATIVE_CONTENT_TYPE
            if name != "thumb.jpg":
                raise ManifestFormatError("key is not the thumbnail key")
        if self.content_type != expected_type:
            raise ManifestFormatError("content_type does not match the object role / key")

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "object",
            "asset_id": self.asset_id,
            "role": self.role.value,
            "key": self.key,
            "size": self.size,
            "sha256": self.sha256,
            "content_type": self.content_type,
            "action": self.action.value,
            "sha_provenance": self.sha_provenance,
            "target_etag": self.target_etag,
            "verified_at": self.verified_at,
        }


# --- summary -------------------------------------------------------------------------


@dataclass(frozen=True)
class ManifestSummary:
    ready_assets: int
    objects: int
    total_bytes: int
    skipped_pending: int
    skipped_failed: int
    source_keys: int
    orphan_candidates: int

    def __post_init__(self) -> None:
        for name in (
            "ready_assets",
            "objects",
            "total_bytes",
            "skipped_pending",
            "skipped_failed",
            "source_keys",
            "orphan_candidates",
        ):
            _count(getattr(self, name), f"summary.{name}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "summary",
            "ready_assets": self.ready_assets,
            "objects": self.objects,
            "bytes": self.total_bytes,
            "skipped": {"pending": self.skipped_pending, "failed": self.skipped_failed},
            "source_listing": {"keys": self.source_keys, "orphan_candidates": self.orphan_candidates},
        }


# --- the manifest --------------------------------------------------------------------


def ready_assets_from_objects(objects: Iterable[ManifestObject]) -> tuple[ReadyAsset, ...]:
    """The READY assets the object lines describe (exactly three lines each).

    Everything the 14D.2A READY-set line needs is in the object lines: the three
    keys, the three sizes and the original's SHA-256."""
    grouped: dict[str, dict[Role, ManifestObject]] = {}
    for obj in objects:
        slot = grouped.setdefault(obj.asset_id, {})
        if obj.role in slot:
            raise ManifestInvariantError("an asset has two object lines for the same role")
        slot[obj.role] = obj
    assets: list[ReadyAsset] = []
    for asset_id, slot in grouped.items():
        if len(slot) != OBJECTS_PER_ASSET:
            raise ManifestInvariantError(
                f"an asset has {len(slot)} object lines (expected exactly {OBJECTS_PER_ASSET})"
            )
        original, display, thumbnail = slot[Role.ORIGINAL], slot[Role.DISPLAY], slot[Role.THUMBNAIL]
        try:
            assets.append(
                ReadyAsset(
                    asset_id=uuid.UUID(asset_id),
                    key_original=original.key,
                    key_display=display.key,
                    key_thumbnail=thumbnail.key,
                    byte_size=original.size,
                    display_byte_size=display.size,
                    thumbnail_byte_size=thumbnail.size,
                    sha256=original.sha256,
                )
            )
        except ReadySetFormatError:
            raise ManifestInvariantError("an asset cannot be represented in the READY set") from None
    return tuple(assets)


@dataclass(frozen=True)
class Manifest:
    header: ManifestHeader
    objects: tuple[ManifestObject, ...]
    summary: ManifestSummary

    def __post_init__(self) -> None:
        if not isinstance(self.objects, tuple):
            raise ManifestFormatError("objects must be a tuple")
        keys = [obj.key for obj in self.objects]
        if keys != sorted(keys):
            raise ManifestInvariantError("object lines are not sorted by key")
        if len(set(keys)) != len(keys):
            raise ManifestInvariantError("two object lines share a key")
        started = self.header.started_at
        for obj in self.objects:
            if obj.verified_at < started:
                raise ManifestInvariantError("an object was verified before the run started")
            source_run = inherited_run_id(obj.sha_provenance)
            if source_run is not None and source_run >= self.header.run_id:
                raise ManifestInvariantError("an object inherits provenance from a run that is not earlier")

        assets = ready_assets_from_objects(self.objects)
        digest = ready_set_digest(assets)
        if (digest.ready_count, digest.ready_set_sha256) != (
            self.header.snapshot.ready_count,
            self.header.snapshot.ready_set_sha256,
        ):
            raise ManifestInvariantError("the object lines do not reproduce the snapshot's READY-set digest")

        summary = self.summary
        if summary.ready_assets != self.header.snapshot.ready_count or summary.ready_assets != len(assets):
            raise ManifestInvariantError("summary.ready_assets does not match the snapshot / object lines")
        if summary.objects != len(self.objects) or summary.objects != OBJECTS_PER_ASSET * len(assets):
            raise ManifestInvariantError("summary.objects does not match the object lines")
        if summary.total_bytes != sum(obj.size for obj in self.objects):
            raise ManifestInvariantError("summary.bytes does not match the object lines")

    def to_bytes(self) -> bytes:
        lines = [canonical_line(self.header.to_dict())]
        lines.extend(canonical_line(obj.to_dict()) for obj in self.objects)
        lines.append(canonical_line(self.summary.to_dict()))
        return b"".join(lines)

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.to_bytes()).hexdigest()


def build_manifest(
    header: ManifestHeader,
    objects: Iterable[ManifestObject],
    *,
    skipped_pending: int = 0,
    skipped_failed: int = 0,
    source_keys: int,
    orphan_candidates: int,
) -> Manifest:
    """Sort the objects into canonical order, derive the summary and validate everything."""
    ordered = tuple(sorted(objects, key=lambda obj: obj.key))
    assets = len({obj.asset_id for obj in ordered})
    summary = ManifestSummary(
        ready_assets=assets,
        objects=len(ordered),
        total_bytes=sum(obj.size for obj in ordered),
        skipped_pending=skipped_pending,
        skipped_failed=skipped_failed,
        source_keys=source_keys,
        orphan_candidates=orphan_candidates,
    )
    return Manifest(header, ordered, summary)


def verify_against_ready_set(manifest: Manifest, ready_assets: Iterable[ReadyAsset]) -> None:
    """The manifest describes exactly this READY set (backup time: the snapshot's
    inventory; restore time: the set recomputed from the restored database)."""
    expected = list(ready_assets)
    try:
        digest = ready_set_digest(expected)
    except ReadySetFormatError:
        raise ManifestInvariantError("the READY set cannot be represented canonically") from None
    snapshot = manifest.header.snapshot
    if (digest.ready_count, digest.ready_set_sha256) == (snapshot.ready_count, snapshot.ready_set_sha256):
        return
    described = {asset.asset_id: asset for asset in ready_assets_from_objects(manifest.objects)}
    wanted = {asset.asset_id: asset for asset in expected}
    not_in_manifest = len(wanted.keys() - described.keys())
    not_in_ready_set = len(described.keys() - wanted.keys())
    changed = sum(1 for asset_id in wanted.keys() & described.keys() if wanted[asset_id] != described[asset_id])
    raise ManifestInvariantError(
        "the READY set differs from the manifest: "
        f"not_in_manifest={not_in_manifest}, not_in_ready_set={not_in_ready_set}, changed={changed}"
    )


# --- parsing -------------------------------------------------------------------------


def _loads(line: str, where: str) -> dict[str, Any]:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        document: dict[str, Any] = {}
        for name, value in pairs:
            if name in document:
                raise ManifestFormatError(f"{where} repeats a field")
            document[name] = value
        return document

    def reject_constant(_: str) -> Any:
        raise ManifestFormatError(f"{where} contains a non-finite number")

    try:
        document = json.loads(line, object_pairs_hook=reject_duplicates, parse_constant=reject_constant)
    except ManifestFormatError:
        raise
    except (ValueError, RecursionError):
        raise ManifestFormatError(f"{where} is not valid JSON") from None
    if not isinstance(document, dict):
        raise ManifestFormatError(f"{where} is not a JSON object")
    return document


def _nested(document: Mapping[str, Any], name: str, expected: Iterable[str], where: str) -> Mapping[str, Any]:
    value = document[name]
    if not isinstance(value, dict):
        raise ManifestFormatError(f"{where}.{name} is not an object")
    _exact_keys(value, expected, f"{where}.{name}")
    return value


def _header_from(document: Mapping[str, Any]) -> ManifestHeader:
    where = "header"
    _exact_keys(
        document,
        ("type", "manifest_version", "run_id", "started_at", "tool_commit", "source", "target", "db_dump", "snapshot"),
        where,
    )
    source = _nested(document, "source", ("storage_name", "bucket"), where)
    target = _nested(document, "target", ("bucket",), where)
    dump = _nested(
        document,
        "db_dump",
        ("key", "encryption", "recipients", "encrypted_sha256", "encrypted_size", "alembic_head", "dumped_at"),
        where,
    )
    snapshot = _nested(document, "snapshot", ("method", "ready_count", "ready_set_sha256"), where)
    recipients = dump["recipients"]
    if not isinstance(recipients, list):
        raise ManifestFormatError("header.db_dump.recipients is not a list")
    return ManifestHeader(
        manifest_version=document["manifest_version"],
        run_id=document["run_id"],
        started_at=document["started_at"],
        tool_commit=document["tool_commit"],
        source=SourceInfo(storage_name=source["storage_name"], bucket=source["bucket"]),
        target=TargetInfo(bucket=target["bucket"]),
        db_dump=DbDumpInfo(
            key=dump["key"],
            encryption=dump["encryption"],
            recipients=tuple(recipients),
            encrypted_sha256=dump["encrypted_sha256"],
            encrypted_size=dump["encrypted_size"],
            alembic_head=dump["alembic_head"],
            dumped_at=dump["dumped_at"],
        ),
        snapshot=SnapshotInfo(
            method=snapshot["method"],
            ready_count=snapshot["ready_count"],
            ready_set_sha256=snapshot["ready_set_sha256"],
        ),
    )


def _object_from(document: Mapping[str, Any]) -> ManifestObject:
    _exact_keys(
        document,
        (
            "type",
            "asset_id",
            "role",
            "key",
            "size",
            "sha256",
            "content_type",
            "action",
            "sha_provenance",
            "target_etag",
            "verified_at",
        ),
        "object line",
    )
    try:
        role, action = Role(document["role"]), Action(document["action"])
    except ValueError:
        raise ManifestFormatError("object line has an unknown role or action") from None
    return ManifestObject(
        asset_id=document["asset_id"],
        role=role,
        key=document["key"],
        size=document["size"],
        sha256=document["sha256"],
        content_type=document["content_type"],
        action=action,
        sha_provenance=document["sha_provenance"],
        target_etag=document["target_etag"],
        verified_at=document["verified_at"],
    )


def _summary_from(document: Mapping[str, Any]) -> ManifestSummary:
    where = "summary"
    _exact_keys(document, ("type", "ready_assets", "objects", "bytes", "skipped", "source_listing"), where)
    skipped = _nested(document, "skipped", ("pending", "failed"), where)
    listing = _nested(document, "source_listing", ("keys", "orphan_candidates"), where)
    return ManifestSummary(
        ready_assets=document["ready_assets"],
        objects=document["objects"],
        total_bytes=document["bytes"],
        skipped_pending=skipped["pending"],
        skipped_failed=skipped["failed"],
        source_keys=listing["keys"],
        orphan_candidates=listing["orphan_candidates"],
    )


def parse_manifest(data: bytes) -> Manifest:
    """Parse and fully validate `manifest.jsonl`. Accepts only canonical bytes."""
    if not isinstance(data, (bytes, bytearray)):
        raise ManifestFormatError("manifest must be bytes")
    raw = bytes(data)
    if not raw.endswith(b"\n"):
        raise ManifestFormatError("manifest does not end with a newline")
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        raise ManifestFormatError("manifest is not ASCII") from None
    lines = text.split("\n")[:-1]
    if len(lines) < 2:
        raise ManifestFormatError("manifest needs a header line and a summary line")
    if any(not line or len(line) > MAX_LINE_BYTES for line in lines):
        raise ManifestFormatError("manifest has an empty or oversized line")
    documents = [_loads(line, f"line {number}") for number, line in enumerate(lines, start=1)]
    if documents[0].get("type") != "header" or documents[-1].get("type") != "summary":
        raise ManifestFormatError("manifest must start with the header and end with the summary")
    if any(document.get("type") != "object" for document in documents[1:-1]):
        raise ManifestFormatError("manifest has a line of unexpected type between header and summary")
    manifest = Manifest(
        _header_from(documents[0]),
        tuple(_object_from(document) for document in documents[1:-1]),
        _summary_from(documents[-1]),
    )
    if manifest.to_bytes() != raw:
        raise ManifestFormatError("manifest is not in canonical form")
    return manifest


# --- COMPLETE.json -------------------------------------------------------------------


@dataclass(frozen=True)
class CompleteRecord:
    run_id: str
    manifest_key: str
    manifest_sha256: str
    objects: int
    total_bytes: int
    ready_assets: int
    ready_set_sha256: str
    db_dump_encrypted_sha256: str
    completed_at: str
    manifest_version: int = MANIFEST_VERSION

    def __post_init__(self) -> None:
        if self.manifest_version != MANIFEST_VERSION or isinstance(self.manifest_version, bool):
            raise ManifestFormatError("manifest_version must be 1")
        _run_id(self.run_id, "run_id")
        if self.manifest_key != manifest_key(self.run_id):
            raise ManifestFormatError("manifest_key does not match the run_id")
        _sha256(self.manifest_sha256, "manifest_sha256")
        _count(self.objects, "objects")
        _count(self.total_bytes, "bytes")
        _count(self.ready_assets, "ready_assets")
        _sha256(self.ready_set_sha256, "ready_set_sha256")
        _sha256(self.db_dump_encrypted_sha256, "db_dump_encrypted_sha256")
        _timestamp(self.completed_at, "completed_at")

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "manifest_version": self.manifest_version,
            "manifest_key": self.manifest_key,
            "manifest_sha256": self.manifest_sha256,
            "objects": self.objects,
            "bytes": self.total_bytes,
            "ready_assets": self.ready_assets,
            "ready_set_sha256": self.ready_set_sha256,
            "db_dump_encrypted_sha256": self.db_dump_encrypted_sha256,
            "completed_at": self.completed_at,
        }

    def to_bytes(self) -> bytes:
        return canonical_line(self.to_dict())


def build_complete(manifest: Manifest, completed_at: datetime) -> CompleteRecord:
    """The seal for a validated manifest. Written last, only when every invariant holds."""
    stamp = format_timestamp(completed_at)
    latest = max([manifest.header.started_at, *(obj.verified_at for obj in manifest.objects)])
    if stamp < latest:
        raise ManifestInvariantError("completed_at precedes the run's own timestamps")
    return CompleteRecord(
        run_id=manifest.header.run_id,
        manifest_key=manifest_key(manifest.header.run_id),
        manifest_sha256=manifest.sha256,
        objects=manifest.summary.objects,
        total_bytes=manifest.summary.total_bytes,
        ready_assets=manifest.summary.ready_assets,
        ready_set_sha256=manifest.header.snapshot.ready_set_sha256,
        db_dump_encrypted_sha256=manifest.header.db_dump.encrypted_sha256,
        completed_at=stamp,
    )


def parse_complete(data: bytes) -> CompleteRecord:
    """Parse `COMPLETE.json`. Accepts only canonical bytes."""
    if not isinstance(data, (bytes, bytearray)):
        raise ManifestFormatError("COMPLETE.json must be bytes")
    raw = bytes(data)
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError:
        raise ManifestFormatError("COMPLETE.json is not ASCII") from None
    if not text.endswith("\n") or text.count("\n") != 1 or len(text) > MAX_LINE_BYTES:
        raise ManifestFormatError("COMPLETE.json must be a single canonical line")
    document = _loads(text[:-1], "COMPLETE.json")
    _exact_keys(
        document,
        (
            "run_id",
            "manifest_version",
            "manifest_key",
            "manifest_sha256",
            "objects",
            "bytes",
            "ready_assets",
            "ready_set_sha256",
            "db_dump_encrypted_sha256",
            "completed_at",
        ),
        "COMPLETE.json",
    )
    record = CompleteRecord(
        run_id=document["run_id"],
        manifest_version=document["manifest_version"],
        manifest_key=document["manifest_key"],
        manifest_sha256=document["manifest_sha256"],
        objects=document["objects"],
        total_bytes=document["bytes"],
        ready_assets=document["ready_assets"],
        ready_set_sha256=document["ready_set_sha256"],
        db_dump_encrypted_sha256=document["db_dump_encrypted_sha256"],
        completed_at=document["completed_at"],
    )
    if record.to_bytes() != raw:
        raise ManifestFormatError("COMPLETE.json is not in canonical form")
    return record


@dataclass(frozen=True)
class VerifiedRun:
    """A run whose COMPLETE.json seals its (re-parsed, re-validated) manifest."""

    complete: CompleteRecord
    manifest: Manifest
    _by_key: dict[str, ManifestObject] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_by_key", {obj.key: obj for obj in self.manifest.objects})

    @property
    def run_id(self) -> str:
        return self.complete.run_id

    def object_for(self, key: str) -> ManifestObject | None:
        return self._by_key.get(key)


def verify_run(complete_bytes: bytes, manifest_bytes: bytes) -> VerifiedRun:
    """COMPLETE.json seals this manifest (plan §8.2.1-2, §10 'Manifest')."""
    complete = parse_complete(complete_bytes)
    if hashlib.sha256(manifest_bytes).hexdigest() != complete.manifest_sha256:
        raise CompleteMismatchError("the manifest's SHA-256 is not the one COMPLETE.json records")
    manifest = parse_manifest(manifest_bytes)
    header, summary = manifest.header, manifest.summary
    checks = {
        "run_id": complete.run_id == header.run_id,
        "objects": complete.objects == summary.objects,
        "bytes": complete.total_bytes == summary.total_bytes,
        "ready_assets": complete.ready_assets == summary.ready_assets,
        "ready_set_sha256": complete.ready_set_sha256 == header.snapshot.ready_set_sha256,
        "db_dump_encrypted_sha256": complete.db_dump_encrypted_sha256 == header.db_dump.encrypted_sha256,
    }
    wrong = [name for name, ok in checks.items() if not ok]
    if wrong:
        raise CompleteMismatchError(f"COMPLETE.json disagrees with the manifest: {', '.join(wrong)}")
    latest = max([header.started_at, *(obj.verified_at for obj in manifest.objects)])
    if complete.completed_at < latest:
        raise CompleteMismatchError("COMPLETE.json predates the run's own timestamps")
    return VerifiedRun(complete=complete, manifest=manifest)


# --- SHA-256 provenance (plan §8) ----------------------------------------------------


class ProvenanceKind(enum.StrEnum):
    DOWNLOAD = "download"
    INHERIT = "inherit"


class DownloadReason(enum.StrEnum):
    DEEP = "deep"
    NO_PRIOR_RUN = "no_prior_run"
    KEY_NOT_IN_PRIOR = "key_not_in_prior"
    SIZE_DIFFERS_FROM_PRIOR = "size_differs_from_prior"
    TARGET_MISSING = "target_missing"
    TARGET_SIZE_DIFFERS = "target_size_differs"
    SHA_DIFFERS_FROM_DB = "sha_differs_from_db"


@dataclass(frozen=True)
class ProvenanceDecision:
    kind: ProvenanceKind
    reason: DownloadReason | None = None
    run_id: str | None = None
    sha256: str | None = None

    @property
    def provenance(self) -> str:
        """The `sha_provenance` value for the object line."""
        if self.kind is ProvenanceKind.INHERIT and self.run_id is not None:
            return inherited_provenance(self.run_id)
        return DOWNLOADED


def decide_provenance(
    prior: VerifiedRun | None,
    *,
    key: str,
    expected_size: int,
    expected_sha256: str | None,
    target_size: int | None,
    deep: bool = False,
) -> ProvenanceDecision:
    """May an object already present in the target be admitted without re-downloading?

    `prior` is a run already verified by `verify_run` (valid COMPLETE.json whose
    manifest SHA-256 was recomputed -- plan §8.2.1-2). The rest of §8.2 is checked
    here: same key, size and a trusted SHA-256 in the prior manifest (3), the
    target object exists (4) and its current size matches (5). Originals must also
    equal the database SHA-256 (`expected_sha256`, None for derivatives).
    Anything short of that is a download -- never an assumption. A provider ETag
    is not an input.
    """

    def download(reason: DownloadReason) -> ProvenanceDecision:
        return ProvenanceDecision(ProvenanceKind.DOWNLOAD, reason=reason)

    if deep:
        return download(DownloadReason.DEEP)
    if prior is None:
        return download(DownloadReason.NO_PRIOR_RUN)
    recorded = prior.object_for(key)
    if recorded is None:
        return download(DownloadReason.KEY_NOT_IN_PRIOR)
    if recorded.size != expected_size:
        return download(DownloadReason.SIZE_DIFFERS_FROM_PRIOR)
    if target_size is None:
        return download(DownloadReason.TARGET_MISSING)
    if target_size != recorded.size:
        return download(DownloadReason.TARGET_SIZE_DIFFERS)
    if expected_sha256 is not None and recorded.sha256 != expected_sha256:
        return download(DownloadReason.SHA_DIFFERS_FROM_DB)
    return ProvenanceDecision(ProvenanceKind.INHERIT, run_id=prior.run_id, sha256=recorded.sha256)
