"""Stage 13E.3 — server-side technological template application.

POST …/work-plan/apply-template: APPEND / REPLACE on the CURRENT plan under
the plan row lock; required + explicitly selected optional steps; stale
template (expected_step_ids) and stale plan (expected_occurrence_keys)
protection; application_id idempotency via a server fingerprint (migration
0029); atomic provenance; Estimate untouched.
"""
from decimal import Decimal
import hashlib
import json
import uuid

from httpx import AsyncClient
from sqlalchemy import func, select, text

from app.domain.services.estimate_service import EstimateService
from app.domain.services.work_plan_service import SurfaceWorkPlanService, _application_fingerprint
from app.domain.services.workflow_template_service import (
    WorkflowTemplateService,
    WorkflowTemplateStepSpec as Step,
)
from app.models.checklist import QualityLevel, Substrate
from app.models.estimate import EstimateLine
from app.models.price_item import PriceCategory
from app.models.surface import SurfaceType
from app.models.user import User
from app.models.work_plan import SurfacePlannedWork, SurfacePlannedWorkCoefficientAssignment
from app.models.workflow_template import SurfaceWorkPlanTemplateApplication, TemplateApplicationMode
from app.schemas.work_plan import ApplyTemplateRequest, OrderedPriceItemSelection as Sel
from tests.test_estimates import _make_price_item, _make_project, _make_room, _make_surface
from tests.test_planned_work_coefficient_assignments import (
    OTHER_USER,
    VALID_USER,
    _make_group_with_options,
    auth_header,
    get_token,
)


async def _login(client, db, user_dict=VALID_USER):
    headers = auth_header(await get_token(client, user_dict))
    user = (await db.execute(select(User).where(User.telegram_user_id == user_dict["id"]))).scalar_one()
    return headers, user


class Ctx:
    pass


async def _setup(client, db, *, quality=QualityLevel.S2, surface_type=SurfaceType.WALL, existing=True):
    c = Ctx()
    c.headers, c.user = await _login(client, db)
    c.project = await _make_project(db, c.user.id)
    c.room = await _make_room(db, c.project.id)
    c.surface = await _make_surface(db, c.room.id, surface_type)
    c.p1 = await _make_price_item(db, c.user.id, category=PriceCategory.PREPARATION, price="10.00")
    c.p2 = await _make_price_item(db, c.user.id, category=PriceCategory.SKIM_COAT, price="20.00")
    c.p3 = await _make_price_item(db, c.user.id, category=PriceCategory.SKIM_COAT, price="30.00")
    c.x = await _make_price_item(db, c.user.id, category=PriceCategory.OTHER, price="5.00")
    _, c.opts = await _make_group_with_options(db, c.user.id, percentages=["0", "15"])
    c.templates = WorkflowTemplateService(db)
    # required P1 (24 h), optional P2, required P1 again (duplicate), optional P3 (48 h)
    c.template = await c.templates.create_template(
        c.user.id, display_name="Beton S2 test",
        applies_to_substrates=[Substrate.CONCRETE], applies_to_quality=[QualityLevel.S2],
        applies_to_surface_types=[SurfaceType.WALL, SurfaceType.CEILING],
        steps=[
            Step(price_item_id=c.p1.id, wait_after_hours=24),
            Step(price_item_id=c.p2.id, is_optional=True),
            Step(price_item_id=c.p1.id),
            Step(price_item_id=c.p3.id, is_optional=True, wait_after_hours=48),
        ],
    )
    c.step_ids = [s.id for s in c.template.steps]
    c.plans = SurfaceWorkPlanService(db)
    c.plan = await c.plans.set_plan(
        c.project.id, c.room.id, c.surface.id, c.user.id,
        substrate=Substrate.CONCRETE, quality_target=quality,
        planned_works=[Sel(price_item_id=c.x.id, wait_after_hours=6, coefficient_option_ids=[c.opts[1].id])] if existing else [],
    )
    c.url = f"/api/projects/{c.project.id}/rooms/{c.room.id}/surfaces/{c.surface.id}/work-plan/apply-template"
    return c


