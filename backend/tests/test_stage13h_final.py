"""Stage 13H.6 — final adversarial checks that close gaps left by the 13H.2–13H.5B
suites: the complete forward-only bulk matrix (incl. an explicit NOT_STARTED
row), the owner-verified walkthrough case, source additions / re-keying between
preview and apply, global isolation (Price Book, workflow templates) and
breaks never blocking transitions.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.domain.services.workflow_template_service import WorkflowTemplateStepSpec as Step
from app.domain.services.workflow_template_service import WorkflowTemplateService
from app.models.checklist import QualityLevel, Substrate
from app.models.surface import SurfaceType
from app.models.work_execution import WorkExecutionStatus
from app.schemas.work_plan import OrderedPriceItemSelection as Sel
from tests.test_stage13h_bulk_execution import _apply, _ctx, _plan, _preview, _rows, _wall, _wall_counts

S = WorkExecutionStatus
NS, IP, C = S.NOT_STARTED, S.IN_PROGRESS, S.COMPLETED


class TestForwardMatrix:
    @pytest.mark.parametrize("source,dest,expected", [
        (NS, NS, NS), (NS, IP, IP), (NS, C, C),          # source NOT_STARTED never acts / never resets
        (IP, NS, IP), (IP, IP, IP), (IP, C, C),          # never backward from COMPLETED
        (C, NS, C), (C, IP, C), (C, C, C),
        ("explicit", NS, NS),                            # explicit NOT_STARTED source row == lazy
        (C, "explicit", C),                              # explicit NOT_STARTED destination row advances
    ])
    async def test_every_pair(self, async_client: AsyncClient, db_session, source, dest, expected):
        c = await _ctx(async_client, db_session)
        a, b = await _wall(c, "A", 0), await _wall(c, "B", 1)
        ka = await _plan(c, a, [c.p1], [] if source == "explicit" else [source])
        kb = await _plan(c, b, [c.p1], [] if dest == "explicit" else [dest])
        for wall, key, marker in ((a, ka[0], source), (b, kb[0], dest)):
            if marker == "explicit":  # start + reset leaves an explicit NOT_STARTED row
                await c.exec.transition(c.project, c.room, wall, c.user, key, status=IP, expected_status=NS)
                await c.exec.transition(c.project, c.room, wall, c.user, key, status=NS, expected_status=IP)
        before = await _rows(db_session)
        body = (await _apply(c, a, (await _preview(c, a)).json()["expected_source"])).json()
        after = await _rows(db_session)
        assert after.get(kb[0], (NS, None, None))[0] == expected
        changed = expected != (NS if dest == "explicit" else dest)
        assert _wall_counts(body, b) == ((1, 0) if changed else (0, 1)) + (0, 0, True)
        assert after.get(ka[0]) == before.get(ka[0])  # source untouched


class TestOwnerVerifiedCase:
    async def test_three_walls_six_changed_three_unchanged_then_zero_nine(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        a = await _wall(c, "Стена 1", 0)
        targets = [await _wall(c, f"Стена {i}", i - 1) for i in (2, 3, 4)]
        await _plan(c, a, [c.p1, c.p2, c.p3], [C, IP, NS])
        keys = {t: await _plan(c, t, [c.p1, c.p2, c.p3]) for t in targets}

        first = (await _preview(c, a)).json()
        assert (len(first["walls"]), first["changed"], first["unchanged"], first["unmatched"], first["ambiguous"]) == (3, 6, 3, 0, 0)
        applied = (await _apply(c, a, first["expected_source"])).json()
        assert (applied["changed"], applied["unchanged"]) == (6, 3)
        rows = await _rows(db_session)
        for t in targets:
            assert [rows.get(k, (NS,))[0] for k in keys[t]] == [C, IP, NS]
        second = (await _preview(c, a)).json()
        assert (second["changed"], second["unchanged"]) == (0, 9)


class TestSourceSnapshot:
    async def _setup(self, client, db):
        c = await _ctx(client, db)
        c.a, c.b = await _wall(c, "A", 0), await _wall(c, "B", 1)
        c.ka = await _plan(c, c.a, [c.p1, c.p2], [C, NS])
        c.kb = await _plan(c, c.b, [c.p1, c.p2])
        c.snap = (await _preview(c, c.a)).json()["expected_source"]
        return c

    async def _save_source(self, c, entries):
        await c.plans.set_plan(c.project, c.room, c.a, c.user, substrate=Substrate.CONCRETE,
                               quality_target=QualityLevel.S2, planned_works=entries)

    async def test_source_occurrence_added_after_preview(self, async_client: AsyncClient, db_session):
        c = await self._setup(async_client, db_session)
        await self._save_source(c, [Sel(price_item_id=c.p1, occurrence_key=c.ka[0]),
                                    Sel(price_item_id=c.p2, occurrence_key=c.ka[1]), Sel(price_item_id=c.p3)])
        before = await _rows(db_session)
        res = await _apply(c, c.a, c.snap)
        assert res.status_code == 409 and res.json()["detail"]["code"] == "WORK_EXECUTION_SOURCE_CHANGED"
        assert await _rows(db_session) == before

    async def test_source_occurrence_rekeyed_after_preview(self, async_client: AsyncClient, db_session):
        c = await self._setup(async_client, db_session)
        # same PriceItem at the same position but a NEW occurrence (key) -- still a source change
        await self._save_source(c, [Sel(price_item_id=c.p1, occurrence_key=c.ka[0]), Sel(price_item_id=c.p2)])
        before = await _rows(db_session)
        res = await _apply(c, c.a, c.snap)
        assert res.status_code == 409 and res.json()["detail"]["code"] == "WORK_EXECUTION_SOURCE_CHANGED"
        assert await _rows(db_session) == before


class TestGlobalIsolation:
    async def test_price_book_and_template_definitions_untouched(self, async_client: AsyncClient, db_session):
        c = await _ctx(async_client, db_session)
        await WorkflowTemplateService(db_session).create_template(
            c.user, display_name="T", applies_to_substrates=[Substrate.CONCRETE],
            applies_to_quality=[QualityLevel.S2], applies_to_surface_types=[SurfaceType.WALL],
            steps=[Step(price_item_id=c.p1, wait_after_hours=24), Step(price_item_id=c.p2)])
        a, b = await _wall(c, "A", 0), await _wall(c, "B", 1)
        ka = await _plan(c, a, [c.p1, c.p2], [C, NS], waits={0: 24})
        await _plan(c, b, [c.p1, c.p2])
        tables = ("price_items", "workflow_templates", "workflow_template_steps", "coefficient_groups", "coefficient_options")
        snap = {t: (await db_session.execute(text(f"SELECT * FROM {t} ORDER BY id"))).all() for t in tables}
        # a break never blocks the next work: start the work right after a completed one with a 24 h break
        await c.exec.transition(c.project, c.room, a, c.user, ka[1], status=IP, expected_status=NS)
        await c.exec.transition(c.project, c.room, a, c.user, ka[1], status=NS, expected_status=IP)
        body = (await _apply(c, a, (await _preview(c, a)).json()["expected_source"])).json()
        assert body["changed"] == 1
        for t in tables:
            assert (await db_session.execute(text(f"SELECT * FROM {t} ORDER BY id"))).all() == snap[t], t
