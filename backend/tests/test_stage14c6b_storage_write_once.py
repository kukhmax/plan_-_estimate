"""Stage 14C.6B — S3 write-once adapter under ambiguous / partial outcomes
(Stage 14B contract, unchanged). botocore Stubber only; no live R2.

Already covered in test_stage14b_media_storage.py (not duplicated here):
412 + identical object -> success; 412 + size mismatch -> conflict;
412 + same size, different MD5 ETag -> conflict.

Here:
A. The ambiguous PUT: botocore's own retry of a PUT whose first attempt timed
   out but actually stored the object surfaces to the adapter as a single
   412 PreconditionFailed (the adapter calls put_object once; retries happen
   inside botocore and cannot be injected through the Stubber). The adapter
   must HEAD and accept the matching object idempotently.
B/C. Mismatching size / MD5 after the ambiguous retry -> MediaObjectConflict.
D. A non-MD5 (multipart-style "<hex>-<n>") ETag: only the size can be
   compared, so a same-size object is accepted (accepted 14B behaviour, C9 in
   the 14C contract: size is not content identity).
E. A 412 whose HEAD finds nothing -> MediaStorageUnavailable (retryable).
F. Exhausted transport retries -> MediaStorageUnavailable, never a raw
   botocore exception.
"""

import hashlib

import pytest
from botocore.exceptions import ReadTimeoutError

from app.domain.exceptions import MediaObjectConflict, MediaStorageUnavailable
from tests.test_stage14b_media_storage import BUCKET, KEY, make_s3


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "derivative.jpg"
    path.write_bytes(bytes(range(256)) * 8)  # 2048 bytes
    return path


def precondition_failed(stub) -> None:
    stub.add_client_error("put_object", service_error_code="PreconditionFailed", http_status_code=412)


def head(stub, size: int, etag: str | None) -> None:
    response: dict = {"ContentLength": size}
    if etag is not None:
        response["ETag"] = f'"{etag}"'
    stub.add_response("head_object", response, {"Bucket": BUCKET, "Key": KEY})


async def test_a_ambiguous_put_then_412_with_matching_object_is_idempotent(source):
    storage, stub = make_s3()
    md5 = hashlib.md5(source.read_bytes()).hexdigest()
    precondition_failed(stub)
    head(stub, source.stat().st_size, md5)
    with stub:
        await storage.put_object(KEY, source, "image/jpeg")
    stub.assert_no_pending_responses()


async def test_b_ambiguous_put_then_412_with_wrong_size_is_conflict(source):
    storage, stub = make_s3()
    precondition_failed(stub)
    head(stub, source.stat().st_size - 1, hashlib.md5(source.read_bytes()).hexdigest())
    with stub, pytest.raises(MediaObjectConflict):
        await storage.put_object(KEY, source, "image/jpeg")


async def test_c_ambiguous_put_then_412_with_same_size_other_md5_is_conflict(source):
    storage, stub = make_s3()
    precondition_failed(stub)
    head(stub, source.stat().st_size, "0" * 32)
    with stub, pytest.raises(MediaObjectConflict):
        await storage.put_object(KEY, source, "image/jpeg")


@pytest.mark.parametrize("etag", ["9b2cf535f27731c974343645a3985328-3", None], ids=["multipart-etag", "no-etag"])
async def test_d_non_md5_etag_falls_back_to_size_only(source, etag):
    storage, stub = make_s3()
    precondition_failed(stub)
    head(stub, source.stat().st_size, etag)
    with stub:
        await storage.put_object(KEY, source, "image/jpeg")  # accepted: size matches, ETag not an MD5
    storage2, stub2 = make_s3()
    precondition_failed(stub2)
    head(stub2, source.stat().st_size + 5, etag)
    with stub2, pytest.raises(MediaObjectConflict):  # size still guards
        await storage2.put_object(KEY, source, "image/jpeg")


async def test_e_412_but_object_not_visible_is_retryable_unavailable(source):
    storage, stub = make_s3()
    precondition_failed(stub)
    stub.add_client_error("head_object", service_error_code="404", http_status_code=404)
    with stub, pytest.raises(MediaStorageUnavailable):
        await storage.put_object(KEY, source, "image/jpeg")


async def test_f_exhausted_timeouts_map_to_unavailable(source, monkeypatch):
    storage, _ = make_s3()
    client = storage._get_client()

    def timed_out(**kwargs):
        raise ReadTimeoutError(endpoint_url="https://example.invalid")

    monkeypatch.setattr(client, "put_object", timed_out)
    with pytest.raises(MediaStorageUnavailable) as exc:
        await storage.put_object(KEY, source, "image/jpeg")
    assert "example.invalid" not in str(exc.value)  # provider details never escape
