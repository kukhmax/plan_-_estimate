import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_area_segment_service, get_current_user
from app.domain.exceptions import (
    AreaSegmentNotFoundError,
    NegativeNetAreaError,
    ProjectNotFoundError,
    RoomNotFoundError,
)
from app.domain.services.area_segment_service import AreaSegmentService
from app.models.area_segment import AreaPlane
from app.models.user import User
from app.schemas.area_segment import (
    AreaSegmentCreate,
    AreaSegmentListResponse,
    AreaSegmentRead,
    AreaSegmentUpdate,
)

router = APIRouter()


@router.get(
    "/projects/{project_id}/rooms/{room_id}/area-segments",
    response_model=AreaSegmentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List area segments for a room",
)
async def list_area_segments(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    plane: AreaPlane | None = Query(default=None),
    include_archived: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    area_segment_service: AreaSegmentService = Depends(get_area_segment_service),
) -> AreaSegmentListResponse:
    try:
        items, total = await area_segment_service.list_area_segments(
            project_id,
            room_id,
            owner_id=current_user.id,
            plane=plane,
            include_archived=include_archived,
        )
    except ProjectNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    except RoomNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )
    return AreaSegmentListResponse(
        items=[AreaSegmentRead.model_validate(segment) for segment in items],
        total=total,
    )


@router.post(
    "/projects/{project_id}/rooms/{room_id}/area-segments",
    response_model=AreaSegmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an area segment on a room plane",
)
async def create_area_segment(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    payload: AreaSegmentCreate,
    current_user: User = Depends(get_current_user),
    area_segment_service: AreaSegmentService = Depends(get_area_segment_service),
) -> AreaSegmentRead:
    try:
        segment = await area_segment_service.create_area_segment(
            project_id,
            room_id,
            payload,
            owner_id=current_user.id,
        )
    except ProjectNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    except RoomNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )
    except NegativeNetAreaError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    return AreaSegmentRead.model_validate(segment)


@router.get(
    "/projects/{project_id}/rooms/{room_id}/area-segments/{segment_id}",
    response_model=AreaSegmentRead,
    status_code=status.HTTP_200_OK,
    summary="Get an area segment from a room",
)
async def get_area_segment(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    segment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    area_segment_service: AreaSegmentService = Depends(get_area_segment_service),
) -> AreaSegmentRead:
    try:
        segment = await area_segment_service.get_area_segment(
            project_id,
            room_id,
            segment_id,
            owner_id=current_user.id,
        )
    except ProjectNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    except RoomNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )
    except AreaSegmentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Area segment not found",
        )
    return AreaSegmentRead.model_validate(segment)


@router.patch(
    "/projects/{project_id}/rooms/{room_id}/area-segments/{segment_id}",
    response_model=AreaSegmentRead,
    status_code=status.HTTP_200_OK,
    summary="Partially update an area segment",
)
async def update_area_segment(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    segment_id: uuid.UUID,
    payload: AreaSegmentUpdate,
    current_user: User = Depends(get_current_user),
    area_segment_service: AreaSegmentService = Depends(get_area_segment_service),
) -> AreaSegmentRead:
    try:
        segment = await area_segment_service.update_area_segment(
            project_id,
            room_id,
            segment_id,
            payload,
            owner_id=current_user.id,
        )
    except ProjectNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    except RoomNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )
    except AreaSegmentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Area segment not found",
        )
    except NegativeNetAreaError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    return AreaSegmentRead.model_validate(segment)


@router.post(
    "/projects/{project_id}/rooms/{room_id}/area-segments/{segment_id}/archive",
    response_model=AreaSegmentRead,
    status_code=status.HTTP_200_OK,
    summary="Archive an area segment",
)
async def archive_area_segment(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    segment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    area_segment_service: AreaSegmentService = Depends(get_area_segment_service),
) -> AreaSegmentRead:
    try:
        segment = await area_segment_service.archive_area_segment(
            project_id,
            room_id,
            segment_id,
            owner_id=current_user.id,
        )
    except ProjectNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    except RoomNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )
    except AreaSegmentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Area segment not found",
        )
    except NegativeNetAreaError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    return AreaSegmentRead.model_validate(segment)


@router.post(
    "/projects/{project_id}/rooms/{room_id}/area-segments/{segment_id}/restore",
    response_model=AreaSegmentRead,
    status_code=status.HTTP_200_OK,
    summary="Restore an archived area segment",
)
async def restore_area_segment(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    segment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    area_segment_service: AreaSegmentService = Depends(get_area_segment_service),
) -> AreaSegmentRead:
    try:
        segment = await area_segment_service.restore_area_segment(
            project_id,
            room_id,
            segment_id,
            owner_id=current_user.id,
        )
    except ProjectNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    except RoomNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )
    except AreaSegmentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Area segment not found",
        )
    except NegativeNetAreaError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    return AreaSegmentRead.model_validate(segment)
