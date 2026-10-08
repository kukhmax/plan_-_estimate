"""Photo endpoints: upload (Stage 14C.4) and reads / metadata / archive (Stage 14C.5).

Canonical contract: docs/STAGE_14C_MEDIA_API_CONTRACT.md §9–§11, §14, §17,
§19–§21 (incl. the 14C.4 refinements in §11b).

The route takes `Request` and only header-level dependencies (no File()/
Form() parameters), so FastAPI never parses the body on its own. Pipeline:

  auth -> upload gate -> Content-Length early check -> project ownership
  -> admission slot -> stale temp sweep -> byte-counting receive guard
  -> strict multipart parsing -> bounded copy into a workspace -> close the
  multipart spool -> PhotoUploadService -> presign display/thumbnail
  -> response; workspace removal and admission release in `finally`.

Errors use the project envelope `{"detail": {"code", "message"}}` with
fixed messages: no storage keys, sha256, paths, provider details or traces.
"""

import logging
import math
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import NoReturn

import anyio
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from python_multipart.exceptions import FormParserError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import ClientDisconnect

from app.api import upload_guard
from app.api.deps import PhotoRuntime, get_current_user, get_photo_runtime
from app.api.upload_guard import (
    RequestBodyIdleTimeoutError,
    RequestBodyTooLargeError,
    copy_bounded,
    limited_receive,
    parse_content_length,
    sweep_stale_photo_temp,
)
from app.core.config import settings
from app.core.database import get_db
from app.domain.exceptions import (
    ChecklistQuestionNotFoundError,
    InspectionFindingNotFoundError,
    InspectionNotFoundError,
    MediaObjectConflict,
    MediaStorageDisabled,
    MediaStorageError,
    MediaStorageUnavailable,
    OpeningNotFoundError,
    PhotoAnnotationLimitReachedError,
    PhotoAnnotationNotFoundError,
    PhotoAnnotationReadOnlyError,
    PhotoAnnotationValidationError,
    PhotoAssetNotFoundError,
    PhotoAttachmentDuplicateError,
    PhotoAttachmentNotFoundError,
    PhotoAttachmentValidationError,
    PhotoContextNotSupportedError,
    PhotoCursorInvalidError,
    PhotoProcessingBusyError,
    PhotoStorageQuotaExceededError,
    PhotoTooLargeError,
    PhotoUnsupportedFormatError,
    PhotoUploadIdConflictError,
    PhotoUploadMalformedError,
    PhotoUploadResumeMismatchError,
    PhotoUploadsDisabledError,
    PhotoValidationError,
    PhotoWorkOccurrenceNotCurrentError,
    ProjectNotFoundError,
    RoomNotFoundError,
    SurfaceNotFoundError,
)
from app.domain.photos.temp import photo_workspace
from app.domain.services.media_storage import MediaStorage
from app.domain.services.photo_annotation_service import PhotoAnnotationService
from app.domain.services.photo_asset_service import PhotoAssetService
from app.domain.services.photo_attachment_service import (
    AttachmentTarget,
    PhotoAttachmentService,
)
from app.domain.services.photo_query_service import (
    DEFAULT_LIMIT,
    MAX_LIMIT,
    PhotoListFilters,
    PhotoQueryService,
)
from app.domain.services.photo_quota import logical_usage_bytes, storage_state
from app.domain.services.photo_upload_service import (
    PhotoUploadConfig,
    PhotoUploadRequest,
    PhotoUploadResult,
    PhotoUploadService,
    parse_upload_id,
)
from app.domain.services.project_service import ProjectService
from app.models.photo_asset import PhotoCaptureSource
from app.models.photo_attachment import PhotoAttachmentContext, PhotoCategory
from app.models.user import User
from app.schemas.photo import (
    PhotoAnnotationCreate,
    PhotoAnnotationListResponse,
    PhotoAnnotationPatch,
    PhotoAnnotationRead,
    PhotoAssetRead,
    PhotoAttachmentPatch,
    PhotoAttachmentRead,
    PhotoAttachRequest,
    PhotoCountsResponse,
    PhotoDetailResponse,
    PhotoListItem,
    PhotoListResponse,
    PhotoStorageRead,
    PhotoStorageStatus,
    PhotoUploadResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Multipart limits (contract §9): one file; at most eight scalar fields
# (upload_id, context, the target id(s), category, caption, include_in_report, source -- `source`
# added in 14E.2, owner decision D11; an INSPECTION photo may name a question next to its inspection,
# 14F.2; a WORK photo names a surface and an occurrence_key, 14H.1 -- both are the largest forms and
# still fit in eight); scalar parts <= 8 KiB. max_part_size does NOT bound file parts.
MAX_FILES = 1
MAX_FIELDS = 8
MAX_SCALAR_PART_BYTES = 8192
FILE_FIELD = "file"
SCALAR_FIELDS = frozenset(
    {
        "upload_id", "context", "room_id", "surface_id", "opening_id", "inspection_id", "question_id", "finding_id",
        "occurrence_key", "category", "caption", "include_in_report", "source",
    }
)
ORIGINAL_NAME = "original"  # server-chosen workspace file name

_MESSAGES = {
    "PHOTO_UPLOADS_DISABLED": "Photo uploads are currently disabled",
    "PHOTO_TOO_LARGE": "The upload exceeds the maximum allowed size",
    "PHOTO_UPLOAD_TIMEOUT": "The upload stalled; no data was received in time",
    "PHOTO_UPLOAD_MALFORMED": "The upload request is malformed",
    "PHOTO_PROCESSING_BUSY": "Photo processing is busy; retry later",
    "PHOTO_STORAGE_UNAVAILABLE": "Photo storage is temporarily unavailable",
    "PHOTO_STORAGE_ERROR": "Photo storage error",
    "PHOTO_STORAGE_QUOTA_EXCEEDED": "Photo storage quota exceeded",
    "PHOTO_OBJECT_CONFLICT": "Stored photo data conflicts with this upload",
    "PHOTO_UPLOAD_RESUME_MISMATCH": "This upload cannot be resumed; start a new upload",
    "PHOTO_UNSUPPORTED_FORMAT": "Unsupported image format; use JPEG, PNG or WebP",
    "PHOTO_INVALID_IMAGE": "The image is invalid or corrupted",
    "PHOTO_TOO_MANY_PIXELS": "The image dimensions exceed the limit",
    "PHOTO_ANIMATED_NOT_SUPPORTED": "Animated images are not supported",
    "PHOTO_CONTEXT_NOT_SUPPORTED": "This photo context is not supported",
    "PROJECT_NOT_FOUND": "Project not found",
    "ROOM_NOT_FOUND": "Room not found",
    "SURFACE_NOT_FOUND": "Surface not found",
    "OPENING_NOT_FOUND": "Opening not found",
    "INSPECTION_NOT_FOUND": "Inspection not found",
    "QUESTION_NOT_FOUND": "Checklist question not found",
    "FINDING_NOT_FOUND": "Inspection finding not found",
    "WORK_OCCURRENCE_NOT_CURRENT": "This work is no longer part of the surface plan",
    "PHOTO_NOT_FOUND": "Photo not found",
    "PHOTO_ATTACHMENT_NOT_FOUND": "Photo attachment not found",
    "PHOTO_ATTACHMENT_DUPLICATE": "An equivalent active attachment already exists",
    "PHOTO_ATTACHMENT_INVALID": "Invalid photo attachment data",
    "PHOTO_CURSOR_INVALID": "Invalid list cursor",
    "PHOTO_ANNOTATION_NOT_FOUND": "Photo marker not found",
    "PHOTO_ANNOTATION_INVALID": "Invalid photo marker data",
    "PHOTO_ANNOTATION_LIMIT_REACHED": "The photo already has the maximum number of markers",
    "PHOTO_ANNOTATION_READ_ONLY": "Markers of an archived photo cannot be changed",
}


def _error(status_code: int, code: str, *, message: str | None = None, retry_after: bool = False) -> HTTPException:
    headers = None
    if retry_after:
        headers = {"Retry-After": str(math.ceil(settings.PHOTO_PROCESSING_WAIT_SECONDS))}
    return HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message or _MESSAGES[code]},
        headers=headers,
    )


