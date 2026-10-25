"""The payment schedule, the work hours and the margin of an object (V2-9): thin routes over their services. Online only; owner-scoped."""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import (
    get_current_user,
    get_margin_service,
    get_payment_schedule_service,
    get_work_hours_service,
)
from app.domain.exceptions import (
    PaymentInvalidError,
    PaymentNotFoundError,
    PaymentStageInvalidError,
    PaymentStageNotFoundError,
    ProjectNotFoundError,
    WorkHourNotFoundError,
)
from app.domain.services.payment_schedule_service import (
    PaymentScheduleService,
    Schedule,
    StageView,
)
from app.domain.services.project_margin_service import ProjectMarginService
from app.domain.services.work_hours_service import WorkHoursService
from app.models.user import User
from app.schemas.payment import PaymentRead
from app.schemas.payment_schedule import (
    HourCreate,
    HourRead,
    HoursResponse,
    HourUpdate,
    MarginRead,
    ScheduleResponse,
    ScheduleSummaryRead,
    StageCreate,
    StageRead,
    StageUpdate,
)

router = APIRouter()

FAILURES = (ProjectNotFoundError, PaymentStageNotFoundError, PaymentStageInvalidError, WorkHourNotFoundError, PaymentInvalidError, PaymentNotFoundError)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PaymentStageNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Stage not found")
    if isinstance(exc, WorkHourNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Entry not found")
    if isinstance(exc, PaymentStageInvalidError):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": exc.code, "message": str(exc)})
    if isinstance(exc, PaymentInvalidError):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": exc.code, "message": str(exc)})
    return HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")


def _stage(view: StageView) -> StageRead:
    row, standing = view.stage, view.standing
    return StageRead(
        id=row.id, project_id=row.project_id, title=row.title, percent=row.percent, amount_fixed=row.amount, due_on=row.due_on,
        amount=standing.amount, received=standing.received, remaining=standing.remaining, state=standing.state,
        created_at=row.created_at, updated_at=row.updated_at,
    )


def _schedule(found: Schedule) -> ScheduleResponse:
    summary = found.summary
    return ScheduleResponse(
        items=[_stage(view) for view in found.items],
        summary=ScheduleSummaryRead(
            agreed=summary.agreed, stages_total=summary.stages_total, unpriced=summary.unpriced, difference=summary.difference,
            received=summary.received, to_receive=summary.to_receive,
        ),
    )


async def _one(service: PaymentScheduleService, user: User, project_id: uuid.UUID, stage_id: uuid.UUID) -> StageRead:
    found = await service.schedule(user.id, project_id)
    return _stage(next(view for view in found.items if view.stage.id == stage_id))


@router.get("/projects/{project_id}/payment-stages", response_model=ScheduleResponse, summary="The payment schedule of an object: its stages and where each stands")
async def list_stages(
    project_id: uuid.UUID, current_user: User = Depends(get_current_user), service: PaymentScheduleService = Depends(get_payment_schedule_service)
) -> ScheduleResponse:
    try:
        return _schedule(await service.schedule(current_user.id, project_id, today=datetime.now(UTC).date()))
    except FAILURES as exc:
        raise _http_error(exc) from exc


@router.post("/projects/{project_id}/payment-stages", response_model=StageRead, status_code=status.HTTP_201_CREATED, summary="Add a stage to the schedule")
async def create_stage(
    project_id: uuid.UUID,
    payload: StageCreate,
    current_user: User = Depends(get_current_user),
    service: PaymentScheduleService = Depends(get_payment_schedule_service),
) -> StageRead:
    try:
        row = await service.create(current_user.id, project_id, payload.model_dump())
        return await _one(service, current_user, project_id, row.id)
    except FAILURES as exc:
        raise _http_error(exc) from exc


@router.patch("/projects/{project_id}/payment-stages/{stage_id}", response_model=StageRead, summary="Change a stage of the schedule")
async def update_stage(
    project_id: uuid.UUID,
    stage_id: uuid.UUID,
    payload: StageUpdate,
    current_user: User = Depends(get_current_user),
    service: PaymentScheduleService = Depends(get_payment_schedule_service),
) -> StageRead:
    try:
        row = await service.change(current_user.id, project_id, stage_id, payload.model_dump(exclude_unset=True))
        return await _one(service, current_user, project_id, row.id)
    except FAILURES as exc:
        raise _http_error(exc) from exc


@router.delete(
    "/projects/{project_id}/payment-stages/{stage_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a stage (the money received for it stays, without a stage)",
)
async def delete_stage(
    project_id: uuid.UUID,
    stage_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: PaymentScheduleService = Depends(get_payment_schedule_service),
) -> Response:
    try:
        await service.delete(current_user.id, project_id, stage_id)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/projects/{project_id}/payment-stages/{stage_id}/receive",
    response_model=PaymentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Book the rest of a stage as one payment received today",
)
async def receive_stage(
    project_id: uuid.UUID,
    stage_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: PaymentScheduleService = Depends(get_payment_schedule_service),
) -> PaymentRead:
    try:
        row = await service.receive(current_user.id, project_id, stage_id, today=datetime.now(UTC).date())
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return PaymentRead.model_validate(row)


@router.get("/projects/{project_id}/work-hours", response_model=HoursResponse, summary="The work log of an object with the sum of the hours")
async def list_hours(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: WorkHoursService = Depends(get_work_hours_service),
    margin: ProjectMarginService = Depends(get_margin_service),
) -> HoursResponse:
    try:
        rows, total = await service.list_entries(current_user.id, project_id)
        rate = await margin.hourly_rate(current_user.id)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return HoursResponse(items=[HourRead.model_validate(r) for r in rows], total_hours=total, hourly_rate=rate)


@router.post("/projects/{project_id}/work-hours", response_model=HourRead, status_code=status.HTTP_201_CREATED, summary="Add hours to the work log")
async def create_hours(
    project_id: uuid.UUID,
    payload: HourCreate,
    current_user: User = Depends(get_current_user),
    service: WorkHoursService = Depends(get_work_hours_service),
) -> HourRead:
    try:
        return HourRead.model_validate(await service.create(current_user.id, project_id, payload.model_dump()))
    except FAILURES as exc:
        raise _http_error(exc) from exc


@router.patch("/projects/{project_id}/work-hours/{entry_id}", response_model=HourRead, summary="Change an entry of the work log")
async def update_hours(
    project_id: uuid.UUID,
    entry_id: uuid.UUID,
    payload: HourUpdate,
    current_user: User = Depends(get_current_user),
    service: WorkHoursService = Depends(get_work_hours_service),
) -> HourRead:
    try:
        return HourRead.model_validate(await service.change(current_user.id, project_id, entry_id, payload.model_dump(exclude_unset=True)))
    except FAILURES as exc:
        raise _http_error(exc) from exc


@router.delete("/projects/{project_id}/work-hours/{entry_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete an entry of the work log")
async def delete_hours(
    project_id: uuid.UUID,
    entry_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: WorkHoursService = Depends(get_work_hours_service),
) -> Response:
    try:
        await service.delete(current_user.id, project_id, entry_id)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{project_id}/margin", response_model=MarginRead, summary="The margin of an object: agreed amount less expenses less the owner's own work")
async def get_margin(
    project_id: uuid.UUID, current_user: User = Depends(get_current_user), service: ProjectMarginService = Depends(get_margin_service)
) -> MarginRead:
    try:
        found = await service.margin(current_user.id, project_id)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return MarginRead(**{name: getattr(found, name) for name in MarginRead.model_fields})
