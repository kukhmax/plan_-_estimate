import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_checklist_service, get_current_user
from app.domain.exceptions import ChecklistTemplateNotFoundError
from app.domain.services.checklist_service import ChecklistService
from app.models.checklist import Substrate
from app.models.user import User
from app.schemas.checklist import (
    ChecklistTemplateListResponse,
    ChecklistTemplateRead,
)

router = APIRouter()


@router.get(
    "/checklist-templates",
    response_model=ChecklistTemplateListResponse,
    status_code=status.HTTP_200_OK,
    summary="List active inspection checklist templates",
)
async def list_checklist_templates(
    substrate: Substrate | None = Query(default=None),
    include_inactive: bool = Query(default=False),
    current_user: User = Depends(get_current_user),
    checklist_service: ChecklistService = Depends(get_checklist_service),
) -> ChecklistTemplateListResponse:
    items, total = await checklist_service.list_templates(
        substrate=substrate,
        include_inactive=include_inactive,
    )
    return ChecklistTemplateListResponse(
        items=[ChecklistTemplateRead.model_validate(item) for item in items],
        total=total,
    )


@router.get(
    "/checklist-templates/{template_id}",
    response_model=ChecklistTemplateRead,
    status_code=status.HTTP_200_OK,
    summary="Get an inspection checklist template with its full structure",
)
async def get_checklist_template(
    template_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    checklist_service: ChecklistService = Depends(get_checklist_service),
) -> ChecklistTemplateRead:
    try:
        template = await checklist_service.get_template(template_id)
    except ChecklistTemplateNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        )
    return ChecklistTemplateRead.model_validate(template)
