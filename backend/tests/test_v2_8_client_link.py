"""V2-8 -- the link for the client (docs/V2_8_PLAN_RU.md): the rules, the owner's side, the open page, the journal of consents."""
import hashlib
import json
import re
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_message_sender
from app.api.v1.endpoints import client_portal
from app.core.config import settings
from app.core.rate_limit import SlidingWindowLimiter
from app.domain import client_link as rules
from app.domain.exceptions import MessageChatUnavailableError, MessageDeliveryDisabledError, MessageRejectedError, MessageUnavailableError
from app.main import app
from app.models.client_link import ClientConsent, ClientLink, ClientProposal
from app.models.estimate import Estimate, EstimateStatus
from app.models.project import Project
from app.models.user import User
from tests.test_v2_6_vat import _price, _profile, _quick, _signed_in

PUBLIC = "/api/public/client"


@pytest.fixture(autouse=True)
def _fresh_limits():
    client_portal.reset_limits()
    yield
    client_portal.reset_limits()


@pytest.fixture
def web(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_PASSWORD_ENABLED", True)


# --- the rules -----------------------------------------------------------------------------------------------------------------------


def test_a_secret_is_long_random_and_only_its_hash_is_kept():
    first, second = rules.new_token(), rules.new_token()
    assert first != second and rules.looks_like_token(first) and len(first) == 43
    assert rules.hash_token(first) == hashlib.sha256(first.encode()).hexdigest() and rules.hash_token(first) != first


@pytest.mark.parametrize("value", [None, "", "short", "a" * 42, "a" * 44, "a" * 42 + "!", "a" * 42 + " ", "../" + "a" * 40])
def test_a_wrong_looking_secret_is_not_even_looked_up(value):
    assert not rules.looks_like_token(value)


def test_the_hash_of_what_is_shown_is_a_proof_of_the_words_and_the_numbers():
    assert rules.proposal_hash("Gruntowanie", "dwa razy", Decimal("100"), "PLN", 2) == rules.proposal_hash("Gruntowanie", "dwa razy", Decimal("100.00"), "PLN", 2)
    base = rules.proposal_hash("Gruntowanie", None, Decimal("100"), "PLN", None)
    for other in (
        rules.proposal_hash("Gruntowanie 2", None, Decimal("100"), "PLN", None),
        rules.proposal_hash("Gruntowanie", "x", Decimal("100"), "PLN", None),
        rules.proposal_hash("Gruntowanie", None, Decimal("100.01"), "PLN", None),
        rules.proposal_hash("Gruntowanie", None, Decimal("100"), "EUR", None),
        rules.proposal_hash("Gruntowanie", None, Decimal("100"), "PLN", 1),
    ):
        assert other != base


@pytest.mark.parametrize("raw,expected", [("  Jan   Kowalski ", "Jan Kowalski"), ("Jan\tKow\nalski", "Jan Kow alski"), ("Ян", "Ян"), ("Anna\x00Nowak", "Anna Nowak")])
def test_the_name_of_the_signer_is_tidied(raw, expected):
    assert rules.clean_name(raw) == expected


@pytest.mark.parametrize("raw,code", [(None, "NAME_REQUIRED"), ("", "NAME_REQUIRED"), (" J ", "NAME_REQUIRED"), ("\x00\x01  ", "NAME_REQUIRED"), ("x" * 81, "NAME_TOO_LONG")])
def test_a_missing_or_absurd_name_is_refused_with_a_code(raw, code):
    with pytest.raises(rules.ClientLinkError) as caught:
        rules.clean_name(raw)
    assert caught.value.code == code


@pytest.mark.parametrize("amount", [None, Decimal("0"), Decimal("-1"), Decimal("10000000.01"), Decimal("0.004")])
def test_a_wrong_amount_is_refused(amount):
    with pytest.raises(rules.ClientLinkError) as caught:
        rules.clean_amount(amount)
    assert caught.value.code == "AMOUNT_INVALID"


def test_the_words_and_the_days_of_a_proposal_are_limited():
    assert rules.clean_amount(Decimal("12.345")) == Decimal("12.35")
    assert rules.clean_days(0) is None and rules.clean_days(None) is None and rules.clean_days(7) == 7
    for bad in (-1, 366):
        with pytest.raises(rules.ClientLinkError):
            rules.clean_days(bad)
    assert rules.clean_description("  \r\n ") is None
    with pytest.raises(rules.ClientLinkError):
        rules.clean_description("x" * 2001)
    with pytest.raises(rules.ClientLinkError):
        rules.clean_title("   ")
    with pytest.raises(rules.ClientLinkError):
        rules.clean_title("x" * 121)


def test_every_text_exists_in_four_languages_with_the_same_places_to_fill():
    for key, entry in rules.texts().items():
        assert set(entry) == set(rules.LANGUAGES), key
        marks = {lang: sorted(re.findall(r"\{[^}]*\}", entry[lang])) for lang in rules.LANGUAGES}
        assert len({tuple(m) for m in marks.values()}) == 1, (key, marks)


def test_the_consent_names_the_work_the_sum_and_the_days_in_the_language_asked_for():
    kw = {"contractor": "Vvv Remonty", "amount": Decimal("1234.5"), "currency": "PLN", "title": "Gruntowanie", "extra_days": 3}
    pl = rules.statement("proposal_accept", "pl", **kw)
    assert "„Gruntowanie”" in pl and "1234,50 PLN" in pl and "o 3 dni" in pl and "Vvv Remonty" in pl
    assert "1234.50 PLN" in rules.statement("proposal_decline", "en", **kw) and "do not accept" in rules.statement("proposal_decline", "en", **kw)
    assert "{" not in rules.statement("estimate_accept", "uk", contractor="X", amount=Decimal("5"), currency="PLN", version=2)
    assert rules.statement("proposal_accept", "de", **kw) == pl  # an unknown language falls back to Polish


def test_the_limiter_counts_a_sliding_window_and_forgets():
    limiter = SlidingWindowLimiter(limit=3, window_seconds=10, max_keys=2)
    assert [limiter.allow("a", now=t) for t in (0, 1, 2, 3)] == [True, True, True, False]
    assert limiter.retry_after("a", now=3) == 8
    assert limiter.allow("a", now=10.5)  # the first hit has left the window
    assert limiter.allow("b", now=11) and limiter.allow("c", now=11)  # the table is capped: it never grows without end
    assert len(limiter._hits) <= 2


def test_an_old_burst_does_not_close_the_door_for_ever():
    limiter = SlidingWindowLimiter(limit=3, window_seconds=10)
    for t in (0, 1, 2):
        assert limiter.allow("a", now=t)
    assert limiter.retry_after("a", now=3) > 0
    assert limiter.retry_after("a", now=50) == 0  # asking is enough: nothing in the window, nothing to wait for
    assert limiter.allow("a", now=50)


# --- the world -----------------------------------------------------------------------------------------------------------------------


async def make_world(client: AsyncClient, db, *, finalize: bool = True, email: str = "jan@example.pl") -> dict:
    headers = await _signed_in(client, db, email)
    await _price(client, headers)
    await _profile(client, headers, vat_mode="RATE", vat_rate_percent=23)
    made = await _quick(client, headers)
    if finalize:
        done = await client.post(f"/api/projects/{made['project_id']}/estimates/{made['estimate_id']}/finalize", headers=headers)
        assert done.status_code == 200, done.text
    return {"headers": headers, "project": made["project_id"], "estimate": made["estimate_id"], "base": f"/api/projects/{made['project_id']}"}


async def issue(client, world, language="pl") -> str:
    made = await client.post(world["base"] + "/client-link", json={"language": language}, headers=world["headers"])
    assert made.status_code == 201, made.text
    return made.json()["token"]


def door(token: str, **extra) -> dict:
    return {"X-Client-Link": token, **extra}


async def open_page(client, token, **params):
    return await client.get(PUBLIC, headers=door(token), params=params)


def accept_body(page: dict, name="Jan Kowalski", agree=True) -> dict:
    est = page["estimate"]
    return {"estimate_id": est["id"], "version": est["version"], "hash": est["hash"], "decision": "ACCEPT", "signer_name": name, "agree": agree}


# --- the owner's side ----------------------------------------------------------------------------------------------------------------


async def test_there_is_no_link_until_one_is_made_and_the_secret_is_shown_once(async_client, db_session, web):
    world = await make_world(async_client, db_session)
    assert (await async_client.get(world["base"] + "/client-link", headers=world["headers"])).json() == {"link": None}
    made = await async_client.post(world["base"] + "/client-link", json={"language": "uk"}, headers=world["headers"])
    assert made.status_code == 201
    body = made.json()
    token = body["token"]
    assert rules.looks_like_token(token) and body["link"]["language"] == "uk" and body["link"]["view_count"] == 0 and body["link"]["expired"] is False
    expires = datetime.fromisoformat(body["link"]["expires_at"])
    assert timedelta(days=29, hours=23) < expires - datetime.now(UTC if expires.tzinfo else None) < timedelta(days=30, minutes=1)
    status = (await async_client.get(world["base"] + "/client-link", headers=world["headers"])).json()
    assert token not in json.dumps(status) and status["link"]["id"] == body["link"]["id"]
    row = (await db_session.execute(select(ClientLink))).scalar_one()
    assert row.token_hash == rules.hash_token(token) and token not in {str(v) for v in vars(row).values()}


async def test_a_new_link_stops_the_old_one_and_a_revoked_link_is_gone(async_client, db_session, web):
    world = await make_world(async_client, db_session)
    first = await issue(async_client, world)
    second = await issue(async_client, world, "en")
    assert first != second
    assert (await open_page(async_client, first)).status_code == 410
    assert (await open_page(async_client, second)).status_code == 200
    assert (await async_client.delete(world["base"] + "/client-link", headers=world["headers"])).status_code == 204
    gone = await open_page(async_client, second)
    assert gone.status_code == 410 and gone.json()["detail"]["code"] == "LINK_INACTIVE"
    assert (await async_client.get(world["base"] + "/client-link", headers=world["headers"])).json() == {"link": None}
    assert (await async_client.delete(world["base"] + "/client-link", headers=world["headers"])).status_code == 404
    assert (await async_client.post(world["base"] + "/client-link/extend", headers=world["headers"])).status_code == 404
    third = await issue(async_client, world)  # after a revoke a new one can be made again
    assert (await open_page(async_client, third)).status_code == 200


async def test_an_expired_link_answers_gone_and_extending_brings_it_back(async_client, db_session, web):
    world = await make_world(async_client, db_session)
    token = await issue(async_client, world)
    await db_session.execute(update(ClientLink).values(expires_at=datetime.now(UTC) - timedelta(minutes=1)))
    await db_session.commit()
    assert (await open_page(async_client, token)).status_code == 410
    assert (await async_client.get(world["base"] + "/client-link", headers=world["headers"])).json()["link"]["expired"] is True
    extended = await async_client.post(world["base"] + "/client-link/extend", headers=world["headers"])
    assert extended.status_code == 200 and extended.json()["link"]["expired"] is False
    assert (await open_page(async_client, token)).status_code == 200


async def test_the_owner_calls_need_the_login_and_an_owner_never_reaches_another_owners_object(async_client, db_session, web):
    mine = await make_world(async_client, db_session)
    other = await make_world(async_client, db_session, email="ewa@example.pl")
    calls = [
        ("get", "/client-link", None), ("post", "/client-link", {"language": "pl"}), ("post", "/client-link/extend", None), ("delete", "/client-link", None),
        ("get", "/client-proposals", None), ("post", "/client-proposals", {"title": "x", "amount": "10"}), ("get", "/client-journal", None),
    ]
    for method, tail, body in calls:
        assert (await async_client.request(method.upper(), mine["base"] + tail, json=body)).status_code == 401, tail
        stranger = await async_client.request(method.upper(), mine["base"] + tail, json=body, headers=other["headers"])
        assert stranger.status_code == 404, (tail, stranger.text)
    assert (await db_session.execute(select(ClientLink))).first() is None
    assert (await db_session.execute(select(ClientProposal))).first() is None


# --- the open page -------------------------------------------------------------------------------------------------------------------


async def test_the_page_shows_the_estimate_with_its_sums_and_nothing_else(async_client, db_session, web):
    world = await make_world(async_client, db_session)
    token = await issue(async_client, world)
    response = await open_page(async_client, token)
    assert response.status_code == 200
    page = response.json()
    assert set(page) == {"link", "lang", "contractor", "project", "estimate", "proposals"}
    assert page["lang"] == "pl" and page["contractor"]["name"] == "Vvv Remonty" and page["project"]["city"] == "Kraków"
    est = page["estimate"]
    assert est["status"] == "FINAL" and est["consent"] is None and est["version"] == 1
    assert set(est) == {"id", "version", "status", "name", "currency", "total", "vat_mode", "vat_rate_percent", "vat_amount", "gross_total", "hash", "lines", "consent", "accept_statement", "decline_statement"}
    assert Decimal(est["total"]) == Decimal("2837.12") and Decimal(est["gross_total"]) == Decimal("3489.66") and Decimal(est["vat_amount"]) == Decimal("652.54")
    assert est["lines"] and set(est["lines"][0]) == {"position", "room_name", "surface_name", "description", "unit", "quantity", "unit_price", "amount"}
    assert sum(Decimal(ln["amount"]) for ln in est["lines"]) == Decimal(est["total"])
    assert "3489,66" in est["accept_statement"]["pl"] and "wyceną nr 1" in est["accept_statement"]["pl"]
    assert est["accept_statement"]["text"] == est["accept_statement"]["pl"]
    assert all(ln["description"] and not ln["description"].startswith("pricebook") for ln in est["lines"])  # the Polish names of the PDF, never the keys
    assert any(ln["surface_name"] and not ln["surface_name"].startswith("Wall ") for ln in est["lines"])
    # nothing that identifies the owner or the account, no price book, no codes
    raw = response.text
    assert "pricebook." not in raw
    for forbidden in ("owner_id", "project_id", "price_item", "item_code", "token_hash", "email\": \"jan@example.pl", "telegram"):
        assert forbidden not in raw, forbidden


async def test_the_answers_are_never_cached_indexed_or_passed_on_in_a_referrer(async_client, db_session, web):
    world = await make_world(async_client, db_session)
    token = await issue(async_client, world)
    for response in (await open_page(async_client, token), await open_page(async_client, "x" * 43), await async_client.get(PUBLIC)):
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-robots-tag"] == "noindex, nofollow"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert response.headers["x-content-type-options"] == "nosniff"


async def test_a_page_counts_its_openings_and_the_owner_sees_the_last_one(async_client, db_session, web):
    world = await make_world(async_client, db_session)
    token = await issue(async_client, world)
    await open_page(async_client, token)
    await open_page(async_client, token)
    link = (await async_client.get(world["base"] + "/client-link", headers=world["headers"])).json()["link"]
    assert link["view_count"] == 2 and link["last_viewed_at"] is not None


@pytest.mark.parametrize("header", [None, "", "short", "a" * 43, "a" * 44, "../etc/passwd", "a" * 99])
async def test_every_wrong_secret_gets_the_same_not_found(async_client, db_session, web, header):
    await make_world(async_client, db_session)
    headers = {} if header is None else {"X-Client-Link": header}
    response = await async_client.get(PUBLIC, headers=headers)
    assert response.status_code == 404 and response.json()["detail"] == {"code": "NOT_FOUND", "message": "the link does not exist"}


async def test_the_secret_in_the_path_or_the_query_is_not_a_door(async_client, db_session, web):
    world = await make_world(async_client, db_session)
    token = await issue(async_client, world)
    assert (await async_client.get(PUBLIC, params={"token": token})).status_code == 404
    assert (await async_client.get(f"{PUBLIC}/{token}")).status_code in (404, 405)


async def test_a_draft_estimate_is_not_shown_and_the_latest_final_one_is(async_client, db_session, web):
    world = await make_world(async_client, db_session, finalize=False)
    token = await issue(async_client, world)
    assert (await open_page(async_client, token)).json()["estimate"] is None
    await async_client.post(f"{world['base']}/estimates/{world['estimate']}/finalize", headers=world["headers"])
    shown = (await open_page(async_client, token)).json()["estimate"]
    assert shown["id"] == world["estimate"] and shown["version"] == 1


async def test_the_page_speaks_the_language_asked_for_and_the_polish_text_stays(async_client, db_session, web):
    world = await make_world(async_client, db_session)
    token = await issue(async_client, world, "ru")
    default = (await open_page(async_client, token)).json()
    assert default["lang"] == "ru" and "Я ознакомился" in default["estimate"]["accept_statement"]["text"]
    english = (await open_page(async_client, token, lang="en")).json()
    assert english["lang"] == "en" and "I have read estimate no. 1" in english["estimate"]["accept_statement"]["text"]
    assert english["estimate"]["accept_statement"]["pl"].startswith("Zapoznałem/am się")
    assert (await open_page(async_client, token, lang="zz")).json()["lang"] == "pl"


# --- accepting the estimate ----------------------------------------------------------------------------------------------------------


async def test_the_client_accepts_the_estimate_and_the_journal_holds_the_proof(async_client, db_session, web):
    world = await make_world(async_client, db_session)
    token = await issue(async_client, world)
    page = (await open_page(async_client, token)).json()
    sent = await async_client.post(
        f"{PUBLIC}/estimate/decide", json=accept_body(page, "  Jan   Kowalski "), headers=door(token, **{"User-Agent": "Mozilla/5.0 test", "CF-Connecting-IP": "203.0.113.7"})
    )
    assert sent.status_code == 200, sent.text
    after = sent.json()["estimate"]
    assert after["status"] == "ACCEPTED" and after["accept_statement"] is None
    assert after["consent"]["signer_name"] == "Jan Kowalski" and after["consent"]["kind"] == "ESTIMATE_ACCEPTED"
    estimate = (await db_session.execute(select(Estimate).execution_options(populate_existing=True))).scalar_one()
    assert estimate.status == EstimateStatus.ACCEPTED
    row = (await db_session.execute(select(ClientConsent))).scalar_one()
    assert row.subject_hash == page["estimate"]["hash"] and row.amount == Decimal("3489.66") and row.currency == "PLN" and row.estimate_version == 1
    assert row.statement == page["estimate"]["accept_statement"]["pl"] and row.statement_lang == "pl"
    assert re.fullmatch(r"[0-9a-f]{64}", row.ip_hash) and re.fullmatch(r"[0-9a-f]{64}", row.agent_hash)
    assert "203.0.113.7" not in row.ip_hash and "Mozilla" not in row.agent_hash and row.ip_hash == rules.hash_value(settings.JWT_SECRET_KEY, "203.0.113.7")
    journal = (await async_client.get(world["base"] + "/client-journal", headers=world["headers"])).json()["items"]
    assert len(journal) == 1 and journal[0]["signer_name"] == "Jan Kowalski" and Decimal(journal[0]["amount"]) == Decimal("3489.66")
    assert "ip_hash" not in journal[0] and "agent_hash" not in journal[0]


async def test_the_acceptance_needs_the_box_a_name_and_the_page_the_client_saw(async_client, db_session, web):
    world = await make_world(async_client, db_session)
    token = await issue(async_client, world)
    page = (await open_page(async_client, token)).json()
    post = lambda body: async_client.post(f"{PUBLIC}/estimate/decide", json=body, headers=door(token))  # noqa: E731
    no_box = await post(accept_body(page, agree=False))
    assert no_box.status_code == 422 and no_box.json()["detail"]["code"] == "AGREE_REQUIRED"
    no_name = await post(accept_body(page, name=" "))
    assert no_name.status_code == 422 and no_name.json()["detail"]["code"] == "NAME_REQUIRED"
    stale = await post({**accept_body(page), "hash": "0" * 64})
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "ESTIMATE_CHANGED"
    old_version = await post({**accept_body(page), "version": 7})
    assert old_version.status_code == 409 and old_version.json()["detail"]["code"] == "ESTIMATE_CHANGED"
    other = await post({**accept_body(page), "estimate_id": "00000000-0000-0000-0000-000000000001"})
    assert other.status_code == 409
    assert (await post({**accept_body(page), "extra": 1})).status_code == 422
    assert (await post({"estimate_id": "nope"})).status_code == 422
    assert (await db_session.execute(select(ClientConsent))).first() is None
    estimate = (await db_session.execute(select(Estimate).execution_options(populate_existing=True))).scalar_one()
    assert estimate.status == EstimateStatus.FINAL


async def test_a_second_acceptance_is_refused_and_the_journal_keeps_one_row(async_client, db_session, web):
    world = await make_world(async_client, db_session)
    token = await issue(async_client, world)
    page = (await open_page(async_client, token)).json()
    assert (await async_client.post(f"{PUBLIC}/estimate/decide", json=accept_body(page), headers=door(token))).status_code == 200
    again = await async_client.post(f"{PUBLIC}/estimate/decide", json=accept_body(page, "Ewa Nowak"), headers=door(token))
    assert again.status_code == 409 and again.json()["detail"]["code"] == "ALREADY_DECIDED"
    assert len((await db_session.execute(select(ClientConsent))).scalars().all()) == 1


async def test_an_estimate_approved_in_a_contract_is_shown_as_approved_without_a_form(async_client, db_session, web):
    world = await make_world(async_client, db_session)
    token = await issue(async_client, world)
    await db_session.execute(update(Estimate).values(status=EstimateStatus.ACCEPTED))  # what the signing of a contract does
    await db_session.commit()
    shown = (await open_page(async_client, token)).json()["estimate"]
    assert shown["status"] == "ACCEPTED" and shown["consent"] is None and shown["accept_statement"] is None
    page = (await open_page(async_client, token)).json()
    recorded = await async_client.post(f"{PUBLIC}/estimate/decide", json=accept_body(page), headers=door(token))
    assert recorded.status_code == 200  # the page offers no form, but a consent sent anyway is recorded; the journal then holds it
    assert (await db_session.execute(select(ClientConsent))).scalar_one().kind == "ESTIMATE_ACCEPTED"


async def test_the_page_stays_open_after_the_acceptance_and_a_changed_estimate_waits_for_a_new_one(async_client, db_session, web):
    world = await make_world(async_client, db_session)
    token = await issue(async_client, world)
    page = (await open_page(async_client, token)).json()
    await async_client.post(f"{PUBLIC}/estimate/decide", json=accept_body(page), headers=door(token))
    again = (await open_page(async_client, token)).json()["estimate"]
    assert again["status"] == "ACCEPTED" and again["consent"]["signer_name"] == "Jan Kowalski"
    # the estimate is changed after the acceptance: a new version is made and finalized; the page now shows it, waiting
    regenerated = await async_client.post(f"{world['base']}/estimates/generate", headers=world["headers"])
    assert regenerated.status_code in (200, 201), regenerated.text
    new_id = regenerated.json()["id"]
    done = await async_client.post(f"{world['base']}/estimates/{new_id}/finalize", headers=world["headers"])
    assert done.status_code == 200, done.text
    fresh = (await open_page(async_client, token)).json()["estimate"]
    assert fresh["id"] == new_id and fresh["version"] == 2 and fresh["status"] == "FINAL" and fresh["consent"] is None
    stale = await async_client.post(f"{PUBLIC}/estimate/decide", json=accept_body({"estimate": again}), headers=door(token))
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "ESTIMATE_CHANGED"


# --- the proposals of extra work ----------------------------------------------------------------------------------------------------------------


async def propose(client, world, title="Gruntowanie sufitu", amount="450.50", days=2, description="Dodatkowa warstwa gruntu"):
    made = await client.post(
        world["base"] + "/client-proposals", json={"title": title, "amount": amount, "extra_days": days, "description": description}, headers=world["headers"]
    )
    assert made.status_code == 201, made.text
    return made.json()


async def test_the_owner_writes_a_proposal_and_the_client_agrees(async_client, db_session, web):
    world = await make_world(async_client, db_session)
    token = await issue(async_client, world)
    proposal = await propose(async_client, world)
    assert proposal["status"] == "OPEN" and proposal["sequence"] == 1 and proposal["currency"] == "PLN"
    shown = (await open_page(async_client, token)).json()["proposals"]
    assert len(shown) == 1 and shown[0]["title"] == "Gruntowanie sufitu" and Decimal(shown[0]["amount"]) == Decimal("450.50")
    assert "450,50 PLN" in shown[0]["accept_statement"]["pl"] and "o 2 dni" in shown[0]["accept_statement"]["pl"] and "nie akceptuję" in shown[0]["decline_statement"]["pl"]
    assert set(shown[0]) == {"id", "sequence", "title", "description", "amount", "currency", "extra_days", "status", "hash", "created_at", "consent", "accept_statement", "decline_statement"}
    decided = await async_client.post(
        f"{PUBLIC}/proposals/{shown[0]['id']}/decide", json={"decision": "ACCEPT", "hash": shown[0]["hash"], "signer_name": "Jan Kowalski", "agree": True}, headers=door(token)
    )
    assert decided.status_code == 200, decided.text
    after = decided.json()["proposals"][0]
    assert after["status"] == "ACCEPTED" and after["accept_statement"] is None and after["consent"]["kind"] == "PROPOSAL_ACCEPTED"
    listed = (await async_client.get(world["base"] + "/client-proposals", headers=world["headers"])).json()
    assert listed["items"][0]["status"] == "ACCEPTED" and listed["items"][0]["decided_at"] is not None
    journal = (await async_client.get(world["base"] + "/client-journal", headers=world["headers"])).json()["items"]
    assert journal[0]["kind"] == "PROPOSAL_ACCEPTED" and journal[0]["proposal_id"] == proposal["id"] and Decimal(journal[0]["amount"]) == Decimal("450.50")


async def test_the_client_may_decline_and_a_decision_is_final(async_client, db_session, web):
    world = await make_world(async_client, db_session)
    token = await issue(async_client, world)
    await propose(async_client, world)
    item = (await open_page(async_client, token)).json()["proposals"][0]
    body = {"decision": "DECLINE", "hash": item["hash"], "signer_name": "Jan Kowalski", "agree": True}
    declined = await async_client.post(f"{PUBLIC}/proposals/{item['id']}/decide", json=body, headers=door(token))
    assert declined.status_code == 200 and declined.json()["proposals"][0]["status"] == "DECLINED"
    again = await async_client.post(f"{PUBLIC}/proposals/{item['id']}/decide", json={**body, "decision": "ACCEPT"}, headers=door(token))
    assert again.status_code == 409 and again.json()["detail"]["code"] == "ALREADY_DECIDED"
    withdraw = await async_client.post(f"{world['base']}/client-proposals/{item['id']}/withdraw", headers=world["headers"])
    assert withdraw.status_code == 409 and withdraw.json()["detail"]["code"] == "PROPOSAL_NOT_OPEN"
    assert (await db_session.execute(select(ClientConsent.kind))).scalars().all() == ["PROPOSAL_DECLINED"]


async def test_a_withdrawn_proposal_disappears_from_the_page_and_cannot_be_decided(async_client, db_session, web):
    world = await make_world(async_client, db_session)
    token = await issue(async_client, world)
    proposal = await propose(async_client, world)
    item = (await open_page(async_client, token)).json()["proposals"][0]
    assert (await async_client.post(f"{world['base']}/client-proposals/{proposal['id']}/withdraw", headers=world["headers"])).json()["status"] == "WITHDRAWN"
    assert (await open_page(async_client, token)).json()["proposals"] == []
    late = await async_client.post(
        f"{PUBLIC}/proposals/{item['id']}/decide", json={"decision": "ACCEPT", "hash": item["hash"], "signer_name": "Jan Kowalski", "agree": True}, headers=door(token)
    )
    assert late.status_code == 404
    assert (await async_client.post(f"{world['base']}/client-proposals/{proposal['id']}/withdraw", headers=world["headers"])).status_code == 409


async def test_a_proposal_is_decided_only_on_what_the_client_saw(async_client, db_session, web):
    world = await make_world(async_client, db_session)
    token = await issue(async_client, world)
    await propose(async_client, world)
    item = (await open_page(async_client, token)).json()["proposals"][0]
    url = f"{PUBLIC}/proposals/{item['id']}/decide"
    ok = {"decision": "ACCEPT", "hash": item["hash"], "signer_name": "Jan Kowalski", "agree": True}
    assert (await async_client.post(url, json={**ok, "hash": "f" * 64}, headers=door(token))).json()["detail"]["code"] == "PROPOSAL_CHANGED"
    assert (await async_client.post(url, json={**ok, "agree": False}, headers=door(token))).json()["detail"]["code"] == "AGREE_REQUIRED"
    assert (await async_client.post(url, json={**ok, "signer_name": "A"}, headers=door(token))).json()["detail"]["code"] == "NAME_REQUIRED"
    assert (await async_client.post(url, json={**ok, "decision": "MAYBE"}, headers=door(token))).status_code == 422
    assert (await async_client.post(f"{PUBLIC}/proposals/00000000-0000-0000-0000-000000000009/decide", json=ok, headers=door(token))).status_code == 404
    assert (await db_session.execute(select(ClientConsent))).first() is None


async def test_the_proposals_of_another_object_or_owner_are_out_of_reach(async_client, db_session, web):
    mine = await make_world(async_client, db_session)
    other = await make_world(async_client, db_session, email="ewa@example.pl")
    my_token, other_token = await issue(async_client, mine), await issue(async_client, other)
    foreign = await propose(async_client, other, title="Cudze prace")
    assert (await open_page(async_client, my_token)).json()["proposals"] == []
    item = (await open_page(async_client, other_token)).json()["proposals"][0]
    body = {"decision": "ACCEPT", "hash": item["hash"], "signer_name": "Jan Kowalski", "agree": True}
    assert (await async_client.post(f"{PUBLIC}/proposals/{foreign['id']}/decide", json=body, headers=door(my_token))).status_code == 404
    assert (await async_client.post(f"{mine['base']}/client-proposals/{foreign['id']}/withdraw", headers=mine["headers"])).status_code == 404


async def test_the_proposals_are_limited_and_checked(async_client, db_session, web):
    world = await make_world(async_client, db_session)
    for bad in ({"title": " ", "amount": "10"}, {"title": "x", "amount": "0"}, {"title": "x", "amount": "-5"}, {"title": "x", "amount": "10", "extra_days": 4000}, {"amount": "10"}, {"title": "x", "amount": "abc"}):
        assert (await async_client.post(world["base"] + "/client-proposals", json=bad, headers=world["headers"])).status_code == 422, bad
    for n in range(rules.MAX_PROPOSALS):
        await propose(async_client, world, title=f"Praca {n}")
    over = await async_client.post(world["base"] + "/client-proposals", json={"title": "Jeszcze jedna", "amount": "10"}, headers=world["headers"])
    assert over.status_code == 422 and over.json()["detail"]["code"] == "TOO_MANY_PROPOSALS"


async def test_a_proposal_is_never_changed_after_it_is_made(async_client, db_session, web):
    world = await make_world(async_client, db_session)
    proposal = await propose(async_client, world)
    for method in ("PUT", "PATCH", "DELETE"):
        assert (await async_client.request(method, f"{world['base']}/client-proposals/{proposal['id']}", json={"amount": "1"}, headers=world["headers"])).status_code in (404, 405)


# --- the journal and the doors -------------------------------------------------------------------------------------------------------


def test_the_journal_has_no_door_that_changes_it():
    from app.main import app

    paths = app.openapi()["paths"]
    for path, ops in paths.items():
        if "client-journal" in path or "consent" in path:
            assert set(ops) == {"get"}, path
    assert {m for m in paths["/api/projects/{project_id}/client-journal"]} == {"get"}


def test_exactly_three_open_operations_belong_to_the_client():
    from app.main import app

    opened = {
        (method.upper(), path)
        for path, ops in app.openapi()["paths"].items()
        for method, op in ops.items()
        if path.startswith("/api/public/") and not op.get("security")
    }
    assert opened == {("GET", PUBLIC), ("POST", PUBLIC + "/estimate/decide"), ("POST", PUBLIC + "/proposals/{proposal_id}/decide")}


async def test_too_many_wrong_secrets_from_one_address_close_the_door_for_a_while(async_client, db_session, web):
    world = await make_world(async_client, db_session)
    token = await issue(async_client, world)
    heads = {"CF-Connecting-IP": "198.51.100.9"}
    codes = [(await async_client.get(PUBLIC, headers={**heads, "X-Client-Link": "b" * 43})).status_code for _ in range(22)]
    assert codes[:20] == [404] * 20 and codes[20:] == [429, 429]
    blocked = await async_client.get(PUBLIC, headers={**heads, "X-Client-Link": token})
    assert blocked.status_code == 429 and blocked.json()["detail"]["code"] == "RATE_LIMITED" and int(blocked.headers["retry-after"]) > 0
    assert (await async_client.get(PUBLIC, headers={"CF-Connecting-IP": "198.51.100.10", "X-Client-Link": token})).status_code == 200  # another address is not punished


async def test_the_presses_are_counted_too(async_client, db_session, web):
    world = await make_world(async_client, db_session)
    token = await issue(async_client, world)
    page = (await open_page(async_client, token)).json()
    codes = [(await async_client.post(f"{PUBLIC}/estimate/decide", json=accept_body(page, agree=False), headers=door(token))).status_code for _ in range(22)]
    assert codes[:20] == [422] * 20 and codes[20:] == [429, 429]


# --- the stored data -----------------------------------------------------------------------------------------------------------------


async def test_with_the_encryption_on_the_words_of_the_client_and_the_proposal_are_ciphertext(async_client, db_session, web, encryption_on):
    world = await make_world(async_client, db_session)
    token = await issue(async_client, world)
    await propose(async_client, world, title="Sekretna praca", description="Szczegóły dla klienta")
    page = (await open_page(async_client, token)).json()
    assert page["proposals"][0]["title"] == "Sekretna praca"
    await async_client.post(f"{PUBLIC}/estimate/decide", json=accept_body(page, "Zofia Wójcik"), headers=door(token))
    raw = {
        "title": (await db_session.execute(text("select title from client_proposals"))).scalar_one(),
        "description": (await db_session.execute(text("select description from client_proposals"))).scalar_one(),
        "signer": (await db_session.execute(text("select signer_name from client_consents"))).scalar_one(),
    }
    assert all(v.startswith("enc1:") for v in raw.values()), raw
    assert "Sekretna" not in raw["title"] and "Zofia" not in raw["signer"]
    journal = (await async_client.get(world["base"] + "/client-journal", headers=world["headers"])).json()["items"]
    assert journal[0]["signer_name"] == "Zofia Wójcik"


async def test_the_links_and_the_journal_go_with_the_object(async_client, db_session, web):
    world = await make_world(async_client, db_session)
    token = await issue(async_client, world)
    await propose(async_client, world)
    page = (await open_page(async_client, token)).json()
    await async_client.post(f"{PUBLIC}/estimate/decide", json=accept_body(page), headers=door(token))
    await db_session.execute(delete(Project).where(Project.id == uuid.UUID(world["project"])))
    await db_session.commit()
    assert (await db_session.execute(select(ClientLink))).first() is None
    assert (await db_session.execute(select(ClientConsent))).first() is None
    assert (await db_session.execute(select(ClientProposal))).first() is None


# --- the message to the owner (V2-8a) ----------------------------------------------------------------------------------------------------


class FakeSender:
    def __init__(self, *outcomes):
        self.calls: list[tuple[int, str, str | None, str]] = []
        self.outcomes = list(outcomes)

    async def send_message(self, chat_id, text, *, open_url=None, button_text=""):
        self.calls.append((chat_id, text, open_url, button_text))
        outcome = self.outcomes.pop(0) if self.outcomes else None
        if outcome is not None:
            raise outcome


@pytest.fixture
def sender():
    fake = FakeSender()
    app.dependency_overrides[get_message_sender] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_message_sender, None)


