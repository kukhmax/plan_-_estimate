"""Stage 13H.5B.1 — bulk execution progress across the walls of one room.

Preview + atomic apply over ONE canonical engine: (PriceItem, k-th duplicate)
matching with the equal-count rule, forward-only transitions, server
timestamps per destination, exact ordered expected_source, scope (active
WALLs of the same room, never the source), and strict isolation of the
source, WorkPlan structure, waits, coefficients and the Estimate. Real row
locks are exercised by the PostgreSQL harness (SQLite has none).
"""
import uuid
from datetime import datetime, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text, update

import app.domain.services.work_execution_service as exec_module
from app.domain.services.estimate_service import EstimateService
from app.domain.services.work_execution_service import SurfaceWorkExecutionService
from app.domain.services.work_plan_service import SurfaceWorkPlanService
from app.models.checklist import QualityLevel, Substrate
from app.models.price_item import PriceCategory
from app.models.project import Project
from app.models.room import Room
from app.models.surface import Surface, SurfaceType
from app.models.work_execution import SurfaceWorkExecution, WorkExecutionStatus
from app.schemas.work_plan import OrderedPriceItemSelection as Sel
from tests.test_apply_template import _estimate_snapshot, _login
from tests.test_planned_work_coefficient_assignments import (
    _make_group_with_options,
    _make_price_item,
    _make_project,
    _make_room,
    _make_surface,
)
from tests.test_stage13h_execution_api import OTHER_USER

S = WorkExecutionStatus
NS, IP, C = S.NOT_STARTED, S.IN_PROGRESS, S.COMPLETED


class Ctx:
    pass


async def _ctx(client, db) -> Ctx:
    c = Ctx()
    c.db, c.client = db, client
    c.headers, user = await _login(client, db)
    c.user = user.id
    project = await _make_project(db, c.user)
    room = await _make_room(db, project.id)
    c.project, c.room = project.id, room.id
    c.items = [(await _make_price_item(db, c.user, category=PriceCategory.SKIM_COAT, price="10.00")).id for _ in range(5)]
    c.p1, c.p2, c.p3, c.p4, c.p5 = c.items
    c.plans = SurfaceWorkPlanService(db)
    c.exec = SurfaceWorkExecutionService(db)
    c.base = f"/api/projects/{c.project}/rooms/{c.room}/surfaces"
    return c


async def _wall(c, name, position, surface_type=SurfaceType.WALL, room=None):
    s = await _make_surface(c.db, room or c.room, surface_type, name=name)
    await c.db.execute(update(Surface).where(Surface.id == s.id).values(position=position))
    await c.db.commit()
    return s.id


async def _plan(c, surface_id, items, statuses=(), waits=None, coefficients=None, room=None):
    plan = await c.plans.set_plan(
        c.project, room or c.room, surface_id, c.user, substrate=Substrate.CONCRETE, quality_target=QualityLevel.S2,
        planned_works=[Sel(price_item_id=i, wait_after_hours=(waits or {}).get(n),
                           coefficient_option_ids=(coefficients or {}).get(n, [])) for n, i in enumerate(items)],
    )
    keys = [w.occurrence_key for w in plan.planned_works]
    for key, status in zip(keys, statuses):
        if status in (IP, C):
            await c.exec.transition(c.project, room or c.room, surface_id, c.user, key,
                                    status=status, expected_status=NS)
    return keys


async def _rows(db) -> dict:
    rows = (await db.execute(select(SurfaceWorkExecution).execution_options(populate_existing=True))).scalars().all()
    return {r.occurrence_key: (r.status, r.started_at, r.completed_at) for r in rows}


async def _structure(db):
    return (await db.execute(text(
        "SELECT w.occurrence_key, w.work_plan_id, w.price_item_id, w.position, w.wait_after_hours, p.substrate, p.quality_target"
        " FROM surface_planned_works w JOIN surface_work_plans p ON p.id = w.work_plan_id ORDER BY w.occurrence_key"))).all()


