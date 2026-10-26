"""V2-12b: the protocol of a pressure test -- the rules, the draft, the document, issuing and freezing, the API and the migration (docs/V2_12B_PLAN_RU.md)."""
import io
import uuid
from datetime import date, datetime
from decimal import Decimal

import pytest
from app.domain.documents.pressure_test_document import bar_text, build_pressure_document, render_pressure_html
from app.domain.documents.registry import DocumentKind, get_template
from app.domain.exceptions import PressureGateError, PressureInvalidError, PressureNotEditableError, PressureNotFoundError, ProjectNotFoundError
from app.domain.protocols import pressure as P
from app.domain.protocols.sources import load_pressure_sources
from app.domain.services.pressure_service import PressureService, data_of
from app.models.photo_asset import PhotoAssetStatus
from app.models.photo_attachment import PhotoAttachment, PhotoAttachmentContext, PhotoCategory
from app.models.pressure_test_protocol import PressureTestProtocol
from httpx import AsyncClient
from pypdf import PdfReader
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from tests.test_stage14b4_photo_asset import raw_asset
from tests.test_stage15f2_api import use_issuer  # noqa: F401  (a fixture)
from tests.test_stage15f2_issuing import Delivery, issuer, journal, text_of, user_of
from tests.test_stage16e2_contract import OWNER_TG, STRANGER_TG, contract_engine, load_migration, login, ready, run

PHOTO = str(uuid.uuid4())
OTHER_PHOTO = str(uuid.uuid4())
PERSON = str(uuid.uuid4())
PEOPLE = {PERSON: ("Anna Nowak", "Właścicielka")}
TODAY = date(2026, 10, 20)
NBSP = " "


def change(current=None, changes=None, photos=(PHOTO, OTHER_PHOTO), people=PEOPLE):
    return P.apply_changes(current or P.empty_state(), changes or {}, photo_ids=set(photos), people=people)


def refused(**kw):
    with pytest.raises(PressureInvalidError) as exc:
        change(**kw)
    return exc.value.key, exc.value.reason


# --- the rules ---------------------------------------------------------------------------------------------------------------------------


def test_the_numbers_and_words_are_checked_and_cleared_with_null():
    state = change(changes={"held_on": TODAY, "held_time": "08:15", "system": "HOT_WATER", "section": "  łazienka,   pion  ", "medium": "WATER",
                            "test_pressure_bar": "6,5", "duration_min": 30, "pressure_drop_bar": 0, "result": "POSITIVE", "remarks": "brak", "customer_absent": None})
    assert (state["section"], state["test_pressure_bar"], state["pressure_drop_bar"], state["duration_min"], state["customer_absent"]) == (
        "łazienka, pion", Decimal("6.50"), Decimal("0.00"), 30, False)
    cleared = change(state, {key: None for key in ("system", "section", "medium", "test_pressure_bar", "duration_min", "pressure_drop_bar", "result", "remarks", "held_time")})
    assert all(cleared[key] is None for key in ("system", "section", "medium", "test_pressure_bar", "duration_min", "pressure_drop_bar", "result", "remarks", "held_time"))
    assert refused(changes={"system": "STEAM"}) == ("system", "NOT_AN_OPTION")
    assert refused(changes={"medium": "OIL"}) == ("medium", "NOT_AN_OPTION")
    assert refused(changes={"result": "OK"}) == ("result", "NOT_AN_OPTION")
    assert refused(changes={"held_time": "8:15"}) == ("held_time", "BAD_TIME")
    assert refused(changes={"held_on": "2026-10-20"}) == ("held_on", "WRONG_TYPE")
    assert refused(changes={"customer_absent": "yes"}) == ("customer_absent", "WRONG_TYPE")
    assert refused(changes={"section": "x" * 201}) == ("section", "TOO_LONG")
    assert refused(changes={"remarks": 7}) == ("remarks", "WRONG_TYPE")
    assert refused(changes={"nonsense": 1}) == ("nonsense", P.UNKNOWN_FIELD)


@pytest.mark.parametrize("key,value,reason", [
    ("test_pressure_bar", 0, "OUT_OF_RANGE"), ("test_pressure_bar", "-1", "OUT_OF_RANGE"), ("test_pressure_bar", 100.5, "OUT_OF_RANGE"), ("test_pressure_bar", "6,555", "WRONG_TYPE"),
    ("test_pressure_bar", "abc", "WRONG_TYPE"), ("test_pressure_bar", True, "WRONG_TYPE"), ("test_pressure_bar", [6], "WRONG_TYPE"),
    ("pressure_drop_bar", -0.01, "OUT_OF_RANGE"), ("pressure_drop_bar", 101, "OUT_OF_RANGE"),
    ("duration_min", 0, "OUT_OF_RANGE"), ("duration_min", 1441, "OUT_OF_RANGE"), ("duration_min", 30.5, "WRONG_TYPE"), ("duration_min", "30", "WRONG_TYPE"), ("duration_min", True, "WRONG_TYPE"),
])
def test_a_number_that_is_not_one_or_out_of_range_is_refused(key, value, reason):
    assert refused(changes={key: value}) == (key, reason)


