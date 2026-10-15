"""Calendar and reminders (Stage 18E): the agenda, the settings, the owner's own reminders and the planned dates of works."""
import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_calendar_service, get_current_user
from app.domain.calendar.agenda import PresetUnavailableError
from app.domain.calendar.events import PUSH_BY_DEFAULT, EventKind
from app.domain.calendar.prefs import ALLOWED_TIMEZONES
from app.domain.exceptions import (
    CalendarSettingsInvalidError,
    ProjectNotFoundError,
    ReminderInvalidError,
    ReminderNotFoundError,
    ScheduleOccurrenceNotFoundError,
)
from app.domain.services.calendar_service import CalendarService
from app.models.user import User
from app.schemas.calendar import (
    AgendaItemRead,
    AgendaRead,
    AgendaWorkRead,
    CalendarSettingsRead,
    CalendarSettingsUpdate,
    KindSettingRead,
    PlannedDateRead,
    PlannedDateWrite,
    ReminderCreate,
    ReminderListResponse,
    ReminderRead,
    ScheduleApply,
    ScheduleRead,
    ScheduleSuggestRequest,
    ScheduleWarningRead,
)

router = APIRouter()
MAX_SPAN = timedelta(days=366)
FAILURES = (
    ProjectNotFoundError, ReminderNotFoundError, ScheduleOccurrenceNotFoundError, ReminderInvalidError, CalendarSettingsInvalidError,
    PresetUnavailableError,
)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ReminderNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Reminder not found")
    if isinstance(exc, ScheduleOccurrenceNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, "Work not found")
    if isinstance(exc, (ReminderInvalidError, CalendarSettingsInvalidError, PresetUnavailableError)):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": exc.code, "message": str(exc)})
    return HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")


def _settings_read(service: CalendarService, row, prefs) -> CalendarSettingsRead:
    return CalendarSettingsRead(
        timezone=prefs.tz_name, enabled=prefs.enabled, kind_overrides=dict(prefs.kind_overrides), quiet_from=prefs.quiet_from, quiet_to=prefs.quiet_to,
        digest_at=prefs.digest_at, language=row.language if row else None,
        kinds=[KindSettingRead(kind=k.value, default_push=k in PUSH_BY_DEFAULT, sends=prefs.sends(k)) for k in EventKind if k != EventKind.USER],
        timezones=list(ALLOWED_TIMEZONES),
    )


@router.get("/calendar", response_model=AgendaRead, summary="The agenda: derived events, own reminders, dated works, overdue works")
async def get_agenda(
    start: date | None = None,
    end: date | None = None,
    project_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    service: CalendarService = Depends(get_calendar_service),
) -> AgendaRead:
    if start and end and (end < start or end - start > MAX_SPAN):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "PERIOD_INVALID", "message": "end before start or longer than a year"})
    try:
        agenda = await service.agenda(current_user.id, start=start, end=end, project_id=project_id)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return AgendaRead(
        today=agenda.today, start=agenda.start, end=agenda.end,
        items=[AgendaItemRead.model_validate(i, from_attributes=True) for i in agenda.items],
        works=[AgendaWorkRead.model_validate(w, from_attributes=True) for w in agenda.works],
        overdue=[AgendaWorkRead.model_validate(w, from_attributes=True) for w in agenda.overdue],
    )


@router.get("/calendar/settings", response_model=CalendarSettingsRead, summary="The calendar settings (the defaults when none were saved)")
async def get_settings(
    current_user: User = Depends(get_current_user), service: CalendarService = Depends(get_calendar_service)
) -> CalendarSettingsRead:
    row = await service.settings_row(current_user.id)
    return _settings_read(service, row, service.prefs_of(row))


@router.put("/calendar/settings", response_model=CalendarSettingsRead, summary="Save the calendar settings")
async def put_settings(
    body: CalendarSettingsUpdate,
    current_user: User = Depends(get_current_user),
    service: CalendarService = Depends(get_calendar_service),
) -> CalendarSettingsRead:
    try:
        row = await service.save_settings(current_user.id, **body.model_dump())
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return _settings_read(service, row, service.prefs_of(row))


