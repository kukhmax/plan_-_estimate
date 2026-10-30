"""Floor technology (owner 2026-10-30): a floor is inspected for the covering it is prepared for, and its risks, technical basis, phrases
and works are the floor's own (`floor_rules.py`, `docs/FLOOR_TECH_RESEARCH_RU.md`)."""
import json
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.domain.data.checklist_templates import build_baseline_templates
from app.domain.data.communication_phrases import build_baseline_communication_phrases, risk_phrase_code
from app.domain.data.floor_rules import FLOOR_RULE_CODES, FLOOR_WORK_CODES, build_floor_rules
from app.domain.data.price_book_seed import build_approved_price_book_items
from app.domain.data.risk_rules import build_baseline_risk_rules
from app.domain.data.work_recommendation_rules import build_baseline_work_recommendation_rules, recommended_work_allows_target
from app.domain.knowledge.catalog import load_knowledge_catalog
from app.models.work_recommendation import WorkRecommendationTargetKind
from tests.test_canonical_planes import auth_header
from tests.test_communications import _complete, _evaluate_risks, _put_answers, _scaffold
from tests.test_inspections import inspections_url, question_by_key

ROOT = Path(__file__).resolve().parents[2]
FLOOR_V2 = {"substrate-screed": "SCREED", "substrate-old-tile": "OLD_TILE", "substrate-wood-boards": "WOOD_BOARDS",
            "floor-concrete": "CONCRETE", "floor-other": "OTHER"}
WALL_RULES = {rule.code for rule in build_baseline_risk_rules()} - set(FLOOR_RULE_CODES)


# --- the catalogue ----------------------------------------------------------------------------------------------------------------


def test_every_floor_checklist_has_a_version_2_that_asks_for_the_covering_and_records_floor_only_findings():
    templates = {(t.code, t.version): t for t in build_baseline_templates()}
    wall_keys = {c.finding_key for r in build_baseline_risk_rules() if r.code in WALL_RULES for c in r.conditions if c.finding_key}
    for code in FLOOR_V2:
        template = templates[(code, 2)]
        assert [s.key for s in template.sections][:2] == ["floor_target", "floor_conditions"]
        finish = next(q for q in template.sections[0].questions if q.key == "planned_finish")
        assert {o.key for o in finish.options} == {"TILES", "LARGE_TILES", "MICROCEMENT", "LAMINATE", "WOOD", "VINYL", "UNKNOWN"}
        keys = {q.finding_key for s in template.sections for q in s.questions if q.finding_key}
        keys |= {o.finding_key for s in template.sections for q in s.questions for o in q.options if o.finding_key}
        assert not keys & wall_keys, f"{code} v2 would fire a wall rule: {keys & wall_keys}"
    assert ("floor-painted", 1) not in templates and ("floor-painted", 2) not in templates  # no old paint on a floor


def test_the_floor_rules_read_only_floor_findings_and_target_the_floor():
    for floor in build_floor_rules():
        targets = [c.value for c in floor.rule.conditions if c.operator.value == "TARGET_IN"]
        assert targets == [{"values": ["FLOOR"]}], floor.rule.code
    assert len(FLOOR_RULE_CODES) == 40 and len(set(FLOOR_RULE_CODES)) == 40


def test_every_floor_rule_has_its_words_in_four_languages_and_in_the_polish_report():
    locales = {code: json.loads((ROOT / "frontend" / "src" / "locales" / f"{code}.json").read_text(encoding="utf-8")) for code in ("pl", "ru", "uk", "en")}
    report = json.loads((ROOT / "backend" / "app" / "domain" / "documents" / "catalog" / "risk_texts_pl.json").read_text(encoding="utf-8"))
    for code in FLOOR_RULE_CODES:
        slug = code.lower()
        for lang, words in locales.items():
            texts = words["risk"][slug]
            assert set(texts) == {"title", "explanation", "consequence", "mitigation", "communication"}, (lang, code)
            assert all(texts.values()), (lang, code)
        for field in ("title", "explanation", "consequence", "communication"):
            assert report[f"risk.{slug}.{field}"] == locales["pl"]["risk"][slug][field]


def test_every_floor_rule_has_a_phrase_for_the_client_and_its_technical_basis():
    phrases = {p.code: p for p in build_baseline_communication_phrases()}
    catalog = load_knowledge_catalog()
    linked = {link.target: link.entries for link in catalog.links if link.target_kind == "RISK"}
    entries = {e.code: e for e in catalog.entries}
    for code in FLOOR_RULE_CODES:
        assert phrases[risk_phrase_code(code)].risk_code == code
        if code in ("FLOOR_SURFACE_DUSTY", "FLOOR_SURFACE_OILY"):
            continue  # plain preparation: no technical basis of its own
        assert linked[code], code
        # the floor never points at the plaster / skim coat / glass fleece entries of the walls
        assert not set(linked[code]) & {"TECH.FLATNESS", "TECH.FLEECE", "TECH.MOISTURE", "TECH.GK-SYSTEM"}, code
        assert all(entries[e].status == "DRAFT" for e in linked[code] if e.startswith("TECH."))


