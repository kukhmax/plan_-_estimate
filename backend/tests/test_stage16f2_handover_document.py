"""Stage 16F.2: the protocol of handing over the premises as a document -- the page, the working version, issuing and freezing, the
journal, the HTTP API and the migration."""
import io
import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from pypdf import PdfReader
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.domain.contracts.catalog import load_contract_catalog
from app.domain.documents.handover_document import build_handover_document, render_handover_html
from app.domain.documents.renderer import DocumentRenderer
from app.domain.exceptions import DocumentDataError, HandoverGateError, HandoverNotEditableError
from app.domain.protocols.sources import load_handover_sources
from app.domain.services.handover_service import HandoverService, _data
from app.models.handover_protocol import HandoverProtocol
from app.models.project import Project
from tests.test_stage15f2_api import use_issuer  # noqa: F401  (a fixture)
from tests.test_stage15f2_issuing import Delivery, issuer, journal, text_of, user_of
from tests.test_stage16e2_contract import OWNER_TG, STRANGER_TG, contract_engine, load_migration, login, ready, run
from tests.test_stage16e4_signing import issued

TODAY = date(2026, 10, 20)
KEYS = [r.key for r in load_contract_catalog().requirements.items]


def met(**exceptions):
    entries = {k: {"state": "YES"} for k in KEYS}
    entries.update(exceptions)
    return entries


async def complete(db, telegram_id, *, decision="HANDED_OVER", requirements=None):
    """A world with an issued contract and a draft protocol that passes the gate."""
    w, owner_id, project_id, contract_id = await issued(db, telegram_id)
    service = HandoverService(db)
    draft, _ = await service.open_draft(project_id, owner_id)
    await service.update(project_id, draft.id, owner_id, {
        "held_on": TODAY, "held_time": "09:30", "attendees": [{"person_id": str(w.person.id)}, {"name": "Jan Sąsiad", "role": "administrator"}],
        "meters": "woda 123,4 m³", "notes": "Klucze odebrane.",
        "rooms": {str(w.salon.id): {"requirements": requirements or met(), "damages": "Rysa nad oknem (zdjęcie 12)", "decision": decision}}})
    return w, owner_id, project_id, draft.id


async def built(db, w, owner_id, project_id, *, working=False, number="PRZEK/2026/10/20/0930", draft_id=None):
    sources = await load_handover_sources(db, owner_id, project_id)
    row = await db.get(HandoverProtocol, draft_id) if draft_id else None
    data = _data(row) if row else {}
    return build_handover_document(data, sources, working=working, issued_on=TODAY, number=None if working else number, sequence=1), sources, data


# --- the page ---------------------------------------------------------------------------------------------------------------------


async def test_the_page_prints_the_day_the_people_the_requirements_with_the_contracts_numbers_and_the_decision(db_session):
    w, owner_id, project_id, hid = await complete(db_session, 9961, decision="CONDITIONAL", requirements=met(
        lighting_level={"state": "NO", "value": 120, "note": "tylko lampa budowlana"}, temperature_range={"state": "CONDITIONAL", "value": {"min": 8, "max": 12}}))
    document, _, _ = await built(db_session, w, owner_id, project_id, draft_id=hid)
    html = render_handover_html(document)
    body = html[html.index("<body"):]
    assert document.held == "20.10.2026, 09:30" and [a.name for a in document.attendees] == ["Anna Nowak", "Jan Sąsiad"]
    assert "Pomieszczenie: Salon" in body and "Stałe oświetlenie elektryczne w pomieszczeniach" in body
    (lighting,) = [line for line in document.rooms[0].lines if line.text.startswith("Minimalne natężenie")]
    assert lighting.required == "300\xa0lx" and lighting.found == "120\xa0lx" and lighting.note == "tylko lampa budowlana"
    assert [o.label for o in lighting.states if o.checked] == ["niespełnione"]
    assert "Rysa nad oknem (zdjęcie 12)" in body and "woda 123,4 m³" in body and "Klucze odebrane." in body
    assert [o.label.split(" (")[0] for o in document.rooms[0].decisions if o.checked] == ["Pomieszczenie przekazane warunkowo"]
    assert "☒&nbsp;warunkowo" in body and "§ 8 ust. 4 i § 17 Umowy" in body
    assert 'class="watermark' not in body and "wersja 1" in body and "PRZEK/2026/10/20/0930" in body  # an issued protocol has no watermark
    assert document.summary == (("Salon", "Pomieszczenie przekazane warunkowo (niespełnione wymagania wpisano powyżej; zob. § 8 ust. 4 i § 17 Umowy)"),)


