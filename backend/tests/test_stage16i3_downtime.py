"""Stage 16I.3: the notice and the protocol of downtime on the customer's side -- the rules, the sum for readiness, the episode, the two
documents, issuing and freezing, the API and the migration."""
import io
import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient
from pypdf import PdfReader
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.domain.contracts.catalog import load_contract_catalog
from app.domain.documents.downtime_document import build_notice_document, build_protocol_document, render_notice_html, render_protocol_html
from app.domain.documents.registry import TEMPLATES, DocumentKind
from app.domain.documents.renderer import DocumentRenderer
from app.domain.exceptions import DowntimeGateError, DowntimeInvalidError, DowntimeNotEditableError, DowntimeNotFoundError, ProjectNotFoundError
from app.domain.protocols import downtime as D
from app.domain.protocols.sources import load_downtime_sources
from app.domain.services.downtime_service import DowntimeService, data_of
from app.models.contract import Contract
from app.models.downtime_episode import DowntimeEpisode
from app.models.photo_asset import PhotoAssetStatus
from app.models.photo_attachment import PhotoAttachment, PhotoAttachmentContext, PhotoCategory
from app.models.project import Project
from tests.test_stage14b4_photo_asset import raw_asset
from tests.test_stage15f2_api import use_issuer  # noqa: F401  (a fixture)
from tests.test_stage15f2_issuing import Delivery, issuer, journal, text_of, user_of
from tests.test_stage16e2_contract import OWNER_TG, STRANGER_TG, contract_engine, load_migration, login, ready, run
from tests.test_stage16e4_signing import issued

CATALOG = load_contract_catalog()
NOTICE_DAY, HELD = date(2026, 10, 12), date(2026, 10, 19)  # a Monday, the Monday after
ROOM, PHOTO = str(uuid.uuid4()), str(uuid.uuid4())
PERSON = str(uuid.uuid4())
PEOPLE = {PERSON: ("Anna Nowak", "Właścicielka")}


def change(current=None, changes=None, *, status="DRAFT", rooms=(ROOM,), photos=None, people=PEOPLE):
    photos = {PHOTO} if photos is None else photos
    return D.apply_changes(current or D.empty_state(), changes or {}, status=status, room_ids=set(rooms), photos_of=lambda _rooms: set(photos),
                           people=people, catalog=CATALOG)


def refused(**kw):
    with pytest.raises(DowntimeInvalidError) as exc:
        change(**kw)
    return exc.value.key, exc.value.reason


def noticed_state(**over):
    return {**D.empty_state(), "cause_key": "no_access", "noticed_on": NOTICE_DAY, "need_text": "Klucze do lokalu", "photo_ids": [PHOTO], **over}


# --- the rules: the entries -------------------------------------------------------------------------------------------------------------------


def test_the_notice_entries_are_checked_normalised_and_cleared():
    state = change(changes={"cause_key": "no_utilities", "cause_note": " brak prądu ", "room_ids": [ROOM, ROOM], "noticed_on": NOTICE_DAY, "noticed_time": "08:30",
                            "notice_channel": "  e-mail  ", "photo_ids": [PHOTO, PHOTO], "need_text": "Włączyć prąd", "need_by": date(2026, 10, 14)})
    assert (state["cause_key"], state["cause_note"], state["room_ids"], state["photo_ids"], state["notice_channel"]) == (
        "no_utilities", "brak prądu", [ROOM], [PHOTO], "e-mail")
    cleared = change(state, {"cause_key": None, "noticed_time": None, "need_by": None, "photo_ids": None, "room_ids": None, "notice_channel": None})
    assert (cleared["cause_key"], cleared["noticed_time"], cleared["need_by"], cleared["photo_ids"], cleared["room_ids"]) == (None, None, None, [], [])
    assert refused(changes={"cause_key": "weather"}) == ("cause_key", D.UNKNOWN_CAUSE)
    assert refused(changes={"noticed_time": "8:30"}) == ("noticed_time", "BAD_TIME")
    assert refused(changes={"noticed_on": "2026-10-12"}) == ("noticed_on", "WRONG_TYPE")
    assert refused(changes={"need_text": 5}) == ("need_text", "WRONG_TYPE")
    assert refused(changes={"notice_channel": "x" * 256}) == ("notice_channel", "TOO_LONG")
    assert refused(changes={"need_text": "x" * 4001}) == ("need_text", "TOO_LONG")
    assert refused(changes={"room_ids": [str(uuid.uuid4())]}) == ("room_ids", D.UNKNOWN_ROOM)
    assert refused(changes={"room_ids": ["x"]}) == ("room_ids", "WRONG_TYPE")
    assert refused(changes={"room_ids": "all"}) == ("room_ids", "WRONG_TYPE")
    assert refused(changes={"photo_ids": [str(uuid.uuid4())]}) == ("photo_ids", D.UNKNOWN_PHOTO)
    assert refused(changes={"nonsense": 1}) == ("nonsense", D.UNKNOWN_FIELD)


def test_the_photos_are_those_of_the_rooms_as_they_will_be_and_a_room_change_drops_the_ones_that_no_longer_belong():
    state = change(changes={"photo_ids": [PHOTO]})
    assert state["photo_ids"] == [PHOTO]
    dropped = D.apply_changes(state, {"room_ids": [ROOM]}, status="DRAFT", room_ids={ROOM}, photos_of=lambda rooms: set() if rooms else {PHOTO},
                              people=PEOPLE, catalog=CATALOG)
    assert dropped["photo_ids"] == []  # the rooms were chosen and the photo is not among theirs
    both = D.apply_changes(state, {"room_ids": [ROOM], "photo_ids": [PHOTO]}, status="DRAFT", room_ids={ROOM}, photos_of=lambda rooms: {PHOTO},
                           people=PEOPLE, catalog=CATALOG)
    assert both["photo_ids"] == [PHOTO]


def test_the_notice_is_changed_only_while_a_draft_and_the_protocol_only_once_noticed_and_nothing_after():
    assert refused(changes={"days": {"2026-10-14": {}}}) == ("days", D.NOT_NOTICED_YET)  # a draft has no protocol yet
    assert refused(changes={"held_on": HELD}) == ("held_on", D.NOT_NOTICED_YET)
    assert refused(changes={"signature_refused": True}) == ("signature_refused", D.NOT_NOTICED_YET)
    frozen = noticed_state()
    for key, value in (("cause_key", "other"), ("need_text", "x"), ("noticed_on", NOTICE_DAY), ("room_ids", []), ("photo_ids", [])):
        with pytest.raises(DowntimeInvalidError) as exc:
            change(frozen, {key: value}, status="NOTICED")
        assert (exc.value.key, exc.value.reason) == (key, D.NOTICE_FROZEN)
    again = change(frozen, {"notes": "uwagi"}, status="NOTICED")
    assert again["photo_ids"] == [PHOTO] and again["notes"] == "uwagi"  # the photos of the issued notice stay


