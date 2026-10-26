"""V2-14 -- the link for the electrician and the plumber (docs/V2_14_PLAN_RU.md): the rules of the checklist, the owner's side, the open page, the journal, the migration."""
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_message_sender
from app.api.v1.endpoints import trade_portal
from app.domain import client_link as links
from app.domain import trade_link as texts
from app.domain.rules import trade_checklist as rules
from app.main import app
from app.models.room import Room
from app.models.trade_link import TradeAnswer, TradeLink, TradeSubmission
from app.models.user import User
from tests.test_clients import OTHER_USER
from tests.test_stage15f2_api import login
from tests.test_stage16c_tech_card import world
from tests.test_stage16e2_contract import (
    OWNER_TG,
    STRANGER_TG,
    contract_engine,
    load_migration,
    run,
)
from tests.test_v2_8_client_link import FakeSender

PUBLIC = "/api/public/trade"


@pytest.fixture(autouse=True)
def _fresh_limits():
    trade_portal.reset_limits()
    yield
    trade_portal.reset_limits()


@pytest.fixture
def sender():
    fake = FakeSender()
    app.dependency_overrides[get_message_sender] = lambda: fake
    yield fake
    app.dependency_overrides.pop(get_message_sender, None)


# --- the rules --------------------------------------------------------------------------------------------------------------------


def test_each_trade_has_its_own_typical_positions_in_the_order_of_a_walk_through_a_room():
    assert [(p.key, p.unit) for p in rules.positions_of("ELECTRIC")] == [("SOCKET", "PCS"), ("SWITCH", "PCS"), ("LIGHT_POINT", "PCS"), ("CIRCUIT", "PCS"), ("CABLE_ROUTE", "LM")]
    assert [(p.key, p.unit) for p in rules.positions_of("PLUMBING")] == [("WATER_POINT", "PCS"), ("DRAIN_POINT", "PCS"), ("MANIFOLD_OUT", "PCS"), ("PIPE_ROUTE", "LM")]
    with pytest.raises(rules.TradeChecklistError) as unknown:
        rules.positions_of("TILE")
    assert unknown.value.code == "UNKNOWN_TRADE"
    assert rules.clean_trade("ELECTRIC") == "ELECTRIC"
    with pytest.raises(rules.TradeChecklistError):
        rules.clean_trade("DRYWALL")


@pytest.mark.parametrize("unit,value,expected", [
    ("PCS", "4", Decimal("4.00")), ("PCS", 0, Decimal("0.00")), ("PCS", " 12 ", Decimal("12.00")), ("LM", "12,5", Decimal("12.50")), ("LM", "7.25", Decimal("7.25")),
    ("LM", 3, Decimal("3.00")), ("PCS", None, None), ("PCS", "", None), ("LM", "   ", None),
])
def test_a_quantity_is_read_with_a_comma_whole_for_pieces_and_blank_is_not_an_answer(unit, value, expected):
    assert rules.clean_quantity(unit, value) == expected


@pytest.mark.parametrize("unit,value,code", [
    ("PCS", "2,5", "QUANTITY_NOT_WHOLE"), ("PCS", "-1", "QUANTITY_INVALID"), ("PCS", "abc", "QUANTITY_INVALID"), ("PCS", "501", "QUANTITY_TOO_BIG"),
    ("LM", "5001", "QUANTITY_TOO_BIG"), ("LM", "1,234", "QUANTITY_TOO_PRECISE"), ("LM", "NaN", "QUANTITY_INVALID"), ("LM", "Infinity", "QUANTITY_INVALID"), ("PCS", True, "QUANTITY_INVALID"),
])
def test_a_wrong_quantity_is_refused_with_its_reason(unit, value, code):
    with pytest.raises(rules.TradeChecklistError) as refused:
        rules.clean_quantity(unit, value)
    assert refused.value.code == code and refused.value.field == "quantity"


def test_what_a_craftsman_writes_for_a_room_is_cleaned_and_an_empty_row_is_dropped():
    typical, own = rules.clean_room_answers(
        "ELECTRIC",
        [{"key": "SOCKET", "quantity": "6", "note": "  przy  oknie\n"}, {"key": "SWITCH"}, {"key": "CABLE_ROUTE", "note": "pod sufitem"}],
        [{"name": "  Gniazdo   400V ", "quantity": "1", "unit": "PCS", "note": ""}],
    )
    assert [(t.key, t.unit, t.quantity, t.note) for t in typical] == [("SOCKET", "PCS", Decimal("6.00"), "przy oknie"), ("CABLE_ROUTE", "LM", None, "pod sufitem")]
    assert [(o.name, o.unit, o.quantity, o.note) for o in own] == [("Gniazdo 400V", "PCS", Decimal("1.00"), None)]


