"""Stage 16H.2: the acceptance protocol as a document -- the page, the working version, the real PDF, the gate and the freeze, issuing,
the API and the migration of the journal kind."""
import io
import uuid
from datetime import date

import pytest
from httpx import AsyncClient
from pypdf import PdfReader
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.domain.documents import registry
from app.domain.documents.acceptance_document import build_acceptance_document, render_acceptance_html
from app.domain.documents.registry import TEMPLATES, DocumentKind
from app.domain.documents.renderer import DocumentRenderer
from app.domain.exceptions import AcceptanceGateError, AcceptanceNotEditableError
from app.domain.protocols.sources import load_acceptance_sources
from app.domain.services.acceptance_service import AcceptanceService, data_of
from app.models.acceptance_protocol import AcceptanceProtocol
from app.models.checklist import QualityLevel
from app.models.project import Project
from app.models.surface import Surface, SurfaceType
from tests.test_stage15f2_api import use_issuer  # noqa: F401  (a fixture)
from tests.test_stage15f2_issuing import Delivery, issuer, journal, text_of, user_of
from tests.test_stage16c_tech_card import plan
from tests.test_stage16e2_contract import OWNER_TG, STRANGER_TG, contract_engine, load_migration, login, ready, run
from tests.test_stage16e4_signing import issued
from tests.test_stage16h1_acceptance import complete_works, defect_photo

TODAY = date(2026, 10, 20)
NUMBER = "ODBIOR/2026/10/20/1000"
RID = str(uuid.uuid4())


def svc(db):
    return AcceptanceService(db)


async def record(db, w, owner_id, project_id, *, finished=True, absent=False, remarks=True, extra=None):
    """A draft that passes the gate: the salon in scope, the wall assessed, one removable remark with a photo of the defect."""
    if finished:
        await complete_works(db, w)
    photo = await defect_photo(db, w, w.wall.id, caption="Smuga po gładzi")
    draft, _ = await svc(db).open_draft(project_id, owner_id)
    wall = {"assessed": True}
    if remarks:
        wall["remarks"] = {RID: {"place": "Narożnik przy oknie", "description": "Smuga widoczna w świetle bocznym", "classification": "REMOVABLE",
                                 "deadline": date(2026, 10, 25), "photo_ids": [photo]}}
    changes = {"room_ids": [str(w.salon.id)], "held_on": TODAY, "held_time": "10:00", "instrument_keys": ["raking_light", "moisture_meter"],
               "surfaces": {str(w.wall.id): wall}, "batches": "Gładź L77/3", "instructions_given": True, "amount_due": "2000", "amount_retained": "300,5",
               "notes": "Klucze oddane"}
    if absent:
        changes.update(customer_absent=True, notified_on=date(2026, 10, 14), renotified_on=date(2026, 10, 17))
    else:
        changes["attendees"] = [{"person_id": str(w.person.id)}, {"name": "Jan Sąsiad", "role": "administrator"}]
    changes.update(extra or {})
    await svc(db).update(project_id, draft.id, owner_id, changes)
    return draft.id, photo


async def world(db, telegram_id, **kw):
    w, owner_id, project_id, contract_id = await issued(db, telegram_id)
    hid, photo = await record(db, w, owner_id, project_id, **kw)
    return w, owner_id, project_id, hid, photo


async def build(db, owner_id, project_id, hid=None, *, working=False, number=NUMBER):
    sources = await load_acceptance_sources(db, owner_id, project_id)
    row = await db.get(AcceptanceProtocol, hid) if hid else None
    data = data_of(row) if row else {}
    return build_acceptance_document(data, sources, working=working, issued_on=TODAY, number=None if working else number, sequence=1), sources, data


def body_of(document):
    html = render_acceptance_html(document)
    return html[html.index("<body"):]


# --- the page ----------------------------------------------------------------------------------------------------------------------------


