"""Stage 16G: the protocol of acceptance of concealed works -- the rules, the draft, the document, issuing and freezing, the API
and the migration."""
import io
import uuid
from datetime import date, datetime, timedelta

import pytest
from httpx import AsyncClient
from pypdf import PdfReader
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.domain.contracts.catalog import load_contract_catalog
from app.domain.documents.concealed_works_document import build_concealed_document, render_concealed_html
from app.domain.documents.renderer import DocumentRenderer
from app.domain.exceptions import ConcealedGateError, ConcealedInvalidError, ConcealedNotEditableError, ConcealedNotFoundError, ProjectNotFoundError
from app.domain.protocols import concealed as C
from app.domain.protocols.sources import load_concealed_sources
from app.domain.services.concealed_service import ConcealedService, data_of
from app.models.concealed_works_protocol import ConcealedWorksProtocol
from app.models.photo_asset import PhotoAssetStatus
from app.models.photo_attachment import PhotoAttachment, PhotoAttachmentContext, PhotoCategory
from app.models.project import Project
from tests.test_stage14b4_photo_asset import raw_asset
from tests.test_stage15f2_api import use_issuer  # noqa: F401  (a fixture)
from tests.test_stage15f2_issuing import Delivery, issuer, journal, text_of, user_of
from tests.test_stage16e2_contract import OWNER_TG, STRANGER_TG, contract_engine, load_migration, login, ready, run
from tests.test_stage16e4_signing import issued

CATALOG = load_contract_catalog()
SURFACE = str(uuid.uuid4())
PHOTO = str(uuid.uuid4())
OTHER_PHOTO = str(uuid.uuid4())
PERSON = str(uuid.uuid4())
PEOPLE = {PERSON: ("Anna Nowak", "Właścicielka")}
TODAY = date(2026, 10, 20)


def change(current=None, changes=None, surfaces=(SURFACE,), photos=None, people=PEOPLE):
    photos = {SURFACE: {PHOTO, OTHER_PHOTO}} if photos is None else photos
    return C.apply_changes(current or C.empty_state(), changes or {}, surface_ids=set(surfaces),
                           photos_of=lambda sid: set(photos.get(sid, ())), people=people, catalog=CATALOG)


def refused(**kw):
    with pytest.raises(ConcealedInvalidError) as exc:
        change(**kw)
    return exc.value.key, exc.value.reason


# --- the rules -------------------------------------------------------------------------------------------------------------------


def test_the_fields_are_checked_and_cleared_with_null():
    state = change(changes={"held_on": TODAY, "held_time": "08:15", "work_kind": "priming", "material": "  Grunt  głęboko penetrujący ", "batch": "L2210",
                            "work_note": "dwie warstwy", "remarks": "brak", "result": "ACCEPTED", "cover_consent": "GIVEN", "customer_absent": None})
    assert (state["held_time"], state["material"], state["customer_absent"]) == ("08:15", "Grunt głęboko penetrujący", False)
    cleared = change(state, {"held_time": None, "material": None, "batch": None, "result": None, "cover_consent": None, "work_kind": None})
    assert all(cleared[k] is None for k in ("held_time", "material", "batch", "result", "cover_consent", "work_kind"))
    assert refused(changes={"held_time": "8:15"}) == ("held_time", "BAD_TIME")
    assert refused(changes={"held_on": "2026-10-20"}) == ("held_on", "WRONG_TYPE")
    assert refused(changes={"notified_on": 5}) == ("notified_on", "WRONG_TYPE")
    assert refused(changes={"customer_absent": "yes"}) == ("customer_absent", "WRONG_TYPE")
    assert refused(changes={"work_kind": "painting"}) == ("work_kind", "NOT_AN_OPTION")
    assert refused(changes={"result": "OK"}) == ("result", "NOT_AN_OPTION")
    assert refused(changes={"cover_consent": "MAYBE"}) == ("cover_consent", "NOT_AN_OPTION")
    assert refused(changes={"material": "x" * 501}) == ("material", "TOO_LONG")
    assert refused(changes={"batch": "x" * 256}) == ("batch", "TOO_LONG")
    assert refused(changes={"remarks": "x" * 4001}) == ("remarks", "TOO_LONG")
    assert refused(changes={"remarks": 7}) == ("remarks", "WRONG_TYPE")
    assert refused(changes={"nonsense": 1}) == ("nonsense", C.UNKNOWN_FIELD)


