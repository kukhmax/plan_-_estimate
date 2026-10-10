"""Stage 16I.1: the protocol of information and decisions of the customer -- the rules, the draft, the document, issuing and freezing,
the API and the migration."""
import io
import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from pypdf import PdfReader
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.domain.documents.decision_document import build_decision_document, render_decision_html
from app.domain.documents.registry import TEMPLATES, DocumentKind
from app.domain.documents.renderer import DocumentRenderer
from app.domain.exceptions import DecisionGateError, DecisionInvalidError, DecisionNotEditableError, DecisionNotFoundError, ProjectNotFoundError
from app.domain.protocols import decision as D
from app.domain.protocols.decision import RiskFacts
from app.domain.protocols.sources import load_decision_sources
from app.domain.services.decision_service import DecisionService, data_of
from app.models.decision_protocol import DecisionProtocol
from app.models.project import Project
from app.models.risk import Risk, RiskSeverity
from tests.test_stage15f2_api import use_issuer  # noqa: F401  (a fixture)
from tests.test_stage15f2_issuing import Delivery, issuer, journal, text_of, user_of
from tests.test_stage16e2_contract import OWNER_TG, STRANGER_TG, contract_engine, load_migration, login, ready, run
from tests.test_stage16e4_signing import issued

TODAY = date(2026, 10, 20)
NUMBER = "DECYZ/2026/10/20/1000"
PERSON = str(uuid.uuid4())
PEOPLE = {PERSON: ("Anna Nowak", "Właścicielka")}
ROOM, RISK, OTHER_RISK = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
I1, I2, I3 = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())


def facts(risk_id=RISK, room_id=ROOM, code="moisture_block_finishing"):
    return RiskFacts(risk_id, room_id, "Salon", "CRITICAL", f"risk.{code}.title", f"risk.{code}.explanation", f"risk.{code}.consequence",
                     f"risk.{code}.communication", True)


RISKS = {RISK: facts(), OTHER_RISK: facts(OTHER_RISK, code="board_movement_crack")}


def change(current=None, changes=None, risks=None, rooms=(ROOM,), people=PEOPLE):
    return D.apply_changes(current or D.empty_state(), changes or {}, risks=RISKS if risks is None else risks, room_ids=set(rooms), people=people)


def refused(**kw):
    with pytest.raises(DecisionInvalidError) as exc:
        change(**kw)
    return exc.value.key, exc.value.reason


OWN = {"title": "Wydłużenie przerwy technologicznej", "recommendation": "Odczekać 72 godziny przed gruntowaniem", "consequence": "Gładź może pękać"}


# --- the rules -------------------------------------------------------------------------------------------------------------------------


def test_the_simple_fields_are_checked_and_cleared():
    state = change(changes={"held_on": TODAY, "held_time": "09:30", "understood": True, "signature_refused": None, "notes": "  Rozmowa w salonie  "})
    assert (state["held_time"], state["understood"], state["signature_refused"], state["notes"]) == ("09:30", True, False, "Rozmowa w salonie")
    cleared = change(state, {"held_time": None, "notes": None, "understood": None})
    assert (cleared["held_time"], cleared["notes"], cleared["understood"]) == (None, None, False)
    assert refused(changes={"held_time": "9:30"}) == ("held_time", "BAD_TIME")
    assert refused(changes={"held_on": "2026-10-20"}) == ("held_on", "WRONG_TYPE")
    assert refused(changes={"understood": "yes"}) == ("understood", "WRONG_TYPE")
    assert refused(changes={"signature_refused": 1}) == ("signature_refused", "WRONG_TYPE")
    assert refused(changes={"notes": "x" * 4001}) == ("notes", "TOO_LONG")
    assert refused(changes={"nonsense": 1}) == ("nonsense", D.UNKNOWN_FIELD)
    state = change(changes={"attendees": [{"person_id": PERSON}, {"name": "Jan Sąsiad", "role": "administrator"}]})
    assert [a["name"] for a in state["attendees"]] == ["Anna Nowak", "Jan Sąsiad"]
    assert refused(changes={"attendees": [{"person_id": str(uuid.uuid4())}]}) == ("attendees", "UNKNOWN_PERSON")


def test_an_item_is_a_risk_of_the_object_or_a_recommendation_with_its_three_texts():
    state = change(changes={"items": {I1: {"risk_id": RISK}, I2: OWN}})
    assert [(i["id"], i["source"]) for i in state["items"]] == [(I1, "RISK"), (I2, "OWN")]  # in the order they were added
    assert state["items"][0]["risk_id"] == RISK and state["items"][1]["title"] == "Wydłużenie przerwy technologicznej"
    assert refused(changes={"items": {I1: {"risk_id": str(uuid.uuid4())}}}) == ("risk_id", D.UNKNOWN_RISK)
    assert refused(changes={"items": {I1: {"risk_id": "x"}}}) == ("risk_id", "WRONG_TYPE")
    assert refused(changes={"items": {I1: {"title": "Sam tytuł"}}}) == ("items", D.BAD_ITEM)
    assert refused(changes={"items": {I1: {"decision": "DECLINED"}}}) == ("items", D.BAD_ITEM)  # nothing to decide about
    assert refused(changes={"items": {"x": OWN}}) == ("items", "WRONG_TYPE")
    assert refused(changes={"items": {I1: {**OWN, "colour": "red"}}}) == ("items", "WRONG_TYPE")
    assert refused(changes={"items": [I1]}) == ("items", "WRONG_TYPE")
    assert refused(changes={"items": {I1: {**OWN, "title": "x" * 256}}}) == ("title", "TOO_LONG")
    assert refused(changes={"items": {I1: {**OWN, "recommendation": 5}}}) == ("recommendation", "WRONG_TYPE")
    assert refused(changes={"items": {I1: {**OWN, "price": "dużo"}}}) == ("price", D.BAD_MONEY)
    assert refused(changes={"items": {I1: {**OWN, "room_id": str(uuid.uuid4())}}}) == ("room_id", D.UNKNOWN_ROOM)
    own = change(changes={"items": {I1: {**OWN, "price": "1250,5", "room_id": ROOM}}})["items"][0]
    assert (own["price"], own["room_id"]) == ("1250.50", ROOM)


