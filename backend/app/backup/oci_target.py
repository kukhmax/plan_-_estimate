"""Oracle Object Storage backup target (Stage 14D.2F; 14D.3 owner decisions O1 / O3 / O5).

Native OCI API through the official SDK (not the S3 compatibility layer), with the
VM's instance principal -- no key file, no secret on disk. The uploader's IAM
(`plan-estimate-backup-uploader-*-policy`, 14D.3 §6.2) allows `OBJECT_CREATE` plus
read / inspect only, which is exactly what this adapter uses:

    put_new      PutObject with `If-None-Match: *` (+ Content-MD5, Content-Length)
                 -> 200 CREATED; 412 IfNoneMatchFailed -> EXISTS (verified 14D.4.5)
    head         HeadObject; a missing object -> None
    download_to  GetObject streamed into a NEW file (exclusive create, mode 0600)

There is no overwrite (a plain put over an existing name would be refused by IAM),
no delete, no multipart upload (it needs `OBJECT_OVERWRITE`) and no listing here.
A single PutObject carries up to 50 GiB, far above the largest object this tool
writes. The SDK's own retries are disabled: retry policy lives in
`app.backup.target`, in one place, with bounded backoff.

Error mapping (provider exceptions never escape; messages carry no credential,
token, OCID or response body):

    HTTP 408 / 429 / >= 500, transport errors (timeout, connection) -> MediaStorageUnavailable
    HTTP 401 / 403, 404 BucketNotFound / NamespaceNotFound /
      NotAuthorizedOrNotFound (Object Storage masks a missing permission as 404),
      other 4xx                                                       -> MediaStorageMisconfigured
    HTTP 404 on head / get otherwise                                   -> absent / MediaObjectNotFound

`oci` is imported lazily: this module and its tests need no SDK installed.
"""

import asyncio
import base64
import configparser
import hashlib
import logging
import os
import re
import stat
from pathlib import Path
from typing import Any, cast

from app.backup.target import CHUNK_BYTES, PutOutcome, TargetObject
from app.domain.exceptions import (
    MediaObjectNotFound,
    MediaStorageError,
    MediaStorageMisconfigured,
    MediaStorageUnavailable,
)
from app.domain.services.media_storage import validate_object_key

logger = logging.getLogger(__name__)

OCI_SDK_PIN = "oci==2.187.1"
DEFAULT_REGION = "eu-frankfurt-1"
CONNECT_TIMEOUT_SECONDS = 10.0
READ_TIMEOUT_SECONDS = 120.0
_NAMESPACE = re.compile(r"^[A-Za-z0-9]{1,63}$", re.ASCII)
_BUCKET = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$", re.ASCII)
_MASKED_DENIAL_CODES = frozenset({"BucketNotFound", "NamespaceNotFound", "NotAuthorizedOrNotFound", "NotAuthenticated"})
_TRANSIENT_CODES = frozenset({"Throttled", "TooManyRequests", "InternalServerError", "ServiceUnavailable"})
_TRANSPORT_MODULES = frozenset({"requests", "urllib3", "http", "socket", "ssl"})
CONFIG_MAX_BYTES = 64 * 1024


def service_error_facts(exc: BaseException) -> tuple[int, str | None] | None:
    """(HTTP status, code) of an OCI ServiceError (duck-typed). `code` is None for body-less
    responses such as the answer to HEAD."""
    status = getattr(exc, "status", None)
    code = getattr(exc, "code", None)
    if isinstance(status, int) and not isinstance(status, bool) and (code is None or isinstance(code, str)):
        return status, code
    return None


def map_oci_error(exc: Exception) -> MediaStorageError:
    """Translate an OCI SDK / transport exception into a provider-neutral storage error.

    Programming errors are not mapped: the caller re-raises them."""
    facts = service_error_facts(exc)
    if facts is not None:
        status, code = facts
        if status in (408, 429) or status >= 500 or code in _TRANSIENT_CODES:
            return MediaStorageUnavailable("backup target temporarily unavailable", error_code=code, http_status=status)
        if status in (401, 403) or code in _MASKED_DENIAL_CODES:
            return MediaStorageMisconfigured(
                "backup target rejected the request (bucket, namespace or permission)", error_code=code, http_status=status
            )
        if status == 404:
            return MediaObjectNotFound("object not found", error_code=code, http_status=status)
        return MediaStorageMisconfigured("backup target rejected the request", error_code=code, http_status=status)
    module = type(exc).__module__.split(".")[0]
    # Transport failures only. Local I/O errors (FileExistsError, PermissionError, ...) and SDK
    # configuration errors are neither transient nor provider answers: they propagate unchanged.
    transport = (
        isinstance(exc, (ConnectionError, TimeoutError))
        or module in _TRANSPORT_MODULES
        or (module == "oci" and isinstance(exc, OSError))  # oci.exceptions.RequestException family
    )
    if transport:
        return MediaStorageUnavailable("backup target temporarily unavailable", error_code=type(exc).__name__)
    raise TypeError("not a backup target provider exception") from exc


