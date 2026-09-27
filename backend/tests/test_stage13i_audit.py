"""Stage 13I — final Stage 13 adversarial/integration scenarios (verification only).

Cross-stage chains the per-stage suites exercise only piecewise: occurrence
identity + coefficients + waits + execution + Estimate provenance together
(duplicates, reorder, APPEND, REPLACE, apply-to-all, bulk, template edits,
Price Book archive, recommendation append, ready_after), reveal isolation and a
cross-user sweep of the Stage 13 endpoints. No production behaviour changes.
"""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text

from app.domain.exceptions import (
    ExecutionDetachConfirmationRequiredError,
    SurfaceWorkPlanOccurrenceConflictError,
    SurfaceWorkPlanValidationError,
)
from app.domain.services.estimate_service import EstimateService
from app.domain.services.opening_reveal_work_service import OpeningRevealWorkService
from app.domain.services.price_book_service import PriceBookService
from app.domain.services.workflow_template_service import WorkflowTemplateService
from app.domain.services.workflow_template_service import WorkflowTemplateStepSpec as Step
from app.models.checklist import QualityLevel, Substrate
from app.models.estimate import EstimateLine
from app.models.price_item import PriceCategory
from app.models.surface import SurfaceType
from app.models.work_execution import WorkExecutionStatus
from app.models.workflow_template import SurfaceWorkPlanTemplateApplication, TemplateApplicationMode
from app.schemas.work_plan import ApplyTemplateRequest
from app.schemas.work_plan import OrderedPriceItemSelection as Sel
from tests.test_apply_template import _login
from tests.test_planned_work_coefficient_assignments import (
    _make_group_with_options,
    _make_opening,
    _make_price_item,
)
from tests.test_stage13h_bulk_execution import _ctx, _rows, _wall
from tests.test_stage13h_execution_api import OTHER_USER
from tests.test_work_recommendation_accept import _setup_actionable

S = WorkExecutionStatus
NS, IP, C = S.NOT_STARTED, S.IN_PROGRESS, S.COMPLETED


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _save(c, wall, entries, confirm=None):
    return await c.plans.set_plan(c.project, c.room, wall, c.user, substrate=Substrate.CONCRETE,
                                  quality_target=QualityLevel.S2, planned_works=entries,
                                  confirm_execution_detach_keys=confirm)


async def _move(c, wall, key, status, expected=NS):
    return await c.exec.transition(c.project, c.room, wall, c.user, key, status=status, expected_status=expected)


async def _plan_state(c, wall):
    """Per occurrence_key: (price_item, position, wait, coefficient option ids, execution status)."""
    plan = await c.plans.get_work_plan(c.project, c.room, wall, c.user)
    return {w.occurrence_key: (w.price_item_id, w.position, w.wait_after_hours,
                               sorted(str(o.id) for o in w.coefficient_options), w.execution.status)
            for w in plan.planned_works}


async def _lines(db, estimate_id):
    rows = (await db.execute(select(EstimateLine).where(EstimateLine.estimate_id == estimate_id)
                             .execution_options(populate_existing=True))).scalars().all()
    return {r.occurrence_key: r for r in rows if r.occurrence_key is not None}


def _coef_ids(line):
    return sorted(str(o.get("option_id") or o.get("id")) for o in (line.coefficient_snapshot or []))


async def _template(c, steps, **kw):
    return await WorkflowTemplateService(c.db).create_template(
        c.user, display_name=kw.get("name", "Proces audytu"), applies_to_substrates=[Substrate.CONCRETE],
        applies_to_quality=[QualityLevel.S2], applies_to_surface_types=[SurfaceType.WALL], steps=steps)


async def _apply(c, wall, template, mode, keys=None, confirm=None, app_id=None):
    template_id, step_ids = template if isinstance(template, tuple) else (template.id, [s.id for s in template.steps])
    return await c.plans.apply_template(c.project, c.room, wall, c.user, ApplyTemplateRequest(
        application_id=app_id or uuid.uuid4(), template_id=template_id, mode=mode,
        expected_step_ids=step_ids,
        expected_occurrence_keys=keys, replace_confirmed=mode == TemplateApplicationMode.REPLACE,
        confirm_execution_detach_keys=confirm))