def test_a_position_of_the_other_trade_twice_a_nameless_or_unquantified_own_position_and_too_many_are_refused():
    def refused(typical=None, own=None, trade="ELECTRIC"):
        with pytest.raises(rules.TradeChecklistError) as err:
            rules.clean_room_answers(trade, typical, own)
        return err.value.code

    assert refused([{"key": "WATER_POINT", "quantity": 1}]) == "UNKNOWN_POSITION"
    assert refused([{"key": "SOCKET", "quantity": 1}, {"key": "SOCKET", "quantity": 2}]) == "DUPLICATE_POSITION"
    assert refused(own=[{"name": " ", "quantity": 1, "unit": "PCS"}]) == "NAME_REQUIRED"
    assert refused(own=[{"name": "x" * 81, "quantity": 1, "unit": "PCS"}]) == "NAME_TOO_LONG"
    assert refused(own=[{"name": "x", "unit": "PCS"}]) == "QUANTITY_REQUIRED"
    assert refused(own=[{"name": "x", "quantity": 1, "unit": "KG"}]) == "UNIT_INVALID"
    assert refused(own=[{"name": f"p{i}", "quantity": 1, "unit": "PCS"} for i in range(31)]) == "TOO_MANY_OWN"
    assert refused([{"key": "SOCKET", "quantity": 1, "note": "n" * 201}]) == "NOTE_TOO_LONG"
    assert refused(trade="PLUMBING", typical=[{"key": "SOCKET", "quantity": 1}]) == "UNKNOWN_POSITION"


def test_the_word_of_the_owner_keeps_its_lines_and_is_bounded():
    assert rules.clean_owner_note("  Pion C\r\n\r\n\r\n\r\nBez bruzd  ") == "Pion C\n\nBez bruzd"
    assert rules.clean_owner_note("   ") is None and rules.clean_owner_note(None) is None
    with pytest.raises(rules.TradeChecklistError):
        rules.clean_owner_note("x" * 1001)


def test_the_hash_of_what_was_sent_is_independent_of_the_order_and_changes_with_any_word():
    a = [("r1", "SOCKET", "PCS", "4.00", ""), ("r1", "SWITCH", "PCS", "2.00", "n")]
    assert rules.answers_hash(a) == rules.answers_hash(list(reversed(a)))
    assert rules.answers_hash(a) != rules.answers_hash([("r1", "SOCKET", "PCS", "5.00", ""), a[1]])
    assert rules.answers_hash(a) != rules.answers_hash([a[0], ("r1", "SWITCH", "PCS", "2.00", "m")])


def test_the_texts_of_the_message_have_four_languages_and_the_words_of_the_craftsman_are_one_line():
    for lang in ("pl", "ru", "uk", "en"):
        line = texts.notice_text(lang, trade=texts.trade_name("PLUMBING", lang), master="Jan\nKowalski", project="Dom", count=7)
        assert "\n" not in line and "Jan Kowalski" in line and "7" in line
    assert texts.trade_name("ELECTRIC", "xx") == "elektryk"  # an unknown language reads as Polish


# --- the owner's side -------------------------------------------------------------------------------------------------------------


async def owner_world(async_client, db):
    w = await world(db, telegram_id=OWNER_TG)
    w.headers = await login(async_client)
    w.base = f"/api/projects/{w.project.id}/trade-links"
    return w


async def make(async_client, w, trade="ELECTRIC", **body):
    made = await async_client.post(f"{w.base}/{trade}", json=body, headers=w.headers)
    assert made.status_code == 201, made.text
    return made.json()


async def test_the_routes_need_a_token_and_a_stranger_finds_nothing(async_client: AsyncClient, db_session):
    w = await owner_world(async_client, db_session)
    assert (await async_client.get(w.base)).status_code == 401
    assert (await async_client.post(w.base + "/ELECTRIC", json={})).status_code == 401
    other = await login(async_client, OTHER_USER)
    assert (await async_client.get(w.base, headers=other)).status_code == 404
    assert (await async_client.post(w.base + "/ELECTRIC", json={}, headers=other)).status_code == 404
    assert (await async_client.get(w.base + "/ELECTRIC/answers", headers=other)).status_code == 404
    assert (await async_client.delete(w.base + "/ELECTRIC", headers=other)).status_code == 404


async def test_there_is_no_link_until_one_is_made_and_the_secret_is_shown_once(async_client, db_session):
    w = await owner_world(async_client, db_session)
    assert (await async_client.get(w.base, headers=w.headers)).json() == {"electric": None, "plumbing": None}
    made = await make(async_client, w, "ELECTRIC", language="uk", note="  Pion C, bez bruzd ")
    assert links.looks_like_token(made["token"])
    link = made["link"]
    assert (link["trade"], link["language"], link["owner_note"], link["view_count"], link["expired"], link["answers_count"], link["submissions_count"]) == (
        "ELECTRIC", "uk", "Pion C, bez bruzd", 0, False, 0, 0)
    status = (await async_client.get(w.base, headers=w.headers)).json()
    assert status["electric"]["trade"] == "ELECTRIC" and status["plumbing"] is None
    assert "token" not in str(status)  # the secret is never read back
    row = (await db_session.execute(select(TradeLink))).scalar_one()
    assert row.token_hash == links.hash_token(made["token"]) and made["token"] not in str(row.__dict__)


