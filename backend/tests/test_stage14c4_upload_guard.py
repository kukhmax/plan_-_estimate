"""Stage 14C.4 — HTTP upload guard primitives, plus pins on the exact
Starlette / python-multipart behaviour the design relies on
(docs/STAGE_14C_MEDIA_API_CONTRACT.md §10, §11b, §20).
"""

import inspect
import io
from pathlib import Path

import pytest
from python_multipart.exceptions import FormParserError, MultipartParseError
from starlette.datastructures import Headers
from starlette.formparsers import MultiPartException, MultiPartParser
from starlette.requests import Request

from app.api.upload_guard import (
    COPY_CHUNK_BYTES,
    MAX_CONCURRENT_UPLOAD_REQUESTS,
    RequestBodyTooLargeError,
    UploadAdmission,
    copy_bounded,
    limited_receive,
    parse_content_length,
)
from app.domain.exceptions import PhotoTooLargeError, PhotoUploadMalformedError
from tests import test_stage14c4_photos_api as c4

api = c4.api  # fixture

# ---------------------------------------------------------------------------
# Content-Length (advisory only)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("raw", "expected"), [(None, None), ("0", 0), ("27000000", 27_000_000), (" 12 ", 12)])
def test_parse_content_length(raw, expected):
    assert parse_content_length(raw) == expected


@pytest.mark.parametrize("raw", ["abc", "-5", "+5", "", "1,2", "1e6", "12.0"])
def test_parse_content_length_rejects_malformed(raw):
    with pytest.raises(PhotoUploadMalformedError):
        parse_content_length(raw)


# ---------------------------------------------------------------------------
# Actual-byte receive guard
# ---------------------------------------------------------------------------


def body_messages(chunks: list[bytes]):
    messages = [{"type": "http.request", "body": c, "more_body": i < len(chunks) - 1} for i, c in enumerate(chunks)]
    state = {"calls": 0}

    async def receive():
        state["calls"] += 1
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    return receive, state


async def drain(receive):
    total = 0
    while True:
        message = await receive()
        total += len(message.get("body", b""))
        if not message.get("more_body"):
            return total


async def test_guard_allows_exactly_the_limit():
    receive, _ = body_messages([b"a" * 600, b"b" * 400])
    assert await drain(limited_receive(receive, 1000)) == 1000


async def test_guard_rejects_one_byte_over_and_stops_reading():
    receive, state = body_messages([b"a" * 600, b"b" * 401, b"c" * 1000, b"d" * 1000])
    guarded = limited_receive(receive, 1000)
    with pytest.raises(RequestBodyTooLargeError):
        await drain(guarded)
    assert state["calls"] == 2  # the crossing message is the last one read


async def test_guard_counts_bytes_not_messages():
    receive, _ = body_messages([b"x"] * 1001)
    with pytest.raises(RequestBodyTooLargeError):
        await drain(limited_receive(receive, 1000))


async def test_guard_passes_non_body_messages_through():
    async def receive():
        return {"type": "http.disconnect"}

    assert (await limited_receive(receive, 0)())["type"] == "http.disconnect"


# ---------------------------------------------------------------------------
# Bounded copy
# ---------------------------------------------------------------------------


class SpyFile(io.BytesIO):
    def __init__(self, data: bytes) -> None:
        super().__init__(data)
        self.read_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:  # type: ignore[override]
        assert size is not None and 0 < size <= COPY_CHUNK_BYTES, size  # never unbounded
        self.read_sizes.append(size)
        return super().read(size)


def test_copy_exact_limit_preserves_bytes(tmp_path):
    data = bytes(range(256)) * 10_000  # 2_560_000 bytes, > 2 chunks
    source = SpyFile(data)
    dest = tmp_path / "original"
    assert copy_bounded(source, dest, len(data)) == len(data)
    assert dest.read_bytes() == data
    assert max(source.read_sizes) == COPY_CHUNK_BYTES == 1024 * 1024


def test_copy_one_byte_over_is_rejected_after_reading_at_most_limit_plus_one(tmp_path):
    data = b"z" * (3 * COPY_CHUNK_BYTES)
    limit = 2 * COPY_CHUNK_BYTES
    source = SpyFile(data)
    with pytest.raises(PhotoTooLargeError):
        copy_bounded(source, tmp_path / "original", limit)
    assert sum(source.read_sizes) <= limit + 1


