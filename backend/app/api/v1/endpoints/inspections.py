import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user, get_inspection_service
from app.domain.exceptions import (
    ChecklistTemplateNotFoundError,
    InspectionAnswerValidationError,
    InspectionNotFoundError,
    InspectionStateError,
    InvalidInspectionTargetError,
    InvalidSurfaceTypeError,
    ProjectNotFoundError,
    QualityScaleMismatchError,
    RoomNotFoundError,
    SubstrateTemplateMismatchError,
    SurfaceNotFoundError,
)
from app.domain.services.inspection_service import InspectionService
from app.models.user import User
from app.schemas.inspection import (
    InspectionAnswerListResponse,
    InspectionAnswerRead,
    InspectionAnswersPut,
    InspectionCreate,
    InspectionDetailRead,
    InspectionFindingListResponse,
    InspectionFindingRead,
    InspectionListResponse,
    InspectionRead,
    InspectionUpdate,
)

router = APIRouter()


@router.get(
    "/projects/{project_id}/rooms/{room_id}/inspections",
    response_model=InspectionListResponse,
    status_code=status.HTTP_200_OK,
    summary="List substrate inspections for a room",
)
async def list_inspections(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    include_archived: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    inspection_service: InspectionService = Depends(get_inspection_service),
) -> InspectionListResponse:
    try:
        items, total = await inspection_service.list_inspections(
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
    return InspectionListResponse(
        items=[InspectionRead.model_validate(item) for item in items],
        total=total,
    )


@router.post(
    "/projects/{project_id}/rooms/{room_id}/inspections",
    response_model=InspectionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Start a substrate inspection in a room",
)
async def create_inspection(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    payload: InspectionCreate,
    current_user: User = Depends(get_current_user),
    inspection_service: InspectionService = Depends(get_inspection_service),
) -> InspectionRead:
    try:
        inspection = await inspection_service.create_inspection(
            project_id,
            room_id,
            owner_id=current_user.id,
            payload=payload,
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
    except ChecklistTemplateNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Checklist template not found",
        )
    except (
        InvalidInspectionTargetError,
        InvalidSurfaceTypeError,
        QualityScaleMismatchError,
        SubstrateTemplateMismatchError,
    ) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    return InspectionRead.model_validate(inspection)


@router.get(
    "/projects/{project_id}/rooms/{room_id}/inspections/{inspection_id}",
    response_model=InspectionDetailRead,
    status_code=status.HTTP_200_OK,
    summary="Get an inspection with its current answers",
)
async def get_inspection(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    inspection_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    inspection_service: InspectionService = Depends(get_inspection_service),
) -> InspectionDetailRead:
    try:
        inspection = await inspection_service.get_inspection(
            project_id,
            room_id,
            inspection_id,
            owner_id=current_user.id,
        )
        answers = await inspection_service.list_answers(
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
    detail = InspectionDetailRead.model_validate(inspection)
    detail.answers = [
        InspectionAnswerRead.model_validate(answer) for answer in answers
    ]
    return detail


@router.patch(
    "/projects/{project_id}/rooms/{room_id}/inspections/{inspection_id}",
    response_model=InspectionRead,
    status_code=status.HTTP_200_OK,
    summary="Update inspection substrate, quality target, or notes",
)
async def update_inspection(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    inspection_id: uuid.UUID,
    payload: InspectionUpdate,
    current_user: User = Depends(get_current_user),
    inspection_service: InspectionService = Depends(get_inspection_service),
) -> InspectionRead:
    try:
        inspection = await inspection_service.update_inspection(
            project_id,
            room_id,
            inspection_id,
            owner_id=current_user.id,
            payload=payload,
        )
    except (ProjectNotFoundError, RoomNotFoundError, InspectionNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inspection not found",
        )
    except (QualityScaleMismatchError, SubstrateTemplateMismatchError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except InspectionStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    return InspectionRead.model_validate(inspection)


@router.get(
    "/projects/{project_id}/rooms/{room_id}/inspections/{inspection_id}/answers",
    response_model=InspectionAnswerListResponse,
    status_code=status.HTTP_200_OK,
    summary="List answers for an inspection",
)
async def list_answers(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    inspection_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    inspection_service: InspectionService = Depends(get_inspection_service),
) -> InspectionAnswerListResponse:
    try:
        answers = await inspection_service.list_answers(
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
    return InspectionAnswerListResponse(
        items=[InspectionAnswerRead.model_validate(answer) for answer in answers],
        total=len(answers),
    )


@router.put(
    "/projects/{project_id}/rooms/{room_id}/inspections/{inspection_id}/answers",
    response_model=InspectionAnswerListResponse,
    status_code=status.HTTP_200_OK,
    summary="Replace the full set of answers for a DRAFT inspection",
)
async def replace_answers(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    inspection_id: uuid.UUID,
    payload: InspectionAnswersPut,
    current_user: User = Depends(get_current_user),
    inspection_service: InspectionService = Depends(get_inspection_service),
) -> InspectionAnswerListResponse:
    try:
        answers = await inspection_service.replace_answers(
            project_id,
            room_id,
            inspection_id,
            owner_id=current_user.id,
            payload=payload,
        )
    except (ProjectNotFoundError, RoomNotFoundError, InspectionNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inspection not found",
        )
    except InspectionAnswerValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )
    except InspectionStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    return InspectionAnswerListResponse(
        items=[InspectionAnswerRead.model_validate(answer) for answer in answers],
        total=len(answers),
    )


@router.post(
    "/projects/{project_id}/rooms/{room_id}/inspections/{inspection_id}/complete",
    response_model=InspectionRead,
    status_code=status.HTTP_200_OK,
    summary="Complete an inspection and materialize its findings",
)
async def complete_inspection(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    inspection_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    inspection_service: InspectionService = Depends(get_inspection_service),
) -> InspectionRead:
    try:
        inspection = await inspection_service.complete_inspection(
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
    except InspectionStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    return InspectionRead.model_validate(inspection)


@router.post(
    "/projects/{project_id}/rooms/{room_id}/inspections/{inspection_id}/reopen",
    response_model=InspectionRead,
    status_code=status.HTTP_200_OK,
    summary="Reopen a completed inspection for rework",
)
async def reopen_inspection(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    inspection_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    inspection_service: InspectionService = Depends(get_inspection_service),
) -> InspectionRead:
    try:
        inspection = await inspection_service.reopen_inspection(
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
    except InspectionStateError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )
    return InspectionRead.model_validate(inspection)


@router.post(
    "/projects/{project_id}/rooms/{room_id}/inspections/{inspection_id}/archive",
    response_model=InspectionRead,
    status_code=status.HTTP_200_OK,
    summary="Archive an inspection",
)
async def archive_inspection(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    inspection_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    inspection_service: InspectionService = Depends(get_inspection_service),
) -> InspectionRead:
    try:
        inspection = await inspection_service.archive_inspection(
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
    return InspectionRead.model_validate(inspection)


@router.post(
    "/projects/{project_id}/rooms/{room_id}/inspections/{inspection_id}/restore",
    response_model=InspectionRead,
    status_code=status.HTTP_200_OK,
    summary="Restore an archived inspection",
)
async def restore_inspection(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    inspection_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    inspection_service: InspectionService = Depends(get_inspection_service),
) -> InspectionRead:
    try:
        inspection = await inspection_service.restore_inspection(
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
    return InspectionRead.model_validate(inspection)


@router.get(
    "/projects/{project_id}/rooms/{room_id}/inspections/{inspection_id}/findings",
    response_model=InspectionFindingListResponse,
    status_code=status.HTTP_200_OK,
    summary="List inspection findings (materialized facts)",
)
async def list_findings(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    inspection_id: uuid.UUID,
    include_inactive: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    inspection_service: InspectionService = Depends(get_inspection_service),
) -> InspectionFindingListResponse:
    try:
        findings = await inspection_service.list_findings(
            project_id,
            room_id,
            inspection_id,
            owner_id=current_user.id,
            include_inactive=include_inactive,
        )
    except (ProjectNotFoundError, RoomNotFoundError, InspectionNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inspection not found",
        )
    return InspectionFindingListResponse(
        items=[InspectionFindingRead.model_validate(finding) for finding in findings],
        total=len(findings),
    )
