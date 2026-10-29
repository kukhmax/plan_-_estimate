"""V2-14a -- carrying the answers of a craftsman over into "Punkty i trasy" and the materials of the rooms (docs/V2_14A_PLAN_RU.md)."""
import uuid
from decimal import Decimal

from sqlalchemy import select, text

from app.domain.rules import trade_transfer as rules
from app.models.material import MaterialCalc
from app.models.price_item import PriceCategory, PriceItem, PriceScope, PriceUnit
from app.models.room_point import RoomPoint
from app.models.trade_link import TradeAnswer
from tests.test_clients import OTHER_USER
from tests.test_stage15f2_api import login
from tests.test_stage16e2_contract import contract_engine, load_migration, run
from tests.test_v2_14_trade_links import owner_world

ELEC_POINT = "Punkt elektryczny - gniazdko / włącznik"


async def item(db, owner_id, name, unit=PriceUnit.PCS, category=PriceCategory.ELECTRICAL, archived=False):
    row = PriceItem(owner_id=owner_id, code=f"CUSTOM_{uuid.uuid4().hex[:8]}", category=category, unit=unit, price_scope=PriceScope.LABOR, price=Decimal("10.00"),
                    display_name=name, is_archived=archived)
    db.add(row)
    await db.commit()
    return row


async def answer(db, w, room, key, quantity, trade="ELECTRIC", note=None, unit="PCS"):
    db.add(TradeAnswer(owner_id=w.owner.id, project_id=w.project.id, trade=trade, room_id=room.id, position_key=key, quantity=quantity, unit=unit, note=note))
    await db.commit()


async def own_answer(db, w, room, name):
    db.add(TradeAnswer(owner_id=w.owner.id, project_id=w.project.id, trade="ELECTRIC", room_id=room.id, custom_name=name, quantity=1, unit="PCS"))
    await db.commit()


async def electric_world(async_client, db):
    w = await owner_world(async_client, db)
    w.point = await item(db, w.owner.id, ELEC_POINT)
    w.light = await item(db, w.owner.id, "Punkt oświetleniowy")
    w.cable = await item(db, w.owner.id, "Ułożenie przewodu elektrycznego", PriceUnit.LM)
    await answer(db, w, w.salon, "SOCKET", 6, note="przy TV")
    await answer(db, w, w.salon, "SWITCH", 2, note="przy drzwiach")
    await answer(db, w, w.salon, "LIGHT_POINT", 3)
    await answer(db, w, w.salon, "CIRCUIT", 2)
    await answer(db, w, w.salon, "CABLE_ROUTE", Decimal("12.50"))
    await answer(db, w, w.kuchnia, "SOCKET", 8)
    w.url = f"{w.base}/ELECTRIC/transfer"
    return w


async def post(async_client, w, path, body=None):
    return await async_client.post(w.url + path, json=body or {}, headers=w.headers)


async def points(db):
    return list((await db.execute(select(RoomPoint).order_by(RoomPoint.room_id, RoomPoint.position))).scalars())


async def calcs(db):
    return list((await db.execute(select(MaterialCalc))).scalars())


# --- the rules --------------------------------------------------------------------------------------------------------------------


def test_the_positions_of_one_price_item_are_added_together_and_the_notes_are_joined_without_repeats():
    item_a, item_b = uuid.uuid4(), uuid.uuid4()
    typical = {"SOCKET": rules.Answer(Decimal(6), "przy TV"), "SWITCH": rules.Answer(Decimal(2), "przy TV"), "LIGHT_POINT": rules.Answer(Decimal(3), None), "CIRCUIT": rules.Answer(Decimal(2), None)}
    mapping = {"SOCKET": item_a, "SWITCH": item_a, "LIGHT_POINT": item_b, "CIRCUIT": None}
    order = ("SOCKET", "SWITCH", "LIGHT_POINT", "CIRCUIT", "CABLE_ROUTE")
    wanted = {w.item_id: w for w in rules.wanted_rows(typical, mapping, order)}
    assert wanted[item_a].quantity == Decimal("8.00") and wanted[item_a].note == "przy TV"
    assert wanted[item_b].quantity == Decimal("3.00") and wanted[item_b].note is None
    assert len(wanted) == 2  # the circuits have no item; zero and blank answers make no row
    assert rules.wanted_rows({"SOCKET": rules.Answer(Decimal(0), "x"), "SWITCH": rules.Answer(None, "y")}, mapping, order) == []


