"""Point markers on photo attachments (Stage 14G.1).

Canonical design: docs/STAGE_14_PHOTO_FIXATION_ARCHITECTURE.md §6.4 and docs/STAGE_14G_POINT_ANNOTATIONS_PLAN_RU.md.

A marker is only a place on the picture (normalized x / y of the display image) with an optional short label and an
optional freehand contour around the defect (14G.4).
Rules:
  * owner -> project -> attachment of a READY asset, exactly as every other photo operation (foreign / missing
    -> the same not-found);
  * markers are changed only on an ACTIVE attachment of an ACTIVE asset; an archived one can only be read, so
    archive -> restore returns the very same markers;
  * at most MAX_ANNOTATIONS_PER_ATTACHMENT per attachment (checked under a row lock on the attachment so two
    simultaneous requests cannot both pass the check);
  * `position` is assigned by the server (after the last marker); markers are never reordered or moved
    (owner decision Q5): a wrong marker is deleted and placed again;
  * a marker can be deleted for good (presentation data); the photo is untouched.
"""
import math
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import (
    PhotoAnnotationLimitReachedError,
    PhotoAnnotationNotFoundError,
    PhotoAnnotationReadOnlyError,
    PhotoAnnotationValidationError,
)
from app.domain.services.photo_attachment_service import PhotoAttachmentService
from app.models.photo_annotation import (
    MAX_ANNOTATIONS_PER_ATTACHMENT,
    MAX_LABEL_LENGTH,
    MAX_OUTLINE_POINTS,
    MIN_OUTLINE_POINTS,
    PhotoAnnotation,
    PhotoAnnotationKind,
)
from app.models.photo_asset import PhotoAsset, PhotoAssetStatus
from app.models.photo_attachment import PhotoAttachment

_UNSET: Any = object()
COORDINATE_DECIMALS = 6


