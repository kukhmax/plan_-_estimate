"""UX walk B4 (owner 2026-10-29): the floor substrates SCREED, OLD_TILE and WOOD_BOARDS -- no quality scale, a checklist of their own,
the findings the existing risk rules already understand, and the migration of the enum."""
import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, text

from app.domain.data.checklist_templates import build_baseline_templates
from app.domain.exceptions import QualityScaleMismatchError
from app.domain.rules.inspection_rules import assert_quality_scale_valid
from app.models.checklist import QualityLevel, Substrate
from tests.test_canonical_planes import auth_header, canonical_planes, create_project, create_room, get_token, VALID_USER
from tests.test_communications import _complete, _evaluate_risks, _put_answers, _scaffold_inspection
from tests.test_stage16e2_contract import load_migration, run

FLOOR = (Substrate.SCREED, Substrate.OLD_TILE, Substrate.WOOD_BOARDS)


# --- the rule: no scale ------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("substrate", FLOOR)
def test_a_floor_substrate_takes_no_quality_target(substrate):
    assert_quality_scale_valid(substrate, None)
    for level in QualityLevel:
        with pytest.raises(QualityScaleMismatchError):
            assert_quality_scale_valid(substrate, level)


def test_the_walls_substrates_keep_their_scales():
    assert_quality_scale_valid(Substrate.CONCRETE, QualityLevel.S3)
    assert_quality_scale_valid(Substrate.GYPSUM_BOARD, QualityLevel.Q2)
    assert_quality_scale_valid(Substrate.OTHER, QualityLevel.Q1)
    with pytest.raises(QualityScaleMismatchError):
        assert_quality_scale_valid(Substrate.CONCRETE, QualityLevel.Q1)


# --- the checklists -----------------------------------------------------------------------------------------------------------------


def test_each_floor_substrate_has_a_checklist_with_the_common_floor_checks_and_its_own():
    templates = {t.substrate: t for t in build_baseline_templates()}
    common = {"floor_moisture_measured", "floor_moisture_high", "cracks_present", "expansion_joints_missing", "floor_flatness_mm",
              "floor_level_deviation_mm", "substrate_condition", "notes"}
    own = {Substrate.SCREED: {"screed_type", "underfloor_heating", "screed_hollow", "screed_weak_surface"},
           Substrate.OLD_TILE: {"tiles_hollow", "tiles_glazed", "tiles_layers"},
           Substrate.WOOD_BOARDS: {"boards_flex", "wood_decay", "boards_coating"}}
    for substrate in FLOOR:
        keys = [q.key for s in templates[substrate].sections for q in s.questions]
        assert len(keys) == len(set(keys))  # a key twice in one checklist would clash
        assert common | own[substrate] == set(keys)
        findings = [q.finding_key for s in templates[substrate].sections for q in s.questions if q.finding_key]
        assert len(findings) == len(set(findings))  # one finding per fact: the inspection materializes a finding once per key


def test_the_floor_findings_reuse_the_keys_the_risk_engine_knows():
    from app.domain.data.risk_rules import build_baseline_risk_rules

    known = {c.finding_key for r in build_baseline_risk_rules() for c in r.conditions if c.finding_key}
    used = {q.finding_key for t in build_baseline_templates() if t.substrate in FLOOR for s in t.sections for q in s.questions if q.finding_key}
    assert {"CRACK", "HIGH_MOISTURE", "UNEVENNESS", "DELAMINATION", "WEAK_ADHESION"} <= known & used
    assert used - known == {"EXPANSION_JOINT_MISSING", "FLOOR_LEVEL_DEVIATION", "BOARDS_FLEX", "WOOD_DECAY"}  # facts only: no risk rule yet


# --- through the API ----------------------------------------------------------------------------------------------------------------