async def test_the_page_prints_the_scope_the_conditions_the_remarks_the_derived_result_and_the_settlement(db_session):
    w, owner_id, project_id, hid, photo = await world(db_session, 9701)
    document, _, _ = await build(db_session, owner_id, project_id, hid)
    body = body_of(document)
    facts = {row.label: row.value for row in document.facts}
    assert document.layout.meta.title == "Protokół odbioru końcowego" and facts["Zakres odbioru"].startswith("Odbiór końcowy")
    assert facts["Data i godzina odbioru"] == "20.10.2026, 10:00" and facts["Umowa"].startswith("wersja 1, nr UMOWA/")
    assert [(c.key, c.text.startswith("Ocena wizualna przy oświetleniu rozproszonym")) for c in document.conditions] == [("S2", True)]
    assert document.instruments == ("Lampa światła smugowego (oświetlenie boczne)", "Wilgotnościomierz")
    [block] = document.surfaces
    assert block.heading == "Salon — Ściana A" and block.standard == "S2" and block.result == "Odebrano z uwagami"
    assert [w_.status for w_ in block.works] == ["wykonana"] * len(block.works)
    [remark] = document.remarks
    assert (remark.number, remark.surface, remark.place, remark.classification, remark.deadline) == (
        1, "Salon — Ściana A", "Narożnik przy oknie", "Do usunięcia — odbiór z uwagami", "25.10.2026")
    assert remark.photos == photo[:8] and {item.name for item in document.legend} == {"Do usunięcia — odbiór z uwagami", "Istotne — brak odbioru"}
    assert [o.label for o in document.results if o.checked] == ["Odebrano z uwagami"] and len(document.results) == 3
    assert [(r.label, r.value) for r in document.settlement] == [
        ("Kwota należna za odebrany zakres", "2\xa0000,00\xa0zł"), ("Kwota zatrzymana do czasu usunięcia uwag", "300,50\xa0zł"),
        ("Numery partii materiałów", "Gładź L77/3")]
    assert document.instructions.checked and document.notes == "Klucze oddane" and document.absent_text is None
    assert "Jan Sąsiad" in body and NUMBER in body and 'class="watermark' not in body and "☒&nbsp;Odebrano z uwagami" in body
    assert "Smuga widoczna w świetle bocznym" in body and "Zakres" in body and body.count("☒") == 2  # the result and the instructions


async def test_unfinished_works_or_a_significant_remark_print_not_accepted(db_session):
    w, owner_id, project_id, hid, _ = await world(db_session, 9702, finished=False, remarks=False)
    document, _, _ = await build(db_session, owner_id, project_id, hid)
    [block] = document.surfaces
    assert block.result == "Nie odebrano" and {x.status for x in block.works} == {"niewykonana"}
    assert [o.label for o in document.results if o.checked] == ["Nie odebrano"] and document.remarks == ()
    assert "Bez uwag i zastrzeżeń." in body_of(document)
    w2, owner2, project2, hid2, _ = await world(db_session, 9703)
    await svc(db_session).update(project2, hid2, owner2, {"surfaces": {str(w2.wall.id): {"assessed": True, "remarks": {RID: {"classification": "SIGNIFICANT"}}}}})
    document2, _, _ = await build(db_session, owner2, project2, hid2)
    assert [o.label for o in document2.results if o.checked] == ["Nie odebrano"] and document2.remarks[0].classification == "Istotne — brak odbioru"
    assert document2.remarks[0].deadline is not None  # the earlier deadline of the same remark is kept


async def test_a_partial_acceptance_names_the_rooms_and_a_complete_one_is_final(db_session):
    w, owner_id, project_id, contract_id = await issued(db_session, 9704)
    kitchen_wall = Surface(room_id=w.kuchnia.id, name="Ściana K", surface_type=SurfaceType.WALL)
    db_session.add(kitchen_wall)
    await db_session.commit()
    await plan(db_session, kitchen_wall, [w.item_a], quality=QualityLevel.Q4)
    hid, _ = await record(db_session, w, owner_id, project_id, remarks=False)
    document, _, _ = await build(db_session, owner_id, project_id, hid)
    assert document.layout.meta.title == "Protokół odbioru częściowego" and document.facts[1].value == "Odbiór częściowy — pomieszczenia: Salon"
    assert [b.heading for b in document.surfaces] == ["Salon — Ściana A"]
    await svc(db_session).update(project_id, hid, owner_id, {"room_ids": [str(w.salon.id), str(w.kuchnia.id)]})
    document, _, _ = await build(db_session, owner_id, project_id, hid)
    assert document.layout.meta.title == "Protokół odbioru końcowego" and [b.heading for b in document.surfaces] == ["Salon — Ściana A", "Kuchnia — Ściana K"]
    assert [c.key for c in document.conditions] == ["S2", "Q4"] and [b.standard for b in document.surfaces] == ["S2", "Q4"]