def test_the_surface_must_be_one_of_the_objects_and_the_photos_one_of_its_evidence():
    state = change(changes={"surface_id": SURFACE, "photo_ids": [PHOTO, PHOTO, OTHER_PHOTO]})
    assert state["surface_id"] == SURFACE and state["photo_ids"] == [PHOTO, OTHER_PHOTO]  # no repeats, the order kept
    assert refused(changes={"surface_id": str(uuid.uuid4())}) == ("surface_id", C.UNKNOWN_SURFACE)
    assert refused(changes={"surface_id": "x"}) == ("surface_id", "WRONG_TYPE")
    assert refused(changes={"photo_ids": [str(uuid.uuid4())]}) == ("photo_ids", C.UNKNOWN_PHOTO)
    assert refused(changes={"photo_ids": [PHOTO]}) == ("photo_ids", C.UNKNOWN_PHOTO)  # no surface chosen yet: no evidence to choose from
    assert refused(changes={"photo_ids": "all"}) == ("photo_ids", "WRONG_TYPE")
    assert refused(changes={"photo_ids": [5]}) == ("photo_ids", "WRONG_TYPE")
    assert change(state, {"photo_ids": None})["photo_ids"] == []
    # the surface and its photos may be chosen in one change, in either order of the keys
    both = change(changes={"photo_ids": [PHOTO], "surface_id": SURFACE})
    assert both["photo_ids"] == [PHOTO]


def test_changing_the_surface_drops_the_photos_of_the_old_one_unless_new_ones_are_chosen_with_it():
    second = str(uuid.uuid4())
    other_photo = str(uuid.uuid4())
    photos = {SURFACE: {PHOTO}, second: {other_photo}}
    state = change(changes={"surface_id": SURFACE, "photo_ids": [PHOTO]}, surfaces=(SURFACE, second), photos=photos)
    moved = change(state, {"surface_id": second}, surfaces=(SURFACE, second), photos=photos)
    assert moved["surface_id"] == second and moved["photo_ids"] == []
    with_new = change(state, {"surface_id": second, "photo_ids": [other_photo]}, surfaces=(SURFACE, second), photos=photos)
    assert with_new["photo_ids"] == [other_photo]
    same = change(state, {"surface_id": SURFACE}, surfaces=(SURFACE, second), photos=photos)
    assert same["photo_ids"] == [PHOTO]  # the same surface again keeps its photos


def test_people_present_are_copied_by_name_and_a_wrong_entry_changes_nothing():
    state = change(changes={"attendees": [{"person_id": PERSON}, {"name": "Jan Sąsiad", "role": "administrator"}]})
    assert state["attendees"] == [{"person_id": PERSON, "name": "Anna Nowak", "role": "Właścicielka"}, {"person_id": None, "name": "Jan Sąsiad", "role": "administrator"}]
    assert refused(changes={"attendees": [{"person_id": str(uuid.uuid4())}]}) == ("attendees", "UNKNOWN_PERSON")
    current = change(changes={"material": "stare"})
    with pytest.raises(ConcealedInvalidError):
        change(current, {"material": "nowe", "result": "OK"})
    assert current["material"] == "stare"


def codes(blockers):
    return [b.code for b in blockers]


def complete(**over):
    data = {**C.empty_state(), "surface_id": SURFACE, "work_kind": "priming", "held_on": TODAY, "attendees": [{"person_id": None, "name": "A", "role": None}],
            "photo_ids": [PHOTO], "result": "ACCEPTED", "cover_consent": "GIVEN"}
    data.update(over)
    return data


def test_the_blockers_are_listed_in_the_order_of_doing():
    assert codes(C.evaluate(C.empty_state())) == [C.SURFACE_REQUIRED, C.WORK_KIND_REQUIRED, C.HELD_ON_REQUIRED, C.NO_ATTENDEES, C.PHOTOS_REQUIRED,
                                                  C.RESULT_REQUIRED, C.COVER_CONSENT_REQUIRED]
    assert C.evaluate(complete()) == []
    assert codes(C.evaluate(complete(work_kind="other"))) == [C.WORK_NOTE_REQUIRED]  # "other" is described in words
    assert C.evaluate(complete(work_kind="other", work_note="Taśma uszczelniająca")) == []
    assert codes(C.evaluate(complete(result="WITH_REMARKS"))) == [C.REMARKS_REQUIRED]
    assert C.evaluate(complete(result="WITH_REMARKS", remarks="Zacieki przy oknie")) == []
    assert codes(C.evaluate(complete(photo_ids=[]))) == [C.PHOTOS_REQUIRED]  # without evidence nobody can say later what was covered


def test_an_absent_customer_needs_the_day_he_was_notified_and_no_consent_but_still_needs_the_photos():
    absent = complete(customer_absent=True, attendees=[], cover_consent=None)
    assert codes(C.evaluate(absent)) == [C.NOTIFIED_ON_REQUIRED]
    assert C.evaluate({**absent, "notified_on": date(2026, 10, 19)}) == []
    assert codes(C.evaluate({**absent, "notified_on": date(2026, 10, 19), "photo_ids": []})) == [C.PHOTOS_REQUIRED]
    assert codes(C.evaluate(complete(attendees=[], cover_consent=None))) == [C.NO_ATTENDEES, C.COVER_CONSENT_REQUIRED]  # present: people and a consent


