"""Deterministic execution-state rules (Stage 13H).

Pure functions/values shared by the execution service and the WorkPlan read
path (which attaches each current occurrence's execution view), kept outside
both services so neither imports the other. See
docs/STAGE_13_TECHNOLOGICAL_WORKFLOWS_ARCHITECTURE.md §33.
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.models.work_execution import SurfaceWorkExecution, WorkExecutionStatus

S = WorkExecutionStatus

ALLOWED_TRANSITIONS: frozenset[tuple[WorkExecutionStatus, WorkExecutionStatus]] = frozenset(
    {
        (S.NOT_STARTED, S.IN_PROGRESS),
        (S.IN_PROGRESS, S.COMPLETED),
        (S.NOT_STARTED, S.COMPLETED),
        (S.COMPLETED, S.IN_PROGRESS),
        (S.IN_PROGRESS, S.NOT_STARTED),
    }
)


def derive_ready_after(
    status: WorkExecutionStatus,
    completed_at: datetime | None,
    wait_after_hours: int | None,
) -> datetime | None:
    """Earliest technological readiness after a COMPLETED occurrence (D-H12):
    completed_at + the occurrence's CURRENT break. Derived on read, never
    stored; None when the work is not completed or has no break. Not a
    scheduled start, calendar event or reminder (Stage 18)."""
    if status != S.COMPLETED or completed_at is None or wait_after_hours is None:
        return None
    return completed_at + timedelta(hours=wait_after_hours)


@dataclass(frozen=True)
class OccurrenceExecution:
    """Read view of one occurrence's execution state."""

    occurrence_key: uuid.UUID
    status: WorkExecutionStatus
    started_at: datetime | None
    completed_at: datetime | None
    ready_after: datetime | None


def execution_view(
    key: uuid.UUID,
    execution: SurfaceWorkExecution | None,
    wait_after_hours: int | None,
) -> OccurrenceExecution:
    """The occurrence's execution view; no row = NOT_STARTED (D-H20)."""
    if execution is None:
        return OccurrenceExecution(key, S.NOT_STARTED, None, None, None)
    return OccurrenceExecution(
        occurrence_key=key,
        status=execution.status,
        started_at=execution.started_at,
        completed_at=execution.completed_at,
        ready_after=derive_ready_after(
            execution.status, execution.completed_at, wait_after_hours
        ),
    )


# Stage 13H.4: execution that a destructive WorkPlan mutation must not detach
# silently. NOT_STARTED (with or without an explicit row) is never protected.
PROTECTED_STATUSES: frozenset[WorkExecutionStatus] = frozenset({S.IN_PROGRESS, S.COMPLETED})


@dataclass(frozen=True)
class AffectedExecution:
    """One protected execution record that a requested WorkPlan mutation
    would detach from the current plan (Stage 13H.4). Built only from the
    target plan(s) the caller owns; never from confirmation input."""

    surface_id: uuid.UUID
    occurrence_key: uuid.UUID
    position: int
    status: WorkExecutionStatus
    price_item_id: uuid.UUID
    price_item_code: str
    price_item_name_key: str | None
    price_item_display_name: str | None


def detach_confirmation_matches(
    protected_keys: set[uuid.UUID], confirmed_keys: set[uuid.UUID]
) -> bool:
    """Exact-set rule (D-H7): the confirmation must equal the protected set --
    a subset, a superset, or stale/unrelated keys all mismatch."""
    return protected_keys == confirmed_keys


# ---------------------------------------------------------------------------
# Stage 13H.5B — bulk execution progress across the walls of one room.
# ---------------------------------------------------------------------------

EXECUTION_RANK: dict[WorkExecutionStatus, int] = {
    S.NOT_STARTED: 0,
    S.IN_PROGRESS: 1,
    S.COMPLETED: 2,
}


@dataclass(frozen=True)
class BulkWork:
    """One CURRENT occurrence as seen by the bulk engine (read-only input)."""

    occurrence_key: uuid.UUID
    price_item_id: uuid.UUID
    position: int
    status: WorkExecutionStatus


