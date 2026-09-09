import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user, get_project_service
from app.domain.exceptions import ClientNotFoundError, ProjectNotFoundError
from app.domain.services.project_service import ProjectService
from app.models.user import User
from app.schemas.project import (
    ProjectCreate,
    ProjectListResponse,
    ProjectRead,
    ProjectUpdate,
)

router = APIRouter()


@router.get(
    "/projects",
    response_model=ProjectListResponse,
    status_code=status.HTTP_200_OK,
    summary="List projects for the authenticated owner",
)
async def list_projects(
    include_archived: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
) -> ProjectListResponse:
    items, total = await project_service.list_projects(
        owner_id=current_user.id,
        include_archived=include_archived,
    )
    return ProjectListResponse(
        items=[ProjectRead.model_validate(project) for project in items],
        total=total,
    )


@router.post(
    "/projects",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new project",
)
async def create_project(
    payload: ProjectCreate,
    current_user: User = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
) -> ProjectRead:
    try:
        project = await project_service.create_project(payload, owner_id=current_user.id)
    except ClientNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return ProjectRead.model_validate(project)


@router.get(
    "/projects/{project_id}",
    response_model=ProjectRead,
    status_code=status.HTTP_200_OK,
    summary="Get a specific project by ID",
)
async def get_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
) -> ProjectRead:
    try:
        project = await project_service.get_project(project_id, owner_id=current_user.id)
    except ProjectNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return ProjectRead.model_validate(project)


@router.patch(
    "/projects/{project_id}",
    response_model=ProjectRead,
    status_code=status.HTTP_200_OK,
    summary="Partially update a project",
)
async def update_project(
    project_id: uuid.UUID,
    payload: ProjectUpdate,
    current_user: User = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
) -> ProjectRead:
    try:
        project = await project_service.update_project(
            project_id,
            payload,
            owner_id=current_user.id,
        )
    except ProjectNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    except ClientNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Client not found")
    return ProjectRead.model_validate(project)


@router.post(
    "/projects/{project_id}/archive",
    response_model=ProjectRead,
    status_code=status.HTTP_200_OK,
    summary="Archive a project",
)
async def archive_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
) -> ProjectRead:
    try:
        project = await project_service.archive_project(
            project_id,
            owner_id=current_user.id,
        )
    except ProjectNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return ProjectRead.model_validate(project)


@router.post(
    "/projects/{project_id}/restore",
    response_model=ProjectRead,
    status_code=status.HTTP_200_OK,
    summary="Restore an archived project",
)
async def restore_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    project_service: ProjectService = Depends(get_project_service),
) -> ProjectRead:
    try:
        project = await project_service.restore_project(
            project_id,
            owner_id=current_user.id,
        )
    except ProjectNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return ProjectRead.model_validate(project)
