"""Canonical READY photo-asset set and its digest (Stage 14D.2A).

`docs/STAGE_14D_BACKUP_RESTORE_PLAN.md` §7: a media backup is bound to one
PostgreSQL snapshot; `ready_count` / `ready_set_sha256` identify exactly the
READY assets that snapshot contains, so the set can be recomputed
independently from a restored dump (Python or plain SQL) and compared.

Canonical serialization, version 1 (byte-exact):

    "plan-estimate/ready-set/v1\\n"
    + one line per READY asset, lines sorted by their bytes (equivalently by
      the asset id, which leads every line and has a fixed width):
      asset_id|key_original|key_display|key_thumbnail|byte_size|display_byte_size|thumbnail_byte_size|sha256\\n

- `asset_id`: canonical lowercase hyphenated UUID text (`str(uuid.UUID)`,
  PostgreSQL `id::text`).
- keys: printable ASCII 0x21-0x7E, non-empty, never containing `|`.
- sizes: positive integers in base-10 ASCII without sign, padding or leading
  zeros (Python `str(int)`, PostgreSQL `bigint::text`).
- `sha256`: 64 lowercase hexadecimal characters.
- encoding ASCII (hence UTF-8), separator `|` (0x7C), terminator `\\n`
  (0x0A); no other whitespace.

`ready_set_sha256` = lowercase hex SHA-256 of those bytes. An empty set is the
header alone, so it has a fixed, well-defined digest. Any value that does not
satisfy the rules raises `ReadySetFormatError` -- it is never normalized or
silently skipped.
"""

import hashlib
import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass

READY_SET_HEADER = b"plan-estimate/ready-set/v1\n"
FIELD_SEPARATOR = "|"

_KEY = re.compile(r"^[\x21-\x7b\x7d\x7e]+$")  # printable ASCII except '|' (0x7c)
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ReadySetFormatError(ValueError):
    """A READY asset value cannot be represented canonically."""


@dataclass(frozen=True)
class ReadyAsset:
    asset_id: uuid.UUID
    key_original: str
    key_display: str
    key_thumbnail: str
    byte_size: int
    display_byte_size: int
    thumbnail_byte_size: int
    sha256: str


@dataclass(frozen=True)
class ReadySetDigest:
    ready_count: int
    ready_set_sha256: str


def _key(value: object, field: str) -> str:
    if not isinstance(value, str) or not _KEY.match(value):
        raise ReadySetFormatError(f"{field} is not a canonical object key")
    return value


def _size(value: object, field: str) -> str:
    if type(value) is not int or value <= 0:  # bool is rejected: type(True) is bool
        raise ReadySetFormatError(f"{field} must be a positive integer")
    return str(value)


def canonical_line(asset: ReadyAsset) -> bytes:
    if not isinstance(asset.asset_id, uuid.UUID):
        raise ReadySetFormatError("asset_id must be a uuid.UUID")
    if not isinstance(asset.sha256, str) or not _SHA256.match(asset.sha256):
        raise ReadySetFormatError("sha256 must be 64 lowercase hexadecimal characters")
    fields = [
        str(asset.asset_id),
        _key(asset.key_original, "key_original"),
        _key(asset.key_display, "key_display"),
        _key(asset.key_thumbnail, "key_thumbnail"),
        _size(asset.byte_size, "byte_size"),
        _size(asset.display_byte_size, "display_byte_size"),
        _size(asset.thumbnail_byte_size, "thumbnail_byte_size"),
        asset.sha256,
    ]
    return (FIELD_SEPARATOR.join(fields) + "\n").encode("ascii")


def canonical_bytes(assets: Iterable[ReadyAsset]) -> bytes:
    lines: list[bytes] = []
    seen: set[uuid.UUID] = set()
    for asset in assets:
        if asset.asset_id in seen:
            raise ReadySetFormatError("duplicate asset_id in READY set")
        seen.add(asset.asset_id)
        lines.append(canonical_line(asset))
    return READY_SET_HEADER + b"".join(sorted(lines))


def ready_set_digest(assets: Iterable[ReadyAsset]) -> ReadySetDigest:
    materialized = list(assets)
    payload = canonical_bytes(materialized)
    return ReadySetDigest(ready_count=len(materialized), ready_set_sha256=hashlib.sha256(payload).hexdigest())
