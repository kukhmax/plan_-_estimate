"""UX walk B2: the empty answers of a contract draft are filled from the facts of the object and the owner's latest contract of
another object -- never an invented number, never over an answer the owner gave."""
import uuid
from datetime import UTC, date, datetime

from httpx import AsyncClient

from app.domain.contracts.prefill import STANDARD_TERM_KEYS, PrefillFacts, prefill_changes
from app.domain.documents.formatting import local_datetime
from tests.test_clients import OTHER_USER, auth_header, get_token
from tests.test_v2_6_vat import _price, _profile, _quick, _signed_in, web  # noqa: F401  (the fixture is used by name)

TODAY = date(2026, 10, 29)
PERSON = str(uuid.uuid4())


def facts(**over) -> PrefillFacts:
    values = {"today": TODAY, "place": "Kraków", "vat_rate_percent": 8, "private_client": True, "customer_ids": (PERSON,)}
    values.update(over)
    return PrefillFacts(**values)


# --- the rule -------------------------------------------------------------------------------------------------------------------


def test_the_facts_of_the_object_fill_only_the_empty_answers():
    assert prefill_changes({}, facts(), {}) == {
        "contract_date": "2026-10-29", "contract_place": "Kraków", "vat_rate_percent": 8, "client_status": "CONSUMER", "who_accepts": [PERSON]}
    stored = {"contract_place": "Wieliczka", "who_accepts": [], "vat_rate_percent": 23}
    changes = prefill_changes(stored, facts(), {})
    assert "contract_place" not in changes and "vat_rate_percent" not in changes  # the owner's answers stay
    assert changes["who_accepts"] == [PERSON]  # an empty list is no answer


def test_an_unknown_fact_fills_nothing():
    changes = prefill_changes({}, facts(place=None, vat_rate_percent=None, private_client=False, customer_ids=()), {})
    assert changes == {"contract_date": "2026-10-29"}


def test_the_owner_terms_come_over_and_nothing_else_of_the_other_contract():
    other = {"warranty_months": 24, "advance_percent": 30, "conclusion_mode": "OFF_PREMISES", "contract_place": "Łódź",
             "contract_date": "2025-01-01", "client_status": "ENTREPRENEUR", "who_accepts": [str(uuid.uuid4())], "work_end_date": "2025-02-01"}
    changes = prefill_changes({"advance_percent": 50}, facts(), other)
    assert changes["warranty_months"] == 24 and changes["conclusion_mode"] == "OFF_PREMISES"
    assert "advance_percent" not in changes  # answered here
    assert (changes["contract_place"], changes["contract_date"], changes["client_status"], changes["who_accepts"]) == ("Kraków", "2026-10-29", "CONSUMER", [PERSON])
    assert "work_end_date" not in changes  # a date of one object is not a term
    assert set(STANDARD_TERM_KEYS).isdisjoint({"contract_date", "contract_place", "vat_rate_percent", "client_status", "who_accepts",
                                                "paid_orders_persons", "work_start_date", "work_end_date"})


# --- the API --------------------------------------------------------------------------------------------------------------------


def url(project_id: str, tail: str = "") -> str:
    return f"/api/projects/{project_id}/contracts{tail}"


async def _draft(client: AsyncClient, headers: dict, project_id: str) -> str:
    opened = await client.post(url(project_id), headers=headers)
    assert opened.status_code in (200, 201), opened.text
    return opened.json()["id"]


async def test_a_new_draft_gets_the_day_the_place_the_vat_the_consumer_and_the_client_who_accepts(async_client: AsyncClient, db_session, web):  # noqa: F811
    headers = await _signed_in(async_client, db_session)
    await _price(async_client, headers)
    await _profile(async_client, headers, vat_mode="RATE", vat_rate_percent=8)
    made = await _quick(async_client, headers)
    project = made["project_id"]
    contract = await _draft(async_client, headers, project)

    first = await async_client.post(url(project, f"/{contract}/prefill"), headers=headers)
    assert first.status_code == 200, first.text
    body = first.json()
    assert set(body["filled"]) == {"contract_date", "contract_place", "vat_rate_percent", "client_status", "who_accepts"}
    assert body["terms_from"] is None
    answers = body["contract"]["answers"]
    assert answers["contract_date"] == local_datetime(datetime.now(UTC)).date().isoformat()
    assert (answers["contract_place"], answers["vat_rate_percent"], answers["client_status"]) == ("Kraków", 8, "CONSUMER")
    assert body["contract"]["missing_required"] == ["conclusion_mode"]
    people = (await async_client.get(f"/api/projects/{project}/representatives", headers=headers)).json()["items"]
    assert [(p["side"], p["name"], p["may_accept_and_sign"]) for p in people] == [("CUSTOMER", "Jan Kowalski", True)]
    assert answers["who_accepts"] == [people[0]["id"]]

    again = (await async_client.post(url(project, f"/{contract}/prefill"), headers=headers)).json()
    assert again["filled"] == [] and again["contract"]["answers"] == answers
    assert len((await async_client.get(f"/api/projects/{project}/representatives", headers=headers)).json()["items"]) == 1