async def _coefficients(db):
    return (await db.execute(text(
        "SELECT w.occurrence_key, a.coefficient_option_id FROM surface_planned_work_coefficient_assignments a"
        " JOIN surface_planned_works w ON w.id = a.surface_planned_work_id ORDER BY 1, 2"))).all()


async def _preview(c, source):
    return await c.client.post(f"{c.base}/{source}/work-plan/execution/apply-to-room-walls-preview", headers=c.headers)


async def _apply(c, source, snapshot, headers=None):
    return await c.client.post(f"{c.base}/{source}/work-plan/execution/apply-to-room-walls",
                               headers=headers or c.headers, json={"expected_source": snapshot})


def _wall_counts(body, surface_id):
    w = next(w for w in body["walls"] if w["surface_id"] == str(surface_id))
    return (w["changed"], w["unchanged"], w["unmatched"], w["ambiguous"], w["has_plan"])


async def _status(c, key):
    return (await _rows(c.db)).get(key, (NS, None, None))


def _as_utc(value):
    return value if value is None or value.tzinfo else value.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Core semantics
# ---------------------------------------------------------------------------


class TestForwardOnly:
    async def test_multiple_walls_forward_transitions_and_counts(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        a, b, cc = await _wall(c, "A", 0), await _wall(c, "B", 1), await _wall(c, "C", 2)
        ka = await _plan(c, a, [c.p1, c.p2, c.p3, c.p4], [C, IP, NS, C])
        kb = await _plan(c, b, [c.p1, c.p2, c.p3, c.p4], [NS, NS, NS, IP])
        kc = await _plan(c, cc, [c.p1, c.p2, c.p3, c.p4], [IP, C, NS, C])
        before = await _rows(db_session)

        prev = await _preview(c, a)
        assert prev.status_code == 200, prev.text
        body = prev.json()
        assert body["applied"] is False
        assert body["expected_source"] == [{"occurrence_key": str(k), "status": s.value} for k, s in zip(ka, [C, IP, NS, C])]
        assert _wall_counts(body, b) == (3, 1, 0, 0, True)
        assert _wall_counts(body, cc) == (1, 3, 0, 0, True)
        assert (body["changed"], body["unchanged"], body["unmatched"], body["ambiguous"]) == (4, 4, 0, 0)
        assert await _rows(db_session) == before  # preview writes nothing

        t0 = datetime.now(timezone.utc)
        res = await _apply(c, a, body["expected_source"])
        assert res.status_code == 200, res.text
        applied = res.json()
        assert applied["applied"] is True
        assert {k: v for k, v in applied.items() if k != "applied"} == {k: v for k, v in body.items() if k != "applied"}
        rows = await _rows(db_session)

        # B: p1 NS->C (direct complete), p2 NS->IP, p3 untouched (source NS), p4 IP->C (own started_at kept)
        s1, st1, ct1 = rows[kb[0]]
        assert s1 == C and st1 == ct1 and _as_utc(st1) >= t0.replace(microsecond=0)
        assert st1 not in (before[ka[0]][1], before[ka[0]][2])  # never copied from the source
        assert rows[kb[1]][0] == IP and rows[kb[1]][2] is None and rows[kb[1]][1] not in (before[ka[1]][1],)
        assert kb[2] not in rows
        assert rows[kb[3]][0] == C and rows[kb[3]][1] == before[kb[3]][1] and rows[kb[3]][2] is not None
        # C: p1 IP->C; p2 already C vs source IP stays C (never backward); p4 equal
        assert rows[kc[0]][0] == C and rows[kc[0]][1] == before[kc[0]][1]
        assert rows[kc[1]] == before[kc[1]] and rows[kc[3]] == before[kc[3]]
        # source untouched; source keys only in the source's own rows
        assert {k: rows[k] for k in ka if k in rows} == {k: before[k] for k in ka if k in before}
        assert set(rows) - set(before) <= set(kb) | set(kc)
        # one server time for the whole operation
        assert rows[kb[0]][1] == rows[kb[1]][1] == rows[kc[0]][2]

    async def test_one_wall_and_idempotent_repeat(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        a, b = await _wall(c, "A", 0), await _wall(c, "B", 1)
        await _plan(c, a, [c.p1, c.p2], [C, NS])
        kb = await _plan(c, b, [c.p1, c.p2], [NS, IP])
        snap = (await _preview(c, a)).json()["expected_source"]
        first = (await _apply(c, a, snap)).json()
        assert _wall_counts(first, b) == (1, 1, 0, 0, True)
        rows = await _rows(db_session)
        assert rows[kb[1]][0] == IP  # source NS never resets
        again = (await _apply(c, a, snap)).json()
        assert _wall_counts(again, b) == (0, 2, 0, 0, True)
        assert await _rows(db_session) == rows


class TestMatching:
    async def test_duplicates_order_missing_extra_ambiguous(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        a = await _wall(c, "A", 0)
        b, cc, d, e = [await _wall(c, n, i) for i, n in enumerate("BCDE", start=1)]
        # source: p1 C, p2 C, p2 NS (duplicates), p3 IP
        await _plan(c, a, [c.p1, c.p2, c.p2, c.p3], [C, C, NS, IP])
        kb = await _plan(c, b, [c.p3, c.p2, c.p1, c.p2])                 # different order, equal duplicate count
        kc = await _plan(c, cc, [c.p1, c.p2, c.p2, c.p2])                # p2 count differs -> ambiguous; p3 missing
        kd = await _plan(c, d, [c.p1, c.p2, c.p2, c.p3, c.p5], [NS, NS, NS, NS, IP])  # extra p5 untouched
        # E: no plan
        body = (await _apply(c, a, (await _preview(c, a)).json()["expected_source"])).json()
        rows = await _rows(db_session)

        # B (by PriceItem + k-th duplicate by position): p3->IP, 1st p2 (pos 1)->C, p1->C, 2nd p2 (pos 3) stays NS
        assert (rows[kb[0]][0], rows[kb[1]][0], rows[kb[2]][0]) == (IP, C, C)
        assert kb[3] not in rows
        assert _wall_counts(body, b) == (3, 1, 0, 0, True)
        # C: p2 group ambiguous (3 vs 2) -> none of its 3 touched; p3 unmatched; p1 -> C
        assert rows[kc[0]][0] == C and not {kc[1], kc[2], kc[3]} & set(rows)
        assert _wall_counts(body, cc) == (1, 0, 1, 2, True)
        wall_c = next(w for w in body["walls"] if w["surface_id"] == str(cc))
        assert wall_c["ambiguous_price_item_ids"] == [str(c.p2)] and wall_c["unmatched_price_item_ids"] == [str(c.p3)]
        # D: all matched, extra p5 (IN_PROGRESS) unchanged
        assert rows[kd[4]][0] == IP and _wall_counts(body, d) == (3, 1, 0, 0, True)
        # E: no plan -> every source occurrence unmatched
        assert _wall_counts(body, e) == (0, 0, 4, 0, False)
        # no double counting: every wall accounts for each source occurrence exactly once
        for w in body["walls"]:
            assert w["changed"] + w["unchanged"] + w["unmatched"] + w["ambiguous"] == 4
        assert body["changed"] == sum(w["changed"] for w in body["walls"])


class TestScope:
    async def test_only_active_walls_of_the_same_room(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        a, b = await _wall(c, "A", 0), await _wall(c, "B", 1)
        archived = await _wall(c, "Arch", 2)
        floor = await _wall(c, "Podłoga", 3, SurfaceType.FLOOR)
        ceiling = await _wall(c, "Sufit", 4, SurfaceType.CEILING)
        other = await _wall(c, "Inne", 5, SurfaceType.OTHER)
        other_room = (await _make_room(db_session, c.project)).id
        far = await _wall(c, "Daleka", 0, room=other_room)
        await _plan(c, a, [c.p1], [C])
        await _plan(c, b, [c.p1])
        keys = {sid: await _plan(c, sid, [c.p1]) for sid in (archived, floor, ceiling, other)}
        keys[far] = await _plan(c, far, [c.p1], room=other_room)
        await db_session.execute(update(Surface).where(Surface.id == archived).values(is_archived=True))
        await db_session.commit()

        body = (await _apply(c, a, (await _preview(c, a)).json()["expected_source"])).json()
        assert [w["surface_id"] for w in body["walls"]] == [str(b)]
        rows = await _rows(db_session)
        assert not {k for ks in keys.values() for k in ks} & set(rows)

    async def test_non_wall_source_and_archived_source_are_422(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        a, b = await _wall(c, "A", 0), await _wall(c, "B", 1)
        floor = await _wall(c, "Podłoga", 2, SurfaceType.FLOOR)
        await _plan(c, a, [c.p1], [C])
        await _plan(c, b, [c.p1])
        await _plan(c, floor, [c.p1], [C])
        assert (await _preview(c, floor)).status_code == 422
        assert (await _apply(c, floor, [])).status_code == 422
        snap = (await _preview(c, a)).json()["expected_source"]
        before = await _rows(db_session)
        for model, ident in ((Surface, a), (Room, c.room), (Project, c.project)):
            await db_session.execute(update(model).where(model.id == ident).values(is_archived=True))
            await db_session.commit()
            assert (await _preview(c, a)).status_code == 422
            assert (await _apply(c, a, snap)).status_code == 422
            await db_session.execute(update(model).where(model.id == ident).values(is_archived=False))
            await db_session.commit()
        assert await _rows(db_session) == before  # refused applies wrote nothing
        assert (await _apply(c, a, snap)).status_code == 200

    async def test_other_user_cannot_reach_or_be_reached(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        a, b = await _wall(c, "A", 0), await _wall(c, "B", 1)
        await _plan(c, a, [c.p1], [C])
        kb = await _plan(c, b, [c.p1])
        snap = (await _preview(c, a)).json()["expected_source"]
        stranger_headers, _ = await _login(async_client, db_session, OTHER_USER)
        assert (await async_client.post(f"{c.base}/{a}/work-plan/execution/apply-to-room-walls-preview",
                                        headers=stranger_headers)).status_code == 404
        assert (await _apply(c, a, snap, headers=stranger_headers)).status_code == 404
        assert kb[0] not in await _rows(db_session)


# ---------------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------------


class TestIsolation:
    async def test_source_structure_waits_coefficients_estimate_untouched(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        _, opts = await _make_group_with_options(db_session, c.user, percentages=["0", "15"])
        a, b = await _wall(c, "A", 0), await _wall(c, "B", 1)
        ka = await _plan(c, a, [c.p1, c.p2], [C, IP], waits={0: 24}, coefficients={1: [opts[1].id]})
        await _plan(c, b, [c.p1, c.p2], waits={0: 4}, coefficients={0: [opts[1].id]})
        await EstimateService(db_session).generate_estimate(c.project, c.user)
        structure, coefs, estimate = await _structure(db_session), await _coefficients(db_session), await _estimate_snapshot(db_session)
        history = (await db_session.execute(text("SELECT * FROM surface_work_plan_template_applications"))).all()
        source_rows = {k: v for k, v in (await _rows(db_session)).items() if k in ka}

        body = (await _apply(c, a, (await _preview(c, a)).json()["expected_source"])).json()
        assert body["changed"] == 2
        assert await _structure(db_session) == structure          # keys, positions, PriceItems, waits, substrate, quality
        assert await _coefficients(db_session) == coefs
        assert await _estimate_snapshot(db_session) == estimate
        assert (await db_session.execute(text("SELECT * FROM surface_work_plan_template_applications"))).all() == history
        assert {k: v for k, v in (await _rows(db_session)).items() if k in ka} == source_rows


# ---------------------------------------------------------------------------
# expected_source contract
# ---------------------------------------------------------------------------


class TestExpectedSource:
    async def _setup(self, client, db):
        c = await _ctx(client, db)
        c.a, c.b = await _wall(c, "A", 0), await _wall(c, "B", 1)
        c.ka = await _plan(c, c.a, [c.p1, c.p2, c.p3], [C, NS, NS])
        c.kb = await _plan(c, c.b, [c.p1, c.p2, c.p3])
        c.snap = (await _preview(c, c.a)).json()["expected_source"]
        return c

    async def _assert_409_nothing_applied(self, c, snap):
        before = await _rows(c.db)
        res = await _apply(c, c.a, snap)
        assert res.status_code == 409, res.text
        detail = res.json()["detail"]
        assert detail["code"] == "WORK_EXECUTION_SOURCE_CHANGED"
        assert await _rows(c.db) == before
        assert not set(c.kb) & set(await _rows(c.db))
        return detail

    async def test_status_changed_after_preview(self, async_client: AsyncClient, db_session):
        c = await self._setup(async_client, db_session)
        await c.exec.transition(c.project, c.room, c.a, c.user, c.ka[1], status=IP, expected_status=NS)
        detail = await self._assert_409_nothing_applied(c, c.snap)
        assert detail["current_source"][1] == {"occurrence_key": str(c.ka[1]), "status": "IN_PROGRESS"}

    async def test_reorder_after_preview(self, async_client: AsyncClient, db_session):
        c = await self._setup(async_client, db_session)
        await c.plans.set_plan(c.project, c.room, c.a, c.user, substrate=Substrate.CONCRETE, quality_target=QualityLevel.S2,
                               planned_works=[Sel(price_item_id=c.p2, occurrence_key=c.ka[1]),
                                              Sel(price_item_id=c.p1, occurrence_key=c.ka[0]),
                                              Sel(price_item_id=c.p3, occurrence_key=c.ka[2])])
        await self._assert_409_nothing_applied(c, c.snap)

    async def test_occurrence_set_changed_after_preview(self, async_client: AsyncClient, db_session):
        c = await self._setup(async_client, db_session)
        await c.plans.set_plan(c.project, c.room, c.a, c.user, substrate=Substrate.CONCRETE, quality_target=QualityLevel.S2,
                               planned_works=[Sel(price_item_id=c.p1, occurrence_key=c.ka[0]),
                                              Sel(price_item_id=c.p2, occurrence_key=c.ka[1])])
        await self._assert_409_nothing_applied(c, c.snap)
        await self._assert_409_nothing_applied(c, c.snap[:2] + [{"occurrence_key": str(uuid.uuid4()), "status": "NOT_STARTED"}])

    async def test_exact_snapshot_required_even_without_structure_change(self, async_client: AsyncClient, db_session):
        c = await self._setup(async_client, db_session)
        await self._assert_409_nothing_applied(c, c.snap[:2])                     # missing NOT_STARTED item
        await self._assert_409_nothing_applied(c, [c.snap[1], c.snap[0], c.snap[2]])  # order
        await self._assert_409_nothing_applied(c, [{**c.snap[0], "status": "IN_PROGRESS"}, *c.snap[1:]])
        assert (await _apply(c, c.a, c.snap)).status_code == 200

    @pytest.mark.parametrize("body", [
        {},
        {"expected_source": [{"occurrence_key": "not-a-uuid", "status": "COMPLETED"}]},
        {"expected_source": [{"occurrence_key": str(uuid.uuid4())}]},
        {"expected_source": [{"occurrence_key": str(uuid.uuid4()), "status": "DONE"}]},
        {"expected_source": [{"occurrence_key": str(uuid.uuid4()), "status": "COMPLETED", "started_at": "2026-01-01T00:00:00Z"}]},
        {"expected_source": [], "force": True},
    ])
    async def test_malformed_body_is_422(self, async_client: AsyncClient, db_session, body):
        c = await self._setup(async_client, db_session)
        res = await async_client.post(f"{c.base}/{c.a}/work-plan/execution/apply-to-room-walls", headers=c.headers, json=body)
        assert res.status_code == 422

    async def test_duplicate_key_is_422(self, async_client: AsyncClient, db_session):
        c = await self._setup(async_client, db_session)
        assert (await _apply(c, c.a, [c.snap[0], c.snap[0], c.snap[1]])).status_code == 422


# ---------------------------------------------------------------------------
# Engine, atomicity, locking
# ---------------------------------------------------------------------------


class TestEngineAndAtomicity:
    async def test_preview_and_apply_share_the_engine(self, async_client: AsyncClient, db_session, monkeypatch):
        c = await _ctx(async_client, db_session)
        a, b = await _wall(c, "A", 0), await _wall(c, "B", 1)
        await _plan(c, a, [c.p1, c.p2], [C, IP])
        await _plan(c, b, [c.p1, c.p2])
        calls = []
        original = exec_module.calculate_bulk_execution_plan

        def spy(*args, **kwargs):
            calls.append(args)
            return original(*args, **kwargs)

        monkeypatch.setattr(exec_module, "calculate_bulk_execution_plan", spy)
        prev = (await _preview(c, a)).json()
        res = (await _apply(c, a, prev["expected_source"])).json()
        assert len(calls) == 2 and calls[0] == calls[1]  # same inputs -> same engine
        assert res["changed"] == prev["changed"] == 2

    async def test_all_or_nothing(self, async_client: AsyncClient, db_session, monkeypatch):
        c = await _ctx(async_client, db_session)
        a, b, cc = await _wall(c, "A", 0), await _wall(c, "B", 1), await _wall(c, "C", 2)
        await _plan(c, a, [c.p1, c.p2], [C, C])
        await _plan(c, b, [c.p1, c.p2])
        await _plan(c, cc, [c.p1, c.p2])
        snap = (await _preview(c, a)).json()["expected_source"]
        before = await _rows(db_session)
        original, count = exec_module._apply_transition, {"n": 0}

        def failing(*args):
            count["n"] += 1
            if count["n"] == 3:
                raise RuntimeError("simulated failure mid-apply")
            return original(*args)

        monkeypatch.setattr(exec_module, "_apply_transition", failing)
        with pytest.raises(RuntimeError):
            await c.exec.apply_room_walls(c.project, c.room, a, c.user,
                                          [(uuid.UUID(i["occurrence_key"]), S(i["status"])) for i in snap])
        await db_session.rollback()
        assert await _rows(db_session) == before

    async def test_plans_locked_in_ascending_id_order_including_source(self, async_client: AsyncClient, db_session):
        from sqlalchemy import event
        from app.models.work_plan import SurfaceWorkPlan
        c = await _ctx(async_client, db_session)
        walls = [await _wall(c, n, i) for i, n in enumerate("ABCDE")]
        for w in walls:
            await _plan(c, w, [c.p1], [C] if w == walls[2] else [])
        snap = (await _preview(c, walls[2])).json()["expected_source"]
        locked = []

        def capture(state):
            if getattr(state.statement, "_for_update_arg", None) is not None:
                locked.extend(v for v in state.statement.compile().params.values() if isinstance(v, uuid.UUID))

        event.listen(db_session.sync_session, "do_orm_execute", capture)
        try:
            await c.exec.apply_room_walls(c.project, c.room, walls[2], c.user,
                                          [(uuid.UUID(i["occurrence_key"]), S(i["status"])) for i in snap])
        finally:
            event.remove(db_session.sync_session, "do_orm_execute", capture)
        plan_ids = (await db_session.execute(select(SurfaceWorkPlan.id))).scalars().all()
        assert locked == sorted(plan_ids) and len(locked) == 5
