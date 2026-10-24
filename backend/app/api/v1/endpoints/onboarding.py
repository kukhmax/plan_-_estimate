"""Onboarding API router (V2-3; docs/V2_3_PLAN_RU.md).

Thin owner-scoped controller: the starter prices of a new contractor and the example object of the account (the same demo data as the
command `python -m app.cli.demo`, without prices). All rules live in `PriceBookService` and `DemoDataService`.
"""
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, get_demo_data_service, get_price_book_service
from app.domain.exceptions import (
    ClientHasProjectsError,
    ProjectPurgeBlockedError,
    ProjectPurgeConflictError,
)
from app.domain.services.demo_data_service import DemoDataService
from app.domain.services.price_book_service import PriceBookService
from app.models.user import User
from app.schemas.onboarding import ExampleCreated, ExampleRemoved, ExampleStatus
from app.schemas.price import PriceItemListResponse, PriceItemRead

router = APIRouter()


@router.get(
    "/onboarding/starter-prices",
    response_model=PriceItemListResponse,
    status_code=status.HTTP_200_OK,
    summary="The five price rows a new contractor sets first",
)
async def starter_prices(
    current_user: User = Depends(get_current_user),
    price_book_service: PriceBookService = Depends(get_price_book_service),
) -> PriceItemListResponse:
    items = await price_book_service.list_starter_items(current_user.id)
    return PriceItemListResponse(items=[PriceItemRead.model_validate(i) for i in items], total=len(items))


@router.get(
    "/onboarding/example",
    response_model=ExampleStatus,
    status_code=status.HTTP_200_OK,
    summary="The example object of the account, if it has one",
)
async def example_status(
    current_user: User = Depends(get_current_user),
    service: DemoDataService = Depends(get_demo_data_service),
) -> ExampleStatus:
    found = await service.status(current_user.id)
    return ExampleStatus(project_id=found.project_id, client_id=found.client_id)


@router.post(
    "/onboarding/example",
    response_model=ExampleCreated,
    status_code=status.HTTP_200_OK,
    summary="Make the example object (idempotent; no prices are set)",
)
async def example_create(
    current_user: User = Depends(get_current_user),
    service: DemoDataService = Depends(get_demo_data_service),
) -> ExampleCreated:
    result = await service.seed(current_user.id, with_prices=False)
    found = await service.status(current_user.id)
    return ExampleCreated(project_id=found.project_id, client_id=found.client_id, created=result.created_objects)


@router.delete(
    "/onboarding/example",
    response_model=ExampleRemoved,
    status_code=status.HTTP_200_OK,
    summary="Delete the example object and its client for good (prices are not touched)",
)
async def example_remove(
    current_user: User = Depends(get_current_user),
    service: DemoDataService = Depends(get_demo_data_service),
) -> ExampleRemoved:
    try:
        result = await service.remove(current_user.id, reset_prices=False)
    except (ProjectPurgeBlockedError, ProjectPurgeConflictError) as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": error.code, "message": str(error)}) from error
    except ClientHasProjectsError as error:  # the client is kept by the service; this is not reached, kept for a defensive answer
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "CLIENT_HAS_PROJECTS", "message": str(error)}) from error
    return ExampleRemoved(removed_project=result.removed_project, removed_client=result.removed_client)