def test_copy_refuses_an_existing_destination(tmp_path):
    dest = tmp_path / "original"
    dest.write_bytes(b"x")
    with pytest.raises(FileExistsError):
        copy_bounded(io.BytesIO(b"y"), dest, 10)


# ---------------------------------------------------------------------------
# Admission
# ---------------------------------------------------------------------------


def test_admission_capacity_two_non_blocking():
    assert MAX_CONCURRENT_UPLOAD_REQUESTS == 2
    admission = UploadAdmission(MAX_CONCURRENT_UPLOAD_REQUESTS)
    assert admission.try_acquire() and admission.try_acquire()
    assert admission.try_acquire() is False  # third refused immediately, no queue
    admission.release()
    assert admission.try_acquire() is True
    admission.release()
    admission.release()
    assert admission.in_use == 0
    with pytest.raises(RuntimeError):
        admission.release()


# ---------------------------------------------------------------------------
# Pins: the Starlette / python-multipart behaviour this design relies on
# ---------------------------------------------------------------------------


def test_form_accepts_the_limits_we_pass():
    params = inspect.signature(Request.form).parameters
    assert {"max_files", "max_fields", "max_part_size"} <= set(params)


def test_file_parts_spool_after_one_mib():
    assert MultiPartParser.spool_max_size == 1024 * 1024


def multipart(parts: list[tuple[str, bytes, str | None]], boundary: str = "pinBOUNDARY") -> bytes:
    out = b""
    for name, data, filename in parts:
        disposition = f'form-data; name="{name}"' + (f'; filename="{filename}"' if filename else "")
        out += f"--{boundary}\r\nContent-Disposition: {disposition}\r\n\r\n".encode() + data + b"\r\n"
    return out + f"--{boundary}--\r\n".encode()


async def parse(body: bytes, **limits):
    async def stream():
        yield body
        yield b""

    headers = Headers({"content-type": "multipart/form-data; boundary=pinBOUNDARY"})
    return await MultiPartParser(headers, stream(), **limits).parse()


async def test_max_part_size_does_not_bound_file_parts():
    """Why copy_bounded + limited_receive exist: a 2 MiB file passes an
    8 KiB max_part_size untouched."""
    form = await parse(multipart([("file", b"f" * (2 * 1024 * 1024), "a.jpg")]), max_part_size=8192)
    upload = form["file"]
    assert upload.size == 2 * 1024 * 1024 and upload.file._rolled  # spooled to disk
    await form.close()


async def test_max_part_size_bounds_scalar_parts():
    with pytest.raises(MultiPartException):
        await parse(multipart([("caption", b"c" * 8193, None)]), max_part_size=8192)


async def test_rolled_spool_is_an_unnamed_file(tmp_path):
    form = await parse(multipart([("file", b"f" * (2 * 1024 * 1024), "a.jpg")]))
    fd = form["file"].file.fileno()
    assert Path(f"/proc/self/fd/{fd}").readlink().name.endswith("(deleted)")
    await form.close()


@pytest.mark.parametrize(
    "failure",
    [
        pytest.param(lambda: FormParserError("injected"), id="raw-FormParserError"),
        pytest.param(lambda: MultipartParseError("injected"), id="raw-MultipartParseError"),
        pytest.param(lambda: MultiPartException("Invalid multipart data."), id="starlette-MultiPartException"),
    ],
)
async def test_any_framework_multipart_failure_is_normalized_to_422(api, monkeypatch, failure):
    """Application normalization boundary (contract §10): whichever shape the
    framework uses for a multipart parse failure -- python-multipart's raw
    error escaping the parser (Starlette 1.6.0) or Starlette's own
    MultiPartException, which Request.form turns into a 400 (Starlette 1.7.0
    wraps raw parser errors this way) -- the route answers 422
    PHOTO_UPLOAD_MALFORMED and leaves no state behind. The failure is injected
    at the parser, so Starlette's own conversion in Request.form still runs."""
    calls = {"n": 0}

    async def failing_parse(self):
        calls["n"] += 1
        raise failure()

    monkeypatch.setattr(MultiPartParser, "parse", failing_parse)
    c = await c4.call(c4.path_for(api.project), token=api.token, body=c4.form(api))
    assert calls["n"] == 1  # the injected parser really ran
    assert c.status == 422, (c.status, c.body)
    assert c4.detail(c) == {"code": "PHOTO_UPLOAD_MALFORMED", "message": "The upload request is malformed"}
    assert await c4.counts(api.db) == (0, 0) and c4.temp_clean(api) and api.runtime.admission.in_use == 0