def test_the_texts_of_a_risk_item_and_its_risk_are_not_the_owners_to_change():
    first = change(changes={"items": {I1: {"risk_id": RISK}}})
    assert refused(current=first, changes={"items": {I1: {"title": "Mój tytuł"}}}) == ("title", D.ITEM_LOCKED)
    assert refused(current=first, changes={"items": {I1: {"price": "100"}}}) == ("price", D.ITEM_LOCKED)
    assert refused(current=first, changes={"items": {I1: {"risk_id": OTHER_RISK}}}) == ("risk_id", D.ITEM_LOCKED)
    assert change(first, {"items": {I1: {"risk_id": RISK}}})["items"][0]["risk_id"] == RISK  # the same risk again changes nothing
    noted = change(first, {"items": {I1: {"note": " Klient był zaskoczony "}}})["items"][0]
    assert noted["note"] == "Klient był zaskoczony"


def test_a_decision_is_one_of_three_and_the_answer_of_the_contractor_exists_only_with_a_demand():
    state = change(changes={"items": {I1: {"risk_id": RISK, "decision": "ACCEPTED", "order_ref": " Z/12 "}}})
    first = state["items"][0]
    assert (first["decision"], first["order_ref"]) == ("ACCEPTED", "Z/12")
    insisting = change(state, {"items": {I1: {"decision": "INSISTS", "executor_action": "PERFORM"}}})
    insists = insisting["items"][0]
    assert (insists["decision"], insists["executor_action"], "order_ref" in insists) == ("INSISTS", "PERFORM", False)  # an order of an accepted one only
    declined = change(insisting, {"items": {I1: {"decision": "DECLINED"}}})["items"][0]
    assert "executor_action" not in declined and declined["decision"] == "DECLINED"  # no demand: no answer to it
    assert change(insisting, {"items": {I1: {"decision": None}}})["items"][0].get("decision") is None
    assert refused(changes={"items": {I1: {"risk_id": RISK, "decision": "MAYBE"}}}) == ("decision", "NOT_AN_OPTION")
    assert refused(changes={"items": {I1: {"risk_id": RISK, "decision": "INSISTS", "executor_action": "IGNORE"}}}) == ("executor_action", "NOT_AN_OPTION")
    assert refused(changes={"items": {I1: {"risk_id": RISK, "order_ref": "x" * 65}}}) == ("order_ref", "TOO_LONG")
    assert refused(changes={"items": {I1: {"risk_id": RISK, "note": "x" * 2001}}}) == ("note", "TOO_LONG")


def test_an_item_is_removed_with_null_the_order_is_kept_and_a_failed_change_changes_nothing():
    state = change(changes={"items": {I1: {"risk_id": RISK}, I2: OWN, I3: {"risk_id": OTHER_RISK}}})
    assert [i["id"] for i in change(state, {"items": {I2: None}})["items"]] == [I1, I3]
    assert [i["id"] for i in change(state, {"items": {I1: {"decision": "DECLINED"}}})["items"]] == [I1, I2, I3]
    assert change(state, {"items": {str(uuid.uuid4()): None}})["items"] == state["items"]  # removing what is not there is no error
    with pytest.raises(DecisionInvalidError):
        change(state, {"notes": "nowe", "items": {I2: {"decision": "NOPE"}}})
    assert state["notes"] is None and [i.get("decision") for i in state["items"]] == [None, None, None]


# --- what is missing -----------------------------------------------------------------------------------------------------------------------


def codes(blockers):
    return [b.code for b in blockers]


def decided(**over):
    item = {"id": I1, "source": "RISK", "risk_id": RISK, "decision": "DECLINED"}
    return {**D.empty_state(), "held_on": TODAY, "attendees": [{"person_id": None, "name": "A", "role": None}], "items": [{**item, **over}], "understood": True}


def test_the_blockers_are_listed_in_the_order_of_doing():
    assert codes(D.evaluate(D.empty_state(), RISKS)) == [D.HELD_ON_REQUIRED, D.NO_ATTENDEES, D.NO_ITEMS, D.DECLARATION_REQUIRED]
    assert D.evaluate(decided(), RISKS) == []
    undecided = D.evaluate(decided(decision=None), RISKS)
    assert [(b.code, b.details) for b in undecided] == [(D.ITEM_DECISION_REQUIRED, {"item_ids": [I1]})]
    unanswered = D.evaluate(decided(decision="INSISTS"), RISKS)
    assert [(b.code, b.details) for b in unanswered] == [(D.ITEM_ACTION_REQUIRED, {"item_ids": [I1]})]
    assert D.evaluate(decided(decision="INSISTS", executor_action="REFUSE"), RISKS) == []
    assert D.evaluate(decided(decision="ACCEPTED"), RISKS) == []  # an accepted recommendation needs no answer, not even an order number


