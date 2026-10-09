"""Works of other contractors on an object (Stage 16D.1): the register the production plan and the contract refer to."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_adjacent_work_service, get_current_user
from app.domain.exceptions import (
    AdjacentWorkNotFoundError,
    AdjacentWorkPeriodInvalidError,
    AdjacentWorkRoomInvalidError,
    ProjectNotFoundError,
)
from app.domain.services.adjacent_work_service import AdjacentWorkService
from app.models.user import User
from app.schemas.adjacent_work import (
    AdjacentWorkCreate,
    AdjacentWorkListResponse,
    AdjacentWorkRead,
    AdjacentWorkUpdate,
)

router = APIRouter()
BASE = "/projects/{project_id}/adjacent-works"
FAILURES = (ProjectNotFoundError, AdjacentWorkNotFoundError, AdjacentWorkRoomInvalidError, AdjacentWorkPeriodInvalidError)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, AdjacentWorkNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Adjacent work not found")
    if isinstance(exc, (AdjacentWorkRoomInvalidError, AdjacentWorkPeriodInvalidError)):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": exc.code, "message": str(exc)}
        )
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")


@router.get(BASE, response_model=AdjacentWorkListResponse, summary="Works of other contractors on an object")
async def list_adjacent_works(
    project_id: uuid.UUID,
    include_archived: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    service: AdjacentWorkService = Depends(get_adjacent_work_service),
) -> AdjacentWorkListResponse:
    try:
        rows, total = await service.list(project_id, current_user.id, include_archived=include_archived)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return AdjacentWorkListResponse(items=[AdjacentWorkRead.model_validate(r) for r in rows], total=total)


@router.post(BASE, response_model=AdjacentWorkRead, status_code=status.HTTP_201_CREATED, summary="Add an adjacent work")
async def create_adjacent_work(
    project_id: uuid.UUID,
    payload: AdjacentWorkCreate,
    current_user: User = Depends(get_current_user),
    service: AdjacentWorkService = Depends(get_adjacent_work_service),
) -> AdjacentWorkRead:
    try:
        row = await service.create(project_id, current_user.id, payload)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return AdjacentWorkRead.model_validate(row)


@router.patch(BASE + "/{work_id}", response_model=AdjacentWorkRead, summary="Change an adjacent work")
async def update_adjacent_work(
    project_id: uuid.UUID,
    work_id: uuid.UUID,
    payload: AdjacentWorkUpdate,
    current_user: User = Depends(get_current_user),
    service: AdjacentWorkService = Depends(get_adjacent_work_service),
) -> AdjacentWorkRead:
    try:
        row = await service.update(project_id, work_id, current_user.id, payload)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return AdjacentWorkRead.model_validate(row)


@router.post(BASE + "/{work_id}/archive", response_model=AdjacentWorkRead, summary="Archive an adjacent work")
async def archive_adjacent_work(
    project_id: uuid.UUID,
    work_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: AdjacentWorkService = Depends(get_adjacent_work_service),
) -> AdjacentWorkRead:
    try:
        row = await service.set_archived(project_id, work_id, current_user.id, True)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return AdjacentWorkRead.model_validate(row)


@router.post(BASE + "/{work_id}/restore", response_model=AdjacentWorkRead, summary="Restore an adjacent work")
async def restore_adjacent_work(
    project_id: uuid.UUID,
    work_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: AdjacentWorkService = Depends(get_adjacent_work_service),
) -> AdjacentWorkRead:
    try:
        row = await service.set_archived(project_id, work_id, current_user.id, False)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return AdjacentWorkRead.model_validate(row)
