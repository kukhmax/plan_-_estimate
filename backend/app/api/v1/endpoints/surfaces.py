import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user, get_surface_service
from app.domain.exceptions import (
    ProjectNotFoundError,
    RoomNotFoundError,
    SurfaceNotFoundError,
)
from app.domain.services.surface_service import SurfaceService
from app.models.user import User
from app.schemas.surface import (
    SurfaceCreate,
    SurfaceListResponse,
    SurfaceRead,
    SurfaceUpdate,
)

router = APIRouter()


@router.get(
    "/projects/{project_id}/rooms/{room_id}/surfaces",
    response_model=SurfaceListResponse,
    status_code=status.HTTP_200_OK,
    summary="List surfaces for a room",
)
async def list_surfaces(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    include_archived: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    surface_service: SurfaceService = Depends(get_surface_service),
) -> SurfaceListResponse:
    try:
        items, total = await surface_service.list_surfaces(
            project_id,
            room_id,
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
    return SurfaceListResponse(
        items=[SurfaceRead.model_validate(surface) for surface in items],
        total=total,
    )


@router.post(
    "/projects/{project_id}/rooms/{room_id}/surfaces",
    response_model=SurfaceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a surface inside a room",
)
async def create_surface(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    payload: SurfaceCreate,
    current_user: User = Depends(get_current_user),
    surface_service: SurfaceService = Depends(get_surface_service),
) -> SurfaceRead:
    try:
        surface = await surface_service.create_surface(
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
    return SurfaceRead.model_validate(surface)


@router.get(
    "/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}",
    response_model=SurfaceRead,
    status_code=status.HTTP_200_OK,
    summary="Get a surface from a room",
)
async def get_surface(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    surface_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    surface_service: SurfaceService = Depends(get_surface_service),
) -> SurfaceRead:
    try:
        surface = await surface_service.get_surface(
            project_id,
            room_id,
            surface_id,
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
    return SurfaceRead.model_validate(surface)


@router.patch(
    "/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}",
    response_model=SurfaceRead,
    status_code=status.HTTP_200_OK,
    summary="Partially update a surface",
)
async def update_surface(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    surface_id: uuid.UUID,
    payload: SurfaceUpdate,
    current_user: User = Depends(get_current_user),
    surface_service: SurfaceService = Depends(get_surface_service),
) -> SurfaceRead:
    try:
        surface = await surface_service.update_surface(
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
    return SurfaceRead.model_validate(surface)


@router.post(
    "/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}/archive",
    response_model=SurfaceRead,
    status_code=status.HTTP_200_OK,
    summary="Archive a surface",
)
async def archive_surface(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    surface_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    surface_service: SurfaceService = Depends(get_surface_service),
) -> SurfaceRead:
    try:
        surface = await surface_service.archive_surface(
            project_id,
            room_id,
            surface_id,
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
    return SurfaceRead.model_validate(surface)


@router.post(
    "/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}/restore",
    response_model=SurfaceRead,
    status_code=status.HTTP_200_OK,
    summary="Restore an archived surface",
)
async def restore_surface(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    surface_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    surface_service: SurfaceService = Depends(get_surface_service),
) -> SurfaceRead:
    try:
        surface = await surface_service.restore_surface(
            project_id,
            room_id,
            surface_id,
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
    return SurfaceRead.model_validate(surface)