async def with_telegram(db, chat_id=777001, language_code="uk"):
    await db.execute(update(User).values(telegram_user_id=chat_id, language_code=language_code))
    await db.commit()


async def approve(client, token, page, name="Jan Kowalski"):
    return await client.post(f"{PUBLIC}/estimate/decide", json=accept_body(page, name), headers=door(token))


async def test_the_owner_is_told_in_telegram_that_the_client_approved_the_estimate(async_client, db_session, web, sender, monkeypatch):
    monkeypatch.setattr(settings, "CALENDAR_WEB_APP_URL", "https://plan-estimate.pl")
    world = await make_world(async_client, db_session)
    await with_telegram(db_session)
    token = await issue(async_client, world)
    page = (await open_page(async_client, token)).json()
    assert (await approve(async_client, token, page)).status_code == 200
    assert len(sender.calls) == 1
    chat, text, url, button = sender.calls[0]
    assert chat == 777001 and url == f"https://plan-estimate.pl?open=project:{world['project']}"
    assert text.startswith("✅ Клієнт Jan Kowalski прийняв кошторис № 1") and "3489,66 PLN" in text and "\n" not in text  # Telegram language of the owner: Ukrainian
    assert button == "Відкрити об’єкт"


async def test_the_owner_chooses_the_language_of_the_message_in_the_settings_of_the_calendar(async_client, db_session, web, sender):
    world = await make_world(async_client, db_session)
    await with_telegram(db_session, language_code="ru")
    saved = await async_client.put("/api/calendar/settings", json={"timezone": "Europe/Warsaw", "language": "en"}, headers=world["headers"])
    assert saved.status_code == 200, saved.text
    token = await issue(async_client, world)
    await approve(async_client, token, (await open_page(async_client, token)).json())
    assert sender.calls[0][1].startswith("✅ The client Jan Kowalski approved estimate no. 1") and "3489.66 PLN" in sender.calls[0][1]
    assert sender.calls[0][2] is None and sender.calls[0][3] == "Open the property"  # no address of the application configured: no address on the button


