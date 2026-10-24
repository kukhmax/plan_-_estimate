"""Room work plan API router (V2-5; docs/V2_5_PLAN_RU.md).

Thin owner-scoped controller: the plan of a whole room and the "back to the plan of the room" of one surface. All rules live in `RoomWorkPlanService`.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, get_room_work_plan_service
from app.domain.exceptions import (
    PriceItemNotFoundError,
    ProjectNotFoundError,
    QualityScaleMismatchError,
    RoomNotFoundError,
    RoomPlanError,
    SurfaceWorkPlanValidationError,
)
from app.domain.services.room_work_plan_service import RoomWorkPlanService
from app.models.user import User
from app.schemas.room_work_plan import RoomWorkPlanResponse, RoomWorkPlanWrite, SurfaceOutcome

router = APIRouter()


def _detail(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


@router.get(
    "/projects/{project_id}/rooms/{room_id}/work-plan",
    response_model=RoomWorkPlanResponse,
    status_code=status.HTTP_200_OK,
    summary="The plan of the works of a room and what each of its walls and its ceiling does with it",
)
async def get_room_work_plan(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: RoomWorkPlanService = Depends(get_room_work_plan_service),
) -> RoomWorkPlanResponse:
    try:
        return await service.get(project_id, room_id, current_user.id)
    except (ProjectNotFoundError, RoomNotFoundError) as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found") from error


@router.put(
    "/projects/{project_id}/rooms/{room_id}/work-plan",
    response_model=RoomWorkPlanResponse,
    status_code=status.HTTP_200_OK,
    summary="Save the plan of the works of a room and bring its walls and its ceiling to it",
)
async def put_room_work_plan(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    payload: RoomWorkPlanWrite,
    current_user: User = Depends(get_current_user),
    service: RoomWorkPlanService = Depends(get_room_work_plan_service),
) -> RoomWorkPlanResponse:
    try:
        return await service.put(project_id, room_id, current_user.id, payload)
    except (ProjectNotFoundError, RoomNotFoundError) as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found") from error
    except QualityScaleMismatchError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_detail("QUALITY_SCALE_MISMATCH", str(error))) from error
    except PriceItemNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_detail("PRICE_ITEM_NOT_FOUND", str(error))) from error
    except SurfaceWorkPlanValidationError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=_detail("WORK_PLAN_INVALID", str(error))) from error


@router.post(
    "/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}/work-plan/follow-room-plan",
    response_model=SurfaceOutcome,
    status_code=status.HTTP_200_OK,
    summary="Bring this wall (or the ceiling) back to the plan of its room",
)
async def follow_room_work_plan(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    surface_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: RoomWorkPlanService = Depends(get_room_work_plan_service),
) -> SurfaceOutcome:
    try:
        return await service.follow(project_id, room_id, surface_id, current_user.id)
    except (ProjectNotFoundError, RoomNotFoundError) as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found") from error
    except RoomPlanError as error:
        code = status.HTTP_409_CONFLICT if error.code == "ROOM_PLAN_STARTED" else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=code, detail=_detail(error.code, error.message)) from error