def test_the_numbers_of_the_materials_are_whole_pieces_and_metres_only_above_zero():
    typical = {"SOCKET": rules.Answer(Decimal("6.00"), None), "SWITCH": rules.Answer(Decimal(0), None), "CIRCUIT": rules.Answer(Decimal(2), None), "CABLE_ROUTE": rules.Answer(Decimal("12.5"), None)}
    assert rules.material_numbers("ELECTRIC", typical) == {"sockets": 6, "circuits": 2, "route_m": Decimal("12.50")}
    assert rules.material_numbers("PLUMBING", {"MANIFOLD_OUT": rules.Answer(Decimal(4), None), "PIPE_ROUTE": rules.Answer(Decimal(9), None)}) == {"manifold_outlets": 4, "pipe_m": Decimal("9.00")}
    assert rules.material_numbers("ELECTRIC", {"SOCKET": rules.Answer(Decimal(0), None)}) is None
    assert rules.same_numbers({"sockets": 6, "route_m": "12.50", "lights": 0}, {"sockets": 6, "route_m": Decimal("12.5")})
    assert not rules.same_numbers({"sockets": 6}, {"sockets": 7})


def test_a_row_of_another_item_is_left_alone_and_a_row_nobody_asks_for_any_more_goes():
    mine, other, gone = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    existing = [rules.ExistingRow(uuid.uuid4(), mine, Decimal(5), None), rules.ExistingRow(uuid.uuid4(), gone, Decimal(1), None), rules.ExistingRow(uuid.uuid4(), other, Decimal(1), None)]
    actions = rules.plan_rows([rules.Wanted(mine, Decimal(5), None), rules.Wanted(uuid.uuid4(), Decimal(2), "x")], existing, {mine, gone})
    assert sorted(a.kind for a in actions) == ["NEW", "REMOVE", "SAME"]
    assert not any(a.item_id == other for a in actions)  # not in the scope: the other craftsman's


# --- the preview ------------------------------------------------------------------------------------------------------------------


async def test_the_preview_finds_the_items_by_name_and_writes_nothing(async_client, db_session):
    w = await electric_world(async_client, db_session)
    response = await post(async_client, w, "/preview")
    assert response.status_code == 200, response.text
    body = response.json()
    chosen = {p["key"]: p["item_id"] for p in body["positions"]}
    assert chosen["SOCKET"] == chosen["SWITCH"] == str(w.point.id)
    assert chosen["LIGHT_POINT"] == str(w.light.id) and chosen["CABLE_ROUTE"] == str(w.cable.id) and chosen["CIRCUIT"] is None
    circuit = next(p for p in body["positions"] if p["key"] == "CIRCUIT")
    assert circuit["goes_to_points"] is False and circuit["candidates"] == []
    socket = next(p for p in body["positions"] if p["key"] == "SOCKET")
    assert socket["answered_rooms"] == 2 and {c["id"] for c in socket["candidates"]} == {str(w.point.id), str(w.light.id)}  # the items in pieces
    cable = next(p for p in body["positions"] if p["key"] == "CABLE_ROUTE")
    assert {c["id"] for c in cable["candidates"]} == {str(w.cable.id)}  # the items in metres
    salon = next(r for r in body["rooms"] if r["room_id"] == str(w.salon.id))
    assert [(r["kind"], r["quantity"]) for r in salon["rows"]] == [("NEW", "8.00"), ("NEW", "3.00"), ("NEW", "12.50")]
    assert salon["material"]["kind"] == "NEW" and salon["material"]["numbers"] == {"sockets": "6", "switches": "2", "lights": "3", "circuits": "2", "route_m": "12.50"}
    assert body["own_not_carried"] == 0 and body["nothing"] is False
    assert await points(db_session) == [] and await calcs(db_session) == []


