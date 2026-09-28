"""S3-compatible `MediaStorage` adapter (Stage 14B.3; 14B.1 plan §3, §8).

Generic S3 (boto3): Cloudflare R2 is reached only through configuration
(endpoint URL, bucket, region "auto"); nothing here is Cloudflare-specific,
so the same adapter serves any S3-compatible provider (e.g. the Oracle
Object Storage backup target in 14D).

boto3 is synchronous: every call that may touch the network runs in a
worker thread via `anyio.to_thread.run_sync`, so the event loop never
blocks. botocore exceptions are mapped onto the provider-neutral
`MediaStorageError` subclasses and never escape this module; the mapped
errors carry only the provider error code and HTTP status (no credentials,
no signed URLs, no response bodies).

Write-once: correctness rests on fresh UUID keys written once (14A D14-4).
`put_object` additionally sends `If-None-Match: *` (conditional PUT) as a
guard; a 412 means "already stored" and is accepted only when the stored
object matches the local bytes (ETag = MD5 for a single PUT, else size).
Whether R2 honours the conditional header through boto3 is verified in the
manual smoke test, not assumed here; `conditional_put=False` turns the guard
off (plain PUT, idempotent for identical bytes). No head-before-put check is
performed: it would be race-prone and is not a write-once guarantee.
"""

import hashlib
import logging
import re
import threading
from collections.abc import AsyncIterator
from functools import partial
from pathlib import Path
from typing import Any

import anyio
import boto3
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    NoCredentialsError,
    ParamValidationError,
    PartialCredentialsError,
)
from urllib3.exceptions import HTTPError as Urllib3HTTPError

from app.core.config import Settings
from app.domain.exceptions import (
    MediaObjectConflict,
    MediaObjectNotFound,
    MediaStorageError,
    MediaStorageMisconfigured,
    MediaStorageUnavailable,
)
from app.domain.services.media_storage import (
    DisabledMediaStorage,
    MediaStorage,
    ObjectInfo,
    validate_object_key,
    validate_presign_ttl,
)

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT_SECONDS = 5
READ_TIMEOUT_SECONDS = 60
MAX_ATTEMPTS = 3
DOWNLOAD_CHUNK_BYTES = 1024 * 1024
HASH_CHUNK_BYTES = 1024 * 1024

_NOT_FOUND_CODES = {"404", "NoSuchKey", "NotFound"}
_PRECONDITION_CODES = {"412", "PreconditionFailed"}
_MISCONFIGURED_CODES = {
    "NoSuchBucket",
    "AccessDenied",
    "InvalidAccessKeyId",
    "SignatureDoesNotMatch",
    "InvalidBucketName",
    "AuthorizationHeaderMalformed",
    "InvalidToken",
    "ExpiredToken",
    "Unauthorized",
}
_UNAVAILABLE_CODES = {
    "SlowDown",
    "Throttling",
    "ThrottlingException",
    "RequestTimeout",
    "ServiceUnavailable",
    "InternalError",
}
_MD5_ETAG = re.compile(r"^[0-9a-f]{32}$")


def _client_error_facts(exc: ClientError) -> tuple[str, int | None]:
    error = exc.response.get("Error", {}) or {}
    meta = exc.response.get("ResponseMetadata", {}) or {}
    return str(error.get("Code", "")), meta.get("HTTPStatusCode")


def map_storage_error(exc: Exception) -> MediaStorageError:
    """Translate a botocore/urllib3 exception into a provider-neutral error."""
    if isinstance(exc, ClientError):
        code, status = _client_error_facts(exc)
        if code in _MISCONFIGURED_CODES:
            return MediaStorageMisconfigured("media storage rejected the request", error_code=code, http_status=status)
        if code in _NOT_FOUND_CODES or status == 404:
            return MediaObjectNotFound("object not found", error_code=code, http_status=status)
        if code in _UNAVAILABLE_CODES or status in (408, 429) or (status is not None and status >= 500):
            return MediaStorageUnavailable("media storage temporarily unavailable", error_code=code, http_status=status)
        return MediaStorageMisconfigured("media storage rejected the request", error_code=code, http_status=status)
    if isinstance(exc, (NoCredentialsError, PartialCredentialsError, ParamValidationError)):
        return MediaStorageMisconfigured("media storage is misconfigured", error_code=type(exc).__name__)
    if isinstance(exc, (BotoCoreError, Urllib3HTTPError)):
        # Timeouts, connection errors, incomplete reads.
        return MediaStorageUnavailable("media storage temporarily unavailable", error_code=type(exc).__name__)
    raise TypeError("not a storage provider exception") from exc


def _is_provider_exception(exc: BaseException) -> bool:
    return isinstance(exc, (ClientError, BotoCoreError, Urllib3HTTPError))