async def test_the_two_trades_have_their_own_links_and_a_new_one_stops_the_old_one_of_the_same_trade(async_client, db_session):
    w = await owner_world(async_client, db_session)
    first = await make(async_client, w, "ELECTRIC")
    plumber = await make(async_client, w, "PLUMBING", language="ru")
    second = await make(async_client, w, "ELECTRIC", language="en")
    assert (await async_client.get(PUBLIC, headers={"X-Trade-Link": first["token"]})).status_code == 410
    assert (await async_client.get(PUBLIC, headers={"X-Trade-Link": plumber["token"]})).status_code == 200
    assert (await async_client.get(PUBLIC, headers={"X-Trade-Link": second["token"]})).status_code == 200
    unrevoked = (await db_session.execute(select(TradeLink.trade).where(TradeLink.revoked_at.is_(None)))).scalars().all()
    assert sorted(unrevoked) == ["ELECTRIC", "PLUMBING"]


async def test_an_unknown_trade_is_refused_and_the_words_are_bounded(async_client, db_session):
    w = await owner_world(async_client, db_session)
    for trade in ("TILE", "electric", "x"):
        response = await async_client.post(f"{w.base}/{trade}", json={}, headers=w.headers)
        assert response.status_code == 422 and response.json()["detail"]["code"] == "UNKNOWN_TRADE"
    assert (await async_client.post(w.base + "/ELECTRIC", json={"note": "x" * 1001}, headers=w.headers)).status_code in (422,)
    assert (await async_client.post(w.base + "/ELECTRIC", json={"who": 1}, headers=w.headers)).status_code == 422
    assert (await db_session.execute(select(TradeLink))).scalars().all() == []


async def test_the_term_is_thirty_days_it_can_be_extended_and_revoked_and_the_word_changed(async_client, db_session):
    w = await owner_world(async_client, db_session)
    made = await make(async_client, w, "PLUMBING")
    token = made["token"]
    expires = datetime.fromisoformat(made["link"]["expires_at"])
    assert timedelta(days=29, hours=23) < expires - datetime.now(UTC).replace(tzinfo=expires.tzinfo) < timedelta(days=30, minutes=1)
    await db_session.execute(update(TradeLink).values(expires_at=datetime.now(UTC) - timedelta(days=1)))
    await db_session.commit()
    assert (await async_client.get(PUBLIC, headers={"X-Trade-Link": token})).status_code == 410
    assert (await async_client.get(w.base, headers=w.headers)).json()["plumbing"]["expired"] is True
    extended = await async_client.post(w.base + "/PLUMBING/extend", headers=w.headers)
    assert extended.status_code == 200 and extended.json()["expired"] is False
    assert (await async_client.get(PUBLIC, headers={"X-Trade-Link": token})).status_code == 200
    changed = await async_client.patch(w.base + "/PLUMBING", json={"note": "Kolektor w łazience"}, headers=w.headers)
    assert changed.status_code == 200 and changed.json()["owner_note"] == "Kolektor w łazience"
    assert (await async_client.get(PUBLIC, headers={"X-Trade-Link": token})).json()["owner_note"] == "Kolektor w łazience"
    assert (await async_client.delete(w.base + "/PLUMBING", headers=w.headers)).status_code == 204
    assert (await async_client.get(PUBLIC, headers={"X-Trade-Link": token})).status_code == 410
    assert (await async_client.post(w.base + "/PLUMBING/extend", headers=w.headers)).status_code == 404  # a revoked link does not come back
    assert (await async_client.delete(w.base + "/PLUMBING", headers=w.headers)).status_code == 404
    assert (await async_client.patch(w.base + "/ELECTRIC", json={"note": "x"}, headers=w.headers)).status_code == 404  # no link of that trade


# --- the open page ----------------------------------------------------------------------------------------------------------------


async def page_world(async_client, db, trade="ELECTRIC", **body):
    w = await owner_world(async_client, db)
    await db.execute(update(Room).where(Room.id == w.salon.id).values(length=Decimal("4.00"), width=Decimal("3.50"), height=Decimal("2.60")))
    await db.commit()
    w.token = (await make(async_client, w, trade, **body))["token"]
    w.door = {"X-Trade-Link": w.token}
    return w


async def test_the_page_has_the_rooms_with_their_sizes_the_checklist_and_nothing_private(async_client, db_session):
    w = await page_world(async_client, db_session, note="Pion C")
    response = await async_client.get(PUBLIC, headers=w.door)
    assert response.status_code == 200
    for header, value in (("cache-control", "no-store"), ("x-robots-tag", "noindex, nofollow"), ("referrer-policy", "no-referrer"), ("x-content-type-options", "nosniff")):
        assert response.headers[header] == value
    page = response.json()
    assert set(page) == {"link", "lang", "trade", "contractor", "project_name", "owner_note", "positions", "rooms", "submissions_count", "last_submitted_at"}
    assert (page["trade"], page["project_name"], page["owner_note"], page["lang"]) == ("ELECTRIC", "Mokotów", "Pion C", "pl")
    assert [p["key"] for p in page["positions"]] == ["SOCKET", "SWITCH", "LIGHT_POINT", "CIRCUIT", "CABLE_ROUTE"]
    salon = next(r for r in page["rooms"] if r["name"] == "Salon")
    assert set(salon) == {"id", "name", "length", "width", "height", "floor_area", "perimeter", "typical", "own"}
    assert (Decimal(salon["length"]), Decimal(salon["floor_area"]), Decimal(salon["perimeter"])) == (Decimal(4), Decimal(14), Decimal(15))
    assert salon["typical"] == [] and salon["own"] == []
    dump = response.text
    for private in ("Anna", "Nowak", "Dobra", "Warszawa", "00-001", "price", "amount", "client"):  # the client, the address, any money
        assert private not in dump


