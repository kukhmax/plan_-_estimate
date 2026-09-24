"""Price coefficient catalog API router (Stage 12C).

Thin owner-scoped controller: auth -> input validation -> service -> typed
response. All domain rules live in `PriceCoefficientService`; this module
only maps domain exceptions to HTTP errors (404 for missing/foreign rows, 422
for domain validation failures) and bootstraps the owner catalog on the list
entry point -- mirrors `app/api/v1/endpoints/pricebook.py` exactly.

No planned-work assignment endpoint exists here (Stage 12D) and no Estimate
integration exists here (Stage 12E) -- this router is catalog CRUD only.
"""
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user, get_price_coefficient_service
from app.domain.exceptions import (
    CoefficientGroupNotFoundError,
    CoefficientOptionNotFoundError,
    PriceCoefficientValidationError,
)
from app.domain.services.price_coefficient_service import PriceCoefficientService
from app.models.price_coefficient import CoefficientGroup
from app.models.user import User
from app.schemas.price_coefficient import (
    CoefficientGroupCreate,
    CoefficientGroupListResponse,
    CoefficientGroupRead,
    CoefficientGroupUpdate,
    CoefficientOptionCreate,
    CoefficientOptionRead,
    CoefficientOptionUpdate,
)

router = APIRouter()


def _group_read(
    group: CoefficientGroup, *, include_archived_options: bool
) -> CoefficientGroupRead:
    """Build the response schema, filtering archived options at render time
    rather than mutating the ORM relationship (which would mark filtered-out
    rows for deletion under `cascade="all, delete-orphan"`)."""
    options = (
        group.options
        if include_archived_options
        else [option for option in group.options if not option.is_archived]
    )
    return CoefficientGroupRead(
        id=group.id,
        code=group.code,
        name_key=group.name_key,
        display_name=group.display_name,
        description=group.description,
        selection_mode=group.selection_mode,
        position=group.position,
        is_archived=group.is_archived,
        created_at=group.created_at,
        updated_at=group.updated_at,
        options=[CoefficientOptionRead.model_validate(option) for option in options],
    )


@router.get(
    "/price-coefficient-groups",
    response_model=CoefficientGroupListResponse,
    status_code=status.HTTP_200_OK,
    summary="List the owner's price coefficient catalog (bootstraps the baseline)",
)
async def list_coefficient_groups(
    archived: Literal["active", "archived", "all"] = Query(
        default="active", description="Archived filter: active (default) / archived / all"
    ),
    include_archived_options: bool = Query(
        default=False,
        description="Include each group's archived options (for a management screen)",
    ),
    current_user: User = Depends(get_current_user),
    service: PriceCoefficientService = Depends(get_price_coefficient_service),
) -> CoefficientGroupListResponse:
    # Bootstrap-on-access: materialize any missing baseline groups/options for
    # the owner (idempotent, currently a no-op -- see price_coefficients.py).
    await service.ensure_owner_catalog(current_user.id)
    groups = await service.list_owner_groups(current_user.id, archived=archived)
    items = [
        _group_read(group, include_archived_options=include_archived_options)
        for group in groups
    ]
    return CoefficientGroupListResponse(items=items, total=len(items))


@router.post(
    "/price-coefficient-groups",
    response_model=CoefficientGroupRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an owner coefficient group with a server-generated code",
)
async def create_coefficient_group(
    payload: CoefficientGroupCreate,
    current_user: User = Depends(get_current_user),
    service: PriceCoefficientService = Depends(get_price_coefficient_service),
) -> CoefficientGroupRead:
    try:
        created = await service.create_group(
            current_user.id,
            display_name=payload.display_name,
            description=payload.description,
        )
    except PriceCoefficientValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )
    # Re-fetch with options eagerly loaded rather than touching the bare
    # just-created object's relationship attribute directly (async sessions
    # disallow an implicit lazy load -- see EstimateService's own precedent).
    group = await service.get_owned_group(current_user.id, created.id, with_options=True)
    return _group_read(group, include_archived_options=True)


@router.get(
    "/price-coefficient-groups/{group_id}",
    response_model=CoefficientGroupRead,
    status_code=status.HTTP_200_OK,
    summary="Get an owned coefficient group (with its options) by ID",
)
async def get_coefficient_group(
    group_id: uuid.UUID,
    include_archived_options: bool = Query(
        default=False,
        description="Include archived options (for a management screen)",
    ),
    current_user: User = Depends(get_current_user),
    service: PriceCoefficientService = Depends(get_price_coefficient_service),
) -> CoefficientGroupRead:
    try:
        group = await service.get_owned_group(
            current_user.id, group_id, with_options=True
        )
    except CoefficientGroupNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Coefficient group not found"
        )
    return _group_read(group, include_archived_options=include_archived_options)


