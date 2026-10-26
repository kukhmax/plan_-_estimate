"""V2-12 -- the arithmetic of the materials of the electrician and of the plumber (pure, hand-counted numbers; docs/V2_12_PLAN_RU.md)."""
from decimal import Decimal as D

from app.domain.data.material_norms import BY_CODE, MATERIAL, NORMS, PARAM
from app.domain.rules import materials as m

NORMS_START = {n.code: n.default for n in NORMS if n.kind == PARAM}


def by_code(items):
    return {i.code: i for i in items}


def electric(**over):
    return by_code(m.electric_materials(m.ElectricInput(**over), NORMS_START))


def plumbing(**over):
    return by_code(m.plumbing_materials(m.PlumbingInput(**over), NORMS_START))


def count(item):
    return m.packs(item.quantity, item.pack_size)


def test_the_reference_has_the_materials_of_both_trades_and_the_formulas_read_only_what_it_has():
    assert {n.code for n in NORMS if n.kind == MATERIAL and n.package == "ELECTRIC"} == {
        "ELEC_CABLE", "ELEC_CONDUIT", "ELEC_FLUSH_BOX", "ELEC_SOCKETS", "ELEC_SWITCHES", "ELEC_BREAKERS", "ELEC_JBOX", "ELEC_TERMINALS",
    }
    assert {n.code for n in NORMS if n.kind == MATERIAL and n.package == "PLUMBING"} == {
        "PL_PIPE", "PL_FITTINGS", "PL_VALVES", "PL_MANIFOLD", "PL_CLIPS", "PL_DRAIN_PIPE", "PL_DRAIN_FITTINGS",
    }
    made = [*electric(sockets=1, switches=1, lights=1, circuits=1).values(), *plumbing(water_points=1, drain_points=1, manifold_outlets=1).values()]
    assert {i.code for i in made} == {n.code for n in NORMS if n.kind == MATERIAL and n.package in ("ELECTRIC", "PLUMBING")}
    assert all(BY_CODE[i.code].kind == MATERIAL and BY_CODE[i.code].billing_unit == "PCS" for i in made)
    assert all(n.minimum <= n.default <= n.maximum for n in NORMS if n.kind == PARAM)


def test_an_electrical_room_counted_from_its_points():
    found = electric(sockets=4, switches=2, lights=3, circuits=2)
    # the cable: 4 * 6 + 2 * 4 + 3 * 5 = 47 m, 10 % waste
    assert found["ELEC_CABLE"].quantity == D("51.7") and found["ELEC_CABLE"].unit_text == "m" and count(found["ELEC_CABLE"]) == 1  # a coil of 100 m
    assert found["ELEC_CONDUIT"].quantity == D("51.7") and count(found["ELEC_CONDUIT"]) == 2  # 100 % of the cable, coils of 50 m
    assert found["ELEC_FLUSH_BOX"].quantity == D(6) and found["ELEC_SOCKETS"].quantity == D(4) and found["ELEC_SWITCHES"].quantity == D(2)
    assert found["ELEC_BREAKERS"].quantity == D(2) and found["ELEC_JBOX"].quantity == D(2)
    assert found["ELEC_TERMINALS"].quantity == D(27) and count(found["ELEC_TERMINALS"]) == 1  # 9 points * 3, packs of 50


def test_the_length_of_the_routes_replaces_the_length_counted_from_the_points():
    found = electric(sockets=4, switches=2, lights=3, circuits=1, route_m=D(30))
    assert found["ELEC_CABLE"].quantity == D(33) and found["ELEC_CONDUIT"].quantity == D(33)
    assert found["ELEC_SOCKETS"].quantity == D(4)  # the points are still counted
    routes_only = electric(route_m=D(20))
    assert set(routes_only) == {"ELEC_CABLE", "ELEC_CONDUIT"} and routes_only["ELEC_CABLE"].quantity == D(22)


def test_what_is_not_needed_is_not_made():
    found = electric(sockets=1)
    assert set(found) == {"ELEC_CABLE", "ELEC_CONDUIT", "ELEC_FLUSH_BOX", "ELEC_SOCKETS", "ELEC_TERMINALS"}  # no switches, no breakers, no junction boxes
    assert found["ELEC_CABLE"].quantity == D("6.6")
    assert electric() == {} and plumbing() == {}


def test_a_plumbed_room_counted_from_its_points():
    found = plumbing(water_points=3, drain_points=2, manifold_outlets=4)
    assert found["PL_PIPE"].quantity == D("13.2") and count(found["PL_PIPE"]) == 1  # 3 * 4 m, 10 % waste, a coil of 100 m
    assert found["PL_FITTINGS"].quantity == D(12) and found["PL_VALVES"].quantity == D(3) and found["PL_MANIFOLD"].quantity == D(4)
    assert found["PL_CLIPS"].quantity == D(24) and count(found["PL_CLIPS"]) == 1  # 12 m, 2 per metre (no waste), packs of 100
    assert found["PL_DRAIN_PIPE"].quantity == D(4) and count(found["PL_DRAIN_PIPE"]) == 2  # 2 points * 2 m, bars of 2 m
    assert found["PL_DRAIN_FITTINGS"].quantity == D(6)


def test_the_length_of_the_pipe_replaces_the_length_counted_from_the_points():
    found = plumbing(water_points=3, pipe_m=D(50))
    assert found["PL_PIPE"].quantity == D(55) and count(found["PL_PIPE"]) == 1
    assert found["PL_CLIPS"].quantity == D(100) and count(found["PL_CLIPS"]) == 1  # exactly one pack
    assert found["PL_FITTINGS"].quantity == D(12)  # the points are still counted
    assert "PL_DRAIN_PIPE" not in found and "PL_MANIFOLD" not in found


def test_the_packs_of_an_object_are_made_once_over_the_sum_of_its_rooms():
    one = electric(sockets=4, switches=2, lights=3, circuits=2)
    two = electric(sockets=4, switches=2, lights=3, circuits=2)
    totals = {t.code: t for t in m.total([one.values(), two.values()])}
    assert totals["ELEC_CABLE"].quantity == D("103.4") and totals["ELEC_CABLE"].packs == 2  # one coil each would be 2, but 103.4 / 100 also needs 2
    assert totals["ELEC_TERMINALS"].quantity == D(54) and totals["ELEC_TERMINALS"].packs == 2  # 27 + 27: two packs of 50 -- one pack per room would be two as well
    third = electric(sockets=1)
    summed = {t.code: t for t in m.total([electric(sockets=4).values(), third.values()])}
    assert summed["ELEC_TERMINALS"].quantity == D(15) and summed["ELEC_TERMINALS"].packs == 1  # 12 + 3 in one pack, not two