def test_the_limits_themselves_are_accepted():
    state = change(changes={"test_pressure_bar": 100, "duration_min": 1440, "pressure_drop_bar": 100})
    assert (state["test_pressure_bar"], state["duration_min"], state["pressure_drop_bar"]) == (Decimal("100.00"), 1440, Decimal("100.00"))
    assert change(changes={"test_pressure_bar": "0.01"})["test_pressure_bar"] == Decimal("0.01")


def test_the_photos_are_the_objects_without_repeats_and_at_most_four():
    state = change(changes={"photo_ids": [PHOTO, PHOTO, OTHER_PHOTO]})
    assert state["photo_ids"] == [PHOTO, OTHER_PHOTO]
    assert refused(changes={"photo_ids": [str(uuid.uuid4())]}) == ("photo_ids", P.UNKNOWN_PHOTO)
    assert refused(changes={"photo_ids": ["x"]}) == ("photo_ids", P.UNKNOWN_PHOTO)
    assert refused(changes={"photo_ids": "x"}) == ("photo_ids", "WRONG_TYPE")
    many = [str(uuid.uuid4()) for _ in range(5)]
    with pytest.raises(PressureInvalidError) as too_many:
        P.apply_changes(P.empty_state(), {"photo_ids": many}, photo_ids=set(many), people=PEOPLE)
    assert too_many.value.reason == P.TOO_MANY_PHOTOS
    assert change(changes={"photo_ids": None})["photo_ids"] == []


def test_people_present_are_copied_by_name_and_a_wrong_entry_changes_nothing():
    state = change(changes={"attendees": [{"person_id": PERSON}, {"name": "Jan Sąsiad", "role": "administrator"}]})
    assert [a["name"] for a in state["attendees"]] == ["Anna Nowak", "Jan Sąsiad"]
    before = change(changes={"system": "GAS"})
    with pytest.raises(PressureInvalidError):
        change(before, {"system": "SEWER", "attendees": [{"person_id": str(uuid.uuid4())}]})
    assert before["system"] == "GAS"  # nothing was applied


def test_the_blockers_are_listed_in_the_order_of_doing():
    assert [b.code for b in P.evaluate(P.empty_state())] == [
        "SYSTEM_REQUIRED", "MEDIUM_REQUIRED", "PRESSURE_REQUIRED", "DURATION_REQUIRED", "DROP_REQUIRED", "HELD_ON_REQUIRED", "NO_ATTENDEES", "PHOTOS_REQUIRED", "RESULT_REQUIRED"]
    full = change(changes={"system": "HEATING", "medium": "WATER", "test_pressure_bar": 6, "duration_min": 30, "pressure_drop_bar": 0, "held_on": TODAY,
                           "attendees": [{"person_id": PERSON}], "photo_ids": [PHOTO], "result": "POSITIVE"})
    assert P.evaluate(full) == []
    negative = change(full, {"result": "NEGATIVE"})
    assert [b.code for b in P.evaluate(negative)] == ["REMARKS_REQUIRED"]  # a negative result is explained
    assert P.evaluate(change(negative, {"remarks": "przeciek na złączce"})) == []


def test_an_absent_customer_needs_the_day_he_was_notified_but_still_needs_the_manometer():
    state = change(changes={"system": "SEWER", "medium": "AIR", "test_pressure_bar": 0.5, "duration_min": 15, "pressure_drop_bar": 0.02, "held_on": TODAY, "customer_absent": True,
                            "result": "POSITIVE"})
    assert [b.code for b in P.evaluate(state)] == ["NOTIFIED_ON_REQUIRED", "PHOTOS_REQUIRED"]
    done = change(state, {"notified_on": date(2026, 10, 19), "photo_ids": [PHOTO]})
    assert P.evaluate(done) == []


# --- the draft ---------------------------------------------------------------------------------------------------------------------------


def svc(db):
    return PressureService(db)


async def add_photo(db, w, *, caption="Manometr przy pionie", archived=False, context=PhotoAttachmentContext.ROOM, captured=None):
    asset = raw_asset(w.owner, w.project, status=PhotoAssetStatus.READY, width=1600, height=1200, captured_at=captured)
    db.add(asset)
    await db.flush()
    attachment = PhotoAttachment(
        asset_id=asset.id, project_id=w.project.id, context=context, category=PhotoCategory.GENERAL, caption=caption,
        room_id=w.salon.id if context == PhotoAttachmentContext.ROOM else None,
        surface_id=w.wall.id if context == PhotoAttachmentContext.SURFACE else None,
        archived_at=datetime(2026, 10, 1) if archived else None, position=0,
    )
    db.add(attachment)
    await db.commit()
    return str(attachment.id)


