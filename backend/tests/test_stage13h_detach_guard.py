"""Stage 13H.4 — execution-safe destructive WorkPlan mutations.

Every path that can remove current occurrences (ordinary save, service
replace_planned_works, template REPLACE, apply-to-all targets) must not detach
IN_PROGRESS/COMPLETED execution silently: the request must carry
`confirm_execution_detach_keys` equal to EXACTLY the protected set, else 409
WORK_EXECUTION_DETACH_CONFIRMATION_REQUIRED listing the current affected
records. Append-only paths (APPEND, recommendation accept) and key-preserving
saves never need it. Real row-lock concurrency is exercised separately against
PostgreSQL (SQLite has no row locks); here the lock ORDER is asserted.
"""
import hashlib
import json
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import event, func, select

from app.domain.exceptions import ExecutionDetachConfirmationRequiredError
from app.domain.services.work_execution_service import SurfaceWorkExecutionService
from app.domain.services.work_plan_service import SurfaceWorkPlanService, _application_fingerprint
from app.models.checklist import Substrate
from app.models.work_execution import SurfaceWorkExecution, WorkExecutionStatus
from app.models.work_plan import SurfaceWorkPlan
from app.models.workflow_template import SurfaceWorkPlanTemplateApplication, TemplateApplicationMode
from app.schemas.work_plan import ApplyTemplateRequest, OrderedPriceItemSelection
from tests.test_apply_template import _body, _login
from tests.test_planned_work_coefficient_assignments import (
    _make_price_item,
    _make_project,
    _make_room,
    _make_surface,
)
from tests.test_stage13h_execution_api import OTHER_USER, _ctx, _exec_rows, _patch, _works
from tests.test_work_recommendation_accept import _setup_actionable

CODE = "WORK_EXECUTION_DETACH_CONFIRMATION_REQUIRED"
S = WorkExecutionStatus


async def _save(client, c, rows, confirm=None, **extra):
    """rows = [(price_item_id, occurrence_key|None, wait)]; returns the response."""
    body = {
        "substrate": extra.pop("substrate", "CONCRETE"), "quality_target": extra.pop("quality_target", "S2"),
        "planned_works": [
            {"price_item_id": str(item), "occurrence_key": str(key) if key else None, "wait_after_hours": wait}
            for item, key, wait in rows
        ],
        **extra,
    }
    if confirm is not None:
        body["confirm_execution_detach_keys"] = [str(k) for k in confirm]
    return await client.put(c.base, headers=c.headers, json=body)


async def _abc(client, c):
    """Plan A (NOT_STARTED), B (COMPLETED), C (IN_PROGRESS); returns keys."""
    resp = await _save(client, c, [(c.p1.id, None, None), (c.p2.id, None, 24), (c.p3.id, None, None)])
    assert resp.status_code == 200, resp.text
    a, b, cc = (w["occurrence_key"] for w in resp.json()["planned_works"])
    assert (await _patch(client, c, b, "COMPLETED", "NOT_STARTED")).status_code == 200
    assert (await _patch(client, c, cc, "IN_PROGRESS", "NOT_STARTED")).status_code == 200
    return a, b, cc


def _affected(resp) -> list[tuple[str, str]]:
    assert resp.status_code == 409, resp.text
    detail = resp.json()["detail"]
    assert detail["code"] == CODE
    return [(e["occurrence_key"], e["status"]) for e in detail["affected"]]


async def _snapshot(client, c):
    works = await _works(client, c)
    return [(w["occurrence_key"], w["price_item_id"], w["wait_after_hours"], w["execution"]["status"]) for w in works]


# ---------------------------------------------------------------------------
# Ordinary save
# ---------------------------------------------------------------------------


