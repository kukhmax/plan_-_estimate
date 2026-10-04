"""Stage 14D.2I.3 — the OCI clients over the REAL oci SDK with a stubbed transport (skipped without the SDK)."""

import hashlib
import io
import json
import os
import stat
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from app.backup import oci_target as ot
from app.backup import target as tg
from app.domain.exceptions import (
    MediaObjectNotFound,
    MediaStorageMisconfigured,
    MediaStorageUnavailable,
)
from tests.test_stage14d2i3_oci_reader import (
    BUCKET,
    FINGERPRINT,
    NAMESPACE,
    TENANCY,
    USER,
    write_private,
)

# --- the real SDK with a stubbed transport --------------------------------------------------------------------------------

oci = pytest.importorskip("oci")  # the SDK is a development / operator dependency, not a production pin
requests = pytest.importorskip("requests")
urllib3_response = pytest.importorskip("urllib3.response")


@pytest.fixture
def signing_key(tmp_path: Path) -> Path:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    ).decode()
    return write_private(tmp_path / "key.pem", pem)


class Stub:
    """A requests transport adapter that answers from a handler and records every request."""

    def __init__(self, handler: Callable[[Any], tuple[int, dict[str, str], bytes]]) -> None:
        self.handler = handler
        self.requests: list[Any] = []

    def mount_on(self, client: Any) -> None:
        stub = self

        class Adapter(requests.adapters.BaseAdapter):  # type: ignore[name-defined,misc]
            def send(self, request: Any, **kwargs: Any) -> Any:
                stub.requests.append(request)
                status, headers, body = stub.handler(request)
                response = requests.Response()
                response.status_code = status
                response.headers = requests.structures.CaseInsensitiveDict(headers)
                response.request = request
                response.url = request.url
                response.raw = urllib3_response.HTTPResponse(
                    body=io.BytesIO(body),
                    preload_content=False,
                    status=status,
                    headers=headers,
                    request_method=request.method,
                    enforce_content_length=False,
                )
                return response

            def close(self) -> None:
                pass

        client.base_client.session.mount("https://", Adapter())

    def methods(self) -> list[str]:
        return [request.method for request in self.requests]


def oci_config(tmp_path: Path, signing_key: Path, **overrides: str) -> Path:
    fields = {
        "user": USER, "fingerprint": FINGERPRINT, "tenancy": TENANCY, "region": "eu-frankfurt-1", "key_file": str(signing_key),
        **overrides,
    }  # fmt: skip
    body = "\n".join(f"{name}={value}" for name, value in fields.items())
    return write_private(tmp_path / "oci-config", f"[DEFAULT]\n{body}\n")


def reader_for(tmp_path: Path, signing_key: Path, stub: Stub, **kwargs: Any) -> ot.OciBackupReader:
    config = oci_config(tmp_path, signing_key)
    reader = ot.OciBackupReader.from_api_key_config(namespace=NAMESPACE, bucket=BUCKET, config_file=config, **kwargs)
    stub.mount_on(reader._target._client)
    return reader


def error_body(code: str) -> bytes:
    return json.dumps({"code": code, "message": "provider text that must never be surfaced"}).encode()


async def test_head_goes_out_signed_to_the_object_endpoint(tmp_path: Path, signing_key: Path):
    stub = Stub(lambda request: (200, {"content-length": "321", "etag": '"abc"'}, b""))
    reader = reader_for(tmp_path, signing_key, stub)
    facts = await reader.head("photos/v1/x/original.jpg")
    assert facts == tg.TargetObject(size=321, etag='"abc"')
    (request,) = stub.requests
    assert request.method == "HEAD"
    assert request.url == f"https://objectstorage.eu-frankfurt-1.oraclecloud.com/n/{NAMESPACE}/b/{BUCKET}/o/photos%2Fv1%2Fx%2Foriginal.jpg"  # the SDK encodes '/' inside object names
    authorization = request.headers["authorization"]
    assert authorization.startswith("Signature ") and f"keyId=\"{TENANCY}/{USER}/{FINGERPRINT}\"" in authorization
    assert "signature=" in authorization


async def test_the_region_can_be_overridden(tmp_path: Path, signing_key: Path):
    stub = Stub(lambda request: (200, {"content-length": "1"}, b""))
    reader = reader_for(tmp_path, signing_key, stub, region="eu-amsterdam-1")
    await reader.head("a/b.bin")
    assert stub.requests[0].url.startswith("https://objectstorage.eu-amsterdam-1.oraclecloud.com/")


async def test_a_missing_object_is_none(tmp_path: Path, signing_key: Path):
    stub = Stub(lambda request: (404, {}, b""))
    assert await reader_for(tmp_path, signing_key, stub).head("photos/v1/x/original.jpg") is None


async def test_download_streams_into_a_new_private_file(tmp_path: Path, signing_key: Path):
    payload = os.urandom(3 * 1024 * 1024 + 17)
    stub = Stub(lambda request: (200, {"content-length": str(len(payload))}, payload))
    reader = reader_for(tmp_path, signing_key, stub)
    target = tmp_path / "downloaded"
    await reader.download_to("photos/v1/x/original.jpg", target)
    assert hashlib.sha256(target.read_bytes()).hexdigest() == hashlib.sha256(payload).hexdigest()
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert stub.methods() == ["GET"]


async def test_download_never_overwrites_and_cleans_up_a_short_body(tmp_path: Path, signing_key: Path):
    stub = Stub(lambda request: (200, {"content-length": "100"}, b"short"))
    reader = reader_for(tmp_path, signing_key, stub)
    target = tmp_path / "short"
    with pytest.raises(MediaStorageUnavailable):
        await reader.download_to("photos/v1/x/original.jpg", target)
    assert not target.exists(), "an incomplete download leaves no file"
    existing = write_private(tmp_path / "existing", "keep")
    with pytest.raises(FileExistsError):
        await reader.download_to("photos/v1/x/original.jpg", existing)
    assert existing.read_text() == "keep"


