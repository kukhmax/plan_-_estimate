"""Calendar and reminders of the owner (Stage 18C): the data of an object -> the events -> the queue of reminders.

The read side gathers the plain facts of one object (the breaks of the completed works, the planned dates, the dates of the contract
and of the protocols), the pure functions of `domain/calendar` turn them into events and reminders, and `reconcile_project` brings the
queue in step with them. Every call is scoped to the owner's own data (`ProjectNotFoundError` otherwise).

Transactions: `reconcile_project`, `reconcile_owner`, `close_for_status` and `on_executions_changed` only flush -- they run inside the
transaction of the change that caused them (a work marked done) so that the queue never lags behind the status; the calls the API makes
(`save_settings`, `create_reminder`, `cancel_reminder`, `set_planned_date`) commit.
"""
import logging
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.calendar import agenda as ag
from app.domain.calendar import events as ev
from app.domain.calendar import schedule as sched
from app.domain.calendar.prefs import ALLOWED_TIMEZONES, CalendarPrefs, parse_timezone
from app.domain.calendar.reconcile import (
    DesiredReminder,
    QueuedReminder,
    ReconcilePlan,
    desired_reminders,
    local_instant,
    plan_changes,
)
from app.domain.exceptions import (
    CalendarSettingsInvalidError,
    ProjectNotFoundError,
    ReminderInvalidError,
    ReminderNotFoundError,
    ScheduleOccurrenceNotFoundError,
)
from app.domain.rules.payment_totals import PAID, Entry, invoice_standings
from app.domain.rules.work_execution_rules import derive_ready_after
from app.models.acceptance_protocol import AcceptanceProtocol, AcceptanceStatus
from app.models.adjacent_work import AdjacentWork
from app.models.calendar_settings import CalendarSettings
from app.models.client import Client, ClientType
from app.models.concealed_works_protocol import ConcealedStatus, ConcealedWorksProtocol
from app.models.contract import Contract, ContractStatus
from app.models.downtime_episode import DowntimeEpisode, DowntimeStatus
from app.models.price_item import PriceItem
from app.models.project import Project
from app.models.project_payment import ProjectPayment
from app.models.reminder import Reminder, ReminderOrigin, ReminderStatus
from app.models.room import Room
from app.models.surface import Surface
from app.models.work_execution import SurfaceWorkExecution, WorkExecutionStatus
from app.models.work_plan import SurfacePlannedWork, SurfaceWorkPlan
from app.models.work_schedule import WorkSchedule

logger = logging.getLogger(__name__)

TITLE_LIMIT = 120
MAX_OWN_PENDING = 200  # waiting own reminders of one owner: a guard against a script or a stuck button, far above a real use
LANGUAGES = ("pl", "ru")
CLOSING_RANK = {WorkExecutionStatus.IN_PROGRESS.value: 1, WorkExecutionStatus.COMPLETED.value: 2}


def _date(value: Any) -> date | None:
    """A date out of the answers of the contract; a value that is not a date is no date (the calendar goes on without it)."""
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _utc(value: datetime | None) -> datetime | None:
    """A stored instant as an aware UTC one (PostgreSQL returns it aware; SQLite of the tests drops the offset)."""
    return value if value is None or value.tzinfo is not None else value.replace(tzinfo=UTC)