async def test_a_proposal_agreed_or_declined_is_told_with_its_title_and_amount(async_client, db_session, web, sender):
    world = await make_world(async_client, db_session)
    await with_telegram(db_session, language_code="pl")
    token = await issue(async_client, world)
    await propose(async_client, world, title="Gruntowanie sufitu", amount="450.50")
    await propose(async_client, world, title="Druga warstwa", amount="99")
    first, second = (await open_page(async_client, token)).json()["proposals"]
    for item, decision in ((first, "ACCEPT"), (second, "DECLINE")):
        body = {"decision": decision, "hash": item["hash"], "signer_name": "Jan\nKowalski", "agree": True}
        assert (await async_client.post(f"{PUBLIC}/proposals/{item['id']}/decide", json=body, headers=door(token))).status_code == 200
    texts = [call[1] for call in sender.calls]
    assert texts[0].startswith("✅ Klient Jan Kowalski zgodził się na pracę dodatkową „Gruntowanie sufitu”") and "450,50 PLN" in texts[0]
    assert texts[1].startswith("❌ Klient Jan Kowalski odrzucił pracę dodatkową „Druga warstwa”") and "99,00 PLN" in texts[1]


async def test_an_owner_without_a_telegram_chat_gets_no_message(async_client, db_session, web, sender):
    world = await make_world(async_client, db_session)  # an account with a password has no chat
    token = await issue(async_client, world)
    assert (await approve(async_client, token, (await open_page(async_client, token)).json())).status_code == 200
    assert sender.calls == []