def _malformed() -> HTTPException:
    return _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "PHOTO_UPLOAD_MALFORMED")


def _map_domain_error(exc: Exception) -> HTTPException:
    """Domain / storage exception -> HTTP error (contract §21)."""
    if isinstance(exc, ProjectNotFoundError):
        return _error(status.HTTP_404_NOT_FOUND, "PROJECT_NOT_FOUND")
    if isinstance(exc, RoomNotFoundError):
        return _error(status.HTTP_404_NOT_FOUND, "ROOM_NOT_FOUND")
    if isinstance(exc, SurfaceNotFoundError):
        return _error(status.HTTP_404_NOT_FOUND, "SURFACE_NOT_FOUND")
    if isinstance(exc, OpeningNotFoundError):
        return _error(status.HTTP_404_NOT_FOUND, "OPENING_NOT_FOUND")
    if isinstance(exc, InspectionNotFoundError):
        return _error(status.HTTP_404_NOT_FOUND, "INSPECTION_NOT_FOUND")
    if isinstance(exc, ChecklistQuestionNotFoundError):
        return _error(status.HTTP_404_NOT_FOUND, "QUESTION_NOT_FOUND")
    if isinstance(exc, InspectionFindingNotFoundError):
        return _error(status.HTTP_404_NOT_FOUND, "FINDING_NOT_FOUND")
    if isinstance(exc, PhotoWorkOccurrenceNotCurrentError):
        return _error(status.HTTP_409_CONFLICT, "WORK_OCCURRENCE_NOT_CURRENT")
    if isinstance(exc, PhotoUploadIdConflictError):
        # Fixed §14 message, identical for every conflict cause.
        return _error(status.HTTP_409_CONFLICT, exc.code, message=str(exc))
    if isinstance(exc, PhotoStorageQuotaExceededError):
        return _error(status.HTTP_409_CONFLICT, exc.code)
    if isinstance(exc, MediaObjectConflict):
        return _error(status.HTTP_409_CONFLICT, "PHOTO_OBJECT_CONFLICT")
    if isinstance(exc, PhotoUploadResumeMismatchError):
        return _error(status.HTTP_409_CONFLICT, exc.code)
    if isinstance(exc, PhotoTooLargeError):
        return _error(status.HTTP_413_CONTENT_TOO_LARGE, "PHOTO_TOO_LARGE")
    if isinstance(exc, PhotoUnsupportedFormatError):
        return _error(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, exc.code)
    if isinstance(exc, PhotoValidationError):  # invalid / too many pixels / animated
        return _error(status.HTTP_422_UNPROCESSABLE_CONTENT, exc.code)
    if isinstance(exc, PhotoContextNotSupportedError):
        return _error(status.HTTP_422_UNPROCESSABLE_CONTENT, exc.code)
    if isinstance(exc, (PhotoUploadMalformedError, PhotoAttachmentValidationError)):
        return _malformed()
    if isinstance(exc, PhotoUploadsDisabledError):
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "PHOTO_UPLOADS_DISABLED")
    if isinstance(exc, PhotoProcessingBusyError):
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "PHOTO_PROCESSING_BUSY", retry_after=True)
    if isinstance(exc, MediaStorageUnavailable):
        return _error(status.HTTP_503_SERVICE_UNAVAILABLE, "PHOTO_STORAGE_UNAVAILABLE")
    if isinstance(exc, MediaStorageError):  # misconfigured / disabled / other
        logger.error("photo storage error (%s)", type(exc).__name__)
        return _error(status.HTTP_500_INTERNAL_SERVER_ERROR, "PHOTO_STORAGE_ERROR")
    raise exc


