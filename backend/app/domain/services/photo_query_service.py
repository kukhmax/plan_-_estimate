"""Photo read model (Stage 14C.5): list with keyset pagination and asset
detail. Canonical contract: docs/STAGE_14C_MEDIA_API_CONTRACT.md §16–§18,
§21, §11c.

Visibility (§18):
- archived=False (normal view): active attachment AND non-archived asset.
- archived=True (archive view): archived attachment OR archived asset --
  the restorable items, NOT a superset of the normal view.
Always READY assets only, and always the full ownership chain
(attachment.project_id = asset.project_id = project, asset.owner_id = owner),
even though the foreign keys should already guarantee it.

Ordering is (attachment.position, asset.uploaded_at, attachment.id), and the
same tuple continues a page. The cursor is opaque API state: base64url JSON
with a version, the last row's ordering tuple and a fingerprint of the
filter set it was issued for. It is strictly validated and never trusted
for anything but those typed values (no SQL fragments, no field names, no
executable serialization).
"""

import base64
import binascii
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.domain.exceptions import PhotoAttachmentValidationError, PhotoCursorInvalidError
from app.domain.services.photo_asset_service import PhotoAssetService
from app.domain.services.photo_attachment_service import AttachmentTarget, PhotoAttachmentService
from app.domain.services.project_service import ProjectService
from app.models.photo_asset import PhotoAsset, PhotoAssetStatus
from app.models.photo_attachment import PhotoAttachment, PhotoAttachmentContext, PhotoCategory

DEFAULT_LIMIT = 30
MAX_LIMIT = 100
CURSOR_VERSION = 1
_CURSOR_KEYS = {"v", "p", "u", "i", "f"}


