import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_communication_service, get_current_user
from app.domain.exceptions import (
    CommunicationNotFoundError,
    InspectionNotCompletedError,
    InspectionNotFoundError,
    ProjectNotFoundError,
    RoomNotFoundError,
)
from app.domain.services.communication_service import CommunicationService
from app.models.user import User
from app.schemas.communication import (
    CommunicationApplicationDetailRead,
    CommunicationApplicationListResponse,
    CommunicationApplicationRead,
)

router = APIRouter()


@router.get(
    "/projects/{project_id}/rooms/{room_id}/inspections/{inspection_id}/communications",
    response_model=CommunicationApplicationListResponse,
    status_code=status.HTTP_200_OK,
    summary="List communication applications for one inspection",
)
async def list_communications(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    inspection_id: uuid.UUID,
    communication_status: str = Query(default="active", alias="status"),
    current_user: User = Depends(get_current_user),
    communication_service: CommunicationService = Depends(get_communication_service),
) -> CommunicationApplicationListResponse:
    try:
        items, total = await communication_service.list_applications(
            project_id,
            room_id,
            owner_id=current_user.id,
            inspection_id=inspection_id,
            status=communication_status,
        )
    except (ProjectNotFoundError, RoomNotFoundError, InspectionNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inspection not found",
        )
    return CommunicationApplicationListResponse(
        items=[CommunicationApplicationRead.model_validate(item) for item in items],
        total=total,
    )


@router.post(
    "/projects/{project_id}/rooms/{room_id}/inspections/{inspection_id}"
    "/communications/evaluate",
    response_model=CommunicationApplicationListResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate communication phrases for a COMPLETED inspection (idempotent)",
)
async def evaluate_communications(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    inspection_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    communication_service: CommunicationService = Depends(get_communication_service),
) -> CommunicationApplicationListResponse:
    try:
        apps = await communication_service.evaluate_communications(
            project_id,
            room_id,
            inspection_id,
            owner_id=current_user.id,
        )
    except (ProjectNotFoundError, RoomNotFoundError, InspectionNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inspection not found",
        )
    except InspectionNotCompletedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    return CommunicationApplicationListResponse(
        items=[CommunicationApplicationRead.model_validate(app) for app in apps],
        total=len(apps),
    )


@router.get(
    "/projects/{project_id}/rooms/{room_id}/inspections/{inspection_id}"
    "/communications/{communication_id}",
    response_model=CommunicationApplicationDetailRead,
    status_code=status.HTTP_200_OK,
    summary="Get one communication application with its traceability source",
)
async def get_communication(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    inspection_id: uuid.UUID,
    communication_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    communication_service: CommunicationService = Depends(get_communication_service),
) -> CommunicationApplicationDetailRead:
    try:
        app = await communication_service.get_application(
            project_id,
            room_id,
            inspection_id,
            communication_id,
            owner_id=current_user.id,
        )
    except (ProjectNotFoundError, RoomNotFoundError, CommunicationNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Communication not found",
        )
    source = await communication_service.build_source(app)
    return CommunicationApplicationDetailRead(
        **CommunicationApplicationRead.model_validate(app).model_dump(),
        source=source,
    )