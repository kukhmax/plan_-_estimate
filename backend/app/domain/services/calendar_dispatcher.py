"""The loop that sends the reminders to the owner's chat (Stage 18D).

Each pass: bring back what a crashed pass left half done, take what is due (`FOR UPDATE SKIP LOCKED`, so even two processes would never take
the same row), put it together into messages (`domain/calendar/messages.py`), send, and record the outcome on every reminder. The rules:
- an automatic reminder is not sent in the owner's quiet hours (it waits for the morning); the owner's own reminder is (they chose the time);
- later than 15 minutes after its time a message says it is late; later than 24 hours it is not sent at all (MISSED);
- Telegram "blocked" or "rejected" is final (FAILED with the reason); "slow down", 5xx and no connection are retried 1, 5, 15, 15 minutes, five
  attempts in all; a message that was taken and not finished for 5 minutes goes back to the queue (at-least-once: in the rare window of a crash
  a message may be sent twice, never lost);
- at most `max_per_day` messages to one owner in 24 hours (the rest is SKIPPED with the reason), a pause between two messages to one chat.
A fault of one owner or one message is logged and never stops the pass.
"""
import asyncio
import logging
import time as monotonic
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.domain.calendar import policy
from app.domain.calendar.messages import (
    LANGUAGES,
    Message,
    ReminderView,
    compose_messages,
    language_of_telegram,
)
from app.domain.calendar.prefs import CalendarPrefs, in_quiet_hours
from app.domain.documents.delivery import (
    DisabledMessageSender,
    MessageSender,
    message_sender_from_settings,
)
from app.domain.exceptions import (
    MessageDeliveryDisabledError,
    MessageDeliveryError,
    MessageUnavailableError,
)
from app.domain.services.data_key_service import DataKeyService
from app.domain.services.calendar_service import CalendarService
from app.models.project import Project
from app.models.reminder import Reminder, ReminderOrigin, ReminderStatus
from app.models.room import Room
from app.models.surface import Surface
from app.models.user import User

logger = logging.getLogger(__name__)

CLAIM_LIMIT = 100  # rows read at a time
MAX_PAGES = 20  # pages of one pass: a queue longer than this waits for the next pass (2000 reminders)
SessionFactory = Callable[[], AsyncSession]