def _md5_base64(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return base64.b64encode(digest.digest()).decode("ascii")


class OciBackupTarget:
    def __init__(self, *, namespace: str, bucket: str, client: Any) -> None:
        if not _NAMESPACE.fullmatch(namespace):
            raise ValueError("invalid Object Storage namespace")
        if not _BUCKET.fullmatch(bucket):
            raise ValueError("invalid bucket name")
        self._namespace = namespace
        self._bucket = bucket
        self._client = client

    def __repr__(self) -> str:  # never exposes the namespace
        return f"OciBackupTarget(bucket={self._bucket!r})"

    @classmethod
    def from_instance_principal(
        cls,
        *,
        namespace: str,
        bucket: str,
        region: str = DEFAULT_REGION,
        connect_timeout: float = CONNECT_TIMEOUT_SECONDS,
        read_timeout: float = READ_TIMEOUT_SECONDS,
    ) -> "OciBackupTarget":
        try:
            import oci  # type: ignore[import-not-found,unused-ignore]
        except ImportError:
            raise MediaStorageMisconfigured(f"the OCI SDK is not installed (pip install {OCI_SDK_PIN})") from None
        try:
            signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
        except Exception as exc:  # noqa: BLE001 - any failure means: no instance principal from here
            raise MediaStorageMisconfigured(
                "no instance principal is available here", error_code=type(exc).__name__
            ) from None
        client = oci.object_storage.ObjectStorageClient(
            {"region": region},
            signer=signer,
            retry_strategy=oci.retry.NoneRetryStrategy(),
            timeout=(connect_timeout, read_timeout),
        )
        return cls(namespace=namespace, bucket=bucket, client=client)

    # -- BackupTarget -------------------------------------------------------------------

    async def put_new(self, key: str, source: Path, content_type: str) -> PutOutcome:
        validate_object_key(key)
        return cast(PutOutcome, await self._run(self._put_sync, key, Path(source), content_type))

    async def head(self, key: str) -> TargetObject | None:
        validate_object_key(key)
        return cast(TargetObject | None, await self._run(self._head_sync, key))

    async def download_to(self, key: str, path: Path) -> None:
        validate_object_key(key)
        await self._run(self._download_sync, key, Path(path))

    # -- internals ----------------------------------------------------------------------

    async def _run(self, fn: Any, *args: Any) -> Any:
        try:
            return await asyncio.to_thread(fn, *args)
        except MediaStorageError:
            raise
        except Exception as exc:  # noqa: BLE001 - provider errors are mapped; anything else is re-raised unchanged
            try:
                mapped = map_oci_error(exc)
            except TypeError:
                raise exc from None
            logger.warning(
                "backup target error: %s (code=%s, status=%s)",
                type(mapped).__name__,
                mapped.error_code,
                mapped.http_status,
            )
            raise mapped from None

    def _put_sync(self, key: str, source: Path, content_type: str) -> PutOutcome:
        size = source.stat().st_size
        if size == 0:
            raise ValueError("refusing to store an empty object")
        md5 = _md5_base64(source)
        with open(source, "rb") as body:
            try:
                self._client.put_object(
                    self._namespace,
                    self._bucket,
                    key,
                    body,
                    content_length=size,
                    content_type=content_type,
                    content_md5=md5,
                    if_none_match="*",
                )
            except Exception as exc:
                facts = service_error_facts(exc)
                if facts is not None and facts[0] == 412:
                    return PutOutcome.EXISTS
                raise
        return PutOutcome.CREATED

    def _head_sync(self, key: str) -> TargetObject | None:
        try:
            response = self._client.head_object(self._namespace, self._bucket, key)
        except Exception as exc:
            facts = service_error_facts(exc)
            if facts is not None and facts[0] == 404 and facts[1] in (None, "ObjectNotFound", "NotFound"):
                return None
            raise
        headers = response.headers
        length = headers.get("content-length")
        if length is None or not str(length).isdigit():
            raise MediaStorageUnavailable("backup target answered HEAD without a valid size")
        return TargetObject(size=int(length), etag=headers.get("etag"))

    def _download_sync(self, key: str, path: Path) -> None:
        try:
            response = self._client.get_object(self._namespace, self._bucket, key)
        except Exception as exc:
            facts = service_error_facts(exc)
            if facts is not None and facts[0] == 404 and facts[1] in (None, "ObjectNotFound", "NotFound"):
                raise MediaObjectNotFound("object not found", error_code=facts[1], http_status=404) from None
            raise
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        written = 0
        try:
            with os.fdopen(fd, "wb") as out:
                for chunk in response.data.raw.stream(CHUNK_BYTES, decode_content=False):
                    out.write(chunk)
                    written += len(chunk)
                out.flush()
                os.fsync(out.fileno())
            expected = response.headers.get("content-length")
            if expected is not None and int(expected) != written:
                raise MediaStorageUnavailable("incomplete download")
        except BaseException:
            path.unlink(missing_ok=True)
            raise


# -- restore principal: read-only client from an API-key config file (Stage 14D.2I.3) ----------------------


def _private_regular_file(path: Path, what: str, *, euid: int | None = None) -> None:
    """Absolute, regular, not a symlink, owned by the effective user, no group / other bits, sane size.
    The error names the rule and the role of the file, never its path or content."""
    expected_uid = os.geteuid() if euid is None else euid
    if not path.is_absolute():
        raise MediaStorageMisconfigured(f"the {what} path must be absolute", error_code="ConfigFileUnsafe")
    try:
        st = os.lstat(path)
    except OSError:
        raise MediaStorageMisconfigured(f"the {what} does not exist or is not accessible", error_code="ConfigFileUnsafe") from None
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        raise MediaStorageMisconfigured(f"the {what} must be a regular file (no symlink)", error_code="ConfigFileUnsafe")
    if st.st_uid != expected_uid:
        raise MediaStorageMisconfigured(f"the {what} is not owned by the effective user", error_code="ConfigFileUnsafe")
    if st.st_mode & 0o077:
        raise MediaStorageMisconfigured(
            f"the {what} has group / other permissions (expected 0600 or 0400)", error_code="ConfigFileUnsafe"
        )
    if st.st_size == 0 or st.st_size > CONFIG_MAX_BYTES:
        raise MediaStorageMisconfigured(f"the {what} is empty or unexpectedly large", error_code="ConfigFileUnsafe")


def validate_api_key_config(config_file: Path, profile: str, *, euid: int | None = None) -> None:
    """The OCI config file and the private key it names must both be private files owned by the effective user."""
    _private_regular_file(config_file, "OCI config file", euid=euid)
    parser = configparser.ConfigParser(interpolation=None)
    try:
        with open(config_file, encoding="utf-8") as handle:
            parser.read_file(handle)
    except (OSError, UnicodeDecodeError, configparser.Error):
        raise MediaStorageMisconfigured("the OCI config file could not be parsed", error_code="ConfigFileUnsafe") from None
    if not parser.has_section(profile) and profile != "DEFAULT":
        raise MediaStorageMisconfigured("the OCI config profile does not exist", error_code="ConfigFileUnsafe")
    key_file = parser.defaults().get("key_file") if profile == "DEFAULT" else parser.get(profile, "key_file", fallback=None)
    if not key_file:
        raise MediaStorageMisconfigured("the OCI config profile names no key_file", error_code="ConfigFileUnsafe")
    _private_regular_file(Path(os.path.expanduser(key_file)), "OCI API signing key", euid=euid)


class OciBackupReader:
    """The read side of the backup bucket for the restore principal (IAM: read / inspect only).

    Exposes `head` and `download_to` and nothing else -- there is no write verb to call, not even one that IAM
    would refuse. Authentication is the operator's API signing key from a local OCI config file (the private key
    stays on the operator's workstation, never on the production VM); the instance principal is available for
    verification on the VM."""

    def __init__(self, target: OciBackupTarget) -> None:
        self._target = target

    def __repr__(self) -> str:
        return f"OciBackupReader({self._target!r})"

    @classmethod
    def from_api_key_config(
        cls,
        *,
        namespace: str,
        bucket: str,
        config_file: Path,
        profile: str = "DEFAULT",
        region: str | None = None,
        connect_timeout: float = CONNECT_TIMEOUT_SECONDS,
        read_timeout: float = READ_TIMEOUT_SECONDS,
    ) -> "OciBackupReader":
        try:
            import oci  # type: ignore[import-not-found,unused-ignore]
        except ImportError:
            raise MediaStorageMisconfigured(f"the OCI SDK is not installed (pip install {OCI_SDK_PIN})") from None
        validate_api_key_config(config_file, profile)
        try:
            config = oci.config.from_file(file_location=str(config_file), profile_name=profile)
            if region is not None:
                config["region"] = region
            oci.config.validate_config(config)
        except Exception as exc:  # noqa: BLE001 - the SDK's messages can quote the config; only the type is kept
            raise MediaStorageMisconfigured("the OCI config is not usable", error_code=type(exc).__name__) from None
        client = oci.object_storage.ObjectStorageClient(
            config,
            retry_strategy=oci.retry.NoneRetryStrategy(),
            timeout=(connect_timeout, read_timeout),
        )
        return cls(OciBackupTarget(namespace=namespace, bucket=bucket, client=client))

    @classmethod
    def from_instance_principal(
        cls, *, namespace: str, bucket: str, region: str = DEFAULT_REGION
    ) -> "OciBackupReader":
        return cls(OciBackupTarget.from_instance_principal(namespace=namespace, bucket=bucket, region=region))

    async def head(self, key: str) -> TargetObject | None:
        return await self._target.head(key)

    async def download_to(self, key: str, path: Path) -> None:
        await self._target.download_to(key, path)