_DOMAIN_ERRORS = (
    ProjectNotFoundError,
    RoomNotFoundError,
    SurfaceNotFoundError,
    OpeningNotFoundError,
    InspectionNotFoundError,
    ChecklistQuestionNotFoundError,
    InspectionFindingNotFoundError,
    PhotoWorkOccurrenceNotCurrentError,
    PhotoUploadIdConflictError,
    PhotoStorageQuotaExceededError,
    PhotoUploadResumeMismatchError,
    PhotoValidationError,
    PhotoContextNotSupportedError,
    PhotoUploadMalformedError,
    PhotoAttachmentValidationError,
    PhotoUploadsDisabledError,
    PhotoProcessingBusyError,
    MediaStorageError,
)


def _optional_uuid(value: str | None) -> uuid.UUID | None:
    if value is None:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        raise _malformed() from None


def _parse_form(form_items: list[tuple[str, str | UploadFile]]) -> tuple[dict[str, str], UploadFile]:
    """Strict semantic validation after parsing: only known names, each at
    most once, exactly one file part named `file`, scalars as text."""
    scalars: dict[str, str] = {}
    upload: UploadFile | None = None
    for name, value in form_items:
        if name == FILE_FIELD:
            if upload is not None or not isinstance(value, UploadFile):
                raise _malformed()
            upload = value
        elif name in SCALAR_FIELDS:
            if name in scalars or not isinstance(value, str):
                raise _malformed()
            scalars[name] = value
        else:
            raise _malformed()
    if upload is None or "upload_id" not in scalars or "context" not in scalars:
        raise _malformed()
    return scalars, upload