@dataclass
class TickReport:
    recovered: int = 0
    claimed: int = 0
    messages: int = 0
    sent: int = 0  # reminders sent
    retried: int = 0
    failed: int = 0
    missed: int = 0
    skipped: int = 0
    deferred_quiet: int = 0
    deferred_off: int = 0
    errors: list[str] = field(default_factory=list)


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class CalendarDispatcher:
    def __init__(
        self, session_factory: SessionFactory, sender: MessageSender, *, web_app_url: str = "", max_per_day: int = 100,
        pause_seconds: float = 0.0, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._sessions = session_factory
        self._sender = sender
        self._web_app_url = web_app_url
        self._max_per_day = max_per_day
        self._pause = pause_seconds
        self._sleep = sleep

    # --- the pass -------------------------------------------------------------------------------------------------------------------

    async def reconcile_all(self, now: datetime | None = None) -> int:
        """Bring the queue of every owner in step with the data (the periodic pass; the statuses and the archive do it at once)."""
        async with self._sessions() as db:
            await DataKeyService(db).prepare()  # the names of the objects are ciphertext: the keys must be in the ring before they are read
            owners = (await db.execute(select(Project.owner_id).distinct())).scalars().all()
        done = 0
        for owner_id in owners:
            try:
                async with self._sessions() as db:
                    await CalendarService(db).reconcile_owner(owner_id, now=now)
                    await db.commit()
                done += 1
            except Exception:  # one owner's fault must not stop the others
                logger.exception("calendar reconciliation failed for an owner")
        return done

    async def tick(self, now: datetime | None = None) -> TickReport:
        now = now or datetime.now(UTC)
        report = TickReport()
        async with self._sessions() as db:
            await DataKeyService(db).prepare()
            report.recovered = await self._recover_stale(db, now)
            claimed = await self._claim(db, now, report)
        for owner_id, ids in claimed.items():
            try:
                await self._deliver(owner_id, ids, now, report)
            except Exception as error:  # a bug in one owner's delivery: the rows go back with a backoff, the pass goes on
                logger.exception("calendar delivery failed for an owner")
                report.errors.append(type(error).__name__)
                await self._release(ids, now, None)
        return report

    # --- steps ----------------------------------------------------------------------------------------------------------------------

    async def _recover_stale(self, db: AsyncSession, now: datetime) -> int:
        rows = (await db.execute(
            select(Reminder).where(Reminder.status == ReminderStatus.SENDING.value, Reminder.locked_at < now - policy.STALE_SENDING)
        )).scalars().all()
        for row in rows:
            row.locked_at = None
            if row.attempts >= policy.MAX_ATTEMPTS:
                row.status, row.error_code = ReminderStatus.FAILED.value, "GIVE_UP"
            else:
                row.status = ReminderStatus.PENDING.value
        await db.commit()
        return len(rows)

    async def _claim(self, db: AsyncSession, now: datetime, report: TickReport) -> dict[uuid.UUID, list[uuid.UUID]]:
        """Take what is due, page by page (by time and id): a reminder that has to wait (quiet hours, the messages switched off) stays in
        the queue and must not hide the ones behind it, so the pass goes on to the next page until the queue of the due is over."""
        prefs: dict[uuid.UUID, CalendarPrefs] = {}
        sent_today: dict[uuid.UUID, int] = {}
        claimed: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
        after: tuple[datetime, uuid.UUID] | None = None
        for _ in range(MAX_PAGES):
            stmt = select(Reminder).where(Reminder.status == ReminderStatus.PENDING.value, Reminder.send_at <= now)
            if after is not None:
                stmt = stmt.where(tuple_(Reminder.send_at, Reminder.id) > tuple_(after[0], after[1]))
            rows = (await db.execute(stmt.order_by(Reminder.send_at, Reminder.id).limit(CLAIM_LIMIT).with_for_update(skip_locked=True))).scalars().all()
            if not rows:
                break
            after = (rows[-1].send_at, rows[-1].id)
            for row in rows:
                if row.owner_id not in prefs:
                    prefs[row.owner_id] = await CalendarService(db).prefs(row.owner_id)
                    sent_today[row.owner_id] = (await db.execute(
                        select(func.count()).select_from(Reminder).where(
                            Reminder.owner_id == row.owner_id, Reminder.status == ReminderStatus.SENT.value, Reminder.sent_at > now - timedelta(hours=24)
                        )
                    )).scalar_one()
                owner_prefs = prefs[row.owner_id]
                late = policy.lateness(_utc(row.send_at), now)
                if late == policy.MISSED:
                    row.status, report.missed = ReminderStatus.MISSED.value, report.missed + 1
                elif not owner_prefs.enabled:
                    report.deferred_off += 1  # the owner switched the messages off: nothing goes, nothing is lost until it is too late
                elif row.origin == ReminderOrigin.AUTO.value and in_quiet_hours(now.astimezone(owner_prefs.tz).time(), owner_prefs.quiet_from, owner_prefs.quiet_to):
                    report.deferred_quiet += 1  # stays PENDING: it goes in the morning
                elif sent_today[row.owner_id] + len(claimed[row.owner_id]) >= self._max_per_day:
                    row.status, row.error_code, report.skipped = ReminderStatus.SKIPPED.value, "DAILY_LIMIT", report.skipped + 1
                else:
                    row.status, row.locked_at, row.attempts = ReminderStatus.SENDING.value, now, row.attempts + 1
                    claimed[row.owner_id].append(row.id)
                    report.claimed += 1
            if len(rows) < CLAIM_LIMIT:
                break
        await db.commit()
        return dict(claimed)

    async def _views(self, db: AsyncSession, ids: list[uuid.UUID]) -> list[ReminderView]:
        rows = (await db.execute(
            select(Reminder, Project.name, Room.name, Surface.name)
            .outerjoin(Project, Project.id == Reminder.project_id)
            .outerjoin(Room, Room.id == Reminder.room_id)
            .outerjoin(Surface, Surface.id == Reminder.surface_id)
            .where(Reminder.id.in_(ids))
        )).all()
        return [
            ReminderView(r.id, r.origin, r.kind, r.ref, r.title, r.title_key, dict(r.params or {}), r.event_on, r.lead_days, _utc(r.send_at),
                         r.project_id, project, r.room_id, room, surface)
            for r, project, room, surface in rows
        ]

    async def _deliver(self, owner_id: uuid.UUID, ids: list[uuid.UUID], now: datetime, report: TickReport) -> None:
        async with self._sessions() as db:
            user = (await db.execute(select(User).where(User.id == owner_id))).scalar_one_or_none()
            prefs = await CalendarService(db).prefs(owner_id)
            views = await self._views(db, ids)
        if user is None or user.telegram_user_id <= 0:  # the owner is gone, or signs in without Telegram (V2-1) and has no chat: nothing to deliver to
            await self._finish(ids, ReminderStatus.CANCELLED, now, None)
            return
        language = prefs.language or language_of_telegram(user.language_code)
        messages = compose_messages(views, lang=language if language in LANGUAGES else "pl", now=now, base_url=self._web_app_url, tz=prefs.tz)
        for index, message in enumerate(messages):
            if index and self._pause:
                await self._sleep(self._pause)
            report.messages += 1
            try:
                await self._sender.send_message(user.telegram_user_id, message.text, open_url=message.open_url, button_text=message.button)
            except MessageDeliveryError as error:
                rest = [rid for later in messages[index + 1:] for rid in later.reminder_ids]
                await self._after_failure(message, rest, error, now, report)
                return
            await self._finish(list(message.reminder_ids), ReminderStatus.SENT, now, None)
            report.sent += len(message.reminder_ids)

    async def _after_failure(self, message: Message, rest: list[uuid.UUID], error: MessageDeliveryError, now: datetime, report: TickReport) -> None:
        ids = list(message.reminder_ids)
        if isinstance(error, MessageUnavailableError | MessageDeliveryDisabledError):  # temporary: try again later
            retried = await self._release(ids, now, error)
            report.retried += retried
            report.failed += len(ids) - retried
            await self._release(rest, now, error, count_attempt=False)  # not tried: wait with the first and do not spend their attempts
            return
        # final (blocked, refused): the chat will not take the rest either
        await self._finish(ids + rest, ReminderStatus.FAILED, now, error.code)
        report.failed += len(ids) + len(rest)

    async def _finish(self, ids: list[uuid.UUID], status: ReminderStatus, now: datetime, error_code: str | None) -> None:
        if not ids:
            return
        async with self._sessions() as db:
            for row in (await db.execute(select(Reminder).where(Reminder.id.in_(ids)))).scalars():
                row.status, row.error_code, row.locked_at = status.value, error_code, None
                if status == ReminderStatus.SENT:
                    row.sent_at = now
            await db.commit()

    async def _release(self, ids: list[uuid.UUID], now: datetime, error: MessageDeliveryError | None, *, count_attempt: bool = True) -> int:
        """Put the taken reminders back with a delay (or give them up when the attempts are used); returns how many wait for another try."""
        if not ids:
            return 0
        waiting = 0
        async with self._sessions() as db:
            for row in (await db.execute(select(Reminder).where(Reminder.id.in_(ids)))).scalars():
                if not count_attempt:
                    row.attempts = max(0, row.attempts - 1)
                delay = policy.retry_delay(max(row.attempts, 1) if count_attempt else row.attempts, error.retry_after if error else None)
                row.locked_at = None
                if delay is None:
                    row.status, row.error_code = ReminderStatus.FAILED.value, "GIVE_UP"
                else:
                    row.status, row.send_at, row.error_code = ReminderStatus.PENDING.value, now + delay, error.code if error else "ERROR"
                    waiting += 1
            await db.commit()
        return waiting


async def run_loop(
    dispatcher: CalendarDispatcher, *, interval: float, reconcile_every: float, stop: asyncio.Event
) -> None:
    """The loop of the application: a reconciliation now and then, a pass every `interval`, until `stop` is set. A fault is logged, the loop goes on."""
    last_reconcile: float | None = None
    while not stop.is_set():
        try:
            if last_reconcile is None or monotonic.monotonic() - last_reconcile >= reconcile_every:
                await dispatcher.reconcile_all()
                last_reconcile = monotonic.monotonic()
            await dispatcher.tick()
        except Exception:
            logger.exception("calendar loop pass failed")
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError:
            pass


@dataclass
class RunningLoop:
    task: asyncio.Task[None]
    stop_event: asyncio.Event

    async def stop(self, timeout: float = 10.0) -> None:
        """Ask the loop to finish its pass and wait for it; a loop that does not finish in time is cancelled."""
        self.stop_event.set()
        try:
            await asyncio.wait_for(self.task, timeout=timeout)
        except TimeoutError:
            logger.error("calendar loop did not stop in %s s: cancelled", timeout)


def start_dispatcher(settings: Settings, session_factory: SessionFactory, sender: MessageSender | None = None) -> RunningLoop | None:
    """Start the loop when the owner switched it on and the bot can write; otherwise say why not and start nothing."""
    if not settings.CALENDAR_DISPATCHER_ENABLED:
        return None
    sender = sender or message_sender_from_settings(settings)
    if isinstance(sender, DisabledMessageSender):
        logger.error("CALENDAR_DISPATCHER_ENABLED is on but there is no bot token: the calendar loop is not started")
        return None
    dispatcher = CalendarDispatcher(
        session_factory, sender, web_app_url=settings.CALENDAR_WEB_APP_URL, max_per_day=settings.CALENDAR_MAX_PER_DAY,
        pause_seconds=settings.CALENDAR_SEND_PAUSE_SECONDS,
    )
    stop = asyncio.Event()
    task = asyncio.create_task(
        run_loop(dispatcher, interval=settings.CALENDAR_DISPATCH_INTERVAL_SECONDS, reconcile_every=settings.CALENDAR_RECONCILE_INTERVAL_SECONDS, stop=stop),
        name="calendar-dispatcher",
    )
    logger.info("calendar loop started (every %s s)", settings.CALENDAR_DISPATCH_INTERVAL_SECONDS)
    return RunningLoop(task, stop)