async def test_the_items_of_the_trade_come_first_the_others_are_marked_and_the_pack_is_offered_only_when_something_has_no_item(async_client, db_session):
    w = await electric_world(async_client, db_session)
    stair = await item(db_session, w.owner.id, "Mikrocement na schody", category=PriceCategory.PREPARATION)
    universal = await item(db_session, w.owner.id, "Punkt", category=PriceCategory.POINTS_ROUTES)
    water = await item(db_session, w.owner.id, "Punkt wodny", category=PriceCategory.PLUMBING)
    body = (await post(async_client, w, "/preview")).json()
    socket = next(p for p in body["positions"] if p["key"] == "SOCKET")
    flags = {c["id"]: c["relevant"] for c in socket["candidates"]}
    assert flags[str(w.point.id)] and flags[str(universal.id)] and not flags[str(stair.id)] and not flags[str(water.id)]
    order = [c["relevant"] for c in socket["candidates"]]
    assert order == sorted(order, reverse=True)  # the relevant ones first
    assert body["offer_pack"] is False  # every answered position that has an item found its item
    for row in (await db_session.execute(select(PriceItem).where(PriceItem.id.in_([w.point.id, w.light.id])))).scalars():
        row.display_name = "Inna nazwa " + row.display_name
    await db_session.commit()
    assert (await post(async_client, w, "/preview")).json()["offer_pack"] is True  # nothing is found by the name any more
    plumbing = await async_client.post(f"{w.base}/PLUMBING/transfer/preview", json={}, headers=w.headers)
    assert plumbing.json()["offer_pack"] is False  # nothing answered for the plumber


async def test_the_preview_counts_the_own_positions_of_the_craftsman_that_cannot_be_carried(async_client, db_session):
    w = await electric_world(async_client, db_session)
    await own_answer(db_session, w, w.salon, "Gniazdo siłowe")
    assert (await post(async_client, w, "/preview")).json()["own_not_carried"] == 1


async def test_the_owner_may_choose_another_item_or_none_and_a_wrong_choice_is_refused(async_client, db_session):
    w = await electric_world(async_client, db_session)
    other = await item(db_session, w.owner.id, "Gniazdo w wersji premium")
    body = (await post(async_client, w, "/preview", {"mapping": {"SOCKET": str(other.id), "SWITCH": None}})).json()
    salon = next(r for r in body["rooms"] if r["room_id"] == str(w.salon.id))
    assert {(r["item_id"], r["quantity"]) for r in salon["rows"]} == {(str(other.id), "6.00"), (str(w.light.id), "3.00"), (str(w.cable.id), "12.50")}
    foreign = await item(db_session, await world_other_owner(db_session), "Cudzy punkt")
    archived = await item(db_session, w.owner.id, "Stary punkt", archived=True)
    in_metres = w.cable
    for bad in ({"SOCKET": str(foreign.id)}, {"SOCKET": str(archived.id)}, {"SOCKET": str(in_metres.id)}, {"CIRCUIT": str(w.point.id)}, {"NOPE": str(w.point.id)}, {"SOCKET": str(uuid.uuid4())}):
        refused = await post(async_client, w, "/preview", {"mapping": bad})
        assert refused.status_code == 422 and refused.json()["detail"]["code"] == "TRANSFER_ITEM_INVALID", bad


async def world_other_owner(db):
    from app.models.user import User

    other = User(telegram_user_id=OTHER_USER_ID, username="other")
    db.add(other)
    await db.commit()
    return other.id