async def test_only_the_rooms_of_the_protocol_are_printed_in_the_issued_one_and_all_rooms_in_the_working_version(db_session):
    w, owner_id, project_id, hid = await complete(db_session, 9962)
    from app.models.room import Room

    db_session.add(Room(project_id=project_id, name="Łazienka"))
    await db_session.commit()
    issued_doc, _, _ = await built(db_session, w, owner_id, project_id, draft_id=hid)
    working, _, _ = await built(db_session, w, owner_id, project_id, working=True, draft_id=hid)
    assert [r.name for r in issued_doc.rooms] == ["Salon"] and [r.name for r in working.rooms] == ["Salon", "Kuchnia", "Łazienka"]
    assert all(not any(o.checked for o in line.states) for line in working.rooms[2].lines)  # the room not recorded yet: empty boxes
    assert any(o.checked for o in working.rooms[0].lines[0].states)  # a recorded one keeps its findings


async def test_the_working_version_never_refuses_is_a_blank_form_and_cannot_be_numbered(db_session):
    w = await ready(db_session, telegram_id=9963)
    sources = await load_handover_sources(db_session, w.owner.id, w.project.id)
    document = build_handover_document({}, sources, working=True, issued_on=TODAY)
    html = render_handover_html(document)
    body = html[html.index("<body"):]
    assert document.layout.draft and document.layout.light_watermark and document.layout.meta.number is None
    assert [r.name for r in document.rooms] == ["Salon", "Kuchnia"]  # the object's own rooms
    assert 'class="watermark light"' in body and body.count("☐") > 20 and "Obecni: do wpisania." in body and body.count('class="write-line"') >= 6
    with pytest.raises(DocumentDataError) as numbered:
        build_handover_document({}, sources, working=True, issued_on=TODAY, number="PRZEK/1")
    assert numbered.value.reason == "DRAFT_NUMBERED"
    sources.executor = None
    assert build_handover_document({}, sources, working=True, issued_on=TODAY)  # a blank form needs no profile
    with pytest.raises(DocumentDataError) as no_profile:
        build_handover_document({}, sources, working=False, issued_on=TODAY)
    assert no_profile.value.reason == "EXECUTOR_PROFILE_REQUIRED"


async def test_a_real_pdf_with_the_number_on_every_page(db_session):
    w, owner_id, project_id, hid = await complete(db_session, 9964)
    document, _, _ = await built(db_session, w, owner_id, project_id, draft_id=hid)
    pdf = (await DocumentRenderer().render(render_handover_html(document))).pdf
    pages = PdfReader(io.BytesIO(pdf)).pages
    assert len(pages) >= 1 and all("PRZEK/2026/10/20/0930" in page.extract_text() for page in pages)
    flat = " ".join(text_of(pdf).split())
    for part in ("Protokół przekazania pomieszczeń", "Pomieszczenie: Salon", "Anna Nowak", "ul. Zielona 5/7"):
        assert part in flat, part


# --- the gate and the freeze -------------------------------------------------------------------------------------------------------


async def test_a_protocol_that_is_not_ready_is_refused_with_the_list_and_takes_no_number(db_session):
    w, owner_id, project_id, contract_id = await issued(db_session, 9965)
    draft, _ = await HandoverService(db_session).open_draft(project_id, owner_id)
    run_ = issuer(delivery=Delivery())
    with pytest.raises(HandoverGateError) as refused:
        await run_.start_handover(db_session, await user_of(db_session, owner_id), project_id, draft.id)
    assert [b.code for b in refused.value.blockers] == ["HELD_ON_REQUIRED", "NO_ATTENDEES", "NO_ROOMS"]
    assert await journal(db_session) == [] or all(j.kind != "HANDOVER_PROTOCOL" for j in await journal(db_session))
    w2 = await ready(db_session, telegram_id=9966)  # only a draft contract: nothing to hand over against
    other, _ = await HandoverService(db_session).open_draft(w2.project.id, w2.owner.id)
    with pytest.raises(HandoverGateError) as no_contract:
        await run_.start_handover(db_session, await user_of(db_session, w2.owner.id), w2.project.id, other.id)
    assert no_contract.value.blockers[0].code == "CONTRACT_REQUIRED"