@dataclass(frozen=True)
class BulkTransition:
    """A forward transition to perform on ONE destination occurrence. The
    destination key is its own execution identity; nothing of the source
    occurrence (key, timestamps) travels with it."""

    surface_id: uuid.UUID
    occurrence_key: uuid.UUID
    from_status: WorkExecutionStatus
    to_status: WorkExecutionStatus


@dataclass
class BulkWallPlan:
    surface_id: uuid.UUID
    has_plan: bool
    changed: int = 0
    unchanged: int = 0
    unmatched: int = 0
    ambiguous: int = 0
    unmatched_price_item_ids: list[uuid.UUID] = field(default_factory=list)
    ambiguous_price_item_ids: list[uuid.UUID] = field(default_factory=list)


@dataclass
class BulkExecutionPlan:
    walls: list[BulkWallPlan]
    transitions: list[BulkTransition]

    @property
    def changed(self) -> int:
        return sum(w.changed for w in self.walls)

    @property
    def unchanged(self) -> int:
        return sum(w.unchanged for w in self.walls)

    @property
    def unmatched(self) -> int:
        return sum(w.unmatched for w in self.walls)

    @property
    def ambiguous(self) -> int:
        return sum(w.ambiguous for w in self.walls)


def _groups(works: list[BulkWork]) -> dict[uuid.UUID, list[BulkWork]]:
    groups: dict[uuid.UUID, list[BulkWork]] = {}
    for work in sorted(works, key=lambda w: w.position):
        groups.setdefault(work.price_item_id, []).append(work)
    return groups


def calculate_bulk_execution_plan(
    source: list[BulkWork],
    targets: list[tuple[uuid.UUID, list[BulkWork] | None]],
) -> BulkExecutionPlan:
    """The ONE canonical matching/planning engine of Stage 13H.5B (used by
    both preview and apply). Pure: no I/O, no mutation.

    Matching (BULK-H1/H2), per destination wall: the k-th occurrence of a
    PriceItem on the source (by position) pairs with the k-th occurrence of
    the same PriceItem on the destination -- only when that PriceItem occurs
    the SAME number of times on both walls; otherwise the whole PriceItem
    group is ambiguous on that wall and nothing in it is touched. Relative
    order of different PriceItems is irrelevant. Never keys, row ids,
    absolute positions or template provenance.

    Transitions (BULK-H3/H4): forward only -- act when destination rank <
    source rank (NS→IP, NS→C, IP→C); source NOT_STARTED never acts; an equal
    or further destination is left alone.

    Counts are OCCURRENCE counts from the source's point of view, one bucket
    per (source occurrence × destination wall), so nothing is double
    counted and per wall changed + unchanged + unmatched + ambiguous ==
    number of source occurrences:
    - changed: matched pair whose destination will be advanced;
    - unchanged: matched pair needing nothing (source NOT_STARTED, or
      destination equal/further);
    - unmatched: the PriceItem is absent on that wall, or the wall has no
      plan;
    - ambiguous: the PriceItem's duplicate counts differ.
    Extra destination works (PriceItems the source lacks) are untouched and
    not counted.
    """
    source_groups = _groups(source)
    walls: list[BulkWallPlan] = []
    transitions: list[BulkTransition] = []
    for surface_id, target_works in targets:
        wall = BulkWallPlan(surface_id=surface_id, has_plan=target_works is not None)
        target_groups = _groups(target_works or [])
        for price_item_id, source_group in source_groups.items():
            target_group = target_groups.get(price_item_id)
            if not target_group:
                wall.unmatched += len(source_group)
                wall.unmatched_price_item_ids.append(price_item_id)
                continue
            if len(target_group) != len(source_group):
                wall.ambiguous += len(source_group)
                wall.ambiguous_price_item_ids.append(price_item_id)
                continue
            for src, dst in zip(source_group, target_group):
                if EXECUTION_RANK[dst.status] < EXECUTION_RANK[src.status]:
                    wall.changed += 1
                    transitions.append(
                        BulkTransition(surface_id, dst.occurrence_key, dst.status, src.status)
                    )
                else:
                    wall.unchanged += 1
        wall.unmatched_price_item_ids.sort(key=str)
        wall.ambiguous_price_item_ids.sort(key=str)
        walls.append(wall)
    return BulkExecutionPlan(walls=walls, transitions=transitions)
