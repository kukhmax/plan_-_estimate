"""Stage 16E.1: the contract of an object and the questionnaire "compose the contract" -- the shape of every answer, completeness,
the one draft per object, owner isolation and the migration."""
import importlib.util
import uuid
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from httpx import AsyncClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.domain.contracts.answers import (
    DATE_ORDER,
    NOT_AN_OPTION,
    OUT_OF_RANGE,
    TOO_LONG,
    NOT_AUTHORISED,
    UNKNOWN_PERSON,
    UNKNOWN_QUESTION,
    UNKNOWN_REQUIREMENT,
    WRONG_TYPE,
    BAD_DATE,
    effective_answers,
    merge_answers,
    missing_required,
)
from app.domain.contracts.catalog import load_contract_catalog
from app.domain.exceptions import ContractAnswerInvalidError
from app.models.contract import Contract
from tests.test_clients import OTHER_USER, VALID_USER, auth_header, get_token

BACKEND = Path(__file__).resolve().parents[1]
PROJECT = {"name": "Obiekt", "address": "ul. Długa 1", "city": "Kraków", "postal_code": "30-001"}
CATALOG = load_contract_catalog()
PERSON_A, PERSON_B = str(uuid.uuid4()), str(uuid.uuid4())
PERSON_C = str(uuid.uuid4())  # a person of the object without the authority to accept
PEOPLE = {PERSON_A, PERSON_B, PERSON_C}
AUTHORISED = {PERSON_A, PERSON_B}


def merge(changes, stored=None):
    return merge_answers(stored or {}, changes, person_ids=PEOPLE, authorised_ids=AUTHORISED, catalog=CATALOG)


def refused(changes, stored=None) -> tuple[str, str]:
    with pytest.raises(ContractAnswerInvalidError) as error:
        merge(changes, stored)
    return error.value.key, error.value.reason


# --- the shape of an answer -------------------------------------------------------------------------------------------------


def test_every_kind_of_question_has_a_good_answer_and_it_is_stored_in_one_form():
    merged = merge({
        "contract_place": "  Kraków   ", "contract_date": " 2026-10-12 ", "advance_percent": 30, "payment_mode": "BY_STAGES",
        "payment_due_days": 14, "warranty_months": 24, "downtime_rate_per_day": "150,5", "partial_acceptance": False,
        "who_accepts": [PERSON_B, PERSON_A, PERSON_B], "reinspection_limit": 2,
        "premises_requirement_values": {"lighting_permanent": True, "lighting_level": 300, "humidity_max": 3.456,
                                        "temperature_range": {"min": 5, "max": 25.5}, "windows_glazed": None},
    })
    assert merged["contract_place"] == "Kraków" and merged["contract_date"] == "2026-10-12"
    assert (merged["advance_percent"], merged["payment_mode"], merged["payment_due_days"], merged["warranty_months"]) == (30, "BY_STAGES", 14, 24)
    assert merged["downtime_rate_per_day"] == "150.50" and merged["partial_acceptance"] is False and merged["reinspection_limit"] == 2
    assert merged["who_accepts"] == [PERSON_B, PERSON_A]  # no person twice, the order is kept
    assert merged["premises_requirement_values"] == {
        "lighting_permanent": True, "lighting_level": 300, "humidity_max": 3.46, "temperature_range": {"min": 5, "max": 25.5}}


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"nonsense": 1}, ("nonsense", UNKNOWN_QUESTION)),
        ({"contract_place": 5}, ("contract_place", WRONG_TYPE)),
        ({"contract_place": "x" * 501}, ("contract_place", TOO_LONG)),
        ({"contract_date": "12.10.2026"}, ("contract_date", BAD_DATE)),
        ({"contract_date": "2026-02-30"}, ("contract_date", BAD_DATE)),
        ({"contract_date": 20261012}, ("contract_date", WRONG_TYPE)),
        ({"advance_percent": 101}, ("advance_percent", OUT_OF_RANGE)),
        ({"advance_percent": -1}, ("advance_percent", OUT_OF_RANGE)),
        ({"advance_percent": 10.5}, ("advance_percent", WRONG_TYPE)),
        ({"advance_percent": True}, ("advance_percent", WRONG_TYPE)),
        ({"advance_percent": "30"}, ("advance_percent", WRONG_TYPE)),
        ({"payment_due_days": 366}, ("payment_due_days", OUT_OF_RANGE)),
        ({"warranty_months": 121}, ("warranty_months", OUT_OF_RANGE)),
        ({"payment_mode": "WHENEVER"}, ("payment_mode", NOT_AN_OPTION)),
        ({"payment_mode": 1}, ("payment_mode", WRONG_TYPE)),
        ({"downtime_rate_per_day": "-5"}, ("downtime_rate_per_day", WRONG_TYPE)),
        ({"downtime_rate_per_day": "12,345"}, ("downtime_rate_per_day", WRONG_TYPE)),
        ({"downtime_rate_per_day": True}, ("downtime_rate_per_day", WRONG_TYPE)),
        ({"partial_acceptance": "yes"}, ("partial_acceptance", WRONG_TYPE)),
        ({"partial_acceptance": 1}, ("partial_acceptance", WRONG_TYPE)),
        ({"who_accepts": "not a list"}, ("who_accepts", WRONG_TYPE)),
        ({"who_accepts": ["not-a-uuid"]}, ("who_accepts", WRONG_TYPE)),
        ({"who_accepts": [str(uuid.uuid4())]}, ("who_accepts", UNKNOWN_PERSON)),
        ({"who_accepts": [PERSON_A, PERSON_C]}, ("who_accepts", NOT_AUTHORISED)),
        ({"premises_requirement_values": [1]}, ("premises_requirement_values", WRONG_TYPE)),
        ({"premises_requirement_values": {"warp_drive": 1}}, ("premises_requirement_values", UNKNOWN_REQUIREMENT)),
        ({"premises_requirement_values": {"lighting_permanent": 1}}, ("premises_requirement_values", WRONG_TYPE)),
        ({"premises_requirement_values": {"lighting_level": True}}, ("premises_requirement_values", WRONG_TYPE)),
        ({"premises_requirement_values": {"lighting_level": -1}}, ("premises_requirement_values", OUT_OF_RANGE)),
        ({"premises_requirement_values": {"temperature_range": 20}}, ("premises_requirement_values", WRONG_TYPE)),
        ({"premises_requirement_values": {"temperature_range": {"min": 25, "max": 5}}}, ("premises_requirement_values", OUT_OF_RANGE)),
        ({"premises_requirement_values": {"temperature_range": {"min": 5}}}, ("premises_requirement_values", WRONG_TYPE)),
    ],
)
def test_a_wrong_answer_is_refused_naming_the_question_and_the_reason(changes, expected):
    assert refused(changes) == expected


