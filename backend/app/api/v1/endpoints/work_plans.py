"""Surface Work Plan API router (Stage 10B.2).

Thin owner-scoped controller over the accepted 10B.1 domain: auth → input
validation → service → typed response. All ownership, validation, ordering,
and apply-to-all logic lives in ``SurfaceWorkPlanService``; this module only
maps domain exceptions to the established HTTP error shapes (404 for
missing/foreign rows, 422 for domain validation failures).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_current_user, get_work_plan_service
from app.domain.exceptions import (
    CoefficientOptionNotFoundError,
    PriceCoefficientValidationError,
    PriceItemNotFoundError,
    ProjectNotFoundError,
    QualityScaleMismatchError,
    RoomNotFoundError,
    SurfaceNotFoundError,
    SurfaceWorkPlanNotFoundError,
    SurfaceWorkPlanOccurrenceConflictError,
    SurfaceWorkPlanValidationError,
    TemplateApplicationConflictError,
    TemplateApplicationStaleError,
    WorkflowTemplateNotFoundError,
)
from app.domain.services.work_plan_service import SurfaceWorkPlanService
from app.models.user import User
from app.schemas.work_plan import (
    ApplyTemplateRequest,
    OrderedPriceItemSelection,
    SurfaceWorkPlanApplyResult,
    SurfaceWorkPlanRead,
    SurfaceWorkPlanUpsert,
)

router = APIRouter()


@router.get(
    "/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}/work-plan",
    response_model=SurfaceWorkPlanRead,
    status_code=status.HTTP_200_OK,
    summary="Get one surface's work plan",
)
async def get_work_plan(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    surface_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    work_plan_service: SurfaceWorkPlanService = Depends(get_work_plan_service),
) -> SurfaceWorkPlanRead:
    try:
        plan = await work_plan_service.get_work_plan(
            project_id, room_id, surface_id, current_user.id
        )
    except ProjectNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    except RoomNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Room not found"
        )
    except SurfaceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Surface not found"
        )
    if plan is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Surface work plan not found",
        )
    return SurfaceWorkPlanRead.model_validate(plan)


@router.put(
    "/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}/work-plan",
    response_model=SurfaceWorkPlanRead,
    status_code=status.HTTP_200_OK,
    summary="Create or fully replace a surface's work plan",
)
async def put_work_plan(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    surface_id: uuid.UUID,
    payload: SurfaceWorkPlanUpsert,
    current_user: User = Depends(get_current_user),
    work_plan_service: SurfaceWorkPlanService = Depends(get_work_plan_service),
) -> SurfaceWorkPlanRead:
    planned_works = payload.planned_works
    if planned_works is None:
        planned_works = [
            OrderedPriceItemSelection(price_item_id=item_id)
            for item_id in payload.price_item_ids
        ]
    try:
        plan = await work_plan_service.set_plan(
            project_id,
            room_id,
            surface_id,
            current_user.id,
            substrate=payload.substrate,
            quality_target=payload.quality_target,
            planned_works=planned_works,
            template_applications=payload.template_applications,
        )
    except ProjectNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    except RoomNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Room not found"
        )
    except SurfaceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Surface not found"
        )
    except PriceItemNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Price item not found"
        )
    except CoefficientOptionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Coefficient option not found",
        )
    except QualityScaleMismatchError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )
    except WorkflowTemplateNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workflow template not found"
        )
    except (SurfaceWorkPlanOccurrenceConflictError, TemplateApplicationConflictError) as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except (SurfaceWorkPlanValidationError, PriceCoefficientValidationError) as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )
    return SurfaceWorkPlanRead.model_validate(plan)


@router.post(
    "/projects/{project_id}/rooms/{room_id}/surfaces/{source_surface_id}/work-plan/apply-to-room-walls",
    response_model=SurfaceWorkPlanApplyResult,
    status_code=status.HTTP_200_OK,
    summary="Copy a wall's work plan to every other active wall in the room",
)
async def apply_to_room_walls(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    source_surface_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    work_plan_service: SurfaceWorkPlanService = Depends(get_work_plan_service),
) -> SurfaceWorkPlanApplyResult:
    try:
        targets = await work_plan_service.apply_to_room_walls(
            project_id, room_id, source_surface_id, current_user.id
        )
    except ProjectNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Project not found"
        )
    except RoomNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Room not found"
        )
    except SurfaceNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Surface not found"
        )
    except SurfaceWorkPlanNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Surface work plan not found",
        )
    except SurfaceWorkPlanValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        )
    return SurfaceWorkPlanApplyResult(
        source_surface_id=source_surface_id,
        target_count=len(targets),
        target_surface_ids=[plan.surface_id for plan in targets],
        targets=[SurfaceWorkPlanRead.model_validate(plan) for plan in targets],
    )


@router.post(
    "/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}/work-plan/apply-template",
    response_model=SurfaceWorkPlanRead,
    status_code=status.HTTP_200_OK,
    summary="Apply a workflow template to the current work plan (APPEND or REPLACE)",
)
async def apply_template(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    surface_id: uuid.UUID,
    payload: ApplyTemplateRequest,
    current_user: User = Depends(get_current_user),
    work_plan_service: SurfaceWorkPlanService = Depends(get_work_plan_service),
) -> SurfaceWorkPlanRead:
    """Stage 13E.3: server-side materialization under the plan row lock.
    An identical retry (same application_id and request) returns 200 with
    the current plan and changes nothing."""
    try:
        plan = await work_plan_service.apply_template(
            project_id, room_id, surface_id, current_user.id, payload
        )
    except ProjectNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    except RoomNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    except SurfaceNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Surface not found")
    except SurfaceWorkPlanNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Surface work plan not found"
        )
    except WorkflowTemplateNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Workflow template not found"
        )
    except PriceItemNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Price item not found")
    except (TemplateApplicationConflictError, TemplateApplicationStaleError) as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except SurfaceWorkPlanValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return SurfaceWorkPlanRead.model_validate(plan)