def test_the_days_are_after_the_notice_working_days_each_once_in_order_with_their_answer_about_other_work():
    frozen = noticed_state()
    state = change(frozen, {"days": {"2026-10-15": {"other_work": True, "note": "  malowanie w kuchni "}, "2026-10-14": {}, "2026-10-16": {"other_work": None}}},
                   status="NOTICED")
    assert state["days"] == [
        {"date": "2026-10-14", "other_work": False},  # no answer yet: no other work
        {"date": "2026-10-15", "other_work": True, "note": "malowanie w kuchni"},
        {"date": "2026-10-16", "other_work": False},
    ]
    moved = change(state, {"days": {"2026-10-14": {"other_work": True}, "2026-10-15": {"note": None}}}, status="NOTICED")
    assert moved["days"][0]["other_work"] is True and moved["days"][1] == {"date": "2026-10-15", "other_work": True}
    assert [d["date"] for d in change(state, {"days": {"2026-10-15": None}}, status="NOTICED")["days"]] == ["2026-10-14", "2026-10-16"]
    assert change(state, {"days": {"2026-10-20": None}}, status="NOTICED")["days"] == state["days"]  # removing a day that is not there is no error
    for bad in ("2026-10-12", "2026-10-11", "2026-10-17", "2026-10-18"):  # the day of the notice, before it, a Saturday, a Sunday
        assert refused(current=frozen, changes={"days": {bad: {}}}, status="NOTICED") == ("days", D.BAD_DAY), bad
    assert refused(current=frozen, changes={"days": {"jutro": {}}}, status="NOTICED") == ("days", D.BAD_DAY)
    assert refused(current=frozen, changes={"days": {"2026-10-14": {"colour": 1}}}, status="NOTICED") == ("days", "WRONG_TYPE")
    assert refused(current=frozen, changes={"days": {"2026-10-14": {"other_work": "yes"}}}, status="NOTICED") == ("other_work", "WRONG_TYPE")
    assert refused(current=frozen, changes={"days": {"2026-10-14": {"note": "x" * 501}}}, status="NOTICED") == ("note", "TOO_LONG")
    assert refused(current=frozen, changes={"days": ["2026-10-14"]}, status="NOTICED") == ("days", "WRONG_TYPE")
    assert refused(current=D.empty_state(), changes={"days": {"2026-10-14": {}}}, status="NOTICED") == ("days", D.BAD_DAY)  # no notice day recorded
    with pytest.raises(DowntimeInvalidError):  # a failed change changes nothing
        change(state, {"notes": "nowe", "days": {"2026-10-17": {}}}, status="NOTICED")
    assert state["notes"] is None


def test_the_protocol_entries_are_checked():
    frozen = noticed_state()
    state = change(frozen, {"held_on": HELD, "held_time": "09:00", "attendees": [{"person_id": PERSON}, {"name": "Jan Sąsiad", "role": "administrator"}],
                            "signature_refused": None, "deadline_note": " termin przesuwa się ", "notes": "ok"}, status="NOTICED")
    assert (state["held_time"], state["signature_refused"], state["deadline_note"], [a["name"] for a in state["attendees"]]) == (
        "09:00", False, "termin przesuwa się", ["Anna Nowak", "Jan Sąsiad"])
    assert refused(current=frozen, changes={"held_time": "9:00"}, status="NOTICED") == ("held_time", "BAD_TIME")
    assert refused(current=frozen, changes={"signature_refused": "no"}, status="NOTICED") == ("signature_refused", "WRONG_TYPE")
    assert refused(current=frozen, changes={"attendees": [{"person_id": str(uuid.uuid4())}]}, status="NOTICED") == ("attendees", "UNKNOWN_PERSON")
    assert refused(current=frozen, changes={"deadline_note": 5}, status="NOTICED") == ("deadline_note", "WRONG_TYPE")


# --- the rules: what is missing ------------------------------------------------------------------------------------------------------------


def codes(blockers):
    return [b.code for b in blockers]


def test_the_notice_blockers_are_listed_in_the_order_of_doing():
    assert codes(D.evaluate_notice(D.empty_state())) == [D.CAUSE_REQUIRED, D.NOTICED_ON_REQUIRED, D.NEED_REQUIRED, D.PHOTOS_REQUIRED]
    assert D.evaluate_notice(noticed_state()) == []
    assert codes(D.evaluate_notice(noticed_state(cause_key="other"))) == [D.CAUSE_NOTE_REQUIRED]
    assert D.evaluate_notice(noticed_state(cause_key="other", cause_note="Spór sąsiedzki")) == []
    assert codes(D.evaluate_notice(noticed_state(photo_ids=[]))) == [D.PHOTOS_REQUIRED]


def test_the_protocol_blockers_are_listed_in_the_order_of_doing():
    ready_state = noticed_state(days=[{"date": "2026-10-14", "other_work": False}], held_on=HELD, attendees=[{"person_id": None, "name": "A", "role": None}])
    assert D.evaluate_protocol(ready_state) == []
    assert codes(D.evaluate_protocol(noticed_state())) == [D.DAYS_REQUIRED, D.HELD_ON_REQUIRED, D.NO_ATTENDEES]
    late = D.evaluate_protocol({**ready_state, "held_on": date(2026, 10, 13)})
    assert [(b.code, b.details) for b in late] == [(D.DAY_AFTER_PROTOCOL, {"days": ["2026-10-14"]})]
    assert D.evaluate_protocol({**ready_state, "held_on": date(2026, 10, 14)}) == []  # the day of the protocol itself is fine
    assert codes(D.evaluate_protocol({**ready_state, "signature_refused": True})) == [D.REFUSAL_NOTE_REQUIRED]
    assert D.evaluate_protocol({**ready_state, "signature_refused": True, "notes": "Odmówił podpisu"}) == []


# --- the sum for readiness ------------------------------------------------------------------------------------------------------------------


def contract(rate="150.00", cap="10", total="12000.00", limit=3):
    answers = {"downtime_rate_per_day": rate, "downtime_cap_percent": cap, "downtime_days_limit": limit}
    return {"answers": {k: v for k, v in answers.items() if v is not None}, "estimate": {"total": total}}


def day(n, other=False):
    return {"date": f"2026-10-{n:02d}", "other_work": other}


def test_the_sum_is_the_rate_times_the_days_without_other_work_not_more_than_the_cap():
    s = D.settlement([day(14), day(15, other=True), day(16)], contract())
    assert (s["listed"], s["chargeable"], s["rate"], s["amount"], s["cap"], s["capped"], s["payable"]) == (
        3, 2, Decimal("150.00"), Decimal("300.00"), Decimal("1200.00"), False, Decimal("300.00"))
    capped = D.settlement([day(n) for n in range(12, 22)], contract(rate="400", cap="10", total="12000"))
    assert (capped["amount"], capped["cap"], capped["capped"], capped["payable"]) == (Decimal("4000.00"), Decimal("1200.00"), True, Decimal("1200.00"))
    exact = D.settlement([day(14), day(15), day(16)], contract(rate="400"))
    assert (exact["amount"], exact["capped"], exact["payable"]) == (Decimal("1200.00"), False, Decimal("1200.00"))  # as much as the cap is not over it
    assert D.settlement([day(14, other=True)], contract())["payable"] == Decimal("0.00")


def test_what_the_contract_leaves_empty_stays_empty_and_nothing_is_invented():
    no_rate = D.settlement([day(14)], contract(rate=None))
    assert (no_rate["rate"], no_rate["amount"], no_rate["payable"]) == (None, None, None) and no_rate["chargeable"] == 1
    no_cap = D.settlement([day(14)], contract(cap=None))
    assert (no_cap["cap"], no_cap["capped"], no_cap["payable"]) == (None, False, Decimal("150.00"))
    no_total = D.settlement([day(14)], contract(total=None))
    assert (no_total["cap"], no_total["payable"]) == (None, Decimal("150.00"))
    empty = D.settlement([day(14)], None)
    assert (empty["rate"], empty["amount"], empty["cap"], empty["limit_days"], empty["limit_exceeded"]) == (None, None, None, None, False)
    assert D.settlement([day(14)], contract(rate="abc"))["rate"] is None and D.settlement([day(14)], contract(rate=True))["rate"] is None
    assert D.settlement([day(14)], contract(rate="150,5"))["rate"] == Decimal("150.5")  # a comma is a decimal point


def test_the_amounts_are_rounded_half_up_to_the_grosz_and_the_limit_of_days_is_the_contracts_own():
    assert D.settlement([day(14)], contract(rate="100.005", cap=None))["amount"] == Decimal("100.01")
    assert D.settlement([day(14)], contract(rate="33.333", cap="1", total="333.33"))["cap"] == Decimal("3.33")
    days = [day(14), day(15), day(16)]
    assert D.settlement(days, contract(limit=3))["limit_exceeded"] is False  # three days of a limit of three: not past it
    over = D.settlement(days + [day(19)], contract(limit=3))
    assert (over["limit_days"], over["limit_exceeded"]) == (3, True)
    assert D.settlement(days, contract(limit=None))["limit_days"] is None  # the open field: nothing to exceed
    assert D.settlement([day(14, other=True)] * 4, contract(limit=3))["limit_exceeded"] is True  # the limit counts the days of the obstacle, paid or not