def test_a_risk_that_is_gone_blocks_but_an_own_item_does_not_depend_on_risks():
    gone = D.evaluate(decided(risk_id=str(uuid.uuid4())), RISKS)
    assert [(b.code, b.details) for b in gone] == [(D.ITEM_RISK_GONE, {"item_ids": [I1]})]
    own = {"id": I1, "source": "OWN", **OWN, "decision": "DECLINED"}
    assert D.evaluate({**decided(), "items": [own]}, {}) == []


def test_the_customer_either_declares_he_understood_or_his_refusal_to_sign_is_written_down():
    assert codes(D.evaluate({**decided(), "understood": False}, RISKS)) == [D.DECLARATION_REQUIRED]
    assert codes(D.evaluate({**decided(), "understood": False, "signature_refused": True}, RISKS)) == [D.REFUSAL_NOTE_REQUIRED]
    assert D.evaluate({**decided(), "understood": False, "signature_refused": True, "notes": "Odmówił podpisu, bo chciał skonsultować z mężem"}, RISKS) == []
    assert codes(D.evaluate({**decided(), "signature_refused": True}, RISKS)) == [D.REFUSAL_NOTE_REQUIRED]  # a refusal is always explained


# --- the draft ----------------------------------------------------------------------------------------------------------------------------


def svc(db):
    return DecisionService(db)


def make_risk(w, code="moisture_block_finishing", *, room=None, active=True, candidate=True, severity=RiskSeverity.CRITICAL):
    return Risk(
        room_id=(room or w.salon).id, inspection_id=w.inspection.id, risk_code=code.upper(), rule_code=code.upper(), rule_version=1, severity=severity,
        title_key=f"risk.{code}.title", explanation_key=f"risk.{code}.explanation", consequence_key=f"risk.{code}.consequence",
        mitigation_key=f"risk.{code}.mitigation", communication_key=f"risk.{code}.communication", source_signature=uuid.uuid4().hex,
        is_active=active, warranty_exclusion_candidate=candidate, blocks_finishing=severity is RiskSeverity.CRITICAL,
    )


async def add_risks(db, w):
    moisture, board = make_risk(w), make_risk(w, "board_movement_crack", severity=RiskSeverity.HIGH)
    db.add_all([moisture, board, make_risk(w, "crack_recurrence", candidate=False), make_risk(w, "dusty_substrate_prime", active=False),
                make_risk(w, "weak_adhesion_prep", room=w.kuchnia)])
    await db.commit()
    return str(moisture.id), str(board.id)


async def test_only_active_candidate_risks_of_the_object_are_offered_with_the_catalogues_texts(db_session):
    w = await ready(db_session, telegram_id=9801)
    moisture, board = await add_risks(db_session, w)
    draft, _ = await svc(db_session).open_draft(w.project.id, w.owner.id)
    read = await svc(db_session).read(draft)
    assert [o.id for o in read.risk_options] == [moisture, board, read.risk_options[2].id]  # moisture, board movement, the kitchen's adhesion
    assert read.risk_options[0].title == "Podwyższona wilgotność podłoża" and read.risk_options[0].severity == "CRITICAL" and read.risk_options[0].blocks_finishing
    assert [(o.room_name, o.used) for o in read.risk_options] == [("Salon", False), ("Salon", False), ("Kuchnia", False)]
    assert "crack_recurrence" not in str([o.id for o in read.risk_options]) and len(read.risk_options) == 3  # not a candidate / not active
    assert [r.name for r in read.rooms] == ["Salon", "Kuchnia"]
    foreign = await ready(db_session, telegram_id=9802)
    assert (await load_decision_sources(db_session, foreign.owner.id, foreign.project.id)).risks == {}  # another object's risks are not seen


async def test_the_read_model_resolves_a_risk_item_to_the_catalogues_texts_and_marks_the_option_used(db_session):
    w = await ready(db_session, telegram_id=9803)
    moisture, board = await add_risks(db_session, w)
    draft, _ = await svc(db_session).open_draft(w.project.id, w.owner.id)
    row = await svc(db_session).update(w.project.id, draft.id, w.owner.id, {"items": {I1: {"risk_id": moisture, "decision": "INSISTS", "executor_action": "REFUSE"}, I2: OWN}})
    read = await svc(db_session).read(row)
    risk_item, own_item = read.items
    assert (risk_item.source, risk_item.risk_id, risk_item.room_name, risk_item.severity, risk_item.blocks_finishing, risk_item.risk_active) == (
        "RISK", moisture, "Salon", "CRITICAL", True, True)
    assert risk_item.title and risk_item.state and risk_item.recommendation and risk_item.consequence and risk_item.price is None
    assert (risk_item.decision, risk_item.executor_action) == ("INSISTS", "REFUSE")
    assert (own_item.source, own_item.title, own_item.recommendation, own_item.state, own_item.room_name) == (
        "OWN", OWN["title"], OWN["recommendation"], None, None)
    assert [(o.id, o.used) for o in read.risk_options if o.id in (moisture, board)] == [(moisture, True), (board, False)]