# --- the draft ---------------------------------------------------------------------------------------------------------------------


def svc(db):
    return ConcealedService(db)


async def add_photo(db, w, surface_id, *, category=PhotoCategory.HIDDEN_WORK, caption="Gruntowanie, narożnik", archived=False, minute=0,
                    captured=None, context=PhotoAttachmentContext.SURFACE):
    asset = raw_asset(w.owner, w.project, status=PhotoAssetStatus.READY, width=1600, height=1200, captured_at=captured)
    db.add(asset)
    await db.flush()
    attachment = PhotoAttachment(
        asset_id=asset.id, project_id=w.project.id, context=context, category=category, caption=caption,
        surface_id=surface_id if context == PhotoAttachmentContext.SURFACE else None,
        room_id=w.salon.id if context == PhotoAttachmentContext.ROOM else None,
        archived_at=datetime(2026, 10, 1) if archived else None, position=minute,
    )
    db.add(attachment)
    await db.commit()
    return str(attachment.id)


async def test_the_draft_is_one_per_object_numbered_and_records_the_acceptance(db_session):
    w = await ready(db_session, telegram_id=9981)
    surface = w.wall.id
    ok = await add_photo(db_session, w, surface)
    first, created = await svc(db_session).open_draft(w.project.id, w.owner.id)
    again, created_again = await svc(db_session).open_draft(w.project.id, w.owner.id)
    assert created and not created_again and again.id == first.id and first.sequence == 1 and first.status == "DRAFT"
    row = await svc(db_session).update(w.project.id, first.id, w.owner.id, {
        "surface_id": str(surface), "work_kind": "glass_fleece", "held_on": TODAY, "photo_ids": [ok], "result": "ACCEPTED",
        "cover_consent": "GIVEN", "attendees": [{"person_id": str(w.person.id)}], "material": "Welon 50 g/m²", "batch": "L77"})
    read = await svc(db_session).read(row)
    assert [b.code for b in read.blockers] == ["CONTRACT_REQUIRED"]  # only a draft contract exists
    assert read.surface.name == "Ściana A" and read.surface.room_name == "Salon" and [p.id for p in read.photo_options] == [ok]
    assert read.photo_ids == [ok] and read.work_kind == "glass_fleece" and read.customer_absent is False
    archived = await svc(db_session).archive_draft(w.project.id, first.id, w.owner.id)
    assert archived.status == "ARCHIVED"
    with pytest.raises(ConcealedNotEditableError):
        await svc(db_session).update(w.project.id, first.id, w.owner.id, {"material": "x"})
    with pytest.raises(ConcealedNotEditableError):
        await svc(db_session).archive_draft(w.project.id, first.id, w.owner.id)
    second, _ = await svc(db_session).open_draft(w.project.id, w.owner.id)
    assert second.sequence == 2


async def test_only_the_evidence_photos_of_the_chosen_surface_are_offered(db_session):
    w = await ready(db_session, telegram_id=9982)
    surface = w.wall.id
    other = (await load_concealed_sources(db_session, w.owner.id, w.project.id)).surfaces
    assert str(surface) in other
    mine = await add_photo(db_session, w, surface, minute=1)
    await add_photo(db_session, w, surface, category=PhotoCategory.GENERAL)  # not evidence of concealed work
    await add_photo(db_session, w, surface, archived=True)  # archived
    await add_photo(db_session, w, None, context=PhotoAttachmentContext.ROOM, category=PhotoCategory.HIDDEN_WORK)  # a room photo
    draft, _ = await svc(db_session).open_draft(w.project.id, w.owner.id)
    with pytest.raises(ConcealedInvalidError) as no_surface:
        await svc(db_session).update(w.project.id, draft.id, w.owner.id, {"photo_ids": [mine]})
    assert no_surface.value.reason == C.UNKNOWN_PHOTO
    row = await svc(db_session).update(w.project.id, draft.id, w.owner.id, {"surface_id": str(surface)})
    assert [p.id for p in (await svc(db_session).read(row)).photo_options] == [mine]
    for bad in ({"photo_ids": [str(uuid.uuid4())]},):
        with pytest.raises(ConcealedInvalidError):
            await svc(db_session).update(w.project.id, draft.id, w.owner.id, bad)


