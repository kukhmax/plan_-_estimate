"""Stage 13G — technological breaks on the actual surface work plan.

Existing coverage kept (not duplicated): per-occurrence breaks and key
preservation (test_occurrence_key), template APPEND/REPLACE copying step waits
(test_apply_template), apply-to-all copying waits with new keys and Stage 11
appends without a break (test_occurrence_key). Added here: a wait-only edit
through the ordinary PUT leaves coefficients, keys and the Estimate untouched
(generation AND regeneration), and invalid waits are rejected without mutation.
"""
from httpx import AsyncClient

from app.domain.services.estimate_service import EstimateService
from sqlalchemy import text

from tests.test_apply_template import _estimate_snapshot, _setup


async def _priced(db) -> list[dict]:
    """Estimate lines without the volatile row link / timestamp columns."""
    rows = (await db.execute(text("SELECT * FROM estimate_lines ORDER BY id"))).mappings().all()
    return [{k: v for k, v in r.items() if k not in ("planned_work_id", "updated_at")} for r in rows]


def _payload(works: list[dict], waits: list[int | None]) -> dict:
    return {"substrate": "CONCRETE", "quality_target": "S2", "planned_works": [
        {"price_item_id": w["price_item_id"], "occurrence_key": w["occurrence_key"], "wait_after_hours": wait,
         "coefficient_option_ids": [o["id"] for o in w["coefficient_options"]]}
        for w, wait in zip(works, waits)
    ]}


class TestWaitOnlyEdit:
    async def test_wait_edit_keeps_keys_and_coefficients_and_estimate(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)  # one occurrence: item X, wait 6 h, coefficient opts[1]
        base = c.url.removesuffix("/apply-template")
        before = (await async_client.get(base, headers=c.headers)).json()["planned_works"]
        assert [(w["wait_after_hours"], [o["id"] for o in w["coefficient_options"]]) for w in before] == [(6, [str(c.opts[1].id)])]
        svc = EstimateService(db_session)
        estimate = await svc.generate_estimate(c.project.id, c.user.id)
        lines_before = await _estimate_snapshot(db_session)
        priced_before = await _priced(db_session)

        for wait in (48, None, 1):
            put = await async_client.put(base, headers=c.headers, json=_payload(before, [wait]))
            assert put.status_code == 200, put.text
            got = put.json()["planned_works"]
            assert [(w["occurrence_key"], w["wait_after_hours"]) for w in got] == [(before[0]["occurrence_key"], wait)]
            assert [o["id"] for o in got[0]["coefficient_options"]] == [str(c.opts[1].id)]
            assert await _estimate_snapshot(db_session) == lines_before  # nothing written to the Estimate

        preview = await svc.regenerate_draft(estimate.id, c.user.id, c.project.id)
        assert (preview.added, preview.removed) == (0, 0)
        # Only the row link moves: every ordinary save recreates planned-work ROWS
        # (D13) and regeneration re-links the line via the stable occurrence_key.
        # Prices, quantities, coefficients and the key itself are unchanged.
        assert await _priced(db_session) == priced_before

    async def test_invalid_wait_rejected_without_mutation(self, async_client: AsyncClient, db_session):
        c = await _setup(async_client, db_session)
        base = c.url.removesuffix("/apply-template")
        before = (await async_client.get(base, headers=c.headers)).json()
        for bad in (0, -4, 1.5, "abc"):
            resp = await async_client.put(base, headers=c.headers, json=_payload(before["planned_works"], [bad]))
            assert resp.status_code == 422, (bad, resp.text)
        assert (await async_client.get(base, headers=c.headers)).json() == before
