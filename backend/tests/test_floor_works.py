"""Owner 2026-10-31: "Zabezpieczenie podłóg" lives in the plan of the floor -- once per room, measured by the floor -- not on every wall."""
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select

from app.models.estimate import EstimateLine
from app.models.price_item import PriceItem
from app.models.room_work_plan import RoomPlannedWork
from app.models.work_execution import SurfaceWorkExecution, WorkExecutionStatus
from app.models.work_plan import SurfacePlannedWork, SurfaceWorkPlan
from tests.test_v2_5_room_work_plan import PRIM, SKIM, _codes, _room, web  # noqa: F401  (web is a fixture)

PROT = "CENNIK_PREP_PROT-01"


async def test_the_plan_of_a_room_puts_the_protection_once_into_the_plan_of_the_floor(async_client: AsyncClient, db_session, web):
    r = await _room(async_client, db_session)
    saved = await r.put(walls=(PROT, PRIM, SKIM), ceiling=(PROT, PRIM))
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["floor_works_on_floor"] is True
    assert body["plan"]["walls"] == [r.items[PRIM], r.items[SKIM]] and body["plan"]["ceiling"] == [r.items[PRIM]]  # not named for the walls any more
    for name in ("Wall 1", "Wall 2", "Ceiling"):
        assert PROT not in await _codes(db_session, (await r.plan_of(name))["id"])
    floor_plans = (
        await db_session.execute(
            select(SurfaceWorkPlan).join(SurfacePlannedWork, SurfacePlannedWork.work_plan_id == SurfaceWorkPlan.id)
            .join(PriceItem, PriceItem.id == SurfacePlannedWork.price_item_id).where(PriceItem.code == PROT)
        )
    ).scalars().unique().all()
    assert len(floor_plans) == 1
    assert await _codes(db_session, str(floor_plans[0].id)) == [PROT]
    # saving again adds nothing twice
    await r.put(walls=(PROT, PRIM), ceiling=())
    assert await _codes(db_session, str(floor_plans[0].id)) == [PROT]

    # the estimate: one line, the area of the floor (5.2 x 3.6)
    made = await async_client.post(f"/api/projects/{r.project}/estimates/generate", headers=r.headers)
    assert made.status_code in (200, 201), made.text
    lines = (await db_session.execute(select(EstimateLine).join(PriceItem, PriceItem.id == EstimateLine.price_item_id).where(PriceItem.code == PROT))).scalars().all()
    assert [line.quantity for line in lines] == [Decimal("18.720")]


async def test_the_move_takes_the_protection_off_the_walls_and_keeps_a_started_one(async_client: AsyncClient, db_session, web):
    r = await _room(async_client, db_session)
    # an old plan of every wall with the protection (made before the rule): through the ordinary save of the walls
    for name in ("Wall 1", "Wall 2", "Wall 3"):
        surface = await r.surface(name)
        put = await async_client.put(
            f"{r.base}/surfaces/{surface['surface_id']}/work-plan",
            json={"substrate": "GYPSUM_PLASTER", "quality_target": "S2", "planned_works": [{"price_item_id": r.items[PRIM]}, {"price_item_id": r.items[PROT]}, {"price_item_id": r.items[SKIM]}]},
            headers=r.headers,
        )
        assert put.status_code == 200, put.text
        assert put.json()["planned_works"][1]["price_item"]["measured_by_floor"] is True
        assert put.json()["planned_works"][0]["price_item"]["measured_by_floor"] is False
    wall3 = await r.plan_of("Wall 3")
    started_key = wall3["planned_works"][1]["occurrence_key"]
    db_session.add(SurfaceWorkExecution(occurrence_key=uuid.UUID(started_key), status=WorkExecutionStatus.COMPLETED, started_at=datetime.now(UTC), completed_at=datetime.now(UTC), work_plan_id=uuid.UUID(wall3["id"]), price_item_id=uuid.UUID(r.items[PROT])))
    await db_session.commit()

    moved = await async_client.post(f"{r.base}/floor-works/move", headers=r.headers)
    assert moved.status_code == 200, moved.text
    assert moved.json()["moved"] == 2 and moved.json()["added"] == 1
    assert await _codes(db_session, (await r.plan_of("Wall 1"))["id"]) == [PRIM, SKIM]  # the gap closed
    assert [w["position"] for w in (await r.plan_of("Wall 1"))["planned_works"]] == [0, 1]
    assert await _codes(db_session, (await r.plan_of("Wall 3"))["id"]) == [PRIM, PROT, SKIM]  # started: stays
    again = await async_client.post(f"{r.base}/floor-works/move", headers=r.headers)
    assert again.json()["moved"] == 0 and again.json()["added"] == 0
    assert (await db_session.execute(select(RoomPlannedWork))).scalars().all() == []


async def test_the_move_needs_the_owner(async_client: AsyncClient, db_session, web):
    r = await _room(async_client, db_session)
    assert (await async_client.post(f"{r.base}/floor-works/move")).status_code == 401
    other = await _room(async_client, db_session, email="ewa@example.pl")
    assert (await async_client.post(f"{r.base}/floor-works/move", headers=other.headers)).status_code == 404
