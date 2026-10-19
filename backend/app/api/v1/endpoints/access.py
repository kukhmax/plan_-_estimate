"""The access list (closed registration): thin routes over `AccessService`, for the administrator only."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_admin
from app.core.database import get_db
from app.domain.exceptions import AccessAdminProtectedError, AccessEntryNotFoundError, AccessSettingsInvalidError
from app.domain.services.access_service import AccessService
from app.models.user import User
from app.schemas.access import (
    AccessDecision,
    AccessEntryRead,
    AccessOverview,
    AccessSettingsRead,
    AccessSettingsUpdate,
)

router = APIRouter()


def _map(exc: Exception) -> HTTPException:
    if isinstance(exc, AccessEntryNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, {"code": "ACCESS_ENTRY_NOT_FOUND", "message": "Access list row not found"})
    if isinstance(exc, AccessAdminProtectedError):
        return HTTPException(status.HTTP_409_CONFLICT, {"code": "ACCESS_ADMIN_PROTECTED", "message": "An administrator is changed only on the server"})
    if isinstance(exc, AccessSettingsInvalidError):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, {"code": "ACCESS_CONTACT_TOO_LONG", "message": "The contact text is too long"})
    raise exc


async def _overview(service: AccessService) -> AccessOverview:
    closed, contact = await service.settings()
    return AccessOverview(
        settings=AccessSettingsRead(closed=closed, contact=contact),
        entries=[AccessEntryRead.model_validate(row) for row in await service.list_entries()],
    )


@router.get("/access", response_model=AccessOverview, summary="The access list and its settings (administrator)")
async def get_access(_admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> AccessOverview:
    return await _overview(AccessService(db))


@router.patch("/access/entries/{entry_id}", response_model=AccessEntryRead, summary="Admit or block an account (administrator)")
async def decide_entry(
    entry_id: uuid.UUID,
    payload: AccessDecision,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AccessEntryRead:
    try:
        return AccessEntryRead.model_validate(await AccessService(db).decide(entry_id, payload.status))
    except (AccessEntryNotFoundError, AccessAdminProtectedError) as exc:
        raise _map(exc)


@router.delete("/access/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove a row of the access list (administrator)")
async def remove_entry(entry_id: uuid.UUID, _admin: User = Depends(require_admin), db: AsyncSession = Depends(get_db)) -> Response:
    try:
        await AccessService(db).remove(entry_id)
    except (AccessEntryNotFoundError, AccessAdminProtectedError) as exc:
        raise _map(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/access/settings", response_model=AccessSettingsRead, summary="Close or open the registration, set the contact text (administrator)")
async def update_settings(
    payload: AccessSettingsUpdate,
    _admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AccessSettingsRead:
    try:
        closed, contact = await AccessService(db).update_settings(payload.closed, payload.contact)
    except AccessSettingsInvalidError as exc:
        raise _map(exc)
    return AccessSettingsRead(closed=closed, contact=contact)
