"""Workflow template API router (Stage 13C).

Thin owner-scoped controller over `WorkflowTemplateService`: auth -> input
validation -> service -> typed response. 404 for missing/foreign templates
and price items (no existence disclosure), 422 for domain validation.

Deliberately absent: an "apply template" endpoint (13E materialises steps into
the local WorkPlan draft and saves through the existing WorkPlan PUT, sending
a provenance intent), a hard-delete endpoint, and default-recipe bootstrap
(13D).
"""
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_current_user, get_workflow_template_service
from app.domain.exceptions import (
    PriceItemNotFoundError,
    WorkflowTemplateNotFoundError,
    WorkflowTemplateValidationError,
)
from app.domain.services.workflow_template_service import (
    WorkflowTemplateService,
    WorkflowTemplateStepSpec,
)
from app.models.checklist import QualityLevel, Substrate
from app.models.surface import SurfaceType
from app.models.user import User
from app.models.workflow_template import WorkflowTemplate
from app.schemas.work_plan import SurfacePriceItemSummaryRead
from app.schemas.workflow_template import (
    WorkflowTemplateCreate,
    WorkflowTemplateListResponse,
    WorkflowTemplateRead,
    WorkflowTemplateStepRead,
    WorkflowTemplateStepsReplace,
    WorkflowTemplateStepWrite,
    WorkflowTemplateUpdate,
)

router = APIRouter()

_NOT_FOUND = "Workflow template not found"


def _template_read(template: WorkflowTemplate) -> WorkflowTemplateRead:
    return WorkflowTemplateRead(
        id=template.id,
        code=template.code,
        name_key=template.name_key,
        display_name=template.display_name,
        description=template.description,
        applies_to_substrates=template.applies_to_substrates or [],
        applies_to_quality=template.applies_to_quality or [],
        applies_to_surface_types=template.applies_to_surface_types or [],
        position=template.position,
        is_archived=template.is_archived,
        created_at=template.created_at,
        updated_at=template.updated_at,
        steps=[
            WorkflowTemplateStepRead(
                id=step.id,
                position=step.position,
                price_item_id=step.price_item_id,
                is_optional=step.is_optional,
                note=step.note,
                wait_after_hours=step.wait_after_hours,
                price_item=SurfacePriceItemSummaryRead.model_validate(step.price_item),
            )
            for step in template.steps
        ],
    )


def _specs(steps: list[WorkflowTemplateStepWrite]) -> list[WorkflowTemplateStepSpec]:
    return [
        WorkflowTemplateStepSpec(
            price_item_id=step.price_item_id,
            is_optional=step.is_optional,
            note=step.note,
            wait_after_hours=step.wait_after_hours,
        )
        for step in steps
    ]


def _map_errors(exc: Exception) -> HTTPException:
    if isinstance(exc, WorkflowTemplateNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    if isinstance(exc, PriceItemNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Price item not found"
        )
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
    )


_DOMAIN_ERRORS = (
    WorkflowTemplateNotFoundError,
    PriceItemNotFoundError,
    WorkflowTemplateValidationError,
)


@router.get(
    "/workflow-templates",
    response_model=WorkflowTemplateListResponse,
    status_code=status.HTTP_200_OK,
    summary="List the owner's workflow templates, optionally matching a plan context",
)
async def list_workflow_templates(
    archived: Literal["active", "archived", "all"] = Query(
        default="active", description="Archived filter: active (default) / archived / all"
    ),
    substrate: Substrate | None = Query(
        default=None, description="Match templates for any substrate or this one"
    ),
    quality_target: QualityLevel | None = Query(
        default=None, description="Match templates for any quality target or this one"
    ),
    surface_type: SurfaceType | None = Query(
        default=None, description="Match templates for any surface type or this one"
    ),
    current_user: User = Depends(get_current_user),
    service: WorkflowTemplateService = Depends(get_workflow_template_service),
) -> WorkflowTemplateListResponse:
    templates = await service.list_owner_templates(
        current_user.id,
        archived=archived,
        substrate=substrate,
        quality_target=quality_target,
        surface_type=surface_type,
    )
    items = [_template_read(t) for t in templates]
    return WorkflowTemplateListResponse(items=items, total=len(items))


