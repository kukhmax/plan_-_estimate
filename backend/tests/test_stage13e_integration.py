"""Stage 13E.5A — cross-boundary integration / adversarial verification.

Only the end-to-end gaps not already covered by the 13B/13C/13D/13E.2B/13E.3
suites: template application -> WorkPlan identity -> Estimate preview and
regeneration, with same-PriceItem collisions, ordinary saves after apply,
stale conflicts vs the Estimate, legacy lines vs a REAL REPLACE, and reveal
isolation.
"""
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import func, select

from app.domain.services.estimate_service import EstimateService
from app.domain.services.opening_reveal_work_service import OpeningRevealWorkService
from app.domain.services.workflow_template_service import WorkflowTemplateStepSpec
from app.models.checklist import QualityLevel, Substrate
from app.models.estimate import EstimateLine
from app.models.opening_reveal_planned_work import OpeningRevealPlannedWork
from app.models.price_item import PriceCategory, PriceUnit
from app.models.work_plan import SurfacePlannedWorkCoefficientAssignment
from app.models.workflow_template import SurfaceWorkPlanTemplateApplication
from app.schemas.work_plan import OrderedPriceItemSelection as Sel
from tests.test_apply_template import _body, _estimate_snapshot, _rows, _setup
from tests.test_estimates import _make_opening, _make_price_item
from tests.test_planned_work_coefficient_assignments import _make_group_with_options

NET = Decimal("13.500")  # 5.000 x 2.700 test wall


async def _override(svc, c, estimate, line_id, price, qty):
    await svc.patch_line(
        c.project.id, estimate.id, c.user.id, line_id,
        provided_fields={"unit_price", "quantity"}, unit_price=Decimal(price), quantity=Decimal(qty),
    )


async def _lines(db, estimate_id):
    rows = await db.execute(
        select(EstimateLine).where(EstimateLine.estimate_id == estimate_id)
        .order_by(EstimateLine.position).execution_options(populate_existing=True)
    )
    return list(rows.scalars().all())


async def _prov(db):
    return (await db.execute(select(func.count()).select_from(SurfaceWorkPlanTemplateApplication))).scalar_one()


class TestAdversarialAppend:
    async def test_append_same_price_item_never_inherits_and_ordinary_save_keeps_identity(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session, existing=False)
        # A = P1 (+15 %, 24 h), B = P2 (no coefficient, no wait)
        await c.plans.set_plan(c.project.id, c.room.id, c.surface.id, c.user.id, substrate=Substrate.CONCRETE,
                               quality_target=QualityLevel.S2, planned_works=[
                                   Sel(price_item_id=c.p1.id, wait_after_hours=24, coefficient_option_ids=[c.opts[1].id]),
                                   Sel(price_item_id=c.p2.id)])
        a, b = await _rows(db_session, c.plan.id)
        a_state = (a.id, a.occurrence_key, a.wait_after_hours)
        b_state = (b.id, b.occurrence_key, b.wait_after_hours)
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(c.project.id, c.user.id)
        line_a = next(ln for ln in estimate.lines if ln.occurrence_key == a.occurrence_key)
        line_a_id = line_a.id
        await _override(svc, c, estimate, line_a_id, "30.00", "9.000")
        before_estimate = await _estimate_snapshot(db_session)

        # template: P1 (req, 24 h), P2 (opt), P1 (req), P3 (opt, 48 h) -- select P3
        resp = await async_client.post(c.url, headers=c.headers, json=_body(c, selected=[c.step_ids[3]]))
        assert resp.status_code == 200, resp.text
        rows = await _rows(db_session, c.plan.id)
        assert (rows[0].id, rows[0].occurrence_key, rows[0].wait_after_hours) == a_state
        assert (rows[1].id, rows[1].occurrence_key, rows[1].wait_after_hours) == b_state
        new = rows[2:]
        assert [(w.price_item_id, w.wait_after_hours) for w in new] == [(c.p1.id, 24), (c.p1.id, None), (c.p3.id, 48)]
        assert len({w.occurrence_key for w in rows}) == 5
        coef = (await db_session.execute(select(SurfacePlannedWorkCoefficientAssignment.surface_planned_work_id))).scalars().all()
        assert coef == [a.id]  # only A keeps its +15 %; new rows have none
        assert await _prov(db_session) == 1
        assert await _estimate_snapshot(db_session) == before_estimate

        preview = await svc.preview_regeneration(c.project.id, estimate.id, c.user.id)
        assert (preview.added, preview.removed) == (3, 0)
        added_pwids = {ch.planned_work_id for ch in preview.changes if ch.change_type == "ADDED"}
        assert added_pwids == {w.id for w in new}
        await svc.regenerate_draft(estimate.id, c.user.id, c.project.id)
        lines = {ln.occurrence_key: ln for ln in await _lines(db_session, estimate.id)}
        kept = lines[a.occurrence_key]
        assert (kept.id, kept.unit_price, kept.quantity, kept.price_override, kept.quantity_overridden) == (
            line_a_id, Decimal("30.00"), Decimal("9.000"), True, True,
        )
        for w in new[:2]:  # the appended P1 occurrences get normal pricing, no inherited override
            ln = lines[w.occurrence_key]
            assert (ln.unit_price, ln.quantity, ln.price_override, ln.quantity_overridden) == (Decimal("10.00"), NET, False, False)
        line_ids_after_regen = {k: ln.id for k, ln in lines.items()}

        # Ordinary save after apply (frontend contract): echo keys/waits/coefficients,
        # and assign a coefficient to the first appended P1.
        base = c.url.removesuffix("/apply-template")
        current = (await async_client.get(base, headers=c.headers)).json()["planned_works"]
        payload = []
        for i, w in enumerate(current):
            coefs = [o["id"] for o in w["coefficient_options"]]
            if i == 2:
                coefs = [str(c.opts[1].id)]
            payload.append({"price_item_id": w["price_item_id"], "occurrence_key": w["occurrence_key"],
                            "wait_after_hours": w["wait_after_hours"], "coefficient_option_ids": coefs})
        put = await async_client.put(base, headers=c.headers, json={"substrate": "CONCRETE", "quality_target": "S2", "planned_works": payload})
        assert put.status_code == 200, put.text
        saved = put.json()["planned_works"]
        assert [w["occurrence_key"] for w in saved] == [w["occurrence_key"] for w in current]
        assert [w["wait_after_hours"] for w in saved] == [24, None, 24, None, 48]
        assert {w["id"] for w in saved}.isdisjoint({w["id"] for w in current})  # rows recreated

        result = await svc.regenerate_draft(estimate.id, c.user.id, c.project.id)
        assert (result.added, result.removed) == (0, 0)
        lines = {ln.occurrence_key: ln for ln in await _lines(db_session, estimate.id)}
        assert {k: ln.id for k, ln in lines.items()} == line_ids_after_regen  # identity stable
        assert lines[a.occurrence_key].unit_price == Decimal("30.00")
        first_new = lines[new[0].occurrence_key]
        assert first_new.unit_price == Decimal("11.50")  # 10.00 + 15 %
        assert [e["percentage"] for e in first_new.coefficient_snapshot] == ["15.000"]


