"""Immutable photo object keys (Stage 14B.3, 14B.1 R1 — OWNER APPROVED).

Layout::

    photos/v1/{asset_uuid}/original.{validated_extension}
    photos/v1/{asset_uuid}/display.jpg
    photos/v1/{asset_uuid}/thumb.jpg

Keys are built only from the asset UUID and the format established by
decoding the image. The builder deliberately accepts nothing else: client
filenames, browser MIME types and client/project/room/surface labels or
captions can never influence storage identity.
"""

import uuid
from dataclasses import dataclass
from enum import StrEnum

PHOTO_KEY_PREFIX = "photos/v1/"


class PhotoFormat(StrEnum):
    """Validated (decoded) image formats accepted in Stage 14 v1."""

    JPEG = "JPEG"
    PNG = "PNG"
    WEBP = "WEBP"


ORIGINAL_EXTENSIONS: dict[PhotoFormat, str] = {
    PhotoFormat.JPEG: "jpg",
    PhotoFormat.PNG: "png",
    PhotoFormat.WEBP: "webp",
}

ORIGINAL_CONTENT_TYPES: dict[PhotoFormat, str] = {
    PhotoFormat.JPEG: "image/jpeg",
    PhotoFormat.PNG: "image/png",
    PhotoFormat.WEBP: "image/webp",
}

DERIVATIVE_CONTENT_TYPE = "image/jpeg"


@dataclass(frozen=True)
class PhotoObjectKeys:
    original: str
    display: str
    thumbnail: str


def build_photo_object_keys(asset_id: uuid.UUID, validated_format: PhotoFormat) -> PhotoObjectKeys:
    """Return the three immutable keys for one photo asset.

    `asset_id` must be a UUIDv4 instance (the client upload_id); strings are
    refused so no caller can smuggle path segments through it.
    `validated_format` must come from the image pipeline, never from the client.
    """
    if not isinstance(asset_id, uuid.UUID) or asset_id.version != 4:
        raise ValueError("asset_id must be a UUIDv4")
    if not isinstance(validated_format, PhotoFormat):
        raise ValueError("validated_format must be a PhotoFormat")
    base = f"{PHOTO_KEY_PREFIX}{asset_id}/"  # str(UUID) is canonical lowercase
    return PhotoObjectKeys(
        original=f"{base}original.{ORIGINAL_EXTENSIONS[validated_format]}",
        display=f"{base}display.jpg",
        thumbnail=f"{base}thumb.jpg",
    )