class TestOrdinarySave:
    async def test_remove_not_started_needs_no_confirmation(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        a, b, cc = await _abc(async_client, c)
        resp = await _save(async_client, c, [(c.p2.id, b, 24), (c.p3.id, cc, None)])  # A removed
        assert resp.status_code == 200, resp.text

    async def test_remove_explicit_not_started_row_needs_no_confirmation(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        a, b, cc = await _abc(async_client, c)
        await _patch(async_client, c, a, "IN_PROGRESS", "NOT_STARTED")
        await _patch(async_client, c, a, "NOT_STARTED", "IN_PROGRESS")  # explicit NOT_STARTED row
        resp = await _save(async_client, c, [(c.p2.id, b, 24), (c.p3.id, cc, None)])
        assert resp.status_code == 200, resp.text
        rows = {str(r.occurrence_key): r.status for r in await _exec_rows(db_session)}
        assert rows[a] == S.NOT_STARTED  # kept as detached history

    async def test_owner_example_exact_set(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        a, b, cc = await _abc(async_client, c)
        before = await _snapshot(async_client, c)

        # result A, C -> removes B (COMPLETED)
        resp = await _save(async_client, c, [(c.p1.id, a, None), (c.p3.id, cc, None)])
        assert _affected(resp) == [(b, "COMPLETED")]
        entry = resp.json()["detail"]["affected"][0]
        assert entry["surface_id"] == str(c.ids[2]) and entry["position"] == 1
        assert entry["price_item_id"] == str(c.p2.id) and entry["price_item_code"] == c.p2.code
        assert set(entry) == {"surface_id", "occurrence_key", "position", "status", "price_item_id",
                              "price_item_code", "price_item_name_key", "price_item_display_name"}
        assert await _snapshot(async_client, c) == before  # nothing mutated

        # result A only -> removes B + C; [B] is a subset
        assert _affected(await _save(async_client, c, [(c.p1.id, a, None)], confirm=[b])) == [
            (b, "COMPLETED"), (cc, "IN_PROGRESS")]
        assert await _snapshot(async_client, c) == before
        # [B, C] exact (order irrelevant)
        resp = await _save(async_client, c, [(c.p1.id, a, None)], confirm=[cc, b])
        assert resp.status_code == 200, resp.text
        assert [w["occurrence_key"] for w in resp.json()["planned_works"]] == [a]
        rows = {str(r.occurrence_key): r.status for r in await _exec_rows(db_session)}
        assert rows == {b: S.COMPLETED, cc: S.IN_PROGRESS}  # detached history kept

    @pytest.mark.parametrize("status", ["IN_PROGRESS", "COMPLETED"])
    async def test_remove_protected_without_confirmation_is_409(self, async_client: AsyncClient, db_session, status):
        c = await _ctx(async_client, db_session)
        resp = await _save(async_client, c, [(c.p1.id, None, None), (c.p2.id, None, None)])
        k1, k2 = (w["occurrence_key"] for w in resp.json()["planned_works"])
        await _patch(async_client, c, k2, status, "NOT_STARTED")
        before = await _snapshot(async_client, c)
        for confirm in (None, []):
            assert _affected(await _save(async_client, c, [(c.p1.id, k1, None)], confirm=confirm)) == [(k2, status)]
        assert await _snapshot(async_client, c) == before
        assert (await _save(async_client, c, [(c.p1.id, k1, None)], confirm=[k2])).status_code == 200

    async def test_superset_and_unrelated_keys_are_409(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        a, b, cc = await _abc(async_client, c)
        keep = [(c.p1.id, a, None), (c.p3.id, cc, None)]
        assert _affected(await _save(async_client, c, keep, confirm=[b, str(uuid.uuid4())])) == [(b, "COMPLETED")]
        assert _affected(await _save(async_client, c, keep, confirm=[b, cc])) == [(b, "COMPLETED")]  # cc kept
        # nothing protected is removed, but a stale/unrelated key is sent
        resp = await _save(async_client, c, [(c.p1.id, a, None), (c.p2.id, b, 24), (c.p3.id, cc, None)],
                           confirm=[str(uuid.uuid4())])
        assert _affected(resp) == []
        assert (await _save(async_client, c, keep, confirm=[b])).status_code == 200

    async def test_confirmation_schema(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        a, b, cc = await _abc(async_client, c)
        keep = [(c.p1.id, a, None), (c.p3.id, cc, None)]
        assert (await _save(async_client, c, keep, confirm=[b, b])).status_code == 422  # duplicates
        for bad in (["not-a-uuid"], [123], "b"):
            resp = await async_client.put(c.base, headers=c.headers, json={
                "substrate": "CONCRETE", "quality_target": "S2", "confirm_execution_detach_keys": bad,
                "planned_works": [{"price_item_id": str(c.p1.id), "occurrence_key": a}]})
            assert resp.status_code == 422, bad
        assert (await _save(async_client, c, keep, confirm_execution_loss=True)).status_code == 422

    async def test_key_preserving_saves_never_need_confirmation(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        a, b, cc = await _abc(async_client, c)
        rows = {str(r.occurrence_key): (r.status, r.started_at, r.completed_at) for r in await _exec_rows(db_session)}
        for payload, extra in [
            ([(c.p3.id, cc, None), (c.p1.id, a, None), (c.p2.id, b, 24)], {}),                  # reorder
            ([(c.p1.id, a, 4), (c.p2.id, b, 72), (c.p3.id, cc, None)], {}),                      # waits
            ([(c.p1.id, a, None), (c.p2.id, b, 24), (c.p3.id, cc, None)],
             {"substrate": "GYPSUM_PLASTER", "quality_target": "S3"}),                            # quality/substrate
            ([(c.p1.id, a, None), (c.p2.id, b, 24), (c.p3.id, cc, None), (c.p1.id, None, None)], {}),  # add
        ]:
            resp = await _save(async_client, c, payload, **extra)
            assert resp.status_code == 200, resp.text
        after = {str(r.occurrence_key): (r.status, r.started_at, r.completed_at) for r in await _exec_rows(db_session)}
        assert after == rows
        statuses = {w["occurrence_key"]: w["execution"]["status"] for w in await _works(async_client, c)}
        assert (statuses[b], statuses[cc]) == ("COMPLETED", "IN_PROGRESS")

    async def test_duplicate_price_items_protected_independently(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        resp = await _save(async_client, c, [(c.p2.id, None, None), (c.p2.id, None, None)])
        k1, k2 = (w["occurrence_key"] for w in resp.json()["planned_works"])
        await _patch(async_client, c, k2, "COMPLETED", "NOT_STARTED")
        assert (await _save(async_client, c, [(c.p2.id, k2, None)])).status_code == 200  # drop NOT_STARTED twin
        assert _affected(await _save(async_client, c, [(c.p2.id, None, None)])) == [(k2, "COMPLETED")]

    async def test_legacy_price_item_ids_save_is_guarded(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        key = (await _works(async_client, c))[0]["occurrence_key"]
        await _patch(async_client, c, key, "COMPLETED", "NOT_STARTED")
        resp = await async_client.put(c.base, headers=c.headers, json={
            "substrate": "CONCRETE", "quality_target": "S2", "price_item_ids": [str(c.x.id)]})
        assert _affected(resp) == [(key, "COMPLETED")]

    async def test_service_replace_planned_works_is_guarded(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        key = (await _works(async_client, c))[0]["occurrence_key"]
        await _patch(async_client, c, key, "IN_PROGRESS", "NOT_STARTED")
        svc = SurfaceWorkPlanService(db_session)
        user_id, p1_id = c.user.id, c.p1.id  # plain ids survive the rollback below
        sel = [OrderedPriceItemSelection(price_item_id=p1_id)]
        with pytest.raises(ExecutionDetachConfirmationRequiredError) as err:
            await svc.replace_planned_works(*c.ids, user_id, planned_works=sel)
        assert [str(a.occurrence_key) for a in err.value.affected] == [key]
        await db_session.rollback()
        plan = await svc.replace_planned_works(*c.ids, user_id, planned_works=sel,
                                               confirm_execution_detach_keys=[uuid.UUID(key)])
        assert [w.price_item_id for w in plan.planned_works] == [p1_id]

    async def test_foreign_confirmation_key_is_never_resolved(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        a, b, cc = await _abc(async_client, c)
        _, stranger = await _login(async_client, db_session, OTHER_USER)
        s_project = await _make_project(db_session, stranger.id)
        s_room = await _make_room(db_session, s_project.id)
        s_surface = await _make_surface(db_session, s_room.id)
        s_item = await _make_price_item(db_session, stranger.id, code="FOREIGN_SECRET")
        s_plan = await SurfaceWorkPlanService(db_session).set_plan(
            s_project.id, s_room.id, s_surface.id, stranger.id, substrate=Substrate.CONCRETE,
            planned_works=[OrderedPriceItemSelection(price_item_id=s_item.id)])
        s_key = s_plan.planned_works[0].occurrence_key
        await SurfaceWorkExecutionService(db_session).transition(
            s_project.id, s_room.id, s_surface.id, stranger.id, s_key,
            status=S.COMPLETED, expected_status=S.NOT_STARTED)

        resp = await _save(async_client, c, [(c.p1.id, a, None), (c.p3.id, cc, None)], confirm=[b, s_key])
        assert _affected(resp) == [(b, "COMPLETED")]
        assert str(s_key) not in resp.text and "FOREIGN_SECRET" not in resp.text and str(s_surface.id) not in resp.text


# ---------------------------------------------------------------------------
# Template apply
# ---------------------------------------------------------------------------


async def _applications(db) -> int:
    return (await db.execute(select(func.count()).select_from(SurfaceWorkPlanTemplateApplication))).scalar_one()


class TestTemplateApply:
    async def test_append_needs_no_confirmation_and_preserves_execution(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        key = (await _works(async_client, c))[0]["occurrence_key"]
        await _patch(async_client, c, key, "COMPLETED", "NOT_STARTED")
        resp = await async_client.post(c.url, headers=c.headers, json=_body(c))
        assert resp.status_code == 200, resp.text
        works = resp.json()["planned_works"]
        assert works[0]["occurrence_key"] == key and works[0]["execution"]["status"] == "COMPLETED"
        assert all(w["execution"]["status"] == "NOT_STARTED" for w in works[1:])

    async def test_append_with_a_confirmation_is_an_exact_set_mismatch(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        key = (await _works(async_client, c))[0]["occurrence_key"]
        await _patch(async_client, c, key, "COMPLETED", "NOT_STARTED")
        resp = await async_client.post(c.url, headers=c.headers,
                                       json={**_body(c), "confirm_execution_detach_keys": [key]})
        assert _affected(resp) == []
        assert await _applications(db_session) == 0

    async def test_replace_without_protected_execution(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        key = (await _works(async_client, c))[0]["occurrence_key"]
        resp = await async_client.post(c.url, headers=c.headers, json=_body(c, "REPLACE", keys=[key], confirmed=True))
        assert resp.status_code == 200, resp.text

    @pytest.mark.parametrize("status", ["IN_PROGRESS", "COMPLETED"])
    async def test_replace_requires_exact_confirmation_and_records_once(self, async_client: AsyncClient, db_session, status):
        c = await _ctx(async_client, db_session)
        key = (await _works(async_client, c))[0]["occurrence_key"]
        await _patch(async_client, c, key, status, "NOT_STARTED")
        before = await _snapshot(async_client, c)
        app_id = uuid.uuid4()
        body = _body(c, "REPLACE", keys=[key], confirmed=True, app_id=app_id)

        first = await async_client.post(c.url, headers=c.headers, json=body)
        assert _affected(first) == [(key, status)]
        partial = await async_client.post(c.url, headers=c.headers,
                                          json={**body, "confirm_execution_detach_keys": [str(uuid.uuid4())]})
        assert _affected(partial) == [(key, status)]
        assert await _applications(db_session) == 0  # a failed check records nothing
        assert await _snapshot(async_client, c) == before

        confirmed = {**body, "confirm_execution_detach_keys": [key]}
        ok = await async_client.post(c.url, headers=c.headers, json=confirmed)  # same application_id
        assert ok.status_code == 200, ok.text
        works = ok.json()["planned_works"]
        assert key not in {w["occurrence_key"] for w in works}
        assert works and all(w["execution"]["status"] == "NOT_STARTED" for w in works)
        assert [(str(r.occurrence_key), r.status.value) for r in await _exec_rows(db_session)] == [(key, status)]
        assert await _applications(db_session) == 1

        retry = await async_client.post(c.url, headers=c.headers, json=confirmed)  # identical retry
        assert retry.status_code == 200 and retry.json()["planned_works"] == works
        assert await _applications(db_session) == 1
        # the same application_id with a different request is a conflict, never a second application
        changed = await async_client.post(c.url, headers=c.headers, json=body)
        assert changed.status_code == 409 and isinstance(changed.json()["detail"], str)
        assert await _applications(db_session) == 1

    async def test_fingerprint_unchanged_when_confirmation_not_sent(self):
        plan_id, template_id, step = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        request = ApplyTemplateRequest(application_id=uuid.uuid4(), template_id=template_id,
                                       mode=TemplateApplicationMode.APPEND, expected_step_ids=[step])
        pre_13h4 = {  # the exact 13E.3 payload
            "v": 1, "work_plan_id": str(plan_id), "template_id": str(template_id), "mode": "APPEND",
            "selected_optional_step_ids": [], "expected_step_ids": [str(step)],
            "expected_occurrence_keys": None, "replace_confirmed": None,
        }
        digest = hashlib.sha256(json.dumps(pre_13h4, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        assert _application_fingerprint(plan_id, request) == digest
        sent = request.model_copy(update={"confirm_execution_detach_keys": []})
        assert _application_fingerprint(plan_id, sent) != digest


# ---------------------------------------------------------------------------
# Apply to all walls
# ---------------------------------------------------------------------------


async def _walls(client, c, db, n=2):
    """Source wall = c.surface (X, completed); n target walls each with a plan."""
    svc = SurfaceWorkPlanService(db)
    targets = []
    for i in range(n):
        wall = await _make_surface(db, c.ids[1], name=f"Ściana {i}")
        plan = await svc.set_plan(c.ids[0], c.ids[1], wall.id, c.user.id, substrate=Substrate.CONCRETE,
                                  planned_works=[OrderedPriceItemSelection(price_item_id=c.p1.id),
                                                 OrderedPriceItemSelection(price_item_id=c.p2.id)])
        targets.append((wall.id, plan.id, [w.occurrence_key for w in plan.planned_works]))
    return targets


async def _apply_all(client, c, confirm=None):
    kwargs = {} if confirm is None else {"json": {"confirm_execution_detach_keys": [str(k) for k in confirm]}}
    return await client.post(f"{c.base}/apply-to-room-walls", headers=c.headers, **kwargs)


async def _move(db, c, wall_id, key, status):
    await SurfaceWorkExecutionService(db).transition(c.ids[0], c.ids[1], wall_id, c.user.id, key,
                                                     status=status, expected_status=S.NOT_STARTED)


class TestApplyToAll:
    async def test_not_started_targets_need_no_confirmation(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        src_key = (await _works(async_client, c))[0]["occurrence_key"]
        await _patch(async_client, c, src_key, "COMPLETED", "NOT_STARTED")
        await _walls(async_client, c, db_session)
        resp = await _apply_all(async_client, c)
        assert resp.status_code == 200, resp.text
        target_works = [w for t in resp.json()["targets"] for w in t["planned_works"]]
        assert target_works and all(w["execution"]["status"] == "NOT_STARTED" for w in target_works)
        assert src_key not in {w["occurrence_key"] for w in target_works}  # source never copied
        assert (await _works(async_client, c))[0]["execution"]["status"] == "COMPLETED"

    async def test_multiple_targets_aggregate_exact_keys(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        src_key = (await _works(async_client, c))[0]["occurrence_key"]
        await _patch(async_client, c, src_key, "COMPLETED", "NOT_STARTED")
        (w1, p1, k1), (w2, p2, k2) = await _walls(async_client, c, db_session)
        await _move(db_session, c, w1, k1[1], S.COMPLETED)
        await _move(db_session, c, w2, k2[0], S.IN_PROGRESS)
        expected = sorted([(str(p1), str(k1[1]), "COMPLETED", str(w1)), (str(p2), str(k2[0]), "IN_PROGRESS", str(w2))])

        resp = await _apply_all(async_client, c)
        assert resp.status_code == 409
        affected = resp.json()["detail"]["affected"]
        assert [(e["occurrence_key"], e["status"], e["surface_id"]) for e in affected] == [x[1:] for x in expected]
        assert _affected(await _apply_all(async_client, c, confirm=[k1[1]])) == [x[1:3] for x in expected]  # partial
        assert _affected(await _apply_all(async_client, c, confirm=[k1[1], k2[0], src_key])) == [x[1:3] for x in expected]
        assert len(await _exec_rows(db_session)) == 3  # nothing changed

        resp = await _apply_all(async_client, c, confirm=[k2[0], k1[1]])
        assert resp.status_code == 200, resp.text
        target_works = [w for t in resp.json()["targets"] for w in t["planned_works"]]
        assert all(w["execution"]["status"] == "NOT_STARTED" for w in target_works)
        assert not {w["occurrence_key"] for w in target_works} & {str(k) for k in k1 + k2}
        rows = {str(r.occurrence_key): r.status for r in await _exec_rows(db_session)}
        assert rows == {src_key: S.COMPLETED, str(k1[1]): S.COMPLETED, str(k2[0]): S.IN_PROGRESS}  # detached kept
        assert (await _works(async_client, c))[0]["execution"]["status"] == "COMPLETED"  # source unchanged

    async def test_invalid_body(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        await _walls(async_client, c, db_session, n=1)
        resp = await async_client.post(f"{c.base}/apply-to-room-walls", headers=c.headers,
                                       json={"confirm_execution_detach_keys": [], "force": True})
        assert resp.status_code == 422

    async def test_target_plans_locked_in_ascending_id_order(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        targets = await _walls(async_client, c, db_session, n=4)
        locked: list[uuid.UUID] = []

        def capture(state):
            stmt = state.statement
            if getattr(stmt, "_for_update_arg", None) is not None:
                params = stmt.compile().params
                locked.extend(v for v in params.values() if isinstance(v, uuid.UUID))

        event.listen(db_session.sync_session, "do_orm_execute", capture)
        try:
            await SurfaceWorkPlanService(db_session).apply_to_room_walls(c.ids[0], c.ids[1], c.ids[2], c.user.id)
        finally:
            event.remove(db_session.sync_session, "do_orm_execute", capture)
        plan_ids = [p for _, p, _ in targets]
        assert locked == sorted(plan_ids)
        assert set(locked) == set((await db_session.execute(
            select(SurfaceWorkPlan.id).where(SurfaceWorkPlan.id.in_(plan_ids)))).scalars().all())


# ---------------------------------------------------------------------------
# Recommendation acceptance (append-only)
# ---------------------------------------------------------------------------


class TestRecommendation:
    async def test_accept_needs_no_confirmation_and_keeps_execution(self, db_session):
        user, project, room, wall, plan, item, rec, service = await _setup_actionable(
            db_session, 9501, with_plan_codes=["EXISTING_13H4"])
        key = plan.planned_works[0].occurrence_key
        await SurfaceWorkExecutionService(db_session).transition(
            project.id, room.id, wall.id, user.id, key, status=S.COMPLETED, expected_status=S.NOT_STARTED)
        await service.accept_recommendation(project.id, rec.id, user.id)
        fetched = await SurfaceWorkPlanService(db_session).get_work_plan(project.id, room.id, wall.id, user.id)
        assert [(w.occurrence_key == key, w.execution.status) for w in fetched.planned_works] == [
            (True, S.COMPLETED), (False, S.NOT_STARTED)]
        rows = (await db_session.execute(select(SurfaceWorkExecution))).scalars().all()
        assert [(r.occurrence_key, r.status) for r in rows] == [(key, S.COMPLETED)]