# --- the episode ---------------------------------------------------------------------------------------------------------------------------


def svc(db):
    return DowntimeService(db)


async def add_photo(db, w, *, context, caption="Zamknięte drzwi", **targets):
    asset = raw_asset(w.owner, w.project, status=PhotoAssetStatus.READY, width=1600, height=1200)
    db.add(asset)
    await db.flush()
    attachment = PhotoAttachment(asset_id=asset.id, project_id=w.project.id, context=context, category=PhotoCategory.GENERAL, caption=caption,
                                 position=0, **targets)
    db.add(attachment)
    await db.commit()
    return str(attachment.id)


async def test_the_open_episode_is_one_per_object_numbered_and_its_photos_follow_the_rooms(db_session):
    w = await ready(db_session, telegram_id=9951)
    whole = await add_photo(db_session, w, context=PhotoAttachmentContext.PROJECT, caption="Brama")
    salon = await add_photo(db_session, w, context=PhotoAttachmentContext.ROOM, room_id=w.salon.id, caption="Drzwi do salonu")
    kitchen = await add_photo(db_session, w, context=PhotoAttachmentContext.ROOM, room_id=w.kuchnia.id, caption="Kuchnia bez wody")
    on_wall = await add_photo(db_session, w, context=PhotoAttachmentContext.SURFACE, surface_id=w.wall.id, caption="Ściana w salonie")
    first, created = await svc(db_session).open_episode(w.project.id, w.owner.id)
    again, created_again = await svc(db_session).open_episode(w.project.id, w.owner.id)
    assert created and not created_again and again.id == first.id and first.sequence == 1 and first.status == "DRAFT"
    read = await svc(db_session).read(first)
    options = {o.id for o in read.photo_options}
    assert {whole, salon, kitchen, on_wall} <= options  # no room chosen: the whole object
    assert [r.name for r in read.rooms] == ["Salon", "Kuchnia"] and read.cause_text is None and read.days == []
    row = await svc(db_session).update(w.project.id, first.id, w.owner.id, {"room_ids": [str(w.kuchnia.id)], "photo_ids": [whole, kitchen]})
    read = await svc(db_session).read(row)
    options = {o.id for o in read.photo_options}
    assert {whole, kitchen} <= options and not {salon, on_wall} & options  # the object's own and the kitchen's, not the salon's
    assert {p.id for p in read.photos} == {whole, kitchen}
    with pytest.raises(DowntimeInvalidError) as other_room:
        await svc(db_session).update(w.project.id, first.id, w.owner.id, {"photo_ids": [salon]})
    assert other_room.value.reason == D.UNKNOWN_PHOTO
    row = await svc(db_session).update(w.project.id, first.id, w.owner.id, {"room_ids": [str(w.salon.id)]})
    assert set(row.photo_ids) == {whole}  # the kitchen's photo went with the kitchen
    archived = await svc(db_session).archive(w.project.id, first.id, w.owner.id)
    assert archived.status == "ARCHIVED"
    assert (await svc(db_session).open_episode(w.project.id, w.owner.id))[0].sequence == 2


async def test_foreign_data_is_refused_and_a_stranger_finds_nothing(db_session):
    mine = await ready(db_session, telegram_id=9952)
    theirs = await ready(db_session, telegram_id=9953)
    their_photo = await add_photo(db_session, theirs, context=PhotoAttachmentContext.PROJECT)
    first, _ = await svc(db_session).open_episode(mine.project.id, mine.owner.id)
    with pytest.raises(DowntimeInvalidError) as foreign_photo:
        await svc(db_session).update(mine.project.id, first.id, mine.owner.id, {"photo_ids": [their_photo]})
    assert foreign_photo.value.reason == D.UNKNOWN_PHOTO
    with pytest.raises(DowntimeInvalidError) as foreign_room:
        await svc(db_session).update(mine.project.id, first.id, mine.owner.id, {"room_ids": [str(theirs.salon.id)]})
    assert foreign_room.value.reason == D.UNKNOWN_ROOM
    with pytest.raises(ProjectNotFoundError):
        await svc(db_session).open_episode(mine.project.id, theirs.owner.id)
    with pytest.raises(ProjectNotFoundError):
        await svc(db_session).get(mine.project.id, first.id, theirs.owner.id)
    with pytest.raises(DowntimeNotFoundError):
        await svc(db_session).get(mine.project.id, uuid.uuid4(), mine.owner.id)
    other, _ = await svc(db_session).open_episode(theirs.project.id, theirs.owner.id)
    with pytest.raises(DowntimeNotFoundError):
        await svc(db_session).get(mine.project.id, other.id, mine.owner.id)
    assert their_photo not in (await load_downtime_sources(db_session, mine.owner.id, mine.project.id)).photos


# --- the documents -------------------------------------------------------------------------------------------------------------------------


async def set_answers(db, contract_id, **answers):
    row = await db.get(Contract, contract_id)
    snapshot = dict(row.snapshot)
    snapshot["answers"] = {**snapshot["answers"], **answers}
    row.snapshot = snapshot
    await db.commit()


async def set_total(db, contract_id, total):
    row = await db.get(Contract, contract_id)
    row.snapshot = {**row.snapshot, "estimate": {**row.snapshot["estimate"], "total": total}}
    await db.commit()


async def noticed_world(db, telegram_id, *, close=False):
    """A world with an issued contract (a rate of 150 zł, a cap of 10 %), photos and a draft notice that passes the gate."""
    w, owner_id, project_id, contract_id = await issued(db, telegram_id)
    await set_answers(db, contract_id, downtime_rate_per_day="150.00", downtime_cap_percent=10, downtime_days_limit=3)
    await set_total(db, contract_id, "12000.00")  # a cap of 1 200 zł
    first = await add_photo(db, w, context=PhotoAttachmentContext.ROOM, room_id=w.salon.id, caption="Zamknięte drzwi do salonu")
    second = await add_photo(db, w, context=PhotoAttachmentContext.PROJECT, caption="Brama wjazdowa")
    episode, _ = await svc(db).open_episode(project_id, owner_id)
    await svc(db).update(project_id, episode.id, owner_id, {
        "cause_key": "no_access", "cause_note": "Klucze u administratora", "room_ids": [str(w.salon.id)], "noticed_on": NOTICE_DAY, "noticed_time": "08:30",
        "notice_channel": "e-mail", "photo_ids": [first, second], "need_text": "Udostępnić klucze do lokalu", "need_by": date(2026, 10, 14)})
    return w, owner_id, project_id, episode.id, (first, second)


async def noticed_episode(db, telegram_id):
    """... and the notice issued, the episode NOTICED, the days and the protocol's entries recorded."""
    w, owner_id, project_id, eid, photos = await noticed_world(db, telegram_id)
    run_ = issuer(delivery=Delivery())
    await run_.start_downtime_notice(db, await user_of(db, owner_id), project_id, eid)
    await run_.drain()
    await svc(db).update(project_id, eid, owner_id, {
        "days": {"2026-10-14": {}, "2026-10-15": {"other_work": True, "note": "malowanie w kuchni"}, "2026-10-16": {}},
        "held_on": HELD, "held_time": "09:00", "attendees": [{"person_id": str(w.person.id)}, {"name": "Jan Sąsiad", "role": "administrator"}],
        "deadline_note": "Termin zakończenia przesuwa się o 2 dni robocze", "notes": "Klucze oddane 17.10"})
    return w, owner_id, project_id, eid, run_


async def build_notice(db, owner_id, project_id, eid=None, *, working=False, number="ZAWPRZ/2026/10/12/0830"):
    sources = await load_downtime_sources(db, owner_id, project_id)
    row = await db.get(DowntimeEpisode, eid) if eid else None
    data = data_of(row) if row else {}
    return build_notice_document(data, sources, working=working, issued_on=NOTICE_DAY, number=None if working else number, sequence=1), sources