OTHER_USER_ID = 7777001


# --- carrying over ----------------------------------------------------------------------------------------------------------------


async def test_carrying_over_makes_the_rows_and_the_calculation_marked_as_carried_and_touches_nothing_of_the_owners(async_client, db_session):
    w = await electric_world(async_client, db_session)
    mine = RoomPoint(owner_id=w.owner.id, project_id=w.project.id, room_id=w.salon.id, price_item_id=w.point.id, quantity=Decimal("1.00"), position=0)
    manual_calc = MaterialCalc(owner_id=w.owner.id, project_id=w.project.id, room_id=w.salon.id, package="ELECTRIC", params={"sockets": 1}, position=0)
    db_session.add_all([mine, manual_calc])
    await db_session.commit()
    done = await post(async_client, w, "", {"own": "ADD"})  # "add next to it": the owner's rows stay (the default REPLACE is tested in test_transfer_own_rows.py)
    assert done.status_code == 200, done.text
    assert done.json() == {"points_added": 4, "points_changed": 0, "points_removed": 0, "materials_added": 2, "materials_changed": 0, "materials_removed": 0}
    rows = await points(db_session)
    carried = [r for r in rows if r.source == "TRADE_LINK"]
    assert len(rows) == 5 and len(carried) == 4
    salon_point = next(r for r in carried if r.room_id == w.salon.id and r.price_item_id == w.point.id)
    assert salon_point.quantity == Decimal("8.00") and salon_point.note == "przy TV · przy drzwiach"
    await db_session.refresh(mine)
    assert mine.quantity == Decimal("1.00") and mine.source is None  # the owner's own row with the same item stays as it was
    made = [c for c in await calcs(db_session) if c.source == "TRADE_LINK"]
    assert len(made) == 2
    salon_calc = next(c for c in made if c.room_id == w.salon.id)
    assert salon_calc.package == "ELECTRIC" and salon_calc.title is None
    assert salon_calc.params["sockets"] == 6 and salon_calc.params["circuits"] == 2 and Decimal(str(salon_calc.params["route_m"])) == Decimal("12.5")
    await db_session.refresh(manual_calc)
    assert manual_calc.source is None and manual_calc.params == {"sockets": 1}


async def test_a_second_carrying_over_adds_nothing_and_the_preview_then_says_same(async_client, db_session):
    w = await electric_world(async_client, db_session)
    await post(async_client, w, "")
    again = await post(async_client, w, "")
    assert again.json() == {"points_added": 0, "points_changed": 0, "points_removed": 0, "materials_added": 0, "materials_changed": 0, "materials_removed": 0}
    assert len(await points(db_session)) == 4 and len(await calcs(db_session)) == 2
    body = (await post(async_client, w, "/preview")).json()
    assert {r["kind"] for room in body["rooms"] for r in room["rows"]} == {"SAME"} and {room["material"]["kind"] for room in body["rooms"]} == {"SAME"}


async def test_a_corrected_answer_changes_the_carried_rows_and_zero_takes_them_away(async_client, db_session):
    w = await electric_world(async_client, db_session)
    await post(async_client, w, "")
    for row in (await db_session.execute(select(TradeAnswer).where(TradeAnswer.position_key == "SOCKET", TradeAnswer.room_id == w.salon.id))).scalars():
        row.quantity = Decimal(4)
    for row in (await db_session.execute(select(TradeAnswer).where(TradeAnswer.position_key == "LIGHT_POINT"))).scalars():
        row.quantity = Decimal(0)
    await db_session.commit()
    body = (await post(async_client, w, "/preview")).json()
    salon = next(r for r in body["rooms"] if r["room_id"] == str(w.salon.id))
    kinds = {(r["item_id"], r["kind"]): r for r in salon["rows"]}
    changed = kinds[(str(w.point.id), "CHANGE")]
    assert (changed["was_quantity"], changed["quantity"]) == ("8.00", "6.00") and kinds[(str(w.light.id), "REMOVE")]["quantity"] == "3.00"
    assert salon["material"]["kind"] == "CHANGE"
    done = (await post(async_client, w, "")).json()
    assert (done["points_changed"], done["points_removed"], done["materials_changed"]) == (1, 1, 1)
    salon_point = next(r for r in await points(db_session) if r.room_id == w.salon.id and r.price_item_id == w.point.id)
    assert salon_point.quantity == Decimal("6.00")
    assert not [r for r in await points(db_session) if r.price_item_id == w.light.id]
    calc = next(c for c in await calcs(db_session) if c.room_id == w.salon.id)
    assert calc.params["sockets"] == 4 and calc.params["lights"] == 0