def _utc_required(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


MAX_TERM_DAYS = 3650  # a term of the contract longer than ten years is a typo, not a term


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= MAX_TERM_DAYS else None


@dataclass(frozen=True)
class WorkRow:
    room_id: uuid.UUID
    room_name: str
    surface_id: uuid.UUID
    surface_name: str
    step: sched.WorkStep
    name_key: str | None
    display_name: str | None


class CalendarService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # --- settings --------------------------------------------------------------------------------------------------------------

    @staticmethod
    def prefs_of(row: CalendarSettings | None) -> CalendarPrefs:
        if row is None:
            return CalendarPrefs()
        return CalendarPrefs(
            enabled=row.enabled, tz=parse_timezone(row.timezone), tz_name=row.timezone, kind_overrides=dict(row.kind_overrides or {}),
            quiet_from=row.quiet_from, quiet_to=row.quiet_to, digest_at=row.digest_at, language=row.language,
        )

    async def settings_row(self, owner_id: uuid.UUID) -> CalendarSettings | None:
        return (await self.db.execute(select(CalendarSettings).where(CalendarSettings.owner_id == owner_id))).scalar_one_or_none()

    async def prefs(self, owner_id: uuid.UUID) -> CalendarPrefs:
        return self.prefs_of(await self.settings_row(owner_id))

    async def save_settings(
        self, owner_id: uuid.UUID, *, timezone: str, enabled: bool, kind_overrides: Mapping[str, bool], quiet_from: time, quiet_to: time,
        digest_at: time, language: str | None, now: datetime | None = None,
    ) -> CalendarSettings:
        """Save the settings and bring the queue in step with them (a zone or a quiet hour moves the pending reminders)."""
        if timezone not in ALLOWED_TIMEZONES:
            raise CalendarSettingsInvalidError("TIMEZONE_UNKNOWN")
        if language is not None and language not in LANGUAGES:
            raise CalendarSettingsInvalidError("LANGUAGE_UNKNOWN")
        known = {kind.value for kind in ev.EventKind}
        if any(key not in known or not isinstance(value, bool) for key, value in kind_overrides.items()):
            raise CalendarSettingsInvalidError("KIND_UNKNOWN")
        try:
            CalendarPrefs(quiet_from=quiet_from, quiet_to=quiet_to, digest_at=digest_at)
        except ValueError as error:
            raise CalendarSettingsInvalidError("DIGEST_IN_QUIET_HOURS") from error
        row = await self.settings_row(owner_id)
        if row is None:
            row = CalendarSettings(owner_id=owner_id)
            self.db.add(row)
        row.timezone, row.enabled, row.kind_overrides = timezone, enabled, dict(kind_overrides)
        row.quiet_from, row.quiet_to, row.digest_at, row.language = quiet_from, quiet_to, digest_at, language
        await self.db.flush()
        await self.reconcile_owner(owner_id, now=now)
        await self.db.commit()
        return row

    # --- reading the facts of an object -------------------------------------------------------------------------------------------

    async def _project(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> Project:
        project = (
            await self.db.execute(select(Project).where(Project.id == project_id, Project.owner_id == owner_id))
        ).scalar_one_or_none()
        if project is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")
        return project

    async def _works(self, project_id: uuid.UUID) -> list["WorkRow"]:
        """Every work of the current plans of the object's live rooms and surfaces, with the names the screens need."""
        rows = (
            await self.db.execute(
                select(
                    Room.id, Room.name, Surface.id, Surface.name, SurfacePlannedWork.occurrence_key, SurfacePlannedWork.position,
                    SurfacePlannedWork.wait_after_hours, SurfaceWorkExecution.status, SurfaceWorkExecution.completed_at, WorkSchedule.planned_date,
                    PriceItem.name_key, PriceItem.display_name,
                )
                .join(Surface, Surface.room_id == Room.id)
                .join(SurfaceWorkPlan, SurfaceWorkPlan.surface_id == Surface.id)
                .join(SurfacePlannedWork, SurfacePlannedWork.work_plan_id == SurfaceWorkPlan.id)
                .join(PriceItem, PriceItem.id == SurfacePlannedWork.price_item_id)
                .outerjoin(SurfaceWorkExecution, SurfaceWorkExecution.occurrence_key == SurfacePlannedWork.occurrence_key)
                .outerjoin(WorkSchedule, WorkSchedule.occurrence_key == SurfacePlannedWork.occurrence_key)
                .where(Room.project_id == project_id, Room.is_archived.is_(False), Surface.is_archived.is_(False))
                .order_by(Room.id, Surface.id, SurfacePlannedWork.position)
            )
        ).all()
        return [
            WorkRow(room_id, room_name, surface_id, surface_name,
                    sched.WorkStep(key, position, wait, status or WorkExecutionStatus.NOT_STARTED, _utc(completed_at), planned), name_key, display_name)
            for room_id, room_name, surface_id, surface_name, key, position, wait, status, completed_at, planned, name_key, display_name in rows
        ]

    async def _steps(self, project_id: uuid.UUID) -> list[tuple[uuid.UUID, uuid.UUID, sched.WorkStep]]:
        """(room_id, surface_id, step) of every work of the object."""
        return [(w.room_id, w.surface_id, w.step) for w in await self._works(project_id)]

    async def _contract(self, project_id: uuid.UUID) -> Contract | None:
        """The contract the dates come from: the signed one, otherwise the issued one, otherwise the draft (never an archived version)."""
        rows = (
            await self.db.execute(select(Contract).where(Contract.project_id == project_id).order_by(Contract.version.desc()))
        ).scalars().all()
        for status in (ContractStatus.SIGNED, ContractStatus.ISSUED, ContractStatus.DRAFT):
            for row in rows:
                if row.status == status.value:
                    return row
        return None

    async def events_for_project(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> list[ev.CalendarEvent]:
        project = await self._project(owner_id, project_id)
        if project.is_archived:
            return []
        steps = await self._steps(project_id)
        events: list[ev.CalendarEvent] = []
        events += ev.break_events(
            ev.BreakInput(project_id, step.occurrence_key, step.status, step.completed_at, step.wait_after_hours, room_id, surface_id)
            for room_id, surface_id, step in steps
        )
        events += ev.schedule_events(
            ev.PlannedWork(project_id, step.occurrence_key, step.planned_date, room_id) for room_id, _, step in steps if step.planned_date
        )
        contract = await self._contract(project_id)
        answers: Mapping[str, Any] = (contract.answers or {}) if contract else {}
        consumer = False
        if project.client_id is not None:
            client_type = (await self.db.execute(select(Client.client_type).where(Client.id == project.client_id))).scalar_one_or_none()
            consumer = client_type == ClientType.PRIVATE_PERSON
        if contract is not None:
            events += ev.contract_events(ev.ContractDates(
                project_id, signed_on=contract.signed_on if contract.status == ContractStatus.SIGNED.value else None,
                work_start_date=_date(answers.get("work_start_date")), work_end_date=_date(answers.get("work_end_date")),
                price_validity_days=_int(answers.get("price_validity_days")), consumer=consumer,
            ))
        appearance = _int(answers.get("customer_appearance_days"))
        for acceptance in (await self.db.execute(
            select(AcceptanceProtocol).where(AcceptanceProtocol.project_id == project_id, AcceptanceProtocol.status != AcceptanceStatus.ARCHIVED.value)
        )).scalars():
            events += ev.acceptance_events(ev.AcceptanceDates(project_id, appearance, acceptance.notified_on, acceptance.renotified_on, acceptance.held_on))
        events += ev.concealed_events(
            ev.ConcealedDates(project_id, str(row.id), row.notified_on, row.held_on)
            for row in (await self.db.execute(
                select(ConcealedWorksProtocol).where(
                    ConcealedWorksProtocol.project_id == project_id, ConcealedWorksProtocol.status != ConcealedStatus.ARCHIVED.value
                )
            )).scalars()
        )
        for episode in (await self.db.execute(
            select(DowntimeEpisode).where(
                DowntimeEpisode.project_id == project_id, DowntimeEpisode.status.in_((DowntimeStatus.DRAFT.value, DowntimeStatus.NOTICED.value))
            )
        )).scalars():
            events += ev.downtime_events(ev.DowntimeDates(project_id, episode.noticed_on, episode.need_by, episode.held_on))
        events += ev.adjacent_events(
            ev.AdjacentPeriod(project_id, str(row.id), row.period_from, row.period_to)
            for row in (await self.db.execute(
                select(AdjacentWork).where(AdjacentWork.project_id == project_id, AdjacentWork.is_archived.is_(False))
            )).scalars()
        )
        events += await self._invoice_events(project_id)
        return events

    async def _invoice_events(self, project_id: uuid.UUID) -> list[ev.CalendarEvent]:
        """The due days of the invoices of the settlements that are still to be paid (IA-5): not archived, with a term, not paid in full.
        An invoice that is paid, archived or without a term gives nothing, so its waiting reminder is cancelled by the next reconciliation."""
        rows = (await self.db.execute(select(ProjectPayment).where(ProjectPayment.project_id == project_id))).scalars().all()
        standings = invoice_standings(
            (Entry(r.id, r.kind, r.amount_gross, r.due_on, r.settles_id, r.is_archived) for r in rows), datetime.now(UTC).date()
        )
        return ev.invoice_events(
            ev.InvoiceDue(project_id, r.id, r.due_on, r.number or r.title)
            for r in rows
            if r.kind == "INVOICE" and not r.is_archived and r.due_on is not None and standings[r.id].state != PAID
        )

    # --- the queue -------------------------------------------------------------------------------------------------------------------

    async def reconcile_project(self, owner_id: uuid.UUID, project_id: uuid.UUID, *, now: datetime | None = None) -> ReconcilePlan:
        """Bring the automatic reminders of one object in step with its events (flushes, does not commit)."""
        now = now or datetime.now(UTC)
        project = await self._project(owner_id, project_id)
        prefs = await self.prefs(owner_id)
        desired = desired_reminders(await self.events_for_project(owner_id, project_id), prefs)
        rows = {
            row.dedupe_key: row
            for row in (await self.db.execute(
                select(Reminder).where(Reminder.owner_id == owner_id, Reminder.project_id == project_id, Reminder.origin == ReminderOrigin.AUTO.value)
            )).scalars()
        }
        plan = plan_changes(desired, {key: QueuedReminder(row.status, _utc_required(row.send_at)) for key, row in rows.items()}, now)
        await self._insert_new(owner_id, plan.insert, prefs)
        for item in plan.retime:
            rows[item.dedupe_key].send_at = item.send_at
            rows[item.dedupe_key].tz = prefs.tz_name
        for item in plan.revive:
            row = rows[item.dedupe_key]
            row.status, row.send_at, row.tz, row.attempts, row.error_code = ReminderStatus.PENDING.value, item.send_at, prefs.tz_name, 0, None
        for key in plan.cancel:
            rows[key].status = ReminderStatus.CANCELLED.value
        if project.is_archived:  # an archived object keeps no reminder at all, the owner's own ones included (Q14)
            for row in (await self.db.execute(
                select(Reminder).where(
                    Reminder.owner_id == owner_id, Reminder.project_id == project_id, Reminder.origin == ReminderOrigin.USER.value,
                    Reminder.status == ReminderStatus.PENDING.value,
                )
            )).scalars():
                row.status = ReminderStatus.CANCELLED.value
        await self.db.flush()
        return plan

    async def _insert_new(self, owner_id: uuid.UUID, items: list[DesiredReminder], prefs: CalendarPrefs) -> None:
        """Queue the new facts. A fact another pass queued a moment ago (the periodic pass and a request meet on the same object) is
        already there: the unique key makes the second insert a no-op instead of an error that would undo the user's own action."""
        dialect = self.db.get_bind().dialect.name
        insert = pg_insert if dialect == "postgresql" else sqlite_insert
        for item in items:
            row = self._row(owner_id, item, prefs)
            values = {column.name: getattr(row, column.name) for column in Reminder.__table__.columns if getattr(row, column.name) is not None}
            await self.db.execute(insert(Reminder).values(**values).on_conflict_do_nothing(index_elements=["owner_id", "dedupe_key"]))

    @staticmethod
    def _row(owner_id: uuid.UUID, item: DesiredReminder, prefs: CalendarPrefs) -> Reminder:
        event = item.event
        return Reminder(
            owner_id=owner_id, project_id=event.project_id, room_id=event.room_id, surface_id=event.surface_id,
            occurrence_key=event.occurrence_key, origin=ReminderOrigin.AUTO.value, kind=event.kind.value, ref=event.ref,
            title_key=event.title_key, params=dict(event.params), event_on=event.on, event_at=event.at, lead_days=item.lead_days,
            send_at=item.send_at, tz=prefs.tz_name, status=ReminderStatus.PENDING.value, dedupe_key=item.dedupe_key,
        )

    async def reconcile_owner(self, owner_id: uuid.UUID, *, now: datetime | None = None) -> int:
        """Reconcile every object of the owner, archived ones too (their reminders are cancelled); returns the number of objects."""
        ids = (await self.db.execute(select(Project.id).where(Project.owner_id == owner_id))).scalars().all()
        for project_id in ids:
            await self.reconcile_project(owner_id, project_id, now=now)
        return len(ids)

    async def close_for_status(self, owner_id: uuid.UUID, statuses: Mapping[uuid.UUID, WorkExecutionStatus]) -> int:
        """Close (DONE) the pending own reminders that waited for a work to reach the status it now has (flushes, does not commit)."""
        if not statuses:
            return 0
        rows = (await self.db.execute(
            select(Reminder).where(
                Reminder.owner_id == owner_id, Reminder.occurrence_key.in_(list(statuses)), Reminder.status == ReminderStatus.PENDING.value,
                Reminder.close_on_status.is_not(None),
            )
        )).scalars().all()
        closed = 0
        for row in rows:
            reached = CLOSING_RANK.get(statuses[row.occurrence_key].value, 0)  # type: ignore[index]
            if reached >= CLOSING_RANK[row.close_on_status]:  # type: ignore[index]
                row.status = ReminderStatus.DONE.value
                closed += 1
        await self.db.flush()
        return closed

    async def on_executions_changed(self, owner_id: uuid.UUID, project_id: uuid.UUID, statuses: Mapping[uuid.UUID, WorkExecutionStatus]) -> None:
        """The hook of the execution service: works changed status -> close the reminders that waited for it and re-reconcile the object.

        It runs in a savepoint: a fault here is logged and must never undo or block marking a work done (the periodic reconciliation of
        18D and the opening of the calendar bring the queue right again).
        """
        try:
            async with self.db.begin_nested():
                await self.close_for_status(owner_id, statuses)
                await self.reconcile_project(owner_id, project_id)
        except Exception:  # logged with the traceback; the status change itself is the user's act and must go through
            logger.exception("calendar reconciliation after a status change failed (project %s)", project_id)

    async def reconcile_project_guarded(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> None:
        """The same fault isolation for the other hook (archiving or restoring an object)."""
        try:
            async with self.db.begin_nested():
                await self.reconcile_project(owner_id, project_id)
        except Exception:  # logged with the traceback; archiving itself must go through
            logger.exception("calendar reconciliation after archiving failed (project %s)", project_id)

    # --- own reminders ---------------------------------------------------------------------------------------------------------------

    async def create_reminder(
        self, owner_id: uuid.UUID, *, title: str, send_at: datetime, project_id: uuid.UUID | None = None, room_id: uuid.UUID | None = None,
        surface_id: uuid.UUID | None = None, occurrence_key: uuid.UUID | None = None, close_on_status: str | None = None,
        now: datetime | None = None,
    ) -> Reminder:
        now = now or datetime.now(UTC)
        title = (title or "").strip()
        if not title:
            raise ReminderInvalidError("TITLE_REQUIRED")
        if len(title) > TITLE_LIMIT:
            raise ReminderInvalidError("TITLE_TOO_LONG")
        if send_at.tzinfo is None or send_at <= now:
            raise ReminderInvalidError("IN_THE_PAST")
        if close_on_status is not None and close_on_status not in CLOSING_RANK:
            raise ReminderInvalidError("CLOSE_STATUS_INVALID")
        waiting = (await self.db.execute(
            select(func.count()).select_from(Reminder).where(
                Reminder.owner_id == owner_id, Reminder.origin == ReminderOrigin.USER.value, Reminder.status == ReminderStatus.PENDING.value
            )
        )).scalar_one()
        if waiting >= MAX_OWN_PENDING:
            raise ReminderInvalidError("TOO_MANY")
        if project_id is not None:
            await self._project(owner_id, project_id)
        await self._place_of_reminder(project_id, room_id, surface_id)
        prefs = await self.prefs(owner_id)
        row = Reminder(
            owner_id=owner_id, project_id=project_id, room_id=room_id, surface_id=surface_id, occurrence_key=occurrence_key,
            origin=ReminderOrigin.USER.value, kind=ev.EventKind.USER.value, title=title, send_at=send_at.astimezone(UTC), tz=prefs.tz_name,
            close_on_status=close_on_status, status=ReminderStatus.PENDING.value, dedupe_key=f"USER|{uuid.uuid4()}",
        )
        self.db.add(row)
        await self.db.commit()
        return row

    async def _place_of_reminder(self, project_id: uuid.UUID | None, room_id: uuid.UUID | None, surface_id: uuid.UUID | None) -> None:
        """The room of a reminder is a room of ITS object and the surface a surface of that room (the message names them: an id of another
        owner's room must never get there). The object itself was checked to be the owner's."""
        if room_id is not None:
            found = None
            if project_id is not None:
                found = (await self.db.execute(select(Room.id).where(Room.id == room_id, Room.project_id == project_id))).scalar_one_or_none()
            if found is None:
                raise ReminderInvalidError("ROOM_NOT_IN_PROJECT")
        if surface_id is not None:
            found = None
            if room_id is not None:
                found = (await self.db.execute(select(Surface.id).where(Surface.id == surface_id, Surface.room_id == room_id))).scalar_one_or_none()
            if found is None:
                raise ReminderInvalidError("SURFACE_NOT_IN_ROOM")

    async def cancel_reminder(self, owner_id: uuid.UUID, reminder_id: uuid.UUID) -> Reminder:
        row = (await self.db.execute(select(Reminder).where(Reminder.id == reminder_id, Reminder.owner_id == owner_id))).scalar_one_or_none()
        if row is None:
            raise ReminderNotFoundError(str(reminder_id))
        if row.status == ReminderStatus.PENDING.value:
            row.status = ReminderStatus.CANCELLED.value
            await self.db.commit()
        return row

    # --- planned dates ---------------------------------------------------------------------------------------------------------------

    async def planned_dates(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> dict[uuid.UUID, date]:
        await self._project(owner_id, project_id)
        rows = (await self.db.execute(select(WorkSchedule).where(WorkSchedule.project_id == project_id))).scalars()
        return {row.occurrence_key: row.planned_date for row in rows}

    async def set_planned_date(
        self, owner_id: uuid.UUID, project_id: uuid.UUID, occurrence_key: uuid.UUID, day: date | None, note: str | None = None
    ) -> None:
        """Plan a work for a day (or clear the date with None) and re-reconcile the object. A date is a hint: nothing is refused."""
        await self._project(owner_id, project_id)
        if occurrence_key not in {step.occurrence_key for _, _, step in await self._steps(project_id)}:
            raise ScheduleOccurrenceNotFoundError(str(occurrence_key))
        row = (await self.db.execute(select(WorkSchedule).where(WorkSchedule.occurrence_key == occurrence_key))).scalar_one_or_none()
        if day is None:
            if row is not None:
                await self.db.delete(row)
        elif row is None:
            self.db.add(WorkSchedule(owner_id=owner_id, project_id=project_id, occurrence_key=occurrence_key, planned_date=day, note=note))
        else:
            row.planned_date, row.note = day, note
        await self.db.flush()
        await self.reconcile_project(owner_id, project_id)
        await self.db.commit()

    async def contract_window(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> tuple[date | None, date | None]:
        """The start and the end of the works as the contract says (the window the planned dates are checked against)."""
        await self._project(owner_id, project_id)
        contract = await self._contract(project_id)
        answers = (contract.answers or {}) if contract else {}
        return _date(answers.get("work_start_date")), _date(answers.get("work_end_date"))

    async def schedule_warnings(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> list[sched.ScheduleWarning]:
        await self._project(owner_id, project_id)
        prefs = await self.prefs(owner_id)
        contract = await self._contract(project_id)
        answers = (contract.answers or {}) if contract else {}
        window = (_date(answers.get("work_start_date")), _date(answers.get("work_end_date")))
        by_surface: dict[uuid.UUID, list[sched.WorkStep]] = {}
        for _, surface_id, step in await self._steps(project_id):
            by_surface.setdefault(surface_id, []).append(step)
        warnings: list[sched.ScheduleWarning] = []
        for steps in by_surface.values():
            warnings += sched.check_schedule(steps, window, prefs.tz)
        return warnings

    async def suggest_dates(
        self, owner_id: uuid.UUID, project_id: uuid.UUID, start: date, room_id: uuid.UUID | None = None
    ) -> dict[uuid.UUID, date]:
        """The proposal of the earliest dates for the not yet done works of the object (or of one room); nothing is saved."""
        await self._project(owner_id, project_id)
        prefs = await self.prefs(owner_id)
        by_surface: dict[uuid.UUID, list[sched.WorkStep]] = {}
        for step_room, surface_id, step in await self._steps(project_id):
            if room_id is None or step_room == room_id:
                by_surface.setdefault(surface_id, []).append(step)
        return sched.suggest_dates(by_surface, start, prefs.tz)

    # --- reading the queue (for the calendar screen of 18E and the delivery loop of 18D) -------------------------------------------------

    async def reminders_of(self, owner_id: uuid.UUID, project_id: uuid.UUID | None = None, *, statuses: Iterable[str] | None = None) -> list[Reminder]:
        stmt = select(Reminder).where(Reminder.owner_id == owner_id).order_by(Reminder.send_at, Reminder.dedupe_key)
        if project_id is not None:
            stmt = stmt.where(Reminder.project_id == project_id)
        if statuses is not None:
            stmt = stmt.where(Reminder.status.in_(list(statuses)))
        return list((await self.db.execute(stmt)).scalars())

    # --- the agenda, the presets, the planned dates in bulk (Stage 18E) ---------------------------------------------------------------------

    async def agenda(
        self, owner_id: uuid.UUID, *, start: date | None = None, end: date | None = None, project_id: uuid.UUID | None = None,
        now: datetime | None = None,
    ) -> ag.Agenda:
        """The agenda of the owner (or of one object) for the period: derived events, own reminders, dated works, overdue works."""
        now = now or datetime.now(UTC)
        prefs = await self.prefs(owner_id)
        today = now.astimezone(prefs.tz).date()
        start = start or today
        end = end or start + timedelta(days=60)
        if project_id is not None:
            await self._project(owner_id, project_id)
        projects = (await self.db.execute(
            select(Project).where(Project.owner_id == owner_id, Project.is_archived.is_(False), *([Project.id == project_id] if project_id else []))
        )).scalars().all()
        names = {p.id: p.name for p in projects}
        items: list[ag.AgendaItem] = []
        works: list[ag.AgendaWork] = []
        overdue: list[ag.AgendaWork] = []
        room_names: dict[uuid.UUID, str] = {}
        surface_names: dict[uuid.UUID, str] = {}
        for project in projects:
            for row in await self._works(project.id):
                room_names[row.room_id], surface_names[row.surface_id] = row.room_name, row.surface_name
                step = row.step
                if step.planned_date is None or step.status == WorkExecutionStatus.COMPLETED:
                    continue
                work = ag.AgendaWork(
                    step.occurrence_key, step.planned_date, step.status, step.wait_after_hours, project.id, project.name, row.room_id, row.room_name,
                    row.surface_id, row.surface_name, row.name_key, row.display_name,
                )
                if step.planned_date < today:
                    overdue.append(work)
                elif start <= step.planned_date <= end:
                    works.append(work)
            for event in ev.sort_events(await self.events_for_project(owner_id, project.id), prefs.tz):
                if start <= event.day(prefs.tz) <= end:
                    items.append(ag.AgendaItem(
                        source="EVENT", kind=event.kind.value, key=event.key, day=event.day(prefs.tz), on=event.on, at=event.at, ref=event.ref,
                        title_key=event.title_key, params=dict(event.params), sends=prefs.sends(event.kind), project_id=project.id,
                        project_name=project.name, room_id=event.room_id, room_name=room_names.get(event.room_id) if event.room_id else None,
                        surface_id=event.surface_id, surface_name=surface_names.get(event.surface_id) if event.surface_id else None,
                        occurrence_key=event.occurrence_key,
                    ))
        own = (await self.db.execute(
            select(Reminder).where(
                Reminder.owner_id == owner_id, Reminder.origin == ReminderOrigin.USER.value, Reminder.status == ReminderStatus.PENDING.value,
                *([Reminder.project_id == project_id] if project_id else []),
            ).order_by(Reminder.send_at)
        )).scalars().all()
        for row in own:
            send_at = _utc_required(row.send_at)
            day = send_at.astimezone(prefs.tz).date()
            if start <= day <= end:
                items.append(ag.AgendaItem(
                    source="REMINDER", kind=ev.EventKind.USER.value, key=str(row.id), day=day, at=send_at, title=row.title, sends=True,
                    reminder_id=row.id, project_id=row.project_id, project_name=names.get(row.project_id) if row.project_id else None,
                    room_id=row.room_id, room_name=room_names.get(row.room_id) if row.room_id else None, surface_id=row.surface_id,
                    surface_name=surface_names.get(row.surface_id) if row.surface_id else None, occurrence_key=row.occurrence_key,
                ))
        items.sort(key=lambda i: (i.day, i.at is not None, i.at or datetime.min.replace(tzinfo=UTC), i.kind, i.key))
        works.sort(key=lambda w: (w.planned_date, w.project_name, w.room_name, w.surface_name))
        overdue.sort(key=lambda w: (w.planned_date, w.project_name, w.room_name, w.surface_name))
        return ag.Agenda(today, start, end, items, works, overdue)

    async def create_reminder_from_preset(
        self, owner_id: uuid.UUID, *, preset: str, title: str | None = None, send_at: datetime | None = None, project_id: uuid.UUID | None = None,
        room_id: uuid.UUID | None = None, surface_id: uuid.UUID | None = None, occurrence_key: uuid.UUID | None = None, now: datetime | None = None,
        local_date: date | None = None, local_time: time | None = None,
    ) -> Reminder:
        """The "Remind" button: the preset says when, the work (if any) says what it is about. The time is computed here, in the owner's zone."""
        now = now or datetime.now(UTC)
        prefs = await self.prefs(owner_id)
        planned_date: date | None = None
        ready_after: datetime | None = None
        work_title: str | None = None
        if occurrence_key is not None:
            if project_id is None:
                raise ag.PresetUnavailableError("WORK_REQUIRED")
            await self._project(owner_id, project_id)
            row = next((w for w in await self._works(project_id) if w.step.occurrence_key == occurrence_key), None)
            if row is None:
                raise ScheduleOccurrenceNotFoundError(str(occurrence_key))
            room_id, surface_id = row.room_id, row.surface_id
            planned_date = row.step.planned_date
            ready_after = derive_ready_after(row.step.status, row.step.completed_at, row.step.wait_after_hours)
            work_title = f"{row.display_name or row.name_key or ''} — {row.surface_name}".strip(" —")
        elif preset in ag.NEEDS_WORK:
            raise ag.PresetUnavailableError("WORK_REQUIRED")
        if preset == ag.PRESET_CUSTOM and send_at is None and local_date is not None and local_time is not None:
            send_at = local_instant(local_date, local_time, prefs.tz)  # the day and the hour the owner typed, in the owner's zone
        moment = ag.preset_instant(preset, prefs, now, planned_date=planned_date, ready_after=ready_after, custom=send_at)
        return await self.create_reminder(
            owner_id, title=(title or "").strip() or work_title or "", send_at=moment, project_id=project_id, room_id=room_id, surface_id=surface_id,
            occurrence_key=occurrence_key, close_on_status=ag.CLOSE_ON.get(preset), now=now,
        )

    async def apply_planned_dates(self, owner_id: uuid.UUID, project_id: uuid.UUID, dates: Mapping[uuid.UUID, date]) -> None:
        """Accept a proposal (or several dates at once): all or nothing, one reconciliation, one commit."""
        await self._project(owner_id, project_id)
        known = {step.occurrence_key for _, _, step in await self._steps(project_id)}
        if any(key not in known for key in dates):
            raise ScheduleOccurrenceNotFoundError("one of the works is not a work of this object")
        existing = {
            row.occurrence_key: row
            for row in (await self.db.execute(select(WorkSchedule).where(WorkSchedule.project_id == project_id))).scalars()
        }
        for key, day in dates.items():
            if key in existing:
                existing[key].planned_date = day
            else:
                self.db.add(WorkSchedule(owner_id=owner_id, project_id=project_id, occurrence_key=key, planned_date=day))
        await self.db.flush()
        await self.reconcile_project(owner_id, project_id)
        await self.db.commit()