async def test_a_refused_press_sends_nothing_and_a_second_one_sends_nothing_more(async_client, db_session, web, sender):
    world = await make_world(async_client, db_session)
    await with_telegram(db_session)
    token = await issue(async_client, world)
    page = (await open_page(async_client, token)).json()
    assert (await async_client.post(f"{PUBLIC}/estimate/decide", json=accept_body(page, agree=False), headers=door(token))).status_code == 422
    assert (await async_client.post(f"{PUBLIC}/estimate/decide", json={**accept_body(page), "hash": "0" * 64}, headers=door(token))).status_code == 409
    assert sender.calls == []
    assert (await approve(async_client, token, page)).status_code == 200
    assert (await approve(async_client, token, page, "Ewa Nowak")).status_code == 409
    assert len(sender.calls) == 1


@pytest.mark.parametrize(
    "failure",
    [MessageChatUnavailableError("blocked"), MessageUnavailableError("down", retry_after=5), MessageRejectedError("no"), MessageDeliveryDisabledError("off")],
)
async def test_a_message_that_does_not_go_never_costs_the_client_the_consent(async_client, db_session, web, failure, caplog):
    fake = FakeSender(failure)
    app.dependency_overrides[get_message_sender] = lambda: fake
    try:
        world = await make_world(async_client, db_session)
        await with_telegram(db_session)
        token = await issue(async_client, world)
        page = (await open_page(async_client, token)).json()
        with caplog.at_level("INFO"):
            response = await approve(async_client, token, page)
        assert response.status_code == 200 and response.json()["estimate"]["status"] == "ACCEPTED"
        assert len(fake.calls) == 1
        assert (await db_session.execute(select(ClientConsent.kind))).scalars().all() == ["ESTIMATE_ACCEPTED"]
        logged = " ".join(record.getMessage() for record in caplog.records)
        assert "the owner was not told" in logged or "switched off" in logged
        assert "Jan Kowalski" not in logged and "777001" not in logged  # no name of the client, no chat in the log
    finally:
        app.dependency_overrides.pop(get_message_sender, None)