async def test_foreign_data_is_refused_and_a_stranger_finds_nothing(db_session):
    mine = await ready(db_session, telegram_id=9983)
    theirs = await ready(db_session, telegram_id=9984)
    draft, _ = await svc(db_session).open_draft(mine.project.id, mine.owner.id)
    with pytest.raises(ConcealedInvalidError) as foreign_surface:
        await svc(db_session).update(mine.project.id, draft.id, mine.owner.id, {"surface_id": str(theirs.wall.id)})
    assert foreign_surface.value.reason == C.UNKNOWN_SURFACE
    with pytest.raises(ConcealedInvalidError) as foreign_person:
        await svc(db_session).update(mine.project.id, draft.id, mine.owner.id, {"attendees": [{"person_id": str(theirs.person.id)}]})
    assert foreign_person.value.reason == "UNKNOWN_PERSON"
    with pytest.raises(ProjectNotFoundError):
        await svc(db_session).open_draft(mine.project.id, theirs.owner.id)
    with pytest.raises(ProjectNotFoundError):
        await svc(db_session).get(mine.project.id, draft.id, theirs.owner.id)
    with pytest.raises(ConcealedNotFoundError):
        await svc(db_session).get(mine.project.id, uuid.uuid4(), mine.owner.id)
    other, _ = await svc(db_session).open_draft(theirs.project.id, theirs.owner.id)
    with pytest.raises(ConcealedNotFoundError):
        await svc(db_session).get(mine.project.id, other.id, mine.owner.id)


# --- the document --------------------------------------------------------------------------------------------------------------------


async def complete_world(db, telegram_id, *, absent=False, kind="priming", extra=None):
    """A world with an issued contract, evidence photos on the wall and a draft protocol that passes the gate."""
    w, owner_id, project_id, contract_id = await issued(db, telegram_id)
    surface = w.wall.id
    first = await add_photo(db, w, surface, caption="Narożnik przy oknie", minute=1, captured=datetime(2026, 10, 20, 8, 5))
    second = await add_photo(db, w, surface, caption="Ściana przy drzwiach", minute=2)
    draft, _ = await svc(db).open_draft(project_id, owner_id)
    changes = {"surface_id": str(surface), "work_kind": kind, "held_on": TODAY, "held_time": "08:15", "photo_ids": [first, second], "result": "WITH_REMARKS",
               "remarks": "Drobne zacieki przy parapecie – do poprawy przed zakryciem", "material": "Grunt głęboko penetrujący", "batch": "L2210/4"}
    if absent:
        changes.update(customer_absent=True, notified_on=date(2026, 10, 19))
    else:
        changes.update(attendees=[{"person_id": str(w.person.id)}, {"name": "Jan Sąsiad", "role": "administrator"}], cover_consent="WITHHELD")
    changes.update(extra or {})
    await svc(db).update(project_id, draft.id, owner_id, changes)
    return w, owner_id, project_id, draft.id


async def build(db, owner_id, project_id, draft_id=None, *, working=False, number="ZANIK/2026/10/20/0815"):
    sources = await load_concealed_sources(db, owner_id, project_id)
    row = await db.get(ConcealedWorksProtocol, draft_id) if draft_id else None
    data = data_of(row) if row else {}
    return build_concealed_document(data, sources, working=working, issued_on=TODAY, number=None if working else number, sequence=1), sources, data


async def test_the_page_prints_the_work_the_material_the_evidence_the_result_and_the_consent(db_session):
    w, owner_id, project_id, hid = await complete_world(db_session, 9985)
    document, _, _ = await build(db_session, owner_id, project_id, hid)
    body = render_concealed_html(document)
    body = body[body.index("<body"):]
    facts = {row.label: row.value for row in document.facts}
    assert facts["Pomieszczenie"] == "Salon" and facts["Powierzchnia"] == "Ściana A" and facts["Rodzaj roboty zanikającej"] == "Gruntowanie podłoża"
    assert facts["Materiał"] == "Grunt głęboko penetrujący" and facts["Numer partii"] == "L2210/4" and facts["Data i godzina odbioru"] == "20.10.2026, 08:15"
    assert facts["Umowa"].startswith("wersja 1, nr UMOWA/")
    assert [(p.number, p.caption) for p in document.photos] == [(1, "Narożnik przy oknie"), (2, "Ściana przy drzwiach")]
    assert document.photos[0].taken == "20.10.2026 08:05" and len(document.photos[0].ref) == 8
    assert [o.label for o in document.results if o.checked] == ["Odebrano z uwagami"] and "Drobne zacieki przy parapecie" in body
    assert [o.label for o in document.consents if o.checked] == ["Zgody na zakrycie nie udzielono"] and document.absent_text is None
    assert "Jan Sąsiad" in body and "☒&nbsp;Odebrano z uwagami" in body and 'class="watermark' not in body and "ZANIK/2026/10/20/0815" in body


