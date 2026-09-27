"""Surface work execution domain service (Stage 13H.2).

Records the actual execution state of a surface planned-work occurrence,
keyed by its durable `occurrence_key` (D-H1). Execution never travels in the
WorkPlan save payload and never touches pricing (D-H15, D-H16). See
docs/STAGE_13_TECHNOLOGICAL_WORKFLOWS_ARCHITECTURE.md §33.

Transitions (D-H5/D-H6), all timestamps server-generated UTC:

- NOT_STARTED -> IN_PROGRESS: started_at = now
- IN_PROGRESS -> COMPLETED:   completed_at = now
- NOT_STARTED -> COMPLETED:   shortcut; started_at = completed_at = now
- COMPLETED   -> IN_PROGRESS: reopen; started_at kept, completed_at cleared
- IN_PROGRESS -> NOT_STARTED: reset; started_at cleared (row kept)

COMPLETED -> NOT_STARTED is not a transition: reopen first.

Order of checks (D-H18): a request for the status the occurrence already has
succeeds without changing anything; otherwise a stale `expected_status` or a
disallowed transition is a conflict. Every transition runs under the plan row
lock and only for a key that is CURRENT in that plan (D-H17); an unknown,
removed, foreign or invented key gets the same non-leaking conflict as a
WorkPlan save (D13).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import (
    SurfaceWorkPlanOccurrenceConflictError,
    WorkExecutionConflictError,
    WorkExecutionSourceChangedError,
    WorkExecutionValidationError,
)
from app.domain.rules.work_execution_rules import (  # noqa: F401 (re-exported)
    ALLOWED_TRANSITIONS,
    BulkExecutionPlan,
    BulkWork,
    OccurrenceExecution,
    calculate_bulk_execution_plan,
    derive_ready_after,
    execution_view,
)
from app.domain.services.work_plan_service import SurfaceWorkPlanService
from app.models.project import Project
from app.models.room import Room
from app.models.surface import Surface, SurfaceType
from app.models.work_execution import SurfaceWorkExecution, WorkExecutionStatus
from app.models.work_plan import SurfacePlannedWork, SurfaceWorkPlan

S = WorkExecutionStatus


def _apply_transition(
    execution: SurfaceWorkExecution,
    current: WorkExecutionStatus,
    status: WorkExecutionStatus,
    now: datetime,
) -> None:
    """Set status + timestamps for one allowed transition (D-H5/D-H6); the
    single implementation shared by the per-occurrence and bulk paths."""
    if status == S.IN_PROGRESS and current == S.NOT_STARTED:
        execution.started_at = now
    elif status == S.IN_PROGRESS:  # reopen: keep started_at
        execution.completed_at = None
    elif status == S.COMPLETED:
        if current == S.NOT_STARTED:  # shortcut: both recorded now
            execution.started_at = now
        execution.completed_at = now
    else:  # reset IN_PROGRESS -> NOT_STARTED
        execution.started_at = None
    execution.status = status


class SurfaceWorkExecutionService:
    """Owner-scoped execution state of surface planned-work occurrences."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.plans = SurfaceWorkPlanService(db)

    async def _executions_by_key(
        self, keys: list[uuid.UUID]
    ) -> dict[uuid.UUID, SurfaceWorkExecution]:
        if not keys:
            return {}
        rows = (
            await self.db.execute(
                select(SurfaceWorkExecution)
                .where(SurfaceWorkExecution.occurrence_key.in_(keys))
                .execution_options(populate_existing=True)
            )
        ).scalars().all()
        return {row.occurrence_key: row for row in rows}

    async def get_plan_executions(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        surface_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> list[OccurrenceExecution]:
        """Execution state of every CURRENT occurrence of the surface's plan,
        in plan order (empty when unplanned). Detached records (keys no longer
        in the plan) are not listed. Reads work on archived surfaces (D-H19)."""
        plan = await self.plans.get_work_plan(project_id, room_id, surface_id, owner_id)
        if plan is None:
            return []
        # The WorkPlan read path attaches each current occurrence's view (13H.3).
        return [w.execution for w in plan.planned_works]

    async def _ensure_active(
        self, project_id: uuid.UUID, room_id: uuid.UUID, surface_archived: bool
    ) -> None:
        room_archived = (
            await self.db.execute(select(Room.is_archived).where(Room.id == room_id))
        ).scalar_one()
        project_archived = (
            await self.db.execute(select(Project.is_archived).where(Project.id == project_id))
        ).scalar_one()
        if surface_archived or room_archived or project_archived:
            raise WorkExecutionValidationError(
                "execution cannot change on an archived project, room or surface; "
                "restore it first"
            )

    async def transition(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        surface_id: uuid.UUID,
        owner_id: uuid.UUID,
        occurrence_key: uuid.UUID,
        *,
        status: WorkExecutionStatus,
        expected_status: WorkExecutionStatus,
    ) -> OccurrenceExecution:
        """Move one current occurrence to `status` atomically (see module
        docstring) and commit. An idempotent repeat writes nothing; its commit
        only releases the lock. On a raised error nothing was written and the
        caller's transaction is rolled back by the request scope."""
        surface = await self.plans._ensure_surface_owned(
            project_id, room_id, surface_id, owner_id
        )
        await self._ensure_active(project_id, room_id, surface.is_archived)
        plan = await self.plans.lock_plan(surface_id)
        work = None
        if plan is not None:
            work = (
                await self.db.execute(
                    select(SurfacePlannedWork).where(
                        SurfacePlannedWork.work_plan_id == plan.id,
                        SurfacePlannedWork.occurrence_key == occurrence_key,
                    )
                )
            ).scalar_one_or_none()
        if work is None:
            raise SurfaceWorkPlanOccurrenceConflictError(
                f"occurrence_key {occurrence_key} is not a current occurrence of this "
                "work plan; reload the plan and try again"
            )

        wait_after_hours = work.wait_after_hours
        execution = (await self._executions_by_key([occurrence_key])).get(occurrence_key)
        current = execution.status if execution is not None else S.NOT_STARTED

        if current == status:  # idempotent: nothing changes
            view = execution_view(occurrence_key, execution, wait_after_hours)
            await self.db.commit()  # release the lock; nothing was written
            return view
        if current != expected_status or (current, status) not in ALLOWED_TRANSITIONS:
            raise WorkExecutionConflictError(
                f"execution of occurrence {occurrence_key} is {current.value}; "
                f"cannot move to {status.value} (expected {expected_status.value})",
                current,
            )

        if execution is None:
            execution = SurfaceWorkExecution(
                occurrence_key=occurrence_key,
                work_plan_id=plan.id,
                price_item_id=work.price_item_id,
                status=S.NOT_STARTED,
            )
            self.db.add(execution)

        _apply_transition(execution, current, status, datetime.now(timezone.utc))

        view = execution_view(occurrence_key, execution, wait_after_hours)
        await self.db.commit()
        return view

    # -----------------------------------------------------------------------
    # Stage 13H.5B -- bulk execution progress across the room's walls
    # -----------------------------------------------------------------------

    async def _bulk_scope(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        source_surface_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> list[uuid.UUID]:
        """Ownership (existing 404 chain), then BULK-H8/target-scope rules;
        returns the target surface ids: active WALLs of the SAME room, never
        the source, in the same order as WorkPlan apply-to-all."""
        source = await self.plans._ensure_surface_owned(
            project_id, room_id, source_surface_id, owner_id
        )
        if source.surface_type != SurfaceType.WALL:
            raise WorkExecutionValidationError(
                "applying execution statuses to room walls requires a WALL source surface"
            )
        await self._ensure_active(project_id, room_id, source.is_archived)
        return list(
            (
                await self.db.execute(
                    select(Surface.id)
                    .where(
                        Surface.room_id == source.room_id,
                        Surface.surface_type == SurfaceType.WALL,
                        Surface.id != source.id,
                        Surface.is_archived.is_(False),
                    )
                    .order_by(Surface.position.nulls_last(), Surface.id)
                )
            ).scalars().all()
        )

    @staticmethod
    def _bulk_works(plan: SurfaceWorkPlan | None) -> list[BulkWork] | None:
        if plan is None:
            return None
        return [
            BulkWork(w.occurrence_key, w.price_item_id, w.position, w.execution.status)
            for w in sorted(plan.planned_works, key=lambda w: w.position)
        ]

    @staticmethod
    def _snapshot(works: list[BulkWork] | None) -> list[tuple[uuid.UUID, WorkExecutionStatus]]:
        """Canonical exact ordered source snapshot (every current occurrence,
        NOT_STARTED included)."""
        return [(w.occurrence_key, w.status) for w in (works or [])]

    async def preview_room_walls(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        source_surface_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> tuple[list[tuple[uuid.UUID, WorkExecutionStatus]], BulkExecutionPlan]:
        """Read-only preview (BULK-H10): no lock, no write. Returns the
        canonical `expected_source` snapshot to send back on apply and the
        plan from the SAME engine apply uses. Numbers may be stale by apply
        time; apply recomputes under locks."""
        target_ids = await self._bulk_scope(project_id, room_id, source_surface_id, owner_id)
        source = self._bulk_works(await self.plans._fetch_plan(source_surface_id))
        targets = [(sid, self._bulk_works(await self.plans._fetch_plan(sid))) for sid in target_ids]
        return self._snapshot(source), calculate_bulk_execution_plan(source or [], targets)

    async def apply_room_walls(
        self,
        project_id: uuid.UUID,
        room_id: uuid.UUID,
        source_surface_id: uuid.UUID,
        owner_id: uuid.UUID,
        expected_source: list[tuple[uuid.UUID, WorkExecutionStatus]],
    ) -> tuple[list[tuple[uuid.UUID, WorkExecutionStatus]], BulkExecutionPlan]:
        """Atomic bulk apply (BULK-H7/H9): lock the source plan and every
        existing target plan in ascending plan id, re-read them, require the
        exact ordered `expected_source`, run the canonical engine and perform
        only its forward transitions; one commit. Writes nothing but
        execution rows of destination occurrences -- never the source, never
        any plan row, key, wait, coefficient or Estimate; removes nothing, so
        no detach guard applies."""
        target_ids = await self._bulk_scope(project_id, room_id, source_surface_id, owner_id)
        plan_ids = (
            await self.db.execute(
                select(SurfaceWorkPlan.id, SurfaceWorkPlan.surface_id).where(
                    SurfaceWorkPlan.surface_id.in_([source_surface_id, *target_ids])
                )
            )
        ).all()
        for plan_id in sorted(pid for pid, _ in plan_ids):
            await self.db.execute(
                select(SurfaceWorkPlan.id).where(SurfaceWorkPlan.id == plan_id).with_for_update()
            )
        # Only plans locked above take part; a plan created meanwhile on a
        # target wall is treated as "no plan" (never mutated unlocked).
        locked_surfaces = {sid for _, sid in plan_ids}

        async def locked_works(surface_id: uuid.UUID) -> list[BulkWork] | None:
            if surface_id not in locked_surfaces:
                return None
            return self._bulk_works(await self.plans._fetch_plan(surface_id))

        source = await locked_works(source_surface_id)
        current = self._snapshot(source)
        if current != list(expected_source):
            raise WorkExecutionSourceChangedError(
                "the source wall's works or statuses changed since the preview; "
                "review the preview again",
                current,
            )
        targets = [(sid, await locked_works(sid)) for sid in target_ids]
        plan = calculate_bulk_execution_plan(source or [], targets)

        keys = [t.occurrence_key for t in plan.transitions]
        rows = await self._executions_by_key(keys)
        works = {
            w.occurrence_key: w
            for w in (
                await self.db.execute(
                    select(SurfacePlannedWork).where(SurfacePlannedWork.occurrence_key.in_(keys))
                )
            ).scalars().all()
        } if keys else {}
        now = datetime.now(timezone.utc)
        for transition in plan.transitions:
            execution = rows.get(transition.occurrence_key)
            if execution is None:
                work = works[transition.occurrence_key]
                execution = SurfaceWorkExecution(
                    occurrence_key=work.occurrence_key,
                    work_plan_id=work.work_plan_id,
                    price_item_id=work.price_item_id,
                    status=S.NOT_STARTED,
                )
                self.db.add(execution)
            _apply_transition(execution, transition.from_status, transition.to_status, now)
        await self.db.commit()
        return current, plan