def _md5_of_file(path: Path) -> str:
    digest = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(partial(fh.read, HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


class S3MediaStorage:
    def __init__(
        self,
        *,
        endpoint_url: str,
        bucket: str,
        region: str,
        access_key_id: str,
        secret_access_key: str,
        conditional_put: bool = True,
        client: Any | None = None,
    ) -> None:
        self._endpoint_url = endpoint_url
        self._bucket = bucket
        self._region = region
        # Credentials are kept private and never logged or included in repr.
        self.__access_key_id = access_key_id
        self.__secret_access_key = secret_access_key
        self._conditional_put = conditional_put
        self._client = client
        self._client_lock = threading.Lock()

    @classmethod
    def from_settings(cls, settings: Settings) -> "S3MediaStorage":
        return cls(
            endpoint_url=settings.MEDIA_S3_ENDPOINT_URL,
            bucket=settings.MEDIA_S3_BUCKET,
            region=settings.MEDIA_S3_REGION,
            access_key_id=settings.MEDIA_S3_ACCESS_KEY_ID.get_secret_value(),
            secret_access_key=settings.MEDIA_S3_SECRET_ACCESS_KEY.get_secret_value(),
        )

    def __repr__(self) -> str:
        return f"S3MediaStorage(endpoint_url={self._endpoint_url!r}, bucket={self._bucket!r})"

    # -- client -----------------------------------------------------------

    def _get_client(self) -> Any:
        """Create the boto3 client lazily (only when storage is used)."""
        if self._client is None:
            with self._client_lock:
                if self._client is None:
                    self._client = boto3.session.Session().client(
                        "s3",
                        endpoint_url=self._endpoint_url,
                        region_name=self._region,
                        aws_access_key_id=self.__access_key_id,
                        aws_secret_access_key=self.__secret_access_key,
                        config=Config(
                            signature_version="s3v4",
                            connect_timeout=CONNECT_TIMEOUT_SECONDS,
                            read_timeout=READ_TIMEOUT_SECONDS,
                            retries={"max_attempts": MAX_ATTEMPTS, "mode": "standard"},
                            request_checksum_calculation="when_required",
                            response_checksum_validation="when_required",
                            s3={"addressing_style": "path"},
                        ),
                    )
        return self._client

    async def _run(self, fn: Any, *args: Any) -> Any:
        try:
            return await anyio.to_thread.run_sync(partial(fn, *args))
        except MediaStorageError:
            raise
        except Exception as exc:
            if not _is_provider_exception(exc):
                raise
            mapped = map_storage_error(exc)
            logger.warning(
                "media storage error: %s (code=%s, status=%s)",
                type(mapped).__name__,
                mapped.error_code,
                mapped.http_status,
            )
            raise mapped from None

    # -- MediaStorage -----------------------------------------------------

    async def put_object(self, key: str, source: Path, content_type: str) -> None:
        validate_object_key(key)
        await self._run(self._put_sync, key, Path(source), content_type)

    async def head_object(self, key: str) -> ObjectInfo | None:
        validate_object_key(key)
        return await self._run(self._head_sync, key)

    async def presign_get(self, key: str, ttl_seconds: int) -> str:
        validate_object_key(key)
        validate_presign_ttl(ttl_seconds)
        return await self._run(self._presign_sync, key, ttl_seconds)

    async def download_to(self, key: str, path: Path) -> None:
        validate_object_key(key)
        await self._run(self._download_sync, key, Path(path))

    async def iter_keys(self, prefix: str) -> AsyncIterator[str]:
        token: str | None = None
        while True:
            page = await self._run(self._list_page_sync, prefix, token)
            for obj in page.get("Contents", []) or []:
                yield obj["Key"]
            if not page.get("IsTruncated"):
                return
            token = page.get("NextContinuationToken")
            if not token:
                return

    # -- blocking implementations (worker thread) --------------------------

    def _put_sync(self, key: str, source: Path, content_type: str) -> None:
        size = source.stat().st_size
        params: dict[str, Any] = {
            "Bucket": self._bucket,
            "Key": key,
            "ContentType": content_type,
            "ContentLength": size,
        }
        if self._conditional_put:
            params["IfNoneMatch"] = "*"
        with open(source, "rb") as body:
            try:
                self._get_client().put_object(Body=body, **params)
                return
            except ClientError as exc:
                code, status = _client_error_facts(exc)
                if not (self._conditional_put and (code in _PRECONDITION_CODES or status == 412)):
                    raise
        # 412: the key already holds an object. Accept only identical content.
        existing = self._head_sync(key)
        if existing is None:
            raise MediaStorageUnavailable("conditional put reported an existing object that is not visible")
        if existing.size != size:
            raise MediaObjectConflict("object key already holds different content")
        if existing.etag and _MD5_ETAG.match(existing.etag) and existing.etag != _md5_of_file(source):
            raise MediaObjectConflict("object key already holds different content")

    def _head_sync(self, key: str) -> ObjectInfo | None:
        try:
            response = self._get_client().head_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            if isinstance(map_storage_error(exc), MediaObjectNotFound):
                return None
            raise
        etag = response.get("ETag")
        return ObjectInfo(
            size=int(response["ContentLength"]),
            etag=etag.strip('"') if isinstance(etag, str) else None,
        )

    def _presign_sync(self, key: str, ttl_seconds: int) -> str:
        return self._get_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=ttl_seconds,
        )

    def _download_sync(self, key: str, path: Path) -> None:
        response = self._get_client().get_object(Bucket=self._bucket, Key=key)
        body = response["Body"]
        try:
            with open(path, "wb") as out:
                for chunk in body.iter_chunks(DOWNLOAD_CHUNK_BYTES):
                    out.write(chunk)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        finally:
            body.close()

    def _list_page_sync(self, prefix: str, token: str | None) -> dict[str, Any]:
        params: dict[str, Any] = {"Bucket": self._bucket, "Prefix": prefix}
        if token:
            params["ContinuationToken"] = token
        return self._get_client().list_objects_v2(**params)


def create_media_storage(settings: Settings) -> MediaStorage:
    """Select the storage implementation once, from configuration."""
    if settings.MEDIA_STORAGE_BACKEND == "s3":
        return S3MediaStorage.from_settings(settings)
    return DisabledMediaStorage()
