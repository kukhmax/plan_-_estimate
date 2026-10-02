"""Stage 14C.6B — HTTP / multipart adversarial verification of the upload
route (docs/STAGE_14C_MEDIA_API_CONTRACT.md §10, §11b, §11d).

Large bodies are STREAMED to the ASGI app from a generator (1 MiB chunks of a
reused buffer), so no test builds a 27 MB bytes object. Every failure path
asserts the full cleanup set: envelope, admission released, processing slot
free, spool closed, workspace removed, no rows, no PUT/HEAD.
"""

import json
import uuid
from collections.abc import Iterator
from types import SimpleNamespace

import pytest

from app.api.v1.endpoints import photos as photos_endpoint
from app.main import app
from tests import test_stage14c4_photos_api as c4
from tests.test_stage14c4_photos_api import BOUNDARY, image_bytes, path_for
from tests.test_stage14c6a_hardening import assert_clean, counts

api = c4.api  # shared fixture

MIB = 1024 * 1024
_ZEROS = b"\x00" * MIB


def prefix(a, *, upload_id: str, filename: str = "a.jpg", boundary: str = BOUNDARY, extra=()) -> bytes:
    parts = [("upload_id", upload_id), ("context", "ROOM"), ("room_id", str(a.room)), *extra]
    out = b""
    for name, value in parts:
        out += f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
    out += (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: image/jpeg\r\n\r\n").encode()
    return out


def suffix(boundary: str = BOUNDARY) -> bytes:
    return f"\r\n--{boundary}--\r\n".encode()


def streamed_body(head: bytes, file_len: int, tail: bytes) -> Iterator[bytes]:
    yield head
    remaining = file_len
    while remaining:
        n = min(MIB, remaining)
        yield _ZEROS if n == MIB else _ZEROS[:n]
        remaining -= n
    yield tail


async def call_stream(path: str, *, token: str | None, chunks: Iterator[bytes],
                      content_length: str | None = None,
                      content_type: str = f"multipart/form-data; boundary={BOUNDARY}") -> SimpleNamespace:
    headers = [(b"content-type", content_type.encode())]
    if content_length is not None:
        headers.append((b"content-length", content_length.encode()))
    if token:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    it = iter(chunks)
    state = {"messages": 0, "bytes": 0, "done": False}
    pending: list[bytes] = []

    async def receive():
        if state["done"]:
            return {"type": "http.disconnect"}
        chunk = pending.pop() if pending else next(it, None)
        if chunk is None:
            state["done"] = True
            return {"type": "http.request", "body": b"", "more_body": False}
        state["messages"] += 1
        state["bytes"] += len(chunk)
        nxt = next(it, None)
        if nxt is None:
            state["done"] = True
            return {"type": "http.request", "body": chunk, "more_body": False}
        pending.append(nxt)
        return {"type": "http.request", "body": chunk, "more_body": True}

    sent = {"status": None, "body": b""}

    async def send(message):
        if message["type"] == "http.response.start":
            sent["status"] = message["status"]
        elif message["type"] == "http.response.body":
            sent["body"] += message.get("body", b"")

    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
             "scheme": "http", "path": path, "raw_path": path.encode(), "query_string": b"",
             "headers": headers, "client": ("127.0.0.1", 1), "server": ("test", 80), "root_path": ""}
    await app(scope, receive, send)
    return SimpleNamespace(status=sent["status"], body=sent["body"], **state)


def code(r) -> str:
    return json.loads(r.body)["detail"]["code"]


@pytest.fixture
def copy_spy(monkeypatch):
    calls = []
    real = photos_endpoint.copy_bounded

    def spy(*args):
        calls.append(args[1])
        return real(*args)

    monkeypatch.setattr(photos_endpoint, "copy_bounded", spy)
    return calls


async def assert_rejected_clean(a, r, status: int, expected_code: str) -> None:
    assert r.status == status, r.body
    assert code(r) == expected_code
    assert await counts(a.db) == (0, 0)
    assert_clean(a)


def sized(a, total: int) -> tuple[bytes, int, bytes]:
    head = prefix(a, upload_id=str(uuid.uuid4()))
    tail = suffix()
    return head, total - len(head) - len(tail), tail


# ---------------------------------------------------------------------------
# Request-body boundary (27 000 000 actual bytes) at real size, streamed
# ---------------------------------------------------------------------------


async def test_request_of_exactly_27_000_000_bytes_passes_the_request_guard(api, copy_spy):
    head, file_len, tail = sized(api, 27_000_000)
    r = await call_stream(path_for(api.project), token=api.token, chunks=streamed_body(head, file_len, tail),
                          content_length="27000000")
    assert r.bytes == 27_000_000
    assert copy_spy  # the body was fully parsed: the request guard did not fire
    await assert_rejected_clean(api, r, 413, "PHOTO_TOO_LARGE")  # the 25 MB FILE limit fired instead