def _build_request(
    scalars: dict[str, str], owner_id: uuid.UUID, project_id: uuid.UUID, original_path: Path,
    original_filename: str | None,
) -> PhotoUploadRequest:
    try:
        parse_upload_id(scalars["upload_id"])  # reject before the copy; the service re-validates
        context = PhotoAttachmentContext(scalars["context"])
        category = PhotoCategory(scalars["category"]) if "category" in scalars else None
        capture_source = PhotoCaptureSource(scalars["source"]) if "source" in scalars else None
    except (PhotoUploadMalformedError, ValueError):
        raise _malformed() from None
    include = scalars.get("include_in_report", "false")
    if include not in ("true", "false"):
        raise _malformed()
    return PhotoUploadRequest(
        owner_id=owner_id,
        project_id=project_id,
        upload_id=scalars["upload_id"],
        target=AttachmentTarget(
            context=context,
            room_id=_optional_uuid(scalars.get("room_id")),
            surface_id=_optional_uuid(scalars.get("surface_id")),
            opening_id=_optional_uuid(scalars.get("opening_id")),
            inspection_id=_optional_uuid(scalars.get("inspection_id")),
            question_id=_optional_uuid(scalars.get("question_id")),
            finding_id=_optional_uuid(scalars.get("finding_id")),
            occurrence_key=_optional_uuid(scalars.get("occurrence_key")),
        ),
        original_path=original_path,
        category=category,
        caption=scalars.get("caption"),
        include_in_report=include == "true",
        original_filename=original_filename,
        capture_source=capture_source,
    )


async def _receive_upload(
    request: Request, workspace: Path, owner_id: uuid.UUID, project_id: uuid.UUID
) -> PhotoUploadRequest:
    """Guarded parse + bounded copy. The multipart spool is closed when this
    returns (the `async with` exits) -- before any processing starts."""
    guarded = Request(
        request.scope,
        receive=limited_receive(
            request.receive,
            settings.PHOTO_MAX_REQUEST_BYTES,
            idle_timeout_seconds=upload_guard.UPLOAD_IDLE_TIMEOUT_SECONDS,
        ),
    )
    original = workspace / ORIGINAL_NAME
    try:
        async with guarded.form(
            max_files=MAX_FILES, max_fields=MAX_FIELDS, max_part_size=MAX_SCALAR_PART_BYTES
        ) as form:
            scalars, upload = _parse_form(form.multi_items())
            upload_request = _build_request(scalars, owner_id, project_id, original, upload.filename)
            await anyio.to_thread.run_sync(copy_bounded, upload.file, original, settings.PHOTO_MAX_UPLOAD_BYTES)
    except RequestBodyTooLargeError:
        raise _error(status.HTTP_413_CONTENT_TOO_LARGE, "PHOTO_TOO_LARGE") from None
    except RequestBodyIdleTimeoutError:
        raise _error(status.HTTP_408_REQUEST_TIMEOUT, "PHOTO_UPLOAD_TIMEOUT") from None
    except PhotoTooLargeError:
        raise _error(status.HTTP_413_CONTENT_TOO_LARGE, "PHOTO_TOO_LARGE") from None
    except StarletteHTTPException as exc:
        # Local remap only: Starlette turns its own multipart errors (missing
        # boundary, too many files/fields, oversized scalar part) into 400.
        if exc.status_code == status.HTTP_400_BAD_REQUEST:
            raise _malformed() from None
        raise
    except FormParserError:
        # Raw python-multipart parse errors (e.g. a body that is not
        # multipart at all) are not converted by Starlette 1.6.0.
        raise _malformed() from None
    return upload_request


async def _presigned(runtime: PhotoRuntime, result: PhotoUploadResult) -> tuple[str, str, datetime]:
    ttl = settings.PHOTO_SIGNED_URL_TTL_SECONDS
    expires_at = datetime.now(UTC) + timedelta(seconds=ttl)
    thumbnail = await runtime.storage.presign_get(result.asset.storage_key_thumbnail, ttl)
    display = await runtime.storage.presign_get(result.asset.storage_key_display, ttl)
    return thumbnail, display, expires_at


@router.post(
    "/projects/{project_id}/photos",
    response_model=PhotoUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a photo (multipart) and attach it to a project / room / surface / opening",
    responses={200: {"description": "Replay of an already finalized upload", "model": PhotoUploadResponse}},
)
async def upload_photo(
    project_id: uuid.UUID,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    runtime: PhotoRuntime = Depends(get_photo_runtime),
) -> PhotoUploadResponse:
    config = PhotoUploadConfig.from_settings(settings)
    if not config.uploads_available:
        raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "PHOTO_UPLOADS_DISABLED")
    try:
        declared = parse_content_length(request.headers.get("content-length"))
    except PhotoUploadMalformedError:
        raise _malformed() from None
    if declared is not None and declared > settings.PHOTO_MAX_REQUEST_BYTES:
        raise _error(status.HTTP_413_CONTENT_TOO_LARGE, "PHOTO_TOO_LARGE")
    # Only scalars cross the transaction boundary below: rollback expires every
    # loaded ORM attribute (even with expire_on_commit=False), and touching an
    # expired attribute would lazy-load under async.
    owner_id = current_user.id
    try:
        await ProjectService(db).get_project(project_id, owner_id)
    except ProjectNotFoundError as exc:
        raise _map_domain_error(exc) from None
    # F3 (14C.6A): ownership is verified BEFORE any body byte is read; end the
    # completed read-only transaction so no DB transaction / pooled connection
    # stays open during network body reception.
    await db.rollback()
    if not runtime.admission.try_acquire():
        raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "PHOTO_PROCESSING_BUSY", retry_after=True)
    try:
        return await _admitted_upload(request, response, db, runtime, config, owner_id, project_id)
    finally:
        runtime.admission.release()


