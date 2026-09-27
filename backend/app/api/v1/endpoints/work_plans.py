"""Surface Work Plan API router (Stage 10B.2).

Thin owner-scoped controller over the accepted 10B.1 domain: auth → input
validation → service → typed response. All ownership, validation, ordering,
and apply-to-all logic lives in ``SurfaceWorkPlanService``; this module only
maps domain exceptions to the established HTTP error shapes (404 for
missing/foreign rows, 422 for domain validation failures).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import (
    get_current_user,
    get_work_execution_service,
    get_work_plan_service,
)
from app.domain.exceptions import (
    CoefficientOptionNotFoundError,
    ExecutionDetachConfirmationRequiredError,
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
    WorkExecutionConflictError,
    WorkExecutionSourceChangedError,
    WorkExecutionValidationError,
    WorkflowTemplateNotFoundError,
)
from app.domain.services.work_execution_service import SurfaceWorkExecutionService
from app.domain.services.work_plan_service import SurfaceWorkPlanService
from app.models.user import User
from app.schemas.work_plan import (
    ApplyTemplateRequest,
    ApplyToRoomWallsRequest,
    BulkExecutionApplyRequest,
    BulkExecutionResultRead,
    BulkExecutionWallRead,
    ExecutionSnapshotItem,
    ExecutionDetachAffectedRead,
    OrderedPriceItemSelection,
    SurfaceWorkExecutionRead,
    SurfaceWorkExecutionTransition,
    SurfaceWorkPlanApplyResult,
    SurfaceWorkPlanRead,
    SurfaceWorkPlanUpsert,
)

router = APIRouter()


def _detach_confirmation_required(e: ExecutionDetachConfirmationRequiredError) -> HTTPException:
    """Stage 13H.4: structured 409 listing the CURRENT protected records the
    mutation would detach (own target plans only)."""
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "WORK_EXECUTION_DETACH_CONFIRMATION_REQUIRED",
            "message": str(e),
            "affected": [
                ExecutionDetachAffectedRead.model_validate(a).model_dump(mode="json")
                for a in e.affected
            ],
        },
    )


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
            confirm_execution_detach_keys=payload.confirm_execution_detach_keys,
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
    except ExecutionDetachConfirmationRequiredError as e:
        raise _detach_confirmation_required(e)
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
    payload: ApplyToRoomWallsRequest | None = None,
    current_user: User = Depends(get_current_user),
    work_plan_service: SurfaceWorkPlanService = Depends(get_work_plan_service),
) -> SurfaceWorkPlanApplyResult:
    try:
        targets = await work_plan_service.apply_to_room_walls(
            project_id,
            room_id,
            source_surface_id,
            current_user.id,
            confirm_execution_detach_keys=(
                payload.confirm_execution_detach_keys if payload is not None else None
            ),
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
    except ExecutionDetachConfirmationRequiredError as e:
        raise _detach_confirmation_required(e)
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
    except ExecutionDetachConfirmationRequiredError as e:
        raise _detach_confirmation_required(e)
    except SurfaceWorkPlanValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return SurfaceWorkPlanRead.model_validate(plan)


@router.patch(
    "/projects/{project_id}/rooms/{room_id}/surfaces/{surface_id}/work-plan/occurrences/{occurrence_key}/execution",
    response_model=SurfaceWorkExecutionRead,
    status_code=status.HTTP_200_OK,
    summary="Change the execution status of one current planned-work occurrence",
)
async def transition_execution(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    surface_id: uuid.UUID,
    occurrence_key: uuid.UUID,
    payload: SurfaceWorkExecutionTransition,
    current_user: User = Depends(get_current_user),
    execution_service: SurfaceWorkExecutionService = Depends(get_work_execution_service),
) -> SurfaceWorkExecutionRead:
    """Stage 13H.3: the only way to change execution state. A request for the
    current status returns 200 unchanged; a stale expected_status or a
    disallowed transition is 409 WORK_EXECUTION_CONFLICT carrying the current
    status; a key that is not a current occurrence of this plan gets the same
    non-leaking 409 as a WorkPlan save; archived hierarchy is 422."""
    try:
        view = await execution_service.transition(
            project_id,
            room_id,
            surface_id,
            current_user.id,
            occurrence_key,
            status=payload.status,
            expected_status=payload.expected_status,
        )
    except ProjectNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    except RoomNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    except SurfaceNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Surface not found")
    except SurfaceWorkPlanOccurrenceConflictError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except WorkExecutionConflictError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "WORK_EXECUTION_CONFLICT",
                "message": str(e),
                "current_status": e.current_status.value,
            },
        )
    except WorkExecutionValidationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return SurfaceWorkExecutionRead.model_validate(view)


def _bulk_result(source_surface_id: uuid.UUID, applied: bool, snapshot, plan) -> BulkExecutionResultRead:
    return BulkExecutionResultRead(
        source_surface_id=source_surface_id,
        applied=applied,
        expected_source=[ExecutionSnapshotItem(occurrence_key=k, status=st) for k, st in snapshot],
        changed=plan.changed,
        unchanged=plan.unchanged,
        unmatched=plan.unmatched,
        ambiguous=plan.ambiguous,
        walls=[BulkExecutionWallRead.model_validate(w) for w in plan.walls],
    )


def _bulk_errors(e: Exception) -> HTTPException:
    if isinstance(e, ProjectNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    if isinstance(e, RoomNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    if isinstance(e, SurfaceNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Surface not found")
    if isinstance(e, WorkExecutionSourceChangedError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "WORK_EXECUTION_SOURCE_CHANGED",
                "message": str(e),
                "current_source": [
                    {"occurrence_key": str(k), "status": st.value} for k, st in e.current_source
                ],
            },
        )
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.post(
    "/projects/{project_id}/rooms/{room_id}/surfaces/{source_surface_id}/work-plan/execution/apply-to-room-walls-preview",
    response_model=BulkExecutionResultRead,
    status_code=status.HTTP_200_OK,
    summary="Preview carrying a wall's execution progress forward to the room's other walls",
)
async def preview_execution_to_room_walls(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    source_surface_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    execution_service: SurfaceWorkExecutionService = Depends(get_work_execution_service),
) -> BulkExecutionResultRead:
    """Stage 13H.5B: read-only; returns the canonical expected_source and the
    counts the apply would produce right now."""
    try:
        snapshot, plan = await execution_service.preview_room_walls(
            project_id, room_id, source_surface_id, current_user.id
        )
    except (ProjectNotFoundError, RoomNotFoundError, SurfaceNotFoundError, WorkExecutionValidationError) as e:
        raise _bulk_errors(e)
    return _bulk_result(source_surface_id, False, snapshot, plan)


@router.post(
    "/projects/{project_id}/rooms/{room_id}/surfaces/{source_surface_id}/work-plan/execution/apply-to-room-walls",
    response_model=BulkExecutionResultRead,
    status_code=status.HTTP_200_OK,
    summary="Carry a wall's execution progress forward to the room's other walls",
)
async def apply_execution_to_room_walls(
    project_id: uuid.UUID,
    room_id: uuid.UUID,
    source_surface_id: uuid.UUID,
    payload: BulkExecutionApplyRequest,
    current_user: User = Depends(get_current_user),
    execution_service: SurfaceWorkExecutionService = Depends(get_work_execution_service),
) -> BulkExecutionResultRead:
    """Stage 13H.5B: forward-only, all-or-nothing, under ascending plan locks;
    409 WORK_EXECUTION_SOURCE_CHANGED when expected_source is stale."""
    try:
        snapshot, plan = await execution_service.apply_room_walls(
            project_id,
            room_id,
            source_surface_id,
            current_user.id,
            [(item.occurrence_key, item.status) for item in payload.expected_source],
        )
    except (
        ProjectNotFoundError,
        RoomNotFoundError,
        SurfaceNotFoundError,
        WorkExecutionValidationError,
        WorkExecutionSourceChangedError,
    ) as e:
        raise _bulk_errors(e)
    return _bulk_result(source_surface_id, True, snapshot, plan)