async def test_a_message_that_cannot_be_put_together_is_logged_and_the_client_still_succeeds(async_client, db_session, web, sender, monkeypatch, caplog):
    async def broken(self, link, consent):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.domain.services.client_portal_service.ClientPortalService.owner_notice", broken)
    world = await make_world(async_client, db_session)
    await with_telegram(db_session)
    token = await issue(async_client, world)
    with caplog.at_level("ERROR"):
        response = await approve(async_client, token, (await open_page(async_client, token)).json())
    assert response.status_code == 200 and sender.calls == []
    assert any("could not be put together" in record.getMessage() for record in caplog.records)


def test_the_reason_keeps_two_line_breaks_at_most_and_is_cut_in_a_message():
    assert rules.clean_comment("a\r\n\r\n\r\n\r\nb") == "a\n\nb"
    text = rules.owner_notice_text("notice_comment", "pl", comment="x" * 400)
    assert len(text) < 220


def test_the_words_of_the_client_in_a_message_are_one_short_line():
    text = rules.owner_notice_text("notice_estimate", "pl", client="Jan\n\tKowalski " + "x" * 400, project="Dom", version="1", amount="1,00", currency="PLN")
    assert "\n" not in text and "\t" not in text and len(text) < 400
    assert rules.project_open_url("", "p1") is None and rules.project_open_url("https://a.pl", "p1") == "https://a.pl?open=project:p1"


