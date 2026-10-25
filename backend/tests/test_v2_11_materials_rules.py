"""V2-11 -- the arithmetic of the materials of a tile and of a drywall (pure, hand-counted numbers; docs/V2_11_PLAN_RU.md)."""
from decimal import Decimal as D

import pytest
from app.domain.data.material_norms import BY_CODE, MATERIAL, NORMS, PARAM
from app.domain.rules import materials as m

NORMS_START = {n.code: n.default for n in NORMS if n.kind == PARAM}


def by_code(items):
    return {i.code: i for i in items}


def tile(**over):
    base = dict(area_m2=D(10), length_cm=D(30), width_cm=D(60), thickness_mm=D(8), joint_mm=D(3))
    base.update(over)
    return by_code(m.tile_materials(m.TileInput(**base), NORMS_START))


def test_the_reference_has_every_number_the_formulas_read_and_every_material_they_make():
    assert {n.code for n in NORMS if n.kind == MATERIAL} == {
        "TILE_TILES", "TILE_ADHESIVE", "TILE_GROUT", "TILE_WATERPROOF", "TILE_WATERPROOF_TAPE", "TILE_SPACERS",
        "GK_SHEETS", "GK_UD", "GK_CD", "GK_HANGERS", "GK_SCREWS", "GK_FILLER", "GK_TAPE",
    }
    for item in (*tile(waterproof=True, tape_m=D(5)).values(), *by_code(m.drywall_materials(m.DrywallInput(True, D(10), 1, None, D(12)), NORMS_START)).values(),
                 *by_code(m.drywall_materials(m.DrywallInput(False, D(10), 1, D(2.6)), NORMS_START)).values()):
        assert item.code in BY_CODE and BY_CODE[item.code].kind == MATERIAL
    assert all(n.minimum <= n.default <= n.maximum for n in NORMS if n.kind == PARAM)
    assert all(n.billing_unit in ("M2", "PCS", "LM") for n in NORMS if n.kind == MATERIAL)


def test_a_tile_of_30_by_60_on_ten_metres():
    found = tile(waterproof=True, tape_m=D(12))
    assert found["TILE_TILES"].quantity == D("11.00") and found["TILE_TILES"].pieces == 62  # 10 m2 and 10 % waste; 11 / 0.18 = 61.1 -> 62 tiles
    assert found["TILE_ADHESIVE"].quantity == D(50) and m.packs(found["TILE_ADHESIVE"].quantity, found["TILE_ADHESIVE"].pack_size) == 2  # the long side 60 cm: 5 kg/m2; 25 kg bags
    assert found["TILE_GROUT"].quantity == D("2.208") and found["TILE_GROUT"].pack_size == D(5)  # (300 + 600) / (300 * 600) * 3 * 8 * 1.6 * 1.15 per m2
    assert found["TILE_SPACERS"].quantity == D(62) and found["TILE_SPACERS"].pack_size == D(200)
    assert found["TILE_WATERPROOF"].quantity == D(30) and found["TILE_WATERPROOF"].pack_size == D(15)  # 10 m2 * 1.5 kg * 2 layers
    assert found["TILE_WATERPROOF_TAPE"].quantity == D(12) and found["TILE_WATERPROOF_TAPE"].pack_size == D(10)


def test_the_diagonal_has_its_own_waste_and_the_adhesive_follows_the_size_of_the_tile():
    big = tile(length_cm=D(80), width_cm=D(80), diagonal=True)
    assert big["TILE_TILES"].quantity == D("11.50") and big["TILE_TILES"].pieces == 18  # 15 %; 11.5 / 0.64 = 17.97
    assert big["TILE_ADHESIVE"].quantity == D(70)  # above 60 cm: 7 kg/m2
    assert tile(length_cm=D(30), width_cm=D(30))["TILE_ADHESIVE"].quantity == D(35)  # up to 30 cm: 3.5 kg/m2
    assert tile(length_cm=D("30.1"), width_cm=D(30))["TILE_ADHESIVE"].quantity == D(50)  # just above: the next class


def test_the_grout_follows_the_joint_and_the_thickness():
    one = tile(area_m2=D(1), length_cm=D(30), width_cm=D(30), joint_mm=D(2), thickness_mm=D(8))["TILE_GROUT"].quantity
    assert one.quantize(D("0.0001")) == D("0.1963")  # 600 / 90000 * 2 * 8 * 1.6 * 1.15
    wider = tile(area_m2=D(1), length_cm=D(30), width_cm=D(30), joint_mm=D(4), thickness_mm=D(8))["TILE_GROUT"].quantity
    assert wider.quantize(D("0.000001")) == (one * 2).quantize(D("0.000001"))