async def test_an_absent_customer_was_called_twice_and_the_page_says_when(db_session):
    w, owner_id, project_id, hid, _ = await world(db_session, 9705, absent=True)
    document, _, _ = await build(db_session, owner_id, project_id, hid)
    body = body_of(document)
    assert document.absent_text == (
        "Zamawiający ani Osoba upoważniona nie stawili się w terminie wskazanym w zawiadomieniu z dnia 14.10.2026, ani w dodatkowym terminie "
        "wskazanym w ponownym zawiadomieniu z dnia 17.10.2026. Protokół jednostronny (zob. § 14 ust. 5 Umowy).")
    assert document.absent_text in body and document.attendees == () and "Obecni: do wpisania." not in body


async def test_the_working_version_is_a_blank_form_that_never_refuses_and_cannot_be_numbered(db_session):
    w = await ready(db_session, telegram_id=9706)
    document, sources, _ = await build(db_session, w.owner.id, w.project.id, working=True)
    body = body_of(document)
    assert document.layout.draft and document.layout.light_watermark and document.layout.meta.number is None
    assert document.layout.meta.title == "Protokół odbioru prac" and 'class="watermark light"' in body
    assert len(document.remarks) == 6 and len(document.surfaces) == 4 and body.count("☐") == 4 and body.count("☒") == 0
    assert body.count('class="write-line"') >= 14 and "Obecni: do wpisania." in body and "wpisz daty zawiadomienia" in body
    assert document.settlement[0].value is None and not document.instructions.checked
    with pytest.raises(Exception) as numbered:
        build_acceptance_document({}, sources, working=True, issued_on=TODAY, number="ODBIOR/1")
    assert numbered.value.reason == "DRAFT_NUMBERED"
    sources.base.executor = None
    assert build_acceptance_document({}, sources, working=True, issued_on=TODAY)
    with pytest.raises(Exception) as no_profile:
        build_acceptance_document({}, sources, working=False, issued_on=TODAY)
    assert no_profile.value.reason == "EXECUTOR_PROFILE_REQUIRED"


async def test_a_real_pdf_with_the_number_on_every_page(db_session):
    w, owner_id, project_id, hid, _ = await world(db_session, 9707)
    document, _, _ = await build(db_session, owner_id, project_id, hid)
    pdf = (await DocumentRenderer().render(render_acceptance_html(document))).pdf
    pages = PdfReader(io.BytesIO(pdf)).pages
    assert len(pages) >= 1 and all(NUMBER in page.extract_text() for page in pages)
    flat = " ".join(text_of(pdf).split())
    for part in ("Protokół odbioru końcowego", "Narożnik przy oknie", "Anna Nowak", "Odebrano z uwagami", "Wilgotnościomierz", "ul. Zielona 5/7"):
        assert part in flat, part


# --- the gate and the freeze ---------------------------------------------------------------------------------------------------------------


async def test_a_protocol_that_is_not_ready_is_refused_with_the_list_and_takes_no_number(db_session):
    w, owner_id, project_id, contract_id = await issued(db_session, 9708)
    draft, _ = await svc(db_session).open_draft(project_id, owner_id)
    run_ = issuer(delivery=Delivery())
    with pytest.raises(AcceptanceGateError) as refused:
        await run_.start_acceptance(db_session, await user_of(db_session, owner_id), project_id, draft.id)
    assert [b.code for b in refused.value.blockers] == ["SCOPE_REQUIRED", "HELD_ON_REQUIRED", "NO_ATTENDEES"]
    assert all(j.kind != "FINAL_PROTOCOL" for j in await journal(db_session))
    w2 = await ready(db_session, telegram_id=9709)  # only a draft contract: no contract to work under
    other, _ = await svc(db_session).open_draft(w2.project.id, w2.owner.id)
    with pytest.raises(AcceptanceGateError) as no_contract:
        await run_.start_acceptance(db_session, await user_of(db_session, w2.owner.id), w2.project.id, other.id)
    assert "CONTRACT_REQUIRED" in [b.code for b in no_contract.value.blockers]