async def build_protocol(db, owner_id, project_id, eid=None, *, working=False, number="PROPRZ/2026/10/19/0900"):
    service = svc(db)
    sources = await load_downtime_sources(db, owner_id, project_id)
    row = await db.get(DowntimeEpisode, eid) if eid else None
    data = data_of(row) if row else {}
    snapshot = await service.contract_snapshot(row, sources) if row else None
    return build_protocol_document(data, sources, snapshot, working=working, issued_on=HELD, notice_number=row.notice_number if row else None,
                                   notice_on=row.notice_issued_at.date() if row and row.notice_issued_at else None,
                                   number=None if working else number, sequence=2), sources


def body_of(document, render):
    html = render(document)
    return html[html.index("<body"):]


async def test_the_notice_prints_the_cause_the_rooms_the_photos_and_what_the_contractor_needs(db_session):
    w, owner_id, project_id, eid, (first, second) = await noticed_world(db_session, 9961)
    document, _ = await build_notice(db_session, owner_id, project_id, eid)
    body = body_of(document, render_notice_html)
    facts = {row.label: row.value for row in document.facts}
    assert document.layout.meta.title == "Zawiadomienie o przestoju" and not document.layout.signatures
    assert facts["Pomieszczenia"] == "Salon" and facts["Data i godzina zawiadomienia"] == "12.10.2026, 08:30" and facts["Sposób zawiadomienia (forma dokumentowa)"] == "e-mail"
    assert facts["Umowa"].startswith("wersja 1, nr UMOWA/")
    assert [(c.label, c.checked) for c in document.causes][:2] == [("Brak dostępu do Obiektu", True), ("Niespełnienie wymagań gotowości pomieszczeń (Załącznik 4)", False)]
    assert sum(c.checked for c in document.causes) == 1 and len(document.causes) == len(CATALOG.downtime_causes.items) and document.cause_note == "Klucze u administratora"
    assert [(p.number, p.caption, p.place) for p in document.photos] == [(1, "Zamknięte drzwi do salonu", "Salon"), (2, "Brama wjazdowa", None)]
    assert {row.label: row.value for row in document.need} == {"Czego potrzebuje Wykonawca": "Udostępnić klucze do lokalu", "Do kiedy": "14.10.2026"}
    assert "☒&nbsp;Brak dostępu do Obiektu" in body and "§ 10 ust. 2 Umowy" in body and 'class="watermark' not in body and "ZAWPRZ/2026/10/12/0830" in body
    assert body.count("☒") == 1


async def test_a_notice_without_rooms_says_the_whole_object(db_session):
    w, owner_id, project_id, eid, _ = await noticed_world(db_session, 9962)
    await svc(db_session).update(project_id, eid, owner_id, {"room_ids": []})
    document, _ = await build_notice(db_session, owner_id, project_id, eid)
    assert {row.label: row.value for row in document.facts}["Pomieszczenia"] == "cały Obiekt"


async def test_the_protocol_prints_the_notice_the_days_the_sum_and_the_people_present(db_session):
    w, owner_id, project_id, eid, run_ = await noticed_episode(db_session, 9963)
    document, _ = await build_protocol(db_session, owner_id, project_id, eid)
    body = body_of(document, render_protocol_html)
    facts = {row.label: row.value for row in document.facts}
    assert document.layout.meta.title == "Protokół przestoju" and document.layout.signatures
    assert facts["Zawiadomienie o przestoju"].startswith("nr ZAWPRZ/2026/10/08/") and facts["Zawiadomienie o przestoju"].endswith("z dnia 08.10.2026")
    assert facts["Przyczyna przestoju"] == "Brak dostępu do Obiektu — Klucze u administratora" and facts["Pomieszczenia"] == "Salon"
    assert facts["Data i godzina protokołu"] == "19.10.2026, 09:00" and facts["Umowa"].startswith("wersja 1, nr UMOWA/")
    assert [(d.number, d.day, d.weekday, d.other_work, d.note) for d in document.days] == [
        (1, "14.10.2026", "środa", "Nie", None), (2, "15.10.2026", "czwartek", "Tak", "malowanie w kuchni"), (3, "16.10.2026", "piątek", "Nie", None)]
    totals = {row.label: row.value for row in document.totals}
    assert totals["Dni przestoju — razem"] == "3" and totals["w tym dni bez możliwości innych Prac"] == "2"
    assert totals["Stawka za dobę (zgodnie z Umową)"] == "150,00\xa0zł" and totals["Kwota za gotowość"] == "300,00\xa0zł" and document.cap_note is None
    assert document.deadline_note == "Termin zakończenia przesuwa się o 2 dni robocze" and not document.refusal.checked and document.notes == "Klucze oddane 17.10"
    assert [a.name for a in document.attendees] == ["Anna Nowak", "Jan Sąsiad"] and "PROPRZ/2026/10/19/0900" in body and 'class="watermark' not in body
    assert "§ 10 ust. 2 i 3 Umowy" in body


async def test_the_sum_follows_the_contract_the_notice_was_written_under_not_a_newer_one(db_session):
    w, owner_id, project_id, eid, run_ = await noticed_episode(db_session, 9981)
    older = (await db_session.execute(select(Contract).where(Contract.project_id == project_id))).scalars().first()
    newer = Contract(owner_id=owner_id, project_id=project_id, version=older.version + 1, status="ISSUED", answers={}, questionnaire_version=1,
                     issued_at=older.issued_at, document_html="<html></html>",
                     snapshot={"answers": {"downtime_rate_per_day": "999.00"}, "estimate": {"total": "12000.00"}})
    db_session.add(newer)
    await db_session.commit()
    sources = await load_downtime_sources(db_session, owner_id, project_id)
    assert sources.base.contract.id == newer.id  # the latest contract is the newer one ...
    read = await svc(db_session).read(await db_session.get(DowntimeEpisode, eid))
    assert read.settlement.rate == "150.00" and read.settlement.amount == "300.00"  # ... and the sum still follows the one the notice was written under
    protocol, _ = await build_protocol(db_session, owner_id, project_id, eid)
    assert {row.label: row.value for row in protocol.totals}["Kwota za gotowość"] == "300,00\xa0zł"


async def test_photos_of_an_archived_room_or_surface_are_not_offered_and_do_not_pass_for_the_objects_own(db_session):
    w = await ready(db_session, telegram_id=9982)
    kitchen = await add_photo(db_session, w, context=PhotoAttachmentContext.ROOM, room_id=w.kuchnia.id, caption="Kuchnia")
    on_wall = await add_photo(db_session, w, context=PhotoAttachmentContext.SURFACE, surface_id=w.wall.id, caption="Ściana")
    whole = await add_photo(db_session, w, context=PhotoAttachmentContext.PROJECT, caption="Brama")
    assert {kitchen, on_wall, whole} <= set((await load_downtime_sources(db_session, w.owner.id, w.project.id)).photos)
    w.kuchnia.is_archived = True
    w.wall.is_archived = True
    await db_session.commit()
    sources = await load_downtime_sources(db_session, w.owner.id, w.project.id)
    assert whole in sources.photos and kitchen not in sources.photos and on_wall not in sources.photos
    assert all(p.id != on_wall for p in sources.allowed([str(w.salon.id)]))  # an archived surface's photo is not "of the whole object"


async def test_a_sum_over_the_cap_is_printed_as_the_cap_with_the_reason(db_session):
    w, owner_id, project_id, eid, run_ = await noticed_episode(db_session, 9964)
    contract_row = (await db_session.execute(select(Contract).where(Contract.project_id == project_id))).scalars().first()
    await set_answers(db_session, contract_row.id, downtime_rate_per_day="5000.00", downtime_cap_percent=1)
    document, _ = await build_protocol(db_session, owner_id, project_id, eid)
    totals = {row.label: row.value for row in document.totals}
    assert document.cap_note is not None and document.cap_note.startswith("Kwota ograniczona do ") and totals["Kwota za gotowość"] in document.cap_note


