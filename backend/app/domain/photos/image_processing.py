"""Photo validation and derivative pipeline (Stage 14B.3; plan §4, §5.2).

Canonical original: the exact uploaded bytes. The pipeline only reads them
(SHA-256 over exactly those bytes, lazy header parse, full decode of an
in-memory copy) and never rewrites the file, so the original keeps its
EXIF/metadata byte-for-byte.

Derivatives (display, thumbnail): EXIF orientation applied to the decoded
copy, colour converted to sRGB, transparency flattened onto #FFFFFF, resized
to a maximum longest edge (never upscaled) and encoded as JPEG with every
metadata block stripped (no EXIF, ICC, XMP, comments).

Decompression-bomb safety: the explicit application limit
(PHOTO_MAX_DECODED_PIXELS) and a maximum edge are checked from the header
before any pixel data is decoded. Pillow's own global bomb limit is left
untouched; its DecompressionBombError is treated as a rejection.

`process_image_file` is synchronous CPU work. `ImageProcessor` is the
service boundary: it serializes processing (concurrency 1, OWNER APPROVED)
and runs it in a worker thread.
"""

import asyncio
import hashlib
import io
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING

import anyio
from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

from app.domain.exceptions import (
    PhotoAnimatedError,
    PhotoInvalidImageError,
    PhotoProcessingBusyError,
    PhotoTooLargeError,
    PhotoTooManyPixelsError,
    PhotoUnsupportedFormatError,
)
from app.domain.photos.keys import (
    DERIVATIVE_CONTENT_TYPE,
    ORIGINAL_CONTENT_TYPES,
    ORIGINAL_EXTENSIONS,
    PhotoFormat,
)

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)

# OWNER APPROVED (14B.1 R8 / closure): initial derivative geometry and limits.
DISPLAY_MAX_EDGE = 2048
THUMBNAIL_MAX_EDGE = 480
MAX_EDGE_PIXELS = 12_000
FLATTEN_BACKGROUND = (255, 255, 255)  # #FFFFFF
# OWNER APPROVED: maximum concurrent image-processing operations.
MAX_CONCURRENT_PROCESSING = 1

# OWNER APPROVED initial defaults after the ARM64 benchmark (14B plan §23.12).
# Tunable via ImagePipelineConfig after evaluating real site photos; not a
# domain invariant (no schema depends on them).
DEFAULT_DISPLAY_JPEG_QUALITY = 85
DEFAULT_THUMBNAIL_JPEG_QUALITY = 80

JPEG_SUBSAMPLING = "4:2:0"
HASH_CHUNK_BYTES = 1024 * 1024

# Pillow plugins allowed to identify input. Anything else (HEIC/HEIF, GIF,
# TIFF, BMP, SVG, PDF, text...) is unidentified -> unsupported format.
_ALLOWED_PILLOW_FORMATS = ("JPEG", "PNG", "WEBP")
# Phone JPEGs with an embedded preview are reported by Pillow as MPO; the
# file is a standard JPEG whose first frame is the primary image.
_PILLOW_FORMAT_MAP = {
    "JPEG": PhotoFormat.JPEG,
    "MPO": PhotoFormat.JPEG,
    "PNG": PhotoFormat.PNG,
    "WEBP": PhotoFormat.WEBP,
}

_EXIF_ORIENTATION = 0x0112
_EXIF_IFD = 0x8769
_EXIF_DATETIME_ORIGINAL = 0x9003


@dataclass(frozen=True)
class ImagePipelineConfig:
    max_encoded_bytes: int = 25_000_000
    max_decoded_pixels: int = 60_000_000
    max_edge_pixels: int = MAX_EDGE_PIXELS
    display_max_edge: int = DISPLAY_MAX_EDGE
    thumbnail_max_edge: int = THUMBNAIL_MAX_EDGE
    display_jpeg_quality: int = DEFAULT_DISPLAY_JPEG_QUALITY
    thumbnail_jpeg_quality: int = DEFAULT_THUMBNAIL_JPEG_QUALITY

    @classmethod
    def from_settings(cls, settings: "Settings") -> "ImagePipelineConfig":
        return cls(
            max_encoded_bytes=settings.PHOTO_MAX_UPLOAD_BYTES,
            max_decoded_pixels=settings.PHOTO_MAX_DECODED_PIXELS,
        )