def test_nothing_is_applied_when_one_change_of_several_is_refused():
    with pytest.raises(ContractAnswerInvalidError):
        merge({"contract_place": "Kraków", "advance_percent": 500})
    stored = {"contract_place": "Łódź"}
    with pytest.raises(ContractAnswerInvalidError):
        merge({"contract_place": "Kraków", "advance_percent": 500}, stored)
    assert stored == {"contract_place": "Łódź"}


def test_null_blank_text_and_an_empty_list_clear_an_answer():
    stored = {"contract_place": "Kraków", "advance_percent": 30, "who_accepts": [PERSON_A], "premises_requirement_values": {"lighting_permanent": True}}
    cleared = merge({"contract_place": None, "advance_percent": None, "who_accepts": [], "premises_requirement_values": {"lighting_permanent": None}}, stored)
    assert cleared == {}
    assert merge({"contract_place": "   "}, {"contract_place": "x"}) == {}


def test_the_end_may_not_be_before_the_start_even_when_only_one_date_is_sent():
    assert refused({"work_start_date": "2026-10-20", "work_end_date": "2026-10-10"}) == ("work_end_date", DATE_ORDER)
    stored = {"work_start_date": "2026-10-20"}
    assert refused({"work_end_date": "2026-10-10"}, stored) == ("work_end_date", DATE_ORDER)
    assert merge({"work_end_date": "2026-10-20"}, stored)["work_end_date"] == "2026-10-20"


# --- completeness and defaults ----------------------------------------------------------------------------------------------


def test_the_only_defaults_are_the_two_the_owner_accepted():
    assert effective_answers({}, CATALOG) == {"customer_appearance_days": 3, "partial_acceptance": True}
    assert effective_answers({"customer_appearance_days": 5, "contract_place": "Kraków"}, CATALOG)["customer_appearance_days"] == 5


def test_the_required_questions_are_reported_in_the_questionnaires_order_and_a_default_is_an_answer():
    required = [q.key for q in CATALOG.questionnaire.items if q.requirement == "REQUIRED"]
    assert required == ["who_accepts", "contract_date", "contract_place", "partial_acceptance"]
    assert missing_required({}, CATALOG) == ["who_accepts", "contract_date", "contract_place"]  # partial_acceptance has its default
    done = {"who_accepts": [PERSON_A], "contract_date": "2026-10-12", "contract_place": "Kraków"}
    assert missing_required(done, CATALOG) == []
    assert missing_required({**done, "who_accepts": []}, CATALOG) == ["who_accepts"]


