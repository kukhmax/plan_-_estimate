"""Stage 15H.2: the card of a work recommendation shows the wall and the defect, and warns when the same work is already in
the wall's plan or asked for by another card. Read-time only; nothing is written."""
from sqlalchemy import func, select

from app.domain.services.work_plan_service import SurfaceWorkPlanService
from app.domain.services.work_recommendation_service import WorkRecommendationService
from app.models.checklist import Substrate
from app.models.work_plan import SurfacePlannedWork, SurfaceWorkPlan
from app.models.work_recommendation import WorkRecommendation, WorkRecommendationStatus
from tests.test_stage15e3_recommended_works import CRACK, PRIM, full_world, rec

S = WorkRecommendationStatus


async def context_of(db, w, *, activity="active"):
    service = WorkRecommendationService(db)
    items, _ = await service.list_recommendations(w.project.id, w.salon.id, w.owner.id, activity=activity)
    prices = await service.resolve_current_price_items(w.owner.id, items)
    return items, await service.describe_context(w.owner.id, items, prices)


async def plan_count(db, w) -> int:
    return (await db.execute(select(func.count(SurfacePlannedWork.id)))).scalar_one()


async def with_plan(db, w):
    await SurfaceWorkPlanService(db).set_plan(w.project.id, w.salon.id, w.wall.id, w.owner.id, substrate=Substrate.GYPSUM_PLASTER, planned_works=[])


async def test_a_card_names_the_wall_and_the_defect_that_asks_for_the_work(db_session):
    w = await full_world(db_session, 9960)
    items, context = await context_of(db_session, w)
    by_work = {i.recommended_work_code: context[i.id] for i in items}
    assert (by_work[PRIM].surface_name, by_work[PRIM].surface_type) == ("Ściana A", "WALL")
    assert by_work[PRIM].reason_key == "risk.dusty_substrate_prime.title"
    assert by_work[CRACK].reason_key == "risk.crack_recurrence.title"
    assert all(c.in_plan_count == 0 and c.same_work_other_cards == 0 for c in context.values())


async def test_the_same_work_asked_by_two_defects_warns_both_cards(db_session):
    w = await full_world(db_session, 9961)
    twin = await rec(db_session, w, w.crack_risk, PRIM)  # a second defect asks for the primer on the same wall
    items, context = await context_of(db_session, w)
    prims = [i for i in items if i.recommended_work_code == PRIM]
    assert {i.id for i in prims} == {w.rec_prim.id, twin.id}
    assert [context[i.id].same_work_other_cards for i in prims] == [1, 1]
    assert context[next(i.id for i in items if i.recommended_work_code == CRACK)].same_work_other_cards == 0


async def test_a_dismissed_card_does_not_count_as_another_card(db_session):
    w = await full_world(db_session, 9962)
    await rec(db_session, w, w.crack_risk, PRIM, status=S.DISMISSED)
    items, context = await context_of(db_session, w)
    assert context[w.rec_prim.id].same_work_other_cards == 0


async def test_a_work_already_in_the_plan_of_the_wall_is_counted(db_session):
    w = await full_world(db_session, 9963)
    await with_plan(db_session, w)
    service = WorkRecommendationService(db_session)
    await service.accept_recommendation(w.project.id, w.rec_prim.id, w.owner.id)
    twin = await rec(db_session, w, w.crack_risk, PRIM)
    items, context = await context_of(db_session, w)
    assert context[twin.id].in_plan_count == 1 and context[twin.id].same_work_other_cards == 1  # the first card was accepted, the work is in the plan once
    assert context[w.rec_prim.id].in_plan_count == 1  # an accepted card says so too (its own occurrence)
    await service.accept_recommendation(w.project.id, twin.id, w.owner.id)  # accepting again is allowed by design: two occurrences
    items, context = await context_of(db_session, w)
    assert context[twin.id].in_plan_count == 2 and await plan_count(db_session, w) == 2


