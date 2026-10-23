"""Merged walls -- join several walls of a room into one (the first stays; sizes become parts; photos and openings move; the rest is archived),
and take them apart again. Rules decided by the owner on 2026-10-23: the plan is the plan of the first wall, separation is possible, the
parts are a list in the card.
"""
import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import app
from app.models.estimate import Estimate, EstimateLine, EstimateStatus
from app.models.opening import Opening
from app.models.photo_asset import PhotoAssetStatus
from app.models.photo_attachment import PhotoAttachment, PhotoAttachmentContext, PhotoCategory
from app.models.surface import Surface
from app.models.work_execution import SurfaceWorkExecution, WorkExecutionStatus
from app.models.work_plan import SurfaceWorkPlan
from tests import test_stage14c4_photos_api as c4
from tests.test_estimates import _make_opening, _make_room, _make_surface
from tests.test_stage14b4_photo_asset import raw_asset

api = c4.api


@pytest.fixture
async def http(api):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {api.token}"
        yield client


async def _photo(api, surface_id) -> PhotoAttachment:
    asset = raw_asset(SimpleNamespace(id=api.me), SimpleNamespace(id=api.project), status=PhotoAssetStatus.READY)
    api.db.add(asset)
    await api.db.flush()
    row = PhotoAttachment(
        asset_id=asset.id, project_id=api.project, surface_id=surface_id,
        context=PhotoAttachmentContext.SURFACE, category=PhotoCategory.GENERAL, position=0,
    )
    api.db.add(row)
    await api.db.commit()
    return row


def _base(api) -> str:
    return f"/api/projects/{api.project}/rooms/{api.room}/surfaces"


async def _three(api):
    """The wall of the fixture (5.000 x 2.700) and two more: 3.420 x 2.520 and 2.700 x 2.500."""
    first = await api.db.get(Surface, api.surface)
    second = await _make_surface(api.db, api.room, width="3.420", height="2.520")
    third = await _make_surface(api.db, api.room, width="2.700", height="2.500")
    return first, second, third


async def test_merge_keeps_every_size_as_a_part_and_sums_the_area(api, http):
    first, second, third = await _three(api)
    response = await http.post(f"{_base(api)}/merge", json={"surface_ids": [str(first.id), str(second.id), str(third.id)]})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["id"] == str(first.id) and body["merged_into_id"] is None
    assert [(p["width"], p["height"]) for p in body["parts"]] == [("5.000", "2.700"), ("3.420", "2.520"), ("2.700", "2.500")]
    assert Decimal(body["gross_area"]) == Decimal("13.500") + Decimal("8.618") + Decimal("6.750")  # each part rounded like a wall
    assert Decimal(body["net_area"]) == Decimal(body["gross_area"]) - Decimal(body["deduction_area"])
    listed = (await http.get(_base(api))).json()["items"]
    assert [row["id"] for row in listed] == [str(first.id)]  # the joined walls are archived
    everything = (await http.get(_base(api), params={"include_archived": "true"})).json()["items"]
    absorbed = {row["id"]: row for row in everything if row["is_archived"]}
    assert set(absorbed) == {str(second.id), str(third.id)}
    assert all(row["merged_into_id"] == str(first.id) for row in absorbed.values())


async def test_photos_and_openings_move_to_the_merged_wall_and_come_back_on_unmerge(api, http):
    first, second, third = await _three(api)
    own_deduction = Decimal((await http.get(f"{_base(api)}/{first.id}")).json()["deduction_area"])  # the wall of the fixture has a window
    own_photo = await _photo(api, first.id)
    photo = await _photo(api, second.id)
    window = await _make_opening(api.db, second.id, width="1.000", height="1.000")
    door = await _make_opening(api.db, third.id, width="0.900", height="2.100")
    await http.post(f"{_base(api)}/merge", json={"surface_ids": [str(first.id), str(second.id), str(third.id)]})
    for row in (photo, window, door):
        await api.db.refresh(row)
    assert photo.surface_id == first.id and window.surface_id == first.id and door.surface_id == first.id
    merged = (await http.get(f"{_base(api)}/{first.id}")).json()
    assert Decimal(merged["deduction_area"]) == own_deduction + Decimal("1.000") + Decimal("1.890")

    # something added after the merge stays on the merged wall
    added = await _make_opening(api.db, first.id, width="0.500", height="0.500")
    response = await http.post(f"{_base(api)}/{first.id}/unmerge")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["parts"] == [] and body["gross_area"] == "13.500"
    for row in (own_photo, photo, window, door, added):
        await api.db.refresh(row)
    assert (own_photo.surface_id, photo.surface_id) == (first.id, second.id)
    assert (window.surface_id, door.surface_id, added.surface_id) == (second.id, third.id, first.id)
    listed = (await http.get(_base(api))).json()["items"]
    assert {row["id"] for row in listed} == {str(first.id), str(second.id), str(third.id)}
    assert all(row["merged_into_id"] is None and row["parts"] == [] for row in listed)