async def test_the_draft_is_one_per_object_numbered_and_records_the_test(db_session):
    w = await ready(db_session, telegram_id=9701)
    photo = await add_photo(db_session, w)
    first, created = await svc(db_session).open_draft(w.project.id, w.owner.id)
    again, created_again = await svc(db_session).open_draft(w.project.id, w.owner.id)
    assert created and not created_again and again.id == first.id and first.sequence == 1 and first.status == "DRAFT"
    row = await svc(db_session).update(w.project.id, first.id, w.owner.id, {
        "system": "COLD_WATER", "section": "łazienka, pion", "medium": "WATER", "test_pressure_bar": "10", "duration_min": 30, "pressure_drop_bar": "0.1",
        "held_on": TODAY, "photo_ids": [photo], "result": "POSITIVE", "attendees": [{"person_id": str(w.person.id)}]})
    read = await svc(db_session).read(row)
    assert read.blockers == [] and read.test_pressure_bar == Decimal("10.00") and read.photo_ids == [photo] and read.section == "łazienka, pion"
    assert photo in [p.id for p in read.photo_options] and next(p for p in read.photo_options if p.id == photo).place == "Salon"
    archived = await svc(db_session).archive_draft(w.project.id, first.id, w.owner.id)
    assert archived.status == "ARCHIVED"
    with pytest.raises(PressureNotEditableError):
        await svc(db_session).update(w.project.id, first.id, w.owner.id, {"section": "x"})
    with pytest.raises(PressureNotEditableError):
        await svc(db_session).archive_draft(w.project.id, first.id, w.owner.id)
    second, _ = await svc(db_session).open_draft(w.project.id, w.owner.id)
    assert second.sequence == 2
    assert [r.id for r in await svc(db_session).list(w.project.id, w.owner.id)] == [second.id]  # an abandoned draft is not listed


async def test_the_photos_offered_are_the_active_ones_of_the_object_and_its_rooms_and_surfaces(db_session):
    w = await ready(db_session, telegram_id=9702)
    room = await add_photo(db_session, w, caption="pokój")
    wall = await add_photo(db_session, w, caption="ściana", context=PhotoAttachmentContext.SURFACE)
    archived = await add_photo(db_session, w, archived=True)
    sources = await load_pressure_sources(db_session, w.owner.id, w.project.id)
    assert {room, wall} <= set(sources.photos) and archived not in sources.photos
    assert sources.photos[wall].place == "Salon › Ściana A" and sources.photos[room].place == "Salon"
    draft, _ = await svc(db_session).open_draft(w.project.id, w.owner.id)
    with pytest.raises(PressureInvalidError) as foreign:
        await svc(db_session).update(w.project.id, draft.id, w.owner.id, {"photo_ids": [str(uuid.uuid4())]})
    assert foreign.value.reason == P.UNKNOWN_PHOTO


async def test_foreign_data_is_refused_and_a_stranger_finds_nothing(db_session):
    mine = await ready(db_session, telegram_id=9703)
    theirs = await ready(db_session, telegram_id=9704)
    foreign_photo = await add_photo(db_session, theirs)
    draft, _ = await svc(db_session).open_draft(mine.project.id, mine.owner.id)
    with pytest.raises(PressureInvalidError) as photo:
        await svc(db_session).update(mine.project.id, draft.id, mine.owner.id, {"photo_ids": [foreign_photo]})
    assert photo.value.reason == P.UNKNOWN_PHOTO
    with pytest.raises(PressureInvalidError) as person:
        await svc(db_session).update(mine.project.id, draft.id, mine.owner.id, {"attendees": [{"person_id": str(theirs.person.id)}]})
    assert person.value.reason == "UNKNOWN_PERSON"
    with pytest.raises(ProjectNotFoundError):
        await svc(db_session).open_draft(mine.project.id, theirs.owner.id)
    with pytest.raises(ProjectNotFoundError):
        await svc(db_session).get(mine.project.id, draft.id, theirs.owner.id)
    with pytest.raises(PressureNotFoundError):
        await svc(db_session).get(mine.project.id, uuid.uuid4(), mine.owner.id)


# --- the document ------------------------------------------------------------------------------------------------------------------------