async def test_when_everything_is_zero_the_carried_things_go_and_the_owners_own_stay(async_client, db_session):
    w = await electric_world(async_client, db_session)
    mine = RoomPoint(owner_id=w.owner.id, project_id=w.project.id, room_id=w.kuchnia.id, price_item_id=w.point.id, quantity=Decimal("2.00"), position=0)
    db_session.add(mine)
    await db_session.commit()
    await post(async_client, w, "", {"own": "ADD"})
    for row in (await db_session.execute(select(TradeAnswer))).scalars():
        row.quantity = Decimal(0)
    await db_session.commit()
    done = (await post(async_client, w, "", {"own": "ADD"})).json()
    assert done["points_removed"] == 4 and done["materials_removed"] == 2
    left = await points(db_session)
    assert [r.id for r in left] == [mine.id] and await calcs(db_session) == []


async def test_the_options_points_only_and_materials_only(async_client, db_session):
    w = await electric_world(async_client, db_session)
    only_points = (await post(async_client, w, "", {"materials": False})).json()
    assert only_points["points_added"] == 4 and only_points["materials_added"] == 0 and await calcs(db_session) == []
    only_materials = (await post(async_client, w, "", {"points": False})).json()
    assert only_materials["points_added"] == 0 and only_materials["materials_added"] == 2 and len(await points(db_session)) == 4


async def test_the_circuits_reach_the_materials_even_with_no_item_and_a_position_without_an_item_makes_no_row(async_client, db_session):
    w = await electric_world(async_client, db_session)
    done = (await post(async_client, w, "", {"mapping": {"SOCKET": None, "SWITCH": None, "LIGHT_POINT": None, "CABLE_ROUTE": None}})).json()
    assert done["points_added"] == 0 and done["materials_added"] == 2 and await points(db_session) == []


async def test_numbers_that_a_calculation_cannot_hold_are_refused_and_nothing_is_written(async_client, db_session):
    w = await electric_world(async_client, db_session)
    await answer(db_session, w, w.kuchnia, "CIRCUIT", 150)  # a calculation takes at most 100 circuits
    body = (await post(async_client, w, "/preview")).json()
    kuchnia = next(r for r in body["rooms"] if r["room_id"] == str(w.kuchnia.id))
    assert kuchnia["material"]["kind"] == "INVALID"
    refused = await post(async_client, w, "")
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "TRANSFER_MATERIALS_INVALID"
    assert await points(db_session) == [] and await calcs(db_session) == []
    assert (await post(async_client, w, "", {"materials": False})).status_code == 200  # the points may still go


async def test_with_no_answer_there_is_nothing_to_carry_over(async_client, db_session):
    w = await owner_world(async_client, db_session)
    w.url = f"{w.base}/ELECTRIC/transfer"
    assert (await post(async_client, w, "/preview")).json()["nothing"] is True
    refused = await post(async_client, w, "")
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "TRANSFER_NOTHING"


