"""Price Book API router (Stage 9C).

Thin owner-scoped controller: auth → input validation → service → typed
response. All domain rules live in ``PriceBookService``; this module only maps
domain exceptions to HTTP errors (404 for missing/foreign rows, 422 for domain
validation failures) and bootstraps the owner catalog on the list entry point.
"""
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user, get_price_book_service
from app.domain.exceptions import PriceBookValidationError, PriceItemNotFoundError
from app.domain.services.price_book_service import PriceBookService
from app.models.checklist import QualityLevel
from app.models.price_item import PriceCategory, PriceScope, PriceUnit
from app.models.user import User
from app.schemas.price import (
    PriceItemCreate,
    PriceItemListResponse,
    PriceItemRead,
    PriceItemUpdate,
)

router = APIRouter()


@router.get(
    "/price-items",
    response_model=PriceItemListResponse,
    status_code=status.HTTP_200_OK,
    summary="List the owner's price book (bootstraps the seed catalog)",
)
async def list_price_items(
    archived: Literal["active", "archived", "all"] = Query(
        default="active", description="Archived filter: active (default) / archived / all"
    ),
    category: PriceCategory | None = Query(default=None),
    unit: PriceUnit | None = Query(default=None),
    price_scope: PriceScope | None = Query(default=None),
    quality_level: QualityLevel | None = Query(default=None),
    search: str | None = Query(default=None, max_length=255),
    current_user: User = Depends(get_current_user),
    price_book_service: PriceBookService = Depends(get_price_book_service),
) -> PriceItemListResponse:
    # Bootstrap-on-access: materialize any missing technical seed rows for the
    # owner (idempotent, never overwrites owner edits) before listing.
    await price_book_service.ensure_owner_catalog(current_user.id)
    items = await price_book_service.list_owner_items(
        current_user.id,
        archived=archived,
        category=category,
        unit=unit,
        price_scope=price_scope,
        quality_level=quality_level,
        search=search,
    )
    return PriceItemListResponse(
        items=[PriceItemRead.model_validate(i) for i in items],
        total=len(items),
    )


@router.post(
    "/price-items",
    response_model=PriceItemRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an owner catalog item with a server-generated CUSTOM_* code",
)
async def create_price_item(
    payload: PriceItemCreate,
    current_user: User = Depends(get_current_user),
    price_book_service: PriceBookService = Depends(get_price_book_service),
) -> PriceItemRead:
    try:
        item = await price_book_service.create_custom_item(
            current_user.id,
            category=payload.category,
            unit=payload.unit,
            price=payload.price,
            display_name=payload.display_name,
            price_scope=payload.price_scope,
            quality_level=payload.quality_level,
            currency=payload.currency,
        )
    except PriceBookValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )
    return PriceItemRead.model_validate(item)


@router.get(
    "/price-items/{price_item_id}",
    response_model=PriceItemRead,
    status_code=status.HTTP_200_OK,
    summary="Get an owned price item by ID",
)
async def get_price_item(
    price_item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    price_book_service: PriceBookService = Depends(get_price_book_service),
) -> PriceItemRead:
    try:
        item = await price_book_service.get_owned_item(
            current_user.id, price_item_id
        )
    except PriceItemNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Price item not found"
        )
    return PriceItemRead.model_validate(item)


@router.patch(
    "/price-items/{price_item_id}",
    response_model=PriceItemRead,
    status_code=status.HTTP_200_OK,
    summary="Partially update an owned price item (omitted fields unchanged)",
)
async def update_price_item(
    price_item_id: uuid.UUID,
    payload: PriceItemUpdate,
    current_user: User = Depends(get_current_user),
    price_book_service: PriceBookService = Depends(get_price_book_service),
) -> PriceItemRead:
    try:
        item = await price_book_service.update_item(
            current_user.id,
            price_item_id,
            **payload.model_dump(exclude_unset=True),
        )
    except PriceItemNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Price item not found"
        )
    except PriceBookValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )
    return PriceItemRead.model_validate(item)


@router.post(
    "/price-items/{price_item_id}/archive",
    response_model=PriceItemRead,
    status_code=status.HTTP_200_OK,
    summary="Soft-archive an owned price item (idempotent)",
)
async def archive_price_item(
    price_item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    price_book_service: PriceBookService = Depends(get_price_book_service),
) -> PriceItemRead:
    try:
        item = await price_book_service.archive_item(current_user.id, price_item_id)
    except PriceItemNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Price item not found"
        )
    return PriceItemRead.model_validate(item)


@router.post(
    "/price-items/{price_item_id}/restore",
    response_model=PriceItemRead,
    status_code=status.HTTP_200_OK,
    summary="Restore an archived price item (idempotent)",
)
async def restore_price_item(
    price_item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    price_book_service: PriceBookService = Depends(get_price_book_service),
) -> PriceItemRead:
    try:
        item = await price_book_service.restore_item(current_user.id, price_item_id)
    except PriceItemNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Price item not found"
        )
    return PriceItemRead.model_validate(item)