async def test_a_one_sided_protocol_says_when_the_customer_was_notified_and_has_no_consent_boxes(db_session):
    w, owner_id, project_id, hid = await complete_world(db_session, 9986, absent=True, extra={"result": "ACCEPTED", "remarks": None})
    document, _, _ = await build(db_session, owner_id, project_id, hid)
    body = render_concealed_html(document)
    assert document.absent_text.startswith("Zamawiający ani Osoba upoważniona nie stawili się w terminie wskazanym w zawiadomieniu z dnia 19.10.2026.")
    assert "§ 13 ust. 3 Umowy" in document.absent_text and document.consent_note.startswith("Nie dotyczy — protokół jednostronny")
    assert "Zgoda na zakrycie udzielona" not in body and "Nie dotyczy — protokół jednostronny" in body


async def test_the_working_version_is_a_blank_form_that_never_refuses_and_cannot_be_numbered(db_session):
    w = await ready(db_session, telegram_id=9987)
    document, sources, _ = await build(db_session, w.owner.id, w.project.id, working=True)
    body = render_concealed_html(document)
    body = body[body.index("<body"):]
    assert document.layout.draft and document.layout.light_watermark and document.layout.meta.number is None
    assert 'class="watermark light"' in body and body.count("☐") == 4 and len(document.photos) == 5 and body.count('class="write-line"') >= 8
    assert "Obecni: do wpisania." in body and "wpisz datę zawiadomienia" in body
    with pytest.raises(Exception) as numbered:
        build_concealed_document({}, sources, working=True, issued_on=TODAY, number="ZANIK/1")
    assert numbered.value.reason == "DRAFT_NUMBERED"
    sources.base.executor = None
    assert build_concealed_document({}, sources, working=True, issued_on=TODAY)
    with pytest.raises(Exception) as no_profile:
        build_concealed_document({}, sources, working=False, issued_on=TODAY)
    assert no_profile.value.reason == "EXECUTOR_PROFILE_REQUIRED"


async def test_a_real_pdf_with_the_number_on_every_page(db_session):
    w, owner_id, project_id, hid = await complete_world(db_session, 9988)
    document, _, _ = await build(db_session, owner_id, project_id, hid)
    pdf = (await DocumentRenderer().render(render_concealed_html(document))).pdf
    pages = PdfReader(io.BytesIO(pdf)).pages
    assert len(pages) >= 1 and all("ZANIK/2026/10/20/0815" in page.extract_text() for page in pages)
    flat = " ".join(text_of(pdf).split())
    for part in ("Protokół odbioru robót zanikających", "Gruntowanie podłoża", "Narożnik przy oknie", "Anna Nowak", "ul. Zielona 5/7"):
        assert part in flat, part


# --- the gate and the freeze ------------------------------------------------------------------------------------------------------------


async def test_a_protocol_that_is_not_ready_is_refused_with_the_list_and_takes_no_number(db_session):
    w, owner_id, project_id, contract_id = await issued(db_session, 9989)
    draft, _ = await svc(db_session).open_draft(project_id, owner_id)
    run_ = issuer(delivery=Delivery())
    with pytest.raises(ConcealedGateError) as refused:
        await run_.start_concealed(db_session, await user_of(db_session, owner_id), project_id, draft.id)
    assert [b.code for b in refused.value.blockers] == ["SURFACE_REQUIRED", "WORK_KIND_REQUIRED", "HELD_ON_REQUIRED", "NO_ATTENDEES", "PHOTOS_REQUIRED",
                                                       "RESULT_REQUIRED", "COVER_CONSENT_REQUIRED"]
    assert all(j.kind != "CONCEALED_WORKS_PROTOCOL" for j in await journal(db_session))
    w2 = await ready(db_session, telegram_id=9990)  # only a draft contract: no contract to work under
    other, _ = await svc(db_session).open_draft(w2.project.id, w2.owner.id)
    with pytest.raises(ConcealedGateError) as no_contract:
        await run_.start_concealed(db_session, await user_of(db_session, w2.owner.id), w2.project.id, other.id)
    assert no_contract.value.blockers[0].code == "CONTRACT_REQUIRED"