def test_the_floor_works_are_in_the_catalogue_without_a_price_and_are_recommended_for_a_floor_only():
    items = {i.code: i for i in build_approved_price_book_items()}
    assert len(items) == 63
    rules = build_baseline_work_recommendation_rules()
    for code in FLOOR_WORK_CODES:
        assert items[code].price is None
        assert recommended_work_allows_target(code, WorkRecommendationTargetKind.FLOOR)
        assert not recommended_work_allows_target(code, WorkRecommendationTargetKind.WALL)
        assert any(r.recommended_work_code == code for r in rules)
    # the wall works are still never recommended for a floor
    for code in ("CENNIK_PRIM_STD-01", "CENNIK_SKIM_LOCAL-01", "CENNIK_SKIM_CRACK-01"):
        assert not recommended_work_allows_target(code, WorkRecommendationTargetKind.FLOOR)


# --- through the API ----------------------------------------------------------------------------------------------------------------


async def _floor(async_client: AsyncClient, substrate: str, answers: dict[str, dict]) -> set[str]:
    token, project, room = await _scaffold(async_client)
    listed = await async_client.get("/api/checklist-templates", params={"substrate": substrate, "for_floor": "true"}, headers=auth_header(token))
    assert listed.status_code == 200 and listed.json()["total"] == 1, listed.text
    template = (await async_client.get(f"/api/checklist-templates/{listed.json()['items'][0]['id']}", headers=auth_header(token))).json()
    assert template["version"] == 2
    created = await async_client.post(inspections_url(project["id"], room["id"]),
                                      json={"template_id": template["id"], "substrate": substrate, "plane": "FLOOR"}, headers=auth_header(token))
    assert created.status_code == 201, created.text
    inspection = created.json()
    await _put_answers(async_client, token, project, room, inspection, template, answers)
    assert (await _complete(async_client, token, project, room, inspection)).status_code == 200
    risks = await _evaluate_risks(async_client, token, project, room, inspection)
    return {r["rule_code"] for r in risks["items"]}


async def test_a_screed_under_tiles_too_moist_and_too_uneven_gets_the_floor_risks_and_no_wall_risk(async_client: AsyncClient):
    codes = await _floor(async_client, "SCREED", {
        "planned_finish": {"option_key": "TILES"},
        "underfloor_heating": {"value_bool": False},
        "floor_moisture_measured": {"value_number": "2.5"},
        "floor_flatness_mm": {"value_number": "4"},
        "cracks_present": {"value_bool": True},
        "screed_hollow": {"value_bool": True},
    })
    assert codes == {"FLOOR_MOISTURE_CEMENT", "FLOOR_FLATNESS_TILES", "FLOOR_CRACK_REPAIR", "FLOOR_SCREED_HOLLOW"}
    assert not codes & WALL_RULES