async def _admitted_upload(
    request: Request,
    response: Response,
    db: AsyncSession,
    runtime: PhotoRuntime,
    config: PhotoUploadConfig,
    owner_id: uuid.UUID,
    project_id: uuid.UUID,
) -> PhotoUploadResponse:
    await anyio.to_thread.run_sync(
        sweep_stale_photo_temp, settings.PHOTO_TEMP_DIR, settings.PHOTO_TEMP_STALE_AFTER_SECONDS
    )
    content_type = request.headers.get("content-type", "")
    if content_type.split(";", 1)[0].strip().lower() != "multipart/form-data":
        raise _malformed()
    service = PhotoUploadService(db, runtime.storage, runtime.processor, config)
    with photo_workspace(settings.PHOTO_TEMP_DIR) as workspace:
        try:
            upload_request = await _receive_upload(request, workspace, owner_id, project_id)
        except ClientDisconnect:
            logger.info("photo upload: client disconnected during reception")
            _raise_disconnected()
        try:
            result = await service.upload(upload_request)
            thumbnail_url, display_url, expires_at = await _presigned(runtime, result)
        except _DOMAIN_ERRORS as exc:
            raise _map_domain_error(exc) from None
    response.status_code = status.HTTP_201_CREATED if result.outcome.created else status.HTTP_200_OK
    return PhotoUploadResponse(
        asset=PhotoAssetRead.model_validate(result.asset),
        attachment=PhotoAttachmentRead.model_validate(result.attachment) if result.attachment else None,
        thumbnail_url=thumbnail_url,
        display_url=display_url,
        urls_expire_at=expires_at,
        storage=PhotoStorageRead(state=result.storage_state),
    )


def _raise_disconnected() -> NoReturn:
    # Nobody receives this response; it only ends the request cleanly
    # (workspace removal and admission release still run).
    raise _malformed()


# ===========================================================================
# Stage 14C.5 — reads, signed-link refresh, metadata, archive / restore.
# ===========================================================================

_LIBRARY_ERRORS = (
    *_DOMAIN_ERRORS,
    PhotoAssetNotFoundError,
    PhotoAttachmentNotFoundError,
    PhotoAttachmentDuplicateError,
    PhotoCursorInvalidError,
    PhotoAnnotationNotFoundError,
    PhotoAnnotationValidationError,
    PhotoAnnotationLimitReachedError,
    PhotoAnnotationReadOnlyError,
)


def _map_library_error(exc: Exception) -> HTTPException:
    """14C.5 mapping; everything else falls through to the 14C.4 mapping."""
    if isinstance(exc, PhotoAssetNotFoundError):
        return _error(status.HTTP_404_NOT_FOUND, "PHOTO_NOT_FOUND")
    if isinstance(exc, PhotoAttachmentNotFoundError):
        return _error(status.HTTP_404_NOT_FOUND, "PHOTO_ATTACHMENT_NOT_FOUND")
    if isinstance(exc, PhotoAttachmentDuplicateError):
        return _error(status.HTTP_409_CONFLICT, "PHOTO_ATTACHMENT_DUPLICATE")
    if isinstance(exc, PhotoAttachmentValidationError):
        return _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "PHOTO_ATTACHMENT_INVALID")
    if isinstance(exc, PhotoCursorInvalidError):
        return _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "PHOTO_CURSOR_INVALID")
    if isinstance(exc, PhotoAnnotationNotFoundError):
        return _error(status.HTTP_404_NOT_FOUND, "PHOTO_ANNOTATION_NOT_FOUND")
    if isinstance(exc, PhotoAnnotationValidationError):
        return _error(status.HTTP_422_UNPROCESSABLE_CONTENT, "PHOTO_ANNOTATION_INVALID")
    if isinstance(exc, PhotoAnnotationLimitReachedError):
        return _error(status.HTTP_409_CONFLICT, "PHOTO_ANNOTATION_LIMIT_REACHED")
    if isinstance(exc, PhotoAnnotationReadOnlyError):
        return _error(status.HTTP_409_CONFLICT, "PHOTO_ANNOTATION_READ_ONLY")
    return _map_domain_error(exc)


