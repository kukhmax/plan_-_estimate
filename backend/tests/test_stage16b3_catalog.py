"""Stage 16B.3: the catalogues of the contract and the protocols -- starter structure, no numbers, no clauses."""
import json
from pathlib import Path

import pytest
from httpx import AsyncClient
from pydantic import ValidationError

from app.domain.contracts import catalog as cat
from app.domain.contracts.catalog import (
    CATALOG_DIR,
    QUALITY_CLASSES,
    SECTIONS,
    ContractCatalogError,
    DefectClass,
    Question,
    Requirement,
    Tolerance,
    load_contract_catalog,
)
from tests.test_clients import VALID_USER, auth_header, get_token

LOCALES = Path(__file__).resolve().parents[2] / "frontend" / "src" / "locales"
# Words that make a text a clause or a quotation (as in the skeleton guard of 15G); words that are only names of things here
# ("wada", "termin" in a question label) are not in the list.
CLAUSE_WORDS = ("§", "art.", "ust.", "kodeks", "ustaw", "rozporządz", "zgodnie z", "obowiązuj", "odpowiedzialn", "kara", "kary", "gwarancj",
                "rękojm", "pn-", "itb", "din ", "prawo budowlane", "zobowiązuj", "strony ustalaj", "wynagrodzen", "zapłat", "reklamac",
                "rozwiąz", "siła wyższa", "poufn", "rodo")


def raw(name: str) -> dict:
    return json.loads((CATALOG_DIR / name).read_text(encoding="utf-8"))


def locale(lang: str) -> dict:
    return json.loads((LOCALES / f"{lang}.json").read_text(encoding="utf-8"))["contractCatalog"]


# --- the starter content --------------------------------------------------------------------------------------------


def test_every_catalogue_loads_and_has_the_expected_size():
    c = load_contract_catalog()
    assert {n: len(getattr(c, n).items) for n in SECTIONS} == {
        "requirements": 14, "instruments": 8, "evaluation": 8, "defects": 2, "tolerances": 0, "questionnaire": 31}
    assert {n: getattr(c, n).version for n in SECTIONS} == {**{n: 1 for n in SECTIONS}, "questionnaire": 2}  # 16E.3 extended the questionnaire


def test_the_requirements_name_things_and_carry_no_value():
    items = load_contract_catalog().requirements.items
    assert {i.group for i in items} == {"LIGHTING", "GLAZING", "CLIMATE", "UTILITIES", "ACCESS", "CLEANLINESS", "SUBSTRATE"}
    assert {i.key: (i.value_kind, i.unit) for i in items if i.value_kind != "YES_NO"} == {
        "lighting_level": ("NUMBER", "lx"), "temperature_range": ("NUMBER_RANGE", "°C"), "humidity_max": ("NUMBER", "%"),
        "substrate_cure_days": ("NUMBER", "days")}
    for file_item in raw("premises_requirements.json")["items"]:
        assert set(file_item) == {"key", "group", "value_kind", "unit", "label_key", "text_pl"}  # no "value", no threshold


def test_the_visual_classes_cover_s1_to_q4_without_a_millimetre():
    items = load_contract_catalog().evaluation.items
    assert [i.key for i in items] == list(QUALITY_CLASSES)
    by_key = {i.key: i for i in items}
    assert by_key["S4"].requires_agreement and by_key["S4"].lighting == "AGREED_BEFORE_WORK"  # Stage 12: S4 conditions are agreed before the work
    assert by_key["S2"].lighting == "DIFFUSE" and by_key["Q4"].lighting == "RAKING_LIGHT"
    assert [i.key for i in items if i.requires_agreement] == ["S4"]
    for entry in raw("evaluation_conditions.json")["items"]:
        assert not any(unit in json.dumps(entry, ensure_ascii=False) for unit in (" mm", "mm/m", "milimetr"))


def test_the_defect_classes_decide_the_outcome_and_invent_no_criteria():
    by_key = {i.key: i for i in load_contract_catalog().defects.items}
    assert (by_key["REMOVABLE"].outcome, by_key["SIGNIFICANT"].outcome) == ("ACCEPTED_WITH_REMARKS", "NOT_ACCEPTED")
    assert all(i.criteria_pl is None for i in by_key.values())  # the criteria are the owner's and the lawyer's to approve


def test_the_tolerance_file_is_empty_until_the_owner_approves_values_with_a_source():
    assert raw("tolerances.json") == {"version": 1, "items": []}


