"""Photo upload endpoint (Stage 14C.4).

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
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from python_multipart.exceptions import FormParserError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import ClientDisconnect

from app.api.deps import PhotoRuntime, get_current_user, get_photo_runtime
from app.api.upload_guard import (
    RequestBodyTooLargeError,
    copy_bounded,
    limited_receive,
    parse_content_length,
    sweep_stale_photo_temp,
)
from app.core.config import settings
from app.core.database import get_db
from app.domain.exceptions import (
    MediaObjectConflict,
    MediaStorageError,
    MediaStorageUnavailable,
    OpeningNotFoundError,
    PhotoAttachmentValidationError,
    PhotoContextNotSupportedError,
    PhotoProcessingBusyError,
    PhotoStorageQuotaExceededError,
    PhotoTooLargeError,
    PhotoUnsupportedFormatError,
    PhotoUploadIdConflictError,
    PhotoUploadMalformedError,
    PhotoUploadResumeMismatchError,
    PhotoUploadsDisabledError,
    PhotoValidationError,
    ProjectNotFoundError,
    RoomNotFoundError,
    SurfaceNotFoundError,
)
from app.domain.photos.temp import photo_workspace
from app.domain.services.photo_attachment_service import AttachmentTarget
from app.domain.services.photo_upload_service import (
    PhotoUploadConfig,
    PhotoUploadRequest,
    PhotoUploadResult,
    PhotoUploadService,
    parse_upload_id,
)
from app.domain.services.project_service import ProjectService
from app.models.photo_attachment import PhotoAttachmentContext, PhotoCategory
from app.models.user import User
from app.schemas.photo import (
    PhotoAssetRead,
    PhotoAttachmentRead,
    PhotoStorageRead,
    PhotoUploadResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Multipart limits (contract §9): one file; at most six scalar fields
# (upload_id, context, one target id, category, caption, include_in_report);
# scalar parts <= 8 KiB. max_part_size does NOT bound file parts.
MAX_FILES = 1
MAX_FIELDS = 6
MAX_SCALAR_PART_BYTES = 8192
FILE_FIELD = "file"
SCALAR_FIELDS = frozenset(
    {"upload_id", "context", "room_id", "surface_id", "opening_id", "category", "caption", "include_in_report"}
)
ORIGINAL_NAME = "original"  # server-chosen workspace file name

_MESSAGES = {
    "PHOTO_UPLOADS_DISABLED": "Photo uploads are currently disabled",
    "PHOTO_TOO_LARGE": "The upload exceeds the maximum allowed size",
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
        ),
        original_path=original_path,
        category=category,
        caption=scalars.get("caption"),
        include_in_report=include == "true",
        original_filename=original_filename,
    )


async def _receive_upload(
    request: Request, workspace: Path, owner_id: uuid.UUID, project_id: uuid.UUID
) -> PhotoUploadRequest:
    """Guarded parse + bounded copy. The multipart spool is closed when this
    returns (the `async with` exits) -- before any processing starts."""
    guarded = Request(request.scope, receive=limited_receive(request.receive, settings.PHOTO_MAX_REQUEST_BYTES))
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
    try:
        await ProjectService(db).get_project(project_id, current_user.id)
    except ProjectNotFoundError as exc:
        raise _map_domain_error(exc) from None
    if not runtime.admission.try_acquire():
        raise _error(status.HTTP_503_SERVICE_UNAVAILABLE, "PHOTO_PROCESSING_BUSY", retry_after=True)
    try:
        return await _admitted_upload(request, response, db, runtime, config, current_user.id, project_id)
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
