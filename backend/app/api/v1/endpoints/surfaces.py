import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user, get_surface_service, get_wall_merge_service
from app.domain.exceptions import (
    CanonicalPlaneConflictError,
    DeductionExceedsGrossAreaError,
    ProjectNotFoundError,
    RoomNotFoundError,
    SurfaceNotFoundError,
    WallGenerationConflictError,
    WallGenerationDimensionsMissingError,
    WallMergeError,
)
from app.domain.services.surface_service import SurfaceService
from app.domain.services.wall_merge_service import WallMergeService
from app.models.user import User
from app.schemas.surface import (
    SurfaceCreate,
    SurfaceDuplicate,
    SurfaceListResponse,
    SurfaceMergeRequest,
    SurfacePartUpdate,
    SurfaceRead,
    SurfaceReorder,
    SurfaceUnmerge,
    SurfaceUpdate,
)

router = APIRouter()

_MERGE_INPUT_CODES = {"WALL_MERGE_NEED_TWO", "WALL_REORDER_NEED_TWO", "WALL_REORDER_NOT_ACTIVE_WALL", "WALL_MERGE_TOO_MANY", "WALL_MERGE_NOT_A_WALL", "WALL_MERGE_NO_SIZE"}


def _merge_http(error: WallMergeError) -> HTTPException:
    """A refused merge / unmerge: 422 for a wrong choice of walls, 409 for the state of the walls; the screen translates the code."""
    http_status = 422 if error.code in _MERGE_INPUT_CODES else status.HTTP_409_CONFLICT
    return HTTPException(status_code=http_status, detail={"code": error.code, "message": error.message})


def _not_found(error: Exception) -> HTTPException:
    if isinstance(error, ProjectNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if isinstance(error, RoomNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Surface not found")



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
    "/projects/{project_id}/rooms/{room_id}/surfaces/generate",
    response_model=SurfaceListResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate canonical rectangular walls for a room",
)
async def generate_walls(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    surface_service: SurfaceService = Depends(get_surface_service),
) -> SurfaceListResponse:
    try:
        items = await surface_service.generate_walls(
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
    except WallGenerationDimensionsMissingError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except WallGenerationConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    return SurfaceListResponse(
        items=[SurfaceRead.model_validate(surface) for surface in items],
        total=len(items),
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
    except CanonicalPlaneConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
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
    except DeductionExceedsGrossAreaError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )
    except CanonicalPlaneConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except WallMergeError as e:
        raise _merge_http(e)
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
    except CanonicalPlaneConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
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
    except CanonicalPlaneConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except WallMergeError as e:
        raise _merge_http(e)
    return SurfaceRead.model_validate(surface)


@router.post(
    "/projects/{project_id}/rooms/{room_id}/surfaces/merge",
    response_model=SurfaceRead,
    status_code=status.HTTP_200_OK,
    summary="Merge walls into one (the first chosen wall stays, the others are archived into it)",
)
async def merge_surfaces(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    payload: SurfaceMergeRequest,
    current_user: User = Depends(get_current_user),
    merge_service: WallMergeService = Depends(get_wall_merge_service),
) -> SurfaceRead:
    try:
        surface = await merge_service.merge(project_id, room_id, current_user.id, payload.surface_ids)
    except (ProjectNotFoundError, RoomNotFoundError, SurfaceNotFoundError) as e:
        raise _not_found(e)
    except WallMergeError as e:
        raise _merge_http(e)
    return SurfaceRead.model_validate(surface)


@router.post(
    "/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}/unmerge",
    response_model=SurfaceRead,
    status_code=status.HTTP_200_OK,
    summary="Separate a merged wall: the joined walls come back with their photos and openings",
)
async def unmerge_surface(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    surface_id: uuid.UUID,
    payload: SurfaceUnmerge | None = None,
    current_user: User = Depends(get_current_user),
    merge_service: WallMergeService = Depends(get_wall_merge_service),
) -> SurfaceRead:
    try:
        surface = await merge_service.unmerge(project_id, room_id, current_user.id, surface_id, payload.names if payload else None)
    except (ProjectNotFoundError, RoomNotFoundError, SurfaceNotFoundError) as e:
        raise _not_found(e)
    except WallMergeError as e:
        raise _merge_http(e)
    return SurfaceRead.model_validate(surface)


@router.patch(
    "/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}/parts/{part_id}",
    response_model=SurfaceRead,
    status_code=status.HTTP_200_OK,
    summary="Change the size of one part of a merged wall",
)
async def update_surface_part(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    surface_id: uuid.UUID,
    part_id: uuid.UUID,
    payload: SurfacePartUpdate,
    current_user: User = Depends(get_current_user),
    merge_service: WallMergeService = Depends(get_wall_merge_service),
) -> SurfaceRead:
    try:
        surface = await merge_service.update_part(
            project_id, room_id, current_user.id, surface_id, part_id, payload.width, payload.height
        )
    except (ProjectNotFoundError, RoomNotFoundError, SurfaceNotFoundError) as e:
        raise _not_found(e)
    except WallMergeError as e:
        raise _merge_http(e)
    return SurfaceRead.model_validate(surface)


@router.post(
    "/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}/duplicate-merged",
    response_model=SurfaceRead,
    status_code=status.HTTP_201_CREATED,
    summary="Duplicate a merged wall: a new merged wall with the same parts",
)
async def duplicate_merged_surface(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    surface_id: uuid.UUID,
    payload: SurfaceDuplicate,
    current_user: User = Depends(get_current_user),
    merge_service: WallMergeService = Depends(get_wall_merge_service),
) -> SurfaceRead:
    try:
        surface = await merge_service.duplicate(project_id, room_id, current_user.id, surface_id, payload.name, payload.position)
    except (ProjectNotFoundError, RoomNotFoundError, SurfaceNotFoundError) as e:
        raise _not_found(e)
    except WallMergeError as e:
        raise _merge_http(e)
    return SurfaceRead.model_validate(surface)


@router.post(
    "/projects/{project_id}/rooms/{room_id}/surfaces/reorder",
    response_model=SurfaceListResponse,
    status_code=status.HTTP_200_OK,
    summary="Set the order of the active walls of an irregular room",
)
async def reorder_surfaces(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    payload: SurfaceReorder,
    current_user: User = Depends(get_current_user),
    surface_service: SurfaceService = Depends(get_surface_service),
) -> SurfaceListResponse:
    try:
        await surface_service.reorder_walls(project_id, room_id, current_user.id, payload.surface_ids)
        surfaces, total = await surface_service.list_surfaces(project_id, room_id, current_user.id)
    except (ProjectNotFoundError, RoomNotFoundError, SurfaceNotFoundError) as e:
        raise _not_found(e)
    except WallMergeError as e:
        raise _merge_http(e)
    return SurfaceListResponse(items=[SurfaceRead.model_validate(surface) for surface in surfaces], total=total)