async def test_the_plumber_has_his_own_positions_and_does_not_touch_the_electricians_rows(async_client, db_session):
    w = await electric_world(async_client, db_session)
    water = await item(db_session, w.owner.id, "Punkt wodny", category=PriceCategory.PLUMBING)
    await item(db_session, w.owner.id, "Trasa rurowa", PriceUnit.LM, PriceCategory.PLUMBING)
    await post(async_client, w, "")
    await answer(db_session, w, w.salon, "WATER_POINT", 3, trade="PLUMBING")
    await answer(db_session, w, w.salon, "MANIFOLD_OUT", 4, trade="PLUMBING")
    await answer(db_session, w, w.salon, "PIPE_ROUTE", Decimal(9), trade="PLUMBING", unit="LM")
    w.url = f"{w.base}/PLUMBING/transfer"
    done = (await post(async_client, w, "")).json()
    assert done["points_added"] == 2 and done["points_removed"] == 0 and done["materials_added"] == 1
    assert len(await points(db_session)) == 6
    plumbing = next(c for c in await calcs(db_session) if c.package == "PLUMBING")
    assert plumbing.params["water_points"] == 3 and plumbing.params["manifold_outlets"] == 4 and Decimal(str(plumbing.params["pipe_m"])) == Decimal(9)
    assert any(r.price_item_id == water.id and r.quantity == Decimal("3.00") for r in await points(db_session))
    # the electrician again: his rows are still all there
    w.url = f"{w.base}/ELECTRIC/transfer"
    assert (await post(async_client, w, "")).json()["points_removed"] == 0


async def test_only_the_owner_of_the_object_may_carry_over_and_an_unknown_trade_is_refused(async_client, db_session):
    w = await electric_world(async_client, db_session)
    assert (await async_client.post(w.url, json={})).status_code == 401
    assert (await async_client.post(w.url + "/preview", json={})).status_code == 401
    stranger = await login(async_client, OTHER_USER)
    assert (await async_client.post(w.url, json={}, headers=stranger)).status_code == 404
    assert (await async_client.post(w.url + "/preview", json={}, headers=stranger)).status_code == 404
    bad = await async_client.post(f"{w.base}/TILE/transfer", json={}, headers=w.headers)
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "UNKNOWN_TRADE"
    assert (await async_client.post(w.url, json={"mapping": {"SOCKET": "not-a-uuid"}}, headers=w.headers)).status_code == 422
    assert (await async_client.post(w.url, json={"surprise": 1}, headers=w.headers)).status_code == 422
    assert await points(db_session) == []


# --- the migration ----------------------------------------------------------------------------------------------------------------


def engine_0086():
    engine = contract_engine()
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE room_points (id CHAR(32) PRIMARY KEY, note TEXT)"))
        conn.execute(text("CREATE TABLE material_calcs (id CHAR(32) PRIMARY KEY, title TEXT)"))
        conn.execute(text("INSERT INTO room_points (id) VALUES ('a')"))
        conn.execute(text("INSERT INTO material_calcs (id) VALUES ('b')"))
    run(engine, "0086_transfer_source", "upgrade")
    return engine


def test_revision_chain_and_length():
    module = load_migration("0086_transfer_source")
    assert module.revision == "0086_transfer_source" and module.down_revision == "0085_trade_links" and len(module.revision) <= 32


def test_the_migration_adds_a_nullable_label_and_the_downgrade_drops_it_leaving_the_rows():
    from sqlalchemy import inspect

    engine = engine_0086()
    for table in ("room_points", "material_calcs"):
        column = next(c for c in inspect(engine).get_columns(table) if c["name"] == "source")
        assert column["nullable"] is True
    with engine.connect() as conn:
        assert conn.execute(text("SELECT source FROM room_points")).scalar() is None
    run(engine, "0086_transfer_source", "downgrade")
    assert "source" not in {c["name"] for c in inspect(engine).get_columns("room_points")}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM room_points")).scalar() == 1 and conn.execute(text("SELECT count(*) FROM material_calcs")).scalar() == 1
    run(engine, "0086_transfer_source", "upgrade")
