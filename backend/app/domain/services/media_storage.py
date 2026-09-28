"""Provider-neutral media storage port (Stage 14B.3; 14B.1 plan §8).

`MediaStorage` is the runtime port (upload, resume, delivery, Stage 15
retrieval). `MediaStorageAdmin` adds key iteration for integrity/backup
tooling only and is not meant to be injected into API code. There is no
delete operation in Stage 14 v1 (14A D14-14).

All methods are async; implementations that do blocking I/O run it off the
event loop. Errors are the provider-neutral `MediaStorageError` subclasses
from `app.domain.exceptions`.
"""

import hashlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable
from urllib.parse import quote

from app.domain.exceptions import (
    MediaObjectConflict,
    MediaObjectNotFound,
    MediaStorageDisabled,
)

# SigV4 presigned URLs cannot exceed 7 days; the application uses
# PHOTO_SIGNED_URL_TTL_SECONDS (60-3600).
MAX_PRESIGN_TTL_SECONDS = 7 * 24 * 3600


@dataclass(frozen=True)
class ObjectInfo:
    size: int
    etag: str | None = None


@runtime_checkable
class MediaStorage(Protocol):
    async def put_object(self, key: str, source: Path, content_type: str) -> None:
        """Store the local file `source` under the write-once `key`.

        Re-putting identical bytes is a no-op success (idempotent retry); a
        different object already at `key` raises MediaObjectConflict.
        """
        ...

    async def head_object(self, key: str) -> ObjectInfo | None:
        """Return object facts, or None when the key does not exist."""
        ...

    async def presign_get(self, key: str, ttl_seconds: int) -> str:
        """Return a short-lived GET URL for `key` (no existence check)."""
        ...

    async def download_to(self, key: str, path: Path) -> None:
        """Write the object to the local file `path` (MediaObjectNotFound if absent)."""
        ...


@runtime_checkable
class MediaStorageAdmin(MediaStorage, Protocol):
    def iter_keys(self, prefix: str) -> AsyncIterator[str]:
        """Yield every key under `prefix` (integrity/backup tooling only)."""
        ...


def validate_object_key(key: str) -> None:
    """Reject keys that could escape the intended namespace."""
    if not key or key.startswith("/") or "\\" in key or "\x00" in key:
        raise ValueError("invalid object key")
    if any(part in ("", ".", "..") for part in key.split("/")):
        raise ValueError("invalid object key")


def validate_presign_ttl(ttl_seconds: int) -> None:
    if not isinstance(ttl_seconds, int) or not 0 < ttl_seconds <= MAX_PRESIGN_TTL_SECONDS:
        raise ValueError("ttl_seconds out of range")


class DisabledMediaStorage:
    """Used when MEDIA_STORAGE_BACKEND=disabled: every call is refused with
    MediaStorageDisabled (a feature-off condition, never a 500)."""

    async def put_object(self, key: str, source: Path, content_type: str) -> None:
        raise MediaStorageDisabled("media storage is disabled")

    async def head_object(self, key: str) -> ObjectInfo | None:
        raise MediaStorageDisabled("media storage is disabled")

    async def presign_get(self, key: str, ttl_seconds: int) -> str:
        raise MediaStorageDisabled("media storage is disabled")

    async def download_to(self, key: str, path: Path) -> None:
        raise MediaStorageDisabled("media storage is disabled")

    async def iter_keys(self, prefix: str) -> AsyncIterator[str]:
        raise MediaStorageDisabled("media storage is disabled")
        yield  # pragma: no cover — makes this an async generator


@dataclass
class _StoredObject:
    data: bytes
    content_type: str


class InMemoryMediaStorage:
    """Test double with the same contract as the S3 adapter. Not for
    production use (objects live in process memory)."""

    def __init__(self) -> None:
        self._objects: dict[str, _StoredObject] = {}

    async def put_object(self, key: str, source: Path, content_type: str) -> None:
        validate_object_key(key)
        data = Path(source).read_bytes()
        existing = self._objects.get(key)
        if existing is not None:
            if existing.data != data:
                raise MediaObjectConflict("object key already holds different content")
            return
        self._objects[key] = _StoredObject(data=data, content_type=content_type)

    async def head_object(self, key: str) -> ObjectInfo | None:
        validate_object_key(key)
        obj = self._objects.get(key)
        if obj is None:
            return None
        return ObjectInfo(size=len(obj.data), etag=hashlib.md5(obj.data).hexdigest())

    async def presign_get(self, key: str, ttl_seconds: int) -> str:
        validate_object_key(key)
        validate_presign_ttl(ttl_seconds)
        return f"memory://media/{quote(key)}?expires={ttl_seconds}"

    async def download_to(self, key: str, path: Path) -> None:
        validate_object_key(key)
        obj = self._objects.get(key)
        if obj is None:
            raise MediaObjectNotFound("object not found")
        Path(path).write_bytes(obj.data)

    async def iter_keys(self, prefix: str) -> AsyncIterator[str]:
        for key in sorted(self._objects):
            if key.startswith(prefix):
                yield key

    # Test helpers ---------------------------------------------------------

    def get_bytes(self, key: str) -> bytes:
        return self._objects[key].data

    def get_content_type(self, key: str) -> str:
        return self._objects[key].content_type
