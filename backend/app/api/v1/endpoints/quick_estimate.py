"""Quick estimate API router (V2-4; docs/V2_4_PLAN_RU.md).

Thin owner-scoped controller: what the screen offers, and the one request that makes the client, the object, the rooms with their work plans and the
draft estimate. All rules live in `QuickEstimateService`.
"""
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, get_quick_estimate_service
from app.domain.data.quick_estimate_data import QUICK_WORKS
from app.domain.exceptions import QualityScaleMismatchError, QuickEstimateError
from app.domain.services.quick_estimate_service import (
    DEFAULT_QUALITY,
    DEFAULT_SUBSTRATE,
    OFFERED_SUBSTRATES,
    QuickEstimateService,
)
from app.models.user import User
from app.schemas.price import PriceItemRead
from app.schemas.quick_estimate import QuickEstimateCreate, QuickEstimateOptions, QuickEstimateResult, QuickWorkRead

router = APIRouter()


@router.get(
    "/quick-estimate/options",
    response_model=QuickEstimateOptions,
    status_code=status.HTTP_200_OK,
    summary="What the quick estimate offers: the works, the price rows behind them, the substrates and the defaults",
)
async def quick_estimate_options(
    current_user: User = Depends(get_current_user),
    service: QuickEstimateService = Depends(get_quick_estimate_service),
) -> QuickEstimateOptions:
    items = await service.option_items(current_user.id)
    return QuickEstimateOptions(
        works=[QuickWorkRead(code=w.code, ceiling_code=w.ceiling_code, default_on=w.default_on) for w in QUICK_WORKS],
        items=[PriceItemRead.model_validate(i) for i in items],
        substrates=list(OFFERED_SUBSTRATES),
        default_substrate=DEFAULT_SUBSTRATE,
        default_quality=DEFAULT_QUALITY,
    )


@router.post(
    "/quick-estimate",
    response_model=QuickEstimateResult,
    status_code=status.HTTP_201_CREATED,
    summary="Make the client, the object, the rooms with their work plans and the draft estimate in one request",
)
async def quick_estimate_create(
    payload: QuickEstimateCreate,
    current_user: User = Depends(get_current_user),
    service: QuickEstimateService = Depends(get_quick_estimate_service),
) -> QuickEstimateResult:
    try:
        return await service.create(current_user.id, payload)
    except QualityScaleMismatchError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "QUALITY_SCALE_MISMATCH", "message": str(error)}
        ) from error
    except QuickEstimateError as error:
        code = status.HTTP_404_NOT_FOUND if error.code == "CLIENT_NOT_FOUND" else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=code, detail={"code": error.code, "message": error.message}) from error