async def test_issuing_freezes_the_protocol_numbers_it_sends_the_pdf_and_records_it(db_session):
    w, owner_id, project_id, hid, photo = await world(db_session, 9710)
    telegram = w.owner.telegram_user_id
    sender = Delivery()
    run_ = issuer(delivery=sender)
    reservation = await run_.start_acceptance(db_session, await user_of(db_session, owner_id), project_id, hid)
    assert (reservation.document.kind, reservation.document.status, reservation.document.source_id, reservation.document.source_version) == (
        "FINAL_PROTOCOL", "PENDING", hid, 1)
    assert reservation.document.number.startswith("ODBIOR/2026/10/08/")
    await run_.drain()
    done = [j for j in await journal(db_session) if j.kind == "FINAL_PROTOCOL"][0]
    number = done.number
    assert (done.status, done.error_code, done.title) == ("SENT", None, "Protokół odbioru końcowego — nr 1")
    message = sender.sent[-1]
    assert message["chat_id"] == telegram and message["filename"].startswith("ODBIOR-2026-10-08-")
    assert message["caption"].startswith("Protokół odbioru końcowego — nr 1 — Mokotów\nODBIOR/") and number in text_of(message["pdf"])
    db_session.expire_all()
    row = await db_session.get(AcceptanceProtocol, hid)
    assert row.status == "ISSUED" and row.issued_at is not None and row.contract_version == 1 and row.contract_id is not None and number in row.document_html
    snap = row.snapshot
    assert (snap["scope_kind"], snap["result"], snap["held_on"], snap["customer_absent"], snap["amount_due"], snap["amount_retained"]) == (
        "FINAL", "ACCEPTED_WITH_REMARKS", "2026-10-20", False, "2000.00", "300.50")
    [surface] = snap["surfaces"]
    assert surface["name"] == "Ściana A" and surface["room_name"] == "Salon" and surface["quality_target"] == "S2" and surface["result"] == "ACCEPTED_WITH_REMARKS"
    assert {x["status"] for x in surface["works"]} == {"COMPLETED"}
    [remark] = surface["remarks"]
    assert (remark["place"], remark["classification"], remark["deadline"]) == ("Narożnik przy oknie", "REMOVABLE", "2026-10-25")
    assert [p["caption"] for p in remark["photos"]] == ["Smuga po gładzi"] and remark["photos"][0]["id"] == photo
    assert snap["conditions"][0]["key"] == "S2" and snap["instrument_keys"] == ["raking_light", "moisture_meter"] and snap["rooms"][0]["name"] == "Salon"
    assert snap["contract"]["version"] == 1 and snap["contract"]["number"].startswith("UMOWA/") and snap["client"] and snap["executor"]
    with pytest.raises(AcceptanceNotEditableError):
        await svc(db_session).update(project_id, hid, owner_id, {"notes": "inne"})
    with pytest.raises(AcceptanceNotEditableError):
        await run_.start_acceptance(db_session, await user_of(db_session, owner_id), project_id, hid)
    with pytest.raises(AcceptanceNotEditableError):  # the service itself refuses to freeze twice
        await svc(db_session).mark_issued(project_id, hid, owner_id, issued_at=run_.clock(), snapshot={}, document_html="<html></html>",
                                          contract_id=None, contract_version=None)
    assert (await svc(db_session).open_draft(project_id, owner_id))[0].sequence == 2


async def test_the_issued_page_does_not_change_when_the_data_do(db_session):
    w, owner_id, project_id, hid, _ = await world(db_session, 9711)
    run_ = issuer(delivery=Delivery())
    await run_.start_acceptance(db_session, await user_of(db_session, owner_id), project_id, hid)
    await run_.drain()
    frozen = (await db_session.get(AcceptanceProtocol, hid)).document_html
    project = (await db_session.execute(select(Project).where(Project.id == project_id))).scalar_one()
    project.name = "Zupełnie inna nazwa"
    w.wall.name = "Inna ściana"
    w.person.name = "Ktoś Inny"
    await db_session.commit()
    row = [j for j in await journal(db_session) if j.kind == "FINAL_PROTOCOL"][0]
    again = await run_._render(db_session, row)
    assert (await db_session.get(AcceptanceProtocol, hid)).document_html == frozen
    flat = text_of(again.pdf)
    assert "Ściana A" in flat and "Anna Nowak" in flat and "Inna ściana" not in flat and "Ktoś Inny" not in flat