async def test_a_risk_that_stops_being_found_is_shown_as_gone_and_blocks_the_issue(db_session):
    w = await ready(db_session, telegram_id=9804)
    moisture, _ = await add_risks(db_session, w)
    draft, _ = await svc(db_session).open_draft(w.project.id, w.owner.id)
    row = await svc(db_session).update(w.project.id, draft.id, w.owner.id, {"items": {I1: {"risk_id": moisture, "decision": "DECLINED"}}})
    risk = await db_session.get(Risk, uuid.UUID(moisture))
    risk.is_active = False
    await db_session.commit()
    read = await svc(db_session).read(row)
    assert read.items[0].risk_active is False
    assert D.ITEM_RISK_GONE in [b.code for b in read.blockers]
    with pytest.raises(DecisionInvalidError) as late:  # and it cannot be added any more
        await svc(db_session).update(w.project.id, draft.id, w.owner.id, {"items": {I2: {"risk_id": moisture}}})
    assert late.value.reason == D.UNKNOWN_RISK


async def test_the_draft_is_one_per_object_numbered_abandoned_and_foreign_data_is_refused(db_session):
    mine = await ready(db_session, telegram_id=9805)
    theirs = await ready(db_session, telegram_id=9806)
    their_risk, _ = await add_risks(db_session, theirs)
    first, created = await svc(db_session).open_draft(mine.project.id, mine.owner.id)
    again, created_again = await svc(db_session).open_draft(mine.project.id, mine.owner.id)
    assert created and not created_again and again.id == first.id and first.sequence == 1
    with pytest.raises(DecisionInvalidError) as foreign_risk:
        await svc(db_session).update(mine.project.id, first.id, mine.owner.id, {"items": {I1: {"risk_id": their_risk}}})
    assert foreign_risk.value.reason == D.UNKNOWN_RISK
    with pytest.raises(DecisionInvalidError) as foreign_room:
        await svc(db_session).update(mine.project.id, first.id, mine.owner.id, {"items": {I1: {**OWN, "room_id": str(theirs.salon.id)}}})
    assert foreign_room.value.reason == D.UNKNOWN_ROOM
    with pytest.raises(DecisionInvalidError) as foreign_person:
        await svc(db_session).update(mine.project.id, first.id, mine.owner.id, {"attendees": [{"person_id": str(theirs.person.id)}]})
    assert foreign_person.value.reason == "UNKNOWN_PERSON"
    with pytest.raises(ProjectNotFoundError):
        await svc(db_session).open_draft(mine.project.id, theirs.owner.id)
    with pytest.raises(ProjectNotFoundError):
        await svc(db_session).get(mine.project.id, first.id, theirs.owner.id)
    with pytest.raises(DecisionNotFoundError):
        await svc(db_session).get(mine.project.id, uuid.uuid4(), mine.owner.id)
    other, _ = await svc(db_session).open_draft(theirs.project.id, theirs.owner.id)
    with pytest.raises(DecisionNotFoundError):
        await svc(db_session).get(mine.project.id, other.id, mine.owner.id)
    archived = await svc(db_session).archive_draft(mine.project.id, first.id, mine.owner.id)
    assert archived.status == "ARCHIVED"
    with pytest.raises(DecisionNotEditableError):
        await svc(db_session).update(mine.project.id, first.id, mine.owner.id, {"notes": "późno"})
    with pytest.raises(DecisionNotEditableError):
        await svc(db_session).archive_draft(mine.project.id, first.id, mine.owner.id)
    assert (await svc(db_session).open_draft(mine.project.id, mine.owner.id))[0].sequence == 2


# --- the document ---------------------------------------------------------------------------------------------------------------------------


async def full_world(db, telegram_id, *, insists=True):
    """A world with an issued contract, two risks and a draft that passes the gate: one risk the customer insists on, one he declines,
    one recommendation of the contractor's own that he accepts."""
    w, owner_id, project_id, contract_id = await issued(db, telegram_id)
    moisture, board = await add_risks(db, w)
    draft, _ = await svc(db).open_draft(project_id, owner_id)
    first = {"risk_id": moisture, "decision": "INSISTS", "executor_action": "PERFORM", "note": "Klient nalega"} if insists else {"risk_id": moisture, "decision": "DECLINED"}
    await svc(db).update(project_id, draft.id, owner_id, {
        "held_on": TODAY, "held_time": "10:00", "attendees": [{"person_id": str(w.person.id)}, {"name": "Jan Sąsiad", "role": "administrator"}],
        "items": {I1: first, I2: {"risk_id": board, "decision": "DECLINED"},
                  I3: {**OWN, "price": "300", "room_id": str(w.salon.id), "decision": "ACCEPTED", "order_ref": "Z/7"}},
        "understood": True, "notes": "Klucze oddane"})
    return w, owner_id, project_id, draft.id, moisture


async def build(db, owner_id, project_id, hid=None, *, working=False, number=NUMBER):
    sources = await load_decision_sources(db, owner_id, project_id)
    row = await db.get(DecisionProtocol, hid) if hid else None
    data = data_of(row) if row else {}
    return build_decision_document(data, sources, working=working, issued_on=TODAY, number=None if working else number, sequence=1), sources, data


def body_of(document):
    html = render_decision_html(document)
    return html[html.index("<body"):]


