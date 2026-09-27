"""Stage 13H.3 — execution API and read contract.

Read: every CURRENT planned work carries a read-only `execution` object
(absent row = NOT_STARTED, no row created; derived ready_after; detached
records omitted) on every WorkPlan response. Write: only the dedicated
PATCH .../work-plan/occurrences/{occurrence_key}/execution endpoint, with
optimistic `expected_status`; the ordinary WorkPlan save cannot carry
execution state. Plus non-leaking keys, archive, and commercial isolation.
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text, update

from app.domain.services.estimate_service import EstimateService
from app.domain.services.work_plan_service import SurfaceWorkPlanService
from app.models.checklist import Substrate
from app.models.project import Project
from app.models.room import Room
from app.models.surface import Surface
from app.models.work_execution import SurfaceWorkExecution
from app.schemas.work_plan import OrderedPriceItemSelection, SurfaceWorkPlanRead
from tests.test_apply_template import _body, _estimate_snapshot, _login
from tests.test_apply_template import _setup as _setup_priced
from tests.test_planned_work_coefficient_assignments import (
    _make_price_item,
    _make_project,
    _make_room,
    _make_surface,
)
from tests.test_stage13g_waits import _priced
from tests.test_work_recommendation_accept import _setup_actionable

NOT_STARTED = {"status": "NOT_STARTED", "started_at": None, "completed_at": None, "ready_after": None}
OTHER_USER = {"id": 322222222, "username": "stranger13h", "first_name": "Obcy", "last_name": "User", "language_code": "pl"}


async def _ctx(client, db):
    c = await _setup_priced(client, db)  # existing plan: item X, wait 6 h, coefficient opts[1]
    c.ids = (c.project.id, c.room.id, c.surface.id)
    c.base = f"/api/projects/{c.project.id}/rooms/{c.room.id}/surfaces/{c.surface.id}/work-plan"
    return c


def _url(c, key, surface_id=None) -> str:
    base = c.base if surface_id is None else c.base.replace(str(c.ids[2]), str(surface_id))
    return f"{base}/occurrences/{key}/execution"


async def _patch(client, c, key, status, expected, surface_id=None, headers=None):
    return await client.patch(
        _url(c, key, surface_id), headers=headers or c.headers,
        json={"status": status, "expected_status": expected},
    )


async def _works(client, c) -> list[dict]:
    resp = await client.get(c.base, headers=c.headers)
    assert resp.status_code == 200, resp.text
    return resp.json()["planned_works"]


async def _put(client, c, rows, confirm=()) -> list[dict]:
    """rows = [(price_item_id, occurrence_key|None, wait)] -- ordinary save;
    `confirm` = exact execution-detach confirmation (13H.4)."""
    resp = await client.put(c.base, headers=c.headers, json={
        "substrate": "CONCRETE", "quality_target": "S2",
        "confirm_execution_detach_keys": [str(k) for k in confirm],
        "planned_works": [
            {"price_item_id": str(item), "occurrence_key": str(key) if key else None, "wait_after_hours": wait}
            for item, key, wait in rows
        ],
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["planned_works"]


async def _exec_rows(db) -> list[SurfaceWorkExecution]:
    return list((await db.execute(
        select(SurfaceWorkExecution).execution_options(populate_existing=True)
    )).scalars().all())


def _dt(value: str | None) -> datetime | None:
    """Parse an API timestamp as UTC. SQLite (tests only) drops the offset of
    stored values; PostgreSQL returns them UTC-aware (same convention as
    test_market_evidence)."""
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# READ
# ---------------------------------------------------------------------------


class TestRead:
    async def test_no_row_serializes_not_started_without_creating_rows(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        works = await _works(async_client, c)
        assert [w["execution"] for w in works] == [NOT_STARTED]
        assert await _exec_rows(db_session) == []

    async def test_in_progress_and_completed_serialization_and_ready_after(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        works = await _put(async_client, c, [(c.x.id, (await _works(async_client, c))[0]["occurrence_key"], 6),
                                             (c.p1.id, None, None), (c.p2.id, None, 24)])
        k_x, k_p1, k_p2 = (w["occurrence_key"] for w in works)
        await _patch(async_client, c, k_x, "COMPLETED", "NOT_STARTED")
        await _patch(async_client, c, k_p1, "COMPLETED", "NOT_STARTED")
        await _patch(async_client, c, k_p2, "IN_PROGRESS", "NOT_STARTED")
        e_x, e_p1, e_p2 = (w["execution"] for w in await _works(async_client, c))

        assert e_p2["status"] == "IN_PROGRESS" and e_p2["completed_at"] is None
        assert _dt(e_p2["started_at"]) and e_p2["ready_after"] is None  # break, but not completed
        assert e_x["status"] == "COMPLETED"
        assert _dt(e_x["ready_after"]) - _dt(e_x["completed_at"]) == timedelta(hours=6)
        assert e_p1["status"] == "COMPLETED" and e_p1["ready_after"] is None  # completed, no break

        # a later wait edit moves ready_after; the recorded timestamps stay
        works = await _put(async_client, c, [(c.x.id, k_x, 48), (c.p1.id, k_p1, None), (c.p2.id, k_p2, 24)])
        assert (_dt(works[0]["execution"]["started_at"]), _dt(works[0]["execution"]["completed_at"])) == (
            _dt(e_x["started_at"]), _dt(e_x["completed_at"]))
        assert _dt(works[0]["execution"]["ready_after"]) - _dt(e_x["completed_at"]) == timedelta(hours=48)

    async def test_duplicate_price_items_are_independent(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        works = await _put(async_client, c, [(c.p2.id, None, None), (c.p2.id, None, None)])
        resp = await _patch(async_client, c, works[1]["occurrence_key"], "IN_PROGRESS", "NOT_STARTED")
        assert resp.status_code == 200
        assert [w["execution"]["status"] for w in await _works(async_client, c)] == ["NOT_STARTED", "IN_PROGRESS"]

    async def test_detached_execution_is_omitted_and_kept(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        works = await _put(async_client, c, [(c.x.id, (await _works(async_client, c))[0]["occurrence_key"], 6),
                                             (c.p1.id, None, None)])
        removed = works[0]["occurrence_key"]
        await _patch(async_client, c, removed, "COMPLETED", "NOT_STARTED")
        after = await _put(async_client, c, [(c.p1.id, works[1]["occurrence_key"], None)], confirm=[removed])
        assert [w["occurrence_key"] for w in after] == [works[1]["occurrence_key"]]
        assert [w["execution"] for w in after] == [NOT_STARTED]
        rows = await _exec_rows(db_session)
        assert [(str(r.occurrence_key), r.status.value) for r in rows] == [(removed, "COMPLETED")]

    async def test_append_keeps_existing_and_new_read_not_started(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        key = (await _works(async_client, c))[0]["occurrence_key"]
        await _patch(async_client, c, key, "COMPLETED", "NOT_STARTED")
        resp = await async_client.post(c.url, headers=c.headers, json=_body(c))
        assert resp.status_code == 200, resp.text
        works = resp.json()["planned_works"]
        assert works[0]["occurrence_key"] == key and works[0]["execution"]["status"] == "COMPLETED"
        assert len(works) > 1 and all(w["execution"] == NOT_STARTED for w in works[1:])

    async def test_replace_new_occurrences_not_started_and_detached_hidden(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        key = (await _works(async_client, c))[0]["occurrence_key"]
        await _patch(async_client, c, key, "COMPLETED", "NOT_STARTED")
        resp = await async_client.post(c.url, headers=c.headers, json={
            **_body(c, "REPLACE", keys=[key], confirmed=True), "confirm_execution_detach_keys": [key]})
        assert resp.status_code == 200, resp.text
        works = resp.json()["planned_works"]
        assert key not in {w["occurrence_key"] for w in works}
        assert works and all(w["execution"] == NOT_STARTED for w in works)
        assert [str(r.occurrence_key) for r in await _exec_rows(db_session)] == [key]  # history kept

    async def test_apply_to_all_reads_not_started_and_never_copies(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        await _make_surface(db_session, c.ids[1], name="Ściana B")
        key = (await _works(async_client, c))[0]["occurrence_key"]
        await _patch(async_client, c, key, "COMPLETED", "NOT_STARTED")
        resp = await async_client.post(f"{c.base}/apply-to-room-walls", headers=c.headers)
        assert resp.status_code == 200, resp.text
        target_works = [w for t in resp.json()["targets"] for w in t["planned_works"]]
        assert target_works and all(w["execution"] == NOT_STARTED for w in target_works)
        assert key not in {w["occurrence_key"] for w in target_works}
        assert (await _works(async_client, c))[0]["execution"]["status"] == "COMPLETED"
        assert len(await _exec_rows(db_session)) == 1

    async def test_recommendation_occurrence_reads_not_started(self, db_session):
        user, project, room, wall, plan, item, rec, service = await _setup_actionable(db_session, 9401)
        await service.accept_recommendation(project.id, rec.id, user.id)
        fetched = await SurfaceWorkPlanService(db_session).get_work_plan(project.id, room.id, wall.id, user.id)
        read = SurfaceWorkPlanRead.model_validate(fetched).model_dump(mode="json")
        assert [w["execution"] for w in read["planned_works"]] == [NOT_STARTED]
        assert await _exec_rows(db_session) == []


# ---------------------------------------------------------------------------
# MUTATION
# ---------------------------------------------------------------------------


class TestMutation:
    async def test_transitions_and_shortcut(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        works = await _put(async_client, c, [(c.p1.id, None, None), (c.p2.id, None, None)])
        k1, k2 = works[0]["occurrence_key"], works[1]["occurrence_key"]

        r = await _patch(async_client, c, k1, "IN_PROGRESS", "NOT_STARTED")
        assert r.status_code == 200, r.text
        started = r.json()
        assert started["occurrence_key"] == k1 and started["status"] == "IN_PROGRESS"
        assert started["started_at"] and started["completed_at"] is None and started["ready_after"] is None

        done = (await _patch(async_client, c, k1, "COMPLETED", "IN_PROGRESS")).json()
        assert done["status"] == "COMPLETED" and _dt(done["started_at"]) == _dt(started["started_at"])
        assert _dt(done["completed_at"]) >= _dt(done["started_at"])

        reopened = (await _patch(async_client, c, k1, "IN_PROGRESS", "COMPLETED")).json()
        assert (reopened["status"], _dt(reopened["started_at"]), reopened["completed_at"]) == (
            "IN_PROGRESS", _dt(started["started_at"]), None)

        reset = (await _patch(async_client, c, k1, "NOT_STARTED", "IN_PROGRESS")).json()
        assert {k: reset[k] for k in NOT_STARTED} == NOT_STARTED

        shortcut = (await _patch(async_client, c, k2, "COMPLETED", "NOT_STARTED")).json()
        assert shortcut["status"] == "COMPLETED" and shortcut["started_at"] == shortcut["completed_at"]
        assert shortcut["started_at"] is not None

    async def test_same_state_is_idempotent(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        key = (await _works(async_client, c))[0]["occurrence_key"]
        first = (await _patch(async_client, c, key, "COMPLETED", "NOT_STARTED")).json()
        for expected in ("IN_PROGRESS", "NOT_STARTED", "COMPLETED"):
            again = await _patch(async_client, c, key, "COMPLETED", expected)
            assert again.status_code == 200
            got = again.json()
            assert (got["status"], _dt(got["started_at"]), _dt(got["completed_at"])) == (
                first["status"], _dt(first["started_at"]), _dt(first["completed_at"]))
        assert _dt((await _works(async_client, c))[0]["execution"]["completed_at"]) == _dt(first["completed_at"])
        # NOT_STARTED -> NOT_STARTED on a fresh occurrence creates no row
        works = await _put(async_client, c, [(c.x.id, key, 6), (c.p1.id, None, None)])
        assert (await _patch(async_client, c, works[1]["occurrence_key"], "NOT_STARTED", "NOT_STARTED")).status_code == 200
        assert len(await _exec_rows(db_session)) == 1

    async def test_stale_expected_status_is_409_with_current_status(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        key = (await _works(async_client, c))[0]["occurrence_key"]
        done = (await _patch(async_client, c, key, "COMPLETED", "NOT_STARTED")).json()  # session A
        resp = await _patch(async_client, c, key, "IN_PROGRESS", "NOT_STARTED")  # stale session B
        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert detail["code"] == "WORK_EXECUTION_CONFLICT" and detail["current_status"] == "COMPLETED"
        assert _dt((await _works(async_client, c))[0]["execution"]["completed_at"]) == _dt(done["completed_at"])

    async def test_invalid_transition_is_409(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        key = (await _works(async_client, c))[0]["occurrence_key"]
        await _patch(async_client, c, key, "COMPLETED", "NOT_STARTED")
        resp = await _patch(async_client, c, key, "NOT_STARTED", "COMPLETED")  # must reopen first
        assert resp.status_code == 409
        assert resp.json()["detail"] == {
            "code": "WORK_EXECUTION_CONFLICT", "current_status": "COMPLETED",
            "message": resp.json()["detail"]["message"],
        }
        assert (await _works(async_client, c))[0]["execution"]["status"] == "COMPLETED"

    @pytest.mark.parametrize("body", [
        {"status": "DONE", "expected_status": "NOT_STARTED"},
        {"status": "IN_PROGRESS", "expected_status": "planned"},
        {"status": "IN_PROGRESS"},  # expected_status is mandatory
        {"expected_status": "NOT_STARTED"},
    ])
    async def test_invalid_body_is_422(self, async_client: AsyncClient, db_session, body):
        c = await _ctx(async_client, db_session)
        key = (await _works(async_client, c))[0]["occurrence_key"]
        resp = await async_client.patch(_url(c, key), headers=c.headers, json=body)
        assert resp.status_code == 422
        assert await _exec_rows(db_session) == []

    async def test_non_current_keys_are_non_leaking(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        works = await _put(async_client, c, [(c.x.id, (await _works(async_client, c))[0]["occurrence_key"], 6),
                                             (c.p1.id, None, None)])
        removed = works[1]["occurrence_key"]
        await _patch(async_client, c, removed, "IN_PROGRESS", "NOT_STARTED")  # then removed with history
        await _put(async_client, c, [(c.x.id, works[0]["occurrence_key"], 6)], confirm=[removed])

        other_wall = await _make_surface(db_session, c.ids[1], name="Ściana 2")
        other_plan = await SurfaceWorkPlanService(db_session).set_plan(
            c.ids[0], c.ids[1], other_wall.id, c.user.id, substrate=Substrate.CONCRETE,
            planned_works=[OrderedPriceItemSelection(price_item_id=c.p1.id)])
        other_surface_key = other_plan.planned_works[0].occurrence_key

        _, stranger = await _login(async_client, db_session, OTHER_USER)
        s_project = await _make_project(db_session, stranger.id)
        s_room = await _make_room(db_session, s_project.id)
        s_surface = await _make_surface(db_session, s_room.id)
        s_item = await _make_price_item(db_session, stranger.id)
        s_plan = await SurfaceWorkPlanService(db_session).set_plan(
            s_project.id, s_room.id, s_surface.id, stranger.id, substrate=Substrate.CONCRETE,
            planned_works=[OrderedPriceItemSelection(price_item_id=s_item.id)])
        stranger_key = s_plan.planned_works[0].occurrence_key
        await SurfaceWorkPlanService(db_session).get_work_plan(s_project.id, s_room.id, s_surface.id, stranger.id)
        rows_before = [(r.occurrence_key, r.status, r.started_at, r.completed_at) for r in await _exec_rows(db_session)]

        details = set()
        for key, surface_id in [
            (uuid.uuid4(), None),               # invented
            (removed, None),                    # removed (has detached history)
            (other_surface_key, None),          # another surface / WorkPlan of the same owner
            (stranger_key, None),               # another user's project
            (works[0]["occurrence_key"], other_wall.id),  # current key sent via the wrong surface
        ]:
            resp = await _patch(async_client, c, key, "COMPLETED", "IN_PROGRESS", surface_id=surface_id)
            assert resp.status_code == 409, resp.text
            detail = resp.json()["detail"]
            assert isinstance(detail, str) and "current_status" not in resp.text
            details.add(detail.replace(str(key), "<key>"))
        assert len(details) == 1  # indistinguishable
        after = [(r.occurrence_key, r.status, r.started_at, r.completed_at) for r in await _exec_rows(db_session)]
        assert after == rows_before

        # the stranger cannot even reach the owner's surface (existing 404 chain)
        stranger_headers, _ = await _login(async_client, db_session, OTHER_USER)
        resp = await _patch(async_client, c, works[0]["occurrence_key"], "COMPLETED", "NOT_STARTED",
                            headers=stranger_headers)
        assert resp.status_code == 404

    @pytest.mark.parametrize("target", ["surface", "room", "project"])
    async def test_archived_hierarchy_rejects_mutation_restore_preserves(self, async_client: AsyncClient, db_session, target):
        c = await _ctx(async_client, db_session)
        key = (await _works(async_client, c))[0]["occurrence_key"]
        started = (await _patch(async_client, c, key, "IN_PROGRESS", "NOT_STARTED")).json()
        model, ident = {"surface": (Surface, c.ids[2]), "room": (Room, c.ids[1]), "project": (Project, c.ids[0])}[target]
        await db_session.execute(update(model).where(model.id == ident).values(is_archived=True))
        await db_session.commit()

        resp = await _patch(async_client, c, key, "COMPLETED", "IN_PROGRESS")
        assert resp.status_code == 422
        read = await async_client.get(c.base, headers=c.headers)  # reads stay available
        assert read.status_code == 200
        assert read.json()["planned_works"][0]["execution"]["status"] == "IN_PROGRESS"

        await db_session.execute(update(model).where(model.id == ident).values(is_archived=False))
        await db_session.commit()
        execution = (await _works(async_client, c))[0]["execution"]
        assert (execution["status"], _dt(execution["started_at"])) == ("IN_PROGRESS", _dt(started["started_at"]))
        assert (await _patch(async_client, c, key, "COMPLETED", "IN_PROGRESS")).status_code == 200


# ---------------------------------------------------------------------------
# WRITE SAFETY
# ---------------------------------------------------------------------------


class TestWriteSafety:
    @pytest.mark.parametrize("smuggled", [
        {"execution": {"status": "COMPLETED", "started_at": "2026-09-27T10:00:00Z",
                       "completed_at": "2026-09-27T11:00:00Z", "ready_after": "2026-09-27T15:00:00Z"}},
        {"status": "COMPLETED"},
        {"started_at": "2026-09-27T10:00:00Z"},
        {"completed_at": "2026-09-27T11:00:00Z"},
        {"ready_after": "2026-09-27T15:00:00Z"},
    ])
    async def test_workplan_save_cannot_write_execution(self, async_client: AsyncClient, db_session, smuggled):
        c = await _ctx(async_client, db_session)
        before = await async_client.get(c.base, headers=c.headers)
        work = before.json()["planned_works"][0]
        entry = {"price_item_id": work["price_item_id"], "occurrence_key": work["occurrence_key"],
                 "wait_after_hours": work["wait_after_hours"], **smuggled}
        per_work = await async_client.put(c.base, headers=c.headers, json={
            "substrate": "CONCRETE", "quality_target": "S2", "planned_works": [entry]})
        top_level = await async_client.put(c.base, headers=c.headers, json={
            "substrate": "CONCRETE", "quality_target": "S2", **smuggled,
            "planned_works": [{k: entry[k] for k in ("price_item_id", "occurrence_key", "wait_after_hours")}]})
        assert (per_work.status_code, top_level.status_code) == (422, 422)
        assert (await async_client.get(c.base, headers=c.headers)).json() == before.json()
        assert await _exec_rows(db_session) == []

    async def test_echoing_the_read_response_is_rejected(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        work = (await _works(async_client, c))[0]
        resp = await async_client.put(c.base, headers=c.headers, json={
            "substrate": "CONCRETE", "quality_target": "S2", "planned_works": [work]})
        assert resp.status_code == 422

    @pytest.mark.parametrize("extra", [
        {"started_at": "2020-01-01T00:00:00Z"},
        {"completed_at": "2020-01-01T00:00:00Z"},
        {"ready_after": "2020-01-01T00:00:00Z"},
        {"occurrence_key": str(uuid.uuid4())},
    ])
    async def test_execution_endpoint_rejects_client_timestamps(self, async_client: AsyncClient, db_session, extra):
        c = await _ctx(async_client, db_session)
        key = (await _works(async_client, c))[0]["occurrence_key"]
        resp = await async_client.patch(_url(c, key), headers=c.headers,
                                        json={"status": "COMPLETED", "expected_status": "NOT_STARTED", **extra})
        assert resp.status_code == 422
        assert await _exec_rows(db_session) == []


# ---------------------------------------------------------------------------
# ISOLATION
# ---------------------------------------------------------------------------


class TestIsolation:
    async def test_execution_changes_nothing_commercial_or_planning(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        first = (await _works(async_client, c))[0]
        await _put(async_client, c, [(c.x.id, first["occurrence_key"], 6), (c.p1.id, None, 24)])
        # re-apply the coefficient kept on X (ordinary save above carried none)
        works = (await async_client.put(c.base, headers=c.headers, json={
            "substrate": "CONCRETE", "quality_target": "S2", "planned_works": [
                {"price_item_id": str(c.x.id), "occurrence_key": first["occurrence_key"], "wait_after_hours": 6,
                 "coefficient_option_ids": [str(c.opts[1].id)]},
                {"price_item_id": str(c.p1.id), "occurrence_key": (await _works(async_client, c))[1]["occurrence_key"],
                 "wait_after_hours": 24},
            ]})).json()["planned_works"]
        estimates = EstimateService(db_session)
        estimate = await estimates.generate_estimate(c.ids[0], c.user.id)
        lines, priced = await _estimate_snapshot(db_session), await _priced(db_session)
        items = (await db_session.execute(text("SELECT * FROM price_items ORDER BY id"))).all()
        coefs = (await db_session.execute(text(
            "SELECT * FROM surface_planned_work_coefficient_assignments ORDER BY coefficient_option_id"))).all()

        def planning(ws):
            return [(w["occurrence_key"], w["position"], w["price_item_id"], w["wait_after_hours"],
                     [o["id"] for o in w["coefficient_options"]]) for w in ws]

        plan_before = planning(works)
        for key in (w["occurrence_key"] for w in works):
            for status, expected in (("IN_PROGRESS", "NOT_STARTED"), ("COMPLETED", "IN_PROGRESS"),
                                     ("IN_PROGRESS", "COMPLETED"), ("COMPLETED", "IN_PROGRESS")):
                assert (await _patch(async_client, c, key, status, expected)).status_code == 200

        assert planning(await _works(async_client, c)) == plan_before  # order, wait, coefficients
        assert await _estimate_snapshot(db_session) == lines  # lines, quantities, prices, overrides, status
        assert (await db_session.execute(text("SELECT * FROM price_items ORDER BY id"))).all() == items
        assert (await db_session.execute(text(
            "SELECT * FROM surface_planned_work_coefficient_assignments ORDER BY coefficient_option_id"))).all() == coefs
        preview = await estimates.regenerate_draft(estimate.id, c.user.id, c.ids[0])
        assert (preview.added, preview.removed) == (0, 0)
        assert await _priced(db_session) == priced
        assert {w["execution"]["status"] for w in await _works(async_client, c)} == {"COMPLETED"}