async def test_request_of_27_000_001_bytes_is_cut_by_the_request_guard(api, copy_spy):
    head, file_len, tail = sized(api, 27_000_001)
    r = await call_stream(path_for(api.project), token=api.token, chunks=streamed_body(head, file_len, tail),
                          content_length=None)  # missing Content-Length: only actual bytes count
    assert copy_spy == []  # cut during parsing, before any copy
    await assert_rejected_clean(api, r, 413, "PHOTO_TOO_LARGE")


async def test_content_length_smaller_than_actual_body_cannot_bypass(api, copy_spy):
    head, file_len, tail = sized(api, 40_000_000)
    r = await call_stream(path_for(api.project), token=api.token, chunks=streamed_body(head, file_len, tail),
                          content_length="1000")
    assert copy_spy == [] and r.bytes < 40_000_000  # stopped early
    await assert_rejected_clean(api, r, 413, "PHOTO_TOO_LARGE")


@pytest.mark.parametrize("raw", ["abc", "-1", "+5", "1,2", " "])
async def test_malformed_content_length_is_422_before_the_body(api, raw):
    head, file_len, tail = sized(api, 2000)
    r = await call_stream(path_for(api.project), token=api.token, chunks=streamed_body(head, file_len, tail),
                          content_length=raw)
    assert r.messages == 0
    await assert_rejected_clean(api, r, 422, "PHOTO_UPLOAD_MALFORMED")


# ---------------------------------------------------------------------------
# Multipart shape
# ---------------------------------------------------------------------------


async def test_empty_file_is_invalid_image(api):
    head = prefix(api, upload_id=str(uuid.uuid4()))
    r = await call_stream(path_for(api.project), token=api.token, chunks=iter([head + suffix()]),
                          content_length=str(len(head + suffix())))
    await assert_rejected_clean(api, r, 422, "PHOTO_INVALID_IMAGE")


@pytest.mark.parametrize("cut", ["mid-file", "before-file-data", "no-final-boundary"])
async def test_truncated_multipart_is_malformed(api, cut):
    head = prefix(api, upload_id=str(uuid.uuid4()))
    data = image_bytes()
    body = {"mid-file": head + data[: len(data) // 2],
            "before-file-data": head[:-10],
            "no-final-boundary": head + data + b"\r\n"}[cut]
    r = await call_stream(path_for(api.project), token=api.token, chunks=iter([body]),
                          content_length=str(len(body)))
    await assert_rejected_clean(api, r, 422, "PHOTO_UPLOAD_MALFORMED")


def assembled(a, extra_parts: list[tuple[str, object]]) -> bytes:
    return c4.multipart([("upload_id", str(uuid.uuid4())), ("context", "ROOM"), ("room_id", str(a.room)),
                         *extra_parts])


@pytest.mark.parametrize(
    ("label", "body_fn", "content_type"),
    [
        ("two-files", lambda a: assembled(a, [("file", ("a.jpg", "image/jpeg", image_bytes())),
                                              ("other", ("b.jpg", "image/jpeg", image_bytes()))]), None),
        ("duplicate-file", lambda a: assembled(a, [("file", ("a.jpg", "image/jpeg", image_bytes())),
                                                   ("file", ("b.jpg", "image/jpeg", image_bytes()))]), None),
        ("too-many-fields", lambda a: assembled(a, [*[("caption", "x")] * 6,
                                                    ("file", ("a.jpg", "image/jpeg", image_bytes()))]), None),
        ("oversized-scalar", lambda a: assembled(a, [("caption", "c" * 9000),
                                                     ("file", ("a.jpg", "image/jpeg", image_bytes()))]), None),
        ("boundary-mismatch", lambda a: assembled(a, [("file", ("a.jpg", "image/jpeg", image_bytes()))]),
         "multipart/form-data; boundary=SOMETHING-ELSE"),
        ("missing-boundary", lambda a: assembled(a, [("file", ("a.jpg", "image/jpeg", image_bytes()))]),
         "multipart/form-data"),
        ("garbage", lambda a: b"\x00\x01not multipart\r\n--", None),
    ],
)
async def test_malformed_multipart_shapes(api, label, body_fn, content_type):
    body = body_fn(api)
    r = await call_stream(path_for(api.project), token=api.token, chunks=iter([body]),
                          content_length=str(len(body)),
                          content_type=content_type or f"multipart/form-data; boundary={BOUNDARY}")
    await assert_rejected_clean(api, r, 422, "PHOTO_UPLOAD_MALFORMED")


async def test_misleading_filename_and_content_type_are_ignored(api):
    head = prefix(api, upload_id=str(uuid.uuid4()), filename="../../etc/passwd.exe")
    head = head.replace(b"Content-Type: image/jpeg", b"Content-Type: application/x-msdownload")
    data = image_bytes("PNG")
    body = head + data + suffix()
    r = await call_stream(path_for(api.project), token=api.token, chunks=iter([body]),
                          content_length=str(len(body)))
    assert r.status == 201
    asset = json.loads(r.body)["asset"]
    assert asset["content_type"] == "image/png" and asset["original_filename"] == "passwd.exe"
    assert all(".exe" not in key and "passwd" not in key for key in api.storage.keys())
