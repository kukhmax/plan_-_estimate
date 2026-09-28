"""Stage 14B.3 — MediaStorage port: disabled, in-memory and S3 (Stubber, no network)."""

import hashlib
import io
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import boto3
import pytest
from botocore.config import Config
from botocore.exceptions import EndpointConnectionError, NoCredentialsError, ReadTimeoutError
from botocore.response import StreamingBody
from botocore.stub import ANY, Stubber

from app.core.s3_media_storage import S3MediaStorage, map_storage_error
from app.domain.exceptions import (
    MediaObjectConflict,
    MediaObjectNotFound,
    MediaStorageDisabled,
    MediaStorageMisconfigured,
    MediaStorageUnavailable,
)
from app.domain.services.media_storage import (
    DisabledMediaStorage,
    InMemoryMediaStorage,
    MediaStorage,
    MediaStorageAdmin,
    ObjectInfo,
)

KEY = "photos/v1/3f2b8c1e-9d4a-4f6b-8e2a-1c5d7e9f0a1b/original.jpg"
BUCKET = "test-bucket"
ENDPOINT = "https://example-account.eu.r2.cloudflarestorage.com"
FAKE_KEY_ID = "FAKEKEYIDEXAMPLE"
FAKE_SECRET = "fake-secret-never-in-output"


@pytest.fixture
def source(tmp_path: Path) -> Path:
    p = tmp_path / "src.bin"
    p.write_bytes(b"original-bytes-\x00\xff" * 100)
    return p


def make_s3(conditional_put: bool = True):
    client = boto3.client(
        "s3",
        endpoint_url=ENDPOINT,
        region_name="auto",
        aws_access_key_id=FAKE_KEY_ID,
        aws_secret_access_key=FAKE_SECRET,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )
    storage = S3MediaStorage(
        endpoint_url=ENDPOINT,
        bucket=BUCKET,
        region="auto",
        access_key_id=FAKE_KEY_ID,
        secret_access_key=FAKE_SECRET,
        conditional_put=conditional_put,
        client=client,
    )
    return storage, Stubber(client)


# --------------------------------------------------------------------------
# Protocol conformance
# --------------------------------------------------------------------------


def test_implementations_satisfy_the_port():
    storage, _ = make_s3()
    for impl in (DisabledMediaStorage(), InMemoryMediaStorage(), storage):
        assert isinstance(impl, MediaStorage)
        assert isinstance(impl, MediaStorageAdmin)
        assert not hasattr(impl, "delete_object")
        assert not hasattr(impl, "delete")


# --------------------------------------------------------------------------
# Disabled
# --------------------------------------------------------------------------


async def test_disabled_storage_refuses_every_operation(source, tmp_path):
    storage = DisabledMediaStorage()
    with pytest.raises(MediaStorageDisabled):
        await storage.put_object(KEY, source, "image/jpeg")
    with pytest.raises(MediaStorageDisabled):
        await storage.head_object(KEY)
    with pytest.raises(MediaStorageDisabled):
        await storage.presign_get(KEY, 300)
    with pytest.raises(MediaStorageDisabled):
        await storage.download_to(KEY, tmp_path / "out")
    with pytest.raises(MediaStorageDisabled):
        async for _ in storage.iter_keys("photos/"):
            pass


# --------------------------------------------------------------------------
# In-memory
# --------------------------------------------------------------------------


async def test_in_memory_put_head_download_presign_iterate(source, tmp_path):
    storage = InMemoryMediaStorage()
    assert await storage.head_object(KEY) is None
    await storage.put_object(KEY, source, "image/jpeg")
    info = await storage.head_object(KEY)
    assert info == ObjectInfo(size=source.stat().st_size, etag=hashlib.md5(source.read_bytes()).hexdigest())
    out = tmp_path / "out.bin"
    await storage.download_to(KEY, out)
    assert out.read_bytes() == source.read_bytes()
    assert storage.get_content_type(KEY) == "image/jpeg"
    url = await storage.presign_get(KEY, 300)
    assert "expires=300" in url
    other = "photos/v1/other/thumb.jpg"
    await storage.put_object(other, source, "image/jpeg")
    await storage.put_object("unrelated/x", source, "image/jpeg")
    assert [k async for k in storage.iter_keys("photos/")] == sorted([KEY, other])


async def test_in_memory_write_once(source, tmp_path):
    storage = InMemoryMediaStorage()
    await storage.put_object(KEY, source, "image/jpeg")
    await storage.put_object(KEY, source, "image/jpeg")  # identical retry: ok
    different = tmp_path / "different.bin"
    different.write_bytes(b"other")
    with pytest.raises(MediaObjectConflict):
        await storage.put_object(KEY, different, "image/jpeg")
    assert storage.get_bytes(KEY) == source.read_bytes()


