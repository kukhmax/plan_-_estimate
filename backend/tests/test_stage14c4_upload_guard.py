"""Stage 14C.4 — HTTP upload guard primitives, plus pins on the exact
Starlette / python-multipart behaviour the design relies on
(docs/STAGE_14C_MEDIA_API_CONTRACT.md §10, §11b, §20).
"""

import inspect
import io
from pathlib import Path

import pytest
from starlette.datastructures import Headers
from starlette.formparsers import MultiPartParser
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
    from starlette.formparsers import MultiPartException

    with pytest.raises(MultiPartException):
        await parse(multipart([("caption", b"c" * 8193, None)]), max_part_size=8192)


async def test_rolled_spool_is_an_unnamed_file(tmp_path):
    form = await parse(multipart([("file", b"f" * (2 * 1024 * 1024), "a.jpg")]))
    fd = form["file"].file.fileno()
    assert Path(f"/proc/self/fd/{fd}").readlink().name.endswith("(deleted)")
    await form.close()


async def test_non_multipart_body_raises_a_raw_python_multipart_error():
    """Starlette 1.6.0 converts only its own MultiPartException; a body that
    is not multipart raises python-multipart's FormParserError, which the
    upload route therefore catches itself."""
    from python_multipart.exceptions import FormParserError
    from starlette.formparsers import MultiPartException

    with pytest.raises(FormParserError) as exc:
        await parse(b"this is not multipart at all")
    assert not isinstance(exc.value, MultiPartException)
