import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user, get_work_recommendation_service
from app.domain.exceptions import (
    PriceItemNotFoundError,
    ProjectNotFoundError,
    RoomNotFoundError,
    SurfaceWorkPlanNotFoundError,
    SurfaceWorkPlanValidationError,
    WorkRecommendationNotFoundError,
    WorkRecommendationStateError,
    WorkRecommendationTargetError,
)
from app.domain.services.work_recommendation_service import WorkRecommendationService
from app.models.user import User
from app.models.work_recommendation import WorkRecommendation
from app.schemas.work_recommendation import (
    WorkRecommendationAcceptRequest,
    WorkRecommendationEvaluateResponse,
    WorkRecommendationListResponse,
    WorkRecommendationRead,
)

router = APIRouter()


async def _attach_current_price_items(
    service: WorkRecommendationService,
    owner_id: uuid.UUID,
    items: list[WorkRecommendation],
) -> None:
    """Read-time-only PriceBook resolution preview attached as a transient
    attribute for serialization -- never persisted, never resolved_price_item_id.
    """
    price_items_by_code = await service.resolve_current_price_items(owner_id, items)
    for item in items:
        item.current_price_item = price_items_by_code.get(item.recommended_work_code)


@router.get(
    "/projects/{project_id}/rooms/{room_id}/work-recommendations",
    response_model=WorkRecommendationListResponse,
    status_code=status.HTTP_200_OK,
    summary="List a room's work recommendations",
)
async def list_work_recommendations(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    recommendation_status: str = Query(default="active", alias="activity"),
    current_user: User = Depends(get_current_user),
    service: WorkRecommendationService = Depends(get_work_recommendation_service),
) -> WorkRecommendationListResponse:
    try:
        items, total = await service.list_recommendations(
            project_id,
            room_id,
            owner_id=current_user.id,
            activity=recommendation_status,
        )
    except (ProjectNotFoundError, RoomNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )
    await _attach_current_price_items(service, current_user.id, items)
    return WorkRecommendationListResponse(
        items=[WorkRecommendationRead.model_validate(item) for item in items],
        total=total,
    )


@router.post(
    "/projects/{project_id}/rooms/{room_id}/work-recommendations/evaluate",
    response_model=WorkRecommendationEvaluateResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate a room's work recommendations from current Risks/Findings (idempotent)",
)
async def evaluate_work_recommendations(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: WorkRecommendationService = Depends(get_work_recommendation_service),
) -> WorkRecommendationEvaluateResponse:
    try:
        result = await service.evaluate_recommendations(
            project_id, room_id, owner_id=current_user.id
        )
    except (ProjectNotFoundError, RoomNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )
    await _attach_current_price_items(service, current_user.id, result.recommendations)
    return WorkRecommendationEvaluateResponse(
        created=result.created,
        reactivated=result.reactivated,
        unchanged=result.unchanged,
        resolved=result.resolved,
        items=[
            WorkRecommendationRead.model_validate(item)
            for item in result.recommendations
        ],
        total=len(result.recommendations),
    )


@router.post(
    "/projects/{project_id}/work-recommendations/{recommendation_id}/dismiss",
    response_model=WorkRecommendationRead,
    status_code=status.HTTP_200_OK,
    summary="Dismiss a PENDING work recommendation (idempotent)",
)
async def dismiss_work_recommendation(
    project_id: uuid.UUID,
    recommendation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: WorkRecommendationService = Depends(get_work_recommendation_service),
) -> WorkRecommendationRead:
    try:
        recommendation = await service.dismiss(
            project_id, recommendation_id, owner_id=current_user.id
        )
    except (ProjectNotFoundError, WorkRecommendationNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Work recommendation not found",
        )
    except WorkRecommendationStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    await _attach_current_price_items(service, current_user.id, [recommendation])
    return WorkRecommendationRead.model_validate(recommendation)


@router.post(
    "/projects/{project_id}/work-recommendations/{recommendation_id}/accept",
    response_model=WorkRecommendationRead,
    status_code=status.HTTP_200_OK,
    summary="Accept a PENDING work recommendation into its target Surface work plan (idempotent)",
)
async def accept_work_recommendation(
    project_id: uuid.UUID,
    recommendation_id: uuid.UUID,
    payload: WorkRecommendationAcceptRequest | None = None,
    current_user: User = Depends(get_current_user),
    service: WorkRecommendationService = Depends(get_work_recommendation_service),
) -> WorkRecommendationRead:
    price_item_id = payload.price_item_id if payload is not None else None
    try:
        recommendation = await service.accept_recommendation(
            project_id,
            recommendation_id,
            owner_id=current_user.id,
            price_item_id=price_item_id,
        )
    except (ProjectNotFoundError, WorkRecommendationNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Work recommendation not found",
        )
    except SurfaceWorkPlanNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Target surface has no work plan yet",
        )
    except PriceItemNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Price item not found",
        )
    except WorkRecommendationStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    except (WorkRecommendationTargetError, SurfaceWorkPlanValidationError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    # ACCEPTED: show the item actually snapshotted at acceptance
    # (resolved_price_item_id), never a re-resolution by recommended_work_code
    # -- those can legitimately differ after a manual fallback override.
    if recommendation.resolved_price_item_id is not None:
        recommendation.current_price_item = await service.get_price_item_by_id(
            current_user.id, recommendation.resolved_price_item_id
        )
    else:
        await _attach_current_price_items(service, current_user.id, [recommendation])
    return WorkRecommendationRead.model_validate(recommendation)


@router.post(
    "/projects/{project_id}/work-recommendations/{recommendation_id}/reconsider",
    response_model=WorkRecommendationRead,
    status_code=status.HTTP_200_OK,
    summary="Reconsider a DISMISSED work recommendation back to PENDING (idempotent)",
)
async def reconsider_work_recommendation(
    project_id: uuid.UUID,
    recommendation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: WorkRecommendationService = Depends(get_work_recommendation_service),
) -> WorkRecommendationRead:
    try:
        recommendation = await service.reconsider(
            project_id, recommendation_id, owner_id=current_user.id
        )
    except (ProjectNotFoundError, WorkRecommendationNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Work recommendation not found",
        )
    except WorkRecommendationStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    await _attach_current_price_items(service, current_user.id, [recommendation])
    return WorkRecommendationRead.model_validate(recommendation)