# --- the client may decline the estimate and give a reason (V2-8b) ---------------------------------------------------------------------------


def decline_body(page: dict, name="Jan Kowalski", comment="Za drogo, proszę usunąć łazienkę") -> dict:
    return {**accept_body(page, name), "decision": "DECLINE", "comment": comment}


async def test_the_client_declines_the_estimate_with_a_reason_and_the_owner_reads_both(async_client, db_session, web, sender):
    world = await make_world(async_client, db_session)
    await with_telegram(db_session, language_code="pl")
    token = await issue(async_client, world)
    page = (await open_page(async_client, token)).json()
    est = page["estimate"]
    assert "nie zatwierdzam" in est["decline_statement"]["pl"] and "3489,66" in est["decline_statement"]["pl"]
    response = await async_client.post(f"{PUBLIC}/estimate/decide", json=decline_body(page), headers=door(token))
    assert response.status_code == 200, response.text
    after = response.json()["estimate"]
    assert after["status"] == "FINAL" and after["accept_statement"] is None and after["decline_statement"] is None
    assert after["consent"]["kind"] == "ESTIMATE_DECLINED" and after["consent"]["comment"] == "Za drogo, proszę usunąć łazienkę"
    estimate = (await db_session.execute(select(Estimate).execution_options(populate_existing=True))).scalar_one()
    assert estimate.status == EstimateStatus.FINAL  # a refusal changes nothing in the estimate itself
    row = (await db_session.execute(select(ClientConsent))).scalar_one()
    assert row.kind == "ESTIMATE_DECLINED" and row.statement == est["decline_statement"]["pl"] and row.subject_hash == est["hash"] and row.amount == Decimal("3489.66")
    journal = (await async_client.get(world["base"] + "/client-journal", headers=world["headers"])).json()["items"]
    assert journal[0]["kind"] == "ESTIMATE_DECLINED" and journal[0]["comment"] == "Za drogo, proszę usunąć łazienkę"
    text_ = sender.calls[0][1]
    assert text_.startswith("❌ Klient Jan Kowalski nie zatwierdził wyceny nr 1") and "\nPowód: „Za drogo, proszę usunąć łazienkę”" in text_