async def test_the_page_prints_every_item_with_the_catalogues_words_the_decision_and_what_the_contractor_does(db_session):
    w, owner_id, project_id, hid, moisture = await full_world(db_session, 9811)
    document, sources, _ = await build(db_session, owner_id, project_id, hid)
    body = body_of(document)
    assert document.layout.meta.title == "Protokół informacji i decyzji Zamawiającego"
    facts_ = {row.label: row.value for row in document.facts}
    assert facts_["Data i godzina"] == "20.10.2026, 10:00" and facts_["Umowa"].startswith("wersja 1, nr UMOWA/")
    first, second, third = document.items
    risk = sources.risks[moisture]
    from app.domain.documents.catalog import localize_risk_text as t_
    assert (first.title, first.state, first.recommendation, first.consequence, first.room) == (
        t_(risk.title_key), t_(risk.explanation_key), t_(risk.communication_key), t_(risk.consequence_key), "Salon")
    assert [o.label for o in first.decisions if o.checked] == ["Żądam wykonania pracy wbrew zaleceniu Wykonawcy"]
    assert [o.label for o in first.actions if o.checked] == ["Wykonawca wykonuje pracę po sporządzeniu niniejszego protokołu (§ 17 ust. 3 Umowy)"]
    assert first.effect == "Skutki dla gwarancji — w zakresie określonym w § 16 ust. 3 lit. f Umowy." and first.note == "Klient nalega"
    assert [o.label for o in second.decisions if o.checked] == ["Rezygnuję z zalecenia Wykonawcy"] and second.actions is None and second.effect
    assert [o.label for o in third.decisions if o.checked] == ["Akceptuję zalecenie Wykonawcy — Zlecenie nr Z/7"]
    assert third.title == OWN["title"] and third.price == "300,00\xa0zł" and third.room == "Salon" and third.effect is None and third.state is None
    assert document.declaration.checked and not document.refusal.checked and document.notes == "Klucze oddane"
    assert [a.name for a in document.attendees] == ["Anna Nowak", "Jan Sąsiad"] and NUMBER in body and 'class="watermark' not in body
    assert body.count("☒") == 5  # three decisions, one answer of the contractor, the declaration


async def test_a_customer_who_refused_to_sign_is_printed_so_and_the_declaration_is_not_ticked_for_him(db_session):
    w, owner_id, project_id, hid, _ = await full_world(db_session, 9812, insists=False)
    await svc(db_session).update(project_id, hid, owner_id, {"understood": False, "signature_refused": True, "notes": "Odmówił podpisu"})
    document, _, _ = await build(db_session, owner_id, project_id, hid)
    assert document.refusal.checked and not document.declaration.checked and "Odmówił podpisu" in body_of(document)
    assert document.items[0].actions is None  # he declined: nobody asks the contractor to answer a demand


async def test_the_working_version_is_a_blank_form_that_never_refuses_and_cannot_be_numbered(db_session):
    w = await ready(db_session, telegram_id=9813)
    document, sources, _ = await build(db_session, w.owner.id, w.project.id, working=True)
    body = body_of(document)
    assert document.layout.draft and document.layout.light_watermark and document.layout.meta.number is None
    assert 'class="watermark light"' in body and len(document.items) == 3 and body.count("☐") == 3 * 5 + 2 and body.count("☒") == 0
    assert body.count('class="write-line"') >= 15 and "Obecni: do wpisania." in body
    assert all(i.title is None and i.actions is not None for i in document.items)  # a blank item leaves room for the contractor's answer too
    with pytest.raises(Exception) as numbered:
        build_decision_document({}, sources, working=True, issued_on=TODAY, number="DECYZ/1")
    assert numbered.value.reason == "DRAFT_NUMBERED"
    sources.base.executor = None
    assert build_decision_document({}, sources, working=True, issued_on=TODAY)
    with pytest.raises(Exception) as no_profile:
        build_decision_document({}, sources, working=False, issued_on=TODAY)
    assert no_profile.value.reason == "EXECUTOR_PROFILE_REQUIRED"


async def test_a_real_pdf_with_the_number_on_every_page(db_session):
    w, owner_id, project_id, hid, _ = await full_world(db_session, 9814)
    document, _, _ = await build(db_session, owner_id, project_id, hid)
    pdf = (await DocumentRenderer().render(render_decision_html(document))).pdf
    pages = PdfReader(io.BytesIO(pdf)).pages
    assert len(pages) >= 1 and all(NUMBER in page.extract_text() for page in pages)
    flat = " ".join(text_of(pdf).split())
    for part in ("Protokół informacji i decyzji Zamawiającego", "Wydłużenie przerwy technologicznej", "Anna Nowak", "Żądam wykonania pracy wbrew zaleceniu", "§ 16 ust. 3 lit. f"):
        assert part in flat, part


# --- the gate and the freeze ----------------------------------------------------------------------------------------------------------------


