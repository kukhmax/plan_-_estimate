"""Photo annotation: a point marker on one photo attachment (Stage 14G.1).

Canonical design: docs/STAGE_14_PHOTO_FIXATION_ARCHITECTURE.md §6.4, §15.4 (D14-9 .. D14-11, D14-15) and
docs/STAGE_14G_POINT_ANNOTATIONS_PLAN_RU.md.

A marker only says WHERE on the picture something is: `x` / `y` are fractions of the correctly oriented display
image (origin top-left, `x` to the right, `y` down, both 0..1), independent of screen size, thumbnail and PDF.
It carries no defect data (no finding, severity, status or category) -- the defect is the inspection finding the
photo is attached to. The marker belongs to the ATTACHMENT, so the same image attached to two places has two
independent marker sets.

Markers are presentation data: they may be hard-deleted (the photo is untouched). `attachment_id` is CASCADE
because a marker has no meaning without its attachment (attachments themselves are archived, never deleted).
"""
import enum
import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Uuid,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PhotoAnnotationKind(str, enum.Enum):
    POINT = "POINT"  # v1; rectangle / freehand / arrow / text tools are not planned


MAX_ANNOTATIONS_PER_ATTACHMENT = 10  # owner decision Q1 (2026-10-08)
MAX_LABEL_LENGTH = 40

ANNOTATION_CHECKS: tuple[tuple[str, str], ...] = (
    ("ck_photo_annotations_x_range", "x >= 0 AND x <= 1"),
    ("ck_photo_annotations_y_range", "y >= 0 AND y <= 1"),
    ("ck_photo_annotations_position_nonneg", "position >= 0"),
)


class PhotoAnnotation(Base):
    __tablename__ = "photo_annotations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    attachment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("photo_attachments.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[PhotoAnnotationKind] = mapped_column(
        Enum(PhotoAnnotationKind, name="photoannotationkind"), nullable=False, default=PhotoAnnotationKind.POINT
    )
    # numeric(7, 6): six decimals are enough for a point on a phone photo; the service rounds to them.
    x: Mapped[float] = mapped_column(Numeric(7, 6, asdecimal=False), nullable=False)
    y: Mapped[float] = mapped_column(Numeric(7, 6, asdecimal=False), nullable=False)
    label: Mapped[str | None] = mapped_column(String(MAX_LABEL_LENGTH), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    __table_args__ = (
        *(CheckConstraint(sql, name=name) for name, sql in ANNOTATION_CHECKS),
        Index("ix_photo_annotations_attachment_position", "attachment_id", "position"),
    )
