"""Stage 14B.3 — immutable object keys (14B.1 R1)."""

import inspect
import uuid

import pytest

from app.domain.photos.keys import PhotoFormat, build_photo_object_keys

ASSET = uuid.UUID("3f2b8c1e-9d4a-4f6b-8e2a-1c5d7e9f0a1b")


@pytest.mark.parametrize(
    "fmt, ext", [(PhotoFormat.JPEG, "jpg"), (PhotoFormat.PNG, "png"), (PhotoFormat.WEBP, "webp")]
)
def test_all_variants(fmt, ext):
    keys = build_photo_object_keys(ASSET, fmt)
    assert keys.original == f"photos/v1/{ASSET}/original.{ext}"
    assert keys.display == f"photos/v1/{ASSET}/display.jpg"
    assert keys.thumbnail == f"photos/v1/{ASSET}/thumb.jpg"


def test_uuid_rendered_lowercase_canonical():
    upper = uuid.UUID(str(ASSET).upper())
    assert build_photo_object_keys(upper, PhotoFormat.PNG).original == f"photos/v1/{ASSET}/original.png"


@pytest.mark.parametrize(
    "bad",
    [str(ASSET), "../../etc/passwd", None, 42, uuid.uuid1(), uuid.UUID(int=0)],
)
def test_invalid_asset_id_rejected(bad):
    with pytest.raises(ValueError):
        build_photo_object_keys(bad, PhotoFormat.JPEG)


@pytest.mark.parametrize("bad", ["JPEG", "jpg", "heic", "gif", None, "image/jpeg"])
def test_invalid_format_rejected(bad):
    with pytest.raises(ValueError):
        build_photo_object_keys(ASSET, bad)


def test_builder_accepts_no_user_controlled_names():
    params = list(inspect.signature(build_photo_object_keys).parameters)
    assert params == ["asset_id", "validated_format"]
    with pytest.raises(TypeError):
        build_photo_object_keys(ASSET, PhotoFormat.JPEG, filename="evil.png")  # type: ignore[call-arg]


def test_keys_depend_only_on_uuid_and_decoded_format():
    other = uuid.uuid4()
    a = build_photo_object_keys(other, PhotoFormat.WEBP)
    b = build_photo_object_keys(other, PhotoFormat.WEBP)
    assert a == b
    for key in (a.original, a.display, a.thumbnail):
        assert key.startswith(f"photos/v1/{other}/")
        assert ".." not in key and " " not in key