def normalize_coordinate(value: Any, name: str) -> float:
    """A real number 0..1 (bool, text, NaN and infinity are rejected), rounded to the stored precision."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PhotoAnnotationValidationError(f"{name} must be a number")
    number = float(value)
    if not math.isfinite(number) or number < 0.0 or number > 1.0:
        raise PhotoAnnotationValidationError(f"{name} must be between 0 and 1")
    return round(number, COORDINATE_DECIMALS)


def normalize_label(label: Any) -> str | None:
    if label is None:
        return None
    if not isinstance(label, str):
        raise PhotoAnnotationValidationError("label must be text")
    cleaned = label.strip()
    if len(cleaned) > MAX_LABEL_LENGTH:
        raise PhotoAnnotationValidationError(f"label must be at most {MAX_LABEL_LENGTH} characters")
    return cleaned or None


def normalize_outline(outline: Any) -> list[list[float]] | None:
    """A contour: 3..120 points, each [x, y] with numbers 0..1 (rounded like a marker's own x / y); None = no contour.
    All points identical is a dot, not a contour."""
    if outline is None:
        return None
    if not isinstance(outline, (list, tuple)):
        raise PhotoAnnotationValidationError("outline must be a list of points")
    if not MIN_OUTLINE_POINTS <= len(outline) <= MAX_OUTLINE_POINTS:
        raise PhotoAnnotationValidationError(
            f"outline must have between {MIN_OUTLINE_POINTS} and {MAX_OUTLINE_POINTS} points"
        )
    points: list[list[float]] = []
    for point in outline:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            raise PhotoAnnotationValidationError("an outline point must be [x, y]")
        points.append([normalize_coordinate(point[0], "x"), normalize_coordinate(point[1], "y")])
    if len({(x, y) for x, y in points}) < 2:
        raise PhotoAnnotationValidationError("outline must not be a single point")
    return points


class PhotoAnnotationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self._attachments = PhotoAttachmentService(db)

    # -- reads ------------------------------------------------------------------

    async def list_for_attachment(
        self, owner_id: uuid.UUID, project_id: uuid.UUID, attachment_id: uuid.UUID
    ) -> list[PhotoAnnotation]:
        """Markers of one attachment (archived ones included), in display order."""
        await self._attachments.get_attachment(owner_id, project_id, attachment_id)
        return await self._markers(attachment_id)

    async def list_for_attachments(self, attachment_ids: Sequence[uuid.UUID]) -> list[PhotoAnnotation]:
        """Markers of already authorized attachments (detail view), in display order per attachment."""
        if not attachment_ids:
            return []
        stmt = (
            select(PhotoAnnotation)
            .where(PhotoAnnotation.attachment_id.in_(list(attachment_ids)))
            .order_by(PhotoAnnotation.attachment_id, *_ORDER)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def counts_for_attachments(self, attachment_ids: Sequence[uuid.UUID]) -> dict[uuid.UUID, int]:
        """Marker count per attachment for a list page (attachments without markers are absent)."""
        if not attachment_ids:
            return {}
        stmt = (
            select(PhotoAnnotation.attachment_id, func.count(PhotoAnnotation.id))
            .where(PhotoAnnotation.attachment_id.in_(list(attachment_ids)))
            .group_by(PhotoAnnotation.attachment_id)
        )
        return {attachment_id: count for attachment_id, count in (await self.db.execute(stmt)).all()}

    # -- writes -----------------------------------------------------------------

    async def create(
        self,
        owner_id: uuid.UUID,
        project_id: uuid.UUID,
        attachment_id: uuid.UUID,
        *,
        x: Any,
        y: Any,
        label: Any = None,
    ) -> PhotoAnnotation:
        x_value = normalize_coordinate(x, "x")
        y_value = normalize_coordinate(y, "y")
        label_value = normalize_label(label)
        attachment = await self._writable_attachment(owner_id, project_id, attachment_id, lock=True)
        count, last_position = (
            await self.db.execute(
                select(func.count(PhotoAnnotation.id), func.max(PhotoAnnotation.position)).where(
                    PhotoAnnotation.attachment_id == attachment.id
                )
            )
        ).one()
        if count >= MAX_ANNOTATIONS_PER_ATTACHMENT:
            await self.db.rollback()
            raise PhotoAnnotationLimitReachedError("the photo already has the maximum number of markers")
        marker = PhotoAnnotation(
            attachment_id=attachment.id,
            kind=PhotoAnnotationKind.POINT,
            x=x_value,
            y=y_value,
            label=label_value,
            position=0 if last_position is None else last_position + 1,
        )
        self.db.add(marker)
        await self.db.commit()
        await self.db.refresh(marker)
        return marker

    async def update(
        self,
        owner_id: uuid.UUID,
        project_id: uuid.UUID,
        attachment_id: uuid.UUID,
        annotation_id: uuid.UUID,
        *,
        label: Any = _UNSET,
        outline: Any = _UNSET,
    ) -> PhotoAnnotation:
        """The editable fields are the label and the contour (coordinates and order never change, Q5): a new contour
        replaces the old one, `None` removes it."""
        label_value = normalize_label(label) if label is not _UNSET else _UNSET
        outline_value = normalize_outline(outline) if outline is not _UNSET else _UNSET
        await self._writable_attachment(owner_id, project_id, attachment_id)
        marker = await self._get_marker(attachment_id, annotation_id)
        if label_value is not _UNSET:
            marker.label = label_value
        if outline_value is not _UNSET:
            marker.outline = outline_value
        await self.db.commit()
        await self.db.refresh(marker)
        return marker

    async def delete(
        self,
        owner_id: uuid.UUID,
        project_id: uuid.UUID,
        attachment_id: uuid.UUID,
        annotation_id: uuid.UUID,
    ) -> None:
        await self._writable_attachment(owner_id, project_id, attachment_id)
        marker = await self._get_marker(attachment_id, annotation_id)
        await self.db.delete(marker)
        await self.db.commit()

    # -- helpers ----------------------------------------------------------------

    async def _writable_attachment(
        self, owner_id: uuid.UUID, project_id: uuid.UUID, attachment_id: uuid.UUID, *, lock: bool = False
    ) -> PhotoAttachment:
        attachment = await self._attachments.get_attachment(owner_id, project_id, attachment_id)
        if lock:
            # Serializes concurrent creates on PostgreSQL (SQLite ignores FOR UPDATE).
            await self.db.execute(
                select(PhotoAttachment.id).where(PhotoAttachment.id == attachment.id).with_for_update()
            )
            await self.db.refresh(attachment)
        asset_archived = (
            await self.db.execute(
                select(PhotoAsset.archived_at).where(
                    PhotoAsset.id == attachment.asset_id, PhotoAsset.status == PhotoAssetStatus.READY
                )
            )
        ).scalar_one_or_none()
        if attachment.archived_at is not None or asset_archived is not None:
            raise PhotoAnnotationReadOnlyError("markers of an archived photo cannot be changed")
        return attachment

    async def _get_marker(self, attachment_id: uuid.UUID, annotation_id: uuid.UUID) -> PhotoAnnotation:
        marker = (
            await self.db.execute(
                select(PhotoAnnotation).where(
                    PhotoAnnotation.id == annotation_id, PhotoAnnotation.attachment_id == attachment_id
                )
            )
        ).scalar_one_or_none()
        if marker is None:
            raise PhotoAnnotationNotFoundError("photo marker not found")
        return marker

    async def _markers(self, attachment_id: uuid.UUID) -> list[PhotoAnnotation]:
        stmt = select(PhotoAnnotation).where(PhotoAnnotation.attachment_id == attachment_id).order_by(*_ORDER)
        return list((await self.db.execute(stmt)).scalars().all())


_ORDER = (PhotoAnnotation.position, PhotoAnnotation.created_at, PhotoAnnotation.id)