async def test_a_journal_row_whose_protocol_has_no_stored_page_is_refused_by_name(db_session):
    w, owner_id, project_id, hid, _ = await world(db_session, 9714)
    run_ = issuer(delivery=Delivery())
    await run_.start_acceptance(db_session, await user_of(db_session, owner_id), project_id, hid)
    await run_.drain()
    row = [j for j in await journal(db_session) if j.kind == "FINAL_PROTOCOL"][0]
    protocol = await db_session.get(AcceptanceProtocol, hid)
    protocol.document_html = ""
    await db_session.commit()
    with pytest.raises(Exception) as empty:
        await run_._render(db_session, row)
    assert empty.value.reason == "ACCEPTANCE_NOT_ISSUED"
    row.source_id = uuid.uuid4()
    with pytest.raises(Exception) as missing:
        await run_._render(db_session, row)
    assert missing.value.reason == "ACCEPTANCE_NOT_ISSUED"


async def test_the_preview_follows_the_draft_and_never_leaves_a_row(db_session):
    w, owner_id, project_id, hid, _ = await world(db_session, 9712)
    sender = Delivery()
    before = len(await journal(db_session))
    result = await issuer(delivery=sender).preview_acceptance(db_session, await user_of(db_session, owner_id), project_id)
    assert result.pages >= 1
    message = sender.sent[-1]
    assert message["filename"] == "Protokol-odbioru-wersja-robocza.pdf" and message["caption"].startswith("WERSJA ROBOCZA — Protokół odbioru końcowego")
    flat = " ".join(text_of(message["pdf"]).split())
    assert "WERSJA ROBOCZA" in flat and "Narożnik przy oknie" in flat and "Gładź L77/3" in flat
    assert len(await journal(db_session)) == before
    blank = Delivery()
    other = await ready(db_session, telegram_id=9713)  # no draft: a blank form
    await issuer(delivery=blank).preview_acceptance(db_session, await user_of(db_session, other.owner.id), other.project.id)
    assert blank.sent[-1]["caption"].startswith("WERSJA ROBOCZA — Protokół odbioru prac")


# --- HTTP ---------------------------------------------------------------------------------------------------------------------------------------


def url(project_id, tail=""):
    return f"/api/projects/{project_id}/acceptances{tail}"