async def _setup(client, db):
    c = await _ctx(client, db)
    _, c.opts = await _make_group_with_options(db, c.user, percentages=["0", "15", "30"])
    c.est = EstimateService(db)
    return c


# ---------------------------------------------------------------------------
# A — duplicate identity through reorder, save and Estimate regeneration
# ---------------------------------------------------------------------------


class TestScenarioA:
    async def test_duplicates_keep_their_own_state_through_reorder_and_regeneration(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        w = await _wall(c, "A", 0)
        plan = await _save(c, w, [Sel(price_item_id=c.p1, wait_after_hours=24, coefficient_option_ids=[c.opts[1].id]),
                                  Sel(price_item_id=c.p1, wait_after_hours=4, coefficient_option_ids=[c.opts[2].id]),
                                  Sel(price_item_id=c.p2)])
        a1, a2, b = (x.occurrence_key for x in plan.planned_works)
        await _move(c, w, a1, C)
        await _move(c, w, a2, IP)
        est = await c.est.generate_estimate(c.project, c.user)
        est_id = est.id  # plain id survives rollbacks
        lines = await _lines(db_session, est_id)
        assert set(lines) == {a1, a2, b}
        await c.est.patch_line(c.project, est_id, c.user, lines[a2].id, provided_fields={"unit_price"}, unit_price=Decimal("77.77"))
        before = {k: (l.id, l.price_item_id, _coef_ids(l), l.base_unit_price) for k, l in (await _lines(db_session, est_id)).items()}
        state = await _plan_state(c, w)

        await _save(c, w, [Sel(price_item_id=c.p2, occurrence_key=b),
                           Sel(price_item_id=c.p1, occurrence_key=a2, wait_after_hours=4, coefficient_option_ids=[c.opts[2].id]),
                           Sel(price_item_id=c.p1, occurrence_key=a1, wait_after_hours=24, coefficient_option_ids=[c.opts[1].id])])
        after_state = await _plan_state(c, w)
        assert {k: v[:1] + v[2:] for k, v in after_state.items()} == {k: v[:1] + v[2:] for k, v in state.items()}
        assert [after_state[k][1] for k in (b, a2, a1)] == [0, 1, 2]

        result = await c.est.regenerate_draft(est_id, c.user, c.project)
        assert (result.added, result.removed) == (0, 0)
        after = await _lines(db_session, est_id)
        assert {k: (l.id, l.price_item_id, _coef_ids(l), l.base_unit_price) for k, l in after.items()} == before
        assert after[a2].price_override is True and after[a2].unit_price == Decimal("77.77")
        assert after[a1].price_override is False
        assert _coef_ids(after[a1]) != _coef_ids(after[a2])  # never swapped


# ---------------------------------------------------------------------------
# B — APPEND into a live plan
# ---------------------------------------------------------------------------


class TestScenarioB:
    async def test_append_into_live_plan(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        w = await _wall(c, "A", 0)
        plan = await _save(c, w, [Sel(price_item_id=c.p1, wait_after_hours=6, coefficient_option_ids=[c.opts[1].id]),
                                  Sel(price_item_id=c.p2)])
        a, b = (x.occurrence_key for x in plan.planned_works)
        await _move(c, w, a, IP)
        await _move(c, w, b, C)
        est = await c.est.generate_estimate(c.project, c.user)
        est_id = est.id  # plain id survives rollbacks
        old_lines = {k: (l.id, _coef_ids(l)) for k, l in (await _lines(db_session, est_id)).items()}
        state = await _plan_state(c, w)
        rows_before = await _rows(db_session)
        tpl = await _template(c, [Step(price_item_id=c.p1, wait_after_hours=12), Step(price_item_id=c.p3)])

        plan = await _apply(c, w, tpl, TemplateApplicationMode.APPEND)
        after = await _plan_state(c, w)
        assert {k: after[k] for k in (a, b)} == state
        new = [k for k in after if k not in (a, b)]
        assert len(new) == 2 and [after[k][0] for k in sorted(new, key=lambda k: after[k][1])] == [c.p1, c.p3]
        assert [after[k][4] for k in new] == [NS, NS] and [after[k][3] for k in new] == [[], []]
        assert sorted(after[k][2] for k in new if after[k][0] == c.p1) == [12]
        assert await _rows(db_session) == rows_before  # APPEND creates no execution rows
        assert len(plan.template_applications) == 1

        result = await c.est.regenerate_draft(est_id, c.user, c.project)
        assert (result.added, result.removed) == (2, 0)
        lines = await _lines(db_session, est_id)
        assert {k: (lines[k].id, _coef_ids(lines[k])) for k in (a, b)} == old_lines
        assert set(new) <= set(lines)


# ---------------------------------------------------------------------------
# C — REPLACE a live plan
# ---------------------------------------------------------------------------


class TestScenarioC:
    async def test_replace_live_plan(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        w = await _wall(c, "A", 0)
        plan = await _save(c, w, [Sel(price_item_id=c.p1, coefficient_option_ids=[c.opts[1].id]),
                                  Sel(price_item_id=c.p1, coefficient_option_ids=[c.opts[2].id]), Sel(price_item_id=c.p2)])
        keys = [x.occurrence_key for x in plan.planned_works]
        await _move(c, w, keys[0], C)
        await _move(c, w, keys[1], IP)
        est = await c.est.generate_estimate(c.project, c.user)
        est_id = est.id  # plain id survives rollbacks
        state, rows = await _plan_state(c, w), await _rows(db_session)
        coefs = (await db_session.execute(text("SELECT * FROM surface_planned_work_coefficient_assignments ORDER BY id"))).all()
        t = await _template(c, [Step(price_item_id=c.p1), Step(price_item_id=c.p3)])
        tpl = (t.id, [s.id for s in t.steps])  # plain ids survive the rollback below
        app_id = uuid.uuid4()

        with pytest.raises(ExecutionDetachConfirmationRequiredError) as err:
            await _apply(c, w, tpl, TemplateApplicationMode.REPLACE, keys=keys, app_id=app_id)
        assert sorted(a.occurrence_key for a in err.value.affected) == sorted(keys[:2])
        await db_session.rollback()
        assert await _plan_state(c, w) == state and await _rows(db_session) == rows
        assert (await db_session.execute(text("SELECT * FROM surface_planned_work_coefficient_assignments ORDER BY id"))).all() == coefs
        assert (await db_session.execute(select(SurfaceWorkPlanTemplateApplication))).scalars().all() == []

        plan = await _apply(c, w, tpl, TemplateApplicationMode.REPLACE, keys=keys, confirm=keys[:2], app_id=app_id)
        after = await _plan_state(c, w)
        assert not set(after) & set(keys)
        assert all(v[4] == NS and v[3] == [] for v in after.values())  # no coefficient migrated
        assert await _rows(db_session) == rows  # detached history intact, nothing new
        assert len(plan.template_applications) == 1
        # identical retry: idempotent, still one application
        again = await _apply(c, w, tpl, TemplateApplicationMode.REPLACE, keys=keys, confirm=keys[:2], app_id=app_id)
        assert [x.occurrence_key for x in again.planned_works] == [x.occurrence_key for x in plan.planned_works]
        assert len(again.template_applications) == 1

        result = await c.est.regenerate_draft(est_id, c.user, c.project)
        assert (result.added, result.removed) == (2, 3)  # old keyed lines never inherit new occurrences
        assert set(await _lines(db_session, est_id)) == set(after)


# ---------------------------------------------------------------------------
# D + E — apply-to-all over live targets, then bulk execution
# ---------------------------------------------------------------------------


class TestScenarioDE:
    async def test_apply_to_all_live_targets_then_bulk(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        src, t1, t2 = await _wall(c, "S", 0), await _wall(c, "T1", 1), await _wall(c, "T2", 2)
        sp = await _save(c, src, [Sel(price_item_id=c.p1, wait_after_hours=24, coefficient_option_ids=[c.opts[1].id]),
                                  Sel(price_item_id=c.p1), Sel(price_item_id=c.p2)])
        sk = [x.occurrence_key for x in sp.planned_works]
        t1k = [x.occurrence_key for x in (await _save(c, t1, [Sel(price_item_id=c.p1), Sel(price_item_id=c.p1), Sel(price_item_id=c.p2)])).planned_works]
        await _save(c, t2, [Sel(price_item_id=c.p3)])
        await _move(c, t1, t1k[1], IP)
        await _move(c, t1, t1k[2], C)
        await _move(c, src, sk[0], C)
        states = {w: await _plan_state(c, w) for w in (src, t1, t2)}
        rows = await _rows(db_session)

        with pytest.raises(ExecutionDetachConfirmationRequiredError) as err:
            await c.plans.apply_to_room_walls(c.project, c.room, src, c.user)
        assert sorted(a.occurrence_key for a in err.value.affected) == sorted(t1k[1:])
        await db_session.rollback()
        assert {w: await _plan_state(c, w) for w in (src, t1, t2)} == states and await _rows(db_session) == rows

        await c.plans.apply_to_room_walls(c.project, c.room, src, c.user, confirm_execution_detach_keys=t1k[1:])
        for t in (t1, t2):
            st = await _plan_state(c, t)
            assert not set(st) & (set(sk) | set(t1k))
            assert [v[0] for v in sorted(st.values(), key=lambda v: v[1])] == [c.p1, c.p1, c.p2]
            assert all(v[4] == NS for v in st.values())               # execution never copied
            assert sorted(v[2] for v in st.values() if v[2]) == [24]  # waits copied
            assert sum(bool(v[3]) for v in st.values()) == 1          # coefficient copied with its occurrence
        assert await _plan_state(c, src) == states[src]
        assert await _rows(db_session) == rows  # detached target history kept

        # E — bulk after apply-to-all: matched by PriceItem ordinal, never by key
        await _move(c, src, sk[1], IP)
        from tests.test_stage13h_bulk_execution import _apply as bulk_apply, _preview
        body = (await bulk_apply(c, src, (await _preview(c, src)).json()["expected_source"])).json()
        assert body["changed"] == 4
        for t in (t1, t2):
            st = sorted((await _plan_state(c, t)).values(), key=lambda v: v[1])
            assert [v[4] for v in st] == [C, IP, NS]


# ---------------------------------------------------------------------------
# F — template edits after materialisation
# ---------------------------------------------------------------------------


class TestScenarioF:
    async def test_template_edits_are_never_retroactive(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        w = await _wall(c, "A", 0)
        await _save(c, w, [])
        tpl = await _template(c, [Step(price_item_id=c.p1, wait_after_hours=8), Step(price_item_id=c.p2)], name="Stary")
        await _apply(c, w, tpl, TemplateApplicationMode.APPEND)
        state = await _plan_state(c, w)
        await _move(c, w, next(iter(state)), C)
        state = await _plan_state(c, w)
        est = await c.est.generate_estimate(c.project, c.user)
        est_id = est.id  # plain id survives rollbacks
        lines = {k: (l.id, l.price_item_id, l.unit_price) for k, l in (await _lines(db_session, est_id)).items()}
        history = (await db_session.execute(text("SELECT id, template_id, template_code, template_name, mode, steps_applied FROM surface_work_plan_template_applications"))).all()

        svc = WorkflowTemplateService(db_session)
        await svc.update_template(c.user, tpl.id, display_name="Nowa nazwa")
        fresh = await svc.get_owned_template(c.user, tpl.id)
        await svc.replace_steps(c.user, tpl.id, [Step(price_item_id=c.p3, wait_after_hours=72), Step(price_item_id=c.p1)],
                                expected_step_ids=[s.id for s in fresh.steps])
        await svc.archive_template(c.user, tpl.id)

        assert await _plan_state(c, w) == state
        assert {k: (l.id, l.price_item_id, l.unit_price) for k, l in (await _lines(db_session, est_id)).items()} == lines
        assert (await db_session.execute(text("SELECT id, template_id, template_code, template_name, mode, steps_applied FROM surface_work_plan_template_applications"))).all() == history
        result = await c.est.regenerate_draft(est_id, c.user, c.project)
        assert (result.added, result.removed) == (0, 0)


# ---------------------------------------------------------------------------
# G — Price Book archive of an item used everywhere
# ---------------------------------------------------------------------------


class TestScenarioG:
    async def test_archived_price_item_keeps_every_reference_coherent(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        a, b = await _wall(c, "A", 0), await _wall(c, "B", 1)
        t = await _template(c, [Step(price_item_id=c.p1)])
        tpl = (t.id, [s.id for s in t.steps])
        ka = [x.occurrence_key for x in (await _save(c, a, [Sel(price_item_id=c.p1), Sel(price_item_id=c.p2)])).planned_works]
        kb = [x.occurrence_key for x in (await _save(c, b, [Sel(price_item_id=c.p1)])).planned_works]
        await _move(c, a, ka[0], IP)
        est = await c.est.generate_estimate(c.project, c.user)
        est_id = est.id  # plain id survives rollbacks
        lines = {k: (l.id, l.price_item_id, l.unit_price) for k, l in (await _lines(db_session, est_id)).items()}

        await PriceBookService(db_session).archive_item(c.user, c.p1)
        plan = await c.plans.get_work_plan(c.project, c.room, a, c.user)
        assert [(w.occurrence_key, w.price_item.is_archived) for w in plan.planned_works] == [(ka[0], True), (ka[1], False)]
        # existing occurrences may be kept (count not increased) and still progress
        await _save(c, a, [Sel(price_item_id=c.p2, occurrence_key=ka[1]), Sel(price_item_id=c.p1, occurrence_key=ka[0])])
        assert (await _move(c, a, ka[0], C, IP)).status == C
        with pytest.raises(SurfaceWorkPlanValidationError):
            await _save(c, a, [Sel(price_item_id=c.p2, occurrence_key=ka[1]), Sel(price_item_id=c.p1, occurrence_key=ka[0]),
                               Sel(price_item_id=c.p1)])
        await db_session.rollback()
        with pytest.raises(SurfaceWorkPlanValidationError):  # required archived step blocks application
            await _apply(c, b, tpl, TemplateApplicationMode.APPEND)
        await db_session.rollback()
        assert {k: (l.id, l.price_item_id, l.unit_price) for k, l in (await _lines(db_session, est_id)).items()} == lines
        # bulk still matches by the archived item's identity
        from tests.test_stage13h_bulk_execution import _apply as bulk_apply, _preview
        body = (await bulk_apply(c, a, (await _preview(c, a)).json()["expected_source"])).json()
        assert body["changed"] == 1 and (await _rows(db_session))[kb[0]][0] == C


# ---------------------------------------------------------------------------
# H — recommendation into a live plan; re-evaluation never deletes works
# ---------------------------------------------------------------------------


class TestScenarioH:
    async def test_accept_appends_one_independent_occurrence(self, db_session):
        user, project, room, wall, plan, item, rec, service = await _setup_actionable(
            db_session, 9701, with_plan_codes=["LIVE_A"])
        from app.domain.services.work_execution_service import SurfaceWorkExecutionService
        from app.domain.services.work_plan_service import SurfaceWorkPlanService
        plans, ex = SurfaceWorkPlanService(db_session), SurfaceWorkExecutionService(db_session)
        a_item = plan.planned_works[0].price_item_id
        _, opts = await _make_group_with_options(db_session, user.id, percentages=["0", "15"])
        a1 = plan.planned_works[0].occurrence_key
        plan = await plans.set_plan(project.id, room.id, wall.id, user.id, substrate=Substrate.GYPSUM_PLASTER, planned_works=[
            Sel(price_item_id=a_item, occurrence_key=a1, wait_after_hours=12, coefficient_option_ids=[opts[1].id]),
            Sel(price_item_id=a_item), Sel(price_item_id=item.id)])
        keys = [w.occurrence_key for w in plan.planned_works]
        await ex.transition(project.id, room.id, wall.id, user.id, keys[0], status=C, expected_status=NS)
        before = {w.occurrence_key: (w.price_item_id, w.wait_after_hours, [o.id for o in w.coefficient_options], w.execution.status)
                  for w in (await plans.get_work_plan(project.id, room.id, wall.id, user.id)).planned_works}
        rows = await _rows(db_session)

        await service.accept_recommendation(project.id, rec.id, user.id)
        after = (await plans.get_work_plan(project.id, room.id, wall.id, user.id)).planned_works
        assert {k: v for k, v in ((w.occurrence_key, (w.price_item_id, w.wait_after_hours, [o.id for o in w.coefficient_options],
                w.execution.status)) for w in after) if k in before} == before
        new = [w for w in after if w.occurrence_key not in before]
        assert len(new) == 1 and new[0].price_item_id == item.id and new[0].occurrence_key not in keys
        assert (new[0].wait_after_hours, new[0].coefficient_options, new[0].execution.status) == (None, [], NS)
        assert await _rows(db_session) == rows

        await service.evaluate_recommendations(project.id, room.id, user.id)
        assert [w.occurrence_key for w in (await plans.get_work_plan(project.id, room.id, wall.id, user.id)).planned_works] == \
            [w.occurrence_key for w in after]


# ---------------------------------------------------------------------------
# I — ready_after follows the current wait through reorder
# ---------------------------------------------------------------------------


class TestScenarioI:
    async def test_ready_after_through_wait_edit_and_reorder(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        w = await _wall(c, "A", 0)
        k = [x.occurrence_key for x in (await _save(c, w, [Sel(price_item_id=c.p1, wait_after_hours=4), Sel(price_item_id=c.p2)])).planned_works]
        done = await _move(c, w, k[0], C)
        stamp = (await _rows(db_session))[k[0]]
        view = lambda plan: next(x.execution for x in plan.planned_works if x.occurrence_key == k[0])  # noqa: E731
        first = view(await c.plans.get_work_plan(c.project, c.room, w, c.user))
        assert first.ready_after - first.completed_at == timedelta(hours=4) and done.status == C
        plan = await _save(c, w, [Sel(price_item_id=c.p2, occurrence_key=k[1]), Sel(price_item_id=c.p1, occurrence_key=k[0], wait_after_hours=36)])
        e = view(plan)
        assert e.ready_after - e.completed_at == timedelta(hours=36)
        assert (await _rows(db_session))[k[0]] == stamp  # completion timestamp untouched
        plan = await _save(c, w, [Sel(price_item_id=c.p1, occurrence_key=k[0]), Sel(price_item_id=c.p2, occurrence_key=k[1])])
        assert view(plan).ready_after is None  # break cleared -> no readiness


# ---------------------------------------------------------------------------
# J — bulk with a stale source (duplicate count change) and destination changes
# ---------------------------------------------------------------------------


class TestScenarioJ:
    async def test_source_duplicate_count_change_and_destination_duplicate_change(self, async_client: AsyncClient, db_session):
        from tests.test_stage13h_bulk_execution import _apply as bulk_apply, _preview
        c = await _setup(async_client, db_session)
        a, b = await _wall(c, "A", 0), await _wall(c, "B", 1)
        ka = [x.occurrence_key for x in (await _save(c, a, [Sel(price_item_id=c.p1), Sel(price_item_id=c.p2)])).planned_works]
        kb = [x.occurrence_key for x in (await _save(c, b, [Sel(price_item_id=c.p1), Sel(price_item_id=c.p2)])).planned_works]
        await _move(c, a, ka[0], C)
        await _move(c, a, ka[1], C)
        snap = (await _preview(c, a)).json()["expected_source"]
        # source gains a duplicate of p1 -> source changed, nothing written
        await _save(c, a, [Sel(price_item_id=c.p1, occurrence_key=ka[0]), Sel(price_item_id=c.p1), Sel(price_item_id=c.p2, occurrence_key=ka[1])])
        rows = await _rows(db_session)
        res = await bulk_apply(c, a, snap)
        assert res.status_code == 409 and res.json()["detail"]["code"] == "WORK_EXECUTION_SOURCE_CHANGED"
        assert await _rows(db_session) == rows
        # fresh preview, then the DESTINATION gains a duplicate of p1: recomputed as ambiguous under the lock
        snap = (await _preview(c, a)).json()["expected_source"]
        assert (await _preview(c, a)).json()["ambiguous"] == 2
        await _save(c, b, [Sel(price_item_id=c.p1, occurrence_key=kb[0]), Sel(price_item_id=c.p1), Sel(price_item_id=c.p2, occurrence_key=kb[1])])
        body = (await bulk_apply(c, a, snap)).json()
        # p1 now 2 = 2 -> matched by ordinal (1st advances to C, 2nd stays: source NOT_STARTED); p2 advances
        assert (body["changed"], body["unchanged"], body["ambiguous"]) == (2, 1, 0)
        rows = await _rows(db_session)
        assert rows[kb[0]][0] == C and rows[kb[1]][0] == C


# ---------------------------------------------------------------------------
# Reveal isolation + cross-user sweep of Stage 13 endpoints
# ---------------------------------------------------------------------------


class TestRevealIsolation:
    async def test_reveal_works_have_no_occurrence_identity_or_execution(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        w = await _wall(c, "A", 0)
        await _save(c, w, [Sel(price_item_id=c.p1)])
        opening = await _make_opening(db_session, w)
        reveal_item = await _make_price_item(db_session, c.user, category=PriceCategory.REVEAL)
        works = await OpeningRevealWorkService(db_session).set_works(opening.id, c.user, [reveal_item.id],
                                                                     project_id=c.project, room_id=c.room, surface_id=w)
        assert not hasattr(works[0], "occurrence_key")
        est = await c.est.generate_estimate(c.project, c.user)
        est_id = est.id  # plain id survives rollbacks
        reveal_lines = (await db_session.execute(select(EstimateLine).where(EstimateLine.estimate_id == est.id,
                                                                            EstimateLine.opening_id.is_not(None)))).scalars().all()
        assert reveal_lines and all(l.occurrence_key is None for l in reveal_lines)
        with pytest.raises(SurfaceWorkPlanOccurrenceConflictError):
            await _move(c, w, works[0].id, IP)
        assert await _rows(db_session) == {}


class TestCrossUserSweep:
    async def test_stage13_endpoints_never_cross_owners(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        a, b = await _wall(c, "A", 0), await _wall(c, "B", 1)
        ka = [x.occurrence_key for x in (await _save(c, a, [Sel(price_item_id=c.p1)])).planned_works]
        await _save(c, b, [Sel(price_item_id=c.p1)])
        tpl = await _template(c, [Step(price_item_id=c.p1)])
        await _move(c, a, ka[0], C)
        headers, _ = await _login(async_client, db_session, OTHER_USER)
        base = f"/api/projects/{c.project}/rooms/{c.room}/surfaces/{a}/work-plan"
        body = {"application_id": str(uuid.uuid4()), "template_id": str(tpl.id), "mode": "APPEND",
                "selected_optional_step_ids": [], "expected_step_ids": [str(s.id) for s in tpl.steps]}
        calls = [
            ("get", base, None), ("put", base, {"substrate": "CONCRETE", "planned_works": []}),
            ("patch", f"{base}/occurrences/{ka[0]}/execution", {"status": "IN_PROGRESS", "expected_status": "COMPLETED"}),
            ("post", f"{base}/apply-template", body), ("post", f"{base}/apply-to-room-walls", None),
            ("post", f"{base}/execution/apply-to-room-walls-preview", None),
            ("post", f"{base}/execution/apply-to-room-walls", {"expected_source": []}),
            ("get", f"/api/workflow-templates/{tpl.id}", None),
            ("patch", f"/api/workflow-templates/{tpl.id}", {"display_name": "X"}),
        ]
        rows = await _rows(db_session)
        for method, url, payload in calls:
            kwargs = {"headers": headers} | ({"json": payload} if payload is not None else {})
            res = await getattr(async_client, method)(url, **kwargs)
            assert res.status_code == 404, (method, url, res.status_code, res.text)
            assert str(ka[0]) not in res.text and "COMPLETED" not in res.text
        # the stranger's own template cannot reference the owner's PriceItem
        res = await async_client.post("/api/workflow-templates", headers=headers, json={
            "display_name": "Obcy", "steps": [{"price_item_id": str(c.p1)}]})
        assert res.status_code == 404
        assert await _rows(db_session) == rows