async def test_a_missing_object_on_download_is_reported(tmp_path: Path, signing_key: Path):
    stub = Stub(lambda request: (404, {}, error_body("ObjectNotFound")))
    with pytest.raises(MediaObjectNotFound):
        await reader_for(tmp_path, signing_key, stub).download_to("photos/v1/x/original.jpg", tmp_path / "gone")


@pytest.mark.parametrize("status", [429, 500, 503])
async def test_transient_provider_errors_are_unavailable_and_are_not_retried_by_the_sdk(tmp_path: Path, signing_key: Path, status: int):
    stub = Stub(lambda request: (status, {}, error_body("ServiceUnavailable")))
    reader = reader_for(tmp_path, signing_key, stub)
    with pytest.raises(MediaStorageUnavailable) as excinfo:
        await reader.download_to("photos/v1/x/original.jpg", tmp_path / "x")
    assert len(stub.requests) == 1, "retries live in one place (app.backup.target)"
    assert "provider text" not in str(excinfo.value)


@pytest.mark.parametrize("status, code", [(401, "NotAuthenticated"), (403, "NotAuthorizedOrNotFound"), (404, "BucketNotFound")])
async def test_authorization_and_masked_denials_are_a_misconfiguration(tmp_path: Path, signing_key: Path, status: int, code: str):
    stub = Stub(lambda request: (status, {}, error_body(code)))
    reader = reader_for(tmp_path, signing_key, stub)
    with pytest.raises(MediaStorageMisconfigured) as excinfo:
        await reader.download_to("photos/v1/x/original.jpg", tmp_path / "x")
    assert "provider text" not in str(excinfo.value) and NAMESPACE not in str(excinfo.value)


async def test_the_reader_only_ever_sends_head_and_get(tmp_path: Path, signing_key: Path):
    stub = Stub(lambda request: (200, {"content-length": "3"}, b"abc") if request.method == "GET" else (200, {"content-length": "3"}, b""))
    reader = reader_for(tmp_path, signing_key, stub)
    await reader.head("a/b.bin")
    await reader.download_to("a/b.bin", tmp_path / "out")
    assert set(stub.methods()) == {"HEAD", "GET"}


async def test_an_unusable_config_is_reported_without_quoting_it(tmp_path: Path, signing_key: Path):
    config = oci_config(tmp_path, signing_key, fingerprint="not-a-fingerprint")
    with pytest.raises(MediaStorageMisconfigured) as excinfo:
        ot.OciBackupReader.from_api_key_config(namespace=NAMESPACE, bucket=BUCKET, config_file=config)
    assert "not-a-fingerprint" not in str(excinfo.value) and excinfo.value.error_code is not None


def test_the_sdks_own_messages_are_never_surfaced(tmp_path: Path, signing_key: Path, monkeypatch: pytest.MonkeyPatch):
    """The SDK may quote the config it rejects; only the exception type is kept."""

    def reject(config: Any, **kwargs: Any) -> None:
        raise ValueError(f"bad config for {config['user']} with fingerprint {config['fingerprint']}")

    monkeypatch.setattr(oci.config, "validate_config", reject)
    with pytest.raises(MediaStorageMisconfigured) as excinfo:
        ot.OciBackupReader.from_api_key_config(namespace=NAMESPACE, bucket=BUCKET, config_file=oci_config(tmp_path, signing_key))
    assert USER not in str(excinfo.value) and FINGERPRINT not in str(excinfo.value)
    assert excinfo.value.error_code == "ValueError"


def test_invalid_namespace_or_bucket_is_refused(tmp_path: Path, signing_key: Path):
    config = oci_config(tmp_path, signing_key)
    with pytest.raises(ValueError):
        ot.OciBackupReader.from_api_key_config(namespace="bad namespace!", bucket=BUCKET, config_file=config)
    with pytest.raises(ValueError):
        ot.OciBackupReader.from_api_key_config(namespace=NAMESPACE, bucket="Bad_Bucket", config_file=config)


# --- the writer (14D.2F) over the same real SDK ------------------------------------------------------------------------------------


async def test_the_writer_sends_a_conditional_put_with_checksum_and_length(tmp_path: Path, signing_key: Path):
    stub = Stub(lambda request: (200, {"etag": '"e"'}, b""))
    reader = reader_for(tmp_path, signing_key, stub)
    writer = ot.OciBackupTarget(namespace=NAMESPACE, bucket=BUCKET, client=reader._target._client)
    source = write_private(tmp_path / "payload", "x" * 1000)
    assert await writer.put_new("smoke/x/object.bin", source, "application/octet-stream") is tg.PutOutcome.CREATED
    (request,) = stub.requests
    assert request.method == "PUT"
    assert request.headers["if-none-match"] == "*" and request.headers["content-length"] == "1000"
    assert request.headers["content-md5"] and request.headers["content-type"] == "application/octet-stream"
    assert request.headers["authorization"].startswith("Signature ")


async def test_the_writer_maps_a_412_to_exists_over_the_real_sdk(tmp_path: Path, signing_key: Path):
    stub = Stub(lambda request: (412, {}, error_body("IfNoneMatchFailed")))
    reader = reader_for(tmp_path, signing_key, stub)
    writer = ot.OciBackupTarget(namespace=NAMESPACE, bucket=BUCKET, client=reader._target._client)
    source = write_private(tmp_path / "payload", "y" * 10)
    assert await writer.put_new("smoke/x/object.bin", source, "application/octet-stream") is tg.PutOutcome.EXISTS
    assert len(stub.requests) == 1