async def test_a_refusal_to_sign_is_printed_and_a_rate_the_contract_leaves_empty_stays_a_line_to_fill_in(db_session):
    w, owner_id, project_id, eid, run_ = await noticed_episode(db_session, 9965)
    contract_row = (await db_session.execute(select(Contract).where(Contract.project_id == project_id))).scalars().first()
    answers = {k: v for k, v in contract_row.snapshot["answers"].items() if k != "downtime_rate_per_day"}
    contract_row.snapshot = {**contract_row.snapshot, "answers": answers}
    await svc(db_session).update(project_id, eid, owner_id, {"signature_refused": True})
    await db_session.commit()
    document, _ = await build_protocol(db_session, owner_id, project_id, eid)
    totals = {row.label: row.value for row in document.totals}
    assert document.refusal.checked and totals["Stawka za dobę (zgodnie z Umową)"] is None and totals["Kwota za gotowość"] is None
    assert body_of(document, render_protocol_html).count('class="write-line"') >= 2


async def test_the_working_versions_are_blank_forms_that_never_refuse_and_cannot_be_numbered(db_session):
    w = await ready(db_session, telegram_id=9966)
    notice, sources = await build_notice(db_session, w.owner.id, w.project.id, working=True)
    body = body_of(notice, render_notice_html)
    assert notice.layout.draft and notice.layout.light_watermark and notice.layout.meta.number is None and 'class="watermark light"' in body
    assert len(notice.causes) == 8 and body.count("☐") == 8 and body.count("☒") == 0 and len(notice.photos) == 4 and body.count('class="write-line"') >= 6
    with pytest.raises(Exception) as numbered:
        build_notice_document({}, sources, working=True, issued_on=NOTICE_DAY, number="ZAWPRZ/1")
    assert numbered.value.reason == "DRAFT_NUMBERED"
    protocol, sources = await build_protocol(db_session, w.owner.id, w.project.id, working=True)
    body = body_of(protocol, render_protocol_html)
    assert protocol.layout.draft and protocol.layout.meta.number is None and len(protocol.days) == 5 and body.count("☐") == 1 and "Obecni: do wpisania." in body
    assert all(d.day is None for d in protocol.days) and body.count('class="write-line"') >= 12
    with pytest.raises(Exception) as numbered_protocol:
        build_protocol_document({}, sources, None, working=True, issued_on=HELD, number="PROPRZ/1")
    assert numbered_protocol.value.reason == "DRAFT_NUMBERED"
    sources.base.executor = None
    assert build_notice_document({}, sources, working=True, issued_on=NOTICE_DAY) and build_protocol_document({}, sources, None, working=True, issued_on=HELD)
    for issued_build in (lambda: build_notice_document({}, sources, working=False, issued_on=NOTICE_DAY),
                         lambda: build_protocol_document({}, sources, None, working=False, issued_on=HELD)):
        with pytest.raises(Exception) as no_profile:
            issued_build()
        assert no_profile.value.reason == "EXECUTOR_PROFILE_REQUIRED"


async def test_real_pdfs_with_the_number_on_every_page(db_session):
    w, owner_id, project_id, eid, run_ = await noticed_episode(db_session, 9967)
    notice, _ = await build_notice(db_session, owner_id, project_id, eid)
    pdf = (await DocumentRenderer().render(render_notice_html(notice))).pdf
    pages = PdfReader(io.BytesIO(pdf)).pages
    assert len(pages) >= 1 and all("ZAWPRZ/2026/10/12/0830" in page.extract_text() for page in pages)
    flat = " ".join(text_of(pdf).split())
    for part in ("Zawiadomienie o przestoju", "Brak dostępu do Obiektu", "Zamknięte drzwi do salonu", "Udostępnić klucze do lokalu"):
        assert part in flat, part
    protocol, _ = await build_protocol(db_session, owner_id, project_id, eid)
    pdf = (await DocumentRenderer().render(render_protocol_html(protocol))).pdf
    assert all("PROPRZ/2026/10/19/0900" in page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)
    flat = " ".join(text_of(pdf).split())
    for part in ("Protokół przestoju", "środa", "malowanie w kuchni", "300,00", "zakończenia przesuwa się"):
        assert part in flat, part


# --- the gates and the freezes --------------------------------------------------------------------------------------------------------------


async def test_a_notice_that_is_not_ready_is_refused_with_the_list_and_takes_no_number(db_session):
    w, owner_id, project_id, contract_id = await issued(db_session, 9971)
    episode, _ = await svc(db_session).open_episode(project_id, owner_id)
    episode_id = episode.id
    run_ = issuer(delivery=Delivery())
    with pytest.raises(DowntimeGateError) as refused_:
        await run_.start_downtime_notice(db_session, await user_of(db_session, owner_id), project_id, episode_id)
    assert [b.code for b in refused_.value.blockers] == ["CAUSE_REQUIRED", "NOTICED_ON_REQUIRED", "NEED_REQUIRED", "PHOTOS_REQUIRED"]
    assert all(j.kind not in ("DOWNTIME_NOTICE", "DOWNTIME_PROTOCOL") for j in await journal(db_session))
    with pytest.raises(DowntimeNotEditableError):  # no protocol before the notice
        await run_.start_downtime_protocol(db_session, await user_of(db_session, owner_id), project_id, episode_id)
    w2 = await ready(db_session, telegram_id=9972)  # only a draft contract: no contract to work under
    other, _ = await svc(db_session).open_episode(w2.project.id, w2.owner.id)
    with pytest.raises(DowntimeGateError) as no_contract:
        await run_.start_downtime_notice(db_session, await user_of(db_session, w2.owner.id), w2.project.id, other.id)
    assert "CONTRACT_REQUIRED" in [b.code for b in no_contract.value.blockers]


async def test_issuing_the_notice_freezes_it_numbers_it_sends_the_pdf_and_moves_the_episode_on(db_session):
    w, owner_id, project_id, eid, (first, second) = await noticed_world(db_session, 9973)
    sender = Delivery()
    run_ = issuer(delivery=sender)
    reservation = await run_.start_downtime_notice(db_session, await user_of(db_session, owner_id), project_id, eid)
    assert (reservation.document.kind, reservation.document.status, reservation.document.source_id, reservation.document.source_version) == (
        "DOWNTIME_NOTICE", "PENDING", eid, 1)
    assert reservation.document.number.startswith("ZAWPRZ/2026/10/08/")
    await run_.drain()
    done = [j for j in await journal(db_session) if j.kind == "DOWNTIME_NOTICE"][0]
    assert (done.status, done.error_code, done.title) == ("SENT", None, "Zawiadomienie o przestoju — nr 1")
    number = done.number
    message = sender.sent[-1]
    assert message["filename"].startswith("ZAWPRZ-2026-10-08-") and message["caption"].startswith("Zawiadomienie o przestoju — nr 1 — Mokotów\nZAWPRZ/")
    assert number in text_of(message["pdf"])
    db_session.expire_all()
    row = await db_session.get(DowntimeEpisode, eid)
    assert row.status == "NOTICED" and row.notice_number == number and row.notice_issued_at is not None and row.contract_version == 1 and number in row.notice_html
    snap = row.notice_snapshot
    assert (snap["cause_key"], snap["cause_text"], snap["cause_note"], snap["noticed_on"], snap["noticed_time"], snap["need_by"]) == (
        "no_access", "Brak dostępu do Obiektu", "Klucze u administratora", "2026-10-12", "08:30", "2026-10-14")
    assert [p["caption"] for p in snap["photos"]] == ["Zamknięte drzwi do salonu", "Brama wjazdowa"] and snap["rooms"][0]["name"] == "Salon"
    assert snap["contract"]["version"] == 1 and snap["client"] and snap["executor"]
    with pytest.raises(DowntimeInvalidError) as frozen:  # the notice is the notice that was sent
        await svc(db_session).update(project_id, eid, owner_id, {"need_text": "Co innego"})
    assert frozen.value.reason == D.NOTICE_FROZEN
    with pytest.raises(DowntimeNotEditableError):
        await run_.start_downtime_notice(db_session, await user_of(db_session, owner_id), project_id, eid)
    with pytest.raises(DowntimeNotEditableError):  # the service itself refuses to freeze twice
        await svc(db_session).mark_noticed(project_id, eid, owner_id, issued_at=run_.clock(), number="X", snapshot={}, document_html="<html></html>",
                                           contract_id=None, contract_version=None)
    assert (await svc(db_session).open_episode(project_id, owner_id))[0].id == eid  # still the open one