@dataclass(frozen=True)
class PhotoListFilters:
    context: PhotoAttachmentContext | None = None
    room_id: uuid.UUID | None = None
    surface_id: uuid.UUID | None = None
    opening_id: uuid.UUID | None = None
    category: PhotoCategory | None = None
    include_in_report: bool | None = None
    archived: bool = False

    def fingerprint(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> str:
        canonical = json.dumps(
            [
                str(owner_id), str(project_id),
                self.context.value if self.context else None,
                str(self.room_id) if self.room_id else None,
                str(self.surface_id) if self.surface_id else None,
                str(self.opening_id) if self.opening_id else None,
                self.category.value if self.category else None,
                self.include_in_report,
                self.archived,
            ],
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode()).hexdigest()[:32]


@dataclass(frozen=True)
class PhotoListPage:
    items: list[tuple[PhotoAttachment, PhotoAsset]]
    next_cursor: str | None


@dataclass(frozen=True)
class _CursorPosition:
    position: int
    uploaded_at: datetime
    attachment_id: uuid.UUID


def encode_cursor(attachment: PhotoAttachment, asset: PhotoAsset, fingerprint: str) -> str:
    payload = {
        "v": CURSOR_VERSION,
        "p": attachment.position,
        "u": asset.uploaded_at.isoformat(),
        "i": str(attachment.id),
        "f": fingerprint,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def decode_cursor(cursor: str, fingerprint: str) -> _CursorPosition:
    """Strict decoding; anything unexpected -> PhotoCursorInvalidError."""
    invalid = PhotoCursorInvalidError("invalid cursor")
    if not cursor or len(cursor) > 512 or not all(c.isalnum() or c in "-_" for c in cursor):
        raise invalid
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
        payload = json.loads(raw)
    except (binascii.Error, ValueError, UnicodeDecodeError):
        raise invalid from None
    if not isinstance(payload, dict) or set(payload) != _CURSOR_KEYS:
        raise invalid
    version, position, uploaded, attachment_id, cursor_fingerprint = (
        payload["v"], payload["p"], payload["u"], payload["i"], payload["f"]
    )
    if type(version) is not int or version != CURSOR_VERSION:
        raise invalid
    if type(position) is not int or position < 0:
        raise invalid
    if not isinstance(uploaded, str) or not isinstance(attachment_id, str) or not isinstance(cursor_fingerprint, str):
        raise invalid
    if cursor_fingerprint != fingerprint:
        raise invalid  # issued for another filter set (or another owner / project)
    try:
        uploaded_at = datetime.fromisoformat(uploaded)
        parsed_id = uuid.UUID(attachment_id)
    except ValueError:
        raise invalid from None
    return _CursorPosition(position=position, uploaded_at=uploaded_at, attachment_id=parsed_id)


def _after(cursor: _CursorPosition) -> ColumnElement[bool]:
    """Row strictly after the cursor in (position, uploaded_at, id) order."""
    return or_(
        PhotoAttachment.position > cursor.position,
        and_(
            PhotoAttachment.position == cursor.position,
            or_(
                PhotoAsset.uploaded_at > cursor.uploaded_at,
                and_(PhotoAsset.uploaded_at == cursor.uploaded_at, PhotoAttachment.id > cursor.attachment_id),
            ),
        ),
    )


class PhotoQueryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _validate_filters(
        self, owner_id: uuid.UUID, project_id: uuid.UUID, filters: PhotoListFilters
    ) -> None:
        await ProjectService(self.db).get_project(project_id, owner_id)
        if filters.context is None:
            if filters.room_id or filters.surface_id or filters.opening_id:
                raise PhotoAttachmentValidationError("a target id requires a matching context")
            return
        # Same shape + ownership-chain validation as attach/upload (C12: archived
        # targets are accepted; unsupported contexts are rejected).
        await PhotoAttachmentService(self.db).validate_target(
            owner_id,
            project_id,
            AttachmentTarget(
                context=filters.context,
                room_id=filters.room_id,
                surface_id=filters.surface_id,
                opening_id=filters.opening_id,
            ),
        )

    async def list_photos(
        self,
        owner_id: uuid.UUID,
        project_id: uuid.UUID,
        filters: PhotoListFilters,
        *,
        limit: int = DEFAULT_LIMIT,
        cursor: str | None = None,
    ) -> PhotoListPage:
        if not 1 <= limit <= MAX_LIMIT:
            raise PhotoAttachmentValidationError(f"limit must be between 1 and {MAX_LIMIT}")
        await self._validate_filters(owner_id, project_id, filters)
        fingerprint = filters.fingerprint(owner_id, project_id)
        position = decode_cursor(cursor, fingerprint) if cursor is not None else None

        stmt = (
            select(PhotoAttachment, PhotoAsset)
            .join(PhotoAsset, PhotoAttachment.asset_id == PhotoAsset.id)
            .where(
                PhotoAttachment.project_id == project_id,
                PhotoAsset.project_id == project_id,
                PhotoAsset.owner_id == owner_id,
                PhotoAsset.status == PhotoAssetStatus.READY,
            )
        )
        if filters.archived:
            stmt = stmt.where(or_(PhotoAttachment.archived_at.is_not(None), PhotoAsset.archived_at.is_not(None)))
        else:
            stmt = stmt.where(PhotoAttachment.archived_at.is_(None), PhotoAsset.archived_at.is_(None))
        if filters.context is not None:
            stmt = stmt.where(PhotoAttachment.context == filters.context)
            if filters.room_id is not None:
                stmt = stmt.where(PhotoAttachment.room_id == filters.room_id)
            if filters.surface_id is not None:
                stmt = stmt.where(PhotoAttachment.surface_id == filters.surface_id)
            if filters.opening_id is not None:
                stmt = stmt.where(PhotoAttachment.opening_id == filters.opening_id)
        if filters.category is not None:
            stmt = stmt.where(PhotoAttachment.category == filters.category)
        if filters.include_in_report is not None:
            stmt = stmt.where(PhotoAttachment.include_in_report == filters.include_in_report)
        if position is not None:
            stmt = stmt.where(_after(position))
        stmt = stmt.order_by(PhotoAttachment.position, PhotoAsset.uploaded_at, PhotoAttachment.id).limit(limit + 1)

        rows = [(row[0], row[1]) for row in (await self.db.execute(stmt)).all()]
        page = rows[:limit]
        next_cursor = encode_cursor(*page[-1], fingerprint) if len(rows) > limit else None
        return PhotoListPage(items=page, next_cursor=next_cursor)

    async def get_detail(
        self, owner_id: uuid.UUID, project_id: uuid.UUID, asset_id: uuid.UUID
    ) -> tuple[PhotoAsset, list[PhotoAttachment]]:
        """READY asset of this owner and project (archived included) with all
        its attachments of this project, archived ones included, in creation
        order (the first one is the upload's first attachment)."""
        await ProjectService(self.db).get_project(project_id, owner_id)
        asset = await PhotoAssetService(self.db).get_ready(asset_id, owner_id, project_id)
        stmt = (
            select(PhotoAttachment)
            .where(PhotoAttachment.asset_id == asset.id, PhotoAttachment.project_id == project_id)
            .order_by(PhotoAttachment.created_at, PhotoAttachment.id)
        )
        return asset, list((await self.db.execute(stmt)).scalars().all())