async def test_the_page_counts_the_views_and_follows_the_language_of_the_link_or_of_the_visitor(async_client, db_session):
    w = await page_world(async_client, db_session, language="ru")
    assert (await async_client.get(PUBLIC, headers=w.door)).json()["lang"] == "ru"
    assert (await async_client.get(PUBLIC, headers=w.door, params={"lang": "en"})).json()["lang"] == "en"
    assert (await async_client.get(PUBLIC, headers=w.door, params={"lang": "zz"})).json()["lang"] == "pl"
    status = (await async_client.get(w.base, headers=w.headers)).json()["electric"]
    assert status["view_count"] == 3 and status["last_viewed_at"] is not None


@pytest.mark.parametrize("secret", [None, "", "short", "a" * 43, "a" * 44])
async def test_a_missing_or_unknown_secret_is_the_same_404(async_client, db_session, secret):
    await page_world(async_client, db_session)
    headers = {} if secret is None else {"X-Trade-Link": secret}
    response = await async_client.get(PUBLIC, headers=headers)
    assert response.status_code == 404 and response.json()["detail"]["code"] == "NOT_FOUND" and response.headers["cache-control"] == "no-store"


async def test_the_secret_of_the_client_does_not_open_the_page_of_the_craftsman(async_client, db_session):
    w = await page_world(async_client, db_session)
    client_link = await async_client.post(f"/api/projects/{w.project.id}/client-link", json={}, headers=w.headers)
    assert client_link.status_code == 201
    assert (await async_client.get(PUBLIC, headers={"X-Trade-Link": client_link.json()["token"]})).status_code == 404
    assert (await async_client.get("/api/public/client", headers={"X-Client-Link": w.token})).status_code == 404


def room_body(**extra):
    return {"typical": [{"key": "SOCKET", "quantity": "6", "note": "przy oknie"}, {"key": "CABLE_ROUTE", "quantity": "12,5"}], "own": [{"name": "Gniazdo 400V", "quantity": 1, "unit": "PCS", "note": "piekarnik"}], **extra}


async def test_the_craftsman_writes_a_room_and_the_answers_replace_the_earlier_ones_of_that_room(async_client, db_session):
    w = await page_world(async_client, db_session)
    saved = await async_client.put(f"{PUBLIC}/rooms/{w.salon.id}", json=room_body(), headers=w.door)
    assert saved.status_code == 200, saved.text
    salon = next(r for r in saved.json()["rooms"] if r["name"] == "Salon")
    assert [(t["key"], t["unit"], t["quantity"], t["note"]) for t in salon["typical"]] == [("SOCKET", "PCS", "6.00", "przy oknie"), ("CABLE_ROUTE", "LM", "12.50", None)]
    assert [(o["name"], o["quantity"], o["unit"], o["note"]) for o in salon["own"]] == [("Gniazdo 400V", "1.00", "PCS", "piekarnik")]
    again = await async_client.put(f"{PUBLIC}/rooms/{w.salon.id}", json={"typical": [{"key": "SWITCH", "quantity": 3}], "own": []}, headers=w.door)
    salon = next(r for r in again.json()["rooms"] if r["name"] == "Salon")
    assert [t["key"] for t in salon["typical"]] == ["SWITCH"] and salon["own"] == []
    kitchen = next(r for r in again.json()["rooms"] if r["name"] == "Kuchnia")
    assert kitchen["typical"] == []
    assert len((await db_session.execute(select(TradeAnswer))).scalars().all()) == 1
    cleared = await async_client.put(f"{PUBLIC}/rooms/{w.salon.id}", json={"typical": [], "own": []}, headers=w.door)
    assert cleared.status_code == 200 and (await db_session.execute(select(TradeAnswer))).scalars().all() == []


async def test_what_the_craftsman_wrote_is_kept_encrypted_words_and_plain_numbers(async_client, db_session):
    w = await page_world(async_client, db_session)
    await async_client.put(f"{PUBLIC}/rooms/{w.salon.id}", json=room_body(), headers=w.door)
    from app.domain.services.data_reencode_service import encrypted_columns

    assert {c.column for c in encrypted_columns() if c.table.startswith("trade_")} == {"owner_note", "custom_name", "note", "master_name"}
    raw = (await db_session.execute(text("SELECT position_key, quantity, unit FROM trade_answers ORDER BY position_key NULLS LAST"))).all()
    assert [(r[0], str(Decimal(str(r[1])).quantize(Decimal("0.01"))), r[2]) for r in raw] == [("CABLE_ROUTE", "12.50", "LM"), ("SOCKET", "6.00", "PCS"), (None, "1.00", "PCS")]


