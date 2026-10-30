"""UX walk: the protection of the floors planned on the walls and the ceiling is counted by the floor of the room, once per room --
not by the sum of the walls (45.27 m² of walls for a 20 m² floor)."""
from decimal import Decimal

from sqlalchemy import select

from app.domain.services.estimate_service import EstimateService
from app.models.estimate import EstimateLine
from app.models.price_item import PriceCategory, PriceItem, PriceScope, PriceUnit
from app.models.surface import SurfaceType
from tests.test_estimates_api import _make_plane_surface, _make_price_item, _make_project, _make_room, _make_surface, _make_user, _make_work_plan


async def _protection(db, owner_id) -> PriceItem:
    item = PriceItem(owner_id=owner_id, code="CENNIK_PREP_PROT-01", category=PriceCategory.PREPARATION, unit=PriceUnit.M2,
                     price=Decimal("3.00"), price_scope=PriceScope.LABOR)
    db.add(item)
    await db.commit()
    return item


async def test_the_protection_takes_the_floor_of_the_room_once_and_the_other_works_keep_their_surface(db_session):
    user = await _make_user(db_session, 1307001)
    project = await _make_project(db_session, user.id)
    room = await _make_room(db_session, project.id, length="4.000", width="5.000")
    other_room = await _make_room(db_session, project.id, name="Kuchnia", length="3.000", width="2.000")
    walls = [await _make_surface(db_session, room.id, position=i) for i in range(2)]
    ceiling = await _make_plane_surface(db_session, room.id, SurfaceType.CEILING)
    other_wall = await _make_surface(db_session, other_room.id)
    protection = await _protection(db_session, user.id)
    paint = await _make_price_item(db_session, user.id)
    for surface in (*walls, ceiling):
        await _make_work_plan(db_session, project.id, room.id, surface.id, user.id, [protection, paint])
    await _make_work_plan(db_session, project.id, other_room.id, other_wall.id, user.id, [protection])

    estimate = await EstimateService(db_session).generate_estimate(project.id, user.id)
    lines = (await db_session.execute(select(EstimateLine).where(EstimateLine.estimate_id == estimate.id))).scalars().all()
    by_room = {}
    for line in lines:
        if line.price_item_id == protection.id:
            by_room.setdefault(line.room_id, []).append(line.quantity)
    floor = (await EstimateService(db_session)._plane_net_area(room.id, SurfaceType.FLOOR))
    assert floor is not None and floor > 0
    assert sorted(by_room[room.id], reverse=True) == [floor, Decimal("0.000"), Decimal("0.000")]
    assert by_room[other_room.id] == [await EstimateService(db_session)._plane_net_area(other_room.id, SurfaceType.FLOOR)]
    # the painting is still measured by each wall
    painted = [line.quantity for line in lines if line.price_item_id == paint.id and line.surface_id == walls[0].id]
    assert painted == [await EstimateService(db_session)._surface_net_area(walls[0])]

    # a regeneration keeps the same quantities (nothing to change)
    result = await EstimateService(db_session).regenerate_draft(estimate.id, user.id, project.id)
    assert result.updated == 0 and result.added == 0 and result.removed == 0
