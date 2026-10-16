"""The purge ledger as a file: what was deleted for good and must not come back (archive cleanup AC-3).

The application deletes a photo from the working storage and writes a row to `purge_ledger` (AC-2). The backups still hold its objects until the
owner's separate step removes them, and an old database dump still holds its rows. This module is the **one reading of the ledger's exported
file** that the three consumers share:

    the owner's purge tool    which object versions to remove from the backup bucket
    verify / restore media    an object that the manifest lists but the backup no longer has is not an error when the ledger says it was purged
    restore replay            the rows of the purged photos are removed again from a database restored from an old dump

The file is canonical JSON lines, secret-free and content-free (keys, sums, sizes, times):

    {"format":"plan-estimate/purge-ledger/v1","count":N,"exported_at":"..."}      one header line
    {"asset_id":"<uuid4>","id":"<uuid>","keys":{"original":..,"display":..,"thumbnail":..},"kind":"PHOTO","purged_at":"..",
     "sha256":"<64 hex>","sizes":{"original":n,"display":n,"thumbnail":n},"storage_name":".."}                one line per deleted file set

The reader is strict **because a wrong line would delete the wrong object**: every key must be exactly one of the three keys of the named asset
(`photos/v1/<asset_id>/original.<ext> | display.jpg | thumb.jpg`), ids must be canonical UUIDs, a duplicate asset is refused, the count must match.
"""
import json
import re
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from app.backup.manifest import canonical_line
from app.domain.photos.keys import PHOTO_KEY_PREFIX

LEDGER_FORMAT = "plan-estimate/purge-ledger/v1"
MAX_ENTRIES = 100_000
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_ORIGINAL_NAME = re.compile(r"^original\.[a-z0-9]{2,5}$")


class PurgeLedgerError(ValueError):
    """The ledger file is not a valid export (a message without any key or content)."""


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    id: uuid.UUID
    asset_id: uuid.UUID
    storage_name: str
    key_original: str
    key_display: str
    key_thumbnail: str
    sha256: str
    size_original: int
    size_display: int
    size_thumbnail: int
    purged_at: str

    @property
    def keys(self) -> tuple[str, str, str]:
        return (self.key_original, self.key_display, self.key_thumbnail)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": str(self.id),
            "asset_id": str(self.asset_id),
            "kind": "PHOTO",
            "storage_name": self.storage_name,
            "keys": {"original": self.key_original, "display": self.key_display, "thumbnail": self.key_thumbnail},
            "sha256": self.sha256,
            "sizes": {"original": self.size_original, "display": self.size_display, "thumbnail": self.size_thumbnail},
            "purged_at": self.purged_at,
        }


@dataclass(frozen=True, slots=True)
class PurgeLedgerFile:
    entries: tuple[LedgerEntry, ...]
    exported_at: str

    @property
    def purged_keys(self) -> frozenset[str]:
        return frozenset(key for entry in self.entries for key in entry.keys)

    @property
    def asset_ids(self) -> frozenset[uuid.UUID]:
        return frozenset(entry.asset_id for entry in self.entries)


def serialize_ledger(entries: Sequence[LedgerEntry], *, exported_at: str) -> bytes:
    ordered = sorted(entries, key=lambda entry: (entry.purged_at, str(entry.asset_id)))
    header = canonical_line({"format": LEDGER_FORMAT, "count": len(ordered), "exported_at": exported_at})
    return header + b"".join(canonical_line(entry.to_dict()) for entry in ordered)


def _uuid(value: object, what: str) -> uuid.UUID:
    if not isinstance(value, str):
        raise PurgeLedgerError(f"{what} is not a UUID")
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        raise PurgeLedgerError(f"{what} is not a UUID") from None
    if str(parsed) != value:
        raise PurgeLedgerError(f"{what} is not a canonical UUID")
    return parsed


def _size(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise PurgeLedgerError("a size is not a positive integer")
    return value


def _entry(document: object) -> LedgerEntry:
    if not isinstance(document, dict):
        raise PurgeLedgerError("a ledger line is not an object")
    if document.get("kind") != "PHOTO":
        raise PurgeLedgerError("a ledger line is not a photo")
    asset_id = _uuid(document.get("asset_id"), "asset_id")
    keys, sizes = document.get("keys"), document.get("sizes")
    if not isinstance(keys, dict) or not isinstance(sizes, dict) or set(keys) != {"original", "display", "thumbnail"} or set(sizes) != set(keys):
        raise PurgeLedgerError("keys or sizes are malformed")
    base = f"{PHOTO_KEY_PREFIX}{asset_id}/"
    for key in keys.values():
        if not isinstance(key, str) or not key.startswith(base):
            raise PurgeLedgerError("a key does not belong to its asset")
    if not _ORIGINAL_NAME.match(keys["original"][len(base):]) or keys["display"] != f"{base}display.jpg" or keys["thumbnail"] != f"{base}thumb.jpg":
        raise PurgeLedgerError("a key is not one of the three keys of the asset")
    sha256, storage_name, purged_at = document.get("sha256"), document.get("storage_name"), document.get("purged_at")
    if not isinstance(sha256, str) or not _SHA256.match(sha256):
        raise PurgeLedgerError("sha256 is malformed")
    if not isinstance(storage_name, str) or not storage_name or not isinstance(purged_at, str) or not purged_at:
        raise PurgeLedgerError("storage_name or purged_at is malformed")
    return LedgerEntry(
        id=_uuid(document.get("id"), "id"), asset_id=asset_id, storage_name=storage_name,
        key_original=keys["original"], key_display=keys["display"], key_thumbnail=keys["thumbnail"], sha256=sha256,
        size_original=_size(sizes["original"]), size_display=_size(sizes["display"]), size_thumbnail=_size(sizes["thumbnail"]), purged_at=purged_at,
    )


def parse_ledger(data: bytes) -> PurgeLedgerFile:
    """The entries of an exported ledger file; raises `PurgeLedgerError` for anything that is not exactly that."""
    try:
        lines = data.decode("ascii").splitlines()
        documents = [json.loads(line) for line in lines if line.strip()]
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise PurgeLedgerError("the ledger file is not JSON lines") from None
    if not documents or not isinstance(documents[0], dict) or documents[0].get("format") != LEDGER_FORMAT:
        raise PurgeLedgerError("the ledger file has no valid header")
    header, rows = documents[0], documents[1:]
    exported_at = header.get("exported_at")
    if not isinstance(exported_at, str) or not exported_at or header.get("count") != len(rows) or len(rows) > MAX_ENTRIES:
        raise PurgeLedgerError("the header does not match the lines")
    entries = tuple(_entry(row) for row in rows)
    if len({entry.asset_id for entry in entries}) != len(entries) or len({entry.id for entry in entries}) != len(entries):
        raise PurgeLedgerError("a duplicate entry")
    return PurgeLedgerFile(entries, exported_at)


def purged_keys_of(entries: Iterable[LedgerEntry]) -> frozenset[str]:
    return frozenset(key for entry in entries for key in entry.keys)