async def test_a_refusal_without_a_reason_is_fine_and_a_blank_reason_is_no_reason(async_client, db_session, web):
    world = await make_world(async_client, db_session)
    token = await issue(async_client, world)
    page = (await open_page(async_client, token)).json()
    body = {k: v for k, v in decline_body(page).items() if k != "comment"}
    assert (await async_client.post(f"{PUBLIC}/estimate/decide", json=body, headers=door(token))).status_code == 200
    assert (await db_session.execute(select(ClientConsent.comment))).scalar_one() is None
    world2 = await make_world(async_client, db_session, email="ewa@example.pl")
    token2 = await issue(async_client, world2)
    page2 = (await open_page(async_client, token2)).json()
    assert (await async_client.post(f"{PUBLIC}/estimate/decide", json=decline_body(page2, comment="  \n "), headers=door(token2))).status_code == 200
    assert sorted((await db_session.execute(select(ClientConsent.comment))).scalars().all(), key=str) == [None, None]


async def test_a_reason_goes_only_with_a_refusal_and_is_short(async_client, db_session, web):
    world = await make_world(async_client, db_session)
    token = await issue(async_client, world)
    page = (await open_page(async_client, token)).json()
    post = lambda body: async_client.post(f"{PUBLIC}/estimate/decide", json=body, headers=door(token))  # noqa: E731
    with_accept = await post({**accept_body(page), "comment": "ale proszę o rabat"})
    assert with_accept.status_code == 422 and with_accept.json()["detail"]["code"] == "COMMENT_ONLY_ON_DECLINE"
    long = await post(decline_body(page, comment="x" * 501))
    assert long.status_code == 422 and long.json()["detail"]["code"] == "COMMENT_TOO_LONG"
    assert (await post(decline_body(page, comment="x" * 2001))).status_code == 422
    assert (await post({**decline_body(page), "decision": "MAYBE"})).status_code == 422
    assert (await post({k: v for k, v in decline_body(page).items() if k != "decision"})).status_code == 422
    assert (await post(decline_body(page, comment="x" * 500))).status_code == 200
    assert (await db_session.execute(select(ClientConsent.comment))).scalar_one() == "x" * 500