async def test_issuing_freezes_the_protocol_numbers_it_sends_the_pdf_and_records_it(db_session):
    w, owner_id, project_id, hid = await complete_world(db_session, 9991)
    telegram = w.owner.telegram_user_id
    sender = Delivery()
    run_ = issuer(delivery=sender)
    reservation = await run_.start_concealed(db_session, await user_of(db_session, owner_id), project_id, hid)
    assert (reservation.document.kind, reservation.document.status, reservation.document.source_id, reservation.document.source_version) == (
        "CONCEALED_WORKS_PROTOCOL", "PENDING", hid, 1)
    assert reservation.document.number.startswith("ZANIK/2026/10/08/")
    await run_.drain()
    done = [j for j in await journal(db_session) if j.kind == "CONCEALED_WORKS_PROTOCOL"][0]
    number = done.number
    assert (done.status, done.error_code, done.title) == ("SENT", None, "Protokół odbioru robót zanikających — nr 1")
    message = sender.sent[-1]
    assert message["chat_id"] == telegram and message["filename"].startswith("ZANIK-2026-10-08-")
    assert message["caption"].startswith("Protokół odbioru robót zanikających — nr 1 — Mokotów\nZANIK/") and number in text_of(message["pdf"])
    db_session.expire_all()
    row = await db_session.get(ConcealedWorksProtocol, hid)
    assert row.status == "ISSUED" and row.issued_at is not None and row.contract_version == 1 and row.contract_id is not None and number in row.document_html
    snap = row.snapshot
    assert snap["held_on"] == "2026-10-20" and snap["work_kind"] == "priming" and snap["batch"] == "L2210/4" and snap["customer_absent"] is False
    assert snap["surface"]["name"] == "Ściana A" and [p["caption"] for p in snap["photos"]] == ["Narożnik przy oknie", "Ściana przy drzwiach"]
    assert snap["contract"]["version"] == 1 and snap["contract"]["number"].startswith("UMOWA/") and snap["result"] == "WITH_REMARKS"
    with pytest.raises(ConcealedNotEditableError):
        await ConcealedService(db_session).update(project_id, hid, owner_id, {"material": "inny"})
    with pytest.raises(ConcealedNotEditableError):
        await run_.start_concealed(db_session, await user_of(db_session, owner_id), project_id, hid)
    with pytest.raises(ConcealedNotEditableError):  # the service itself refuses to freeze twice
        await ConcealedService(db_session).mark_issued(project_id, hid, owner_id, issued_at=run_.clock(), snapshot={}, document_html="<html></html>",
                                                       contract_id=None, contract_version=None)
    assert (await svc(db_session).open_draft(project_id, owner_id))[0].sequence == 2


async def test_the_issued_page_does_not_change_when_the_data_do(db_session):
    w, owner_id, project_id, hid = await complete_world(db_session, 9992)
    run_ = issuer(delivery=Delivery())
    await run_.start_concealed(db_session, await user_of(db_session, owner_id), project_id, hid)
    await run_.drain()
    frozen = (await db_session.get(ConcealedWorksProtocol, hid)).document_html
    project = (await db_session.execute(select(Project).where(Project.id == project_id))).scalar_one()
    project.name = "Zupełnie inna nazwa"
    w.wall.name = "Inna ściana"
    w.person.name = "Ktoś Inny"
    await db_session.commit()
    row = [j for j in await journal(db_session) if j.kind == "CONCEALED_WORKS_PROTOCOL"][0]
    again = await run_._render(db_session, row)
    assert (await db_session.get(ConcealedWorksProtocol, hid)).document_html == frozen
    flat = text_of(again.pdf)
    assert "Ściana A" in flat and "Anna Nowak" in flat and "Inna ściana" not in flat and "Ktoś Inny" not in flat


async def test_the_preview_follows_the_draft_and_never_leaves_a_row(db_session):
    w, owner_id, project_id, hid = await complete_world(db_session, 9993)
    sender = Delivery()
    before = len(await journal(db_session))
    result = await issuer(delivery=sender).preview_concealed(db_session, await user_of(db_session, owner_id), project_id)
    assert result.pages >= 1
    message = sender.sent[-1]
    assert message["filename"] == "Protokol-robot-zanikajacych-wersja-robocza.pdf" and message["caption"].startswith("WERSJA ROBOCZA — Protokół odbioru robót zanikających")
    flat = " ".join(text_of(message["pdf"]).split())
    assert "WERSJA ROBOCZA" in flat and "Grunt głęboko penetrujący" in flat and "Narożnik przy oknie" in flat
    assert len(await journal(db_session)) == before


# --- HTTP ----------------------------------------------------------------------------------------------------------------------------------


def url(project_id, tail=""):
    return f"/api/projects/{project_id}/concealed-works{tail}"