# --- migration ------------------------------------------------------------------------------------------------------------------


def load_migration():
    spec = importlib.util.spec_from_file_location("m0044", BACKEND / "alembic" / "versions" / "0044_contracts.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_migration(engine, direction: str):
    module = load_migration()
    with engine.begin() as conn:
        module.op = Operations(MigrationContext.configure(conn))
        getattr(module, direction)()


def old_engine():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.execute(text("CREATE TABLE users (id CHAR(32) PRIMARY KEY)"))
        conn.execute(text("CREATE TABLE projects (id CHAR(32) PRIMARY KEY)"))
        conn.execute(text("INSERT INTO users (id) VALUES ('u1')"))
        conn.execute(text("INSERT INTO projects (id) VALUES ('p1'), ('p2')"))
    return engine


def test_revision_chain():
    module = load_migration()
    assert module.revision == "0044_contracts" and module.down_revision == "0043_issued_docs_plan"


def test_upgrade_matches_the_model_and_downgrade_drops_only_the_table():
    engine = old_engine()
    before = set(inspect(engine).get_table_names())
    run_migration(engine, "upgrade")
    insp = inspect(engine)
    assert set(insp.get_table_names()) == before | {"contracts"}
    columns = {c["name"]: c for c in insp.get_columns("contracts")}
    assert set(columns) == {c.name for c in Contract.__table__.columns}
    assert all(not c["nullable"] for c in columns.values())
    assert {fk["referred_table"] for fk in insp.get_foreign_keys("contracts")} == {"users", "projects"}
    assert {c["name"] for c in insp.get_check_constraints("contracts")} == {"ck_contracts_status", "ck_contracts_version_positive"}
    assert {i["name"] for i in insp.get_indexes("contracts")} == {"uq_contracts_one_draft", "ix_contracts_project"}
    run_migration(engine, "downgrade")
    assert set(inspect(engine).get_table_names()) == before


def test_the_database_itself_allows_one_draft_per_object_a_version_once_and_only_known_states():
    engine = old_engine()
    run_migration(engine, "upgrade")
    sql = ("INSERT INTO contracts (id, owner_id, project_id, version, status, answers, questionnaire_version, created_at, updated_at) "
           "VALUES (:id, 'u1', :project, :version, :status, '{}', 1, '2026-10-09', '2026-10-09')")
    good = {"id": "a", "project": "p1", "version": 1, "status": "DRAFT"}
    with engine.begin() as conn:
        conn.execute(text(sql), good)
        conn.execute(text(sql), {**good, "id": "b", "version": 2, "status": "ISSUED"})
        conn.execute(text(sql), {**good, "id": "c", "version": 3, "status": "ISSUED"})  # many issued ones are fine
        conn.execute(text(sql), {**good, "id": "d", "project": "p2"})  # another object has its own draft
    for bad in ({"id": "e", "version": 4}, {"id": "f", "version": 1, "status": "ARCHIVED"}, {"id": "g", "version": 5, "status": "LOST"},
                {"id": "h", "version": 0, "status": "ARCHIVED"}):
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(text(sql), {**good, **bad})
    with engine.begin() as conn:  # an abandoned draft makes room for the next one
        conn.execute(text("UPDATE contracts SET status = 'ARCHIVED' WHERE id = 'a'"))
        conn.execute(text(sql), {**good, "id": "i", "version": 6})


def test_a_project_takes_its_contracts_with_it():
    engine = old_engine()
    run_migration(engine, "upgrade")
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO contracts (id, owner_id, project_id, version, status, answers, questionnaire_version, created_at, updated_at) "
                          "VALUES ('a', 'u1', 'p1', 1, 'DRAFT', '{}', 1, '2026-10-09', '2026-10-09')"))
        conn.execute(text("DELETE FROM projects WHERE id = 'p1'"))
        assert conn.execute(text("SELECT count(*) FROM contracts")).scalar_one() == 0


# --- API ------------------------------------------------------------------------------------------------------------------------


async def project_of(client: AsyncClient, headers: dict) -> str:
    created = await client.post("/api/projects", json=PROJECT, headers=headers)
    assert created.status_code == 201, created.text
    return created.json()["id"]


async def person_of(client: AsyncClient, headers: dict, project: str, name="Anna Nowak", authorised=True) -> str:
    created = await client.post(
        f"/api/projects/{project}/representatives", json={"side": "CUSTOMER", "name": name, "may_accept_and_sign": authorised}, headers=headers)
    assert created.status_code == 201, created.text
    return created.json()["id"]


