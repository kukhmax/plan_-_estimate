"""Stage 16F.1: the protocol of handing over the premises -- the rules, the draft, the API and the migration."""
import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.domain.contracts.catalog import load_contract_catalog
from app.domain.exceptions import HandoverInvalidError, HandoverNotEditableError, HandoverNotFoundError, ProjectNotFoundError
from app.domain.protocols import handover as H
from app.domain.services.handover_service import HandoverService
from app.models.handover_protocol import HandoverProtocol
from tests.test_stage15f2_api import use_issuer  # noqa: F401  (a fixture)
from tests.test_stage15f2_issuing import Delivery, issuer, user_of
from tests.test_stage16e2_contract import OWNER_TG, STRANGER_TG, contract_engine, load_migration, login, ready, run
from tests.test_stage16e4_signing import issued

CATALOG = load_contract_catalog()
KEYS = [r.key for r in CATALOG.requirements.items]
ROOM = str(uuid.uuid4())
PERSON = str(uuid.uuid4())
PEOPLE = {PERSON: ("Anna Nowak", "Właścicielka")}


def change(current=None, changes=None, rooms=(ROOM,), people=PEOPLE):
    current = current or {"held_on": None, "held_time": None, "attendees": [], "rooms": {}, "meters": None, "notes": None}
    return H.apply_changes(current, changes or {}, room_ids=set(rooms), people=people, catalog=CATALOG)


def all_states(state):
    return {"requirements": {k: {"state": state} for k in KEYS}}


def refused(**kw):
    with pytest.raises(HandoverInvalidError) as exc:
        change(**kw)
    return exc.value.key, exc.value.reason


# --- the rules ---------------------------------------------------------------------------------------------------------------------


def test_the_day_the_time_and_the_texts_are_checked_and_cleared_with_null():
    state = change(changes={"held_on": date(2026, 10, 20), "held_time": "09:30", "meters": " woda 123 ", "notes": "Klucze u administratora."})
    assert (state["held_on"], state["held_time"], state["meters"]) == (date(2026, 10, 20), "09:30", "woda 123")
    assert change(state, {"held_time": None, "notes": None})["held_time"] is None
    assert refused(changes={"held_time": "9:30"}) == ("held_time", H.BAD_TIME)
    assert refused(changes={"held_time": "24:00"}) == ("held_time", H.BAD_TIME)
    assert refused(changes={"held_on": "2026-10-20"}) == ("held_on", H.WRONG_TYPE)
    assert refused(changes={"notes": "x" * 4001}) == ("notes", H.TOO_LONG)
    assert refused(changes={"notes": 5}) == ("notes", H.WRONG_TYPE)
    assert refused(changes={"nonsense": 1})[1] == H.UNKNOWN_REQUIREMENT


def test_a_person_of_the_register_is_copied_by_name_and_an_outsider_is_written_by_hand():
    state = change(changes={"attendees": [{"person_id": PERSON}, {"person_id": PERSON}, {"name": " Jan  Kowalski ", "role": "sąsiad"}]})
    assert state["attendees"] == [
        {"person_id": PERSON, "name": "Anna Nowak", "role": "Właścicielka"}, {"person_id": None, "name": "Jan Kowalski", "role": "sąsiad"}]
    assert refused(changes={"attendees": [{"person_id": str(uuid.uuid4())}]}) == ("attendees", H.UNKNOWN_PERSON)
    assert refused(changes={"attendees": [{"person_id": "x"}]}) == ("attendees", H.WRONG_TYPE)
    assert refused(changes={"attendees": [{"role": "bez imienia"}]}) == ("attendees", H.WRONG_TYPE)
    assert refused(changes={"attendees": [{"name": "A", "extra": 1}]}) == ("attendees", H.WRONG_TYPE)
    assert refused(changes={"attendees": "Anna"}) == ("attendees", H.WRONG_TYPE)
    assert change(state, {"attendees": []})["attendees"] == []