def test_the_questionnaire_has_the_questions_the_owner_asked_for():
    questions = {q.key: q for q in load_contract_catalog().questionnaire.items}
    assert {"who_accepts", "downtime_rate_per_day", "customer_appearance_days", "partial_acceptance", "reinspection_limit",
            "premises_requirement_values", "advance_percent", "warranty_months", "penalty_mode", "client_status", "conclusion_mode", "vat_rate_percent",
            "paid_orders_persons", "downtime_days_limit"} <= set(questions)
    assert questions["who_accepts"].kind == "PERSON_LIST" and questions["who_accepts"].requirement == "REQUIRED"
    assert questions["downtime_rate_per_day"].requirement == "OPEN" and questions["downtime_rate_per_day"].default is None  # open: "......"
    assert (questions["customer_appearance_days"].default, questions["partial_acceptance"].default) == (3, True)
    assert questions["payment_mode"].options == ["BY_STAGES", "ON_ACCEPTANCE"]
    # the only defaults are the owner's accepted recommendations; nothing else is pre-filled
    assert {k for k, q in questions.items() if q.default is not None} == {"customer_appearance_days", "partial_acceptance"}


# --- the guards ----------------------------------------------------------------------------------------------------------


def test_the_document_wording_is_never_a_clause():
    texts = []
    c = load_contract_catalog()
    for name in ("requirements", "instruments", "evaluation", "defects"):
        texts += [(f"{name}.{i.key}", i.text_pl) for i in getattr(c, name).items]
    for key, text in texts:
        lowered = text.lower()
        assert not [w for w in CLAUSE_WORDS if w in lowered], f"{key}: {text!r}"
    assert [w for w in CLAUSE_WORDS if w in "Wykonawca ponosi odpowiedzialność za wady".lower()]  # the guard would catch a clause


def test_a_catalogue_that_slips_in_a_value_or_a_clause_is_refused():
    with pytest.raises(ValidationError):
        Requirement(key="humidity_max", group="CLIMATE", value_kind="NUMBER", unit="%", label_key="x", text_pl="Wilgotność", value=65)  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        Requirement(key="windows_glazed", group="GLAZING", value_kind="YES_NO", unit="%", label_key="x", text_pl="Okna")
    with pytest.raises(ValidationError):
        Requirement(key="humidity_max", group="CLIMATE", value_kind="NUMBER", unit=None, label_key="x", text_pl="Wilgotność")


def test_a_tolerance_needs_its_source_a_positive_limit_and_known_classes():
    good = {"key": "wall_flatness", "parameter": "FLATNESS", "instrument_keys": ["straightedge_2m"], "limit_value": "2", "unit": "mm",
            "norm_ref": "Warunki techniczne — pozycja do uzupełnienia", "applies_to": ["S2", "S3"], "label_key": "contractCatalog.tolerances.wall_flatness",
            "text_pl": "Równość ściany"}
    assert Tolerance(**good).limit_value == 2
    for bad in ({"norm_ref": ""}, {"limit_value": "0"}, {"applies_to": ["S9"]}, {"applies_to": []}, {"instrument_keys": []}, {"unit": "cm"}):
        with pytest.raises(ValidationError):
            Tolerance(**{**good, **bad})


def test_a_question_default_must_fit_its_kind_and_a_choice_needs_options():
    base = {"key": "q", "group": "ACCEPTANCE", "requirement": "OPEN", "unit": None, "label_key": "contractCatalog.questions.q", "hint_key": None}
    assert Question(**base, kind="DAYS", default=3, options=None).default == 3
    assert Question(**base, kind="YES_NO", default=True, options=None).default is True
    for kind, default, options in (("TEXT", 3, None), ("YES_NO", 1, None), ("DAYS", True, None), ("CHOICE", None, None), ("DAYS", None, ["A"])):
        with pytest.raises(ValidationError):
            Question(**base, kind=kind, default=default, options=options)
    assert DefectClass(key="REMOVABLE", outcome="ACCEPTED_WITH_REMARKS", label_key="x", text_pl="Wada", criteria_pl=None)