async def test_a_protocol_that_is_not_ready_is_refused_with_the_list_and_takes_no_number(db_session):
    w, owner_id, project_id, contract_id = await issued(db_session, 9815)
    draft, _ = await svc(db_session).open_draft(project_id, owner_id)
    run_ = issuer(delivery=Delivery())
    with pytest.raises(DecisionGateError) as refused_:
        await run_.start_decision(db_session, await user_of(db_session, owner_id), project_id, draft.id)
    assert [b.code for b in refused_.value.blockers] == ["HELD_ON_REQUIRED", "NO_ATTENDEES", "NO_ITEMS", "DECLARATION_REQUIRED"]
    assert all(j.kind != "DECISION_PROTOCOL" for j in await journal(db_session))
    w2 = await ready(db_session, telegram_id=9816)  # only a draft contract: no contract to work under
    other, _ = await svc(db_session).open_draft(w2.project.id, w2.owner.id)
    with pytest.raises(DecisionGateError) as no_contract:
        await run_.start_decision(db_session, await user_of(db_session, w2.owner.id), w2.project.id, other.id)
    assert "CONTRACT_REQUIRED" in [b.code for b in no_contract.value.blockers]


async def test_issuing_freezes_the_protocol_numbers_it_sends_the_pdf_and_records_it(db_session):
    w, owner_id, project_id, hid, moisture = await full_world(db_session, 9817)
    telegram = w.owner.telegram_user_id
    sender = Delivery()
    run_ = issuer(delivery=sender)
    reservation = await run_.start_decision(db_session, await user_of(db_session, owner_id), project_id, hid)
    assert (reservation.document.kind, reservation.document.status, reservation.document.source_id, reservation.document.source_version) == (
        "DECISION_PROTOCOL", "PENDING", hid, 1)
    assert reservation.document.number.startswith("DECYZ/2026/10/08/")
    await run_.drain()
    done = [j for j in await journal(db_session) if j.kind == "DECISION_PROTOCOL"][0]
    number = done.number
    assert (done.status, done.error_code, done.title) == ("SENT", None, "Protokół informacji i decyzji Zamawiającego — nr 1")
    message = sender.sent[-1]
    assert message["chat_id"] == telegram and message["filename"].startswith("DECYZ-2026-10-08-")
    assert message["caption"].startswith("Protokół informacji i decyzji Zamawiającego — nr 1 — Mokotów\nDECYZ/") and number in text_of(message["pdf"])
    db_session.expire_all()
    row = await db_session.get(DecisionProtocol, hid)
    assert row.status == "ISSUED" and row.issued_at is not None and row.contract_version == 1 and row.contract_id is not None and number in row.document_html
    snap = row.snapshot
    assert (snap["held_on"], snap["understood"], snap["signature_refused"], snap["notes"]) == ("2026-10-20", True, False, "Klucze oddane")
    first, second, third = snap["items"]
    assert (first["source"], first["risk_id"], first["decision"], first["executor_action"], first["room_name"], first["severity"]) == (
        "RISK", moisture, "INSISTS", "PERFORM", "Salon", "CRITICAL")
    assert first["title"] and first["state"] and first["recommendation"] and first["consequence"] and first["note"] == "Klient nalega"
    assert (third["source"], third["price"], third["order_ref"], third["decision"], third["risk_id"]) == ("OWN", "300.00", "Z/7", "ACCEPTED", None)
    assert second["decision"] == "DECLINED" and snap["contract"]["version"] == 1 and snap["contract"]["number"].startswith("UMOWA/") and snap["client"] and snap["executor"]
    with pytest.raises(DecisionNotEditableError):
        await svc(db_session).update(project_id, hid, owner_id, {"notes": "inne"})
    with pytest.raises(DecisionNotEditableError):
        await run_.start_decision(db_session, await user_of(db_session, owner_id), project_id, hid)
    with pytest.raises(DecisionNotEditableError):  # the service itself refuses to freeze twice
        await svc(db_session).mark_issued(project_id, hid, owner_id, issued_at=run_.clock(), snapshot={}, document_html="<html></html>",
                                          contract_id=None, contract_version=None)
    assert (await svc(db_session).open_draft(project_id, owner_id))[0].sequence == 2


async def test_the_issued_page_does_not_change_when_the_data_do_and_an_empty_stored_page_is_refused(db_session):
    w, owner_id, project_id, hid, moisture = await full_world(db_session, 9818)
    run_ = issuer(delivery=Delivery())
    await run_.start_decision(db_session, await user_of(db_session, owner_id), project_id, hid)
    await run_.drain()
    frozen = (await db_session.get(DecisionProtocol, hid)).document_html
    project = (await db_session.execute(select(Project).where(Project.id == project_id))).scalar_one()
    project.name = "Zupełnie inna nazwa"
    w.person.name = "Ktoś Inny"
    (await db_session.get(Risk, uuid.UUID(moisture))).is_active = False
    await db_session.commit()
    row = [j for j in await journal(db_session) if j.kind == "DECISION_PROTOCOL"][0]
    again = await run_._render(db_session, row)
    assert (await db_session.get(DecisionProtocol, hid)).document_html == frozen
    flat = text_of(again.pdf)
    assert "Anna Nowak" in flat and "Ktoś Inny" not in flat and "Zupełnie inna nazwa" not in flat
    protocol = await db_session.get(DecisionProtocol, hid)
    protocol.document_html = ""
    await db_session.commit()
    with pytest.raises(Exception) as empty:
        await run_._render(db_session, row)
    assert empty.value.reason == "DECISION_NOT_ISSUED"
    row.source_id = uuid.uuid4()
    with pytest.raises(Exception) as missing:
        await run_._render(db_session, row)
    assert missing.value.reason == "DECISION_NOT_ISSUED"