@pytest.mark.parametrize("body,code", [
    ({"typical": [{"key": "WATER_POINT", "quantity": 1}], "own": []}, "UNKNOWN_POSITION"),
    ({"typical": [{"key": "SOCKET", "quantity": "2,5"}], "own": []}, "QUANTITY_NOT_WHOLE"),
    ({"typical": [{"key": "SOCKET", "quantity": 1}, {"key": "SOCKET", "quantity": 2}], "own": []}, "DUPLICATE_POSITION"),
    ({"typical": [], "own": [{"name": "x", "unit": "PCS"}]}, "QUANTITY_REQUIRED"),
    ({"typical": [], "own": [{"name": "", "quantity": 1, "unit": "PCS"}]}, "NAME_REQUIRED"),
])
async def test_a_wrong_entry_is_refused_with_its_reason_and_changes_nothing(async_client, db_session, body, code):
    w = await page_world(async_client, db_session)
    await async_client.put(f"{PUBLIC}/rooms/{w.salon.id}", json={"typical": [{"key": "SWITCH", "quantity": 2}], "own": []}, headers=w.door)
    refused = await async_client.put(f"{PUBLIC}/rooms/{w.salon.id}", json=body, headers=w.door)
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == code
    kept = (await db_session.execute(select(TradeAnswer.position_key))).scalars().all()
    assert kept == ["SWITCH"]


async def test_unknown_fields_and_oversized_bodies_are_refused_before_the_rules(async_client, db_session):
    w = await page_world(async_client, db_session)
    put = lambda body: async_client.put(f"{PUBLIC}/rooms/{w.salon.id}", json=body, headers=w.door)
    assert (await put({"typical": [], "own": [], "extra": 1})).status_code == 422
    assert (await put({"typical": [{"key": "SOCKET", "quantity": 1, "price": 5}], "own": []})).status_code == 422
    assert (await put({"typical": [], "own": [{"name": "x", "quantity": 1, "unit": "PCS"}] * 61})).status_code == 422
    assert (await put({"typical": [{"key": "SOCKET", "quantity": 1, "note": "n" * 401}], "own": []})).status_code == 422


async def test_a_room_of_another_object_an_archived_one_or_a_stranger_id_is_not_found(async_client, db_session):
    w = await page_world(async_client, db_session)
    foreign = await world(db_session, telegram_id=STRANGER_TG)
    for room_id in (foreign.salon.id, uuid.uuid4()):
        response = await async_client.put(f"{PUBLIC}/rooms/{room_id}", json={"typical": [{"key": "SOCKET", "quantity": 1}], "own": []}, headers=w.door)
        assert response.status_code == 404
    await db_session.execute(update(Room).where(Room.id == w.kuchnia.id).values(is_archived=True))
    await db_session.commit()
    archived = await async_client.put(f"{PUBLIC}/rooms/{w.kuchnia.id}", json={"typical": [{"key": "SOCKET", "quantity": 1}], "own": []}, headers=w.door)
    assert archived.status_code == 404
    assert (await db_session.execute(select(TradeAnswer))).scalars().all() == []
    assert all(r["name"] != "Kuchnia" for r in (await async_client.get(PUBLIC, headers=w.door)).json()["rooms"])


async def test_the_two_trades_never_see_each_others_answers_and_a_renewed_link_keeps_them(async_client, db_session):
    w = await page_world(async_client, db_session, "ELECTRIC")
    plumber = {"X-Trade-Link": (await make(async_client, w, "PLUMBING"))["token"]}
    await async_client.put(f"{PUBLIC}/rooms/{w.salon.id}", json=room_body(), headers=w.door)
    await async_client.put(f"{PUBLIC}/rooms/{w.salon.id}", json={"typical": [{"key": "WATER_POINT", "quantity": 2}], "own": []}, headers=plumber)
    electric_page = (await async_client.get(PUBLIC, headers=w.door)).json()
    plumbing_page = (await async_client.get(PUBLIC, headers=plumber)).json()
    assert [t["key"] for t in next(r for r in electric_page["rooms"] if r["name"] == "Salon")["typical"]] == ["SOCKET", "CABLE_ROUTE"]
    assert [t["key"] for t in next(r for r in plumbing_page["rooms"] if r["name"] == "Salon")["typical"]] == ["WATER_POINT"]
    assert (await async_client.put(f"{PUBLIC}/rooms/{w.salon.id}", json={"typical": [{"key": "WATER_POINT", "quantity": 1}], "own": []}, headers=w.door)).status_code == 422
    renewed = {"X-Trade-Link": (await make(async_client, w, "ELECTRIC"))["token"]}
    again = (await async_client.get(PUBLIC, headers=renewed)).json()
    assert [t["key"] for t in next(r for r in again["rooms"] if r["name"] == "Salon")["typical"]] == ["SOCKET", "CABLE_ROUTE"]


async def test_the_owner_reads_the_answers_by_room_and_the_journal(async_client, db_session, sender):
    w = await page_world(async_client, db_session)
    await async_client.put(f"{PUBLIC}/rooms/{w.salon.id}", json=room_body(), headers=w.door)
    await async_client.post(f"{PUBLIC}/submit", json={"master_name": "Jan Elektryk"}, headers=w.door)
    read = (await async_client.get(w.base + "/ELECTRIC/answers", headers=w.headers)).json()
    assert [p["key"] for p in read["positions"]] == ["SOCKET", "SWITCH", "LIGHT_POINT", "CIRCUIT", "CABLE_ROUTE"]
    salon = next(r for r in read["rooms"] if r["room_name"] == "Salon")
    assert [t["key"] for t in salon["typical"]] == ["SOCKET", "CABLE_ROUTE"] and salon["own"][0]["name"] == "Gniazdo 400V" and salon["updated_at"] is not None
    assert [(s["master_name"], s["answers_count"]) for s in read["submissions"]] == [("Jan Elektryk", 3)]
    status = (await async_client.get(w.base, headers=w.headers)).json()["electric"]
    assert (status["answers_count"], status["submissions_count"]) == (3, 1) and status["last_submitted_at"] is not None
    plumbing = (await async_client.get(w.base + "/PLUMBING/answers", headers=w.headers)).json()
    assert plumbing["submissions"] == [] and all(r["typical"] == [] and r["own"] == [] for r in plumbing["rooms"])