async def test_in_memory_not_found_and_bad_input(tmp_path):
    storage = InMemoryMediaStorage()
    with pytest.raises(MediaObjectNotFound):
        await storage.download_to(KEY, tmp_path / "out")
    for bad in ("", "/abs", "a/../b", "a//b", "a\\b", "./a"):
        with pytest.raises(ValueError):
            await storage.head_object(bad)
    for ttl in (0, -1, 7 * 24 * 3600 + 1):
        with pytest.raises(ValueError):
            await storage.presign_get(KEY, ttl)


# --------------------------------------------------------------------------
# S3 adapter (botocore Stubber — no network)
# --------------------------------------------------------------------------


async def test_s3_put_sends_conditional_write_once_request(source):
    storage, stub = make_s3()
    stub.add_response(
        "put_object",
        {"ETag": '"abc"'},
        {
            "Bucket": BUCKET,
            "Key": KEY,
            "Body": ANY,
            "ContentType": "image/jpeg",
            "ContentLength": source.stat().st_size,
            "IfNoneMatch": "*",
        },
    )
    with stub:
        await storage.put_object(KEY, source, "image/jpeg")
    stub.assert_no_pending_responses()


async def test_s3_put_without_conditional_guard(source):
    storage, stub = make_s3(conditional_put=False)
    stub.add_response(
        "put_object",
        {},
        {"Bucket": BUCKET, "Key": KEY, "Body": ANY, "ContentType": "image/png", "ContentLength": ANY},
    )
    with stub:
        await storage.put_object(KEY, source, "image/png")
    stub.assert_no_pending_responses()


async def test_s3_put_412_with_identical_object_is_idempotent_success(source):
    storage, stub = make_s3()
    md5 = hashlib.md5(source.read_bytes()).hexdigest()
    stub.add_client_error("put_object", service_error_code="PreconditionFailed", http_status_code=412)
    stub.add_response("head_object", {"ContentLength": source.stat().st_size, "ETag": f'"{md5}"'}, {"Bucket": BUCKET, "Key": KEY})
    with stub:
        await storage.put_object(KEY, source, "image/jpeg")
    stub.assert_no_pending_responses()


@pytest.mark.parametrize(
    "head",
    [
        {"ContentLength": 1, "ETag": '"0123456789abcdef0123456789abcdef"'},  # size differs
        {"ContentLength": 1700, "ETag": '"0123456789abcdef0123456789abcdef"'},  # same size, other md5
    ],
)
async def test_s3_put_412_with_different_object_is_conflict(source, head):
    assert source.stat().st_size == 1700
    storage, stub = make_s3()
    stub.add_client_error("put_object", service_error_code="PreconditionFailed", http_status_code=412)
    stub.add_response("head_object", head, {"Bucket": BUCKET, "Key": KEY})
    with stub, pytest.raises(MediaObjectConflict):
        await storage.put_object(KEY, source, "image/jpeg")


async def test_s3_head_found_and_missing():
    storage, stub = make_s3()
    stub.add_response("head_object", {"ContentLength": 42, "ETag": '"e1"'}, {"Bucket": BUCKET, "Key": KEY})
    stub.add_client_error("head_object", service_error_code="404", http_status_code=404)
    with stub:
        assert await storage.head_object(KEY) == ObjectInfo(size=42, etag="e1")
        assert await storage.head_object(KEY) is None


async def test_s3_download_to_file_and_missing(tmp_path):
    storage, stub = make_s3()
    data = b"\x89PNG-bytes" * 5000
    stub.add_response(
        "get_object",
        {"Body": StreamingBody(io.BytesIO(data), len(data)), "ContentLength": len(data)},
        {"Bucket": BUCKET, "Key": KEY},
    )
    stub.add_client_error("get_object", service_error_code="NoSuchKey", http_status_code=404)
    out = tmp_path / "dl.bin"
    with stub:
        await storage.download_to(KEY, out)
        assert out.read_bytes() == data
        missing = tmp_path / "missing.bin"
        with pytest.raises(MediaObjectNotFound):
            await storage.download_to(KEY, missing)
        assert not missing.exists()


async def test_s3_download_removes_partial_file_on_stream_error(tmp_path, monkeypatch):
    storage, stub = make_s3()

    class BrokenBody:
        def iter_chunks(self, size):
            yield b"partial"
            raise ReadTimeoutError(endpoint_url=ENDPOINT)

        def close(self):
            pass

    stub.add_response("get_object", {"ContentLength": 10}, {"Bucket": BUCKET, "Key": KEY})
    client = storage._get_client()
    original = client.get_object

    def get_object(**kw):
        response = original(**kw)
        response["Body"] = BrokenBody()
        return response

    monkeypatch.setattr(client, "get_object", get_object)
    out = tmp_path / "partial.bin"
    with stub, pytest.raises(MediaStorageUnavailable):
        await storage.download_to(KEY, out)
    assert not out.exists()


