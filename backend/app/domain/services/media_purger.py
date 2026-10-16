"""The narrow port that removes stored photo objects (archive cleanup AC-2).

It is **separate from `MediaStorage` on purpose**: the storage port has no delete (Stage 14 decision D14-14, guarded by a test), so nothing
that uploads, reads or backs up can delete by accident. Only the purge service receives a `MediaPurger`.

Contract: `delete_objects(keys)` removes the named objects; a key that is already gone is a success (a retry after a half-done purge must
not fail); any other failure raises a `MediaStorage*` error and nothing is claimed as deleted.
"""
from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from app.domain.exceptions import MediaStorageDisabled
from app.domain.services.media_storage import InMemoryMediaStorage, validate_object_key


@runtime_checkable
class MediaPurger(Protocol):
    async def delete_objects(self, keys: Sequence[str]) -> None: ...


class DisabledMediaPurger:
    """Used while the media storage is not configured: nothing can be deleted."""

    async def delete_objects(self, keys: Sequence[str]) -> None:
        raise MediaStorageDisabled("media storage is not configured")


class InMemoryMediaPurger:
    """Test double over an `InMemoryMediaStorage` (or a wrapper that has `.inner`); records what it was asked to delete."""

    def __init__(self, storage: object) -> None:
        self._store: InMemoryMediaStorage = getattr(storage, "inner", storage)  # type: ignore[assignment]
        self.deleted: list[str] = []
        self.fault: Exception | None = None  # raised once by the next call, for failure tests

    async def delete_objects(self, keys: Sequence[str]) -> None:
        for key in keys:
            validate_object_key(key)
        if self.fault is not None:
            fault, self.fault = self.fault, None
            raise fault
        for key in keys:
            self._store._objects.pop(key, None)
            self.deleted.append(key)