# --- what is sent -----------------------------------------------------------------------------------------------------------------


async def with_telegram(db, chat_id=777002, language_code="ru"):
    await db.execute(update(User).values(telegram_user_id=chat_id, language_code=language_code))
    await db.commit()


async def test_sending_needs_something_written_and_a_name_and_writes_one_row_of_the_journal(async_client, db_session, sender):
    w = await page_world(async_client, db_session)
    empty = await async_client.post(f"{PUBLIC}/submit", json={"master_name": "Jan"}, headers=w.door)
    assert empty.status_code == 422 and empty.json()["detail"]["code"] == "NOTHING_TO_SEND"
    await async_client.put(f"{PUBLIC}/rooms/{w.salon.id}", json=room_body(), headers=w.door)
    for name, code in ((" ", "NAME_REQUIRED"), ("J", "NAME_REQUIRED"), ("x" * 81, "NAME_TOO_LONG")):
        refused = await async_client.post(f"{PUBLIC}/submit", json={"master_name": name}, headers=w.door)
        assert refused.status_code == 422 and refused.json()["detail"]["code"] == code
    assert (await async_client.post(f"{PUBLIC}/submit", json={"master_name": "Jan", "x": 1}, headers=w.door)).status_code == 422
    assert (await db_session.execute(select(TradeSubmission))).scalars().all() == []
    done = await async_client.post(f"{PUBLIC}/submit", json={"master_name": "  Jan   Elektryk "}, headers={**w.door, "CF-Connecting-IP": "198.51.100.7", "User-Agent": "Phone/1"})
    assert done.status_code == 200 and done.json()["submissions_count"] == 1 and done.json()["last_submitted_at"] is not None
    row = (await db_session.execute(select(TradeSubmission))).scalar_one()
    assert (row.master_name, row.trade, row.answers_count) == ("Jan Elektryk", "ELECTRIC", 3)
    assert len(row.answers_hash) == 64 and "198.51.100.7" not in (row.ip_hash + row.agent_hash) and len(row.ip_hash) == 64


async def test_a_second_sending_after_a_correction_is_a_second_row_with_another_hash(async_client, db_session, sender):
    w = await page_world(async_client, db_session)
    await async_client.put(f"{PUBLIC}/rooms/{w.salon.id}", json=room_body(), headers=w.door)
    await async_client.post(f"{PUBLIC}/submit", json={"master_name": "Jan"}, headers=w.door)
    await async_client.put(f"{PUBLIC}/rooms/{w.salon.id}", json=room_body(typical=[{"key": "SOCKET", "quantity": 8}]), headers=w.door)
    await async_client.post(f"{PUBLIC}/submit", json={"master_name": "Jan"}, headers=w.door)
    rows = (await db_session.execute(select(TradeSubmission).order_by(TradeSubmission.created_at))).scalars().all()
    assert len(rows) == 2 and rows[0].answers_hash != rows[1].answers_hash and (rows[0].answers_count, rows[1].answers_count) == (3, 2)


async def test_the_owner_is_told_in_telegram_in_the_language_of_the_messages_with_a_button_that_opens_the_object(async_client, db_session, sender, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "CALENDAR_WEB_APP_URL", "https://plan-estimate.pl")
    w = await page_world(async_client, db_session)
    await with_telegram(db_session)
    await async_client.put(f"{PUBLIC}/rooms/{w.salon.id}", json=room_body(), headers=w.door)
    await async_client.post(f"{PUBLIC}/submit", json={"master_name": "Jan Elektryk"}, headers=w.door)
    assert len(sender.calls) == 1
    chat, text_, url, button = sender.calls[0]
    assert chat == 777002 and url == f"https://plan-estimate.pl?open=project:{w.project.id}"
    assert text_ == "Ответ мастера (электрик): Jan Elektryk отправил(а) ответ по объекту «Mokotów» — позиций: 3." and "\n" not in text_
    assert button == "Открыть объект"
    saved = await async_client.put("/api/calendar/settings", json={"timezone": "Europe/Warsaw", "language": "en"}, headers=w.headers)
    assert saved.status_code == 200, saved.text
    await async_client.post(f"{PUBLIC}/submit", json={"master_name": "Jan"}, headers=w.door)
    assert sender.calls[1][1].startswith("Craftsman's answer (electrician): Jan sent an answer") and sender.calls[1][3] == "Open the property"