async def test_s3_presign_is_offline_short_lived_and_private():
    storage, stub = make_s3()
    with stub:  # no stubbed responses: presigning must not call the API
        url = await storage.presign_get(KEY, 300)
    stub.assert_no_pending_responses()
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "example-account.eu.r2.cloudflarestorage.com"
    assert parsed.path == f"/{BUCKET}/{KEY}"
    assert query["X-Amz-Expires"] == ["300"]
    assert query["X-Amz-Algorithm"] == ["AWS4-HMAC-SHA256"]
    assert "X-Amz-Signature" in query
    assert FAKE_SECRET not in url
    with pytest.raises(ValueError):
        await storage.presign_get(KEY, 0)


async def test_s3_iter_keys_paginates():
    storage, stub = make_s3()
    stub.add_response(
        "list_objects_v2",
        {"Contents": [{"Key": "photos/v1/a/original.jpg"}], "IsTruncated": True, "NextContinuationToken": "t1"},
        {"Bucket": BUCKET, "Prefix": "photos/"},
    )
    stub.add_response(
        "list_objects_v2",
        {"Contents": [{"Key": "photos/v1/b/thumb.jpg"}], "IsTruncated": False},
        {"Bucket": BUCKET, "Prefix": "photos/", "ContinuationToken": "t1"},
    )
    with stub:
        keys = [k async for k in storage.iter_keys("photos/")]
    assert keys == ["photos/v1/a/original.jpg", "photos/v1/b/thumb.jpg"]


@pytest.mark.parametrize(
    "code, status, expected",
    [
        ("AccessDenied", 403, MediaStorageMisconfigured),
        ("InvalidAccessKeyId", 403, MediaStorageMisconfigured),
        ("SignatureDoesNotMatch", 403, MediaStorageMisconfigured),
        ("NoSuchBucket", 404, MediaStorageMisconfigured),
        ("Unauthorized", 401, MediaStorageMisconfigured),
        ("InternalError", 500, MediaStorageUnavailable),
        ("ServiceUnavailable", 503, MediaStorageUnavailable),
        ("SlowDown", 503, MediaStorageUnavailable),
        ("TooManyRequests", 429, MediaStorageUnavailable),
        ("InvalidRequest", 400, MediaStorageMisconfigured),
    ],
)
async def test_s3_provider_errors_are_mapped(code, status, expected):
    storage, stub = make_s3()
    stub.add_client_error("head_object", service_error_code=code, http_status_code=status)
    with stub, pytest.raises(expected) as exc_info:
        await storage.head_object(KEY)
    err = exc_info.value
    assert err.error_code == code and err.http_status == status
    assert err.__cause__ is None and err.__suppress_context__ is True
    assert FAKE_SECRET not in repr(err) and FAKE_KEY_ID not in str(err)


async def test_s3_put_error_mapped(source):
    storage, stub = make_s3()
    stub.add_client_error("put_object", service_error_code="AccessDenied", http_status_code=403)
    with stub, pytest.raises(MediaStorageMisconfigured):
        await storage.put_object(KEY, source, "image/jpeg")


def test_transport_errors_are_mapped():
    assert isinstance(map_storage_error(EndpointConnectionError(endpoint_url=ENDPOINT)), MediaStorageUnavailable)
    assert isinstance(map_storage_error(ReadTimeoutError(endpoint_url=ENDPOINT)), MediaStorageUnavailable)
    assert isinstance(map_storage_error(NoCredentialsError()), MediaStorageMisconfigured)
    with pytest.raises(TypeError):
        map_storage_error(RuntimeError("not a provider error"))


async def test_s3_connection_error_does_not_escape(monkeypatch):
    storage, _ = make_s3()

    def boom(**kw):
        raise EndpointConnectionError(endpoint_url=ENDPOINT)

    monkeypatch.setattr(storage._get_client(), "head_object", boom)
    with pytest.raises(MediaStorageUnavailable):
        await storage.head_object(KEY)


async def test_s3_blocking_calls_run_off_the_event_loop_thread(monkeypatch):
    storage, _ = make_s3()
    seen = []

    def head_object(**kw):
        seen.append(threading.get_ident())
        return {"ContentLength": 1}

    monkeypatch.setattr(storage._get_client(), "head_object", head_object)
    await storage.head_object(KEY)
    assert seen and seen[0] != threading.get_ident()


def test_s3_repr_hides_credentials():
    storage, _ = make_s3()
    assert FAKE_SECRET not in repr(storage)
    assert FAKE_KEY_ID not in repr(storage)


async def test_s3_client_is_created_lazily_without_network():
    storage = S3MediaStorage(
        endpoint_url=ENDPOINT,
        bucket=BUCKET,
        region="auto",
        access_key_id=FAKE_KEY_ID,
        secret_access_key=FAKE_SECRET,
    )
    assert storage._client is None
    url = await storage.presign_get(KEY, 300)  # local signing only
    assert url.startswith(f"{ENDPOINT}/{BUCKET}/")
    assert storage._client is not None