async def test_the_work_of_another_wall_is_not_counted(db_session):
    from app.models.surface import Surface, SurfaceType

    w = await full_world(db_session, 9964)
    await with_plan(db_session, w)
    other = Surface(room_id=w.salon.id, name="Ściana B", surface_type=SurfaceType.WALL)
    db_session.add(other)
    await db_session.commit()
    await SurfaceWorkPlanService(db_session).set_plan(w.project.id, w.salon.id, other.id, w.owner.id, substrate=Substrate.GYPSUM_PLASTER, planned_works=[])
    on_b = await rec(db_session, w, w.dusty, PRIM, surface_id=other.id)
    await WorkRecommendationService(db_session).accept_recommendation(w.project.id, w.rec_prim.id, w.owner.id)  # accepted on wall A only
    items, context = await context_of(db_session, w)
    assert context[on_b.id].in_plan_count == 0 and context[on_b.id].same_work_other_cards == 0
    assert context[on_b.id].surface_name == "Ściana B"


async def test_reading_the_context_writes_nothing_and_asks_a_fixed_number_of_queries(db_session):
    from sqlalchemy import event

    from tests.conftest import test_engine

    w = await full_world(db_session, 9965)
    await with_plan(db_session, w)
    before = (await db_session.execute(select(func.count(WorkRecommendation.id)))).scalar_one()
    plans = (await db_session.execute(select(func.count(SurfaceWorkPlan.id)))).scalar_one()
    statements: list[str] = []

    def collect(conn, cursor, statement, *args):
        statements.append(statement)

    async def count() -> int:
        statements.clear()
        event.listen(test_engine.sync_engine, "before_cursor_execute", collect)
        try:
            await context_of(db_session, w)
        finally:
            event.remove(test_engine.sync_engine, "before_cursor_execute", collect)
        return len(statements)

    await count()  # the first read also checks the one-off bootstrap of the rule catalogue
    first = await count()
    for n in range(4):
        await rec(db_session, w, w.dusty, f"CODE_{n}")
    assert await count() == first
    assert (await db_session.execute(select(func.count(WorkRecommendation.id)))).scalar_one() == before + 4
    assert (await db_session.execute(select(func.count(SurfaceWorkPlan.id)))).scalar_one() == plans




async def test_the_http_answers_carry_the_context(async_client, db_session):
    from tests.test_work_recommendation_api import (
        VALID_USER,
        _accept_url,
        _dismiss_url,
        _list_url,
        _make_actionable_recommendation,
        _make_inspection,
        _make_plan,
        _make_price_item,
        _make_project,
        _make_room,
        _make_surface,
        _make_template,
        _owner,
        auth_header,
        get_token,
    )

    token = await get_token(async_client, VALID_USER)
    owner = await _owner(db_session, VALID_USER)
    project = await _make_project(db_session, owner.id)
    room = await _make_room(db_session, project.id)
    wall = await _make_surface(db_session, room.id)
    inspection = await _make_inspection(db_session, room.id, (await _make_template(db_session)).id)
    await _make_plan(db_session, project.id, room.id, wall.id, owner.id)
    await _make_price_item(db_session, owner.id, code="SKIM_Q3_M2")
    first = await _make_actionable_recommendation(db_session, room, inspection, wall)
    second = await _make_actionable_recommendation(db_session, room, inspection, wall)  # the same work, another card
    headers = auth_header(token)

    listed = (await async_client.get(_list_url(project.id, room.id), headers=headers)).json()["items"]
    assert {(i["surface_name"], i["surface_type"], i["in_plan_count"], i["same_work_other_cards"]) for i in listed} == {("Ściana 1", "WALL", 0, 1)}

    accepted = (await async_client.post(_accept_url(project.id, first.id), headers=headers)).json()
    assert (accepted["in_plan_count"], accepted["same_work_other_cards"]) == (1, 1)
    listed = {i["id"]: i for i in (await async_client.get(_list_url(project.id, room.id), headers=headers)).json()["items"]}
    assert listed[str(second.id)]["in_plan_count"] == 1  # the second card now knows the work is in the plan once

    dismissed = (await async_client.post(_dismiss_url(project.id, second.id), headers=headers)).json()
    assert (dismissed["surface_name"], dismissed["in_plan_count"]) == ("Ściana 1", 1)
    after = {i["id"]: i for i in (await async_client.get(_list_url(project.id, room.id), headers=headers)).json()["items"]}
    assert after[str(first.id)]["same_work_other_cards"] == 0  # a dismissed card is not "another card"