class TestAdversarialReplace:
    async def test_replace_same_price_item_duplicates_never_inherit(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session, existing=False)
        _, opts = await _make_group_with_options(db_session, c.user.id, percentages=["0", "15", "25"])
        await c.plans.set_plan(c.project.id, c.room.id, c.surface.id, c.user.id, substrate=Substrate.CONCRETE,
                               quality_target=QualityLevel.S2, planned_works=[
                                   Sel(price_item_id=c.p1.id, coefficient_option_ids=[opts[1].id]),
                                   Sel(price_item_id=c.p1.id, coefficient_option_ids=[opts[2].id])])
        a, b = await _rows(db_session, c.plan.id)
        old_keys = [a.occurrence_key, b.occurrence_key]
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(c.project.id, c.user.id)
        by_key = {ln.occurrence_key: ln.id for ln in estimate.lines}
        await _override(svc, c, estimate, by_key[a.occurrence_key], "30.00", "9.000")
        await _override(svc, c, estimate, by_key[b.occurrence_key], "40.00", "7.000")
        before_estimate = await _estimate_snapshot(db_session)

        resp = await async_client.post(c.url, headers=c.headers, json=_body(c, "REPLACE", keys=old_keys, confirmed=True))
        assert resp.status_code == 200, resp.text
        rows = await _rows(db_session, c.plan.id)
        assert [w.price_item_id for w in rows] == [c.p1.id, c.p1.id]  # template has P1 twice
        new_keys = [w.occurrence_key for w in rows]
        assert len(set(new_keys)) == 2 and set(new_keys).isdisjoint(old_keys)
        assert (await db_session.execute(select(func.count()).select_from(SurfacePlannedWorkCoefficientAssignment))).scalar_one() == 0
        assert await _estimate_snapshot(db_session) == before_estimate

        preview = await svc.preview_regeneration(c.project.id, estimate.id, c.user.id)
        removed = {ch.estimate_line_id for ch in preview.changes if ch.change_type == "REMOVED"}
        added = {ch.planned_work_id for ch in preview.changes if ch.change_type == "ADDED"}
        assert removed == set(by_key.values())
        assert added == {w.id for w in rows}
        assert not [ch for ch in preview.changes if ch.change_type == "UPDATED"]

        await svc.regenerate_draft(estimate.id, c.user.id, c.project.id)
        lines = await _lines(db_session, estimate.id)
        assert {ln.id for ln in lines}.isdisjoint(by_key.values())
        assert sorted(ln.occurrence_key for ln in lines) == sorted(new_keys)
        for ln in lines:
            assert (ln.unit_price, ln.quantity, ln.price_override, ln.quantity_overridden) == (Decimal("10.00"), NET, False, False)
            assert ln.coefficient_snapshot == []


