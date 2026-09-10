import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user, get_opening_service
from app.domain.exceptions import (
    DeductionExceedsGrossAreaError,
    InvalidSurfaceTypeError,
    OpeningNotFoundError,
    ProjectNotFoundError,
    RoomNotFoundError,
    SurfaceNotFoundError,
)
from app.domain.services.opening_service import OpeningService
from app.models.user import User
from app.schemas.opening import (
    OpeningCreate,
    OpeningListResponse,
    OpeningRead,
    OpeningUpdate,
)

router = APIRouter()


@router.get(
    "/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}/openings",
    response_model=OpeningListResponse,
    status_code=status.HTTP_200_OK,
    summary="List openings for a surface",
)
async def list_openings(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    surface_id: uuid.UUID,
    include_archived: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    opening_service: OpeningService = Depends(get_opening_service),
) -> OpeningListResponse:
    try:
        items, total = await opening_service.list_openings(
            project_id,
            room_id,
            surface_id,
            owner_id=current_user.id,
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
    except SurfaceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Surface not found",
        )
    return OpeningListResponse(
        items=[OpeningRead.model_validate(opening) for opening in items],
        total=total,
    )


@router.post(
    "/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}/openings",
    response_model=OpeningRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an opening inside a wall surface",
)
async def create_opening(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    surface_id: uuid.UUID,
    payload: OpeningCreate,
    current_user: User = Depends(get_current_user),
    opening_service: OpeningService = Depends(get_opening_service),
) -> OpeningRead:
    try:
        opening = await opening_service.create_opening(
            project_id,
            room_id,
            surface_id,
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
    except SurfaceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Surface not found",
        )
    except InvalidSurfaceTypeError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except DeductionExceedsGrossAreaError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    return OpeningRead.model_validate(opening)


@router.get(
    "/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}/openings/{opening_id}",
    response_model=OpeningRead,
    status_code=status.HTTP_200_OK,
    summary="Get an opening from a surface",
)
async def get_opening(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    surface_id: uuid.UUID,
    opening_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    opening_service: OpeningService = Depends(get_opening_service),
) -> OpeningRead:
    try:
        opening = await opening_service.get_opening(
            project_id,
            room_id,
            surface_id,
            opening_id,
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
    except SurfaceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Surface not found",
        )
    except OpeningNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Opening not found",
        )
    return OpeningRead.model_validate(opening)


@router.patch(
    "/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}/openings/{opening_id}",
    response_model=OpeningRead,
    status_code=status.HTTP_200_OK,
    summary="Partially update an opening",
)
async def update_opening(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    surface_id: uuid.UUID,
    opening_id: uuid.UUID,
    payload: OpeningUpdate,
    current_user: User = Depends(get_current_user),
    opening_service: OpeningService = Depends(get_opening_service),
) -> OpeningRead:
    try:
        opening = await opening_service.update_opening(
            project_id,
            room_id,
            surface_id,
            opening_id,
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
    except SurfaceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Surface not found",
        )
    except OpeningNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Opening not found",
        )
    except DeductionExceedsGrossAreaError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    return OpeningRead.model_validate(opening)


@router.post(
    "/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}/openings/{opening_id}/archive",
    response_model=OpeningRead,
    status_code=status.HTTP_200_OK,
    summary="Archive an opening",
)
async def archive_opening(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    surface_id: uuid.UUID,
    opening_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    opening_service: OpeningService = Depends(get_opening_service),
) -> OpeningRead:
    try:
        opening = await opening_service.archive_opening(
            project_id,
            room_id,
            surface_id,
            opening_id,
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
    except SurfaceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Surface not found",
        )
    except OpeningNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Opening not found",
        )
    return OpeningRead.model_validate(opening)


@router.post(
    "/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}/openings/{opening_id}/restore",
    response_model=OpeningRead,
    status_code=status.HTTP_200_OK,
    summary="Restore an archived opening",
)
async def restore_opening(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    surface_id: uuid.UUID,
    opening_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    opening_service: OpeningService = Depends(get_opening_service),
) -> OpeningRead:
    try:
        opening = await opening_service.restore_opening(
            project_id,
            room_id,
            surface_id,
            opening_id,
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
    except SurfaceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Surface not found",
        )
    except OpeningNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Opening not found",
        )
    except DeductionExceedsGrossAreaError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    return OpeningRead.model_validate(opening)