async def test_issuing_the_protocol_closes_the_episode_with_the_sum_from_the_contract_the_notice_was_written_under(db_session):
    w, owner_id, project_id, eid, run_ = await noticed_episode(db_session, 9974)
    sender = Delivery()
    run_ = issuer(delivery=sender)
    contract_row = (await db_session.execute(select(Contract).where(Contract.project_id == project_id))).scalars().first()
    reservation = await run_.start_downtime_protocol(db_session, await user_of(db_session, owner_id), project_id, eid)
    assert (reservation.document.kind, reservation.document.source_id) == ("DOWNTIME_PROTOCOL", eid) and reservation.document.number.startswith("PROPRZ/2026/10/08/")
    await run_.drain()
    done = [j for j in await journal(db_session) if j.kind == "DOWNTIME_PROTOCOL"][0]
    assert (done.status, done.title) == ("SENT", "Protokół przestoju — nr 1")
    number = done.number
    assert sender.sent[-1]["caption"].startswith("Protokół przestoju — nr 1 — Mokotów\nPROPRZ/") and number in text_of(sender.sent[-1]["pdf"])
    db_session.expire_all()
    row = await db_session.get(DowntimeEpisode, eid)
    assert row.status == "CLOSED" and row.protocol_issued_at is not None and number in row.protocol_html and row.notice_html
    snap = row.protocol_snapshot
    assert snap["notice"]["number"] == row.notice_number and snap["settlement"] == {
        "listed": 3, "chargeable": 2, "rate": "150.00", "amount": "300.00", "cap": snap["settlement"]["cap"], "capped": False, "payable": "300.00",
        "limit_days": 3, "limit_exceeded": False}
    assert snap["settlement"]["cap"] is not None and [d["date"] for d in snap["days"]] == ["2026-10-14", "2026-10-15", "2026-10-16"]
    assert snap["held_on"] == "2026-10-19" and snap["signature_refused"] is False and snap["contract"]["version"] == 1 and [a["name"] for a in snap["attendees"]][0] == "Anna Nowak"
    with pytest.raises(DowntimeNotEditableError):
        await svc(db_session).update(project_id, eid, owner_id, {"notes": "późno"})
    with pytest.raises(DowntimeNotEditableError):
        await run_.start_downtime_protocol(db_session, await user_of(db_session, owner_id), project_id, eid)
    with pytest.raises(DowntimeNotEditableError):
        await svc(db_session).archive(project_id, eid, owner_id)
    with pytest.raises(DowntimeNotEditableError):
        await svc(db_session).mark_closed(project_id, eid, owner_id, issued_at=run_.clock(), snapshot={}, document_html="<html></html>")
    assert (await svc(db_session).open_episode(project_id, owner_id))[0].sequence == 2  # the next obstacle is a new episode
    assert contract_row is not None


async def test_a_protocol_that_is_not_ready_is_refused_with_the_list_and_takes_no_number(db_session):
    w, owner_id, project_id, eid, photos = await noticed_world(db_session, 9975)
    run_ = issuer(delivery=Delivery())
    await run_.start_downtime_notice(db_session, await user_of(db_session, owner_id), project_id, eid)
    await run_.drain()
    before = len([j for j in await journal(db_session) if j.kind == "DOWNTIME_PROTOCOL"])
    with pytest.raises(DowntimeGateError) as refused_:
        await run_.start_downtime_protocol(db_session, await user_of(db_session, owner_id), project_id, eid)
    assert [b.code for b in refused_.value.blockers] == ["DAYS_REQUIRED", "HELD_ON_REQUIRED", "NO_ATTENDEES"]
    assert len([j for j in await journal(db_session) if j.kind == "DOWNTIME_PROTOCOL"]) == before == 0


async def test_the_issued_pages_do_not_change_when_the_data_do_and_an_empty_stored_page_is_refused(db_session):
    w, owner_id, project_id, eid, run_ = await noticed_episode(db_session, 9976)
    run_ = issuer(delivery=Delivery())
    await run_.start_downtime_protocol(db_session, await user_of(db_session, owner_id), project_id, eid)
    await run_.drain()
    row = await db_session.get(DowntimeEpisode, eid)
    notice_page, protocol_page = row.notice_html, row.protocol_html
    project = (await db_session.execute(select(Project).where(Project.id == project_id))).scalar_one()
    project.name = "Zupełnie inna nazwa"
    w.person.name = "Ktoś Inny"
    await db_session.commit()
    journal_rows = {j.kind: j for j in await journal(db_session) if j.kind.startswith("DOWNTIME")}
    for kind, marker in (("DOWNTIME_NOTICE", "Zamknięte drzwi do salonu"), ("DOWNTIME_PROTOCOL", "Anna Nowak")):
        again = await run_._render(db_session, journal_rows[kind])
        flat = " ".join(text_of(again.pdf).split())
        assert marker in flat and "Zupełnie inna nazwa" not in flat and "Ktoś Inny" not in flat
    assert (await db_session.get(DowntimeEpisode, eid)).notice_html == notice_page and (await db_session.get(DowntimeEpisode, eid)).protocol_html == protocol_page
    stored = await db_session.get(DowntimeEpisode, eid)
    stored.notice_html = ""
    await db_session.commit()
    with pytest.raises(Exception) as empty_notice:
        await run_._render(db_session, journal_rows["DOWNTIME_NOTICE"])
    assert empty_notice.value.reason == "DOWNTIME_NOT_ISSUED"
    stored.protocol_html = ""
    await db_session.commit()
    with pytest.raises(Exception) as empty_protocol:
        await run_._render(db_session, journal_rows["DOWNTIME_PROTOCOL"])
    assert empty_protocol.value.reason == "DOWNTIME_NOT_ISSUED"
    journal_rows["DOWNTIME_NOTICE"].source_id = uuid.uuid4()
    with pytest.raises(Exception) as missing:
        await run_._render(db_session, journal_rows["DOWNTIME_NOTICE"])
    assert missing.value.reason == "DOWNTIME_NOT_ISSUED"


async def test_the_previews_follow_the_episode_and_never_leave_a_row(db_session):
    w, owner_id, project_id, eid, photos = await noticed_world(db_session, 9977)
    sender = Delivery()
    before = len(await journal(db_session))
    result = await issuer(delivery=sender).preview_downtime_notice(db_session, await user_of(db_session, owner_id), project_id)
    assert result.pages >= 1
    message = sender.sent[-1]
    assert message["filename"] == "Zawiadomienie-o-przestoju-wersja-robocza.pdf" and message["caption"].startswith("WERSJA ROBOCZA — Zawiadomienie o przestoju")
    flat = " ".join(text_of(message["pdf"]).split())
    assert "WERSJA ROBOCZA" in flat and "Udostępnić klucze do lokalu" in flat
    run_ = issuer(delivery=Delivery())
    await run_.start_downtime_notice(db_session, await user_of(db_session, owner_id), project_id, eid)
    await run_.drain()
    await svc(db_session).update(project_id, eid, owner_id, {"days": {"2026-10-14": {}}, "notes": "Dzień pierwszy"})
    count = len(await journal(db_session))
    protocol_sender = Delivery()
    await issuer(delivery=protocol_sender).preview_downtime_protocol(db_session, await user_of(db_session, owner_id), project_id)
    message = protocol_sender.sent[-1]
    assert message["filename"] == "Protokol-przestoju-wersja-robocza.pdf" and message["caption"].startswith("WERSJA ROBOCZA — Protokół przestoju")
    flat = " ".join(text_of(message["pdf"]).split())
    assert "WERSJA ROBOCZA" in flat and "Dzień pierwszy" in flat and "14.10.2026" in flat
    assert len(await journal(db_session)) == count and before <= count
    blank = Delivery()
    other = await ready(db_session, telegram_id=9978)  # no episode: blank forms
    await issuer(delivery=blank).preview_downtime_protocol(db_session, await user_of(db_session, other.owner.id), other.project.id)
    await issuer(delivery=blank).preview_downtime_notice(db_session, await user_of(db_session, other.owner.id), other.project.id)
    assert [m["caption"].split(" — ")[1] for m in blank.sent] == ["Protokół przestoju", "Zawiadomienie o przestoju"]


