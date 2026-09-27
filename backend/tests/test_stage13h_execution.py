"""Stage 13H.2 — execution state of surface planned-work occurrences.

Domain/persistence only (no API yet): lazy NOT_STARTED, the approved
transitions and shortcut, idempotency and stale/invalid conflicts, identity
by occurrence_key across WorkPlan row replacement, detached history on
removal, derived ready_after, isolation from coefficients and the Estimate,
non-leaking key checks, archive refusal, and the DB constraints.
"""
import uuid
from datetime import datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.domain.exceptions import (
    SurfaceWorkPlanOccurrenceConflictError,
    WorkExecutionConflictError,
    WorkExecutionValidationError,
)
from app.domain.services.estimate_service import EstimateService
from app.domain.services.work_execution_service import (
    SurfaceWorkExecutionService,
    derive_ready_after,
)
from app.models.checklist import QualityLevel, Substrate
from app.models.project import Project
from app.models.room import Room
from app.models.surface import Surface
from app.models.work_execution import SurfaceWorkExecution, WorkExecutionStatus
from app.models.workflow_template import TemplateApplicationMode
from app.schemas.work_plan import ApplyTemplateRequest, OrderedPriceItemSelection
from tests.test_apply_template import _estimate_snapshot
from tests.test_apply_template import _setup as _setup_priced
from tests.test_occurrence_key import _save, _setup
from tests.test_planned_work_coefficient_assignments import _make_surface
from tests.test_stage13g_waits import _priced

S = WorkExecutionStatus
Sel = OrderedPriceItemSelection


class Ctx:
    pass


async def _ctx(db, telegram_id: int = 9101, works=None) -> Ctx:
    c = Ctx()
    c.user, c.project, c.room, c.surface, c.a, c.b, c.plans = await _setup(db, telegram_id)
    c.db = db
    c.exec = SurfaceWorkExecutionService(db)
    works = works if works is not None else [Sel(price_item_id=c.a.id), Sel(price_item_id=c.a.id), Sel(price_item_id=c.b.id)]
    c.plan = await _save(c.plans, c.user, c.project, c.room, c.surface, works)
    c.keys = [w.occurrence_key for w in c.plan.planned_works]
    # plain ids survive a rollback (expired ORM objects cannot lazy-load in async)
    c.ids = (c.project.id, c.room.id, c.surface.id, c.user.id)
    return c


async def _move(c: Ctx, key, status, expected, surface=None):
    project_id, room_id, surface_id, user_id = c.ids
    return await c.exec.transition(
        project_id, room_id, surface.id if surface is not None else surface_id, user_id, key,
        status=status, expected_status=expected,
    )


async def _views(c: Ctx, surface=None):
    project_id, room_id, surface_id, user_id = c.ids
    return await c.exec.get_plan_executions(
        project_id, room_id, surface.id if surface is not None else surface_id, user_id
    )