@pytest.mark.parametrize("failure", [None, "disabled", "chat"])
async def test_a_message_that_does_not_go_never_costs_the_craftsman_his_submission(async_client, db_session, failure, caplog):
    from app.domain.exceptions import (
        MessageChatUnavailableError,
        MessageDeliveryDisabledError,
    )

    fake = FakeSender({"disabled": MessageDeliveryDisabledError("off"), "chat": MessageChatUnavailableError("gone")}.get(failure)) if failure else FakeSender()
    app.dependency_overrides[get_message_sender] = lambda: fake
    try:
        w = await page_world(async_client, db_session)
        await with_telegram(db_session)
        await async_client.put(f"{PUBLIC}/rooms/{w.salon.id}", json=room_body(), headers=w.door)
        with caplog.at_level("INFO"):
            done = await async_client.post(f"{PUBLIC}/submit", json={"master_name": "Jan Elektryk"}, headers=w.door)
        assert done.status_code == 200 and len(fake.calls) == 1
        assert len((await db_session.execute(select(TradeSubmission))).scalars().all()) == 1
        logged = " ".join(r.getMessage() for r in caplog.records)
        assert "Jan Elektryk" not in logged and "777002" not in logged  # no name of the craftsman, no chat in the log
    finally:
        app.dependency_overrides.pop(get_message_sender, None)


async def test_an_owner_with_a_password_and_no_telegram_chat_is_not_messaged_and_nothing_breaks(async_client, db_session, sender):
    w = await page_world(async_client, db_session)
    await with_telegram(db_session, chat_id=-5)
    await async_client.put(f"{PUBLIC}/rooms/{w.salon.id}", json=room_body(), headers=w.door)
    assert (await async_client.post(f"{PUBLIC}/submit", json={"master_name": "Jan"}, headers=w.door)).status_code == 200
    assert sender.calls == []


# --- the door ---------------------------------------------------------------------------------------------------------------------


async def test_too_many_wrong_secrets_from_one_address_close_the_door_for_a_while(async_client, db_session):
    w = await page_world(async_client, db_session)
    heads = {"CF-Connecting-IP": "198.51.100.9"}
    codes = [(await async_client.get(PUBLIC, headers={**heads, "X-Trade-Link": "b" * 43})).status_code for _ in range(22)]
    assert codes[:20] == [404] * 20 and codes[20:] == [429, 429]
    blocked = await async_client.get(PUBLIC, headers={**heads, "X-Trade-Link": w.token})
    assert blocked.status_code == 429 and blocked.json()["detail"]["code"] == "RATE_LIMITED" and int(blocked.headers["retry-after"]) > 0
    assert (await async_client.get(PUBLIC, headers={"CF-Connecting-IP": "198.51.100.10", "X-Trade-Link": w.token})).status_code == 200


def test_exactly_three_open_operations_belong_to_the_craftsman_and_the_journal_has_no_way_to_change_it():
    opened = {
        (method.upper(), path)
        for path, ops in app.openapi()["paths"].items()
        for method, op in ops.items()
        if path.startswith("/api/public/trade") and not op.get("security")
    }
    assert opened == {("GET", PUBLIC), ("PUT", PUBLIC + "/rooms/{room_id}"), ("POST", PUBLIC + "/submit")}
    paths = app.openapi()["paths"]
    assert set(paths["/api/projects/{project_id}/trade-links/{trade}/answers"]) == {"get"}  # the answers and the journal are read, never edited by the owner


# --- the migration ----------------------------------------------------------------------------------------------------------------


def engine_0085():
    engine = contract_engine()  # a stub of the users and the projects: u1 and p1
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE rooms (id CHAR(32) PRIMARY KEY)"))
        conn.execute(text("INSERT INTO rooms (id) VALUES ('r1')"))
    run(engine, "0085_trade_links", "upgrade")
    return engine


def test_revision_chain_and_length():
    module = load_migration("0085_trade_links")
    assert module.revision == "0085_trade_links" and module.down_revision == "0084_user_trades" and len(module.revision) <= 32