def _body(c, mode="APPEND", *, selected=(), expected_steps=None, keys=None, confirmed=None, app_id=None, template_id=None):
    body = {
        "application_id": str(app_id or uuid.uuid4()),
        "template_id": str(template_id or c.template.id),
        "mode": mode,
        "selected_optional_step_ids": [str(i) for i in selected],
        "expected_step_ids": [str(i) for i in (expected_steps if expected_steps is not None else c.step_ids)],
    }
    if keys is not None:
        body["expected_occurrence_keys"] = [str(k) for k in keys]
    if confirmed is not None:
        body["replace_confirmed"] = confirmed
    return body


async def _rows(db, plan_id):
    rows = await db.execute(
        select(SurfacePlannedWork)
        .where(SurfacePlannedWork.work_plan_id == plan_id)
        .order_by(SurfacePlannedWork.position)
        .execution_options(populate_existing=True)
    )
    return list(rows.scalars().all())


async def _state(db, plan_id):
    rows = await _rows(db, plan_id)
    assignments = (await db.execute(select(func.count()).select_from(SurfacePlannedWorkCoefficientAssignment))).scalar_one()
    prov = (await db.execute(select(func.count()).select_from(SurfaceWorkPlanTemplateApplication))).scalar_one()
    return [(r.id, r.occurrence_key, r.price_item_id, r.position, r.wait_after_hours) for r in rows], assignments, prov


async def _estimate_snapshot(db):
    rows = (await db.execute(text("SELECT * FROM estimate_lines ORDER BY id"))).all()
    return [tuple(r) for r in rows]


# ---------------------------------------------------------------------------
# APPEND
# ---------------------------------------------------------------------------