async def test_issuing_freezes_the_protocol_numbers_it_sends_the_pdf_and_records_it(db_session):
    w, owner_id, project_id, hid = await complete(db_session, 9967)
    telegram, salon = w.owner.telegram_user_id, str(w.salon.id)
    sender = Delivery()
    run_ = issuer(delivery=sender)
    reservation = await run_.start_handover(db_session, await user_of(db_session, owner_id), project_id, hid)
    assert (reservation.document.kind, reservation.document.status, reservation.document.source_id, reservation.document.source_version) == (
        "HANDOVER_PROTOCOL", "PENDING", hid, 1)
    assert reservation.document.number.startswith("PRZEK/2026/10/08/")
    await run_.drain()
    done = [j for j in await journal(db_session) if j.kind == "HANDOVER_PROTOCOL"][0]
    assert (done.status, done.error_code, done.title) == ("SENT", None, "Protokół przekazania pomieszczeń — nr 1")
    number = done.number
    (message,) = sender.sent[-1:]
    assert message["chat_id"] == telegram and message["filename"].startswith("PRZEK-2026-10-08-")
    assert message["caption"].startswith("Protokół przekazania pomieszczeń — nr 1 — Mokotów\nPRZEK/") and number in text_of(message["pdf"])
    db_session.expire_all()
    row = await db_session.get(HandoverProtocol, hid)
    assert row.status == "ISSUED" and row.issued_at is not None and row.contract_version == 1 and row.contract_id is not None
    assert number in row.document_html
    snap = row.snapshot
    assert snap["held_on"] == "2026-10-20" and snap["contract"]["version"] == 1 and snap["contract"]["number"].startswith("UMOWA/")
    assert snap["required_values"]["lighting_level"] == 300 and snap["room_names"] == {salon: "Salon"}
    assert [a["name"] for a in snap["attendees"]] == ["Anna Nowak", "Jan Sąsiad"] and snap["client"] == "Anna Nowak" or snap["client"]
    with pytest.raises(HandoverNotEditableError):  # frozen: a changed protocol is a new one
        await HandoverService(db_session).update(project_id, hid, owner_id, {"notes": "późno"})
    with pytest.raises(HandoverNotEditableError):
        await run_.start_handover(db_session, await user_of(db_session, owner_id), project_id, hid)
    with pytest.raises(HandoverNotEditableError):  # the service itself refuses to freeze twice
        await HandoverService(db_session).mark_issued(
            project_id, hid, owner_id, issued_at=run_.clock(), snapshot={}, document_html="<html></html>", contract_id=None, contract_version=None)
    again, _ = await HandoverService(db_session).open_draft(project_id, owner_id)  # the next handover is protocol no. 2
    assert again.sequence == 2


async def test_the_issued_page_does_not_change_when_the_data_do(db_session):
    w, owner_id, project_id, hid = await complete(db_session, 9968)
    owner_tg = w.owner.telegram_user_id
    run_ = issuer(delivery=Delivery())
    await run_.start_handover(db_session, await user_of(db_session, owner_id), project_id, hid)
    await run_.drain()
    frozen = (await db_session.get(HandoverProtocol, hid)).document_html
    project = (await db_session.execute(select(Project).where(Project.id == project_id))).scalar_one()
    project.name = "Zupełnie inna nazwa"
    w.person.name = "Ktoś Inny"
    await db_session.commit()
    row = [j for j in await journal(db_session) if j.kind == "HANDOVER_PROTOCOL"][0]
    again = await run_._render(db_session, row)  # the same document, made again
    assert (await db_session.get(HandoverProtocol, hid)).document_html == frozen and owner_tg
    flat = text_of(again.pdf)
    assert "Anna Nowak" in flat and "Zupełnie inna nazwa" not in flat and "Ktoś Inny" not in flat


