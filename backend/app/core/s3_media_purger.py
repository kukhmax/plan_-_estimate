"""S3-compatible (Cloudflare R2) adapter of the `MediaPurger` port (archive cleanup AC-2).

It reuses the lazily created client and the bucket of the `S3MediaStorage`, so there is one connection configuration, and adds nothing to
that class: deleting lives only here, in a class only the purge service is given.
"""
import logging
from collections.abc import Sequence
from functools import partial
from typing import Any

import anyio

from app.core.config import Settings
from app.core.s3_media_storage import (
    S3MediaStorage,
    _is_provider_exception,
    map_storage_error,
)
from app.domain.exceptions import MediaStorageError
from app.domain.services.media_storage import validate_object_key

logger = logging.getLogger(__name__)


class S3MediaPurger:
    def __init__(self, storage: S3MediaStorage) -> None:
        self._storage = storage

    @classmethod
    def from_settings(cls, settings: Settings) -> "S3MediaPurger":
        return cls(S3MediaStorage.from_settings(settings))

    async def delete_objects(self, keys: Sequence[str]) -> None:
        for key in keys:
            validate_object_key(key)
        for key in keys:
            try:
                await anyio.to_thread.run_sync(partial(self._delete_sync, key))
            except MediaStorageError:
                raise
            except Exception as exc:
                if not _is_provider_exception(exc):
                    raise
                mapped = map_storage_error(exc)
                logger.warning("media purge failed: %s", type(mapped).__name__)
                raise mapped from None

    def _delete_sync(self, key: str) -> None:
        client: Any = self._storage._get_client()
        # S3 DeleteObject answers 204 also for a key that does not exist: already gone is a success
        client.delete_object(Bucket=self._storage._bucket, Key=key)