def test_requirements_are_recorded_per_room_with_a_state_a_measured_value_and_a_note():
    changes = {"rooms": {ROOM: {"requirements": {
        "lighting_permanent": {"state": "YES"},
        "lighting_level": {"state": "NO", "value": 120, "note": " za ciemno "},
        "temperature_range": {"state": "CONDITIONAL", "value": {"min": 8, "max": 12}}}, "damages": "Rysa nad oknem", "decision": "CONDITIONAL"}}}
    room = change(changes=changes)["rooms"][ROOM]
    assert room["requirements"]["lighting_level"] == {"state": "NO", "value": 120, "note": "za ciemno"}
    assert room["requirements"]["temperature_range"]["value"] == {"min": 8, "max": 12}
    assert (room["damages"], room["decision"]) == ("Rysa nad oknem", "CONDITIONAL")
    # a later change merges: it keeps the other requirements and only touches the named one
    again = change(change(changes=changes), {"rooms": {ROOM: {"requirements": {"lighting_level": {"state": "YES", "value": 300}}}}})["rooms"][ROOM]
    assert again["requirements"]["lighting_level"] == {"state": "YES", "value": 300, "note": "za ciemno"}
    assert again["requirements"]["lighting_permanent"] == {"state": "YES"} and again["decision"] == "CONDITIONAL"
    only = change(change(changes=changes), {"rooms": {ROOM: {"requirements": {"lighting_level": {"value": None, "note": None}}}}})["rooms"][ROOM]
    assert only["requirements"]["lighting_level"] == {"state": "NO"}  # an explicit null clears the measured value and the note, the state stays
    blank = change(change(changes=changes), {"rooms": {ROOM: {"requirements": {"lighting_level": {"note": "   "}}}}})["rooms"][ROOM]
    assert "note" not in blank["requirements"]["lighting_level"]  # a blank note is no note
    cleared = change(change(changes=changes), {"rooms": {ROOM: {"requirements": {"lighting_level": None}, "damages": None, "decision": None}}})["rooms"][ROOM]
    assert "lighting_level" not in cleared["requirements"] and "damages" not in cleared and "decision" not in cleared
    assert ROOM not in change(change(changes=changes), {"rooms": {ROOM: None}})["rooms"]


@pytest.mark.parametrize(
    "room, expected",
    [
        ({"requirements": {"nope": {"state": "YES"}}}, ("requirements", H.UNKNOWN_REQUIREMENT)),
        ({"requirements": {"lighting_permanent": {"state": "MAYBE"}}}, ("lighting_permanent", H.NOT_AN_OPTION)),
        ({"requirements": {"lighting_permanent": {"state": "YES", "value": 1}}}, ("lighting_permanent", H.WRONG_TYPE)),  # yes / no has no number
        ({"requirements": {"lighting_permanent": {"state": "YES", "value": True}}}, ("lighting_permanent", H.WRONG_TYPE)),
        ({"requirements": {"lighting_level": {"value": "dużo"}}}, ("lighting_level", H.WRONG_TYPE)),
        ({"requirements": {"lighting_level": {"value": -5}}}, ("lighting_level", H.OUT_OF_RANGE)),
        ({"requirements": {"temperature_range": {"value": {"min": 20, "max": 5}}}}, ("temperature_range", H.OUT_OF_RANGE)),
        ({"requirements": {"lighting_level": {"state": "YES", "colour": "red"}}}, ("lighting_level", H.WRONG_TYPE)),
        ({"requirements": []}, ("requirements", H.WRONG_TYPE)),
        ({"decision": "MAYBE"}, ("decision", H.NOT_AN_OPTION)),
        ({"damages": 3}, ("damages", H.WRONG_TYPE)),
        ({"verdict": "ok"}, ("rooms", H.WRONG_TYPE)),
    ],
)
def test_a_wrong_entry_is_refused_by_name_and_reason(room, expected):
    assert refused(changes={"rooms": {ROOM: room}}) == expected


def test_a_room_of_another_object_is_refused_and_nothing_changes():
    current = change(changes={"notes": "stare"})
    with pytest.raises(HandoverInvalidError) as exc:
        change(current, {"notes": "nowe", "rooms": {str(uuid.uuid4()): {"decision": "HANDED_OVER"}}})
    assert exc.value.reason == H.UNKNOWN_ROOM and current["notes"] == "stare"