class TestAppend:
    async def test_append_to_populated_plan(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        (existing,) = await _rows(db_session, c.plan.id)
        before = (existing.id, existing.occurrence_key, existing.price_item_id, existing.position, existing.wait_after_hours)
        resp = await async_client.post(c.url, headers=c.headers, json=_body(c, selected=[c.step_ids[3]]))
        assert resp.status_code == 200, resp.text
        works = resp.json()["planned_works"]
        # existing row untouched (id, key, item, position, wait, coefficients)
        rows = await _rows(db_session, c.plan.id)
        assert (rows[0].id, rows[0].occurrence_key, rows[0].price_item_id, rows[0].position, rows[0].wait_after_hours) == before
        assert [o["id"] for o in works[0]["coefficient_options"]] == [str(c.opts[1].id)]
        # appended in template order: required P1, (P2 unselected), required P1, selected P3
        assert [(w["price_item_id"], w["position"], w["wait_after_hours"]) for w in works[1:]] == [
            (str(c.p1.id), 1, 24), (str(c.p1.id), 2, None), (str(c.p3.id), 3, 48),
        ]
        new_keys = [w["occurrence_key"] for w in works[1:]]
        assert len(set(new_keys)) == 3 and str(existing.occurrence_key) not in new_keys
        assert not set(new_keys) & {str(i) for i in c.step_ids}  # never the template step id
        assert all(w["coefficient_options"] == [] for w in works[1:])
        history = resp.json()["template_applications"]
        assert [(h["mode"], h["steps_applied"], h["template_code"], h["template_name"]) for h in history] == [
            ("APPEND", 3, c.template.code, "Beton S2 test"),
        ]

    async def test_append_to_empty_plan_with_only_required(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session, existing=False)
        resp = await async_client.post(c.url, headers=c.headers, json=_body(c))
        assert resp.status_code == 200, resp.text
        assert [(w["price_item_id"], w["position"]) for w in resp.json()["planned_works"]] == [
            (str(c.p1.id), 0), (str(c.p1.id), 1),
        ]

    async def test_append_leaves_estimate_untouched_then_regeneration_adds(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(c.project.id, c.user.id)
        (line,) = estimate.lines
        await svc.patch_line(c.project.id, estimate.id, c.user.id, line.id, provided_fields={"unit_price"}, unit_price=Decimal("7.00"))
        before = await _estimate_snapshot(db_session)
        resp = await async_client.post(c.url, headers=c.headers, json=_body(c, selected=[c.step_ids[1]]))
        assert resp.status_code == 200
        assert await _estimate_snapshot(db_session) == before
        result = await svc.regenerate_draft(estimate.id, c.user.id, c.project.id)
        assert (result.added, result.removed) == (3, 0)
        kept = await db_session.get(EstimateLine, line.id)
        assert (kept.unit_price, kept.price_override) == (Decimal("7.00"), True)


# ---------------------------------------------------------------------------
# REPLACE
# ---------------------------------------------------------------------------


class TestReplace:
    async def _with_legacy_reveal(self, c, db):
        reveal = await _make_price_item(db, c.user.id, category=PriceCategory.REVEAL)
        rows = await _rows(db, c.plan.id)
        db.add(SurfacePlannedWork(work_plan_id=c.plan.id, price_item_id=reveal.id, position=len(rows), occurrence_key=uuid.uuid4()))
        await db.commit()
        return [r.occurrence_key for r in await _rows(db, c.plan.id)]

    async def test_replace_requires_confirmation_and_keys(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        keys = [r.occurrence_key for r in await _rows(db_session, c.plan.id)]
        before = await _state(db_session, c.plan.id)
        for body in (_body(c, "REPLACE", keys=keys), _body(c, "REPLACE", keys=keys, confirmed=False), _body(c, "REPLACE", confirmed=True)):
            resp = await async_client.post(c.url, headers=c.headers, json=body)
            assert resp.status_code == 422, body
            assert await _state(db_session, c.plan.id) == before

    async def test_replace_removes_everything_and_materializes_new(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        keys = await self._with_legacy_reveal(c, db_session)
        old_ids = {r.id for r in await _rows(db_session, c.plan.id)}
        resp = await async_client.post(c.url, headers=c.headers, json=_body(c, "REPLACE", selected=[c.step_ids[1]], keys=keys, confirmed=True))
        assert resp.status_code == 200, resp.text
        works = resp.json()["planned_works"]
        assert [(w["price_item_id"], w["position"], w["wait_after_hours"]) for w in works] == [
            (str(c.p1.id), 0, 24), (str(c.p2.id), 1, None), (str(c.p1.id), 2, None),
        ]
        new_keys = {w["occurrence_key"] for w in works}
        assert len(new_keys) == 3 and not new_keys & {str(k) for k in keys}
        assert not {uuid.UUID(w["id"]) for w in works} & old_ids
        assert all(w["coefficient_options"] == [] for w in works)
        assert (await db_session.execute(select(func.count()).select_from(SurfacePlannedWorkCoefficientAssignment))).scalar_one() == 0
        assert [(h["mode"], h["steps_applied"]) for h in resp.json()["template_applications"]] == [("REPLACE", 3)]

    async def test_stale_composition_is_409(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        keys = await self._with_legacy_reveal(c, db_session)
        before = await _state(db_session, c.plan.id)
        for stale in (keys + [uuid.uuid4()], keys[:1], list(reversed(keys)), [uuid.uuid4(), keys[1]]):
            resp = await async_client.post(c.url, headers=c.headers, json=_body(c, "REPLACE", keys=stale, confirmed=True))
            assert resp.status_code == 409, stale
            assert await _state(db_session, c.plan.id) == before

    async def test_replace_estimate_untouched_then_removed_added_without_overrides(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        await c.plans.set_plan(c.project.id, c.room.id, c.surface.id, c.user.id, substrate=Substrate.CONCRETE,
                               quality_target=QualityLevel.S2, planned_works=[Sel(price_item_id=c.p1.id)])
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(c.project.id, c.user.id)
        (line,) = estimate.lines
        await svc.patch_line(c.project.id, estimate.id, c.user.id, line.id, provided_fields={"unit_price", "quantity"},
                             unit_price=Decimal("99.00"), quantity=Decimal("3.000"))
        before = await _estimate_snapshot(db_session)
        keys = [r.occurrence_key for r in await _rows(db_session, c.plan.id)]
        resp = await async_client.post(c.url, headers=c.headers, json=_body(c, "REPLACE", keys=keys, confirmed=True))
        assert resp.status_code == 200
        assert await _estimate_snapshot(db_session) == before
        preview = await svc.preview_regeneration(c.project.id, estimate.id, c.user.id)
        assert (preview.added, preview.removed) == (2, 1)
        await svc.regenerate_draft(estimate.id, c.user.id, c.project.id)
        lines = (await svc.get_estimate_detail(c.project.id, estimate.id, c.user.id)).lines
        assert all(not ln.price_override and not ln.quantity_overridden for ln in lines)
        assert all(ln.unit_price == Decimal("10.00") for ln in lines)


# ---------------------------------------------------------------------------
# Validation / stale template (all leave state unchanged)
# ---------------------------------------------------------------------------


class TestValidation:
    async def _expect(self, client, db, c, body, status):
        before = await _state(db, c.plan.id)
        resp = await client.post(c.url, headers=c.headers, json=body)
        assert resp.status_code == status, (body, resp.text)
        assert await _state(db, c.plan.id) == before
        return resp

    async def test_unknown_and_foreign_template_are_indistinguishable_404(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        other_headers, other = await _login(async_client, db_session, OTHER_USER)
        foreign = (await async_client.post("/api/workflow-templates", headers=other_headers, json={"display_name": "Obca"})).json()
        a = await self._expect(async_client, db_session, c, _body(c, template_id=uuid.uuid4()), 404)
        b = await self._expect(async_client, db_session, c, _body(c, template_id=foreign["id"]), 404)
        assert a.json() == b.json()

    async def test_missing_plan_404(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        bare = await _make_surface(db_session, c.room.id)
        resp = await async_client.post(c.url.replace(str(c.surface.id), str(bare.id)), headers=c.headers, json=_body(c))
        assert resp.status_code == 404 and resp.json()["detail"] == "Surface work plan not found"

    async def test_archived_template_409(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        await c.templates.archive_template(c.user.id, c.template.id)
        await self._expect(async_client, db_session, c, _body(c), 409)

    async def test_no_quality_target_422(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session, quality=None)
        await self._expect(async_client, db_session, c, _body(c), 422)

    async def test_incompatible_substrate_quality_surface_422(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session, quality=QualityLevel.S3)
        await self._expect(async_client, db_session, c, _body(c), 422)  # quality mismatch
        await c.plans.set_plan(c.project.id, c.room.id, c.surface.id, c.user.id, substrate=Substrate.GYPSUM_PLASTER,
                               quality_target=QualityLevel.S2, planned_works=[])
        await self._expect(async_client, db_session, c, _body(c), 422)  # substrate mismatch
        floor = await _setup(async_client, db_session, surface_type=SurfaceType.FLOOR)
        await self._expect(async_client, db_session, floor, _body(floor), 422)  # surface type mismatch

    async def test_stale_template_steps_409(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        s = c.step_ids
        for stale in (s[:3], s + [uuid.uuid4()], [s[1], s[0], s[2], s[3]], [uuid.uuid4(), s[1], s[2], s[3]]):
            await self._expect(async_client, db_session, c, _body(c, expected_steps=stale), 409)
        # a real step replacement recreates the ids: the old preview is stale
        await c.templates.replace_steps(c.user.id, c.template.id, [Step(price_item_id=c.p1.id)])
        await self._expect(async_client, db_session, c, _body(c), 409)

    async def test_metadata_edit_does_not_block(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        await c.templates.update_template(c.user.id, c.template.id, display_name="Nowa nazwa")
        resp = await async_client.post(c.url, headers=c.headers, json=_body(c))
        assert resp.status_code == 200
        assert resp.json()["template_applications"][0]["template_name"] == "Nowa nazwa"

    async def test_invalid_optional_selection_422(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        other = await c.templates.create_template(c.user.id, display_name="Inna", steps=[Step(price_item_id=c.p2.id, is_optional=True)])
        for selected in ([uuid.uuid4()], [c.step_ids[0]], [c.step_ids[1], c.step_ids[1]], [other.steps[0].id]):
            await self._expect(async_client, db_session, c, _body(c, selected=selected), 422)

    async def test_archived_items(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        c.p3.is_archived = True  # optional P3
        await db_session.commit()
        await self._expect(async_client, db_session, c, _body(c, selected=[c.step_ids[3]]), 422)
        ok = await async_client.post(c.url, headers=c.headers, json=_body(c))  # P3 unselected: allowed
        assert ok.status_code == 200
        c.p1.is_archived = True  # required P1
        await db_session.commit()
        await self._expect(async_client, db_session, c, _body(c), 422)

    async def test_reveal_item_blocked(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        c.p2.category = PriceCategory.REVEAL  # item re-categorised after the template was built
        await db_session.commit()
        await self._expect(async_client, db_session, c, _body(c, selected=[c.step_ids[1]]), 422)

    async def test_zero_materialized_works_422(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        only_optional = await c.templates.create_template(c.user.id, display_name="Opcje", steps=[Step(price_item_id=c.p2.id, is_optional=True)])
        body = _body(c, template_id=only_optional.id, expected_steps=[only_optional.steps[0].id])
        await self._expect(async_client, db_session, c, body, 422)

    async def test_client_cannot_send_server_owned_fields(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        for extra in ({"steps_applied": 9}, {"price_item_ids": [str(c.p1.id)]}, {"wait_after_hours": 1}):
            await self._expect(async_client, db_session, c, {**_body(c), **extra}, 422)


# ---------------------------------------------------------------------------
# Idempotency (sequential; PostgreSQL concurrency is proven in the scratch gate)
# ---------------------------------------------------------------------------


class TestIdempotency:
    async def test_identical_append_retry_is_a_noop(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        body = _body(c, selected=[c.step_ids[1]])
        first = await async_client.post(c.url, headers=c.headers, json=body)
        after_first = await _state(db_session, c.plan.id)
        second = await async_client.post(c.url, headers=c.headers, json=body)
        assert first.status_code == second.status_code == 200
        assert second.json() == first.json()
        assert await _state(db_session, c.plan.id) == after_first
        assert after_first[2] == 1

    async def test_identical_replace_retry_is_a_noop(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        keys = [r.occurrence_key for r in await _rows(db_session, c.plan.id)]
        body = _body(c, "REPLACE", keys=keys, confirmed=True)
        first = await async_client.post(c.url, headers=c.headers, json=body)
        after_first = await _state(db_session, c.plan.id)
        second = await async_client.post(c.url, headers=c.headers, json=body)  # keys now stale, but it is a replay
        assert second.status_code == 200 and second.json() == first.json()
        assert await _state(db_session, c.plan.id) == after_first

    async def test_reuse_with_different_content_is_409(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        app_id = uuid.uuid4()
        keys = [r.occurrence_key for r in await _rows(db_session, c.plan.id)]
        assert (await async_client.post(c.url, headers=c.headers, json=_body(c, app_id=app_id))).status_code == 200
        other = await c.templates.create_template(c.user.id, display_name="Inna", applies_to_quality=[QualityLevel.S2],
                                                  steps=[Step(price_item_id=c.p2.id)])
        project2_surface = await _make_surface(db_session, c.room.id)
        await c.plans.set_plan(c.project.id, c.room.id, project2_surface.id, c.user.id, substrate=Substrate.CONCRETE,
                               quality_target=QualityLevel.S2, planned_works=[])
        variants = [
            (c.url, _body(c, app_id=app_id, template_id=other.id, expected_steps=[other.steps[0].id])),  # template
            (c.url, _body(c, app_id=app_id, selected=[c.step_ids[1]])),  # optional selection
            (c.url, _body(c, "REPLACE", app_id=app_id, keys=keys, confirmed=True)),  # mode
            (c.url.replace(str(c.surface.id), str(project2_surface.id)), _body(c, app_id=app_id)),  # another plan
        ]
        for url, body in variants:
            before = await _state(db_session, c.plan.id)
            resp = await async_client.post(url, headers=c.headers, json=body)
            assert resp.status_code == 409, body
            assert await _state(db_session, c.plan.id) == before

    async def test_replace_reuse_with_different_expected_composition_is_409(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        app_id = uuid.uuid4()
        keys = [r.occurrence_key for r in await _rows(db_session, c.plan.id)]
        assert (await async_client.post(c.url, headers=c.headers, json=_body(c, "REPLACE", app_id=app_id, keys=keys, confirmed=True))).status_code == 200
        resp = await async_client.post(c.url, headers=c.headers, json=_body(c, "REPLACE", app_id=app_id, keys=[uuid.uuid4()], confirmed=True))
        assert resp.status_code == 409

    async def test_fingerprint_is_deterministic_and_selection_order_independent(self, db_session):
        plan_id, tid, s1, s2 = (uuid.uuid4() for _ in range(4))
        def req(sel):
            return ApplyTemplateRequest(application_id=uuid.uuid4(), template_id=tid, mode=TemplateApplicationMode.APPEND,
                                        selected_optional_step_ids=sel, expected_step_ids=[s1, s2])
        assert _application_fingerprint(plan_id, req([s1, s2])) == _application_fingerprint(plan_id, req([s2, s1]))
        assert _application_fingerprint(plan_id, req([s1])) != _application_fingerprint(plan_id, req([s2]))
        assert len(_application_fingerprint(plan_id, req([]))) == 64


# ---------------------------------------------------------------------------
# 13E.5B-FIX.4: final reviewed APPEND selection (selected_step_ids)
# ---------------------------------------------------------------------------


def _reviewed(c, step_ids, **kw):
    body = _body(c, **kw)
    body["selected_step_ids"] = [str(i) for i in step_ids]
    return body


class TestReviewedSelection:
    async def _expect(self, client, db, c, body, status):
        before = await _state(db, c.plan.id)
        resp = await client.post(c.url, headers=c.headers, json=body)
        assert resp.status_code == status, (body, resp.text)
        assert await _state(db, c.plan.id) == before  # nothing written, no history
        return resp

    async def test_required_step_can_be_skipped_in_template_order(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        (existing,) = await _rows(db_session, c.plan.id)
        before = (existing.id, existing.occurrence_key, existing.price_item_id, existing.position, existing.wait_after_hours)
        # skip the first required P1, keep the second required P1 and optional P3 (sent out of order)
        resp = await async_client.post(c.url, headers=c.headers, json=_reviewed(c, [c.step_ids[3], c.step_ids[2]]))
        assert resp.status_code == 200, resp.text
        works = resp.json()["planned_works"]
        rows = await _rows(db_session, c.plan.id)
        assert (rows[0].id, rows[0].occurrence_key, rows[0].price_item_id, rows[0].position, rows[0].wait_after_hours) == before
        assert [o["id"] for o in works[0]["coefficient_options"]] == [str(c.opts[1].id)]
        assert [(w["price_item_id"], w["position"], w["wait_after_hours"]) for w in works[1:]] == [
            (str(c.p1.id), 1, None), (str(c.p3.id), 2, 48),
        ]
        assert all(w["coefficient_options"] == [] for w in works[1:])
        assert len({w["occurrence_key"] for w in works}) == 3
        (app,) = resp.json()["template_applications"]
        assert (app["mode"], app["steps_applied"]) == ("APPEND", 2)

    async def test_deliberate_duplicate_occurrence_is_still_allowed(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session, existing=False)
        await c.plans.set_plan(c.project.id, c.room.id, c.surface.id, c.user.id, substrate=Substrate.CONCRETE,
                               quality_target=QualityLevel.S2, planned_works=[Sel(price_item_id=c.p1.id)])
        resp = await async_client.post(c.url, headers=c.headers, json=_reviewed(c, [c.step_ids[0], c.step_ids[2]]))
        assert resp.status_code == 200, resp.text
        works = resp.json()["planned_works"]
        assert [w["price_item_id"] for w in works] == [str(c.p1.id)] * 3  # never deduplicated server-side
        assert len({w["occurrence_key"] for w in works}) == 3

    async def test_invalid_reviewed_selections_are_rejected_without_mutation(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        other = await c.templates.create_template(c.user.id, display_name="Inna", steps=[Step(price_item_id=c.p2.id)])
        keys = [r.occurrence_key for r in await _rows(db_session, c.plan.id)]
        for body in (
            _reviewed(c, []),                                   # zero works
            _reviewed(c, [uuid.uuid4()]),                       # unknown step
            _reviewed(c, [other.steps[0].id]),                  # another template's step
            _reviewed(c, [c.step_ids[0], c.step_ids[0]]),       # duplicate id
            _reviewed(c, [c.step_ids[0]], selected=[c.step_ids[1]]),  # both selection fields
            _reviewed(c, [c.step_ids[0]], mode="REPLACE", keys=keys, confirmed=True),  # APPEND only
            {**_reviewed(c, [c.step_ids[0]]), "selected_step_ids": [str(c.p1.id)]},   # a PriceItem id is not a step
        ):
            await self._expect(async_client, db_session, c, body, 422)

    async def test_stale_template_and_archived_selected_item_still_protected(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        await self._expect(async_client, db_session, c, _reviewed(c, [c.step_ids[0]], expected_steps=c.step_ids[:3]), 409)
        c.p3.is_archived = True
        await db_session.commit()
        await self._expect(async_client, db_session, c, _reviewed(c, [c.step_ids[3]]), 422)
        ok = await async_client.post(c.url, headers=c.headers, json=_reviewed(c, [c.step_ids[0]]))
        assert ok.status_code == 200, ok.text

    async def test_idempotent_retry_and_changed_selection_conflict(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        body = _reviewed(c, [c.step_ids[1], c.step_ids[2]])
        first = await async_client.post(c.url, headers=c.headers, json=body)
        after = await _state(db_session, c.plan.id)
        second = await async_client.post(c.url, headers=c.headers, json=body)
        assert first.status_code == second.status_code == 200
        assert second.json() == first.json() and await _state(db_session, c.plan.id) == after
        changed = {**body, "selected_step_ids": [str(c.step_ids[2])]}
        conflict = await async_client.post(c.url, headers=c.headers, json=changed)
        assert conflict.status_code == 409
        assert await _state(db_session, c.plan.id) == after

    async def test_estimate_untouched(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        await EstimateService(db_session).generate_estimate(c.project.id, c.user.id)
        before = await _estimate_snapshot(db_session)
        resp = await async_client.post(c.url, headers=c.headers, json=_reviewed(c, [c.step_ids[2]]))
        assert resp.status_code == 200
        assert await _estimate_snapshot(db_session) == before

    async def test_legacy_fingerprint_unchanged_and_selection_is_covered(self, db_session):
        plan_id, tid, s1, s2 = (uuid.uuid4() for _ in range(4))
        legacy = ApplyTemplateRequest(application_id=uuid.uuid4(), template_id=tid, mode=TemplateApplicationMode.APPEND,
                                      selected_optional_step_ids=[s2], expected_step_ids=[s1, s2])
        v1 = {"v": 1, "work_plan_id": str(plan_id), "template_id": str(tid), "mode": "APPEND",
              "selected_optional_step_ids": [str(s2)], "expected_step_ids": [str(s1), str(s2)],
              "expected_occurrence_keys": None, "replace_confirmed": None}
        expected = hashlib.sha256(json.dumps(v1, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        assert _application_fingerprint(plan_id, legacy) == expected  # pre-FIX.4 retries stay idempotent
        def reviewed(sel):
            return ApplyTemplateRequest(application_id=uuid.uuid4(), template_id=tid, mode=TemplateApplicationMode.APPEND,
                                        selected_step_ids=sel, expected_step_ids=[s1, s2])
        assert _application_fingerprint(plan_id, reviewed([s1, s2])) == _application_fingerprint(plan_id, reviewed([s2, s1]))
        assert _application_fingerprint(plan_id, reviewed([s1])) != _application_fingerprint(plan_id, reviewed([s2]))
        assert _application_fingerprint(plan_id, reviewed([s2])) != _application_fingerprint(plan_id, legacy)


# ---------------------------------------------------------------------------
# Decoupling and existing flows
# ---------------------------------------------------------------------------


class TestDecoupling:
    async def test_template_changes_after_apply_do_not_touch_plan_or_history(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        resp = await async_client.post(c.url, headers=c.headers, json=_body(c))
        before = await _state(db_session, c.plan.id)
        await c.templates.update_template(c.user.id, c.template.id, display_name="Zmieniona")
        await c.templates.replace_steps(c.user.id, c.template.id, [Step(price_item_id=c.p3.id, wait_after_hours=99)])
        await c.templates.archive_template(c.user.id, c.template.id)
        assert await _state(db_session, c.plan.id) == before
        history = (await db_session.execute(select(SurfaceWorkPlanTemplateApplication).execution_options(populate_existing=True))).scalars().all()
        assert [(h.template_name, h.steps_applied) for h in history] == [("Beton S2 test", 2)]
        assert resp.json()["template_applications"][0]["id"] == str(history[0].id)

    async def test_default_template_applies_with_name_key_snapshot(self, async_client: AsyncClient, db_session):
        headers, user = await _login(async_client, db_session)
        listed = (await async_client.get("/api/workflow-templates", headers=headers, params={
            "substrate": "CONCRETE", "quality_target": "S2", "surface_type": "WALL"})).json()["items"]
        (tpl,) = listed
        project = await _make_project(db_session, user.id)
        room = await _make_room(db_session, project.id)
        surface = await _make_surface(db_session, room.id)
        await SurfaceWorkPlanService(db_session).set_plan(project.id, room.id, surface.id, user.id,
                                                          substrate=Substrate.CONCRETE, quality_target=QualityLevel.S2, planned_works=[])
        url = f"/api/projects/{project.id}/rooms/{room.id}/surfaces/{surface.id}/work-plan/apply-template"
        resp = await async_client.post(url, headers=headers, json={
            "application_id": str(uuid.uuid4()), "template_id": tpl["id"], "mode": "APPEND",
            "selected_optional_step_ids": [], "expected_step_ids": [s["id"] for s in tpl["steps"]],
        })
        assert resp.status_code == 200, resp.text
        required = [s for s in tpl["steps"] if not s["is_optional"]]
        assert [w["price_item_id"] for w in resp.json()["planned_works"]] == [s["price_item_id"] for s in required]
        assert resp.json()["template_applications"][0]["template_name"] == "workflow_templates.seed.tech_beton_s2"

    async def test_put_and_apply_to_all_contracts_unchanged(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        await _make_surface(db_session, c.room.id)
        await async_client.post(c.url, headers=c.headers, json=_body(c))
        base = f"/api/projects/{c.project.id}/rooms/{c.room.id}/surfaces/{c.surface.id}/work-plan"
        got = (await async_client.get(base, headers=c.headers)).json()
        put = await async_client.put(base, headers=c.headers, json={"substrate": "CONCRETE", "quality_target": "S2", "planned_works": [
            {"price_item_id": w["price_item_id"], "occurrence_key": w["occurrence_key"], "wait_after_hours": w["wait_after_hours"],
             "coefficient_option_ids": [o["id"] for o in w["coefficient_options"]]} for w in got["planned_works"]]})
        assert put.status_code == 200
        assert [w["occurrence_key"] for w in put.json()["planned_works"]] == [w["occurrence_key"] for w in got["planned_works"]]
        applied = await async_client.post(f"{base}/apply-to-room-walls", headers=c.headers)
        assert applied.status_code == 200 and applied.json()["targets"][0]["template_applications"] == []
