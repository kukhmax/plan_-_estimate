"""Immutable photo media asset (Stage 14B.4).

One row describes one stored image and its three objects (original,
display, thumbnail). It carries the file facts only; business context
(room/surface/inspection/finding/work, caption, category, report inclusion,
annotations) belongs to later attachment/annotation layers (14C+).

Identity: `id` is the client-generated upload UUIDv4 -- the idempotency key
and the `{asset_uuid}` segment of every storage key. Keys are durable
identity; URLs (signed or public) are delivery details and are never stored.

State (14A §8): image decode, validation, derivatives and SHA-256 all happen
BEFORE the row is inserted, so every row -- including PENDING -- carries
complete media metadata. PENDING means "processed locally, durable storage
not yet finalized"; READY means all three objects were stored; FAILED means
storage finalization failed (a retry with the same id may resume).

Timestamps:
- `captured_at`: EXIF DateTimeOriginal, camera-local wall time, timezone
  UNKNOWN. Stored as TIMESTAMP WITHOUT TIME ZONE and never converted to UTC.
- `uploaded_at`, `created_at`, `updated_at`, `archived_at`: server time,
  timezone-aware UTC.

`storage_name` is the logical storage identity (MEDIA_STORAGE_NAME, e.g.
"r2-primary"), not the adapter implementation ("s3"): several logical
stores may share one adapter type.

See docs/STAGE_14_PHOTO_FIXATION_ARCHITECTURE.md §15.1 and
docs/STAGE_14B_MEDIA_INFRASTRUCTURE_PLAN.md §24.
"""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PhotoAssetStatus(str, enum.Enum):
    PENDING = "PENDING"
    READY = "READY"
    FAILED = "FAILED"


class PhotoContentType(str, enum.Enum):
    JPEG = "image/jpeg"
    PNG = "image/png"
    WEBP = "image/webp"


class PhotoCaptureSource(str, enum.Enum):
    """How the client says the file entered the app (Stage 14E.2, owner decision D11 = A).

    `CAMERA`: chosen with the in-app "take a photo" button; `GALLERY`: chosen from the
    gallery / file picker. **Declared by the client, informational, never proof**: the server
    cannot verify it (some phones answer the camera button with the gallery). NULL = unknown
    (every photo uploaded before the column existed, and clients that do not send it)."""

    CAMERA = "CAMERA"
    GALLERY = "GALLERY"


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class PhotoAsset(Base):
    __tablename__ = "photo_assets"

    # = client upload UUIDv4 (idempotency identity, storage-key segment).
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    # Evidence must not vanish through a cascade (14A §15.1).
    owner_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("projects.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[PhotoAssetStatus] = mapped_column(
        Enum(PhotoAssetStatus, name="photoassetstatus"), nullable=False
    )
    storage_name: Mapped[str] = mapped_column(String(40), nullable=False)
    storage_key_original: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key_display: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key_thumbnail: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[PhotoContentType] = mapped_column(
        Enum(PhotoContentType, name="photocontenttype", values_callable=_enum_values),
        nullable=False,
    )
    # Original object size; storage bytes = byte_size + display + thumbnail.
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    display_byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    thumbnail_byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Dimensions AFTER EXIF orientation.
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    # Lowercase hex SHA-256 of the canonical original; deliberately not unique.
    sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    original_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Camera-local, timezone unknown -- see module docstring.
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), nullable=True)
    # Client-declared entry path, informational only (see PhotoCaptureSource); VARCHAR + CHECK,
    # not a native enum, so the column is trivially reversible.
    capture_source: Mapped[PhotoCaptureSource | None] = mapped_column(
        Enum(PhotoCaptureSource, native_enum=False, length=16, create_constraint=False, values_callable=_enum_values),
        nullable=True,
    )
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("uq_photo_assets_storage_key_original", "storage_key_original", unique=True),
        Index("uq_photo_assets_storage_key_display", "storage_key_display", unique=True),
        Index("uq_photo_assets_storage_key_thumbnail", "storage_key_thumbnail", unique=True),
        Index("ix_photo_assets_project_status_archived", "project_id", "status", "archived_at"),
        Index("ix_photo_assets_status_created", "status", "created_at"),
        Index("ix_photo_assets_owner_status", "owner_id", "status"),
        CheckConstraint("byte_size > 0", name="ck_photo_assets_byte_size_positive"),
        CheckConstraint("display_byte_size > 0", name="ck_photo_assets_display_byte_size_positive"),
        CheckConstraint("thumbnail_byte_size > 0", name="ck_photo_assets_thumbnail_byte_size_positive"),
        CheckConstraint("width > 0 AND height > 0", name="ck_photo_assets_dimensions_positive"),
        CheckConstraint("length(trim(storage_name)) > 0", name="ck_photo_assets_storage_name_nonempty"),
        CheckConstraint(
            "capture_source IS NULL OR capture_source IN ('CAMERA', 'GALLERY')",
            name="ck_photo_assets_capture_source",
        ),
        CheckConstraint(
            "length(storage_key_original) > 0 AND length(storage_key_display) > 0"
            " AND length(storage_key_thumbnail) > 0",
            name="ck_photo_assets_storage_keys_nonempty",
        ),
        # Portable (SQLite + PostgreSQL): 64 chars, lowercase.
        CheckConstraint(
            "length(sha256) = 64 AND sha256 = lower(sha256)",
            name="ck_photo_assets_sha256_format",
        ),
        # PostgreSQL only: strictly lowercase hexadecimal.
        CheckConstraint(
            "sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_photo_assets_sha256_hex",
        ).ddl_if(dialect="postgresql"),
    )