async def test_the_catalogue_serves_the_floor_checklists(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    for substrate in FLOOR:
        listed = await async_client.get(f"/api/checklist-templates?substrate={substrate.value}", headers=auth_header(token))
        assert listed.status_code == 200 and listed.json()["total"] == 1, listed.text
        template = (await async_client.get(f"/api/checklist-templates/{listed.json()['items'][0]['id']}", headers=auth_header(token))).json()
        assert template["substrate"] == substrate.value
        assert [s["key"] for s in template["sections"]][0] == "floor_conditions"


async def test_a_screed_inspection_records_the_floor_facts_and_the_known_risk_fires(async_client: AsyncClient):
    token, project, room, inspection, template = await _scaffold_inspection(async_client, substrate="SCREED", plane="FLOOR")
    assert inspection["substrate"] == "SCREED" and inspection["quality_target"] is None
    await _put_answers(async_client, token, project, room, inspection, template, {
        "floor_moisture_measured": {"value_number": "3.2"},
        "floor_moisture_high": {"value_bool": True},
        "expansion_joints_missing": {"value_bool": True},
        "floor_level_deviation_mm": {"value_number": "8"},
        "floor_flatness_mm": {"value_number": "4"},
        "screed_hollow": {"value_bool": True},
    })
    done = await _complete(async_client, token, project, room, inspection)
    assert done.status_code == 200, done.text
    findings = (await async_client.get(
        f"/api/projects/{project['id']}/rooms/{room['id']}/inspections/{inspection['id']}/findings", headers=auth_header(token))).json()
    keys = {f["finding_key"] for f in findings["items"]}
    assert keys == {"HIGH_MOISTURE", "EXPANSION_JOINT_MISSING", "FLOOR_LEVEL_DEVIATION", "UNEVENNESS", "DELAMINATION"}
    risks = await _evaluate_risks(async_client, token, project, room, inspection)
    assert {r["rule_code"] for r in risks["items"]} >= {"MOISTURE_BLOCK_FINISHING", "UNEVENNESS_PREP_INCREASED", "DELAMINATION_REPAIR"}


async def test_an_inspection_with_a_quality_target_on_a_floor_substrate_is_refused(async_client: AsyncClient):
    token, project, room, _, template = await _scaffold_inspection(async_client, substrate="WOOD_BOARDS", plane="FLOOR")
    refused = await async_client.post(
        f"/api/projects/{project['id']}/rooms/{room['id']}/inspections",
        json={"template_id": template["id"], "substrate": "WOOD_BOARDS", "plane": "FLOOR", "quality_target": "S2"}, headers=auth_header(token))
    assert refused.status_code == 422, refused.text


async def test_the_work_plan_of_a_floor_takes_a_floor_substrate_and_no_quality(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    floor = (await canonical_planes(async_client, token, project["id"], room["id"]))["FLOOR"]
    url = f"/api/projects/{project['id']}/rooms/{room['id']}/surfaces/{floor['id']}/work-plan"
    bad = await async_client.put(url, json={"substrate": "OLD_TILE", "quality_target": "S2", "price_item_ids": []}, headers=auth_header(token))
    assert bad.status_code == 422 and "no quality scale" in str(bad.json()["detail"]), bad.text
    good = await async_client.put(url, json={"substrate": "OLD_TILE", "quality_target": None, "price_item_ids": []}, headers=auth_header(token))
    assert good.status_code == 200, good.text
    assert (good.json()["substrate"], good.json()["quality_target"]) == ("OLD_TILE", None)
    assert (await async_client.get(url, headers=auth_header(token))).json()["substrate"] == "OLD_TILE"


# --- the migration ------------------------------------------------------------------------------------------------------------------


def test_revision_chain():
    module = load_migration("0089_floor_substrates")
    assert module.down_revision == "0088_owner_contract_terms" and len(module.revision) <= 32
    assert set(module.NEW_SUBSTRATES) == {s.value for s in FLOOR}


def _engine():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        for table in ("inspections", "room_work_plans", "surface_work_plans"):
            conn.execute(text(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, substrate VARCHAR(32), template_id INTEGER)"))
        conn.execute(text("CREATE TABLE checklist_templates (id INTEGER PRIMARY KEY, substrate VARCHAR(32))"))
        conn.execute(text("CREATE TABLE checklist_sections (id INTEGER PRIMARY KEY, template_id INTEGER)"))
        conn.execute(text("CREATE TABLE checklist_questions (id INTEGER PRIMARY KEY, template_id INTEGER)"))
        conn.execute(text("CREATE TABLE checklist_options (id INTEGER PRIMARY KEY, question_id INTEGER)"))
        conn.execute(text("INSERT INTO checklist_templates VALUES (1, 'CONCRETE'), (2, 'SCREED')"))
        conn.execute(text("INSERT INTO checklist_sections VALUES (1, 1), (2, 2)"))
        conn.execute(text("INSERT INTO checklist_questions VALUES (1, 1), (2, 2)"))
        conn.execute(text("INSERT INTO checklist_options VALUES (1, 1), (2, 2)"))
    return engine


def test_the_downgrade_removes_the_bootstrapped_floor_checklists_and_nothing_else():
    engine = _engine()
    run(engine, "0089_floor_substrates", "downgrade")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT id FROM checklist_templates")).scalars().all() == [1]
        assert conn.execute(text("SELECT count(*) FROM checklist_sections")).scalar_one() == 1
        assert conn.execute(text("SELECT count(*) FROM checklist_questions")).scalar_one() == 1
        assert conn.execute(text("SELECT count(*) FROM checklist_options")).scalar_one() == 1


@pytest.mark.parametrize("table", ["inspections", "room_work_plans", "surface_work_plans"])
def test_the_downgrade_refuses_while_the_owner_has_a_floor_row(table):
    engine = _engine()
    with engine.begin() as conn:
        conn.execute(text(f"INSERT INTO {table} (id, substrate) VALUES (1, 'WOOD_BOARDS')"))
    with pytest.raises(RuntimeError, match="never dropped silently"):
        run(engine, "0089_floor_substrates", "downgrade")
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM checklist_templates")).scalar_one() == 2  # nothing was removed


# --- the words ----------------------------------------------------------------------------------------------------------------------


def test_every_text_of_the_floor_checklists_has_its_words_in_the_four_languages():
    """The backend sends keys, never words: each key a floor checklist uses must be in the dictionary of every language."""
    import json
    from pathlib import Path

    locales = {code: json.loads((Path(__file__).resolve().parents[2] / "frontend" / "src" / "locales" / f"{code}.json").read_text(encoding="utf-8"))
               for code in ("pl", "ru", "uk", "en")}

    def has(dictionary: dict, dotted: str) -> bool:
        node = dictionary
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return False
            node = node[part]
        return isinstance(node, str) and node.strip() != ""

    keys: set[str] = set()
    for template in build_baseline_templates():
        if template.substrate not in FLOOR:
            continue
        keys.add(template.title_key)
        for section in template.sections:
            keys |= {section.title_key, section.description_key}
            for question in section.questions:
                keys |= {question.text_key, question.hint_key, question.unit_key} - {None}
                keys |= {option.label_key for option in question.options}
    keys.discard(None)
    keys.discard("mm")  # the one unit written as a plain word, as before
    missing = {(code, key) for code, words in locales.items() for key in keys if not has(words, key)}
    assert not missing, sorted(missing)
    for code, words in locales.items():
        for substrate in ("screed", "old_tile", "wood_boards"):
            assert has(words, f"inspections.substrate_{substrate}"), (code, substrate)


def test_every_substrate_has_its_name_in_the_documents():
    """The report and the technological card name the substrate of an inspection: a substrate without a name prints a hole."""
    import json
    from pathlib import Path

    documents = Path(__file__).resolve().parents[1] / "app" / "domain" / "documents"
    template = (documents / "templates" / "photo_report.html.j2").read_text(encoding="utf-8")
    labels = json.loads((documents / "locales" / "pl.json").read_text(encoding="utf-8"))
    for substrate in Substrate:
        assert f"'{substrate.value}': t('photo_report.substrate_name.{substrate.value.lower()}')" in template, substrate
        assert labels[f"photo_report.substrate_name.{substrate.value.lower()}"].strip(), substrate


# --- a floor on a substrate the walls know as well asks the floor questions (owner 2026-10-30) ---------------------------------------


async def test_a_floor_on_concrete_old_paint_or_other_gets_the_floor_checklist_and_the_walls_keep_theirs(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    walls = (await async_client.get("/api/checklist-templates", headers=auth_header(token))).json()
    assert walls["total"] == 9 and not any(i["code"].startswith("floor-") for i in walls["items"])  # the list of the walls is as it was

    floor = (await async_client.get("/api/checklist-templates?for_floor=true", headers=auth_header(token))).json()
    assert floor["total"] == 5
    assert {i["substrate"] for i in floor["items"]} == {"CONCRETE", "OTHER", "SCREED", "OLD_TILE", "WOOD_BOARDS"}  # one per substrate, no old paint on a floor
    for substrate in ("CONCRETE", "OTHER"):
        only = (await async_client.get(f"/api/checklist-templates?for_floor=true&substrate={substrate}", headers=auth_header(token))).json()
        assert only["total"] == 1 and only["items"][0]["code"] == f"floor-{substrate.lower()}"
        template = (await async_client.get(f"/api/checklist-templates/{only['items'][0]['id']}", headers=auth_header(token))).json()
        keys = {q["key"] for s in template["sections"] for q in s["questions"]}
        assert [s["key"] for s in template["sections"]] == ["floor_conditions"]
        assert {"floor_moisture_measured", "expansion_joints_missing", "floor_flatness_mm", "floor_level_deviation_mm"} <= keys
        assert "oil_paint_present" not in keys and "efflorescence" not in keys  # nothing of the wall list

    wall_concrete = (await async_client.get("/api/checklist-templates?substrate=CONCRETE", headers=auth_header(token))).json()
    assert wall_concrete["total"] == 1 and wall_concrete["items"][0]["code"] == "substrate-concrete"


async def test_a_floor_inspection_can_start_from_the_floor_variant_of_concrete(async_client: AsyncClient):
    token = await get_token(async_client, VALID_USER)
    project = await create_project(async_client, token)
    room = await create_room(async_client, token, project["id"])
    template = (await async_client.get("/api/checklist-templates?for_floor=true&substrate=CONCRETE", headers=auth_header(token))).json()["items"][0]
    created = await async_client.post(
        f"/api/projects/{project['id']}/rooms/{room['id']}/inspections",
        json={"template_id": template["id"], "substrate": "CONCRETE", "quality_target": None, "plane": "FLOOR"},
        headers=auth_header(token),
    )
    assert created.status_code == 201, created.text
    assert created.json()["template_id"] == template["id"]