async def test_the_preview_follows_the_draft_and_never_leaves_a_row(db_session):
    w, owner_id, project_id, hid = await complete(db_session, 9969)
    sender = Delivery()
    before = len(await journal(db_session))
    result = await issuer(delivery=sender).preview_handover(db_session, await user_of(db_session, owner_id), project_id)
    assert result.pages >= 1
    message = sender.sent[-1]
    assert message["filename"] == "Protokol-przekazania-wersja-robocza.pdf" and message["caption"] == "WERSJA ROBOCZA — Protokół przekazania pomieszczeń — Mokotów"
    flat = " ".join(text_of(message["pdf"]).split())
    assert "WERSJA ROBOCZA" in flat and "Jan Sąsiad" in flat and "Rysa nad oknem" in flat
    assert len(await journal(db_session)) == before


# --- HTTP -------------------------------------------------------------------------------------------------------------------------


def url(project_id, tail=""):
    return f"/api/projects/{project_id}/handovers{tail}"


async def test_the_routes_issue_refuse_and_preview(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w, owner_id, project_id, hid = await complete(db_session, OWNER_TG)
    sender = Delivery()
    run_ = use_issuer(issuer(delivery=sender))
    headers = await login(async_client)
    pid = str(project_id)
    assert (await async_client.post(url(pid, f"/{hid}/issue"))).status_code == 401
    assert (await async_client.post(f"/api/projects/{pid}/documents/handover/preview")).status_code == 401
    preview = await async_client.post(f"/api/projects/{pid}/documents/handover/preview", headers=headers)
    assert preview.status_code == 200 and preview.json()["sent"] is True
    await async_client.patch(url(pid, f"/{hid}"), json={"held_on": None}, headers=headers)
    blocked = await async_client.post(url(pid, f"/{hid}/issue"), headers=headers)
    assert blocked.status_code == 422 and blocked.json()["detail"]["code"] == "HANDOVER_GATE_BLOCKED"
    assert [b["code"] for b in blocked.json()["detail"]["details"]["blockers"]] == ["HELD_ON_REQUIRED"]
    await async_client.patch(url(pid, f"/{hid}"), json={"held_on": "2026-10-20"}, headers=headers)
    ok = await async_client.post(url(pid, f"/{hid}/issue"), headers=headers)
    assert ok.status_code == 202, ok.text
    assert ok.json()["kind"] == "HANDOVER_PROTOCOL" and ok.json()["number"].startswith("PRZEK/") and ok.json()["source_id"] == str(hid)
    await run_.drain()
    again = await async_client.post(url(pid, f"/{hid}/issue"), headers=headers)
    assert again.status_code == 409 and again.json()["detail"]["code"] == "HANDOVER_NOT_EDITABLE"
    listed = (await async_client.get(f"/api/projects/{pid}/documents", headers=headers)).json()
    assert [d["kind"] for d in listed["items"]].count("HANDOVER_PROTOCOL") == 1


async def test_a_stranger_gets_404_on_issue_and_preview(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    await ready(db_session, telegram_id=OWNER_TG)
    theirs = await ready(db_session, telegram_id=STRANGER_TG)
    use_issuer(issuer(delivery=Delivery()))
    headers = await login(async_client)
    draft, _ = await HandoverService(db_session).open_draft(theirs.project.id, theirs.owner.id)
    assert (await async_client.post(url(theirs.project.id, f"/{draft.id}/issue"), headers=headers)).status_code == 404
    assert (await async_client.post(f"/api/projects/{theirs.project.id}/documents/handover/preview", headers=headers)).status_code == 404


# --- migration --------------------------------------------------------------------------------------------------------------------


def test_revision_chain_and_length():
    module = load_migration("0048_handover_issue")
    assert module.revision == "0048_handover_issue" and module.down_revision == "0047_handover_protocols" and len(module.revision) <= 32


def engine_0048():
    engine = contract_engine()
    for name in ("0045_contract_issue", "0046_contract_signed", "0047_handover_protocols", "0048_handover_issue"):
        run(engine, name, "upgrade")
    return engine


ROW = ("INSERT INTO handover_protocols (id, owner_id, project_id, sequence, status, attendees, rooms, issued_at, snapshot, document_html, created_at, updated_at) "
       "VALUES (:id, 'u1', 'p1', :sequence, :status, '[]', '{}', :issued, :snapshot, :html, '2026-10-10', '2026-10-10')")
JOURNAL = ("INSERT INTO issued_documents (id, owner_id, project_id, kind, title, number, project_seq, template_version, status, issued_at) "
           "VALUES (:id, 'u1', 'p1', :kind, 't', :number, :seq, '1', 'SENT', '2026-10-10')")
FROZEN = {"issued": "2026-10-10", "snapshot": "{}", "html": "<html></html>"}
BLANK = {"issued": None, "snapshot": None, "html": None}


def test_the_database_refuses_an_issued_protocol_without_its_snapshot_and_page_and_knows_the_new_kind():
    engine = engine_0048()
    with engine.begin() as conn:
        conn.execute(text(ROW), {"id": "a", "sequence": 1, "status": "DRAFT", **BLANK})
        conn.execute(text(ROW), {"id": "b", "sequence": 2, "status": "ARCHIVED", **BLANK})
        conn.execute(text(ROW), {"id": "c", "sequence": 3, "status": "ISSUED", **FROZEN})
        conn.execute(text(JOURNAL), {"id": "j", "kind": "HANDOVER_PROTOCOL", "number": "PRZEK/1", "seq": 1})
    for bad in ({"id": "d", "sequence": 4, "status": "ISSUED", **BLANK}, {"id": "e", "sequence": 5, "status": "ISSUED", **{**FROZEN, "html": None}},
                {"id": "f", "sequence": 6, "status": "ISSUED", **{**FROZEN, "snapshot": None}}):
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(text(ROW), bad)
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text(JOURNAL), {"id": "k", "kind": "OTHER", "number": "X/1", "seq": 2})
    assert {c["name"] for c in inspect(engine).get_columns("handover_protocols")} == {c.name for c in HandoverProtocol.__table__.columns}


def test_downgrade_refuses_while_an_issued_protocol_or_a_journal_row_exists_and_then_works():
    engine = engine_0048()
    with engine.begin() as conn:
        conn.execute(text(ROW), {"id": "c", "sequence": 1, "status": "ISSUED", **FROZEN})
    with pytest.raises(RuntimeError, match="1 issued protocol"):
        run(engine, "0048_handover_issue", "downgrade")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM handover_protocols"))
        conn.execute(text(JOURNAL), {"id": "j", "kind": "HANDOVER_PROTOCOL", "number": "PRZEK/1", "seq": 1})
    with pytest.raises(RuntimeError, match="1 protocol journal row"):
        run(engine, "0048_handover_issue", "downgrade")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM issued_documents"))
        conn.execute(text(ROW), {"id": "d", "sequence": 1, "status": "DRAFT", **BLANK})
    run(engine, "0048_handover_issue", "downgrade")
    assert {"issued_at", "snapshot", "document_html", "contract_id", "contract_version"}.isdisjoint(
        {c["name"] for c in inspect(engine).get_columns("handover_protocols")})
    run(engine, "0048_handover_issue", "upgrade")


async def test_an_archived_room_is_not_offered_but_stays_in_a_protocol_that_recorded_it(db_session):
    from app.domain.exceptions import HandoverInvalidError
    from app.models.room import Room

    w, owner_id, project_id, hid = await complete(db_session, 9970)
    kitchen = next(r for r in (await db_session.execute(select(Room).where(Room.project_id == project_id))).scalars() if r.name == "Kuchnia")
    kitchen.is_archived = True
    await db_session.commit()
    working, _, _ = await built(db_session, w, owner_id, project_id, working=True, draft_id=hid)
    assert [r.name for r in working.rooms] == ["Salon"]  # the blank form does not offer an archived room
    with pytest.raises(HandoverInvalidError) as refused:  # and nothing new can be recorded for it
        await HandoverService(db_session).update(project_id, hid, owner_id, {"rooms": {str(kitchen.id): {"decision": "HANDED_OVER"}}})
    assert refused.value.reason == "UNKNOWN_ROOM"
    salon = next(r for r in (await db_session.execute(select(Room).where(Room.project_id == project_id))).scalars() if r.name == "Salon")
    salon.is_archived = True  # a room archived after it was recorded keeps its place in the protocol
    await db_session.commit()
    kept, _, _ = await built(db_session, w, owner_id, project_id, draft_id=hid)
    assert [r.name for r in kept.rooms] == ["Salon"]