async def _row(db, key) -> SurfaceWorkExecution | None:
    return (
        await db.execute(
            select(SurfaceWorkExecution)
            .where(SurfaceWorkExecution.occurrence_key == key)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()


async def _count(db) -> int:
    return len((await db.execute(select(SurfaceWorkExecution))).scalars().all())


def _resave(c: Ctx, keys_items_waits, *, confirm=None, **kw):
    project_id, room_id, surface_id, user_id = c.ids
    return c.plans.set_plan(
        project_id, room_id, surface_id, user_id,
        substrate=kw.get("substrate", Substrate.GYPSUM_PLASTER),
        quality_target=kw.get("quality_target"),
        planned_works=[Sel(price_item_id=item, occurrence_key=key, wait_after_hours=wait)
                       for key, item, wait in keys_items_waits],
        confirm_execution_detach_keys=confirm,
    )


# ---------------------------------------------------------------------------
# Lazy NOT_STARTED / legacy plans
# ---------------------------------------------------------------------------


class TestLazyNotStarted:
    async def test_no_row_means_not_started(self, db_session):
        c = await _ctx(db_session)
        views = await _views(c)
        assert [(v.occurrence_key, v.status, v.started_at, v.completed_at, v.ready_after) for v in views] == [
            (k, S.NOT_STARTED, None, None, None) for k in c.keys
        ]
        assert await _count(db_session) == 0  # reading never creates rows

    async def test_unplanned_surface_has_no_executions(self, db_session):
        c = await _ctx(db_session)
        other = await _make_surface(db_session, c.room.id, name="Bez planu")
        assert await _views(c, other) == []


# ---------------------------------------------------------------------------
# Transitions
# ---------------------------------------------------------------------------


class TestTransitions:
    async def test_start_then_complete(self, db_session):
        c = await _ctx(db_session)
        k = c.keys[0]
        started = await _move(c, k, S.IN_PROGRESS, S.NOT_STARTED)
        assert started.status == S.IN_PROGRESS and started.started_at is not None and started.completed_at is None
        row = await _row(db_session, k)
        assert (row.status, row.work_plan_id, row.price_item_id) == (S.IN_PROGRESS, c.plan.id, c.a.id)

        done = await _move(c, k, S.COMPLETED, S.IN_PROGRESS)
        row = await _row(db_session, k)
        assert done.status == S.COMPLETED and row.status == S.COMPLETED
        assert row.started_at is not None and row.completed_at is not None
        assert row.completed_at >= row.started_at

    async def test_direct_complete_shortcut_sets_both_timestamps(self, db_session):
        c = await _ctx(db_session)
        done = await _move(c, c.keys[0], S.COMPLETED, S.NOT_STARTED)
        row = await _row(db_session, c.keys[0])
        assert done.status == S.COMPLETED
        assert row.started_at is not None and row.started_at == row.completed_at

    async def test_reopen_keeps_started_at_and_clears_completed_at(self, db_session):
        c = await _ctx(db_session)
        k = c.keys[0]
        await _move(c, k, S.IN_PROGRESS, S.NOT_STARTED)
        started_at = (await _row(db_session, k)).started_at
        await _move(c, k, S.COMPLETED, S.IN_PROGRESS)
        reopened = await _move(c, k, S.IN_PROGRESS, S.COMPLETED)
        row = await _row(db_session, k)
        assert reopened.status == S.IN_PROGRESS
        assert (row.status, row.started_at, row.completed_at) == (S.IN_PROGRESS, started_at, None)

    async def test_reset_clears_started_at_and_keeps_row(self, db_session):
        c = await _ctx(db_session)
        k = c.keys[0]
        await _move(c, k, S.IN_PROGRESS, S.NOT_STARTED)
        reset = await _move(c, k, S.NOT_STARTED, S.IN_PROGRESS)
        row = await _row(db_session, k)
        assert reset.status == S.NOT_STARTED
        assert (row.status, row.started_at, row.completed_at) == (S.NOT_STARTED, None, None)
        # and it can be started again
        assert (await _move(c, k, S.IN_PROGRESS, S.NOT_STARTED)).status == S.IN_PROGRESS

    async def test_completed_cannot_reset_directly(self, db_session):
        c = await _ctx(db_session)
        k = c.keys[0]
        await _move(c, k, S.COMPLETED, S.NOT_STARTED)
        before = await _row(db_session, k)
        snapshot = (before.status, before.started_at, before.completed_at)
        with pytest.raises(WorkExecutionConflictError) as err:
            await _move(c, k, S.NOT_STARTED, S.COMPLETED)
        assert err.value.current_status == S.COMPLETED
        await db_session.rollback()
        after = await _row(db_session, k)
        assert (after.status, after.started_at, after.completed_at) == snapshot

    async def test_stale_expected_status_conflicts_without_change(self, db_session):
        c = await _ctx(db_session)
        k = c.keys[0]
        await _move(c, k, S.COMPLETED, S.NOT_STARTED)  # session A completed it
        snap = await _row(db_session, k)
        snapshot = (snap.status, snap.started_at, snap.completed_at)
        # session B still sees NOT_STARTED and tries to start it
        with pytest.raises(WorkExecutionConflictError):
            await _move(c, k, S.IN_PROGRESS, S.NOT_STARTED)
        await db_session.rollback()
        # stale COMPLETE after a reopen: B saw NOT_STARTED
        await _move(c, k, S.IN_PROGRESS, S.COMPLETED)
        with pytest.raises(WorkExecutionConflictError):
            await _move(c, k, S.COMPLETED, S.NOT_STARTED)
        await db_session.rollback()
        row = await _row(db_session, k)
        assert (row.status, row.started_at, row.completed_at) == (S.IN_PROGRESS, snapshot[1], None)

    async def test_same_state_request_is_idempotent(self, db_session):
        c = await _ctx(db_session)
        k = c.keys[0]
        # NOT_STARTED -> NOT_STARTED creates nothing
        assert (await _move(c, k, S.NOT_STARTED, S.NOT_STARTED)).status == S.NOT_STARTED
        assert await _row(db_session, k) is None

        await _move(c, k, S.IN_PROGRESS, S.NOT_STARTED)
        first = await _row(db_session, k)
        stamps = (first.started_at, first.completed_at, first.updated_at)
        # repeated START (same or stale expectation) changes nothing
        for expected in (S.NOT_STARTED, S.IN_PROGRESS):
            again = await _move(c, k, S.IN_PROGRESS, expected)
            assert again.status == S.IN_PROGRESS
            row = await _row(db_session, k)
            assert (row.started_at, row.completed_at, row.updated_at) == stamps

        await _move(c, k, S.COMPLETED, S.IN_PROGRESS)
        done = await _row(db_session, k)
        stamps = (done.started_at, done.completed_at, done.updated_at)
        assert (await _move(c, k, S.COMPLETED, S.IN_PROGRESS)).status == S.COMPLETED
        row = await _row(db_session, k)
        assert (row.started_at, row.completed_at, row.updated_at) == stamps

    async def test_duplicate_price_items_are_independent(self, db_session):
        c = await _ctx(db_session)  # keys[0] and keys[1] are both PriceItem A
        await _move(c, c.keys[1], S.COMPLETED, S.NOT_STARTED)
        views = await _views(c)
        assert [v.status for v in views] == [S.NOT_STARTED, S.COMPLETED, S.NOT_STARTED]


# ---------------------------------------------------------------------------
# Identity across WorkPlan edits
# ---------------------------------------------------------------------------


class TestIdentity:
    async def test_execution_survives_row_replacement(self, db_session):
        c = await _ctx(db_session)
        k0, k1, k2 = c.keys
        await _move(c, k0, S.COMPLETED, S.NOT_STARTED)
        await _move(c, k2, S.IN_PROGRESS, S.NOT_STARTED)
        before = {k: (r.status, r.started_at, r.completed_at, r.id) for k in (k0, k2) if (r := await _row(db_session, k))}
        old_row_ids = [w.id for w in c.plan.planned_works]

        # reorder, change waits, substrate and quality target, and add a work
        plan = await _resave(
            c, [(k2, c.b.id, 12), (None, c.b.id, None), (k1, c.a.id, None), (k0, c.a.id, 24)],
            substrate=Substrate.CONCRETE, quality_target=QualityLevel.S3,
        )
        assert not set(old_row_ids) & {w.id for w in plan.planned_works}  # rows recreated
        after = {k: (r.status, r.started_at, r.completed_at, r.id) for k in (k0, k2) if (r := await _row(db_session, k))}
        assert after == before
        views = await _views(c)
        assert [v.status for v in views] == [S.IN_PROGRESS, S.NOT_STARTED, S.NOT_STARTED, S.COMPLETED]
        assert [views[0].occurrence_key, views[2].occurrence_key, views[3].occurrence_key] == [k2, k1, k0]
        assert views[1].occurrence_key not in c.keys  # the new work

    async def test_removed_occurrence_keeps_detached_history(self, db_session):
        c = await _ctx(db_session)
        k0, k1, k2 = c.keys
        await _move(c, k0, S.COMPLETED, S.NOT_STARTED)
        await _resave(c, [(k1, c.a.id, None), (k2, c.b.id, None)], confirm=[k0])  # k0 removed (13H.4 confirmed)
        row = await _row(db_session, k0)
        assert row is not None and row.status == S.COMPLETED and row.price_item_id == c.a.id
        assert [v.occurrence_key for v in await _views(c)] == [k1, k2]  # detached not listed
        with pytest.raises(SurfaceWorkPlanOccurrenceConflictError):
            await _move(c, k0, S.IN_PROGRESS, S.COMPLETED)  # detached is read-only history

    async def test_readded_same_price_item_does_not_inherit(self, db_session):
        c = await _ctx(db_session)
        k0, k1, k2 = c.keys
        await _move(c, k0, S.COMPLETED, S.NOT_STARTED)
        await _resave(c, [(k1, c.a.id, None), (k2, c.b.id, None)], confirm=[k0])
        plan = await _resave(c, [(k1, c.a.id, None), (k2, c.b.id, None), (None, c.a.id, None)])
        new_key = plan.planned_works[2].occurrence_key
        assert new_key not in c.keys
        assert (await _views(c))[2].status == S.NOT_STARTED
        assert await _row(db_session, new_key) is None
        assert (await _row(db_session, k0)).status == S.COMPLETED

    async def test_apply_to_all_never_copies_execution(self, db_session):
        c = await _ctx(db_session)
        wall_b = await _make_surface(db_session, c.room.id, name="Ściana B")
        await _move(c, c.keys[0], S.COMPLETED, S.NOT_STARTED)
        await c.plans.apply_to_room_walls(c.project.id, c.room.id, c.surface.id, c.user.id)
        views_b = await _views(c, wall_b)
        assert len(views_b) == 3 and {v.status for v in views_b} == {S.NOT_STARTED}
        assert not {v.occurrence_key for v in views_b} & set(c.keys)
        assert (await _views(c))[0].status == S.COMPLETED


class TestAppend:
    async def test_append_keeps_state_and_new_works_start_not_started(self, async_client: AsyncClient, db_session):
        p = await _setup_priced(async_client, db_session)  # one existing occurrence (item X)
        svc = SurfaceWorkExecutionService(db_session)
        key = p.plan.planned_works[0].occurrence_key
        await svc.transition(p.project.id, p.room.id, p.surface.id, p.user.id, key,
                             status=S.COMPLETED, expected_status=S.NOT_STARTED)
        await p.plans.apply_template(
            p.project.id, p.room.id, p.surface.id, p.user.id,
            ApplyTemplateRequest(application_id=uuid.uuid4(), template_id=p.template.id,
                                 mode=TemplateApplicationMode.APPEND, expected_step_ids=p.step_ids),
        )
        views = await svc.get_plan_executions(p.project.id, p.room.id, p.surface.id, p.user.id)
        assert views[0].occurrence_key == key and views[0].status == S.COMPLETED
        assert len(views) > 1 and {v.status for v in views[1:]} == {S.NOT_STARTED}


# ---------------------------------------------------------------------------
# ready_after (derived, never stored)
# ---------------------------------------------------------------------------


class TestReadyAfter:
    def test_derivation(self):
        t = datetime(2026, 9, 27, 10, 0)
        assert derive_ready_after(S.COMPLETED, t, 4) == datetime(2026, 9, 27, 14, 0)
        assert derive_ready_after(S.COMPLETED, t, None) is None
        assert derive_ready_after(S.IN_PROGRESS, None, 4) is None
        assert derive_ready_after(S.NOT_STARTED, None, 4) is None

    async def test_ready_after_follows_current_wait(self, db_session):
        c = await _ctx(db_session)
        k0, k1, k2 = c.keys
        await _resave(c, [(k0, c.a.id, 4), (k1, c.a.id, None), (k2, c.b.id, 8)])
        await _move(c, k0, S.COMPLETED, S.NOT_STARTED)
        await _move(c, k1, S.COMPLETED, S.NOT_STARTED)
        await _move(c, k2, S.IN_PROGRESS, S.NOT_STARTED)
        row = await _row(db_session, k0)
        stamps = (row.started_at, row.completed_at, row.updated_at)
        views = await _views(c)
        assert views[0].ready_after == views[0].completed_at + timedelta(hours=4)
        assert views[1].ready_after is None  # completed, no break
        assert views[2].ready_after is None  # break, not completed

        await _resave(c, [(k0, c.a.id, 48), (k1, c.a.id, None), (k2, c.b.id, 8)])
        views = await _views(c)
        assert views[0].ready_after == views[0].completed_at + timedelta(hours=48)
        row = await _row(db_session, k0)
        assert (row.started_at, row.completed_at, row.updated_at) == stamps  # execution untouched


# ---------------------------------------------------------------------------
# Commercial isolation
# ---------------------------------------------------------------------------


class TestCommercialIsolation:
    async def test_transitions_leave_coefficients_and_estimate_untouched(self, async_client: AsyncClient, db_session):
        p = await _setup_priced(async_client, db_session)  # item X, wait 6 h, coefficient opts[1]
        svc = SurfaceWorkExecutionService(db_session)
        key = p.plan.planned_works[0].occurrence_key
        estimates = EstimateService(db_session)
        estimate = await estimates.generate_estimate(p.project.id, p.user.id)
        lines = await _estimate_snapshot(db_session)
        priced = await _priced(db_session)

        for status, expected in ((S.IN_PROGRESS, S.NOT_STARTED), (S.COMPLETED, S.IN_PROGRESS),
                                 (S.IN_PROGRESS, S.COMPLETED), (S.COMPLETED, S.IN_PROGRESS)):
            await svc.transition(p.project.id, p.room.id, p.surface.id, p.user.id, key,
                                 status=status, expected_status=expected)
            assert await _estimate_snapshot(db_session) == lines

        plan = await p.plans.get_work_plan(p.project.id, p.room.id, p.surface.id, p.user.id)
        work = plan.planned_works[0]
        assert (work.occurrence_key, work.wait_after_hours, [o.id for o in work.coefficient_options]) == (
            key, 6, [p.opts[1].id]
        )
        preview = await estimates.regenerate_draft(estimate.id, p.user.id, p.project.id)
        assert (preview.added, preview.removed) == (0, 0)
        assert await _priced(db_session) == priced
        assert (await _row(db_session, key)).status == S.COMPLETED  # regeneration never resets it


# ---------------------------------------------------------------------------
# Ownership / non-leaking keys / archive
# ---------------------------------------------------------------------------


class TestKeysAndArchive:
    async def test_non_current_keys_are_indistinguishable(self, db_session):
        c = await _ctx(db_session, 9201)
        other_wall = await _make_surface(db_session, c.room.id, name="Ściana 2")
        other_plan = await _save(c.plans, c.user, c.project, c.room, other_wall, [Sel(price_item_id=c.a.id)])
        stranger = await _ctx(db_session, 9202)
        removed = c.keys[2]
        await _resave(c, [(c.keys[0], c.a.id, None), (c.keys[1], c.a.id, None)])
        unplanned = await _make_surface(db_session, c.room.id, name="Bez planu")

        cases = [
            (uuid.uuid4(), c.surface),                           # invented
            (removed, c.surface),                                # stale removed
            (other_plan.planned_works[0].occurrence_key, c.surface),  # another surface
            (stranger.keys[0], c.surface),                       # another user's project
            (c.keys[0], unplanned),                              # surface without a plan
        ]
        messages = set()
        for key, surface in cases:
            with pytest.raises(SurfaceWorkPlanOccurrenceConflictError) as err:
                await _move(c, key, S.IN_PROGRESS, S.NOT_STARTED, surface)
            messages.add(str(err.value).replace(str(key), "<key>"))
        assert len(messages) == 1
        assert await _count(db_session) == 0

    @pytest.mark.parametrize("target", ["surface", "room", "project"])
    async def test_archived_parent_refuses_mutation_but_reads(self, db_session, target):
        c = await _ctx(db_session, 9300)
        await _move(c, c.keys[0], S.IN_PROGRESS, S.NOT_STARTED)
        model, idx = {"surface": (Surface, 2), "room": (Room, 1), "project": (Project, 0)}[target]
        await db_session.execute(update(model).where(model.id == c.ids[idx]).values(is_archived=True))
        await db_session.commit()
        with pytest.raises(WorkExecutionValidationError):
            await _move(c, c.keys[0], S.COMPLETED, S.IN_PROGRESS)
        await db_session.rollback()
        assert (await _views(c))[0].status == S.IN_PROGRESS
        # restore exposes the state unchanged
        await db_session.execute(update(model).where(model.id == c.ids[idx]).values(is_archived=False))
        await db_session.commit()
        assert (await _views(c))[0].status == S.IN_PROGRESS
        assert (await _move(c, c.keys[0], S.COMPLETED, S.IN_PROGRESS)).status == S.COMPLETED


# ---------------------------------------------------------------------------
# DB constraints
# ---------------------------------------------------------------------------


class TestConstraints:
    async def _insert(self, c, **kw):
        row = SurfaceWorkExecution(work_plan_id=c.plan.id, price_item_id=c.a.id,
                                   occurrence_key=kw.pop("occurrence_key", uuid.uuid4()), **kw)
        c.db.add(row)
        await c.db.commit()

    async def test_occurrence_key_unique(self, db_session):
        c = await _ctx(db_session)
        key = uuid.uuid4()
        await self._insert(c, occurrence_key=key, status=S.NOT_STARTED)
        with pytest.raises(IntegrityError):
            await self._insert(c, occurrence_key=key, status=S.NOT_STARTED)

    @pytest.mark.parametrize("status,started,completed", [
        (S.NOT_STARTED, True, False),
        (S.NOT_STARTED, False, True),
        (S.IN_PROGRESS, False, False),
        (S.IN_PROGRESS, True, True),
        (S.COMPLETED, False, True),   # never COMPLETED without started_at
        (S.COMPLETED, True, False),
    ])
    async def test_status_timestamp_consistency(self, db_session, status, started, completed):
        c = await _ctx(db_session)
        now = datetime(2026, 9, 27, 10, 0)
        with pytest.raises(IntegrityError):
            await self._insert(c, status=status, started_at=now if started else None,
                               completed_at=now if completed else None)

    async def test_completed_not_before_started(self, db_session):
        c = await _ctx(db_session)
        t = datetime(2026, 9, 27, 10, 0)
        with pytest.raises(IntegrityError):
            await self._insert(c, status=S.COMPLETED, started_at=t, completed_at=t - timedelta(hours=1))

    async def test_valid_rows_accepted(self, db_session):
        c = await _ctx(db_session)
        t = datetime(2026, 9, 27, 10, 0)
        await self._insert(c, status=S.NOT_STARTED)
        await self._insert(c, status=S.IN_PROGRESS, started_at=t)
        await self._insert(c, status=S.COMPLETED, started_at=t, completed_at=t)
        assert await _count(db_session) == 3