def test_the_suggested_decision_follows_the_findings_and_a_room_is_handed_over_only_when_everything_is_met():
    ok = all_states("YES")["requirements"]
    assert H.suggested_decision(ok, CATALOG) == "HANDED_OVER"
    assert H.suggested_decision({**ok, "lighting_level": {"state": "NOT_APPLICABLE"}}, CATALOG) == "HANDED_OVER"
    assert H.suggested_decision({**ok, "lighting_level": {"state": "CONDITIONAL"}}, CATALOG) == "CONDITIONAL"
    assert H.suggested_decision({**ok, "lighting_level": {"state": "CONDITIONAL"}, "windows_glazed": {"state": "NO"}}, CATALOG) == "NOT_HANDED_OVER"
    assert H.suggested_decision({k: v for k, v in ok.items() if k != "windows_glazed"}, CATALOG) is None  # still unanswered
    assert H._allowed("HANDED_OVER", "HANDED_OVER") and not H._allowed("HANDED_OVER", "CONDITIONAL") and not H._allowed("HANDED_OVER", "NOT_HANDED_OVER")
    assert H._allowed("CONDITIONAL", "NOT_HANDED_OVER") and H._allowed("NOT_HANDED_OVER", "HANDED_OVER")  # stricter is always the owner's right


def codes(blockers):
    return [b.code for b in blockers]


def test_the_blockers_are_listed_in_the_order_of_doing():
    assert codes(H.evaluate({"attendees": [], "rooms": {}}, CATALOG)) == [H.HELD_ON_REQUIRED, H.NO_ATTENDEES, H.NO_ROOMS]
    data = {"held_on": date(2026, 10, 20), "attendees": [{"person_id": None, "name": "A", "role": None}],
            "rooms": {"r1": {"requirements": {"lighting_permanent": {"state": "YES"}}}, "r2": {**all_states("NO"), "decision": "HANDED_OVER"}}}
    found = {b.code: b.details for b in H.evaluate(data, CATALOG)}
    assert list(found) == [H.REQUIREMENTS_MISSING, H.DECISION_MISSING, H.DECISION_TOO_FAVOURABLE]
    assert found[H.REQUIREMENTS_MISSING] == {"rooms": [{"room_id": "r1", "keys": KEYS[1:]}]}
    assert found[H.DECISION_MISSING] == {"room_ids": ["r1"]} and found[H.DECISION_TOO_FAVOURABLE] == {"room_ids": ["r2"]}
    data["rooms"] = {"r2": {**all_states("NO"), "decision": "CONDITIONAL"}, "r3": {**all_states("YES"), "decision": "HANDED_OVER"}}
    assert H.evaluate(data, CATALOG) == []


# --- the draft ------------------------------------------------------------------------------------------------------------------------


def svc(db):
    return HandoverService(db)


async def test_the_draft_is_one_per_object_numbered_and_records_the_findings(db_session):
    w = await ready(db_session, telegram_id=9951)
    first, created = await svc(db_session).open_draft(w.project.id, w.owner.id)
    again, created_again = await svc(db_session).open_draft(w.project.id, w.owner.id)
    assert created and not created_again and again.id == first.id and first.sequence == 1 and first.status == "DRAFT"
    room = str(w.salon.id)
    row = await svc(db_session).update(w.project.id, first.id, w.owner.id, {
        "held_on": date(2026, 10, 20), "attendees": [{"person_id": str(w.person.id)}], "rooms": {room: {**all_states("YES"), "decision": "HANDED_OVER"}}})
    read = await svc(db_session).read(row)
    assert [b.code for b in read.blockers] == ["CONTRACT_REQUIRED"] and read.suggested == {room: "HANDED_OVER"}  # only a draft contract exists
    assert read.attendees == [{"person_id": str(w.person.id), "name": "Anna Nowak", "role": "Właścicielka"}]
    archived = await svc(db_session).archive_draft(w.project.id, first.id, w.owner.id)
    assert archived.status == "ARCHIVED"
    with pytest.raises(HandoverNotEditableError):
        await svc(db_session).update(w.project.id, first.id, w.owner.id, {"notes": "późno"})
    with pytest.raises(HandoverNotEditableError):
        await svc(db_session).archive_draft(w.project.id, first.id, w.owner.id)
    second, _ = await svc(db_session).open_draft(w.project.id, w.owner.id)  # an abandoned draft makes room for a new one
    assert second.sequence == 2