async def test_the_preview_follows_the_draft_and_never_leaves_a_row(db_session):
    w, owner_id, project_id, hid, _ = await full_world(db_session, 9819)
    sender = Delivery()
    before = len(await journal(db_session))
    result = await issuer(delivery=sender).preview_decision(db_session, await user_of(db_session, owner_id), project_id)
    assert result.pages >= 1
    message = sender.sent[-1]
    assert message["filename"] == "Protokol-informacji-i-decyzji-wersja-robocza.pdf"
    assert message["caption"].startswith("WERSJA ROBOCZA — Protokół informacji i decyzji Zamawiającego")
    flat = " ".join(text_of(message["pdf"]).split())
    assert "WERSJA ROBOCZA" in flat and "Wydłużenie przerwy technologicznej" in flat
    assert len(await journal(db_session)) == before
    blank = Delivery()
    other = await ready(db_session, telegram_id=9820)  # no draft: a blank form
    await issuer(delivery=blank).preview_decision(db_session, await user_of(db_session, other.owner.id), other.project.id)
    assert blank.sent[-1]["caption"].startswith("WERSJA ROBOCZA — Protokół informacji i decyzji Zamawiającego")


# --- HTTP ---------------------------------------------------------------------------------------------------------------------------------------


def url(project_id, tail=""):
    return f"/api/projects/{project_id}/decisions{tail}"