async def _sign(storage: MediaStorage, keys: list[str]) -> tuple[list[str | None], datetime | None]:
    """Derivative URLs only (never the original). Disabled storage -> null
    URLs and expiry (§17); other storage errors propagate to the mapping
    (503 / 500). Signing never touches the database."""
    ttl = settings.PHOTO_SIGNED_URL_TTL_SECONDS
    expires_at = datetime.now(UTC) + timedelta(seconds=ttl)
    urls: list[str | None] = []
    try:
        for key in keys:
            urls.append(await storage.presign_get(key, ttl))
    except MediaStorageDisabled:
        return [None] * len(keys), None
    return urls, expires_at


@router.get(
    "/projects/{project_id}/photos",
    response_model=PhotoListResponse,
    summary="List photo attachments (normal view or archive view) with fresh thumbnail URLs",
)
async def list_photos(
    project_id: uuid.UUID,
    context: PhotoAttachmentContext | None = Query(default=None),
    room_id: uuid.UUID | None = Query(default=None),
    surface_id: uuid.UUID | None = Query(default=None),
    opening_id: uuid.UUID | None = Query(default=None),
    inspection_id: uuid.UUID | None = Query(default=None),
    question_id: uuid.UUID | None = Query(default=None),
    finding_id: uuid.UUID | None = Query(default=None),
    occurrence_key: uuid.UUID | None = Query(
        default=None,
        description="with context=WORK and surface_id: one occurrence of the surface's work plan (detached ones included)",
    ),
    in_room_id: uuid.UUID | None = Query(
        default=None,
        description="every photo of this room: the room itself, its surfaces and their openings (no other target filter)",
    ),
    site_only: bool = Query(
        default=False,
        description="only PROJECT / ROOM / SURFACE / OPENING photos, leaving out inspection evidence (no other target filter)",
    ),
    lineage: uuid.UUID | None = Query(
        default=None,
        description="every FINDING photo of this finding lineage, whichever row of the lineage it was taken on (no other target filter)",
    ),
    category: PhotoCategory | None = Query(default=None),
    include_in_report: bool | None = Query(default=None),
    archived: bool = Query(default=False, description="false: normal view; true: archive view (restorable items)"),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    cursor: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    runtime: PhotoRuntime = Depends(get_photo_runtime),
) -> PhotoListResponse:
    filters = PhotoListFilters(
        context=context, room_id=room_id, surface_id=surface_id, opening_id=opening_id,
        inspection_id=inspection_id, question_id=question_id, finding_id=finding_id, occurrence_key=occurrence_key,
        category=category, include_in_report=include_in_report, archived=archived, in_room_id=in_room_id,
        lineage_id=lineage, site_only=site_only,
    )
    try:
        page = await PhotoQueryService(db).list_photos(
            current_user.id, project_id, filters, limit=limit, cursor=cursor
        )
        urls, expires_at = await _sign(runtime.storage, [asset.storage_key_thumbnail for _, asset in page.items])
        marker_counts = await PhotoAnnotationService(db).counts_for_attachments([a.id for a, _ in page.items])
    except _LIBRARY_ERRORS as exc:
        raise _map_library_error(exc) from None
    return PhotoListResponse(
        items=[
            PhotoListItem(
                attachment=PhotoAttachmentRead.model_validate(attachment),
                asset=PhotoAssetRead.model_validate(asset),
                thumbnail_url=url,
                annotation_count=marker_counts.get(attachment.id, 0),
            )
            for (attachment, asset), url in zip(page.items, urls, strict=True)
        ],
        next_cursor=page.next_cursor,
        urls_expire_at=expires_at if page.items else None,
    )


