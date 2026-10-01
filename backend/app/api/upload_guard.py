"""HTTP boundary guards for the photo upload route (Stage 14C.4).

Canonical contract: docs/STAGE_14C_MEDIA_API_CONTRACT.md §9–§11, §20.

These primitives exist because, in the audited stack (Starlette 1.6.0 +
python-multipart 0.0.32), multipart parsing has no total-body limit and
`max_part_size` does not apply to file parts: file data is spooled into a
SpooledTemporaryFile (1 MiB in memory, then an unnamed file in the system
temp dir) for as long as the client keeps sending. So:

- `parse_content_length` lets the route reject a declared oversize body
  before reading it; the header is never trusted as the limit.
- `limited_receive` counts the ACTUAL `http.request` body bytes and aborts
  the parse once they exceed PHOTO_MAX_REQUEST_BYTES (missing, false or
  chunked Content-Length cannot bypass it).
- `copy_bounded` copies the parsed file part into the Stage 14B workspace in
  <= 1 MiB chunks and refuses more than PHOTO_MAX_UPLOAD_BYTES actual bytes.
- `UploadAdmission` bounds concurrent upload requests (reception +
  processing) independently of the image-processing slot, failing fast
  before the body is read; this bounds temp disk use.
- `sweep_stale_photo_temp` runs the Stage 14B stale cleanup and never lets a
  cleanup failure break startup or the request.
"""

import logging
from pathlib import Path
from typing import BinaryIO

from starlette.types import Message, Receive

from app.domain.exceptions import PhotoTooLargeError, PhotoUploadMalformedError
from app.domain.photos.temp import PhotoTempDirError, cleanup_stale_photo_temp

logger = logging.getLogger(__name__)

# OWNER APPROVED (14C.4): process-wide in-flight upload requests. Processing
# itself stays serialized by ImageProcessor (MAX_CONCURRENT_PROCESSING = 1);
# admitting more requests than "one processing + one being received" adds
# temp disk use without throughput.
MAX_CONCURRENT_UPLOAD_REQUESTS = 2
COPY_CHUNK_BYTES = 1024 * 1024  # 1 MiB


class RequestBodyTooLargeError(Exception):
    """The actual request body exceeded PHOTO_MAX_REQUEST_BYTES."""

    code = "PHOTO_TOO_LARGE"


def parse_content_length(raw: str | None) -> int | None:
    """Declared body length, or None when absent. Advisory only: used for an
    early 413, never as the enforcement of the limit."""
    if raw is None:
        return None
    value = raw.strip()
    if not value.isdigit():  # rejects negatives, signs, blanks, lists
        raise PhotoUploadMalformedError("invalid Content-Length header")
    return int(value)


def limited_receive(receive: Receive, max_body_bytes: int) -> Receive:
    """Wrap an ASGI `receive` so the body can never exceed `max_body_bytes`
    actual bytes, whatever Content-Length claims. Raising inside the
    multipart stream makes Starlette close every spooled part."""
    total = 0

    async def guarded() -> Message:
        nonlocal total
        message = await receive()
        if message["type"] == "http.request":
            total += len(message.get("body", b""))
            if total > max_body_bytes:
                raise RequestBodyTooLargeError("request body exceeds the maximum size")
        return message

    return guarded


def copy_bounded(source: BinaryIO, destination: Path, max_bytes: int) -> int:
    """Copy `source` to the new file `destination` in <= 1 MiB chunks, reading
    at most `max_bytes + 1` bytes. Returns the byte count; raises
    PhotoTooLargeError above `max_bytes`. Blocking: run in a worker thread."""
    total = 0
    with open(destination, "xb") as out:  # server-chosen name; never pre-existing
        while True:
            chunk = source.read(min(COPY_CHUNK_BYTES, max_bytes + 1 - total))
            if not chunk:
                return total
            total += len(chunk)
            if total > max_bytes:
                raise PhotoTooLargeError("image exceeds the maximum upload size")
            out.write(chunk)


class UploadAdmission:
    """Non-blocking counter of in-flight upload requests (single event loop:
    no await between check and increment, so no lock is needed)."""

    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("capacity must be positive")
        self.capacity = capacity
        self.in_use = 0

    def try_acquire(self) -> bool:
        if self.in_use >= self.capacity:
            return False
        self.in_use += 1
        return True

    def release(self) -> None:
        if self.in_use <= 0:
            raise RuntimeError("upload admission released more often than acquired")
        self.in_use -= 1


def sweep_stale_photo_temp(temp_dir: str, older_than_seconds: int) -> None:
    """Remove abandoned `pe-photo-*` workspaces (crash leftovers). A missing
    directory is nothing to clean; failures are logged, never raised, so a
    cleanup problem cannot stop startup or an upload."""
    if not Path(temp_dir).exists():
        return
    try:
        report = cleanup_stale_photo_temp(temp_dir, older_than_seconds)
    except (OSError, PhotoTempDirError) as exc:
        logger.error("photo temp sweep failed: %s", type(exc).__name__)
        return
    if report.removed or report.errors:
        logger.info(
            "photo temp sweep: %d removed, %d errors, %d kept",
            len(report.removed), len(report.errors), len(report.kept_fresh),
        )