async def test_the_routes_need_a_token_and_a_stranger_gets_404(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    mine = await ready(db_session, telegram_id=OWNER_TG)
    theirs = await ready(db_session, telegram_id=STRANGER_TG)
    use_issuer(issuer(delivery=Delivery()))
    assert (await async_client.get(url(mine.project.id))).status_code == 401
    assert (await async_client.post(url(mine.project.id, f"/{uuid.uuid4()}/issue"))).status_code == 401
    assert (await async_client.post(f"/api/projects/{mine.project.id}/documents/decision/preview")).status_code == 401
    headers = await login(async_client)
    draft, _ = await svc(db_session).open_draft(theirs.project.id, theirs.owner.id)
    for response in (
        await async_client.get(url(theirs.project.id), headers=headers),
        await async_client.post(url(theirs.project.id), headers=headers),
        await async_client.post(url(theirs.project.id, f"/{draft.id}/issue"), headers=headers),
        await async_client.post(f"/api/projects/{theirs.project.id}/documents/decision/preview", headers=headers),
        await async_client.get(url(mine.project.id, f"/{uuid.uuid4()}"), headers=headers),
        await async_client.get(url(mine.project.id, f"/{draft.id}"), headers=headers),
        await async_client.patch(url(theirs.project.id, f"/{draft.id}"), json={"notes": "x"}, headers=headers),
    ):
        assert response.status_code == 404


async def test_open_record_issue_and_abandon_over_http(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w, owner_id, project_id, contract_id = await issued(db_session, OWNER_TG)
    moisture, _ = await add_risks(db_session, w)
    run_ = use_issuer(issuer(delivery=Delivery()))
    headers = await login(async_client)
    pid = str(project_id)
    created = await async_client.post(url(pid), headers=headers)
    assert created.status_code == 201, created.text
    body = created.json()
    assert (body["sequence"], body["status"], body["items"], body["understood"]) == (1, "DRAFT", [], False)
    assert [o["id"] for o in body["risk_options"]][0] == moisture and body["rooms"][0]["name"] == "Salon" and body["contract"]["version"] == 1
    assert (await async_client.post(url(pid), headers=headers)).status_code == 200
    hid = body["id"]
    assert (await async_client.patch(url(pid, f"/{hid}"), json={}, headers=headers)).status_code == 422
    assert (await async_client.patch(url(pid, f"/{hid}"), json={"unknown": 1}, headers=headers)).status_code == 422
    bad = await async_client.patch(url(pid, f"/{hid}"), json={"items": {I1: {"risk_id": str(uuid.uuid4())}}}, headers=headers)
    assert bad.status_code == 422 and bad.json()["detail"] == {"code": "DECISION_INVALID", "message": "decision protocol 'risk_id': UNKNOWN_RISK",
                                                              "details": {"key": "risk_id", "reason": "UNKNOWN_RISK"}}
    blocked = await async_client.post(url(pid, f"/{hid}/issue"), headers=headers)
    assert blocked.status_code == 422 and blocked.json()["detail"]["code"] == "DECISION_GATE_BLOCKED"
    assert blocked.json()["detail"]["details"]["blockers"][0]["code"] == "HELD_ON_REQUIRED"
    saved = await async_client.patch(url(pid, f"/{hid}"), json={
        "held_on": "2026-10-20", "attendees": [{"name": "Jan Sąsiad", "role": "administrator"}], "understood": True,
        "items": {I1: {"risk_id": moisture, "decision": "DECLINED"}}}, headers=headers)
    assert saved.status_code == 200, saved.text
    assert saved.json()["blockers"] == [] and saved.json()["items"][0]["source"] == "RISK" and saved.json()["risk_options"][0]["used"] is True
    ok = await async_client.post(url(pid, f"/{hid}/issue"), headers=headers)
    assert ok.status_code == 202, ok.text
    assert ok.json()["kind"] == "DECISION_PROTOCOL" and ok.json()["number"].startswith("DECYZ/") and ok.json()["source_id"] == hid
    await run_.drain()
    again = await async_client.post(url(pid, f"/{hid}/issue"), headers=headers)
    assert again.status_code == 409 and again.json()["detail"]["code"] == "DECISION_NOT_EDITABLE"
    listed = (await async_client.get(f"/api/projects/{pid}/documents", headers=headers)).json()
    assert [d["kind"] for d in listed["items"]].count("DECISION_PROTOCOL") == 1
    second = (await async_client.post(url(pid), headers=headers)).json()
    gone = await async_client.post(url(pid, f"/{second['id']}/archive"), headers=headers)
    assert gone.status_code == 200 and gone.json()["status"] == "ARCHIVED"
    assert (await async_client.patch(url(pid, f"/{second['id']}"), json={"notes": "x"}, headers=headers)).status_code == 409
    assert (await async_client.get(url(pid), headers=headers)).json()["total"] == 2
    preview = await async_client.post(f"/api/projects/{pid}/documents/decision/preview", headers=headers)
    assert preview.status_code == 200 and preview.json()["sent"] is True


# --- the registry and the migration ------------------------------------------------------------------------------------------------------------


def test_the_kind_has_its_template_and_its_own_number_prefix():
    template = TEMPLATES[DocumentKind.DECISION_PROTOCOL]
    assert (template.file, template.version, template.number_prefix) == ("decision_protocol.html.j2", "1", "DECYZ")
    prefixes = [tpl.number_prefix for tpl in TEMPLATES.values() if tpl.number_prefix]
    assert len(prefixes) == len(set(prefixes))


def test_revision_chain_and_length():
    module = load_migration("0052_decision_protocols")
    assert module.revision == "0052_decision_protocols" and module.down_revision == "0051_final_protocol_kind" and len(module.revision) <= 32


def engine_0052():
    engine = contract_engine()
    for name in ("0045_contract_issue", "0046_contract_signed", "0047_handover_protocols", "0048_handover_issue", "0049_concealed_works",
                 "0050_acceptance_protocols", "0051_final_protocol_kind", "0052_decision_protocols"):
        run(engine, name, "upgrade")
    return engine


ROW = ("INSERT INTO decision_protocols (id, owner_id, project_id, sequence, status, attendees, items, understood, signature_refused, issued_at, "
       "snapshot, document_html, created_at, updated_at) VALUES (:id, 'u1', 'p1', :sequence, :status, '[]', '[]', 0, 0, :issued, :snapshot, :html, "
       "'2026-10-11', '2026-10-11')")
JOURNAL = ("INSERT INTO issued_documents (id, owner_id, project_id, kind, title, number, project_seq, template_version, status, issued_at) "
           "VALUES (:id, 'u1', 'p1', :kind, 't', :number, :seq, '1', 'SENT', '2026-10-10')")
BLANK = {"issued": None, "snapshot": None, "html": None}
FROZEN = {"issued": "2026-10-11", "snapshot": "{}", "html": "<html></html>"}


def test_the_database_allows_one_draft_a_number_once_known_states_a_frozen_issued_protocol_and_the_new_journal_kind():
    engine = engine_0052()
    with engine.begin() as conn:
        conn.execute(text(ROW), {"id": "a", "sequence": 1, "status": "DRAFT", **BLANK})
        conn.execute(text(ROW), {"id": "b", "sequence": 2, "status": "ARCHIVED", **BLANK})
        conn.execute(text(ROW), {"id": "c", "sequence": 3, "status": "ISSUED", **FROZEN})
        conn.execute(text(JOURNAL), {"id": "j", "kind": "DECISION_PROTOCOL", "number": "DECYZ/1", "seq": 1})
    for bad in (
        {"id": "d", "sequence": 4, "status": "DRAFT", **BLANK}, {"id": "e", "sequence": 1, "status": "ARCHIVED", **BLANK},
        {"id": "f", "sequence": 5, "status": "SIGNED", **BLANK}, {"id": "g", "sequence": 0, "status": "ARCHIVED", **BLANK},
        {"id": "h", "sequence": 6, "status": "ISSUED", **BLANK},
    ):
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(text(ROW), bad)
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text(JOURNAL), {"id": "l", "kind": "OTHER", "number": "X/1", "seq": 2})
    assert {c["name"] for c in inspect(engine).get_columns("decision_protocols")} == {c.name for c in DecisionProtocol.__table__.columns}


def test_downgrade_refuses_while_a_protocol_or_a_journal_row_exists_and_then_works():
    engine = engine_0052()
    with engine.begin() as conn:
        conn.execute(text(ROW), {"id": "a", "sequence": 1, "status": "DRAFT", **BLANK})
    with pytest.raises(RuntimeError, match="1 decision protocol"):
        run(engine, "0052_decision_protocols", "downgrade")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM decision_protocols"))
        conn.execute(text(JOURNAL), {"id": "j", "kind": "DECISION_PROTOCOL", "number": "DECYZ/1", "seq": 1})
    with pytest.raises(RuntimeError, match="1 journal row"):
        run(engine, "0052_decision_protocols", "downgrade")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM issued_documents"))
    run(engine, "0052_decision_protocols", "downgrade")
    assert "decision_protocols" not in inspect(engine).get_table_names() and "acceptance_protocols" in inspect(engine).get_table_names()
    run(engine, "0052_decision_protocols", "upgrade")