async def test_a_room_or_a_person_of_another_object_is_refused_and_a_stranger_finds_nothing(db_session):
    mine = await ready(db_session, telegram_id=9952)
    theirs = await ready(db_session, telegram_id=9953)
    draft, _ = await svc(db_session).open_draft(mine.project.id, mine.owner.id)
    with pytest.raises(HandoverInvalidError) as foreign_room:
        await svc(db_session).update(mine.project.id, draft.id, mine.owner.id, {"rooms": {str(theirs.salon.id): {"decision": "HANDED_OVER"}}})
    assert foreign_room.value.reason == H.UNKNOWN_ROOM
    with pytest.raises(HandoverInvalidError) as foreign_person:
        await svc(db_session).update(mine.project.id, draft.id, mine.owner.id, {"attendees": [{"person_id": str(theirs.person.id)}]})
    assert foreign_person.value.reason == H.UNKNOWN_PERSON
    with pytest.raises(ProjectNotFoundError):
        await svc(db_session).open_draft(mine.project.id, theirs.owner.id)
    with pytest.raises(ProjectNotFoundError):
        await svc(db_session).get(mine.project.id, draft.id, theirs.owner.id)
    with pytest.raises(HandoverNotFoundError):
        await svc(db_session).get(mine.project.id, uuid.uuid4(), mine.owner.id)
    other, _ = await svc(db_session).open_draft(theirs.project.id, theirs.owner.id)
    with pytest.raises(HandoverNotFoundError):  # the id of another object's protocol, asked through my own object
        await svc(db_session).get(mine.project.id, other.id, mine.owner.id)
    assert (await db_session.execute(select(HandoverProtocol.rooms).where(HandoverProtocol.id == draft.id))).scalar_one() == {}


async def test_the_requirements_to_meet_are_those_of_the_issued_or_signed_contract(db_session):
    w, owner_id, project_id, contract_id = await issued(db_session, 9954)
    draft, _ = await svc(db_session).open_draft(project_id, owner_id)
    read = await svc(db_session).read(draft)
    assert read.contract is not None and (read.contract.id, read.contract.status) == (contract_id, "ISSUED")
    assert read.required_values["lighting_level"] == 300 and read.required_values["temperature_range"] == {"min": 5, "max": 25}
    from app.models.contract import Contract

    base = await db_session.get(Contract, contract_id)
    later = Contract(owner_id=owner_id, project_id=project_id, version=2, status="ISSUED", answers={}, questionnaire_version=2,
                     issued_at=base.issued_at, snapshot={"answers": {"premises_requirement_values": {"lighting_level": 500}}},
                     document_html="<html></html>", estimate_id=base.estimate_id, estimate_version=1)
    db_session.add(later)
    await db_session.commit()
    newest = await svc(db_session).read(draft)
    assert newest.contract.version == 2 and newest.required_values == {"lighting_level": 500}  # the latest one applies
    bare = await ready(db_session, telegram_id=9955)  # a draft contract only: nothing is required yet
    other, _ = await svc(db_session).open_draft(bare.project.id, bare.owner.id)
    none = await svc(db_session).read(other)
    assert none.contract is None and none.required_values == {}


# --- HTTP -----------------------------------------------------------------------------------------------------------------------------


def url(project_id, tail=""):
    return f"/api/projects/{project_id}/handovers{tail}"


async def test_the_routes_need_a_token_and_a_stranger_gets_404(async_client: AsyncClient, db_session):
    mine = await ready(db_session, telegram_id=OWNER_TG)
    theirs = await ready(db_session, telegram_id=STRANGER_TG)
    assert (await async_client.get(url(mine.project.id))).status_code == 401
    headers = await login(async_client)
    assert (await async_client.get(url(theirs.project.id), headers=headers)).status_code == 404
    assert (await async_client.post(url(theirs.project.id), headers=headers)).status_code == 404
    assert (await async_client.get(url(mine.project.id, f"/{uuid.uuid4()}"), headers=headers)).status_code == 404