async def test_the_routes_need_a_token_and_a_stranger_gets_404(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    mine = await ready(db_session, telegram_id=OWNER_TG)
    theirs = await ready(db_session, telegram_id=STRANGER_TG)
    use_issuer(issuer(delivery=Delivery()))
    assert (await async_client.get(url(mine.project.id))).status_code == 401
    assert (await async_client.post(f"/api/projects/{mine.project.id}/documents/concealed-works/preview")).status_code == 401
    headers = await login(async_client)
    draft, _ = await svc(db_session).open_draft(theirs.project.id, theirs.owner.id)
    for response in (
        await async_client.get(url(theirs.project.id), headers=headers),
        await async_client.post(url(theirs.project.id), headers=headers),
        await async_client.post(url(theirs.project.id, f"/{draft.id}/issue"), headers=headers),
        await async_client.post(f"/api/projects/{theirs.project.id}/documents/concealed-works/preview", headers=headers),
        await async_client.get(url(mine.project.id, f"/{uuid.uuid4()}"), headers=headers),
        await async_client.get(url(mine.project.id, f"/{draft.id}"), headers=headers),
    ):
        assert response.status_code == 404


async def test_open_record_issue_and_abandon_over_http(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w, owner_id, project_id, contract_id = await issued(db_session, OWNER_TG)
    surface = str(w.wall.id)
    photo = await add_photo(db_session, w, w.wall.id, caption="Siatka w narożniku")
    sender = Delivery()
    run_ = use_issuer(issuer(delivery=sender))
    headers = await login(async_client)
    pid = str(project_id)
    created = await async_client.post(url(pid), headers=headers)
    assert created.status_code == 201, created.text
    body = created.json()
    assert (body["sequence"], body["status"], body["photo_ids"], body["customer_absent"]) == (1, "DRAFT", [], False)
    assert (await async_client.post(url(pid), headers=headers)).status_code == 200
    hid = body["id"]
    assert (await async_client.patch(url(pid, f"/{hid}"), json={}, headers=headers)).status_code == 422
    assert (await async_client.patch(url(pid, f"/{hid}"), json={"unknown": 1}, headers=headers)).status_code == 422
    bad = await async_client.patch(url(pid, f"/{hid}"), json={"work_kind": "painting"}, headers=headers)
    assert bad.status_code == 422 and bad.json()["detail"] == {"code": "CONCEALED_INVALID", "message": "concealed works 'work_kind': NOT_AN_OPTION",
                                                              "details": {"key": "work_kind", "reason": "NOT_AN_OPTION"}}
    saved = await async_client.patch(url(pid, f"/{hid}"), json={
        "surface_id": surface, "work_kind": "reinforcing_mesh", "held_on": "2026-10-20", "photo_ids": [photo], "result": "ACCEPTED",
        "customer_absent": True, "notified_on": "2026-10-19"}, headers=headers)
    assert saved.status_code == 200, saved.text
    assert saved.json()["surface"]["room_name"] == "Salon" and [p["id"] for p in saved.json()["photo_options"]] == [photo] and saved.json()["blockers"] == []
    ok = await async_client.post(url(pid, f"/{hid}/issue"), headers=headers)
    assert ok.status_code == 202, ok.text
    assert ok.json()["kind"] == "CONCEALED_WORKS_PROTOCOL" and ok.json()["number"].startswith("ZANIK/") and ok.json()["source_id"] == hid
    await run_.drain()
    again = await async_client.post(url(pid, f"/{hid}/issue"), headers=headers)
    assert again.status_code == 409 and again.json()["detail"]["code"] == "CONCEALED_NOT_EDITABLE"
    listed = (await async_client.get(f"/api/projects/{pid}/documents", headers=headers)).json()
    assert [d["kind"] for d in listed["items"]].count("CONCEALED_WORKS_PROTOCOL") == 1
    second = (await async_client.post(url(pid), headers=headers)).json()
    blocked = await async_client.post(url(pid, f"/{second['id']}/issue"), headers=headers)
    assert blocked.status_code == 422 and blocked.json()["detail"]["code"] == "CONCEALED_GATE_BLOCKED"
    assert blocked.json()["detail"]["details"]["blockers"][0]["code"] == "SURFACE_REQUIRED"
    gone = await async_client.post(url(pid, f"/{second['id']}/archive"), headers=headers)
    assert gone.status_code == 200 and gone.json()["status"] == "ARCHIVED"
    preview = await async_client.post(f"/api/projects/{pid}/documents/concealed-works/preview", headers=headers)
    assert preview.status_code == 200 and preview.json()["sent"] is True


# --- migration -------------------------------------------------------------------------------------------------------------------------------


def test_revision_chain_and_length():
    module = load_migration("0049_concealed_works")
    assert module.revision == "0049_concealed_works" and module.down_revision == "0048_handover_issue" and len(module.revision) <= 32


def engine_0049():
    engine = contract_engine()
    for name in ("0045_contract_issue", "0046_contract_signed", "0047_handover_protocols", "0048_handover_issue", "0049_concealed_works"):
        run(engine, name, "upgrade")
    return engine


ROW = ("INSERT INTO concealed_works_protocols (id, owner_id, project_id, sequence, status, customer_absent, attendees, photo_ids, result, cover_consent, "
       "issued_at, snapshot, document_html, created_at, updated_at) VALUES (:id, 'u1', 'p1', :sequence, :status, 0, '[]', '[]', :result, :consent, "
       ":issued, :snapshot, :html, '2026-10-10', '2026-10-10')")
JOURNAL = ("INSERT INTO issued_documents (id, owner_id, project_id, kind, title, number, project_seq, template_version, status, issued_at) "
           "VALUES (:id, 'u1', 'p1', :kind, 't', :number, :seq, '1', 'SENT', '2026-10-10')")
BLANK = {"result": None, "consent": None, "issued": None, "snapshot": None, "html": None}
FROZEN = {**BLANK, "issued": "2026-10-10", "snapshot": "{}", "html": "<html></html>"}


def test_the_database_allows_one_draft_a_sequence_once_known_states_and_a_frozen_issued_protocol():
    engine = engine_0049()
    with engine.begin() as conn:
        conn.execute(text(ROW), {"id": "a", "sequence": 1, "status": "DRAFT", **BLANK})
        conn.execute(text(ROW), {"id": "b", "sequence": 2, "status": "ARCHIVED", **BLANK})
        conn.execute(text(ROW), {"id": "c", "sequence": 3, "status": "ISSUED", **FROZEN, "result": "ACCEPTED", "consent": "GIVEN"})
        conn.execute(text(JOURNAL), {"id": "j", "kind": "CONCEALED_WORKS_PROTOCOL", "number": "ZANIK/1", "seq": 1})
    for bad in (
        {"id": "d", "sequence": 4, "status": "DRAFT", **BLANK},  # a second draft
        {"id": "e", "sequence": 1, "status": "ARCHIVED", **BLANK},  # a repeated number
        {"id": "f", "sequence": 5, "status": "SIGNED", **BLANK},
        {"id": "g", "sequence": 0, "status": "ARCHIVED", **BLANK},
        {"id": "h", "sequence": 6, "status": "ISSUED", **BLANK},  # issued without its page
        {"id": "i", "sequence": 7, "status": "ARCHIVED", **{**BLANK, "result": "OK"}},
        {"id": "k", "sequence": 8, "status": "ARCHIVED", **{**BLANK, "consent": "MAYBE"}},
    ):
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(text(ROW), bad)
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text(JOURNAL), {"id": "l", "kind": "OTHER", "number": "X/1", "seq": 2})
    assert {c["name"] for c in inspect(engine).get_columns("concealed_works_protocols")} == {c.name for c in ConcealedWorksProtocol.__table__.columns}


def test_downgrade_refuses_while_a_protocol_or_a_journal_row_exists_and_then_works():
    engine = engine_0049()
    with engine.begin() as conn:
        conn.execute(text(ROW), {"id": "a", "sequence": 1, "status": "DRAFT", **BLANK})
    with pytest.raises(RuntimeError, match="1 concealed works protocol"):
        run(engine, "0049_concealed_works", "downgrade")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM concealed_works_protocols"))
        conn.execute(text(JOURNAL), {"id": "j", "kind": "CONCEALED_WORKS_PROTOCOL", "number": "ZANIK/1", "seq": 1})
    with pytest.raises(RuntimeError, match="1 journal row"):
        run(engine, "0049_concealed_works", "downgrade")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM issued_documents"))
    run(engine, "0049_concealed_works", "downgrade")
    assert "concealed_works_protocols" not in inspect(engine).get_table_names() and "handover_protocols" in inspect(engine).get_table_names()
    run(engine, "0049_concealed_works", "upgrade")


async def test_only_the_chosen_photos_are_printed_and_an_archived_surface_cannot_be_chosen(db_session):
    w, owner_id, project_id, hid = await complete_world(db_session, 9994)
    unused = await add_photo(db_session, w, w.wall.id, caption="Zdjęcie niewybrane", minute=3)
    document, sources, _ = await build(db_session, owner_id, project_id, hid)
    assert "Zdjęcie niewybrane" not in [p.caption for p in document.photos] and unused[:8] not in {p.ref for p in document.photos}
    assert len(sources.photos[str(w.wall.id)]) == 3 and len(document.photos) == 2  # three exist, the two chosen are printed
    wall = await db_session.get(type(w.wall), w.wall.id)
    wall.is_archived = True
    await db_session.commit()
    with pytest.raises(ConcealedInvalidError) as refused:
        await svc(db_session).update(project_id, hid, owner_id, {"surface_id": str(w.wall.id)})
    assert refused.value.reason == C.UNKNOWN_SURFACE