def test_the_database_allows_one_active_link_per_trade_one_answer_per_position_and_refuses_the_rest():
    engine = engine_0085()
    now = "2026-11-03 10:00:00"
    link = ("INSERT INTO trade_links (id, owner_id, project_id, trade, token_hash, language, created_at, expires_at, view_count, revoked_at) "
            "VALUES (:id, 'u1', 'p1', :trade, :hash, :lang, :n, :n, 0, :revoked)")
    answer = ("INSERT INTO trade_answers (id, owner_id, project_id, trade, room_id, position_key, custom_name, quantity, unit, note, created_at, updated_at) "
              "VALUES (:id, 'u1', 'p1', :trade, 'r1', :key, :name, :qty, :unit, :note, :n, :n)")
    ok = {"n": now, "revoked": None, "lang": "pl"}
    with engine.begin() as conn:
        conn.execute(text(link), {**ok, "id": "l1", "trade": "ELECTRIC", "hash": "h1"})
        conn.execute(text(link), {**ok, "id": "l2", "trade": "PLUMBING", "hash": "h2"})
        conn.execute(text(link), {**ok, "id": "l3", "trade": "ELECTRIC", "hash": "h3", "revoked": now})  # a revoked one does not count
        conn.execute(text(answer), {"n": now, "id": "a1", "trade": "ELECTRIC", "key": "SOCKET", "name": None, "qty": 4, "unit": "PCS", "note": None})
        conn.execute(text(answer), {"n": now, "id": "a2", "trade": "ELECTRIC", "key": None, "name": "x", "qty": 1, "unit": "PCS", "note": None})
        conn.execute(text(answer), {"n": now, "id": "a3", "trade": "ELECTRIC", "key": None, "name": "y", "qty": 1, "unit": "PCS", "note": None})  # own positions repeat
        conn.execute(text(answer), {"n": now, "id": "a4", "trade": "ELECTRIC", "key": "SWITCH", "name": None, "qty": None, "unit": "PCS", "note": "tylko notatka"})
    bad_links = [
        {**ok, "id": "l4", "trade": "ELECTRIC", "hash": "h4"},  # a second active link of the trade
        {**ok, "id": "l5", "trade": "TILE", "hash": "h5"},
        {**ok, "id": "l6", "trade": "PLUMBING", "hash": "h1"},  # a repeated secret
        {**ok, "id": "l7", "trade": "PLUMBING", "hash": "h7", "lang": "de"},
    ]
    for bad in bad_links:
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(text(link), bad)
    bad_answers = [
        {"id": "b1", "trade": "ELECTRIC", "key": "SOCKET", "name": None, "qty": 5, "unit": "PCS", "note": None},  # the same position twice
        {"id": "b2", "trade": "ELECTRIC", "key": "SOCKET", "name": "x", "qty": 5, "unit": "PCS", "note": None},  # typical and own at once
        {"id": "b3", "trade": "ELECTRIC", "key": None, "name": None, "qty": 5, "unit": "PCS", "note": None},  # neither
        {"id": "b4", "trade": "ELECTRIC", "key": "LIGHT_POINT", "name": None, "qty": -1, "unit": "PCS", "note": None},
        {"id": "b5", "trade": "ELECTRIC", "key": "CIRCUIT", "name": None, "qty": 1, "unit": "KG", "note": None},
        {"id": "b6", "trade": "ELECTRIC", "key": "CIRCUIT", "name": None, "qty": None, "unit": "PCS", "note": None},  # a typical row with nothing in it
        {"id": "b7", "trade": "ELECTRIC", "key": None, "name": "z", "qty": None, "unit": "PCS", "note": "x"},  # an own position with no quantity
        {"id": "b8", "trade": "TILE", "key": "SOCKET", "name": None, "qty": 1, "unit": "PCS", "note": None},
    ]
    for bad in bad_answers:
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(text(answer), {"n": now, **bad})


def test_downgrade_refuses_while_an_answer_or_a_journal_row_exists_and_then_works():
    engine = engine_0085()
    now = "2026-11-03 10:00:00"
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO trade_answers (id, owner_id, project_id, trade, room_id, position_key, quantity, unit, created_at, updated_at) "
                          "VALUES ('a1', 'u1', 'p1', 'ELECTRIC', 'r1', 'SOCKET', 2, 'PCS', :n, :n)"), {"n": now})
    with pytest.raises(RuntimeError, match="1 answer"):
        run(engine, "0085_trade_links", "downgrade")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM trade_answers"))
    run(engine, "0085_trade_links", "downgrade")
    from sqlalchemy import inspect

    assert not {"trade_links", "trade_answers", "trade_submissions"} & set(inspect(engine).get_table_names())
    run(engine, "0085_trade_links", "upgrade")


def test_the_encrypted_columns_are_text_in_the_migration():
    from sqlalchemy import inspect

    engine = engine_0085()
    types = {(t, c["name"]): str(c["type"]).upper() for t in ("trade_links", "trade_answers", "trade_submissions") for c in inspect(engine).get_columns(t)}
    for key in (("trade_links", "owner_note"), ("trade_answers", "custom_name"), ("trade_answers", "note"), ("trade_submissions", "master_name")):
        assert types[key] == "TEXT", key  # the encryption stores `enc1:...` and counts with LIKE: a JSON column breaks both (found on the first production run of V2-12b)


def test_a_deleted_object_takes_its_links_answers_and_journal_with_it():
    engine = engine_0085()
    now = "2026-11-03 10:00:00"
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys=ON"))
        conn.execute(text("INSERT INTO trade_links (id, owner_id, project_id, trade, token_hash, language, created_at, expires_at, view_count) VALUES ('l1', 'u1', 'p1', 'ELECTRIC', 'h', 'pl', :n, :n, 0)"), {"n": now})
        conn.execute(text("INSERT INTO trade_answers (id, owner_id, project_id, trade, room_id, position_key, quantity, unit, created_at, updated_at) "
                          "VALUES ('a1', 'u1', 'p1', 'ELECTRIC', 'r1', 'SOCKET', 2, 'PCS', :n, :n)"), {"n": now})
        conn.execute(text("INSERT INTO trade_submissions (id, owner_id, project_id, link_id, trade, master_name, answers_hash, answers_count, ip_hash, agent_hash, created_at) "
                          "VALUES ('s1', 'u1', 'p1', 'l1', 'ELECTRIC', 'Jan', 'h', 1, 'i', 'a', :n)"), {"n": now})
        conn.execute(text("DELETE FROM projects WHERE id = 'p1'"))
        for table in ("trade_links", "trade_answers", "trade_submissions"):
            assert conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one() == 0, table