async def test_open_save_read_and_abandon_over_http(async_client: AsyncClient, db_session):
    w = await ready(db_session, telegram_id=OWNER_TG)
    headers = await login(async_client)
    pid, room = str(w.project.id), str(w.salon.id)
    created = await async_client.post(url(pid), headers=headers)
    assert created.status_code == 201, created.text
    body = created.json()
    assert (body["sequence"], body["status"], body["rooms"], body["attendees"]) == (1, "DRAFT", {}, [])
    assert [b["code"] for b in body["blockers"]] == ["CONTRACT_REQUIRED", "HELD_ON_REQUIRED", "NO_ATTENDEES", "NO_ROOMS"]
    assert (await async_client.post(url(pid), headers=headers)).status_code == 200  # the same draft
    hid = body["id"]
    assert (await async_client.patch(url(pid, f"/{hid}"), json={}, headers=headers)).status_code == 422
    assert (await async_client.patch(url(pid, f"/{hid}"), json={"unknown": 1}, headers=headers)).status_code == 422
    bad = await async_client.patch(url(pid, f"/{hid}"), json={"held_time": "25:61"}, headers=headers)
    assert bad.status_code == 422 and bad.json()["detail"] == {
        "code": "HANDOVER_INVALID", "message": "handover 'held_time': BAD_TIME", "details": {"key": "held_time", "reason": "BAD_TIME"}}
    saved = await async_client.patch(url(pid, f"/{hid}"), json={
        "held_on": "2026-10-20", "held_time": "09:30", "attendees": [{"person_id": str(w.person.id)}],
        "rooms": {room: {"requirements": {"lighting_permanent": {"state": "NO"}}, "decision": "CONDITIONAL"}}}, headers=headers)
    assert saved.status_code == 200, saved.text
    assert saved.json()["held_on"] == "2026-10-20" and saved.json()["rooms"][room]["requirements"]["lighting_permanent"] == {"state": "NO"}
    assert saved.json()["suggested"] == {room: None}  # a requirement is unanswered
    assert [b["code"] for b in saved.json()["blockers"]] == ["CONTRACT_REQUIRED", "REQUIREMENTS_MISSING"]
    assert (await async_client.get(url(pid), headers=headers)).json()["total"] == 1
    assert (await async_client.get(url(pid, f"/{hid}"), headers=headers)).json()["sequence"] == 1
    gone = await async_client.post(url(pid, f"/{hid}/archive"), headers=headers)
    assert gone.status_code == 200 and gone.json()["status"] == "ARCHIVED"
    assert (await async_client.patch(url(pid, f"/{hid}"), json={"notes": "x"}, headers=headers)).status_code == 409
    assert (await async_client.post(url(pid, f"/{hid}/archive"), headers=headers)).status_code == 409


# --- migration ------------------------------------------------------------------------------------------------------------------------


def test_revision_chain_and_length():
    module = load_migration("0047_handover_protocols")
    assert module.revision == "0047_handover_protocols" and module.down_revision == "0046_contract_signed" and len(module.revision) <= 32


def engine_0047():
    engine = contract_engine()
    run(engine, "0045_contract_issue", "upgrade")
    run(engine, "0046_contract_signed", "upgrade")
    run(engine, "0047_handover_protocols", "upgrade")
    return engine


ROW = ("INSERT INTO handover_protocols (id, owner_id, project_id, sequence, status, attendees, rooms, created_at, updated_at) "
       "VALUES (:id, 'u1', 'p1', :sequence, :status, '[]', '{}', '2026-10-10', '2026-10-10')")


def test_the_database_allows_one_draft_per_object_a_sequence_once_and_only_known_states():
    engine = engine_0047()
    with engine.begin() as conn:
        conn.execute(text(ROW), {"id": "a", "sequence": 1, "status": "DRAFT"})
        conn.execute(text(ROW), {"id": "b", "sequence": 2, "status": "ARCHIVED"})
        conn.execute(text(ROW), {"id": "c", "sequence": 3, "status": "ISSUED"})
    for bad in ({"id": "d", "sequence": 4, "status": "DRAFT"}, {"id": "e", "sequence": 1, "status": "ARCHIVED"},
                {"id": "f", "sequence": 5, "status": "SIGNED"}, {"id": "g", "sequence": 0, "status": "ARCHIVED"}):
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(text(ROW), bad)
    later = {"issued_at", "snapshot", "document_html", "contract_id", "contract_version"}  # added by 0048 (16F.2)
    assert {c["name"] for c in inspect(engine).get_columns("handover_protocols")} == {c.name for c in HandoverProtocol.__table__.columns} - later


def test_downgrade_refuses_while_a_protocol_exists_and_then_drops_only_the_table():
    engine = engine_0047()
    with engine.begin() as conn:
        conn.execute(text(ROW), {"id": "a", "sequence": 1, "status": "DRAFT"})
    with pytest.raises(RuntimeError, match="1 handover protocol"):
        run(engine, "0047_handover_protocols", "downgrade")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM handover_protocols"))
    run(engine, "0047_handover_protocols", "downgrade")
    assert "handover_protocols" not in inspect(engine).get_table_names() and "contracts" in inspect(engine).get_table_names()
    run(engine, "0047_handover_protocols", "upgrade")