async def test_a_declined_version_is_final_and_a_new_version_waits_for_a_new_decision(async_client, db_session, web):
    world = await make_world(async_client, db_session)
    token = await issue(async_client, world)
    page = (await open_page(async_client, token)).json()
    assert (await async_client.post(f"{PUBLIC}/estimate/decide", json=decline_body(page), headers=door(token))).status_code == 200
    again = await approve(async_client, token, page)
    assert again.status_code == 409 and again.json()["detail"]["code"] == "ALREADY_DECIDED"
    regenerated = await async_client.post(f"{world['base']}/estimates/generate", headers=world["headers"])
    new_id = regenerated.json()["id"]
    assert (await async_client.post(f"{world['base']}/estimates/{new_id}/finalize", headers=world["headers"])).status_code == 200
    fresh = (await open_page(async_client, token)).json()
    assert fresh["estimate"]["version"] == 2 and fresh["estimate"]["consent"] is None and fresh["estimate"]["decline_statement"] is not None
    assert (await approve(async_client, token, fresh)).status_code == 200
    assert (await db_session.execute(select(ClientConsent.kind).order_by(ClientConsent.created_at))).scalars().all() == ["ESTIMATE_DECLINED", "ESTIMATE_ACCEPTED"]


async def test_an_estimate_approved_in_a_contract_cannot_be_declined_by_the_client(async_client, db_session, web):
    world = await make_world(async_client, db_session)
    token = await issue(async_client, world)
    page = (await open_page(async_client, token)).json()
    await db_session.execute(update(Estimate).values(status=EstimateStatus.ACCEPTED))
    await db_session.commit()
    refused = await async_client.post(f"{PUBLIC}/estimate/decide", json=decline_body(page), headers=door(token))
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "ESTIMATE_ALREADY_APPROVED"
    assert (await db_session.execute(select(ClientConsent))).first() is None


async def test_a_proposal_is_declined_with_a_reason_and_an_approval_takes_none(async_client, db_session, web, sender):
    world = await make_world(async_client, db_session)
    await with_telegram(db_session, language_code="en")
    token = await issue(async_client, world)
    await propose(async_client, world, title="Druga warstwa")
    item = (await open_page(async_client, token)).json()["proposals"][0]
    url = f"{PUBLIC}/proposals/{item['id']}/decide"
    body = {"decision": "ACCEPT", "hash": item["hash"], "signer_name": "Jan Kowalski", "agree": True, "comment": "tak, ale taniej"}
    bad = await async_client.post(url, json=body, headers=door(token))
    assert bad.status_code == 422 and bad.json()["detail"]["code"] == "COMMENT_ONLY_ON_DECLINE"
    assert (await async_client.post(url, json={**body, "decision": "DECLINE", "comment": "x" * 501}, headers=door(token))).json()["detail"]["code"] == "COMMENT_TOO_LONG"
    ok = await async_client.post(url, json={**body, "decision": "DECLINE", "comment": "too expensive"}, headers=door(token))
    assert ok.status_code == 200 and ok.json()["proposals"][0]["consent"]["comment"] == "too expensive"
    assert sender.calls[0][1].endswith("\nReason: “too expensive”")
    journal = (await async_client.get(world["base"] + "/client-journal", headers=world["headers"])).json()["items"]
    assert journal[0]["kind"] == "PROPOSAL_DECLINED" and journal[0]["comment"] == "too expensive"


async def test_only_a_refusal_may_carry_a_reason_in_the_database_too(async_client, db_session, web):
    world = await make_world(async_client, db_session)
    token = await issue(async_client, world)
    page = (await open_page(async_client, token)).json()
    await approve(async_client, token, page)
    row = (await db_session.execute(select(ClientConsent))).scalar_one()
    db_session.add(
        ClientConsent(
            owner_id=row.owner_id, project_id=row.project_id, link_id=row.link_id, kind="ESTIMATE_ACCEPTED", estimate_id=uuid.uuid4(), subject_hash="h" * 64,
            amount=Decimal("1"), currency="PLN", statement="x", signer_name="Jan", comment="a reason with an approval", ip_hash="i" * 64, agent_hash="a" * 64,
        )
    )
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_with_the_encryption_on_the_reason_is_ciphertext_too(async_client, db_session, web, encryption_on):
    world = await make_world(async_client, db_session)
    token = await issue(async_client, world)
    page = (await open_page(async_client, token)).json()
    await async_client.post(f"{PUBLIC}/estimate/decide", json=decline_body(page, comment="Sekretny powód"), headers=door(token))
    raw = (await db_session.execute(text("select comment from client_consents"))).scalar_one()
    assert raw.startswith("enc1:") and "Sekretny" not in raw
    journal = (await async_client.get(world["base"] + "/client-journal", headers=world["headers"])).json()["items"]
    assert journal[0]["comment"] == "Sekretny powód"