def test_the_waterproofing_is_asked_for_and_its_area_may_differ_from_the_tiled_one():
    assert "TILE_WATERPROOF" not in tile() and "TILE_WATERPROOF_TAPE" not in tile()
    assert "TILE_WATERPROOF_TAPE" not in tile(waterproof=True)  # no tape length given
    found = tile(waterproof=True, waterproof_area_m2=D(4), tape_m=D(0))
    assert found["TILE_WATERPROOF"].quantity == D(12) and "TILE_WATERPROOF_TAPE" not in found


def test_a_wall_of_drywall_in_two_layers():
    found = by_code(m.drywall_materials(m.DrywallInput(False, D(13), 2, D("2.6")), NORMS_START))
    assert found["GK_SHEETS"].quantity == D("28.6") and m.packs(found["GK_SHEETS"].quantity, found["GK_SHEETS"].pack_size) == 10  # 13 * 2 * 1.1 / 3 = 9.53
    assert found["GK_UD"].quantity == D(11) and m.packs(found["GK_UD"].quantity, found["GK_UD"].pack_size) == 4  # 2 * 13 / 2.6 = 10 m, 10 % waste, 3 m pieces
    assert found["GK_CD"].quantity.quantize(D("0.0001")) == D("26.6933") and m.packs(found["GK_CD"].quantity, found["GK_CD"].pack_size) == 9  # (13 / 0.6 + 2.6) * 1.1
    assert found["GK_SCREWS"].quantity == D(650) and m.packs(found["GK_SCREWS"].quantity, found["GK_SCREWS"].pack_size) == 1
    assert found["GK_FILLER"].quantity == D("6.5") and found["GK_TAPE"].quantity == D("19.5")
    assert "GK_HANGERS" not in found


def test_a_ceiling_of_drywall_has_hangers_and_its_own_profiles():
    found = by_code(m.drywall_materials(m.DrywallInput(True, D(10), 1, None, D(12)), NORMS_START))
    assert found["GK_SHEETS"].quantity == D("11.0") and m.packs(found["GK_SHEETS"].quantity, found["GK_SHEETS"].pack_size) == 4
    assert found["GK_UD"].quantity == D("13.2") and m.packs(found["GK_UD"].quantity, found["GK_UD"].pack_size) == 5  # the perimeter
    assert found["GK_CD"].quantity == D("33.0") and m.packs(found["GK_CD"].quantity, found["GK_CD"].pack_size) == 11  # 3 m per m2
    assert found["GK_HANGERS"].quantity == D("15.0") and m.packs(found["GK_HANGERS"].quantity, found["GK_HANGERS"].pack_size) == 15


def test_a_wall_needs_its_height_and_a_ceiling_its_perimeter():
    with pytest.raises(ValueError):
        m.drywall_materials(m.DrywallInput(False, D(10), 1, None, None), NORMS_START)
    with pytest.raises(ValueError):
        m.drywall_materials(m.DrywallInput(False, D(10), 1, D(0), None), NORMS_START)
    with pytest.raises(ValueError):
        m.drywall_materials(m.DrywallInput(True, D(10), 1, None, None), NORMS_START)


def test_a_changed_norm_changes_the_result():
    edited = {**NORMS_START, "TILE_WASTE_STRAIGHT": D(20), "TILE_ADHESIVE_KG_M2_MEDIUM": D(6)}
    found = by_code(m.tile_materials(m.TileInput(D(10), D(30), D(60)), edited))
    assert found["TILE_TILES"].quantity == D("12.00") and found["TILE_ADHESIVE"].quantity == D(60)


def test_packs_are_whole_and_rounded_up_and_nothing_is_no_pack():
    assert m.packs(D("25"), D(25)) == 1 and m.packs(D("25.001"), D(25)) == 2 and m.packs(D(0), D(25)) == 0 and m.packs(D("0.0001"), D(25)) == 1


def test_the_packs_of_an_object_are_made_once_over_the_sum_of_its_calculations():
    one = m.tile_materials(m.TileInput(D(6), D(30), D(60)), NORMS_START)  # 30 kg of adhesive: 2 bags
    two = m.tile_materials(m.TileInput(D(6), D(30), D(60)), NORMS_START)
    totals = {t.code: t for t in m.total([one, two])}
    assert totals["TILE_ADHESIVE"].quantity == D(60) and totals["TILE_ADHESIVE"].packs == 3  # not 2 + 2
    assert totals["TILE_TILES"].packs is None and totals["TILE_TILES"].billing_quantity == D("13.20") and totals["TILE_TILES"].quantity == D("13.20")
    assert totals["TILE_TILES"].pieces == 74  # 37 tiles in each calculation (36.7 rounded up), as counted
    assert totals["TILE_ADHESIVE"].billing_quantity == D(3)
    assert [t.code for t in m.total([])] == []