async def test_an_answer_of_the_owner_is_kept_and_a_customer_who_may_not_accept_is_not_chosen(async_client: AsyncClient, db_session, web):  # noqa: F811
    headers = await _signed_in(async_client, db_session)
    await _price(async_client, headers)
    project = (await _quick(async_client, headers))["project_id"]
    person = (await async_client.post(f"/api/projects/{project}/representatives",
                                      json={"side": "CUSTOMER", "name": "Jan Kowalski", "may_accept_and_sign": False}, headers=headers)).json()["id"]
    contract = await _draft(async_client, headers, project)
    await async_client.patch(url(project, f"/{contract}/answers"), json={"answers": {"contract_place": "Wieliczka"}}, headers=headers)
    body = (await async_client.post(url(project, f"/{contract}/prefill"), headers=headers)).json()
    assert body["contract"]["answers"]["contract_place"] == "Wieliczka"
    assert "who_accepts" not in body["filled"] and "vat_rate_percent" not in body["filled"]  # no VAT on the estimate: nothing to say
    people = (await async_client.get(f"/api/projects/{project}/representatives", headers=headers)).json()["items"]
    assert [p["id"] for p in people] == [person]  # no second customer


async def test_the_terms_of_the_latest_contract_of_another_object_come_over(async_client: AsyncClient, db_session, web):  # noqa: F811
    headers = await _signed_in(async_client, db_session)
    await _price(async_client, headers)
    first = (await _quick(async_client, headers))["project_id"]
    first_contract = await _draft(async_client, headers, first)
    terms = {"warranty_months": 24, "advance_percent": 30, "conclusion_mode": "OFF_PREMISES", "penalty_mode": "NONE",
             "payment_mode": "BY_STAGES", "payment_due_days": 7, "contract_place": "Łódź", "work_end_date": "2026-12-01"}
    saved = await async_client.patch(url(first, f"/{first_contract}/answers"), json={"answers": terms}, headers=headers)
    assert saved.status_code == 200, saved.text
    first_name = (await async_client.get(f"/api/projects/{first}", headers=headers)).json()["name"]

    second = (await _quick(async_client, headers))["project_id"]
    contract = await _draft(async_client, headers, second)
    body = (await async_client.post(url(second, f"/{contract}/prefill"), headers=headers)).json()
    answers = body["contract"]["answers"]
    assert body["terms_from"] == first_name
    assert {k: answers[k] for k in ("warranty_months", "advance_percent", "conclusion_mode", "penalty_mode", "payment_mode", "payment_due_days")} == {
        "warranty_months": 24, "advance_percent": 30, "conclusion_mode": "OFF_PREMISES", "penalty_mode": "NONE", "payment_mode": "BY_STAGES", "payment_due_days": 7}
    assert answers["contract_place"] == "Kraków" and "work_end_date" not in answers  # the facts are this object's
    assert body["contract"]["missing_required"] == []


async def test_only_a_draft_of_the_owner_is_filled(async_client: AsyncClient, db_session, web):  # noqa: F811
    headers = await _signed_in(async_client, db_session)
    await _price(async_client, headers)
    project = (await _quick(async_client, headers))["project_id"]
    contract = await _draft(async_client, headers, project)
    other = auth_header(await get_token(async_client, OTHER_USER))
    assert (await async_client.post(url(project, f"/{contract}/prefill"), headers=other)).status_code == 404
    assert (await async_client.post(url(project, f"/{contract}/prefill"))).status_code == 401
    await async_client.post(url(project, f"/{contract}/archive"), headers=headers)
    closed = await async_client.post(url(project, f"/{contract}/prefill"), headers=headers)
    assert closed.status_code == 409 and closed.json()["detail"]["code"] == "CONTRACT_NOT_EDITABLE"