async def complete_world(db, telegram_id, *, absent=False, result="POSITIVE", extra=None):
    """A world with a client, an executor profile, two photos of the manometer and a draft protocol that passes the gate."""
    w = await ready(db, telegram_id=telegram_id)
    first = await add_photo(db, w, caption="Manometr, początek próby", captured=datetime(2026, 10, 20, 8, 5))
    second = await add_photo(db, w, caption="Manometr, po 30 minutach")
    draft, _ = await svc(db).open_draft(w.project.id, w.owner.id)
    changes = {"system": "HOT_WATER", "section": "łazienka i kuchnia, pion C", "medium": "WATER", "test_pressure_bar": "9.5", "duration_min": 30, "pressure_drop_bar": "0.1",
               "held_on": TODAY, "held_time": "08:15", "photo_ids": [first, second], "result": result}
    if result == "NEGATIVE":
        changes["remarks"] = "Przeciek na złączce – do poprawy <b>przed</b> zakryciem"
    if absent:
        changes.update(customer_absent=True, notified_on=date(2026, 10, 19))
    else:
        changes.update(attendees=[{"person_id": str(w.person.id)}, {"name": "Jan Sąsiad", "role": "administrator"}])
    changes.update(extra or {})
    await svc(db).update(w.project.id, draft.id, w.owner.id, changes)
    return w, draft.id


async def build(db, w, draft_id=None, *, working=False, number="PPC/2026/10/20/0815"):
    sources = await load_pressure_sources(db, w.owner.id, w.project.id)
    row = await db.get(PressureTestProtocol, draft_id) if draft_id else None
    data = data_of(row) if row else {}
    return build_pressure_document(data, sources, working=working, issued_on=TODAY, number=None if working else number, sequence=1), sources, data


def words(html: str) -> str:
    import html as html_lib
    import re

    body = re.sub(r"<style.*?</style>", " ", html, flags=re.S)
    return " ".join(html_lib.unescape(re.sub(r"<[^>]+>", " ", body)).replace(NBSP, " ").split())


def test_a_pressure_is_printed_with_a_comma_and_no_needless_zeros():
    assert bar_text(Decimal("9.50")) == f"9,5{NBSP}bar" and bar_text(Decimal("10.00")) == f"10{NBSP}bar" and bar_text(Decimal("0.00")) == f"0{NBSP}bar" and bar_text(None) is None


async def test_the_page_prints_the_installation_the_numbers_the_manometer_the_result_and_the_people(db_session):
    w, hid = await complete_world(db_session, 9710)
    document, *_ = await build(db_session, w, hid)
    page = words(render_pressure_html(document))
    for expected in ("Protokół próby ciśnieniowej", "PPC/2026/10/20/0815", "Instalacja wody ciepłej — łazienka i kuchnia, pion C", "Woda", "9,5 bar", "30 min", "0,1 bar",
                     "20.10.2026, 08:15", "Anna Nowak", "Jan Sąsiad", "administrator", "Manometr, początek próby", "Manometr, po 30 minutach", "20.10.2026 08:05",
                     "Wynik pozytywny", "Wynik negatywny", "Mokotów", "Zdjęcia manometru"):
        assert expected in page, expected
    assert "☒ Wynik pozytywny" in page and "☐ Wynik negatywny" in page and "WERSJA ROBOCZA" not in page
    assert "Obecni" in page and "jednostronny" not in page


async def test_a_negative_result_prints_the_remarks_escaped_and_a_one_sided_protocol_says_when_the_customer_was_notified(db_session):
    w, hid = await complete_world(db_session, 9711, absent=True, result="NEGATIVE")
    document, *_ = await build(db_session, w, hid)
    html = render_pressure_html(document)
    page = words(html)
    assert "☒ Wynik negatywny" in page and "Przeciek na złączce" in page and "&lt;b&gt;przed&lt;/b&gt;" in html and "<b>przed</b>" not in html
    assert "zawiadomieniu z dnia 19.10.2026" in page and "Protokół jednostronny" in page


async def test_the_working_version_is_a_blank_form_that_never_refuses_and_cannot_be_numbered(db_session):
    w = await ready(db_session, telegram_id=9712)
    document, sources, _ = await build(db_session, w, None, working=True)
    page = words(render_pressure_html(document))
    assert "WERSJA ROBOCZA" in page and "do wypełnienia na miejscu" in page and "Obecni: do wpisania" in page and document.layout.meta.number is None
    assert len(document.photos) == 3 and all(p.taken is None for p in document.photos)  # blank rows to write in
    from app.domain.exceptions import DocumentDataError

    with pytest.raises(DocumentDataError) as numbered:
        build_pressure_document({}, sources, working=True, issued_on=TODAY, number="PPC/1")
    assert numbered.value.reason == "DRAFT_NUMBERED"
    sources.base.executor = None
    with pytest.raises(DocumentDataError) as no_profile:
        build_pressure_document({}, sources, working=False, issued_on=TODAY, number="PPC/1")
    assert no_profile.value.reason == "EXECUTOR_PROFILE_REQUIRED"
    assert build_pressure_document({}, sources, working=True, issued_on=TODAY)


async def test_a_real_pdf_with_the_number(db_session):
    from app.domain.documents.renderer import DocumentRenderer

    w, hid = await complete_world(db_session, 9713)
    document, *_ = await build(db_session, w, hid)
    pdf = (await DocumentRenderer().render(render_pressure_html(document))).pdf
    text_ = " ".join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages).replace(NBSP, " ")
    assert "PPC/2026/10/20/0815" in text_ and "Protokół próby ciśnieniowej" in text_ and "9,5 bar" in text_ and "?" not in text_


