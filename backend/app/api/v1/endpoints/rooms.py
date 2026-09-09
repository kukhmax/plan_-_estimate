import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user, get_room_service
from app.domain.exceptions import ProjectNotFoundError, RoomNotFoundError
from app.domain.services.room_service import RoomService
from app.models.user import User
from app.schemas.room import RoomCreate, RoomListResponse, RoomRead, RoomUpdate

router = APIRouter()


@router.get(
    "/projects/{project_id}/rooms",
    response_model=RoomListResponse,
    status_code=status.HTTP_200_OK,
    summary="List rooms for a project",
)
async def list_rooms(
    project_id: uuid.UUID,
    include_archived: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    room_service: RoomService = Depends(get_room_service),
) -> RoomListResponse:
    try:
        items, total = await room_service.list_rooms(
            project_id,
            owner_id=current_user.id,
            include_archived=include_archived,
        )
    except ProjectNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    return RoomListResponse(
        items=[RoomRead.model_validate(room) for room in items],
        total=total,
    )


@router.post(
    "/projects/{project_id}/rooms",
    response_model=RoomRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a room inside a project",
)
async def create_room(
    project_id: uuid.UUID,
    payload: RoomCreate,
    current_user: User = Depends(get_current_user),
    room_service: RoomService = Depends(get_room_service),
) -> RoomRead:
    try:
        room = await room_service.create_room(
            project_id,
            payload,
            owner_id=current_user.id,
        )
    except ProjectNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )
    return RoomRead.model_validate(room)


@router.get(
    "/projects/{project_id}/rooms/{room_id}",
    response_model=RoomRead,
    status_code=status.HTTP_200_OK,
    summary="Get a room from a project",
)
async def get_room(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    room_service: RoomService = Depends(get_room_service),
) -> RoomRead:
    try:
        room = await room_service.get_room(
            project_id,
            room_id,
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
    return RoomRead.model_validate(room)


@router.patch(
    "/projects/{project_id}/rooms/{room_id}",
    response_model=RoomRead,
    status_code=status.HTTP_200_OK,
    summary="Partially update a room",
)
async def update_room(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    payload: RoomUpdate,
    current_user: User = Depends(get_current_user),
    room_service: RoomService = Depends(get_room_service),
) -> RoomRead:
    try:
        room = await room_service.update_room(
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
    return RoomRead.model_validate(room)


@router.post(
    "/projects/{project_id}/rooms/{room_id}/archive",
    response_model=RoomRead,
    status_code=status.HTTP_200_OK,
    summary="Archive a room",
)
async def archive_room(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    room_service: RoomService = Depends(get_room_service),
) -> RoomRead:
    try:
        room = await room_service.archive_room(
            project_id,
            room_id,
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
    return RoomRead.model_validate(room)


@router.post(
    "/projects/{project_id}/rooms/{room_id}/restore",
    response_model=RoomRead,
    status_code=status.HTTP_200_OK,
    summary="Restore an archived room",
)
async def restore_room(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    room_service: RoomService = Depends(get_room_service),
) -> RoomRead:
    try:
        room = await room_service.restore_room(
            project_id,
            room_id,
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
    return RoomRead.model_validate(room)
