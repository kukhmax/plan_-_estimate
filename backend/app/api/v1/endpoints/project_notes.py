"""Notes of the owner on an object (Stage 18): thin routes over `ProjectNoteService`."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import get_current_user, get_project_note_service
from app.domain.exceptions import (
    ProjectNoteInvalidError,
    ProjectNoteNotFoundError,
    ProjectNotFoundError,
)
from app.domain.services.project_note_service import ProjectNoteService
from app.models.user import User
from app.schemas.project_note import (
    ProjectNoteListResponse,
    ProjectNoteRead,
    ProjectNoteCreate,
    ProjectNoteWrite,
)

router = APIRouter()


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ProjectNoteNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Note not found")
    if isinstance(exc, ProjectNoteInvalidError):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": exc.code, "message": str(exc)})
    return HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")


FAILURES = (ProjectNotFoundError, ProjectNoteNotFoundError, ProjectNoteInvalidError)


@router.get("/projects/{project_id}/notes", response_model=ProjectNoteListResponse, summary="The notes of an object, the newest first")
async def list_notes(
    project_id: uuid.UUID, current_user: User = Depends(get_current_user), service: ProjectNoteService = Depends(get_project_note_service)
) -> ProjectNoteListResponse:
    try:
        items, total = await service.list_notes(current_user.id, project_id)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return ProjectNoteListResponse(items=[ProjectNoteRead.model_validate(item) for item in items], total=total)


@router.post("/projects/{project_id}/notes", response_model=ProjectNoteRead, status_code=status.HTTP_201_CREATED, summary="Write a note")
async def create_note(
    project_id: uuid.UUID,
    payload: ProjectNoteCreate,
    current_user: User = Depends(get_current_user),
    service: ProjectNoteService = Depends(get_project_note_service),
) -> ProjectNoteRead:
    try:
        note = await service.create_note(current_user.id, project_id, payload.body, client_id=payload.id)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return ProjectNoteRead.model_validate(note)


@router.patch("/projects/{project_id}/notes/{note_id}", response_model=ProjectNoteRead, summary="Change the words of a note")
async def update_note(
    project_id: uuid.UUID,
    note_id: uuid.UUID,
    payload: ProjectNoteWrite,
    current_user: User = Depends(get_current_user),
    service: ProjectNoteService = Depends(get_project_note_service),
) -> ProjectNoteRead:
    try:
        note = await service.update_note(current_user.id, project_id, note_id, payload.body)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return ProjectNoteRead.model_validate(note)


@router.delete("/projects/{project_id}/notes/{note_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Remove a note")
async def delete_note(
    project_id: uuid.UUID,
    note_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: ProjectNoteService = Depends(get_project_note_service),
) -> Response:
    try:
        await service.delete_note(current_user.id, project_id, note_id)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