def url(project_id: str, tail: str = "") -> str:
    return f"/api/projects/{project_id}/contracts{tail}"


async def test_opening_the_draft_creates_it_once_and_returns_the_same_one_again(async_client: AsyncClient):
    headers = auth_header(await get_token(async_client, VALID_USER))
    project = await project_of(async_client, headers)
    first = await async_client.post(url(project), headers=headers)
    assert first.status_code == 201, first.text
    body = first.json()
    assert (body["version"], body["status"], body["answers"], body["questionnaire_version"]) == (1, "DRAFT", {}, CATALOG.questionnaire.version)
    assert body["effective_answers"] == {"customer_appearance_days": 3, "partial_acceptance": True}
    assert body["missing_required"] == ["who_accepts", "contract_date", "contract_place"]
    again = await async_client.post(url(project), headers=headers)
    assert again.status_code == 200 and again.json()["id"] == body["id"]
    assert (await async_client.get(url(project), headers=headers)).json()["total"] == 1


async def test_answers_are_saved_partially_and_completeness_follows(async_client: AsyncClient):
    headers = auth_header(await get_token(async_client, VALID_USER))
    project = await project_of(async_client, headers)
    person = await person_of(async_client, headers, project)
    contract = (await async_client.post(url(project), headers=headers)).json()["id"]
    target = url(project, f"/{contract}/answers")
    saved = await async_client.patch(target, json={"answers": {"contract_place": " Kraków ", "who_accepts": [person]}}, headers=headers)
    assert saved.status_code == 200, saved.text
    assert saved.json()["answers"] == {"contract_place": "Kraków", "who_accepts": [person]}
    assert saved.json()["missing_required"] == ["contract_date"]
    done = (await async_client.patch(target, json={"answers": {"contract_date": "2026-10-12", "downtime_rate_per_day": "150"}}, headers=headers)).json()
    assert done["missing_required"] == [] and done["answers"]["contract_place"] == "Kraków" and done["answers"]["downtime_rate_per_day"] == "150.00"
    cleared = (await async_client.patch(target, json={"answers": {"contract_place": None, "partial_acceptance": False}}, headers=headers)).json()
    assert "contract_place" not in cleared["answers"] and cleared["missing_required"] == ["contract_place"]
    assert cleared["effective_answers"]["partial_acceptance"] is False
    assert (await async_client.get(url(project, f"/{contract}"), headers=headers)).json()["answers"] == cleared["answers"]


async def test_a_wrong_answer_is_a_422_with_the_question_and_the_reason_and_changes_nothing(async_client: AsyncClient):
    headers = auth_header(await get_token(async_client, VALID_USER))
    project = await project_of(async_client, headers)
    contract = (await async_client.post(url(project), headers=headers)).json()["id"]
    target = url(project, f"/{contract}/answers")
    bad = await async_client.patch(target, json={"answers": {"contract_place": "Kraków", "advance_percent": 500}}, headers=headers)
    assert bad.status_code == 422
    assert bad.json()["detail"] == {"code": "CONTRACT_ANSWER_INVALID", "message": bad.json()["detail"]["message"],
                                    "details": {"key": "advance_percent", "reason": "OUT_OF_RANGE"}}
    assert (await async_client.get(url(project, f"/{contract}"), headers=headers)).json()["answers"] == {}
    for body in ({}, {"answers": {}}, {"answers": {"x": 1}, "extra": 1}, {"answers": [1]}):
        assert (await async_client.patch(target, json=body, headers=headers)).status_code == 422


async def test_only_authorised_people_of_this_object_who_are_not_archived_can_be_named(async_client: AsyncClient):
    headers = auth_header(await get_token(async_client, VALID_USER))
    project = await project_of(async_client, headers)
    other = await project_of(async_client, headers)
    foreign = await person_of(async_client, headers, other)
    own = await person_of(async_client, headers, project)
    contract = (await async_client.post(url(project), headers=headers)).json()["id"]
    target = url(project, f"/{contract}/answers")
    refused_ = await async_client.patch(target, json={"answers": {"who_accepts": [foreign]}}, headers=headers)
    assert refused_.status_code == 422 and refused_.json()["detail"]["details"]["reason"] == "UNKNOWN_PERSON"
    plain = await person_of(async_client, headers, project, name="Bez uprawnień", authorised=False)
    no_authority = await async_client.patch(target, json={"answers": {"who_accepts": [own, plain]}}, headers=headers)
    assert no_authority.status_code == 422 and no_authority.json()["detail"]["details"]["reason"] == "NOT_AUTHORISED"
    assert (await async_client.patch(target, json={"answers": {"who_accepts": [own]}}, headers=headers)).status_code == 200
    await async_client.post(f"/api/projects/{project}/representatives/{own}/archive", headers=headers)
    assert (await async_client.patch(target, json={"answers": {"who_accepts": [own]}}, headers=headers)).status_code == 422