@router.get(
    "/projects/{project_id}/photos/counts",
    response_model=PhotoCountsResponse,
    summary="Badge counts of visible photos per project / room / surface / opening (one aggregate query)",
)
async def photo_counts(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PhotoCountsResponse:
    # Declared BEFORE the `{asset_id}` detail route so "counts" is never parsed as an asset id.
    try:
        counts = await PhotoQueryService(db).counts(current_user.id, project_id)
    except _LIBRARY_ERRORS as exc:
        raise _map_library_error(exc) from None
    return PhotoCountsResponse(
        project=counts.project, rooms=counts.rooms, surfaces=counts.surfaces, openings=counts.openings,
        room_totals=counts.room_totals, inspections=counts.inspections, findings=counts.findings,
        lineages=counts.lineages, questions=counts.questions, works=counts.works, work_surfaces=counts.work_surfaces,
        inspection_surfaces=counts.inspection_surfaces,
    )


@router.get(
    "/projects/{project_id}/photos/{asset_id}",
    response_model=PhotoDetailResponse,
    summary="Photo detail: READY asset (archived included), all its attachments, thumbnail + display URLs",
)
async def get_photo(
    project_id: uuid.UUID,
    asset_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    runtime: PhotoRuntime = Depends(get_photo_runtime),
) -> PhotoDetailResponse:
    try:
        asset, attachments = await PhotoQueryService(db).get_detail(current_user.id, project_id, asset_id)
        urls, expires_at = await _sign(runtime.storage, [asset.storage_key_thumbnail, asset.storage_key_display])
        markers = await PhotoAnnotationService(db).list_for_attachments([a.id for a in attachments])
    except _LIBRARY_ERRORS as exc:
        raise _map_library_error(exc) from None
    return PhotoDetailResponse(
        asset=PhotoAssetRead.model_validate(asset),
        attachments=[PhotoAttachmentRead.model_validate(a) for a in attachments],
        thumbnail_url=urls[0],
        display_url=urls[1],
        urls_expire_at=expires_at,
        annotations=[PhotoAnnotationRead.model_validate(m) for m in markers],
    )


@router.post(
    "/projects/{project_id}/photos/{asset_id}/attachments",
    response_model=PhotoAttachmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Attach an existing READY photo to another supported context (DB only; no media write)",
)
async def attach_photo(
    project_id: uuid.UUID,
    asset_id: uuid.UUID,
    payload: PhotoAttachRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PhotoAttachmentRead:
    try:
        attachment = await PhotoAttachmentService(db).create_attachment(
            owner_id=current_user.id,
            project_id=project_id,
            asset_id=asset_id,
            target=AttachmentTarget(
                context=payload.context,
                room_id=payload.room_id,
                surface_id=payload.surface_id,
                opening_id=payload.opening_id,
                inspection_id=payload.inspection_id,
                question_id=payload.question_id,
                finding_id=payload.finding_id,
                occurrence_key=payload.occurrence_key,
            ),
            category=payload.category,
            caption=payload.caption,
            include_in_report=payload.include_in_report,
        )
    except _LIBRARY_ERRORS as exc:
        raise _map_library_error(exc) from None
    return PhotoAttachmentRead.model_validate(attachment)


@router.patch(
    "/projects/{project_id}/photo-attachments/{attachment_id}",
    response_model=PhotoAttachmentRead,
    summary="Update attachment metadata (caption, category, include_in_report, position)",
)
async def update_photo_attachment(
    project_id: uuid.UUID,
    attachment_id: uuid.UUID,
    payload: PhotoAttachmentPatch,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PhotoAttachmentRead:
    changes = {name: getattr(payload, name) for name in payload.model_fields_set}
    try:
        await ProjectService(db).get_project(project_id, current_user.id)
        attachment = await PhotoAttachmentService(db).update_attachment(
            current_user.id, project_id, attachment_id, **changes
        )
    except _LIBRARY_ERRORS as exc:
        raise _map_library_error(exc) from None
    return PhotoAttachmentRead.model_validate(attachment)


async def _attachment_state(
    project_id: uuid.UUID, attachment_id: uuid.UUID, owner_id: uuid.UUID, db: AsyncSession, *, archive: bool
) -> PhotoAttachmentRead:
    service = PhotoAttachmentService(db)
    try:
        await ProjectService(db).get_project(project_id, owner_id)
        if archive:
            attachment = await service.archive_attachment(owner_id, project_id, attachment_id)
        else:
            attachment = await service.restore_attachment(owner_id, project_id, attachment_id)
    except _LIBRARY_ERRORS as exc:
        raise _map_library_error(exc) from None
    return PhotoAttachmentRead.model_validate(attachment)


@router.post(
    "/projects/{project_id}/photo-attachments/{attachment_id}/archive",
    response_model=PhotoAttachmentRead,
    summary="Archive one attachment (idempotent; asset, other attachments and storage untouched)",
)
async def archive_photo_attachment(
    project_id: uuid.UUID,
    attachment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PhotoAttachmentRead:
    return await _attachment_state(project_id, attachment_id, current_user.id, db, archive=True)


@router.post(
    "/projects/{project_id}/photo-attachments/{attachment_id}/restore",
    response_model=PhotoAttachmentRead,
    summary="Restore one attachment (idempotent; 409 when an equivalent active attachment exists)",
)
async def restore_photo_attachment(
    project_id: uuid.UUID,
    attachment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PhotoAttachmentRead:
    return await _attachment_state(project_id, attachment_id, current_user.id, db, archive=False)


async def _asset_state(
    project_id: uuid.UUID, asset_id: uuid.UUID, owner_id: uuid.UUID, db: AsyncSession, *, archive: bool
) -> PhotoAssetRead:
    service = PhotoAssetService(db)
    try:
        await ProjectService(db).get_project(project_id, owner_id)
        if archive:
            asset = await service.archive(asset_id, owner_id, project_id)
        else:
            asset = await service.restore(asset_id, owner_id, project_id)
    except _LIBRARY_ERRORS as exc:
        raise _map_library_error(exc) from None
    return PhotoAssetRead.model_validate(asset)


@router.post(
    "/projects/{project_id}/photos/{asset_id}/archive",
    response_model=PhotoAssetRead,
    summary="Archive a READY photo everywhere (idempotent; no attachment cascade, no storage change)",
)
async def archive_photo(
    project_id: uuid.UUID,
    asset_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PhotoAssetRead:
    return await _asset_state(project_id, asset_id, current_user.id, db, archive=True)


@router.post(
    "/projects/{project_id}/photos/{asset_id}/restore",
    response_model=PhotoAssetRead,
    summary="Restore a photo (idempotent; attachment archive states are left exactly as they were)",
)
async def restore_photo(
    project_id: uuid.UUID,
    asset_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PhotoAssetRead:
    return await _asset_state(project_id, asset_id, current_user.id, db, archive=False)


@router.get(
    "/projects/{project_id}/photo-attachments/{attachment_id}/annotations",
    response_model=PhotoAnnotationListResponse,
    summary="Point markers of one attachment (archived attachments included), in display order",
)
async def list_photo_annotations(
    project_id: uuid.UUID,
    attachment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PhotoAnnotationListResponse:
    try:
        await ProjectService(db).get_project(project_id, current_user.id)
        markers = await PhotoAnnotationService(db).list_for_attachment(current_user.id, project_id, attachment_id)
    except _LIBRARY_ERRORS as exc:
        raise _map_library_error(exc) from None
    return PhotoAnnotationListResponse(items=[PhotoAnnotationRead.model_validate(m) for m in markers])


@router.post(
    "/projects/{project_id}/photo-attachments/{attachment_id}/annotations",
    response_model=PhotoAnnotationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Place a point marker (x, y = fractions of the display image; at most 10 per attachment)",
)
async def create_photo_annotation(
    project_id: uuid.UUID,
    attachment_id: uuid.UUID,
    payload: PhotoAnnotationCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PhotoAnnotationRead:
    try:
        await ProjectService(db).get_project(project_id, current_user.id)
        marker = await PhotoAnnotationService(db).create(
            current_user.id, project_id, attachment_id, x=payload.x, y=payload.y, label=payload.label
        )
    except _LIBRARY_ERRORS as exc:
        raise _map_library_error(exc) from None
    return PhotoAnnotationRead.model_validate(marker)


@router.patch(
    "/projects/{project_id}/photo-attachments/{attachment_id}/annotations/{annotation_id}",
    response_model=PhotoAnnotationRead,
    summary="Change the label and / or contour of a marker (a marker is never moved or reordered)",
)
async def update_photo_annotation(
    project_id: uuid.UUID,
    attachment_id: uuid.UUID,
    annotation_id: uuid.UUID,
    payload: PhotoAnnotationPatch,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PhotoAnnotationRead:
    changes = {name: getattr(payload, name) for name in payload.model_fields_set}
    try:
        await ProjectService(db).get_project(project_id, current_user.id)
        marker = await PhotoAnnotationService(db).update(
            current_user.id, project_id, attachment_id, annotation_id, **changes
        )
    except _LIBRARY_ERRORS as exc:
        raise _map_library_error(exc) from None
    return PhotoAnnotationRead.model_validate(marker)


@router.delete(
    "/projects/{project_id}/photo-attachments/{attachment_id}/annotations/{annotation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a marker for good (the photo is untouched)",
)
async def delete_photo_annotation(
    project_id: uuid.UUID,
    attachment_id: uuid.UUID,
    annotation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    try:
        await ProjectService(db).get_project(project_id, current_user.id)
        await PhotoAnnotationService(db).delete(current_user.id, project_id, attachment_id, annotation_id)
    except _LIBRARY_ERRORS as exc:
        raise _map_library_error(exc) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/photo-storage",
    response_model=PhotoStorageStatus,
    summary="Logical photo storage accounting and upload availability (no provider scan)",
)
async def photo_storage_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PhotoStorageStatus:
    """Same logical / reserved accounting as the upload quota (contract §15):
    recorded sizes of READY + PENDING + FAILED assets, archived included. No
    bucket listing, HEAD or network call."""
    config = PhotoUploadConfig.from_settings(settings)
    used = await logical_usage_bytes(db, current_user.id)
    return PhotoStorageStatus(
        uploads_enabled=config.uploads_available,
        media_available=settings.MEDIA_STORAGE_BACKEND == "s3",
        used_bytes=used,
        warning_bytes=settings.PHOTO_STORAGE_WARNING_BYTES,
        soft_cap_bytes=settings.PHOTO_STORAGE_SOFT_CAP_BYTES,
        state=storage_state(
            used,
            warning_bytes=settings.PHOTO_STORAGE_WARNING_BYTES,
            soft_cap_bytes=settings.PHOTO_STORAGE_SOFT_CAP_BYTES,
        ),
    )