class TestStaleConflictsLeaveEstimateUntouched:
    async def test_stale_template_then_refreshed_command_succeeds(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        svc = EstimateService(db_session)
        await svc.generate_estimate(c.project.id, c.user.id)
        before = await _estimate_snapshot(db_session)
        rows_before = [(w.id, w.occurrence_key) for w in await _rows(db_session, c.plan.id)]
        stale_ids = c.step_ids
        refreshed = await c.templates.replace_steps(
            c.user.id, c.template.id, [WorkflowTemplateStepSpec(price_item_id=c.p2.id)]
        )
        resp = await async_client.post(c.url, headers=c.headers, json=_body(c, expected_steps=stale_ids))
        assert resp.status_code == 409
        assert [(w.id, w.occurrence_key) for w in await _rows(db_session, c.plan.id)] == rows_before
        assert await _prov(db_session) == 0
        assert await _estimate_snapshot(db_session) == before
        ok = await async_client.post(c.url, headers=c.headers, json=_body(c, expected_steps=[s.id for s in refreshed.steps]))
        assert ok.status_code == 200 and await _prov(db_session) == 1

    async def test_stale_replace_composition_never_mutates(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        svc = EstimateService(db_session)
        await svc.generate_estimate(c.project.id, c.user.id)
        (x,) = await _rows(db_session, c.plan.id)
        seen = [x.occurrence_key]
        # the plan changes after the owner confirmed [X]: another occurrence is added
        await c.plans.set_plan(c.project.id, c.room.id, c.surface.id, c.user.id, substrate=Substrate.CONCRETE,
                               quality_target=QualityLevel.S2, planned_works=[
                                   Sel(price_item_id=c.x.id, occurrence_key=x.occurrence_key, wait_after_hours=6,
                                       coefficient_option_ids=[c.opts[1].id]),
                                   Sel(price_item_id=c.p2.id)])
        before = await _estimate_snapshot(db_session)
        rows_before = [(w.id, w.occurrence_key) for w in await _rows(db_session, c.plan.id)]
        resp = await async_client.post(c.url, headers=c.headers, json=_body(c, "REPLACE", keys=seen, confirmed=True))
        assert resp.status_code == 409
        assert [(w.id, w.occurrence_key) for w in await _rows(db_session, c.plan.id)] == rows_before
        assert await _prov(db_session) == 0
        assert await _estimate_snapshot(db_session) == before


class TestLegacyAndRealReplace:
    async def test_real_replace_blocks_legacy_fallback(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session, existing=False)
        await c.plans.set_plan(c.project.id, c.room.id, c.surface.id, c.user.id, substrate=Substrate.CONCRETE,
                               quality_target=QualityLevel.S2, planned_works=[Sel(price_item_id=c.p1.id)])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(c.project.id, c.user.id)
        (line,) = estimate.lines
        line_id = line.id
        await _override(svc, c, estimate, line_id, "30.00", "9.000")
        legacy = await db_session.get(EstimateLine, line_id)
        legacy.occurrence_key = None  # pre-0028 line
        await db_session.commit()
        keys = [w.occurrence_key for w in await _rows(db_session, c.plan.id)]
        resp = await async_client.post(c.url, headers=c.headers, json=_body(c, "REPLACE", keys=keys, confirmed=True))
        assert resp.status_code == 200
        preview = await svc.preview_regeneration(c.project.id, estimate.id, c.user.id)
        assert (preview.added, preview.removed) == (2, 1)
        await svc.regenerate_draft(estimate.id, c.user.id, c.project.id)
        lines = await _lines(db_session, estimate.id)
        assert line_id not in {ln.id for ln in lines}
        assert all(not ln.price_override and not ln.quantity_overridden for ln in lines)


class TestRevealIsolation:
    async def test_surface_template_apply_never_touches_opening_reveal_work(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        window = await _make_opening(db_session, c.surface.id)
        reveal_item = await _make_price_item(db_session, c.user.id, category=PriceCategory.REVEAL, unit=PriceUnit.LM, price="15.00")
        await OpeningRevealWorkService(db_session).set_works(window.id, c.user.id, [reveal_item.id])
        (reveal_work,) = (await db_session.execute(select(OpeningRevealPlannedWork))).scalars().all()
        reveal_state = (reveal_work.id, reveal_work.price_item_id, reveal_work.position)
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(c.project.id, c.user.id)
        reveal_line = next(ln for ln in estimate.lines if ln.opening_id is not None)
        reveal_line_id = reveal_line.id
        await _override(svc, c, estimate, reveal_line_id, "33.00", "4.000")

        assert (await async_client.post(c.url, headers=c.headers, json=_body(c))).status_code == 200
        keys = [w.occurrence_key for w in await _rows(db_session, c.plan.id)]
        assert (await async_client.post(c.url, headers=c.headers, json=_body(c, "REPLACE", keys=keys, confirmed=True))).status_code == 200

        (after,) = (await db_session.execute(select(OpeningRevealPlannedWork).execution_options(populate_existing=True))).scalars().all()
        assert (after.id, after.price_item_id, after.position) == reveal_state
        await svc.regenerate_draft(estimate.id, c.user.id, c.project.id)
        kept = next(ln for ln in await _lines(db_session, estimate.id) if ln.opening_id is not None)
        assert (kept.id, kept.unit_price, kept.quantity, kept.occurrence_key) == (reveal_line_id, Decimal("33.00"), Decimal("4.000"), None)
