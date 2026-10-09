"""Persons of an object (Stage 16B.2): who acts for each side and who may accept the work and sign the protocols."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user, get_project_representative_service
from app.domain.exceptions import ProjectNotFoundError, ProjectRepresentativeNotFoundError
from app.domain.services.project_representative_service import ProjectRepresentativeService
from app.models.user import User
from app.schemas.project_representative import (
    ProjectRepresentativeCreate,
    ProjectRepresentativeListResponse,
    ProjectRepresentativeRead,
    ProjectRepresentativeUpdate,
)

router = APIRouter()
BASE = "/projects/{project_id}/representatives"


def _not_found(exc: Exception) -> HTTPException:
    detail = "Representative not found" if isinstance(exc, ProjectRepresentativeNotFoundError) else "Project not found"
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


@router.get(BASE, response_model=ProjectRepresentativeListResponse, summary="Persons of an object")
async def list_representatives(
    project_id: uuid.UUID,
    include_archived: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    service: ProjectRepresentativeService = Depends(get_project_representative_service),
) -> ProjectRepresentativeListResponse:
    try:
        rows, total = await service.list(project_id, current_user.id, include_archived=include_archived)
    except ProjectNotFoundError as exc:
        raise _not_found(exc) from exc
    return ProjectRepresentativeListResponse(items=[ProjectRepresentativeRead.model_validate(r) for r in rows], total=total)


@router.post(BASE, response_model=ProjectRepresentativeRead, status_code=status.HTTP_201_CREATED, summary="Add a person")
async def create_representative(
    project_id: uuid.UUID,
    payload: ProjectRepresentativeCreate,
    current_user: User = Depends(get_current_user),
    service: ProjectRepresentativeService = Depends(get_project_representative_service),
) -> ProjectRepresentativeRead:
    try:
        row = await service.create(project_id, current_user.id, payload)
    except ProjectNotFoundError as exc:
        raise _not_found(exc) from exc
    return ProjectRepresentativeRead.model_validate(row)


@router.patch(BASE + "/{representative_id}", response_model=ProjectRepresentativeRead, summary="Change a person")
async def update_representative(
    project_id: uuid.UUID,
    representative_id: uuid.UUID,
    payload: ProjectRepresentativeUpdate,
    current_user: User = Depends(get_current_user),
    service: ProjectRepresentativeService = Depends(get_project_representative_service),
) -> ProjectRepresentativeRead:
    try:
        row = await service.update(project_id, representative_id, current_user.id, payload)
    except (ProjectNotFoundError, ProjectRepresentativeNotFoundError) as exc:
        raise _not_found(exc) from exc
    return ProjectRepresentativeRead.model_validate(row)


@router.post(BASE + "/{representative_id}/archive", response_model=ProjectRepresentativeRead, summary="Archive a person")
async def archive_representative(
    project_id: uuid.UUID,
    representative_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: ProjectRepresentativeService = Depends(get_project_representative_service),
) -> ProjectRepresentativeRead:
    try:
        row = await service.set_archived(project_id, representative_id, current_user.id, True)
    except (ProjectNotFoundError, ProjectRepresentativeNotFoundError) as exc:
        raise _not_found(exc) from exc
    return ProjectRepresentativeRead.model_validate(row)


@router.post(BASE + "/{representative_id}/restore", response_model=ProjectRepresentativeRead, summary="Restore a person")
async def restore_representative(
    project_id: uuid.UUID,
    representative_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: ProjectRepresentativeService = Depends(get_project_representative_service),
) -> ProjectRepresentativeRead:
    try:
        row = await service.set_archived(project_id, representative_id, current_user.id, False)
    except (ProjectNotFoundError, ProjectRepresentativeNotFoundError) as exc:
        raise _not_found(exc) from exc
    return ProjectRepresentativeRead.model_validate(row)