async def test_an_abandoned_draft_is_closed_and_the_next_draft_is_a_new_version(async_client: AsyncClient):
    headers = auth_header(await get_token(async_client, VALID_USER))
    project = await project_of(async_client, headers)
    first = (await async_client.post(url(project), headers=headers)).json()["id"]
    closed = await async_client.post(url(project, f"/{first}/archive"), headers=headers)
    assert closed.status_code == 200 and closed.json()["status"] == "ARCHIVED"
    locked = await async_client.patch(url(project, f"/{first}/answers"), json={"answers": {"contract_place": "x"}}, headers=headers)
    assert locked.status_code == 409 and locked.json()["detail"]["code"] == "CONTRACT_NOT_EDITABLE"
    assert (await async_client.post(url(project, f"/{first}/archive"), headers=headers)).status_code == 409
    second = await async_client.post(url(project), headers=headers)
    assert second.status_code == 201 and second.json()["version"] == 2 and second.json()["id"] != first
    listed = (await async_client.get(url(project), headers=headers)).json()
    assert [(c["version"], c["status"]) for c in listed["items"]] == [(2, "DRAFT"), (1, "ARCHIVED")]


async def test_another_owner_sees_nothing_and_changes_nothing(async_client: AsyncClient):
    owner = auth_header(await get_token(async_client, VALID_USER))
    other = auth_header(await get_token(async_client, OTHER_USER))
    project = await project_of(async_client, owner)
    contract = (await async_client.post(url(project), headers=owner)).json()["id"]
    for call in (
        async_client.get(url(project), headers=other),
        async_client.post(url(project), headers=other),
        async_client.get(url(project, f"/{contract}"), headers=other),
        async_client.patch(url(project, f"/{contract}/answers"), json={"answers": {"contract_place": "X"}}, headers=other),
        async_client.post(url(project, f"/{contract}/archive"), headers=other),
    ):
        assert (await call).status_code == 404
    assert (await async_client.get(url(project, f"/{contract}"), headers=owner)).json()["answers"] == {}


async def test_a_contract_of_one_object_cannot_be_reached_through_another_object(async_client: AsyncClient):
    headers = auth_header(await get_token(async_client, VALID_USER))
    first = await project_of(async_client, headers)
    second = await project_of(async_client, headers)
    contract = (await async_client.post(url(first), headers=headers)).json()["id"]
    assert (await async_client.get(url(second, f"/{contract}"), headers=headers)).status_code == 404
    assert (await async_client.patch(url(second, f"/{contract}/answers"), json={"answers": {"contract_place": "X"}}, headers=headers)).status_code == 404
    assert (await async_client.get(url(second), headers=headers)).json()["total"] == 0
    assert (await async_client.post(url(str(uuid.uuid4())), headers=headers)).status_code == 404


async def test_every_route_needs_a_token(async_client: AsyncClient):
    pid, cid = uuid.uuid4(), uuid.uuid4()
    for method, path in (("GET", url(str(pid))), ("POST", url(str(pid))), ("GET", url(str(pid), f"/{cid}")),
                         ("PATCH", url(str(pid), f"/{cid}/answers")), ("POST", url(str(pid), f"/{cid}/archive"))):
        assert (await async_client.request(method, path, json={})).status_code == 401, (method, path)


# --- words ----------------------------------------------------------------------------------------------------------------------


def test_every_reason_and_error_code_has_a_sentence_in_polish_and_in_russian():
    """The backend sends stable reasons, never text for the screen: each one must have its sentence in `contract.errors`."""
    import json
    import re

    source = (BACKEND / "app" / "domain" / "contracts" / "answers.py").read_text(encoding="utf-8")
    reasons = set(re.findall(r'^([A-Z_]+) = "\1"', source, flags=re.MULTILINE))
    assert {"WRONG_TYPE", "OUT_OF_RANGE", "NOT_AUTHORISED", "DATE_ORDER", "UNKNOWN_PERSON"} <= reasons and len(reasons) == 10
    for language in ("pl", "ru"):
        sentences = json.loads((BACKEND.parent / "frontend" / "src" / "locales" / f"{language}.json").read_text(encoding="utf-8"))["contract"]["errors"]
        assert reasons - set(sentences) == set(), f"{language}: reasons without a sentence"
        assert {"UNKNOWN", "NOT_EDITABLE"} <= set(sentences)
