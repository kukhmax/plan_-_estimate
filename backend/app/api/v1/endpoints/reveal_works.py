"""Opening reveal work plan HTTP API (Stage 10E).

Thin controller over OpeningRevealWorkService. All domain rules (REVEAL
category guard, reveal_enabled check, archived-item reduction-only, ordering,
duplicate allowance) live in the service and are NOT duplicated here.

Ownership chain: Opening → Surface → Room → Project → owner.
All four path identities are validated by the service to prevent cross-hierarchy
access within the same owner account.
PriceItem owner validation is also handled by the service.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, get_reveal_work_service
from app.domain.exceptions import (
    OpeningNotFoundError,
    OpeningRevealWorkValidationError,
    PriceItemNotFoundError,
)
from app.domain.services.opening_reveal_work_service import OpeningRevealWorkService
from app.models.user import User
from app.schemas.reveal_work import (
    RevealWorkItemRead,
    RevealWorkListResponse,
    RevealWorkSetRequest,
)

router = APIRouter()

_OPENING_PREFIX = (
    "/projects/{project_id}/rooms/{room_id}"
    "/surfaces/{surface_id}/openings/{opening_id}/reveal-works"
)


# ---------------------------------------------------------------------------
# GET ordered reveal works
# ---------------------------------------------------------------------------

@router.get(
    _OPENING_PREFIX,
    response_model=RevealWorkListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get ordered reveal works for an opening",
)
async def get_reveal_works(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    surface_id: uuid.UUID,
    opening_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: OpeningRevealWorkService = Depends(get_reveal_work_service),
) -> RevealWorkListResponse:
    try:
        works = await service.get_works(
            opening_id, current_user.id,
            project_id=project_id, room_id=room_id, surface_id=surface_id,
        )
    except OpeningNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Opening not found"
        )
    return RevealWorkListResponse(
        opening_id=opening_id,
        items=[RevealWorkItemRead.model_validate(w) for w in works],
    )


# ---------------------------------------------------------------------------
# PUT set/replace ordered reveal works
# ---------------------------------------------------------------------------

@router.put(
    _OPENING_PREFIX,
    response_model=RevealWorkListResponse,
    status_code=status.HTTP_200_OK,
    summary="Set (replace) the ordered reveal work list for an opening",
)
async def set_reveal_works(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    surface_id: uuid.UUID,
    opening_id: uuid.UUID,
    payload: RevealWorkSetRequest,
    current_user: User = Depends(get_current_user),
    service: OpeningRevealWorkService = Depends(get_reveal_work_service),
) -> RevealWorkListResponse:
    try:
        works = await service.set_works(
            opening_id, current_user.id, payload.price_item_ids,
            project_id=project_id, room_id=room_id, surface_id=surface_id,
        )
    except OpeningNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Opening not found"
        )
    except PriceItemNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Price item not found"
        )
    except OpeningRevealWorkValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )
    return RevealWorkListResponse(
        opening_id=opening_id,
        items=[RevealWorkItemRead.model_validate(w) for w in works],
    )


# ---------------------------------------------------------------------------
# DELETE clear all reveal works
# ---------------------------------------------------------------------------

@router.delete(
    _OPENING_PREFIX,
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear all reveal works for an opening",
)
async def clear_reveal_works(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    surface_id: uuid.UUID,
    opening_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: OpeningRevealWorkService = Depends(get_reveal_work_service),
) -> None:
    try:
        await service.clear_works(
            opening_id, current_user.id,
            project_id=project_id, room_id=room_id, surface_id=surface_id,
        )
    except OpeningNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Opening not found"
        )
