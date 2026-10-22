"""Usability U-7 -- the list of surfaces tells how many works the saved plan of each holds (an added, read-only field)."""
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.checklist import Substrate
from app.models.work_plan import SurfacePlannedWork, SurfaceWorkPlan
from tests import test_stage14c4_photos_api as c4
from tests.test_estimates import _make_room, _make_surface

api = c4.api


@pytest.fixture
async def http(api):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {api.token}"
        yield client


async def _plan(db, surface_id, price_item_id, works: int):
    plan = SurfaceWorkPlan(surface_id=surface_id, substrate=Substrate.CONCRETE)
    db.add(plan)
    await db.flush()
    for position in range(works):
        db.add(SurfacePlannedWork(work_plan_id=plan.id, price_item_id=price_item_id, position=position, occurrence_key=uuid.uuid4()))
    await db.commit()


async def test_the_list_tells_how_many_works_each_plan_holds(api, http):
    from tests.test_work_recommendation_accept import _make_price_item  # noqa: PLC0415

    item = await _make_price_item(api.db, api.me, code="U7_ITEM")
    other = (await _make_surface(api.db, api.room)).id
    await _plan(api.db, api.surface, item.id, 3)
    listed = (await http.get(f"/api/projects/{api.project}/rooms/{api.room}/surfaces")).json()["items"]
    counts = {row["id"]: row["planned_work_count"] for row in listed}
    assert counts[str(api.surface)] == 3
    assert counts[str(other)] == 0  # a surface with no plan holds no works


async def test_the_count_is_not_a_part_of_another_room_or_owner(api, http):
    from tests.test_work_recommendation_accept import _make_price_item  # noqa: PLC0415

    item = await _make_price_item(api.db, api.me, code="U7_ITEM2")
    neighbour_room = (await _make_room(api.db, api.project, name="Kuchnia")).id
    neighbour_wall = (await _make_surface(api.db, neighbour_room)).id
    await _plan(api.db, neighbour_wall, item.id, 2)
    listed = (await http.get(f"/api/projects/{api.project}/rooms/{api.room}/surfaces")).json()["items"]
    assert all(row["planned_work_count"] == 0 for row in listed)
    in_neighbour = (await http.get(f"/api/projects/{api.project}/rooms/{neighbour_room}/surfaces")).json()["items"]
    assert [row["planned_work_count"] for row in in_neighbour] == [2]