async def test_the_routes_need_a_token_and_a_stranger_gets_404(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    mine = await ready(db_session, telegram_id=OWNER_TG)
    theirs = await ready(db_session, telegram_id=STRANGER_TG)
    use_issuer(issuer(delivery=Delivery()))
    assert (await async_client.post(url(mine.project.id, f"/{uuid.uuid4()}/issue"))).status_code == 401
    assert (await async_client.post(f"/api/projects/{mine.project.id}/documents/acceptance/preview")).status_code == 401
    headers = await login(async_client)
    draft, _ = await svc(db_session).open_draft(theirs.project.id, theirs.owner.id)
    for response in (
        await async_client.post(url(theirs.project.id, f"/{draft.id}/issue"), headers=headers),
        await async_client.post(f"/api/projects/{theirs.project.id}/documents/acceptance/preview", headers=headers),
        await async_client.post(url(mine.project.id, f"/{draft.id}/issue"), headers=headers),
    ):
        assert response.status_code == 404


async def test_record_issue_and_preview_over_http(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w, owner_id, project_id, contract_id = await issued(db_session, OWNER_TG)
    await complete_works(db_session, w)
    sender = Delivery()
    run_ = use_issuer(issuer(delivery=sender))
    headers = await login(async_client)
    pid, salon, wall = str(project_id), str(w.salon.id), str(w.wall.id)
    hid = (await async_client.post(url(pid), headers=headers)).json()["id"]
    blocked = await async_client.post(url(pid, f"/{hid}/issue"), headers=headers)
    assert blocked.status_code == 422 and blocked.json()["detail"]["code"] == "ACCEPTANCE_GATE_BLOCKED"
    assert [b["code"] for b in blocked.json()["detail"]["details"]["blockers"]] == ["SCOPE_REQUIRED", "HELD_ON_REQUIRED", "NO_ATTENDEES"]
    saved = await async_client.patch(url(pid, f"/{hid}"), json={
        "room_ids": [salon], "held_on": "2026-10-20", "attendees": [{"name": "Jan Sąsiad", "role": "administrator"}],
        "surfaces": {wall: {"assessed": True}}}, headers=headers)
    assert saved.status_code == 200, saved.text
    assert saved.json()["blockers"] == [] and saved.json()["result"] == "ACCEPTED"
    ok = await async_client.post(url(pid, f"/{hid}/issue"), headers=headers)
    assert ok.status_code == 202, ok.text
    assert ok.json()["kind"] == "FINAL_PROTOCOL" and ok.json()["number"].startswith("ODBIOR/") and ok.json()["source_id"] == hid
    await run_.drain()
    again = await async_client.post(url(pid, f"/{hid}/issue"), headers=headers)
    assert again.status_code == 409 and again.json()["detail"]["code"] == "ACCEPTANCE_NOT_EDITABLE"
    listed = (await async_client.get(f"/api/projects/{pid}/documents", headers=headers)).json()
    assert [d["kind"] for d in listed["items"]].count("FINAL_PROTOCOL") == 1
    preview = await async_client.post(f"/api/projects/{pid}/documents/acceptance/preview", headers=headers)
    assert preview.status_code == 200 and preview.json()["sent"] is True
    one = await async_client.get(f"/api/projects/{pid}/documents/{ok.json()['id']}", headers=headers)
    assert one.status_code == 200 and one.json()["kind"] == "FINAL_PROTOCOL" and one.json()["status"] == "SENT"


# --- the registry ---------------------------------------------------------------------------------------------------------------------------


def test_every_kind_has_its_own_template_and_the_skeletons_are_gone():
    template = TEMPLATES[DocumentKind.FINAL_PROTOCOL]
    assert (template.file, template.version, template.number_prefix) == ("acceptance_protocol.html.j2", "1", "ODBIOR")
    assert not hasattr(registry, "SKELETON_KINDS") and not hasattr(registry, "SKELETON_FILE")
    templates_dir = registry.__file__.rsplit("/", 1)[0] + "/templates/"
    import os
    for kind, tpl in TEMPLATES.items():
        assert os.path.isfile(templates_dir + tpl.file), (kind, tpl.file)
    assert not os.path.exists(templates_dir + "skeleton.html.j2") and not os.path.exists(registry.__file__.replace("registry", "skeleton_document"))
    assert len({tpl.number_prefix for tpl in TEMPLATES.values() if tpl.number_prefix}) == len([t for t in TEMPLATES.values() if t.number_prefix])


# --- migration ----------------------------------------------------------------------------------------------------------------------------------


def test_revision_chain_and_length():
    module = load_migration("0051_final_protocol_kind")
    assert module.revision == "0051_final_protocol_kind" and module.down_revision == "0050_acceptance_protocols" and len(module.revision) <= 32


def engine_0051():
    engine = contract_engine()
    for name in ("0045_contract_issue", "0046_contract_signed", "0047_handover_protocols", "0048_handover_issue", "0049_concealed_works",
                 "0050_acceptance_protocols", "0051_final_protocol_kind"):
        run(engine, name, "upgrade")
    return engine


JOURNAL = ("INSERT INTO issued_documents (id, owner_id, project_id, kind, title, number, project_seq, template_version, status, issued_at) "
           "VALUES (:id, 'u1', 'p1', :kind, 't', :number, :seq, '1', 'SENT', '2026-10-10')")


def test_the_journal_takes_the_new_kind_and_still_refuses_others_and_the_downgrade_refuses_while_one_exists():
    engine = engine_0051()
    with engine.begin() as conn:
        conn.execute(text(JOURNAL), {"id": "j", "kind": "FINAL_PROTOCOL", "number": "ODBIOR/1", "seq": 1})
        conn.execute(text(JOURNAL), {"id": "k", "kind": "CONCEALED_WORKS_PROTOCOL", "number": "ZANIK/1", "seq": 2})
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text(JOURNAL), {"id": "l", "kind": "OTHER", "number": "X/1", "seq": 3})
    with pytest.raises(RuntimeError, match="1 journal row"):
        run(engine, "0051_final_protocol_kind", "downgrade")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM issued_documents WHERE kind = 'FINAL_PROTOCOL'"))
    run(engine, "0051_final_protocol_kind", "downgrade")
    with pytest.raises(IntegrityError), engine.begin() as conn:  # the old CHECK is back
        conn.execute(text(JOURNAL), {"id": "m", "kind": "FINAL_PROTOCOL", "number": "ODBIOR/2", "seq": 4})
    assert "acceptance_protocols" in inspect(engine).get_table_names()  # only the journal kind came and went
    run(engine, "0051_final_protocol_kind", "upgrade")