def test_the_loader_refuses_a_wrong_file(tmp_path, monkeypatch):
    for name in (v[0] for v in SECTIONS.values()):
        (tmp_path / name).write_text((CATALOG_DIR / name).read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setattr(cat, "CATALOG_DIR", tmp_path)
    load_contract_catalog.cache_clear()
    try:
        assert load_contract_catalog()  # a copy of the real files loads
        data = raw("evaluation_conditions.json")
        data["items"].pop()  # Q4 missing
        (tmp_path / "evaluation_conditions.json").write_text(json.dumps(data), encoding="utf-8")
        load_contract_catalog.cache_clear()
        with pytest.raises(ContractCatalogError, match="cover exactly"):
            load_contract_catalog()
        data = raw("premises_requirements.json")
        data["items"].append(dict(data["items"][0]))  # a duplicate key
        (tmp_path / "evaluation_conditions.json").write_text((CATALOG_DIR / "evaluation_conditions.json").read_text(encoding="utf-8"), encoding="utf-8")
        (tmp_path / "premises_requirements.json").write_text(json.dumps(data), encoding="utf-8")
        load_contract_catalog.cache_clear()
        with pytest.raises(ContractCatalogError, match="duplicate"):
            load_contract_catalog()
        data = raw("premises_requirements.json")
        data["items"][0]["label_key"] = "somewhere.else"
        (tmp_path / "premises_requirements.json").write_text(json.dumps(data), encoding="utf-8")
        load_contract_catalog.cache_clear()
        with pytest.raises(ContractCatalogError, match="label_key"):
            load_contract_catalog()
        (tmp_path / "premises_requirements.json").write_text("{not json", encoding="utf-8")
        load_contract_catalog.cache_clear()
        with pytest.raises(ContractCatalogError):
            load_contract_catalog()
    finally:
        load_contract_catalog.cache_clear()


# --- the interface texts (PL / RU) are pinned to the catalogues --------------------------------------------------------


def lookup(tree: dict, dotted: str):
    node = {"contractCatalog": tree}
    for part in dotted.split("."):
        node = node[part]
    return node


@pytest.mark.parametrize("lang", ["pl", "ru"])
def test_every_label_and_hint_has_an_interface_text_in_both_languages(lang):
    tree = locale(lang)
    c = load_contract_catalog()
    for name in SECTIONS:
        for item in getattr(c, name).items:
            assert lookup(tree, item.label_key).strip(), item.label_key
            hint = getattr(item, "hint_key", None)
            if hint:
                assert lookup(tree, hint).strip(), hint
    for item in c.requirements.items:
        assert tree["groups"]["premises"][item.group].strip()
    for item in c.instruments.items:
        for measure in item.measures:
            assert tree["measures"][measure].strip()
    for item in c.evaluation.items:
        assert tree["lighting"][item.lighting].strip()
    for item in c.defects.items:
        assert tree["outcomes"][item.outcome].strip()
    for item in c.questionnaire.items:
        assert tree["groups"]["questions"][item.group].strip()
        for option in item.options or []:
            assert tree["choices"][option].strip()
        if item.unit:
            assert tree["units"][item.unit].strip()
    for item in c.requirements.items:
        if item.unit:
            assert tree["units"][item.unit].strip()


@pytest.mark.parametrize("lang", ["pl", "ru"])
def test_there_is_no_interface_text_without_a_catalogue_entry(lang):
    tree = locale(lang)
    c = load_contract_catalog()
    assert set(tree["requirements"]) == {i.key for i in c.requirements.items}
    assert set(tree["instruments"]) == {i.key for i in c.instruments.items}
    assert set(tree["evaluation"]) == {i.key for i in c.evaluation.items}
    assert set(tree["defects"]) == {i.key for i in c.defects.items}
    assert set(tree["questions"]) == {i.key for i in c.questionnaire.items}
    assert set(tree["hints"]) == {i.key for i in c.questionnaire.items if i.hint_key}


# --- API ---------------------------------------------------------------------------------------------------------------------


async def test_the_catalogue_is_served_to_a_signed_in_owner_only(async_client: AsyncClient):
    assert (await async_client.get("/api/contract-catalog")).status_code in (401, 403)
    headers = auth_header(await get_token(async_client, VALID_USER))
    resp = await async_client.get("/api/contract-catalog", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert set(body) == set(SECTIONS)
    assert [i["key"] for i in body["evaluation"]["items"]] == list(QUALITY_CLASSES)
    assert body["tolerances"]["items"] == [] and len(body["questionnaire"]["items"]) == 31
    assert body["questionnaire"]["items"][0]["key"] == "client_status"