@router.post(
    "/workflow-templates",
    response_model=WorkflowTemplateRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create an owner workflow template (server-generated code) with ordered steps",
)
async def create_workflow_template(
    payload: WorkflowTemplateCreate,
    current_user: User = Depends(get_current_user),
    service: WorkflowTemplateService = Depends(get_workflow_template_service),
) -> WorkflowTemplateRead:
    try:
        template = await service.create_template(
            current_user.id,
            display_name=payload.display_name,
            description=payload.description,
            applies_to_substrates=payload.applies_to_substrates,
            applies_to_quality=payload.applies_to_quality,
            applies_to_surface_types=payload.applies_to_surface_types,
            steps=_specs(payload.steps),
        )
    except _DOMAIN_ERRORS as e:
        raise _map_errors(e)
    return _template_read(template)


@router.get(
    "/workflow-templates/{template_id}",
    response_model=WorkflowTemplateRead,
    status_code=status.HTTP_200_OK,
    summary="Get an owned workflow template (archived included) with its steps",
)
async def get_workflow_template(
    template_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: WorkflowTemplateService = Depends(get_workflow_template_service),
) -> WorkflowTemplateRead:
    try:
        template = await service.get_owned_template(current_user.id, template_id)
    except _DOMAIN_ERRORS as e:
        raise _map_errors(e)
    return _template_read(template)


@router.patch(
    "/workflow-templates/{template_id}",
    response_model=WorkflowTemplateRead,
    status_code=status.HTTP_200_OK,
    summary="Partially update template metadata (non-retroactive)",
)
async def update_workflow_template(
    template_id: uuid.UUID,
    payload: WorkflowTemplateUpdate,
    current_user: User = Depends(get_current_user),
    service: WorkflowTemplateService = Depends(get_workflow_template_service),
) -> WorkflowTemplateRead:
    try:
        template = await service.update_template(
            current_user.id, template_id, **payload.model_dump(exclude_unset=True)
        )
    except _DOMAIN_ERRORS as e:
        raise _map_errors(e)
    return _template_read(template)


@router.put(
    "/workflow-templates/{template_id}/steps",
    response_model=WorkflowTemplateRead,
    status_code=status.HTTP_200_OK,
    summary="Atomically replace the template's ordered steps (list order = position)",
)
async def replace_workflow_template_steps(
    template_id: uuid.UUID,
    payload: WorkflowTemplateStepsReplace,
    current_user: User = Depends(get_current_user),
    service: WorkflowTemplateService = Depends(get_workflow_template_service),
) -> WorkflowTemplateRead:
    try:
        template = await service.replace_steps(
            current_user.id, template_id, _specs(payload.steps)
        )
    except _DOMAIN_ERRORS as e:
        raise _map_errors(e)
    return _template_read(template)


@router.post(
    "/workflow-templates/{template_id}/archive",
    response_model=WorkflowTemplateRead,
    status_code=status.HTTP_200_OK,
    summary="Soft-archive an owned workflow template (idempotent)",
)
async def archive_workflow_template(
    template_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: WorkflowTemplateService = Depends(get_workflow_template_service),
) -> WorkflowTemplateRead:
    try:
        await service.archive_template(current_user.id, template_id)
        template = await service.get_owned_template(current_user.id, template_id)
    except _DOMAIN_ERRORS as e:
        raise _map_errors(e)
    return _template_read(template)


@router.post(
    "/workflow-templates/{template_id}/restore",
    response_model=WorkflowTemplateRead,
    status_code=status.HTTP_200_OK,
    summary="Restore an archived owned workflow template (idempotent)",
)
async def restore_workflow_template(
    template_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: WorkflowTemplateService = Depends(get_workflow_template_service),
) -> WorkflowTemplateRead:
    try:
        await service.restore_template(current_user.id, template_id)
        template = await service.get_owned_template(current_user.id, template_id)
    except _DOMAIN_ERRORS as e:
        raise _map_errors(e)
    return _template_read(template)
