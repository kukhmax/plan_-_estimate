"""Stage 14B.3 — image validation + derivative pipeline + concurrency guard."""

import asyncio
import hashlib
import io
import struct
import threading
import time
import zlib
from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image, ImageCms

from app.core.config import Settings
from app.domain.exceptions import (
    PhotoAnimatedError,
    PhotoInvalidImageError,
    PhotoProcessingBusyError,
    PhotoTooLargeError,
    PhotoTooManyPixelsError,
    PhotoUnsupportedFormatError,
)
from app.domain.photos.image_processing import (
    ImagePipelineConfig,
    ImageProcessor,
    hash_file_bounded,
    process_image_file,
)
from app.domain.photos.keys import PhotoFormat

CFG = ImagePipelineConfig()


def write(tmp_path: Path, name: str, data: bytes) -> Path:
    p = tmp_path / name
    p.write_bytes(data)
    return p


def encode(image: Image.Image, fmt: str, **params) -> bytes:
    buf = io.BytesIO()
    image.save(buf, format=fmt, **params)
    return buf.getvalue()


def half_image(size=(200, 100), left=(255, 0, 0), right=(0, 0, 255), mode="RGB") -> Image.Image:
    im = Image.new(mode, size, left)
    im.paste(Image.new(mode, (size[0] // 2, size[1]), right), (size[0] // 2, 0))
    return im


def png_header_only(width: int, height: int) -> bytes:
    """A syntactically valid PNG header claiming huge dimensions, with no
    pixel data: proves the header-based limit without allocating memory."""
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(b"\x00")) + chunk(b"IEND", b"")


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    return ws


def assert_clean_jpeg(path: Path) -> Image.Image:
    with Image.open(path) as im:
        im.load()
        assert im.format == "JPEG"
        assert im.mode == "RGB"
        for key in ("exif", "icc_profile", "xmp", "comment", "XML:com.adobe.xmp"):
            assert key not in im.info, key
        assert len(im.getexif()) == 0
        return im.copy()


# --------------------------------------------------------------------------
# Accepted formats
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fmt, expected, ext, ctype",
    [
        ("JPEG", PhotoFormat.JPEG, "jpg", "image/jpeg"),
        ("PNG", PhotoFormat.PNG, "png", "image/png"),
        ("WEBP", PhotoFormat.WEBP, "webp", "image/webp"),
    ],
)
def test_accepted_formats(tmp_path, workspace, fmt, expected, ext, ctype):
    data = encode(half_image((3000, 1500)), fmt)
    src = write(tmp_path, "upload.bin", data)
    result = process_image_file(src, workspace, CFG)
    assert result.format is expected
    assert result.extension == ext
    assert result.content_type == ctype
    assert (result.width, result.height) == (3000, 1500)
    assert (result.stored_width, result.stored_height) == (3000, 1500)
    assert result.byte_size == len(data)
    assert result.sha256 == hashlib.sha256(data).hexdigest()
    # display: longest edge 2048; thumbnail: longest edge 480
    assert (result.display.width, result.display.height) == (2048, 1024)
    assert (result.thumbnail.width, result.thumbnail.height) == (480, 240)
    assert result.display.content_type == result.thumbnail.content_type == "image/jpeg"
    assert result.display.path == workspace / "display.jpg"
    assert result.thumbnail.path == workspace / "thumb.jpg"
    assert result.display.byte_size == result.display.path.stat().st_size
    assert result.thumbnail.byte_size == result.thumbnail.path.stat().st_size
    assert_clean_jpeg(result.display.path)
    assert_clean_jpeg(result.thumbnail.path)


def test_portrait_dimensions(tmp_path, workspace):
    src = write(tmp_path, "p.jpg", encode(half_image((1000, 3000)), "JPEG"))
    result = process_image_file(src, workspace, CFG)
    assert (result.display.width, result.display.height) == (683, 2048)
    assert (result.thumbnail.width, result.thumbnail.height) == (160, 480)


def test_small_image_is_never_upscaled(tmp_path, workspace):
    src = write(tmp_path, "s.png", encode(half_image((300, 120)), "PNG"))
    result = process_image_file(src, workspace, CFG)
    assert (result.display.width, result.display.height) == (300, 120)
    assert (result.thumbnail.width, result.thumbnail.height) == (300, 120)


def test_filename_and_extension_are_ignored(tmp_path, workspace):
    # A PNG named .jpg is identified by content, not by name.
    src = write(tmp_path, "holiday.jpg", encode(half_image(), "PNG"))
    assert process_image_file(src, workspace, CFG).format is PhotoFormat.PNG


def test_phone_mpo_jpeg_is_accepted_as_jpeg(tmp_path, workspace):
    buf = io.BytesIO()
    half_image().save(buf, format="MPO", save_all=True, append_images=[half_image((100, 50))])
    src = write(tmp_path, "phone.jpg", buf.getvalue())
    result = process_image_file(src, workspace, CFG)
    assert result.format is PhotoFormat.JPEG and result.extension == "jpg"
    assert (result.width, result.height) == (200, 100)


# --------------------------------------------------------------------------
# Canonical original immutability + SHA-256
# --------------------------------------------------------------------------


def test_original_bytes_unchanged_and_sha256_over_exact_bytes(tmp_path, workspace):
    exif = Image.Exif()
    exif[0x0112] = 6
    exif[0x010F] = "CameraMaker"
    data = encode(half_image(), "JPEG", exif=exif.tobytes(), comment=b"keep me")
    src = write(tmp_path, "orig.jpg", data)
    before_mtime = src.stat().st_mtime_ns
    result = process_image_file(src, workspace, CFG)
    assert src.read_bytes() == data  # byte-for-byte, EXIF intact
    assert src.stat().st_mtime_ns == before_mtime
    assert result.sha256 == hashlib.sha256(data).hexdigest()
    with Image.open(src) as im:
        assert im.getexif()[0x010F] == "CameraMaker"


def test_hash_file_bounded_reads_at_most_limit_plus_one(tmp_path):
    p = write(tmp_path, "b.bin", b"x" * 1000)
    assert hash_file_bounded(p, 1000) == (hashlib.sha256(b"x" * 1000).hexdigest(), 1000)
    with pytest.raises(PhotoTooLargeError):
        hash_file_bounded(p, 999)


# --------------------------------------------------------------------------
# EXIF orientation, metadata stripping, colour, alpha
# --------------------------------------------------------------------------


def test_exif_orientation_applied_before_resize(tmp_path, workspace):
    exif = Image.Exif()
    exif[0x0112] = 6  # rotate 90° clockwise for display
    exif.get_ifd(0x8769)[0x9003] = "2026:09:28 10:11:12"
    # 3000x1000 stored, left half red / right half blue
    src = write(tmp_path, "rot.jpg", encode(half_image((3000, 1000)), "JPEG", exif=exif.tobytes(), quality=95))
    result = process_image_file(src, workspace, CFG)
    assert result.exif_orientation == 6
    assert (result.stored_width, result.stored_height) == (3000, 1000)
    assert (result.width, result.height) == (1000, 3000)
    assert (result.display.width, result.display.height) == (683, 2048)
    assert result.captured_at == datetime(2026, 9, 28, 10, 11, 12)
    im = assert_clean_jpeg(result.display.path)
    # After a 90° clockwise rotation, the stored left (red) half is on top.
    top = im.getpixel((im.width // 2, 10))
    bottom = im.getpixel((im.width // 2, im.height - 10))
    assert top[0] > 200 and top[2] < 60
    assert bottom[2] > 200 and bottom[0] < 60


def test_metadata_stripped_from_derivatives(tmp_path, workspace):
    exif = Image.Exif()
    exif[0x0112] = 1
    exif[0x010F] = "CameraMaker"
    exif.get_ifd(0x8825)[2] = (50.0, 3.0, 0.0)  # GPS latitude
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    data = encode(
        half_image(), "JPEG", exif=exif.tobytes(), icc_profile=icc, comment=b"secret note",
        xmp=b"<x:xmpmeta xmlns:x='adobe:ns:meta/'>private</x:xmpmeta>",
    )
    src = write(tmp_path, "meta.jpg", data)
    result = process_image_file(src, workspace, CFG)
    for derivative in (result.display, result.thumbnail):
        assert_clean_jpeg(derivative.path)
        raw = derivative.path.read_bytes()
        assert b"secret note" not in raw and b"private" not in raw and b"CameraMaker" not in raw


def test_icc_profile_converted_to_srgb(tmp_path, workspace):
    srgb_icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    src = write(tmp_path, "icc.png", encode(half_image(), "PNG", icc_profile=srgb_icc))
    result = process_image_file(src, workspace, CFG)
    im = assert_clean_jpeg(result.display.path)
    assert im.getpixel((10, 50))[0] > 200


def test_transparency_flattened_onto_white(tmp_path, workspace):
    im = Image.new("RGBA", (200, 100), (0, 0, 0, 0))
    im.paste(Image.new("RGBA", (100, 100), (0, 0, 255, 255)), (100, 0))
    src = write(tmp_path, "alpha.png", encode(im, "PNG"))
    result = process_image_file(src, workspace, CFG)
    out = assert_clean_jpeg(result.display.path)
    assert all(c >= 250 for c in out.getpixel((20, 50)))  # transparent -> #FFFFFF
    blue = out.getpixel((180, 50))
    assert blue[2] > 200 and blue[0] < 40


@pytest.mark.parametrize("mode", ["L", "LA", "P", "CMYK"])
def test_other_colour_modes_become_rgb(tmp_path, workspace, mode):
    im = Image.new("RGB", (120, 80), (200, 30, 30)).convert(mode)
    fmt = "JPEG" if mode in ("L", "CMYK") else "PNG"
    src = write(tmp_path, f"m.{fmt.lower()}", encode(im, fmt))
    result = process_image_file(src, workspace, CFG)
    assert_clean_jpeg(result.thumbnail.path)


# --------------------------------------------------------------------------
# Rejections
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name, data",
    [
        ("text.jpg", b"hello, this is plain text pretending to be a photo" * 10),
        ("page.jpg", b"<!doctype html><html><script>alert(1)</script></html>"),
        ("vector.jpg", b"<svg xmlns='http://www.w3.org/2000/svg'><rect width='10' height='10'/></svg>"),
        ("doc.jpg", b"%PDF-1.7\n1 0 obj << >> endobj\n%%EOF"),
        ("photo.heic", b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic" + b"\x00" * 64),
        ("photo.heif", b"\x00\x00\x00\x18ftypmif1\x00\x00\x00\x00mif1heix" + b"\x00" * 64),
    ],
)
def test_disguised_and_unsupported_files_rejected(tmp_path, workspace, name, data):
    with pytest.raises(PhotoUnsupportedFormatError):
        process_image_file(write(tmp_path, name, data), workspace, CFG)


@pytest.mark.parametrize("fmt", ["GIF", "BMP", "TIFF"])
def test_other_real_image_formats_rejected(tmp_path, workspace, fmt):
    src = write(tmp_path, "img.jpg", encode(half_image(), fmt))
    with pytest.raises(PhotoUnsupportedFormatError):
        process_image_file(src, workspace, CFG)


def test_empty_file_rejected(tmp_path, workspace):
    with pytest.raises(PhotoInvalidImageError):
        process_image_file(write(tmp_path, "e.jpg", b""), workspace, CFG)


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
def test_truncated_image_rejected(tmp_path, workspace, fmt):
    noisy = Image.effect_noise((400, 300), 80).convert("RGB")
    data = encode(noisy, fmt)
    src = write(tmp_path, "t.bin", data[: len(data) // 2])
    with pytest.raises(PhotoInvalidImageError):
        process_image_file(src, workspace, CFG)


def test_corrupted_jpeg_rejected(tmp_path, workspace):
    data = bytearray(encode(Image.effect_noise((200, 200), 80).convert("RGB"), "JPEG"))
    data[200:1200] = b"\xff" * 1000
    with pytest.raises((PhotoInvalidImageError, PhotoUnsupportedFormatError)):
        process_image_file(write(tmp_path, "c.jpg", bytes(data)), workspace, CFG)


def test_encoded_size_limit(tmp_path, workspace):
    data = encode(half_image(), "PNG")
    src = write(tmp_path, "big.png", data)
    with pytest.raises(PhotoTooLargeError):
        process_image_file(src, workspace, ImagePipelineConfig(max_encoded_bytes=len(data) - 1))
    assert process_image_file(src, workspace, ImagePipelineConfig(max_encoded_bytes=len(data))).byte_size == len(data)


def test_default_encoded_limit_is_25_000_000_bytes():
    assert ImagePipelineConfig.from_settings(Settings(_env_file=None)).max_encoded_bytes == 25_000_000


def test_decoded_pixel_limit_from_header_default_60_mp(tmp_path, workspace):
    # 8000 x 8000 = 64 MP > 60 MP (below Pillow's own warning threshold).
    src = write(tmp_path, "huge.png", png_header_only(8000, 8000))
    with pytest.raises(PhotoTooManyPixelsError):
        process_image_file(src, workspace, CFG)


def test_pixel_limit_just_inside_is_not_rejected_as_too_many_pixels(tmp_path, workspace):
    # 7745 x 7745 = 59.98 MP passes the header check; the fake body then fails decoding.
    src = write(tmp_path, "ok.png", png_header_only(7745, 7745))
    with pytest.raises(PhotoInvalidImageError):
        process_image_file(src, workspace, CFG)


def test_pillow_decompression_bomb_treated_as_rejection(tmp_path, workspace):
    # 20000 x 20000 = 400 MP: Pillow itself raises DecompressionBombError.
    src = write(tmp_path, "bomb.png", png_header_only(20000, 20000))
    with pytest.raises(PhotoTooManyPixelsError):
        process_image_file(src, workspace, ImagePipelineConfig(max_decoded_pixels=10**12, max_edge_pixels=10**6))


def test_explicit_pixel_limit_configurable(tmp_path, workspace):
    src = write(tmp_path, "p.png", encode(half_image((200, 100)), "PNG"))
    with pytest.raises(PhotoTooManyPixelsError):
        process_image_file(src, workspace, ImagePipelineConfig(max_decoded_pixels=19_999))


def test_max_edge_limit(tmp_path, workspace):
    src = write(tmp_path, "wide.png", png_header_only(12_001, 10))
    with pytest.raises(PhotoTooManyPixelsError):
        process_image_file(src, workspace, CFG)


def test_pillow_global_bomb_limit_not_modified(tmp_path, workspace):
    before = Image.MAX_IMAGE_PIXELS
    process_image_file(write(tmp_path, "x.png", encode(half_image(), "PNG")), workspace, CFG)
    assert Image.MAX_IMAGE_PIXELS == before


def test_animated_png_rejected(tmp_path, workspace):
    buf = io.BytesIO()
    half_image().save(buf, format="PNG", save_all=True, append_images=[half_image(left=(0, 255, 0))])
    with pytest.raises(PhotoAnimatedError):
        process_image_file(write(tmp_path, "a.png", buf.getvalue()), workspace, CFG)


def test_animated_webp_rejected(tmp_path, workspace):
    buf = io.BytesIO()
    half_image().save(buf, format="WEBP", save_all=True, append_images=[half_image(left=(0, 255, 0))])
    with pytest.raises(PhotoAnimatedError):
        process_image_file(write(tmp_path, "a.webp", buf.getvalue()), workspace, CFG)


def test_error_codes_are_stable():
    assert PhotoTooLargeError.code == "PHOTO_TOO_LARGE"
    assert PhotoTooManyPixelsError.code == "PHOTO_TOO_MANY_PIXELS"
    assert PhotoUnsupportedFormatError.code == "PHOTO_UNSUPPORTED_FORMAT"
    assert PhotoAnimatedError.code == "PHOTO_ANIMATED_NOT_SUPPORTED"
    assert PhotoInvalidImageError.code == "PHOTO_INVALID_IMAGE"
    assert PhotoProcessingBusyError.code == "PHOTO_PROCESSING_BUSY"


# --------------------------------------------------------------------------
# Concurrency guard (approved concurrency = 1)
# --------------------------------------------------------------------------


async def test_only_one_processing_operation_at_a_time(tmp_path):
    lock = threading.Lock()
    state = {"active": 0, "max": 0, "calls": 0}

    def fake(source, workspace, config):
        with lock:
            state["active"] += 1
            state["calls"] += 1
            state["max"] = max(state["max"], state["active"])
        time.sleep(0.05)
        with lock:
            state["active"] -= 1
        return "done"

    processor = ImageProcessor(CFG, wait_seconds=5, process_fn=fake)
    results = await asyncio.gather(*(processor.process(tmp_path, tmp_path) for _ in range(4)))
    assert results == ["done"] * 4
    assert state["calls"] == 4
    assert state["max"] == 1


async def test_wait_timeout_maps_to_busy_error(tmp_path):
    release = threading.Event()

    def slow(source, workspace, config):
        release.wait(5)
        return "first"

    processor = ImageProcessor(CFG, wait_seconds=0.05, process_fn=slow)
    first = asyncio.create_task(processor.process(tmp_path, tmp_path))
    await asyncio.sleep(0.02)
    with pytest.raises(PhotoProcessingBusyError):
        await processor.process(tmp_path, tmp_path)
    release.set()
    assert await first == "first"
    # Slot released afterwards: a new call succeeds.
    release.set()
    assert await processor.process(tmp_path, tmp_path) == "first"


async def test_slot_released_after_processing_error(tmp_path):
    calls = []

    def failing(source, workspace, config):
        calls.append(1)
        raise PhotoInvalidImageError("bad")

    processor = ImageProcessor(CFG, wait_seconds=0.1, process_fn=failing)
    for _ in range(2):
        with pytest.raises(PhotoInvalidImageError):
            await processor.process(tmp_path, tmp_path)
    assert len(calls) == 2


async def test_processing_runs_in_worker_thread_with_real_pipeline(tmp_path):
    src = write(tmp_path, "r.png", encode(half_image(), "PNG"))
    ws = tmp_path / "ws"
    ws.mkdir()
    processor = ImageProcessor(CFG, wait_seconds=1)
    result = await processor.process(src, ws)
    assert result.format is PhotoFormat.PNG


def test_wait_seconds_must_be_positive():
    with pytest.raises(ValueError):
        ImageProcessor(CFG, wait_seconds=0)


def test_mpo_uses_first_frame_only_and_keeps_original(tmp_path, workspace):
    """Phone-camera compatibility path: MPO container -> canonical JPEG, first frame only."""
    from app.domain.photos.keys import build_photo_object_keys
    import uuid

    primary = Image.new("RGB", (400, 200), (255, 0, 0))
    secondary = Image.new("RGB", (100, 300), (0, 0, 255))
    buf = io.BytesIO()
    primary.save(buf, format="MPO", save_all=True, append_images=[secondary])
    data = buf.getvalue()
    src = write(tmp_path, "IMG_0001.jpg", data)
    with Image.open(src) as probe:
        assert probe.format == "MPO" and getattr(probe, "n_frames", 1) == 2
    result = process_image_file(src, workspace, CFG)
    assert result.format is PhotoFormat.JPEG
    assert result.extension == "jpg" and result.content_type == "image/jpeg"
    assert (result.width, result.height) == (400, 200)
    assert src.read_bytes() == data and result.sha256 == hashlib.sha256(data).hexdigest()
    assert build_photo_object_keys(uuid.uuid4(), result.format).original.endswith("/original.jpg")
    for derivative in (result.display, result.thumbnail):
        with Image.open(derivative.path) as out:
            assert out.format == "JPEG" and getattr(out, "n_frames", 1) == 1
            assert not getattr(out, "is_animated", False)
            pixel = out.convert("RGB").getpixel((out.width // 2, out.height // 2))
            assert pixel[0] > 200 and pixel[2] < 60  # red first frame, not the blue second one
            assert "mp" not in out.info and "mpoffset" not in out.info