# --- HTTP -----------------------------------------------------------------------------------------------------------------------------------


def url(project_id, tail=""):
    return f"/api/projects/{project_id}/downtimes{tail}"


async def test_the_routes_need_a_token_and_a_stranger_gets_404(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    mine = await ready(db_session, telegram_id=OWNER_TG)
    theirs = await ready(db_session, telegram_id=STRANGER_TG)
    use_issuer(issuer(delivery=Delivery()))
    assert (await async_client.get(url(mine.project.id))).status_code == 401
    for tail in (f"/{uuid.uuid4()}/issue-notice", f"/{uuid.uuid4()}/issue-protocol"):
        assert (await async_client.post(url(mine.project.id, tail))).status_code == 401
    for slug in ("downtime-notice", "downtime-protocol"):
        assert (await async_client.post(f"/api/projects/{mine.project.id}/documents/{slug}/preview")).status_code == 401
    headers = await login(async_client)
    episode, _ = await svc(db_session).open_episode(theirs.project.id, theirs.owner.id)
    for response in (
        await async_client.get(url(theirs.project.id), headers=headers),
        await async_client.post(url(theirs.project.id), headers=headers),
        await async_client.post(url(theirs.project.id, f"/{episode.id}/issue-notice"), headers=headers),
        await async_client.post(url(theirs.project.id, f"/{episode.id}/issue-protocol"), headers=headers),
        await async_client.post(f"/api/projects/{theirs.project.id}/documents/downtime-notice/preview", headers=headers),
        await async_client.post(f"/api/projects/{theirs.project.id}/documents/downtime-protocol/preview", headers=headers),
        await async_client.get(url(mine.project.id, f"/{uuid.uuid4()}"), headers=headers),
        await async_client.get(url(mine.project.id, f"/{episode.id}"), headers=headers),
        await async_client.patch(url(theirs.project.id, f"/{episode.id}"), json={"notes": "x"}, headers=headers),
        await async_client.post(url(theirs.project.id, f"/{episode.id}/archive"), headers=headers),
    ):
        assert response.status_code == 404


async def test_notice_protocol_and_abandon_over_http(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w, owner_id, project_id, contract_id = await issued(db_session, OWNER_TG)
    await set_answers(db_session, contract_id, downtime_rate_per_day="150.00", downtime_cap_percent=10, downtime_days_limit=1)
    await set_total(db_session, contract_id, "12000.00")
    photo = await add_photo(db_session, w, context=PhotoAttachmentContext.PROJECT, caption="Brama")
    run_ = use_issuer(issuer(delivery=Delivery()))
    headers = await login(async_client)
    pid = str(project_id)
    created = await async_client.post(url(pid), headers=headers)
    assert created.status_code == 201, created.text
    body = created.json()
    assert (body["sequence"], body["status"], body["days"], body["photos"]) == (1, "DRAFT", [], [])
    assert photo in [o["id"] for o in body["photo_options"]] and body["rooms"][0]["name"] == "Salon" and body["contract"]["version"] == 1
    assert body["settlement"]["listed"] == 0 and [b["code"] for b in body["blockers"]] == ["CAUSE_REQUIRED", "NOTICED_ON_REQUIRED", "NEED_REQUIRED", "PHOTOS_REQUIRED"]
    assert (await async_client.post(url(pid), headers=headers)).status_code == 200
    eid = body["id"]
    assert (await async_client.patch(url(pid, f"/{eid}"), json={}, headers=headers)).status_code == 422
    assert (await async_client.patch(url(pid, f"/{eid}"), json={"unknown": 1}, headers=headers)).status_code == 422
    bad = await async_client.patch(url(pid, f"/{eid}"), json={"cause_key": "weather"}, headers=headers)
    assert bad.status_code == 422 and bad.json()["detail"] == {"code": "DOWNTIME_INVALID", "message": "downtime 'cause_key': UNKNOWN_CAUSE",
                                                              "details": {"key": "cause_key", "reason": "UNKNOWN_CAUSE"}}
    early = await async_client.patch(url(pid, f"/{eid}"), json={"days": {"2026-10-14": {}}}, headers=headers)
    assert early.status_code == 422 and early.json()["detail"]["details"] == {"key": "days", "reason": "NOT_NOTICED_YET"}
    blocked = await async_client.post(url(pid, f"/{eid}/issue-notice"), headers=headers)
    assert blocked.status_code == 422 and blocked.json()["detail"]["code"] == "DOWNTIME_GATE_BLOCKED"
    assert blocked.json()["detail"]["details"]["blockers"][0]["code"] == "CAUSE_REQUIRED"
    saved = await async_client.patch(url(pid, f"/{eid}"), json={
        "cause_key": "no_access", "noticed_on": "2026-10-12", "noticed_time": "08:30", "need_text": "Klucze", "photo_ids": [photo]}, headers=headers)
    assert saved.status_code == 200, saved.text
    assert saved.json()["cause_text"] == "Brak dostępu do Obiektu" and saved.json()["blockers"] == [] and [p["id"] for p in saved.json()["photos"]] == [photo]
    assert (await async_client.post(url(pid, f"/{eid}/issue-protocol"), headers=headers)).status_code == 409  # no protocol before the notice
    ok = await async_client.post(url(pid, f"/{eid}/issue-notice"), headers=headers)
    assert ok.status_code == 202, ok.text
    assert ok.json()["kind"] == "DOWNTIME_NOTICE" and ok.json()["number"].startswith("ZAWPRZ/") and ok.json()["source_id"] == eid
    await run_.drain()
    noticed = (await async_client.get(url(pid, f"/{eid}"), headers=headers)).json()
    assert noticed["status"] == "NOTICED" and noticed["notice_number"] == ok.json()["number"] and noticed["photo_options"] == []
    assert [b["code"] for b in noticed["blockers"]] == ["DAYS_REQUIRED", "HELD_ON_REQUIRED", "NO_ATTENDEES"]
    frozen = await async_client.patch(url(pid, f"/{eid}"), json={"need_text": "Co innego"}, headers=headers)
    assert frozen.status_code == 422 and frozen.json()["detail"]["details"]["reason"] == "NOTICE_FROZEN"
    weekend = await async_client.patch(url(pid, f"/{eid}"), json={"days": {"2026-10-17": {}}}, headers=headers)
    assert weekend.status_code == 422 and weekend.json()["detail"]["details"]["reason"] == "BAD_DAY"
    days = await async_client.patch(url(pid, f"/{eid}"), json={
        "days": {"2026-10-14": {}, "2026-10-15": {"other_work": True, "note": "kuchnia"}, "2026-10-16": {}}, "held_on": "2026-10-19",
        "attendees": [{"name": "Jan Sąsiad", "role": "administrator"}]}, headers=headers)
    assert days.status_code == 200, days.text
    out = days.json()
    assert [(d["date"], d["weekday"], d["other_work"], d["note"]) for d in out["days"]] == [("2026-10-14", 2, False, None), ("2026-10-15", 3, True, "kuchnia"), ("2026-10-16", 4, False, None)]
    assert out["settlement"]["listed"] == 3 and out["settlement"]["chargeable"] == 2 and out["settlement"]["rate"] == "150.00"
    assert out["settlement"]["amount"] == "300.00" and out["settlement"]["payable"] == "300.00" and out["settlement"]["capped"] is False
    assert out["settlement"]["limit_days"] == 1 and out["settlement"]["limit_exceeded"] is True and out["blockers"] == []
    closed = await async_client.post(url(pid, f"/{eid}/issue-protocol"), headers=headers)
    assert closed.status_code == 202, closed.text
    assert closed.json()["kind"] == "DOWNTIME_PROTOCOL" and closed.json()["number"].startswith("PROPRZ/")
    await run_.drain()
    assert (await async_client.get(url(pid, f"/{eid}"), headers=headers)).json()["status"] == "CLOSED"
    again = await async_client.post(url(pid, f"/{eid}/issue-protocol"), headers=headers)
    assert again.status_code == 409 and again.json()["detail"]["code"] == "DOWNTIME_NOT_EDITABLE"
    listed = (await async_client.get(f"/api/projects/{pid}/documents", headers=headers)).json()
    assert sorted(d["kind"] for d in listed["items"] if d["kind"].startswith("DOWNTIME")) == ["DOWNTIME_NOTICE", "DOWNTIME_PROTOCOL"]
    second = (await async_client.post(url(pid), headers=headers)).json()
    assert second["sequence"] == 2 and second["status"] == "DRAFT"
    gone = await async_client.post(url(pid, f"/{second['id']}/archive"), headers=headers)
    assert gone.status_code == 200 and gone.json()["status"] == "ARCHIVED"
    assert (await async_client.post(url(pid, f"/{second['id']}/archive"), headers=headers)).status_code == 409
    assert (await async_client.get(url(pid), headers=headers)).json()["total"] == 2
    for slug in ("downtime-notice", "downtime-protocol"):
        preview = await async_client.post(f"/api/projects/{pid}/documents/{slug}/preview", headers=headers)
        assert preview.status_code == 200 and preview.json()["sent"] is True


async def test_a_noticed_episode_can_be_abandoned_when_the_obstacle_goes_away_and_its_notice_stays_in_the_journal(db_session):
    w, owner_id, project_id, eid, photos = await noticed_world(db_session, 9979)
    run_ = issuer(delivery=Delivery())
    await run_.start_downtime_notice(db_session, await user_of(db_session, owner_id), project_id, eid)
    await run_.drain()
    archived = await svc(db_session).archive(project_id, eid, owner_id)
    assert archived.status == "ARCHIVED" and archived.notice_html
    assert [j.kind for j in await journal(db_session) if j.kind.startswith("DOWNTIME")] == ["DOWNTIME_NOTICE"]
    assert (await svc(db_session).open_episode(project_id, owner_id))[0].sequence == 2


# --- the catalogue, the registry and the migration -------------------------------------------------------------------------------------------


def test_the_causes_of_a_downtime_are_the_contracts_own_list_and_the_prefixes_are_unique():
    keys = [c.key for c in CATALOG.downtime_causes.items]
    assert keys == ["no_access", "premises_not_ready", "no_utilities", "other_contractors", "no_decision", "materials_missing", "stop_order", "other"]
    notice, protocol = TEMPLATES[DocumentKind.DOWNTIME_NOTICE], TEMPLATES[DocumentKind.DOWNTIME_PROTOCOL]
    assert (notice.file, notice.number_prefix, protocol.file, protocol.number_prefix) == ("downtime_notice.html.j2", "ZAWPRZ", "downtime_protocol.html.j2", "PROPRZ")
    prefixes = [tpl.number_prefix for tpl in TEMPLATES.values() if tpl.number_prefix]
    assert len(prefixes) == len(set(prefixes))


def test_revision_chain_and_length():
    module = load_migration("0053_downtime_episodes")
    assert module.revision == "0053_downtime_episodes" and module.down_revision == "0052_decision_protocols" and len(module.revision) <= 32


def engine_0053():
    engine = contract_engine()
    for name in ("0045_contract_issue", "0046_contract_signed", "0047_handover_protocols", "0048_handover_issue", "0049_concealed_works",
                 "0050_acceptance_protocols", "0051_final_protocol_kind", "0052_decision_protocols", "0053_downtime_episodes"):
        run(engine, name, "upgrade")
    return engine


ROW = ("INSERT INTO downtime_episodes (id, owner_id, project_id, sequence, status, room_ids, photo_ids, days, attendees, signature_refused, "
       "notice_issued_at, notice_snapshot, notice_html, protocol_issued_at, protocol_snapshot, protocol_html, created_at, updated_at) "
       "VALUES (:id, 'u1', 'p1', :sequence, :status, '[]', '[]', '[]', '[]', 0, :n_at, :n_snap, :n_html, :p_at, :p_snap, :p_html, '2026-10-11', '2026-10-11')")
JOURNAL = ("INSERT INTO issued_documents (id, owner_id, project_id, kind, title, number, project_seq, template_version, status, issued_at) "
           "VALUES (:id, 'u1', 'p1', :kind, 't', :number, :seq, '1', 'SENT', '2026-10-10')")
NONE = {"n_at": None, "n_snap": None, "n_html": None, "p_at": None, "p_snap": None, "p_html": None}
NOTICE = {**NONE, "n_at": "2026-10-11", "n_snap": "{}", "n_html": "<html></html>"}
PROTOCOL = {**NOTICE, "p_at": "2026-10-12", "p_snap": "{}", "p_html": "<html></html>"}


def test_the_database_allows_one_open_episode_a_number_once_known_states_frozen_documents_and_the_new_journal_kinds():
    engine = engine_0053()
    with engine.begin() as conn:
        conn.execute(text(ROW), {"id": "a", "sequence": 1, "status": "ARCHIVED", **NONE})
        conn.execute(text(ROW), {"id": "b", "sequence": 2, "status": "CLOSED", **PROTOCOL})
        conn.execute(text(ROW), {"id": "c", "sequence": 3, "status": "NOTICED", **NOTICE})
        conn.execute(text(JOURNAL), {"id": "j1", "kind": "DOWNTIME_NOTICE", "number": "ZAWPRZ/1", "seq": 1})
        conn.execute(text(JOURNAL), {"id": "j2", "kind": "DOWNTIME_PROTOCOL", "number": "PROPRZ/1", "seq": 2})
    for bad in (
        {"id": "d", "sequence": 4, "status": "DRAFT", **NONE},  # a second open episode (one is NOTICED)
        {"id": "e", "sequence": 1, "status": "ARCHIVED", **NONE},  # a repeated number
        {"id": "f", "sequence": 5, "status": "OPEN", **NONE},
        {"id": "g", "sequence": 0, "status": "ARCHIVED", **NONE},
        {"id": "h", "sequence": 6, "status": "NOTICED", **NONE},  # noticed without its frozen notice
        {"id": "i", "sequence": 7, "status": "CLOSED", **NOTICE},  # closed without its frozen protocol
    ):
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(text(ROW), bad)
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text(JOURNAL), {"id": "l", "kind": "OTHER", "number": "X/1", "seq": 3})
    assert {c["name"] for c in inspect(engine).get_columns("downtime_episodes")} == {c.name for c in DowntimeEpisode.__table__.columns}


def test_downgrade_refuses_while_an_episode_or_a_journal_row_exists_and_then_works():
    engine = engine_0053()
    with engine.begin() as conn:
        conn.execute(text(ROW), {"id": "a", "sequence": 1, "status": "DRAFT", **NONE})
    with pytest.raises(RuntimeError, match="1 downtime episode"):
        run(engine, "0053_downtime_episodes", "downgrade")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM downtime_episodes"))
        conn.execute(text(JOURNAL), {"id": "j", "kind": "DOWNTIME_PROTOCOL", "number": "PROPRZ/1", "seq": 1})
    with pytest.raises(RuntimeError, match="1 journal row"):
        run(engine, "0053_downtime_episodes", "downgrade")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM issued_documents"))
    run(engine, "0053_downtime_episodes", "downgrade")
    assert "downtime_episodes" not in inspect(engine).get_table_names() and "decision_protocols" in inspect(engine).get_table_names()
    run(engine, "0053_downtime_episodes", "upgrade")
