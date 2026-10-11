"""The planned dates of works against the technological breaks (Stage 18C, decision Q12): the check and the proposal.

A work of a surface may follow the previous one only after its technological break. The planned date is a hint: a date earlier than the end
of the break is a **warning**, never a refusal. A break counts in whole days: a planned work with a break of N hours blocks the next one for
ceil(N/24) days (a short break of 8 h still means the next day: the work is done at the end of a day); the break of a *completed* work is the
real `ready_after` of Stage 13. Pure functions over plain steps.
"""
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, tzinfo

from app.domain.calendar import DEFAULT_TIMEZONE
from app.domain.calendar.working_days import working_day_on_or_after
from app.domain.rules.work_execution_rules import derive_ready_after
from app.models.work_execution import WorkExecutionStatus

BEFORE_BREAK_END = "BEFORE_BREAK_END"  # planned earlier than the previous work may be followed
BEFORE_CONTRACT_START = "BEFORE_CONTRACT_START"
AFTER_CONTRACT_END = "AFTER_CONTRACT_END"


@dataclass(frozen=True)
class WorkStep:
    """One planned work of a surface, in the order of the plan."""

    occurrence_key: uuid.UUID
    position: int
    wait_after_hours: int | None = None
    status: WorkExecutionStatus = WorkExecutionStatus.NOT_STARTED
    completed_at: datetime | None = None
    planned_date: date | None = None


@dataclass(frozen=True)
class ScheduleWarning:
    occurrence_key: uuid.UUID
    code: str
    date: date  # the date that explains the warning: the earliest start, or the start / the end of the contract


def break_days(wait_after_hours: int | None) -> int:
    return -(-wait_after_hours // 24) if wait_after_hours and wait_after_hours > 0 else 0


def earliest_start(previous: WorkStep, tz: tzinfo = DEFAULT_TIMEZONE) -> date | None:
    """The first day the work after `previous` may be done; None when nothing is known about `previous`."""
    if previous.status == WorkExecutionStatus.COMPLETED and previous.completed_at is not None:
        ready = derive_ready_after(previous.status, previous.completed_at, previous.wait_after_hours) or previous.completed_at
        return ready.astimezone(tz).date()
    if previous.planned_date is not None:
        return previous.planned_date + timedelta(days=break_days(previous.wait_after_hours))
    return None


def check_schedule(
    steps: Sequence[WorkStep], window: tuple[date | None, date | None] = (None, None), tz: tzinfo = DEFAULT_TIMEZONE
) -> list[ScheduleWarning]:
    """The warnings of the planned dates of one surface (a completed work is history and is not checked)."""
    ordered = sorted(steps, key=lambda s: s.position)
    warnings: list[ScheduleWarning] = []
    start, end = window
    for index, step in enumerate(ordered):
        if step.status == WorkExecutionStatus.COMPLETED or step.planned_date is None:
            continue
        earliest = earliest_start(ordered[index - 1], tz) if index else None
        if earliest is not None and step.planned_date < earliest:
            warnings.append(ScheduleWarning(step.occurrence_key, BEFORE_BREAK_END, earliest))
        if start is not None and step.planned_date < start:
            warnings.append(ScheduleWarning(step.occurrence_key, BEFORE_CONTRACT_START, start))
        if end is not None and step.planned_date > end:
            warnings.append(ScheduleWarning(step.occurrence_key, AFTER_CONTRACT_END, end))
    return warnings


def suggest_dates(
    surfaces: Mapping[uuid.UUID, Sequence[WorkStep]], start: date, tz: tzinfo = DEFAULT_TIMEZONE
) -> dict[uuid.UUID, date]:
    """The earliest working days for the works not yet done, from `start`, in the order of each surface and after each break.

    The surfaces are independent (they may be worked the same day). Nothing is saved: the owner accepts the proposal or not.
    """
    proposal: dict[uuid.UUID, date] = {}
    for steps in surfaces.values():
        previous: WorkStep | None = None
        for step in sorted(steps, key=lambda s: s.position):
            if step.status == WorkExecutionStatus.COMPLETED:
                previous = step
                continue
            day = working_day_on_or_after(start)
            if previous is not None:
                earliest = earliest_start(previous, tz)
                if earliest is not None:
                    day = working_day_on_or_after(max(day, earliest))
            proposal[step.occurrence_key] = day
            previous = replace(step, planned_date=day)
    return proposal