async def test_the_plan_of_the_first_wall_stays_and_the_others_stay_with_the_archived_walls(api, http):
    first, second, _ = await _three(api)
    plan_first = SurfaceWorkPlan(surface_id=first.id, substrate="CONCRETE")
    plan_second = SurfaceWorkPlan(surface_id=second.id, substrate="CONCRETE")
    api.db.add_all([plan_first, plan_second])
    await api.db.commit()
    await http.post(f"{_base(api)}/merge", json={"surface_ids": [str(first.id), str(second.id)]})
    plans = (await api.db.execute(select(SurfaceWorkPlan.surface_id))).scalars().all()
    assert set(plans) == {first.id, second.id}


async def test_the_area_of_the_estimate_and_the_room_follow_the_parts(api, http):
    first, second, _ = await _three(api)
    before = (await http.get(f"/api/projects/{api.project}/rooms/{api.room}")).json()
    await http.post(f"{_base(api)}/merge", json={"surface_ids": [str(first.id), str(second.id)]})
    after = (await http.get(f"/api/projects/{api.project}/rooms/{api.room}")).json()
    keys = ("total_wall_area", "net_wall_area", "wall_count")
    assert {k: before["calculations"][k] for k in keys} == {k: after["calculations"][k] for k in keys}  # the same walls, now as one: the totals do not change


async def test_the_size_of_a_merged_wall_is_edited_by_its_parts(api, http):
    first, second, _ = await _three(api)
    merged = (await http.post(f"{_base(api)}/merge", json={"surface_ids": [str(first.id), str(second.id)]})).json()
    refused = await http.patch(f"{_base(api)}/{first.id}", json={"width": "4.000"})
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "WALL_MERGED_EDIT_PARTS"
    assert (await http.patch(f"{_base(api)}/{first.id}", json={"name": "Ściana północna"})).status_code == 200
    second_part = merged["parts"][1]["id"]
    changed = await http.patch(f"{_base(api)}/{first.id}/parts/{second_part}", json={"width": "4.000", "height": "2.500"})
    assert changed.status_code == 200, changed.text
    assert Decimal(changed.json()["gross_area"]) == Decimal("13.500") + Decimal("10.000")
    first_part = merged["parts"][0]["id"]
    own = await http.patch(f"{_base(api)}/{first.id}/parts/{first_part}", json={"width": "5.000", "height": "2.600"})
    assert own.json()["height"] == "2.600"  # the first part is the wall's own size
    assert (await http.patch(f"{_base(api)}/{first.id}/parts/{uuid.uuid4()}", json={"width": "1", "height": "1"})).status_code == 404


async def test_a_part_cannot_shrink_below_the_openings(api, http):
    first, second, _ = await _three(api)
    await _make_opening(api.db, first.id, width="2.000", height="2.000")
    merged = (await http.post(f"{_base(api)}/merge", json={"surface_ids": [str(first.id), str(second.id)]})).json()
    refused = await http.patch(f"{_base(api)}/{first.id}/parts/{merged['parts'][1]['id']}", json={"width": "0.100", "height": "0.100"})
    assert refused.status_code == 200  # 13.5 + 0.01 still holds the 4.0 of openings
    huge = await http.patch(f"{_base(api)}/{first.id}/parts/{merged['parts'][0]['id']}", json={"width": "0.100", "height": "0.100"})
    assert huge.status_code == 409 and huge.json()["detail"]["code"] == "WALL_PART_OPENINGS_EXCEED"


async def test_a_wall_that_was_joined_cannot_be_restored_alone(api, http):
    first, second, _ = await _three(api)
    await http.post(f"{_base(api)}/merge", json={"surface_ids": [str(first.id), str(second.id)]})
    refused = await http.post(f"{_base(api)}/{second.id}/restore")
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "WALL_RESTORE_MERGED"


