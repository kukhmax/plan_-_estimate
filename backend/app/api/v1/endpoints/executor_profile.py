from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.domain.exceptions import ExecutorProfileValidationError
from app.domain.services.executor_profile_service import ExecutorProfileService
from app.models.user import User
from app.schemas.executor_profile import (
    ExecutorProfileRead,
    ExecutorProfileResponse,
    ExecutorProfileWrite,
)

router = APIRouter()


@router.get(
    "/executor-profile",
    response_model=ExecutorProfileResponse,
    status_code=status.HTTP_200_OK,
    summary="The authenticated owner's executor profile (null until it is filled in)",
)
async def get_executor_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExecutorProfileResponse:
    profile = await ExecutorProfileService(db).get(current_user.id)
    return ExecutorProfileResponse(profile=ExecutorProfileRead.model_validate(profile) if profile else None)


@router.put(
    "/executor-profile",
    response_model=ExecutorProfileRead,
    status_code=status.HTTP_200_OK,
    summary="Create or replace the authenticated owner's executor profile",
)
async def put_executor_profile(
    payload: ExecutorProfileWrite,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExecutorProfileRead:
    try:
        profile = await ExecutorProfileService(db).save(current_user.id, payload)
    except ExecutorProfileValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"code": exc.code, "message": "The executor profile has invalid fields.", "fields": exc.fields},
        ) from None
    return ExecutorProfileRead.model_validate(profile)