def test_the_protocol_is_the_template_of_its_kind():
    template = get_template(DocumentKind.PRESSURE_TEST_PROTOCOL)
    assert (template.number_prefix, template.file, template.version) == ("PPC", "pressure_test_protocol.html.j2", "1")


# --- issuing and freezing ----------------------------------------------------------------------------------------------------------------


async def test_a_protocol_that_is_not_ready_is_refused_with_the_list_and_takes_no_number(db_session):
    w = await ready(db_session, telegram_id=9714)
    draft, _ = await svc(db_session).open_draft(w.project.id, w.owner.id)
    run_ = issuer(delivery=Delivery())
    with pytest.raises(PressureGateError) as refused_:
        await run_.start_pressure_test(db_session, await user_of(db_session, w.owner.id), w.project.id, draft.id)
    assert [b.code for b in refused_.value.blockers] == [
        "SYSTEM_REQUIRED", "MEDIUM_REQUIRED", "PRESSURE_REQUIRED", "DURATION_REQUIRED", "DROP_REQUIRED", "HELD_ON_REQUIRED", "NO_ATTENDEES", "PHOTOS_REQUIRED", "RESULT_REQUIRED"]
    assert all(j.kind != "PRESSURE_TEST_PROTOCOL" for j in await journal(db_session))


async def test_issuing_freezes_the_protocol_numbers_it_sends_the_pdf_and_records_it(db_session):
    w, hid = await complete_world(db_session, 9715)
    telegram, owner_id, project_id = w.owner.telegram_user_id, w.owner.id, w.project.id
    sender = Delivery()
    run_ = issuer(delivery=sender)
    reservation = await run_.start_pressure_test(db_session, await user_of(db_session, w.owner.id), w.project.id, hid)
    assert (reservation.document.kind, reservation.document.status, reservation.document.source_id, reservation.document.source_version) == ("PRESSURE_TEST_PROTOCOL", "PENDING", hid, 1)
    assert reservation.document.number.startswith("PPC/2026/10/08/")
    await run_.drain()
    done = [j for j in await journal(db_session) if j.kind == "PRESSURE_TEST_PROTOCOL"][0]
    assert (done.status, done.error_code, done.title) == ("SENT", None, "Protokół próby ciśnieniowej — nr 1")
    number = done.number
    message = sender.sent[-1]
    assert message["chat_id"] == telegram and message["filename"].startswith("PPC-2026-10-08-") and number in text_of(message["pdf"])
    db_session.expire_all()
    row = await db_session.get(PressureTestProtocol, hid)
    assert row.status == "ISSUED" and row.issued_at is not None and number in row.document_html
    snap = row.snapshot
    assert (snap["system"], snap["medium"], snap["test_pressure_bar"], snap["duration_min"], snap["pressure_drop_bar"], snap["result"]) == ("HOT_WATER", "WATER", "9.50", 30, "0.10", "POSITIVE")
    assert [p["caption"] for p in snap["photos"]] == ["Manometr, początek próby", "Manometr, po 30 minutach"] and snap["photos"][0]["place"] == "Salon"
    with pytest.raises(PressureNotEditableError):
        await PressureService(db_session).update(project_id, hid, owner_id, {"section": "inna"})
    with pytest.raises(PressureNotEditableError):
        await run_.start_pressure_test(db_session, await user_of(db_session, owner_id), project_id, hid)
    with pytest.raises(PressureNotEditableError):
        await PressureService(db_session).mark_issued(project_id, hid, owner_id, issued_at=run_.clock(), snapshot={}, document_html="<html></html>")
    assert (await svc(db_session).open_draft(project_id, owner_id))[0].sequence == 2


async def test_the_issued_page_does_not_change_when_the_photos_or_the_data_do(db_session):
    w, hid = await complete_world(db_session, 9716)
    run_ = issuer(delivery=Delivery())
    await run_.start_pressure_test(db_session, await user_of(db_session, w.owner.id), w.project.id, hid)
    await run_.drain()
    db_session.expire_all()
    frozen = (await db_session.get(PressureTestProtocol, hid)).document_html
    attachment = (await db_session.execute(select(PhotoAttachment).where(PhotoAttachment.caption == "Manometr, początek próby"))).scalar_one()
    attachment.caption = "zmieniony opis"
    await db_session.commit()
    pdf = await run_.render_document(db_session, (await journal(db_session))[-1]) if hasattr(run_, "render_document") else None
    db_session.expire_all()
    assert (await db_session.get(PressureTestProtocol, hid)).document_html == frozen and "zmieniony opis" not in frozen
    assert pdf is None or pdf


