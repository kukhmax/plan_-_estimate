import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user, get_risk_service
from app.domain.exceptions import (
    InspectionNotCompletedError,
    InspectionNotFoundError,
    ProjectNotFoundError,
    RiskNotFoundError,
    RoomNotFoundError,
)
from app.domain.services.risk_service import RiskService
from app.models.area_segment import AreaPlane
from app.models.user import User
from app.schemas.risk import (
    RiskDetailRead,
    RiskDetailResponse,
    RiskEvaluateRequest,
    RiskListResponse,
    RiskRead,
)

router = APIRouter()


@router.get(
    "/projects/{project_id}/rooms/{room_id}/risks",
    response_model=RiskListResponse,
    status_code=status.HTTP_200_OK,
    summary="List materialized risks for a room",
)
async def list_risks(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    inspection_id: uuid.UUID | None = Query(default=None),
    surface_id: uuid.UUID | None = Query(default=None),
    plane: AreaPlane | None = Query(default=None),
    risk_status: str = Query(default="active", alias="status"),
    current_user: User = Depends(get_current_user),
    risk_service: RiskService = Depends(get_risk_service),
) -> RiskListResponse:
    try:
        items, total = await risk_service.list_risks(
            project_id,
            room_id,
            owner_id=current_user.id,
            inspection_id=inspection_id,
            surface_id=surface_id,
            plane=plane,
            status=risk_status,
        )
    except (ProjectNotFoundError, RoomNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Room not found",
        )
    return RiskListResponse(
        items=[RiskRead.model_validate(item) for item in items],
        total=total,
    )


@router.get(
    "/projects/{project_id}/rooms/{room_id}/risks/{risk_id}",
    response_model=RiskDetailRead,
    status_code=status.HTTP_200_OK,
    summary="Get a risk with its source inspection findings",
)
async def get_risk(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    risk_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    risk_service: RiskService = Depends(get_risk_service),
) -> RiskDetailRead:
    try:
        risk = await risk_service.get_risk(
            project_id,
            room_id,
            risk_id,
            owner_id=current_user.id,
        )
    except (ProjectNotFoundError, RoomNotFoundError, RiskNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Risk not found",
        )
    return RiskDetailRead.model_validate(risk)


@router.post(
    "/projects/{project_id}/rooms/{room_id}/risks/evaluate",
    response_model=RiskDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate risks for a COMPLETED inspection (idempotent)",
)
async def evaluate_risks(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    payload: RiskEvaluateRequest,
    current_user: User = Depends(get_current_user),
    risk_service: RiskService = Depends(get_risk_service),
) -> RiskDetailResponse:
    try:
        risks = await risk_service.evaluate_risks(
            project_id,
            room_id,
            payload.inspection_id,
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

    links_by_risk = await risk_service.list_source_findings(
        [risk.id for risk in risks]
    )
    for risk in risks:
        risk.source_findings = links_by_risk.get(risk.id, [])
    return RiskDetailResponse(
        items=[RiskDetailRead.model_validate(risk) for risk in risks],
        total=len(risks),
    )