@pytest.mark.parametrize(
    "case,code,status",
    [("one", "WALL_MERGE_NEED_TWO", 422), ("twice", "WALL_MERGE_NEED_TWO", 422)],
)
async def test_a_merge_needs_two_different_walls(api, http, case, code, status):
    first, _, _ = await _three(api)
    ids = [str(first.id)] if case == "one" else [str(first.id), str(first.id)]
    response = await http.post(f"{_base(api)}/merge", json={"surface_ids": ids})
    assert response.status_code in (422,)
    if case == "twice":
        assert response.json()["detail"]["code"] == code


async def test_merge_refuses_the_wrong_walls(api, http):
    first, second, _ = await _three(api)
    other_room = (await _make_room(api.db, api.project, name="Kuchnia")).id
    stranger = await _make_surface(api.db, other_room)
    assert (await http.post(f"{_base(api)}/merge", json={"surface_ids": [str(first.id), str(stranger.id)]})).status_code == 404
    assert (await http.post(f"{_base(api)}/merge", json={"surface_ids": [str(first.id), str(uuid.uuid4())]})).status_code == 404
    second.is_archived = True
    await api.db.commit()
    archived = await http.post(f"{_base(api)}/merge", json={"surface_ids": [str(first.id), str(second.id)]})
    assert archived.status_code == 409 and archived.json()["detail"]["code"] == "WALL_MERGE_ARCHIVED"


async def test_merge_refuses_a_merged_wall_and_unmerge_refuses_a_plain_one(api, http):
    first, second, third = await _three(api)
    assert (await http.post(f"{_base(api)}/{first.id}/unmerge")).json()["detail"]["code"] == "WALL_UNMERGE_NOT_MERGED"
    await http.post(f"{_base(api)}/merge", json={"surface_ids": [str(first.id), str(second.id)]})
    again = await http.post(f"{_base(api)}/merge", json={"surface_ids": [str(first.id), str(third.id)]})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "WALL_MERGE_ALREADY_MERGED"


async def test_merge_is_refused_when_work_started_or_an_estimate_was_issued(api, http):
    first, second, third = await _three(api)
    from tests.test_work_recommendation_accept import _make_price_item  # noqa: PLC0415

    item = await _make_price_item(api.db, api.me, code="WM_ITEM")
    plan = SurfaceWorkPlan(surface_id=second.id, substrate="CONCRETE")
    api.db.add(plan)
    await api.db.flush()
    from datetime import datetime, timezone  # noqa: PLC0415

    api.db.add(SurfaceWorkExecution(
        occurrence_key=uuid.uuid4(), work_plan_id=plan.id, price_item_id=item.id,
        status=WorkExecutionStatus.IN_PROGRESS, started_at=datetime.now(timezone.utc),
    ))
    await api.db.commit()
    started = await http.post(f"{_base(api)}/merge", json={"surface_ids": [str(first.id), str(second.id)]})
    assert started.status_code == 409 and started.json()["detail"]["code"] == "WALL_MERGE_WORK_STARTED"


async def test_merge_is_refused_for_walls_of_another_owner(api, http):
    # the same checks as every route of the room: a room that is not the caller's is "not found"
    first, second, _ = await _three(api)
    response = await http.post(f"/api/projects/{uuid.uuid4()}/rooms/{api.room}/surfaces/merge", json={"surface_ids": [str(first.id), str(second.id)]})
    assert response.status_code == 404


async def test_openings_are_checked_against_the_area_of_the_whole_merged_wall(api, http):
    first, second, _ = await _three(api)
    big = {"opening_type": "OTHER", "width": "6.000", "height": "3.000", "quantity": 1, "id": str(uuid.uuid4())}
    url = f"{_base(api)}/{first.id}/openings"
    # 18.0 m2 of openings: more than the 13.5 m2 of the wall of the fixture alone ...
    assert (await http.post(url, json=big)).status_code == 422
    await http.post(f"{_base(api)}/merge", json={"surface_ids": [str(first.id), str(second.id)]})
    # ... and fine for the merged wall (13.5 + 8.618 m2)
    created = await http.post(url, json={**big, "id": str(uuid.uuid4())})
    assert created.status_code == 201, created.text