@router.patch(
    "/price-coefficient-groups/{group_id}",
    response_model=CoefficientGroupRead,
    status_code=status.HTTP_200_OK,
    summary="Partially update an owned coefficient group (omitted fields unchanged)",
)
async def update_coefficient_group(
    group_id: uuid.UUID,
    payload: CoefficientGroupUpdate,
    current_user: User = Depends(get_current_user),
    service: PriceCoefficientService = Depends(get_price_coefficient_service),
) -> CoefficientGroupRead:
    try:
        group = await service.update_group(
            current_user.id,
            group_id,
            **payload.model_dump(exclude_unset=True),
        )
    except CoefficientGroupNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Coefficient group not found"
        )
    except PriceCoefficientValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )
    group = await service.get_owned_group(current_user.id, group_id, with_options=True)
    return _group_read(group, include_archived_options=True)


@router.post(
    "/price-coefficient-groups/{group_id}/archive",
    response_model=CoefficientGroupRead,
    status_code=status.HTTP_200_OK,
    summary="Soft-archive an owned coefficient group (idempotent)",
)
async def archive_coefficient_group(
    group_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: PriceCoefficientService = Depends(get_price_coefficient_service),
) -> CoefficientGroupRead:
    try:
        await service.archive_group(current_user.id, group_id)
    except CoefficientGroupNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Coefficient group not found"
        )
    group = await service.get_owned_group(current_user.id, group_id, with_options=True)
    return _group_read(group, include_archived_options=True)


@router.post(
    "/price-coefficient-groups/{group_id}/restore",
    response_model=CoefficientGroupRead,
    status_code=status.HTTP_200_OK,
    summary="Restore an archived owned coefficient group (idempotent)",
)
async def restore_coefficient_group(
    group_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: PriceCoefficientService = Depends(get_price_coefficient_service),
) -> CoefficientGroupRead:
    try:
        await service.restore_group(current_user.id, group_id)
    except CoefficientGroupNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Coefficient group not found"
        )
    group = await service.get_owned_group(current_user.id, group_id, with_options=True)
    return _group_read(group, include_archived_options=True)


@router.post(
    "/price-coefficient-groups/{group_id}/options",
    response_model=CoefficientOptionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an option within an owned, active coefficient group",
)
async def create_coefficient_option(
    group_id: uuid.UUID,
    payload: CoefficientOptionCreate,
    current_user: User = Depends(get_current_user),
    service: PriceCoefficientService = Depends(get_price_coefficient_service),
) -> CoefficientOptionRead:
    try:
        option = await service.create_option(
            current_user.id,
            group_id,
            display_name=payload.display_name,
            description=payload.description,
            percentage=payload.percentage,
            is_base=payload.is_base,
        )
    except CoefficientGroupNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Coefficient group not found"
        )
    except PriceCoefficientValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )
    return CoefficientOptionRead.model_validate(option)


@router.patch(
    "/price-coefficient-options/{option_id}",
    response_model=CoefficientOptionRead,
    status_code=status.HTTP_200_OK,
    summary="Partially update an owned coefficient option (omitted fields unchanged)",
)
async def update_coefficient_option(
    option_id: uuid.UUID,
    payload: CoefficientOptionUpdate,
    current_user: User = Depends(get_current_user),
    service: PriceCoefficientService = Depends(get_price_coefficient_service),
) -> CoefficientOptionRead:
    try:
        option = await service.update_option(
            current_user.id,
            option_id,
            **payload.model_dump(exclude_unset=True),
        )
    except CoefficientOptionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Coefficient option not found"
        )
    except CoefficientGroupNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Coefficient group not found"
        )
    except PriceCoefficientValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )
    return CoefficientOptionRead.model_validate(option)


@router.post(
    "/price-coefficient-options/{option_id}/archive",
    response_model=CoefficientOptionRead,
    status_code=status.HTTP_200_OK,
    summary="Soft-archive an owned coefficient option (idempotent)",
)
async def archive_coefficient_option(
    option_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: PriceCoefficientService = Depends(get_price_coefficient_service),
) -> CoefficientOptionRead:
    try:
        option = await service.archive_option(current_user.id, option_id)
    except CoefficientOptionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Coefficient option not found"
        )
    return CoefficientOptionRead.model_validate(option)


@router.post(
    "/price-coefficient-options/{option_id}/restore",
    response_model=CoefficientOptionRead,
    status_code=status.HTTP_200_OK,
    summary="Restore an archived owned coefficient option (idempotent)",
)
async def restore_coefficient_option(
    option_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: PriceCoefficientService = Depends(get_price_coefficient_service),
) -> CoefficientOptionRead:
    try:
        option = await service.restore_option(current_user.id, option_id)
    except CoefficientOptionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Coefficient option not found"
        )
    return CoefficientOptionRead.model_validate(option)