@dataclass(frozen=True)
class DerivativeInfo:
    path: Path
    width: int
    height: int
    byte_size: int
    content_type: str = DERIVATIVE_CONTENT_TYPE


@dataclass(frozen=True)
class ProcessedImage:
    format: PhotoFormat
    extension: str
    content_type: str
    byte_size: int
    sha256: str
    # Dimensions as stored in the file (before EXIF orientation).
    stored_width: int
    stored_height: int
    # Dimensions as displayed (after EXIF orientation) — the canonical ones.
    width: int
    height: int
    exif_orientation: int | None
    # EXIF DateTimeOriginal: camera-local wall time, timezone unknown.
    captured_at: datetime | None
    display: DerivativeInfo
    thumbnail: DerivativeInfo


def hash_file_bounded(path: Path, max_bytes: int) -> tuple[str, int]:
    """SHA-256 and byte count of `path`, refusing more than `max_bytes`.
    Reads at most `max_bytes + 1` bytes regardless of the file size."""
    digest = hashlib.sha256()
    total = 0
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(min(HASH_CHUNK_BYTES, max_bytes + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise PhotoTooLargeError("image exceeds the maximum upload size")
            digest.update(chunk)
    return digest.hexdigest(), total


def _fit_within(width: int, height: int, max_edge: int) -> tuple[int, int]:
    longest = max(width, height)
    if longest <= max_edge:
        return width, height  # never upscale
    scale = max_edge / longest
    return max(1, round(width * scale)), max(1, round(height * scale))


def _read_captured_at(exif: Image.Exif) -> datetime | None:
    try:
        raw = exif.get_ifd(_EXIF_IFD).get(_EXIF_DATETIME_ORIGINAL)
        if not isinstance(raw, str):
            return None
        return datetime.strptime(raw.strip("\x00 ").strip(), "%Y:%m:%d %H:%M:%S")
    except (ValueError, TypeError, KeyError, OSError):
        return None


def _to_srgb_rgb(image: Image.Image) -> Image.Image:
    """Return an RGB image in sRGB with transparency flattened on white."""
    icc = image.info.get("icc_profile")
    has_alpha = image.mode in ("RGBA", "LA", "PA") or (
        image.mode == "P" and "transparency" in image.info
    )
    if image.mode not in ("RGB", "RGBA", "CMYK"):
        image = image.convert("RGBA" if has_alpha else "RGB")
    if icc:
        try:
            source_profile = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            out_mode = "RGBA" if image.mode == "RGBA" else "RGB"
            converted = ImageCms.profileToProfile(
                image, source_profile, ImageCms.createProfile("sRGB"), outputMode=out_mode
            )
            if converted is not None:  # None only for inPlace=True
                image = converted
        except (ImageCms.PyCMSError, OSError, ValueError):
            # An unusable embedded profile is ignored; pixels are treated as sRGB.
            logger.info("ignoring unusable embedded ICC profile")
    if image.mode == "RGBA":
        background = Image.new("RGB", image.size, FLATTEN_BACKGROUND)
        background.paste(image, mask=image.getchannel("A"))
        image = background
    elif image.mode != "RGB":
        image = image.convert("RGB")
    return image


def _write_derivative(image: Image.Image, max_edge: int, quality: int, path: Path) -> DerivativeInfo:
    size = _fit_within(image.width, image.height, max_edge)
    derived = image.resize(size, Image.Resampling.LANCZOS, reducing_gap=3.0) if size != image.size else image.copy()
    derived.info = {}  # strip every metadata block carried on the image
    derived.save(
        path,
        format="JPEG",
        quality=quality,
        subsampling=JPEG_SUBSAMPLING,
        progressive=True,
        optimize=False,
    )
    return DerivativeInfo(path=path, width=derived.width, height=derived.height, byte_size=path.stat().st_size)


def process_image_file(source: Path, workspace: Path, config: ImagePipelineConfig) -> ProcessedImage:
    """Validate the canonical original at `source` and write `display.jpg` and
    `thumb.jpg` into `workspace`. `source` is opened read-only and never modified."""
    source = Path(source)
    size = source.stat().st_size
    if size > config.max_encoded_bytes:
        raise PhotoTooLargeError("image exceeds the maximum upload size")
    if size == 0:
        raise PhotoInvalidImageError("empty file")
    sha256, byte_size = hash_file_bounded(source, config.max_encoded_bytes)

    try:
        with Image.open(source, formats=_ALLOWED_PILLOW_FORMATS) as image:
            photo_format = _PILLOW_FORMAT_MAP.get(image.format or "")
            if photo_format is None:
                raise PhotoUnsupportedFormatError("unsupported image format")
            stored_width, stored_height = image.size
            if (
                stored_width <= 0
                or stored_height <= 0
                or stored_width * stored_height > config.max_decoded_pixels
                or max(stored_width, stored_height) > config.max_edge_pixels
            ):
                raise PhotoTooManyPixelsError("image dimensions exceed the limit")
            if image.format != "MPO" and getattr(image, "is_animated", False):
                raise PhotoAnimatedError("animated images are not supported")
            if image.format == "MPO":
                image.seek(0)
            image.load()  # full decode: detects truncated/corrupt data
            exif = image.getexif()
            orientation = exif.get(_EXIF_ORIENTATION)
            captured_at = _read_captured_at(exif)
            oriented = ImageOps.exif_transpose(image, in_place=False)
            oriented = _to_srgb_rgb(oriented)
    except (PhotoTooManyPixelsError, PhotoAnimatedError, PhotoUnsupportedFormatError):
        raise
    except Image.DecompressionBombError:
        raise PhotoTooManyPixelsError("image dimensions exceed the limit") from None
    except UnidentifiedImageError:
        raise PhotoUnsupportedFormatError("unsupported image format") from None
    except (OSError, SyntaxError, ValueError, EOFError, MemoryError) as exc:
        raise PhotoInvalidImageError(f"invalid image data ({type(exc).__name__})") from None

    width, height = oriented.size
    display = _write_derivative(
        oriented, config.display_max_edge, config.display_jpeg_quality, workspace / "display.jpg"
    )
    # The thumbnail is derived from the same oriented sRGB image.
    thumbnail = _write_derivative(
        oriented, config.thumbnail_max_edge, config.thumbnail_jpeg_quality, workspace / "thumb.jpg"
    )
    return ProcessedImage(
        format=photo_format,
        extension=ORIGINAL_EXTENSIONS[photo_format],
        content_type=ORIGINAL_CONTENT_TYPES[photo_format],
        byte_size=byte_size,
        sha256=sha256,
        stored_width=stored_width,
        stored_height=stored_height,
        width=width,
        height=height,
        exif_orientation=orientation if isinstance(orientation, int) else None,
        captured_at=captured_at,
        display=display,
        thumbnail=thumbnail,
    )


ProcessFn = Callable[[Path, Path, ImagePipelineConfig], ProcessedImage]


class ImageProcessor:
    """Service boundary for image processing.

    At most `MAX_CONCURRENT_PROCESSING` (1) operations run the pipeline at a
    time in this process. A caller waits up to `wait_seconds`
    (PHOTO_PROCESSING_WAIT_SECONDS, approved default 30) for the slot and
    otherwise gets PhotoProcessingBusyError (retryable). The pipeline runs in
    a worker thread; the slot is held until that thread has finished, even if
    the awaiting task is cancelled, so the limit cannot be exceeded.
    """

    def __init__(
        self,
        config: ImagePipelineConfig,
        *,
        wait_seconds: float,
        process_fn: ProcessFn = process_image_file,
    ) -> None:
        if wait_seconds <= 0:
            raise ValueError("wait_seconds must be positive")
        self._config = config
        self._wait_seconds = wait_seconds
        self._process_fn = process_fn
        self._slot = asyncio.Semaphore(MAX_CONCURRENT_PROCESSING)

    async def process(self, source: Path, workspace: Path) -> ProcessedImage:
        try:
            await asyncio.wait_for(self._slot.acquire(), timeout=self._wait_seconds)
        except TimeoutError:
            raise PhotoProcessingBusyError("image processing is busy; retry later") from None
        try:
            # abandon_on_cancel=False: cancellation waits for the thread.
            return await anyio.to_thread.run_sync(
                partial(self._process_fn, Path(source), Path(workspace), self._config),
                abandon_on_cancel=False,
            )
        finally:
            self._slot.release()