@pytest.mark.parametrize(
    ("answers", "expected"),
    [
        # the limit itself passes: 2.0 % CM on a cement screed, 3 mm under tiles
        ({"planned_finish": {"option_key": "TILES"}, "floor_moisture_measured": {"value_number": "2.0"}, "floor_flatness_mm": {"value_number": "3"}}, set()),
        # underfloor heating lowers the moisture limit to 1.8 %
        ({"planned_finish": {"option_key": "LAMINATE"}, "underfloor_heating": {"value_bool": True}, "floor_moisture_measured": {"value_number": "1.9"}},
         {"FLOOR_MOISTURE_CEMENT_HEATED", "FLOOR_LAMINATE_VAPOUR"}),
        # anhydrite: 0.5 %
        ({"screed_type": {"option_key": "ANHYDRITE"}, "floor_moisture_measured": {"value_number": "0.6"}}, {"FLOOR_MOISTURE_ANHYDRITE"}),
        # the covering decides the flatness: 2.5 mm is fine for laminate, too much for glued vinyl and large tiles
        ({"planned_finish": {"option_key": "LAMINATE"}, "floor_flatness_mm": {"value_number": "2.5"}}, {"FLOOR_LAMINATE_VAPOUR"}),
        ({"planned_finish": {"option_key": "VINYL"}, "floor_flatness_mm": {"value_number": "2.5"}}, {"FLOOR_FLATNESS_VINYL", "FLOOR_VINYL_SMOOTHING"}),
        ({"planned_finish": {"option_key": "LARGE_TILES"}, "floor_flatness_mm": {"value_number": "2.5"}}, {"FLOOR_FLATNESS_LARGE_TILES", "FLOOR_LARGE_TILES_BED"}),
        # no covering chosen: only a large unevenness (> 5 mm) is a risk
        ({"planned_finish": {"option_key": "UNKNOWN"}, "floor_flatness_mm": {"value_number": "4"}}, set()),
        ({"floor_flatness_mm": {"value_number": "6"}, "floor_level_deviation_mm": {"value_number": "8"}}, {"FLOOR_FLATNESS_GENERAL", "FLOOR_LEVEL_OUT"}),
        # wet zone: waterproofing under tiles and microcement, a decision of the client for laminate
        ({"planned_finish": {"option_key": "TILES"}, "wet_zone": {"value_bool": True}}, {"FLOOR_WET_ZONE_TILES"}),
        ({"planned_finish": {"option_key": "MICROCEMENT"}, "wet_zone": {"value_bool": True}, "cracks_present": {"value_bool": True}},
         {"FLOOR_WET_ZONE_MICROCEMENT", "FLOOR_MICROCEMENT_PREP", "FLOOR_CRACK_MICROCEMENT"}),
        ({"planned_finish": {"option_key": "LAMINATE"}, "wet_zone": {"value_bool": True}}, {"FLOOR_WET_ZONE_LAMINATE", "FLOOR_LAMINATE_VAPOUR"}),
        # expansion joints, harder with heating; a weak surface does not matter under a floating laminate
        ({"expansion_joints_missing": {"value_bool": True}, "underfloor_heating": {"value_bool": True}}, {"FLOOR_EXPANSION_JOINTS_HEATED"}),
        ({"planned_finish": {"option_key": "WOOD"}, "floor_weak_surface": {"value_bool": True}, "substrate_condition": {"option_key": "DUSTY"}},
         {"FLOOR_SURFACE_WEAK", "FLOOR_SURFACE_DUSTY"}),
        ({"planned_finish": {"option_key": "LAMINATE"}, "floor_weak_surface": {"value_bool": True}}, {"FLOOR_LAMINATE_VAPOUR"}),
    ],
)
async def test_the_covering_and_the_screed_decide_which_floor_risks_fire(async_client: AsyncClient, answers, expected):
    assert await _floor(async_client, "SCREED", answers) == expected


async def test_old_tiles_and_boards_get_their_own_floor_risks(async_client: AsyncClient):
    assert await _floor(async_client, "OLD_TILE", {
        "planned_finish": {"option_key": "TILES"}, "tiles_hollow": {"value_bool": True}, "tiles_glazed": {"value_bool": True},
        "tiles_layers": {"option_key": "TWO"},
    }) == {"FLOOR_OLD_TILES_HOLLOW", "FLOOR_OLD_TILES_BOND", "FLOOR_OLD_TILES_LAYERS"}
    assert await _floor(async_client, "WOOD_BOARDS", {
        "planned_finish": {"option_key": "TILES"}, "boards_flex": {"value_bool": True}, "wood_decay": {"value_bool": True},
        "floor_moisture_measured": {"value_number": "14"},
    }) == {"FLOOR_BOARDS_FLEX", "FLOOR_WOOD_DECAY", "FLOOR_BOARDS_UNDER_TILES", "FLOOR_WOOD_MOISTURE"}


async def test_a_concrete_floor_gets_the_floor_checklist_and_the_cement_limit(async_client: AsyncClient):
    assert await _floor(async_client, "CONCRETE", {
        "planned_finish": {"option_key": "WOOD"}, "floor_moisture_measured": {"value_number": "2.4"},
    }) == {"FLOOR_MOISTURE_CEMENT"}


async def test_a_wall_keeps_its_wall_risks_and_never_gets_a_floor_one(async_client: AsyncClient):
    from tests.test_communications import _scaffold_inspection

    token, project, room, inspection, template = await _scaffold_inspection(async_client, substrate="CONCRETE", plane="CEILING", quality_target="S2")
    await _put_answers(async_client, token, project, room, inspection, template, {"cracks_present": {"value_bool": True}})
    assert (await _complete(async_client, token, project, room, inspection)).status_code == 200
    codes = {r["rule_code"] for r in (await _evaluate_risks(async_client, token, project, room, inspection))["items"]}
    assert "CRACK_RECURRENCE" in codes and not codes & set(FLOOR_RULE_CODES)


def test_question_keys_of_the_floor_checklists_exist():
    # the keys the API tests above answer exist in version 2 (a renamed question would silently answer nothing)
    for code, keys in (("substrate-screed", {"planned_finish", "wet_zone", "underfloor_heating", "floor_moisture_measured", "floor_flatness_mm",
                                              "floor_level_deviation_mm", "cracks_present", "expansion_joints_missing", "floor_weak_surface",
                                              "substrate_condition", "screed_type", "screed_hollow"}),
                       ("substrate-old-tile", {"tiles_hollow", "tiles_glazed", "tiles_layers"}),
                       ("substrate-wood-boards", {"boards_flex", "wood_decay"})):
        template = next(t for t in build_baseline_templates() if t.code == code and t.version == 2)
        assert keys <= {q.key for s in template.sections for q in s.questions}, code
    assert question_by_key  # imported helper stays in use for the API tests