async def test_the_preview_follows_the_draft_and_never_leaves_a_row(db_session):
    w, hid = await complete_world(db_session, 9717)
    sender = Delivery()
    run_ = issuer(delivery=sender)
    result = await run_.preview_pressure_test(db_session, await user_of(db_session, w.owner.id), w.project.id)
    assert result.pages >= 1
    sent = sender.sent[-1]
    assert sent["filename"] == "Protokol-proby-cisnieniowej-wersja-robocza.pdf" and sent["caption"].startswith("WERSJA ROBOCZA — Protokół próby ciśnieniowej")
    assert "9,5 bar" in text_of(sent["pdf"]) and "WERSJA ROBOCZA" in text_of(sent["pdf"])
    assert all(j.kind != "PRESSURE_TEST_PROTOCOL" for j in await journal(db_session))
    blank = await ready(db_session, telegram_id=9718)
    await run_.preview_pressure_test(db_session, await user_of(db_session, blank.owner.id), blank.project.id)
    assert "9,5 bar" not in text_of(sender.sent[-1]["pdf"])


# --- the API -----------------------------------------------------------------------------------------------------------------------------


def url(project_id, tail=""):
    return f"/api/projects/{project_id}/pressure-tests{tail}"


async def test_the_routes_need_a_token_and_a_stranger_gets_404(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    mine = await ready(db_session, telegram_id=OWNER_TG)
    theirs = await ready(db_session, telegram_id=STRANGER_TG)
    use_issuer(issuer(delivery=Delivery()))
    assert (await async_client.get(url(mine.project.id))).status_code == 401
    assert (await async_client.post(f"/api/projects/{mine.project.id}/documents/pressure-test/preview")).status_code == 401
    headers = await login(async_client)
    draft, _ = await svc(db_session).open_draft(theirs.project.id, theirs.owner.id)
    for response in (
        await async_client.get(url(theirs.project.id), headers=headers),
        await async_client.post(url(theirs.project.id), headers=headers),
        await async_client.post(url(theirs.project.id, f"/{draft.id}/issue"), headers=headers),
        await async_client.post(f"/api/projects/{theirs.project.id}/documents/pressure-test/preview", headers=headers),
        await async_client.get(url(mine.project.id, f"/{uuid.uuid4()}"), headers=headers),
        await async_client.get(url(mine.project.id, f"/{draft.id}"), headers=headers),
    ):
        assert response.status_code == 404


async def test_open_record_issue_and_abandon_over_http(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await ready(db_session, telegram_id=OWNER_TG)
    photo = await add_photo(db_session, w, caption="Manometr 10 bar")
    sender = Delivery()
    run_ = use_issuer(issuer(delivery=sender))
    headers = await login(async_client)
    pid = str(w.project.id)
    created = await async_client.post(url(pid), headers=headers)
    assert created.status_code == 201, created.text
    body = created.json()
    assert (body["sequence"], body["status"], body["photo_ids"], body["customer_absent"], body["test_pressure_bar"]) == (1, "DRAFT", [], False, None)
    assert (await async_client.post(url(pid), headers=headers)).status_code == 200
    hid = body["id"]
    assert (await async_client.patch(url(pid, f"/{hid}"), json={}, headers=headers)).status_code == 422
    assert (await async_client.patch(url(pid, f"/{hid}"), json={"unknown": 1}, headers=headers)).status_code == 422
    bad = await async_client.patch(url(pid, f"/{hid}"), json={"test_pressure_bar": "abc"}, headers=headers)
    assert bad.status_code == 422 and bad.json()["detail"] == {"code": "PRESSURE_INVALID", "message": "pressure test 'test_pressure_bar': WRONG_TYPE",
                                                              "details": {"key": "test_pressure_bar", "reason": "WRONG_TYPE"}}
    saved = await async_client.patch(url(pid, f"/{hid}"), json={
        "system": "HEATING", "section": "grzejniki, piętro", "medium": "WATER", "test_pressure_bar": 6, "duration_min": 60, "pressure_drop_bar": "0,2", "held_on": "2026-10-20",
        "photo_ids": [photo], "result": "POSITIVE", "customer_absent": True, "notified_on": "2026-10-19"}, headers=headers)
    assert saved.status_code == 200, saved.text
    got = saved.json()
    assert (got["test_pressure_bar"], got["pressure_drop_bar"], got["duration_min"], got["blockers"]) == ("6.00", "0.20", 60, [])
    assert photo in [p["id"] for p in got["photo_options"]]
    ok = await async_client.post(url(pid, f"/{hid}/issue"), headers=headers)
    assert ok.status_code == 202, ok.text
    assert ok.json()["kind"] == "PRESSURE_TEST_PROTOCOL" and ok.json()["number"].startswith("PPC/") and ok.json()["source_id"] == hid
    await run_.drain()
    again = await async_client.post(url(pid, f"/{hid}/issue"), headers=headers)
    assert again.status_code == 409 and again.json()["detail"]["code"] == "PRESSURE_NOT_EDITABLE"
    listed = (await async_client.get(f"/api/projects/{pid}/documents", headers=headers)).json()
    assert [d["kind"] for d in listed["items"]].count("PRESSURE_TEST_PROTOCOL") == 1
    second = (await async_client.post(url(pid), headers=headers)).json()
    blocked = await async_client.post(url(pid, f"/{second['id']}/issue"), headers=headers)
    assert blocked.status_code == 422 and blocked.json()["detail"]["code"] == "PRESSURE_GATE_BLOCKED"
    assert blocked.json()["detail"]["details"]["blockers"][0]["code"] == "SYSTEM_REQUIRED"
    gone = await async_client.post(url(pid, f"/{second['id']}/archive"), headers=headers)
    assert gone.status_code == 200 and gone.json()["status"] == "ARCHIVED"
    assert [i["id"] for i in (await async_client.get(url(pid), headers=headers)).json()["items"]] == [hid]
    preview = await async_client.post(f"/api/projects/{pid}/documents/pressure-test/preview", headers=headers)
    assert preview.status_code == 200 and preview.json()["sent"] is True


async def test_the_manometer_photo_of_an_issued_protocol_is_protected_from_purging_and_that_of_an_abandoned_draft_is_not(db_session):
    from app.domain.rules.purge_rules import ProtocolRef, photo_blockers
    from app.domain.services.photo_purge_service import PhotoPurgeService

    w, hid = await complete_world(db_session, 9719)
    row = await db_session.get(PressureTestProtocol, hid)
    chosen = uuid.UUID(row.photo_ids[0])
    refs = await PhotoPurgeService(db_session, None).protocol_refs(w.project.id)
    mine = [r for r in refs if r.kind == "PRESSURE_TEST"]
    assert len(mine) == 1 and mine[0].id == hid and mine[0].status == "DRAFT" and str(chosen) in mine[0].photo_ids
    assert [b.kind for b in photo_blockers(chosen, [ProtocolRef("PRESSURE_TEST", hid, "ISSUED", frozenset(row.photo_ids))])] == ["PRESSURE_TEST"]
    assert photo_blockers(chosen, [ProtocolRef("PRESSURE_TEST", hid, "ARCHIVED", frozenset(row.photo_ids))]) == []


# --- the migration -----------------------------------------------------------------------------------------------------------------------


def test_revision_chain_and_length():
    module = load_migration("0082_pressure_tests")
    assert module.revision == "0082_pressure_tests" and module.down_revision == "0081_installation_map_doc" and len(module.revision) <= 32


def engine_0082():
    engine = contract_engine()
    for name in ("0045_contract_issue", "0046_contract_signed", "0047_handover_protocols", "0048_handover_issue", "0049_concealed_works", "0082_pressure_tests"):
        run(engine, name, "upgrade")
    return engine


ROW = ("INSERT INTO pressure_test_protocols (id, owner_id, project_id, sequence, status, customer_absent, attendees, photo_ids, system, medium, result, test_pressure_bar, duration_min, "
       "pressure_drop_bar, issued_at, snapshot, document_html, created_at, updated_at) VALUES (:id, 'u1', 'p1', :sequence, :status, 0, '[]', '[]', :system, :medium, :result, "
       ":pressure, :duration, :drop, :issued, :snapshot, :html, '2026-11-02', '2026-11-02')")
JOURNAL = ("INSERT INTO issued_documents (id, owner_id, project_id, kind, title, number, project_seq, template_version, status, issued_at) "
           "VALUES (:id, 'u1', 'p1', :kind, 't', :number, :seq, '1', 'SENT', '2026-11-02')")
BLANK = {"system": None, "medium": None, "result": None, "pressure": None, "duration": None, "drop": None, "issued": None, "snapshot": None, "html": None}
FROZEN = {**BLANK, "issued": "2026-11-02", "snapshot": "{}", "html": "<html></html>"}


def test_the_database_allows_one_draft_a_sequence_once_known_values_and_a_frozen_issued_protocol():
    engine = engine_0082()
    with engine.begin() as conn:
        conn.execute(text(ROW), {"id": "a", "sequence": 1, "status": "DRAFT", **BLANK})
        conn.execute(text(ROW), {"id": "b", "sequence": 2, "status": "ARCHIVED", **BLANK})
        conn.execute(text(ROW), {"id": "c", "sequence": 3, "status": "ISSUED", **FROZEN, "system": "GAS", "medium": "AIR", "result": "NEGATIVE", "pressure": 0.5, "duration": 15, "drop": 0})
        conn.execute(text(JOURNAL), {"id": "j", "kind": "PRESSURE_TEST_PROTOCOL", "number": "PPC/1", "seq": 1})
    for bad in (
        {"id": "d", "sequence": 4, "status": "DRAFT", **BLANK},  # a second draft
        {"id": "e", "sequence": 1, "status": "ARCHIVED", **BLANK},  # a repeated number
        {"id": "f", "sequence": 5, "status": "SIGNED", **BLANK},
        {"id": "g", "sequence": 0, "status": "ARCHIVED", **BLANK},
        {"id": "h", "sequence": 6, "status": "ISSUED", **BLANK},  # issued without its page
        {"id": "i", "sequence": 7, "status": "ARCHIVED", **{**BLANK, "system": "STEAM"}},
        {"id": "k", "sequence": 8, "status": "ARCHIVED", **{**BLANK, "medium": "OIL"}},
        {"id": "l", "sequence": 9, "status": "ARCHIVED", **{**BLANK, "result": "OK"}},
        {"id": "m", "sequence": 10, "status": "ARCHIVED", **{**BLANK, "pressure": 0}},
        {"id": "n", "sequence": 11, "status": "ARCHIVED", **{**BLANK, "pressure": 100.5}},
        {"id": "o", "sequence": 12, "status": "ARCHIVED", **{**BLANK, "duration": 0}},
        {"id": "p", "sequence": 13, "status": "ARCHIVED", **{**BLANK, "duration": 1441}},
        {"id": "q", "sequence": 14, "status": "ARCHIVED", **{**BLANK, "drop": -0.1}},
    ):
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(text(ROW), bad)
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text(JOURNAL), {"id": "r", "kind": "OTHER", "number": "X/1", "seq": 2})
    assert {c["name"] for c in inspect(engine).get_columns("pressure_test_protocols")} == {c.name for c in PressureTestProtocol.__table__.columns}


def test_downgrade_refuses_while_a_protocol_or_a_journal_row_exists_and_then_works():
    engine = engine_0082()
    with engine.begin() as conn:
        conn.execute(text(ROW), {"id": "a", "sequence": 1, "status": "DRAFT", **BLANK})
    with pytest.raises(RuntimeError, match="1 pressure test protocol"):
        run(engine, "0082_pressure_tests", "downgrade")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM pressure_test_protocols"))
        conn.execute(text(JOURNAL), {"id": "j", "kind": "PRESSURE_TEST_PROTOCOL", "number": "PPC/1", "seq": 1})
    with pytest.raises(RuntimeError, match="1 journal row"):
        run(engine, "0082_pressure_tests", "downgrade")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM issued_documents"))
    run(engine, "0082_pressure_tests", "downgrade")
    assert "pressure_test_protocols" not in inspect(engine).get_table_names()
    run(engine, "0082_pressure_tests", "upgrade")


def test_the_check_of_the_migration_is_the_check_of_the_model():
    from app.models.issued_document import IssuedDocument

    module = load_migration("0082_pressure_tests")
    model = next(c for c in IssuedDocument.__table__.constraints if getattr(c, "name", None) == "ck_issued_documents_kind")
    assert " ".join(module.KINDS_NEW.split()) == " ".join(str(model.sqltext).split())


def engine_0083():
    engine = engine_0082()
    run(engine, "0083_pressure_encrypted_text", "upgrade")
    return engine


def test_the_hotfix_migration_chain_and_that_every_encrypted_column_is_text():
    module = load_migration("0083_pressure_encrypted_text")
    assert module.revision == "0083_pressure_encrypted_text" and module.down_revision == "0082_pressure_tests" and len(module.revision) <= 32
    from app.domain.services.data_reencode_service import encrypted_columns  # the registry the verification of the encryption walks

    engine = engine_0083()
    types = {c["name"]: str(c["type"]).upper() for c in inspect(engine).get_columns("pressure_test_protocols")}
    ours = [c.column for c in encrypted_columns() if c.table == "pressure_test_protocols"]
    assert sorted(ours) == ["attendees", "document_html", "remarks", "section", "snapshot"]
    # the encryption stores `enc1:...` and counts with LIKE: a JSON(B) column breaks both on a real PostgreSQL (found on the first production run)
    assert {name: types[name] for name in ours} == dict.fromkeys(ours, "TEXT")


def test_encrypted_text_survives_in_the_two_columns_and_the_downgrade_refuses_only_while_it_is_stored():
    engine = engine_0083()
    with engine.begin() as conn:
        conn.execute(text(ROW.replace("'[]', '[]'", "'enc1:abc', '[]'")), {"id": "a", "sequence": 1, "status": "ISSUED", **FROZEN, "snapshot": "enc1:def"})
    with pytest.raises(RuntimeError, match="2 value"):
        run(engine, "0083_pressure_encrypted_text", "downgrade")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM pressure_test_protocols"))
        conn.execute(text(ROW), {"id": "b", "sequence": 1, "status": "ARCHIVED", **BLANK})
    run(engine, "0083_pressure_encrypted_text", "downgrade")
    run(engine, "0083_pressure_encrypted_text", "upgrade")
