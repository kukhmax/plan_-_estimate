"""Owner's UX walk (2026-10-27, A2): carrying the craftsman's answers over must not count twice what the owner already typed in the same room."""
import uuid
from decimal import Decimal

from sqlalchemy import select

from app.domain.rules import trade_transfer as rules
from app.models.material import MaterialCalc
from app.models.room_point import RoomPoint
from tests.test_v2_14a_trade_transfer import calcs, electric_world, points, post


def _own(item: uuid.UUID, quantity: str) -> rules.ExistingRow:
    return rules.ExistingRow(uuid.uuid4(), item, Decimal(quantity), None)


def test_replace_takes_the_owners_row_over_and_removes_his_second_row_of_that_item():
    a, b = uuid.uuid4(), uuid.uuid4()
    wanted = [rules.Wanted(a, Decimal("5.00"), "bateria"), rules.Wanted(b, Decimal("3.00"), None)]
    first, second = _own(a, "4"), _own(a, "4")
    acts = rules.plan_rows(wanted, [], {a, b}, [first, second], rules.REPLACE)
    assert [(x.kind, x.row_id) for x in acts] == [(rules.TAKE_OVER, first.id), (rules.REMOVE_OWN, second.id), (rules.NEW, None)]
    assert acts[0].quantity == Decimal("5.00") and acts[0].was_quantity == Decimal("4.00") and acts[0].own_quantity == Decimal("8.00")


def test_add_keeps_both_and_says_how_many_the_owner_has_and_skip_leaves_his_row_alone():
    a = uuid.uuid4()
    wanted = [rules.Wanted(a, Decimal("5.00"), None)]
    mine = _own(a, "4")
    added = rules.plan_rows(wanted, [], {a}, [mine], rules.ADD)
    assert [(x.kind, x.own_quantity) for x in added] == [(rules.NEW, Decimal("4.00"))]
    skipped = rules.plan_rows(wanted, [], {a}, [mine], rules.SKIP)
    assert [(x.kind, x.own_quantity) for x in skipped] == [(rules.SKIP, Decimal("4.00"))]
    # an own row of ANOTHER item is never in play
    assert [x.kind for x in rules.plan_rows(wanted, [], {a}, [_own(uuid.uuid4(), "9")], rules.REPLACE)] == [rules.NEW]


async def test_the_preview_counts_the_conflicts_and_replace_is_the_default(async_client, db_session):
    w = await electric_world(async_client, db_session)
    db_session.add_all([
        RoomPoint(owner_id=w.owner.id, project_id=w.project.id, room_id=w.salon.id, price_item_id=w.point.id, quantity=Decimal("4.00"), position=0),
        MaterialCalc(owner_id=w.owner.id, project_id=w.project.id, room_id=w.salon.id, package="ELECTRIC", params={"sockets": 1}, position=0),
    ])
    await db_session.commit()
    preview = (await post(async_client, w, "/preview")).json()
    assert preview["own"] == "REPLACE" and preview["own_conflicts"] == 2
    salon = next(r for r in preview["rooms"] if r["room_id"] == str(w.salon.id))
    taken = next(r for r in salon["rows"] if r["item_id"] == str(w.point.id))
    assert taken["kind"] == "TAKE_OVER" and Decimal(taken["own_quantity"]) == Decimal("4.00") and Decimal(taken["quantity"]) == Decimal("8.00")
    assert salon["material"]["kind"] == "TAKE_OVER" and salon["material"]["own"] is True
    assert len(await points(db_session)) == 1  # the preview writes nothing


async def test_replace_leaves_one_row_with_the_craftsmans_number_and_a_second_carrying_over_changes_nothing(async_client, db_session):
    w = await electric_world(async_client, db_session)
    mine = RoomPoint(owner_id=w.owner.id, project_id=w.project.id, room_id=w.salon.id, price_item_id=w.point.id, quantity=Decimal("4.00"), position=0)
    calc = MaterialCalc(owner_id=w.owner.id, project_id=w.project.id, room_id=w.salon.id, package="ELECTRIC", params={"sockets": 1}, position=0)
    db_session.add_all([mine, calc])
    await db_session.commit()
    done = (await post(async_client, w, "")).json()
    assert done["points_changed"] == 1 and done["points_added"] == 3 and done["materials_changed"] == 1 and done["materials_added"] == 1
    salon_points = [r for r in await points(db_session) if r.room_id == w.salon.id and r.price_item_id == w.point.id]
    assert len(salon_points) == 1 and salon_points[0].id == mine.id and salon_points[0].quantity == Decimal("8.00") and salon_points[0].source == "TRADE_LINK"
    salon_calcs = [c for c in await calcs(db_session) if c.room_id == w.salon.id]
    assert len(salon_calcs) == 1 and salon_calcs[0].params["sockets"] == 6 and salon_calcs[0].source == "TRADE_LINK"
    again = (await post(async_client, w, "")).json()
    assert again == {"points_added": 0, "points_changed": 0, "points_removed": 0, "materials_added": 0, "materials_changed": 0, "materials_removed": 0}


async def test_skip_keeps_the_owners_row_and_does_not_carry_that_item_into_that_room(async_client, db_session):
    w = await electric_world(async_client, db_session)
    mine = RoomPoint(owner_id=w.owner.id, project_id=w.project.id, room_id=w.salon.id, price_item_id=w.point.id, quantity=Decimal("4.00"), position=0)
    db_session.add(mine)
    await db_session.commit()
    done = (await post(async_client, w, "", {"own": "SKIP"})).json()
    assert done["points_added"] == 3  # Kuchnia's sockets, Salon's light points and cable; not Salon's sockets
    salon_points = [r for r in await points(db_session) if r.room_id == w.salon.id and r.price_item_id == w.point.id]
    assert [(r.id, r.quantity, r.source) for r in salon_points] == [(mine.id, Decimal("4.00"), None)]


async def test_a_wrong_choice_is_refused(async_client, db_session):
    w = await electric_world(async_client, db_session)
    assert (await post(async_client, w, "/preview", {"own": "MERGE"})).status_code == 422
    assert (await db_session.execute(select(RoomPoint))).scalars().first() is None