@router.get("/calendar/reminders", response_model=ReminderListResponse, summary="The owner's own reminders that are waiting")
async def list_reminders(
    project_id: uuid.UUID | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    service: CalendarService = Depends(get_calendar_service),
) -> ReminderListResponse:
    rows = [r for r in await service.reminders_of(current_user.id, project_id, statuses=["PENDING"]) if r.origin == "USER"]
    return ReminderListResponse(items=[ReminderRead.model_validate(r) for r in rows], total=len(rows))


@router.post("/calendar/reminders", response_model=ReminderRead, status_code=status.HTTP_201_CREATED, summary="The Remind button")
async def create_reminder(
    body: ReminderCreate,
    current_user: User = Depends(get_current_user),
    service: CalendarService = Depends(get_calendar_service),
) -> ReminderRead:
    try:
        row = await service.create_reminder_from_preset(current_user.id, **body.model_dump())
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return ReminderRead.model_validate(row)


@router.delete("/calendar/reminders/{reminder_id}", response_model=ReminderRead, summary="Cancel an own reminder that is still waiting")
async def cancel_reminder(
    reminder_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: CalendarService = Depends(get_calendar_service),
) -> ReminderRead:
    try:
        row = await service.cancel_reminder(current_user.id, reminder_id)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return ReminderRead.model_validate(row)


async def _schedule(service: CalendarService, owner_id: uuid.UUID, project_id: uuid.UUID) -> ScheduleRead:
    planned = await service.planned_dates(owner_id, project_id)
    warnings = await service.schedule_warnings(owner_id, project_id)
    window = await service.contract_window(owner_id, project_id)
    return ScheduleRead(
        planned=[PlannedDateRead(occurrence_key=k, planned_date=d) for k, d in sorted(planned.items(), key=lambda kv: (kv[1], str(kv[0])))],
        warnings=[ScheduleWarningRead(occurrence_key=w.occurrence_key, code=w.code, date=w.date) for w in warnings],
        window_start=window[0], window_end=window[1],
    )


@router.get("/projects/{project_id}/schedule", response_model=ScheduleRead, summary="Planned dates of the works of an object and what is wrong with them")
async def get_schedule(
    project_id: uuid.UUID, current_user: User = Depends(get_current_user), service: CalendarService = Depends(get_calendar_service)
) -> ScheduleRead:
    try:
        return await _schedule(service, current_user.id, project_id)
    except FAILURES as exc:
        raise _http_error(exc) from exc


@router.put("/projects/{project_id}/schedule/{occurrence_key}", response_model=ScheduleRead, summary="Plan a work for a day (or clear the date)")
async def put_planned_date(
    project_id: uuid.UUID,
    occurrence_key: uuid.UUID,
    body: PlannedDateWrite,
    current_user: User = Depends(get_current_user),
    service: CalendarService = Depends(get_calendar_service),
) -> ScheduleRead:
    try:
        await service.set_planned_date(current_user.id, project_id, occurrence_key, body.planned_date, body.note)
        return await _schedule(service, current_user.id, project_id)
    except FAILURES as exc:
        raise _http_error(exc) from exc


@router.post("/projects/{project_id}/schedule/suggest", response_model=list[PlannedDateRead], summary="A proposal of dates in the order of the works (nothing is saved)")
async def suggest_dates(
    project_id: uuid.UUID,
    body: ScheduleSuggestRequest,
    current_user: User = Depends(get_current_user),
    service: CalendarService = Depends(get_calendar_service),
) -> list[PlannedDateRead]:
    try:
        proposal = await service.suggest_dates(current_user.id, project_id, body.start, body.room_id)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return [PlannedDateRead(occurrence_key=k, planned_date=d) for k, d in sorted(proposal.items(), key=lambda kv: (kv[1], str(kv[0])))]


@router.post("/projects/{project_id}/schedule/apply", response_model=ScheduleRead, summary="Accept a proposal: several planned dates at once")
async def apply_dates(
    project_id: uuid.UUID,
    body: ScheduleApply,
    current_user: User = Depends(get_current_user),
    service: CalendarService = Depends(get_calendar_service),
) -> ScheduleRead:
    try:
        await service.apply_planned_dates(current_user.id, project_id, {d.occurrence_key: d.planned_date for d in body.dates})
        return await _schedule(service, current_user.id, project_id)
    except FAILURES as exc:
        raise _http_error(exc) from exc
