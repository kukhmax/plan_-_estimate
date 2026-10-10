"""Stage 16H.1: the protocol of acceptance of the work -- the entries, the derived result, the blockers, the draft, the API and the
migration."""
import uuid
from datetime import UTC, date, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.domain.contracts.catalog import load_contract_catalog
from app.domain.exceptions import AcceptanceInvalidError, AcceptanceNotEditableError, AcceptanceNotFoundError, ProjectNotFoundError
from app.domain.protocols import acceptance as A
from app.domain.protocols.acceptance import SurfaceFacts, WorkLine
from app.domain.services.acceptance_service import AcceptanceService
from app.models.acceptance_protocol import AcceptanceProtocol
from app.models.checklist import QualityLevel
from app.models.photo_asset import PhotoAssetStatus
from app.models.photo_attachment import PhotoAttachment, PhotoAttachmentContext, PhotoCategory
from app.models.surface import Surface, SurfaceType
from app.models.work_execution import SurfaceWorkExecution, WorkExecutionStatus
from app.models.work_plan import SurfacePlannedWork, SurfaceWorkPlan
from tests.test_stage14b4_photo_asset import raw_asset
from tests.test_stage16c_tech_card import plan
from tests.test_stage16e2_contract import OWNER_TG, STRANGER_TG, contract_engine, load_migration, login, ready, run
from tests.test_stage16e4_signing import issued

CATALOG = load_contract_catalog()
ROOM, ROOM2 = str(uuid.uuid4()), str(uuid.uuid4())
S1, S2 = str(uuid.uuid4()), str(uuid.uuid4())
PHOTO = str(uuid.uuid4())
PERSON = str(uuid.uuid4())
PEOPLE = {PERSON: ("Anna Nowak", "Właścicielka")}
RID = str(uuid.uuid4())
DAY = date(2026, 10, 20)


def change(current=None, changes=None, rooms=(ROOM, ROOM2), surfaces=(S1, S2), photos=None, people=PEOPLE):
    photos = {S1: {PHOTO}} if photos is None else photos
    return A.apply_changes(current or A.empty_state(), changes or {}, room_ids=set(rooms), surface_ids=set(surfaces),
                           defect_photos_of=lambda sid: set(photos.get(sid, ())), people=people, catalog=CATALOG)


def refused(**kw):
    with pytest.raises(AcceptanceInvalidError) as exc:
        change(**kw)
    return exc.value.key, exc.value.reason


def facts(sid=S1, room=ROOM, quality="S2", statuses=("COMPLETED", "COMPLETED")):
    return SurfaceFacts(sid, f"Ściana {sid[:2]}", room, "Salon", "WALL", quality, tuple(WorkLine(f"Praca {i}", s) for i, s in enumerate(statuses)))


def remark(**over):
    return {"place": "Narożnik przy oknie", "description": "Smuga po gładzi", "classification": "REMOVABLE", "deadline": date(2026, 10, 25), **over}


# --- the entries ---------------------------------------------------------------------------------------------------------------------


def test_simple_fields_are_checked_normalised_and_cleared():
    state = change(changes={"held_on": DAY, "held_time": "09:30", "notified_on": date(2026, 10, 15), "customer_absent": None, "conditions_note": " światło rozproszone ",
                            "batches": "farba L77", "instructions_given": True, "amount_due": "1234,5", "amount_retained": 500, "notes": "ok",
                            "instrument_keys": ["straightedge_2m", "raking_light", "raking_light"]})
    assert (state["held_time"], state["customer_absent"], state["conditions_note"], state["instructions_given"]) == ("09:30", False, "światło rozproszone", True)
    assert (state["amount_due"], state["amount_retained"], state["instrument_keys"]) == ("1234.50", "500.00", ["straightedge_2m", "raking_light"])
    cleared = change(state, {"held_time": None, "amount_due": None, "conditions_note": None, "instrument_keys": None})
    assert cleared["held_time"] is None and cleared["amount_due"] is None and cleared["instrument_keys"] == []
    assert refused(changes={"held_time": "9:30"}) == ("held_time", "BAD_TIME")
    assert refused(changes={"held_on": "2026-10-20"}) == ("held_on", "WRONG_TYPE")
    assert refused(changes={"customer_absent": "yes"}) == ("customer_absent", "WRONG_TYPE")
    assert refused(changes={"instructions_given": 1}) == ("instructions_given", "WRONG_TYPE")
    assert refused(changes={"amount_due": "dużo"}) == ("amount_due", A.BAD_MONEY)
    assert refused(changes={"amount_due": True}) == ("amount_due", "WRONG_TYPE")
    assert refused(changes={"amount_retained": "-5"}) == ("amount_retained", A.BAD_MONEY)
    assert refused(changes={"instrument_keys": ["hammer"]}) == ("instrument_keys", A.UNKNOWN_INSTRUMENT)
    assert refused(changes={"instrument_keys": "all"}) == ("instrument_keys", "WRONG_TYPE")
    assert refused(changes={"notes": "x" * 4001}) == ("notes", "TOO_LONG")
    assert refused(changes={"nonsense": 1}) == ("nonsense", A.UNKNOWN_FIELD)


def test_the_rooms_in_scope_must_be_rooms_with_planned_works_and_people_are_copied_by_name():
    assert change(changes={"room_ids": [ROOM, ROOM, ROOM2]})["room_ids"] == [ROOM, ROOM2]
    assert change(changes={"room_ids": None})["room_ids"] == []
    assert refused(changes={"room_ids": [str(uuid.uuid4())]}) == ("room_ids", A.UNKNOWN_ROOM)
    assert refused(changes={"room_ids": ["x"]}) == ("room_ids", "WRONG_TYPE")
    assert refused(changes={"room_ids": "all"}) == ("room_ids", "WRONG_TYPE")
    state = change(changes={"attendees": [{"person_id": PERSON}, {"name": "Jan Sąsiad", "role": "administrator"}]})
    assert [a["name"] for a in state["attendees"]] == ["Anna Nowak", "Jan Sąsiad"]
    assert refused(changes={"attendees": [{"person_id": str(uuid.uuid4())}]}) == ("attendees", "UNKNOWN_PERSON")


def test_a_remark_needs_a_place_a_description_and_a_class_and_a_removable_one_its_deadline():
    state = change(changes={"surfaces": {S1: {"assessed": True, "remarks": {RID: {**remark(), "photo_ids": [PHOTO, PHOTO]}}}}})
    saved = state["surfaces"][S1]["remarks"][RID]
    assert saved == {"place": "Narożnik przy oknie", "description": "Smuga po gładzi", "classification": "REMOVABLE", "deadline": "2026-10-25",
                     "photo_ids": [PHOTO], "id": RID} and state["surfaces"][S1]["assessed"] is True
    significant = change(changes={"surfaces": {S1: {"remarks": {RID: remark(classification="SIGNIFICANT", deadline=None)}}}})
    assert "deadline" not in significant["surfaces"][S1]["remarks"][RID]  # a significant one is not repaired in a term: a new acceptance follows
    assert refused(changes={"surfaces": {S1: {"remarks": {RID: remark(deadline=None)}}}}) == ("deadline", A.BAD_REMARK)
    assert refused(changes={"surfaces": {S1: {"remarks": {RID: {"place": "x"}}}}}) == ("remarks", A.BAD_REMARK)
    assert refused(changes={"surfaces": {S1: {"remarks": {RID: remark(classification="MINOR")}}}}) == ("classification", "NOT_AN_OPTION")
    assert refused(changes={"surfaces": {S1: {"remarks": {RID: remark(photo_ids=[str(uuid.uuid4())])}}}}) == ("photo_ids", A.UNKNOWN_PHOTO)
    assert refused(changes={"surfaces": {S2: {"remarks": {RID: remark(photo_ids=[PHOTO])}}}}) == ("photo_ids", A.UNKNOWN_PHOTO)  # a photo of another surface
    assert refused(changes={"surfaces": {S1: {"remarks": {RID: remark(place=5)}}}}) == ("place", "WRONG_TYPE")
    assert refused(changes={"surfaces": {S1: {"remarks": {RID: remark(place="x" * 256)}}}}) == ("place", "TOO_LONG")
    assert refused(changes={"surfaces": {S1: {"remarks": {RID: {**remark(), "colour": "red"}}}}}) == ("remarks", "WRONG_TYPE")
    assert refused(changes={"surfaces": {S1: {"remarks": {"x": remark()}}}}) == ("remarks", "WRONG_TYPE")  # the key of a remark is a UUID
    assert refused(changes={"surfaces": {str(uuid.uuid4()): {"assessed": True}}}) == ("surfaces", A.UNKNOWN_SURFACE)
    assert refused(changes={"surfaces": {S1: {"assessed": "yes"}}}) == ("assessed", "WRONG_TYPE")
    assert refused(changes={"surfaces": {S1: {"verdict": "ok"}}}) == ("surfaces", "WRONG_TYPE")
    assert refused(changes={"surfaces": [S1]}) == ("surfaces", "WRONG_TYPE")


def test_a_remark_is_changed_by_its_fields_and_removed_with_null_and_a_failed_change_changes_nothing():
    first = change(changes={"surfaces": {S1: {"assessed": True, "remarks": {RID: remark()}}}})
    moved = change(first, {"surfaces": {S1: {"remarks": {RID: {"classification": "SIGNIFICANT"}}}}})
    assert moved["surfaces"][S1]["remarks"][RID]["classification"] == "SIGNIFICANT" and moved["surfaces"][S1]["remarks"][RID]["place"] == "Narożnik przy oknie"
    assert first["surfaces"][S1]["remarks"][RID]["classification"] == "REMOVABLE"  # the earlier state is untouched
    redated = change(first, {"surfaces": {S1: {"remarks": {RID: {"deadline": date(2026, 11, 2)}}}}})
    assert redated["surfaces"][S1]["remarks"][RID]["deadline"] == "2026-11-02"
    with pytest.raises(AcceptanceInvalidError):
        change(first, {"notes": "nowe", "surfaces": {S1: {"remarks": {RID: {"deadline": None}}}}})
    assert first["notes"] is None
    gone = change(first, {"surfaces": {S1: {"remarks": {RID: None}}}})
    assert gone["surfaces"][S1]["remarks"] == {} and gone["surfaces"][S1]["assessed"] is True
    assert S1 not in change(first, {"surfaces": {S1: None}})["surfaces"]


# --- the derived result ----------------------------------------------------------------------------------------------------------------


def entry(*classes):
    return {"assessed": True, "remarks": {str(uuid.uuid4()): {"classification": c} for c in classes}}


def test_the_result_of_a_surface_follows_the_works_and_the_classes_of_its_remarks():
    done, undone = facts(), facts(statuses=("COMPLETED", "IN_PROGRESS"))
    assert A.surface_result(done, entry()) == A.ACCEPTED and A.surface_result(done, None) == A.ACCEPTED
    assert A.surface_result(done, entry("REMOVABLE", "REMOVABLE")) == A.WITH_REMARKS
    assert A.surface_result(done, entry("REMOVABLE", "SIGNIFICANT")) == A.NOT_ACCEPTED  # one significant remark is enough
    assert A.surface_result(undone, entry()) == A.NOT_ACCEPTED  # unfinished works: the scope is not done
    assert A.surface_result(facts(statuses=("NOT_STARTED",)), entry()) == A.NOT_ACCEPTED
    assert A.surface_result(facts(statuses=()), entry()) == A.ACCEPTED  # nothing planned: nothing missing (such a surface is not in scope anyway)


def test_the_result_of_the_whole_is_the_worst_of_its_surfaces_and_the_kind_follows_the_rooms():
    assert A.overall_result([]) is None
    assert A.overall_result([A.ACCEPTED, A.ACCEPTED]) == A.ACCEPTED
    assert A.overall_result([A.ACCEPTED, A.WITH_REMARKS]) == A.WITH_REMARKS
    assert A.overall_result([A.WITH_REMARKS, A.NOT_ACCEPTED, A.ACCEPTED]) == A.NOT_ACCEPTED
    everything = {S1: facts(S1, ROOM), S2: facts(S2, ROOM2), "s3": facts("s3", "room-without-plan", statuses=())}
    assert A.scope_kind({"room_ids": []}, everything) is None
    assert A.scope_kind({"room_ids": [ROOM]}, everything) == "PARTIAL"
    assert A.scope_kind({"room_ids": [ROOM, ROOM2]}, everything) == "FINAL"
    assert A.scope_kind({"room_ids": [ROOM, ROOM2, "room-without-plan"]}, everything) == "FINAL"  # a room with nothing planned changes nothing
    assert [f.id for f in A.surfaces_in_scope({"room_ids": [ROOM]}, everything)] == [S1]


def test_the_conditions_of_the_assessment_follow_the_standards_in_scope():
    surfaces = {S1: facts(S1, ROOM, quality="S2"), S2: facts(S2, ROOM2, quality="S4")}
    shown = A.conditions({"room_ids": [ROOM, ROOM2]}, surfaces, CATALOG)
    assert [(c["key"], c["lighting"], c["requires_agreement"]) for c in shown] == [("S2", "DIFFUSE", False), ("S4", "AGREED_BEFORE_WORK", True)]
    assert [c["key"] for c in A.conditions({"room_ids": [ROOM]}, surfaces, CATALOG)] == ["S2"]
    assert A.conditions({"room_ids": []}, surfaces, CATALOG) == []


# --- what is missing ---------------------------------------------------------------------------------------------------------------------


def codes(blockers):
    return [b.code for b in blockers]


def ready_state(**over):
    state = {**A.empty_state(), "room_ids": [ROOM], "held_on": DAY, "attendees": [{"person_id": None, "name": "A", "role": None}],
             "surfaces": {S1: {"assessed": True, "remarks": {}}}}
    state.update(over)
    return state


def test_the_blockers_are_listed_in_the_order_of_doing():
    surfaces = {S1: facts(S1, ROOM)}
    assert codes(A.evaluate(A.empty_state(), surfaces, CATALOG)) == [A.SCOPE_REQUIRED, A.HELD_ON_REQUIRED, A.NO_ATTENDEES]
    assert A.evaluate(ready_state(), surfaces, CATALOG) == []
    unassessed = A.evaluate(ready_state(surfaces={}), surfaces, CATALOG)
    assert [(b.code, b.details) for b in unassessed] == [(A.SURFACE_NOT_ASSESSED, {"surface_ids": [S1]})]
    # a room without planned works is no scope
    assert A.SCOPE_REQUIRED in codes(A.evaluate(ready_state(room_ids=[ROOM2]), surfaces, CATALOG))


def test_a_standard_that_needs_agreed_conditions_needs_them_written_down():
    surfaces = {S1: facts(S1, ROOM, quality="S4")}
    assert codes(A.evaluate(ready_state(), surfaces, CATALOG)) == [A.CONDITIONS_NOTE_REQUIRED]
    assert A.evaluate(ready_state(conditions_note="Światło boczne z lampy LED, obserwacja z 1,5 m"), surfaces, CATALOG) == []
    assert A.evaluate(ready_state(), {S1: facts(S1, ROOM, quality="Q4")}, CATALOG) == []  # Q4's raking light is its own condition, nothing to agree


def test_an_absent_customer_was_called_twice_in_order_and_needs_no_people():
    surfaces = {S1: facts(S1, ROOM)}
    absent = ready_state(customer_absent=True, attendees=[])
    assert codes(A.evaluate(absent, surfaces, CATALOG)) == [A.NOTIFIED_ON_REQUIRED, A.RENOTIFIED_ON_REQUIRED]
    one = {**absent, "notified_on": date(2026, 10, 10)}
    assert codes(A.evaluate(one, surfaces, CATALOG)) == [A.RENOTIFIED_ON_REQUIRED]
    both = {**one, "renotified_on": date(2026, 10, 14)}
    assert A.evaluate(both, surfaces, CATALOG) == []
    assert codes(A.evaluate({**both, "renotified_on": date(2026, 10, 10)}, surfaces, CATALOG)) == [A.NOTIFICATION_ORDER]  # the second call after the first
    assert codes(A.evaluate({**both, "held_on": date(2026, 10, 12)}, surfaces, CATALOG)) == [A.NOTIFICATION_ORDER]  # the acceptance after the second call
    assert A.evaluate({**both, "held_on": date(2026, 10, 14)}, surfaces, CATALOG) == []  # on the day of the second call is still in order


# --- the draft -----------------------------------------------------------------------------------------------------------------------------


def svc(db):
    return AcceptanceService(db)


async def complete_works(db, w, surface=None):
    """Mark every planned work of the surface completed (the execution of Stage 13)."""
    plan_row = (await db.execute(select(SurfaceWorkPlan).where(SurfaceWorkPlan.surface_id == (surface or w.wall).id))).scalar_one()
    for work in (await db.execute(select(SurfacePlannedWork).where(SurfacePlannedWork.work_plan_id == plan_row.id))).scalars():
        db.add(SurfaceWorkExecution(occurrence_key=work.occurrence_key, work_plan_id=plan_row.id, price_item_id=work.price_item_id,
                                    status=WorkExecutionStatus.COMPLETED, started_at=datetime.now(UTC), completed_at=datetime.now(UTC)))
    await db.commit()


async def defect_photo(db, w, surface_id, caption="Smuga po gładzi"):
    asset = raw_asset(w.owner, w.project, status=PhotoAssetStatus.READY, width=1600, height=1200)
    db.add(asset)
    await db.flush()
    attachment = PhotoAttachment(asset_id=asset.id, project_id=w.project.id, context=PhotoAttachmentContext.SURFACE, category=PhotoCategory.DEFECT,
                                 caption=caption, surface_id=surface_id, position=0)
    db.add(attachment)
    await db.commit()
    return str(attachment.id)


async def test_the_draft_is_one_per_object_and_the_read_model_derives_the_result_from_the_works_and_the_remarks(db_session):
    w = await ready(db_session, telegram_id=9971)
    wall, salon = str(w.wall.id), str(w.salon.id)
    first, created = await svc(db_session).open_draft(w.project.id, w.owner.id)
    again, created_again = await svc(db_session).open_draft(w.project.id, w.owner.id)
    assert created and not created_again and again.id == first.id and first.sequence == 1
    empty = await svc(db_session).read(first)
    assert empty.scope_kind is None and empty.result is None and empty.surfaces == [] and [(r.id, r.name, r.surfaces) for r in empty.rooms] == [(salon, "Salon", 1)]
    row = await svc(db_session).update(w.project.id, first.id, w.owner.id, {"room_ids": [salon], "held_on": DAY})
    read = await svc(db_session).read(row)
    assert read.scope_kind == "FINAL" and [s.id for s in read.surfaces] == [wall] and read.surfaces[0].quality_target == "S2"
    assert (read.surfaces[0].incomplete, read.surfaces[0].result, read.result) == (2, "NOT_ACCEPTED", "NOT_ACCEPTED")  # the works are not done yet
    assert [(c.key, c.lighting) for c in read.conditions] == [("S2", "DIFFUSE")]
    await complete_works(db_session, w)
    photo = await defect_photo(db_session, w, w.wall.id)
    row = await svc(db_session).update(w.project.id, first.id, w.owner.id, {"surfaces": {wall: {"assessed": True}}})
    read = await svc(db_session).read(row)
    assert (read.surfaces[0].incomplete, read.surfaces[0].result, read.result) == (0, "ACCEPTED", "ACCEPTED")
    assert [p.id for p in read.surfaces[0].photo_options] == [photo]
    rid = str(uuid.uuid4())
    row = await svc(db_session).update(w.project.id, first.id, w.owner.id, {"surfaces": {wall: {"remarks": {rid: {**remark(), "photo_ids": [photo]}}}}})
    read = await svc(db_session).read(row)
    assert read.result == "ACCEPTED_WITH_REMARKS" and [(r.id, r.classification, r.deadline, r.photo_ids) for r in read.surfaces[0].remarks] == [(rid, "REMOVABLE", date(2026, 10, 25), [photo])]
    row = await svc(db_session).update(w.project.id, first.id, w.owner.id, {"surfaces": {wall: {"remarks": {rid: {"classification": "SIGNIFICANT"}}}}})
    assert (await svc(db_session).read(row)).result == "NOT_ACCEPTED"
    row = await svc(db_session).update(w.project.id, first.id, w.owner.id, {"surfaces": {wall: {"remarks": {rid: None}}}})
    assert (await svc(db_session).read(row)).result == "ACCEPTED"
    assert [b.code for b in (await svc(db_session).read(row)).blockers] == ["CONTRACT_REQUIRED", "NO_ATTENDEES"]


async def test_a_partial_acceptance_becomes_final_when_every_room_with_planned_works_is_in_scope(db_session):
    w = await ready(db_session, telegram_id=9972)
    kitchen_wall = Surface(room_id=w.kuchnia.id, name="Ściana K", surface_type=SurfaceType.WALL)
    db_session.add(kitchen_wall)
    await db_session.commit()
    await plan(db_session, kitchen_wall, [w.item_a], quality=QualityLevel.Q4)
    draft, _ = await svc(db_session).open_draft(w.project.id, w.owner.id)
    salon, kitchen = str(w.salon.id), str(w.kuchnia.id)
    one = await svc(db_session).read(await svc(db_session).update(w.project.id, draft.id, w.owner.id, {"room_ids": [salon]}))
    assert one.scope_kind == "PARTIAL" and [s.room_name for s in one.surfaces] == ["Salon"]
    both = await svc(db_session).read(await svc(db_session).update(w.project.id, draft.id, w.owner.id, {"room_ids": [salon, kitchen]}))
    assert both.scope_kind == "FINAL" and [s.room_name for s in both.surfaces] == ["Salon", "Kuchnia"]
    assert [c.key for c in both.conditions] == ["S2", "Q4"]


async def test_the_draft_is_abandoned_and_a_new_one_gets_the_next_number_and_foreign_data_is_refused(db_session):
    mine = await ready(db_session, telegram_id=9973)
    theirs = await ready(db_session, telegram_id=9974)
    draft, _ = await svc(db_session).open_draft(mine.project.id, mine.owner.id)
    with pytest.raises(AcceptanceInvalidError) as foreign_room:
        await svc(db_session).update(mine.project.id, draft.id, mine.owner.id, {"room_ids": [str(theirs.salon.id)]})
    assert foreign_room.value.reason == A.UNKNOWN_ROOM
    with pytest.raises(AcceptanceInvalidError) as foreign_surface:
        await svc(db_session).update(mine.project.id, draft.id, mine.owner.id, {"surfaces": {str(theirs.wall.id): {"assessed": True}}})
    assert foreign_surface.value.reason == A.UNKNOWN_SURFACE
    with pytest.raises(AcceptanceInvalidError) as foreign_person:
        await svc(db_session).update(mine.project.id, draft.id, mine.owner.id, {"attendees": [{"person_id": str(theirs.person.id)}]})
    assert foreign_person.value.reason == "UNKNOWN_PERSON"
    with pytest.raises(AcceptanceInvalidError):  # a surface without planned works cannot be assessed
        await svc(db_session).update(mine.project.id, draft.id, mine.owner.id, {"surfaces": {str(uuid.uuid4()): {"assessed": True}}})
    with pytest.raises(ProjectNotFoundError):
        await svc(db_session).open_draft(mine.project.id, theirs.owner.id)
    with pytest.raises(ProjectNotFoundError):
        await svc(db_session).get(mine.project.id, draft.id, theirs.owner.id)
    with pytest.raises(AcceptanceNotFoundError):
        await svc(db_session).get(mine.project.id, uuid.uuid4(), mine.owner.id)
    other, _ = await svc(db_session).open_draft(theirs.project.id, theirs.owner.id)
    with pytest.raises(AcceptanceNotFoundError):
        await svc(db_session).get(mine.project.id, other.id, mine.owner.id)
    archived = await svc(db_session).archive_draft(mine.project.id, draft.id, mine.owner.id)
    assert archived.status == "ARCHIVED"
    with pytest.raises(AcceptanceNotEditableError):
        await svc(db_session).update(mine.project.id, draft.id, mine.owner.id, {"notes": "późno"})
    with pytest.raises(AcceptanceNotEditableError):
        await svc(db_session).archive_draft(mine.project.id, draft.id, mine.owner.id)
    assert (await svc(db_session).open_draft(mine.project.id, mine.owner.id))[0].sequence == 2


async def test_the_gate_asks_for_the_contract_the_profile_and_the_customer_first(db_session):
    w, owner_id, project_id, contract_id = await issued(db_session, 9975)
    draft, _ = await svc(db_session).open_draft(project_id, owner_id)
    _, sources, blockers = await svc(db_session).gate(project_id, draft.id, owner_id)
    assert [b.code for b in blockers] == ["SCOPE_REQUIRED", "HELD_ON_REQUIRED", "NO_ATTENDEES"]  # a contract exists
    sources.base.contract = None
    sources.base.executor = None
    sources.base.client = None
    from app.domain.services.acceptance_service import data_of

    assert [b.code for b in svc(db_session).blockers(data_of(draft), sources)][:3] == ["EXECUTOR_PROFILE_REQUIRED", "CLIENT_REQUIRED", "CONTRACT_REQUIRED"]


# --- HTTP ----------------------------------------------------------------------------------------------------------------------------------------


def url(project_id, tail=""):
    return f"/api/projects/{project_id}/acceptances{tail}"


async def test_the_routes_need_a_token_and_a_stranger_gets_404(async_client: AsyncClient, db_session):
    mine = await ready(db_session, telegram_id=OWNER_TG)
    theirs = await ready(db_session, telegram_id=STRANGER_TG)
    assert (await async_client.get(url(mine.project.id))).status_code == 401
    headers = await login(async_client)
    draft, _ = await svc(db_session).open_draft(theirs.project.id, theirs.owner.id)
    for response in (
        await async_client.get(url(theirs.project.id), headers=headers),
        await async_client.post(url(theirs.project.id), headers=headers),
        await async_client.get(url(mine.project.id, f"/{uuid.uuid4()}"), headers=headers),
        await async_client.get(url(mine.project.id, f"/{draft.id}"), headers=headers),
        await async_client.patch(url(theirs.project.id, f"/{draft.id}"), json={"notes": "x"}, headers=headers),
    ):
        assert response.status_code == 404


async def test_open_assess_and_abandon_over_http(async_client: AsyncClient, db_session):
    w = await ready(db_session, telegram_id=OWNER_TG)
    await complete_works(db_session, w)
    headers = await login(async_client)
    pid, salon, wall = str(w.project.id), str(w.salon.id), str(w.wall.id)
    created = await async_client.post(url(pid), headers=headers)
    assert created.status_code == 201, created.text
    body = created.json()
    assert (body["sequence"], body["status"], body["scope_kind"], body["result"], body["surfaces"]) == (1, "DRAFT", None, None, [])
    assert body["rooms"] == [{"id": salon, "name": "Salon", "surfaces": 1}] and body["contract"] is None
    assert (await async_client.post(url(pid), headers=headers)).status_code == 200
    hid = body["id"]
    assert (await async_client.patch(url(pid, f"/{hid}"), json={}, headers=headers)).status_code == 422
    assert (await async_client.patch(url(pid, f"/{hid}"), json={"unknown": 1}, headers=headers)).status_code == 422
    bad = await async_client.patch(url(pid, f"/{hid}"), json={"amount_due": "dużo"}, headers=headers)
    assert bad.status_code == 422 and bad.json()["detail"] == {"code": "ACCEPTANCE_INVALID", "message": "acceptance 'amount_due': BAD_MONEY",
                                                              "details": {"key": "amount_due", "reason": "BAD_MONEY"}}
    rid = str(uuid.uuid4())
    saved = await async_client.patch(url(pid, f"/{hid}"), json={
        "room_ids": [salon], "held_on": "2026-10-20", "instrument_keys": ["raking_light"], "amount_due": "1500", "amount_retained": "200,5",
        "surfaces": {wall: {"assessed": True, "remarks": {rid: {"place": "Sufit", "description": "Smuga", "classification": "REMOVABLE", "deadline": "2026-10-25"}}}}},
        headers=headers)
    assert saved.status_code == 200, saved.text
    out = saved.json()
    assert (out["scope_kind"], out["result"], out["amount_due"], out["amount_retained"]) == ("FINAL", "ACCEPTED_WITH_REMARKS", "1500.00", "200.50")
    assert out["surfaces"][0]["remarks"] == [{"id": rid, "place": "Sufit", "description": "Smuga", "classification": "REMOVABLE", "deadline": "2026-10-25", "photo_ids": []}]
    assert out["conditions"] == [{"key": "S2", "lighting": "DIFFUSE", "requires_agreement": False, "text_pl": out["conditions"][0]["text_pl"]}]
    wrong = await async_client.patch(url(pid, f"/{hid}"), json={"surfaces": {wall: {"remarks": {rid: {"deadline": "jutro"}}}}}, headers=headers)
    assert wrong.status_code == 422 and wrong.json()["detail"]["details"] == {"key": "deadline", "reason": "WRONG_TYPE"}
    assert (await async_client.get(url(pid), headers=headers)).json()["total"] == 1
    gone = await async_client.post(url(pid, f"/{hid}/archive"), headers=headers)
    assert gone.status_code == 200 and gone.json()["status"] == "ARCHIVED"
    assert (await async_client.patch(url(pid, f"/{hid}"), json={"notes": "x"}, headers=headers)).status_code == 409
    assert (await async_client.post(url(pid, f"/{hid}/archive"), headers=headers)).status_code == 409


# --- migration ---------------------------------------------------------------------------------------------------------------------------------------


def test_revision_chain_and_length():
    module = load_migration("0050_acceptance_protocols")
    assert module.revision == "0050_acceptance_protocols" and module.down_revision == "0049_concealed_works" and len(module.revision) <= 32


def engine_0050():
    engine = contract_engine()
    for name in ("0045_contract_issue", "0046_contract_signed", "0047_handover_protocols", "0048_handover_issue", "0049_concealed_works", "0050_acceptance_protocols"):
        run(engine, name, "upgrade")
    return engine


ROW = ("INSERT INTO acceptance_protocols (id, owner_id, project_id, sequence, status, customer_absent, attendees, room_ids, instrument_keys, surfaces, "
       "instructions_given, issued_at, snapshot, document_html, created_at, updated_at) VALUES (:id, 'u1', 'p1', :sequence, :status, 0, '[]', '[]', '[]', '{}', "
       "0, :issued, :snapshot, :html, '2026-10-11', '2026-10-11')")
BLANK = {"issued": None, "snapshot": None, "html": None}
FROZEN = {"issued": "2026-10-11", "snapshot": "{}", "html": "<html></html>"}


def test_the_database_allows_one_draft_a_number_once_known_states_and_a_frozen_issued_protocol():
    engine = engine_0050()
    with engine.begin() as conn:
        conn.execute(text(ROW), {"id": "a", "sequence": 1, "status": "DRAFT", **BLANK})
        conn.execute(text(ROW), {"id": "b", "sequence": 2, "status": "ARCHIVED", **BLANK})
        conn.execute(text(ROW), {"id": "c", "sequence": 3, "status": "ISSUED", **FROZEN})
    for bad in (
        {"id": "d", "sequence": 4, "status": "DRAFT", **BLANK}, {"id": "e", "sequence": 1, "status": "ARCHIVED", **BLANK},
        {"id": "f", "sequence": 5, "status": "SIGNED", **BLANK}, {"id": "g", "sequence": 0, "status": "ARCHIVED", **BLANK},
        {"id": "h", "sequence": 6, "status": "ISSUED", **BLANK},
    ):
        with pytest.raises(IntegrityError), engine.begin() as conn:
            conn.execute(text(ROW), bad)
    assert {c["name"] for c in inspect(engine).get_columns("acceptance_protocols")} == {c.name for c in AcceptanceProtocol.__table__.columns}


def test_downgrade_refuses_while_a_protocol_exists_and_then_drops_only_the_table():
    engine = engine_0050()
    with engine.begin() as conn:
        conn.execute(text(ROW), {"id": "a", "sequence": 1, "status": "DRAFT", **BLANK})
    with pytest.raises(RuntimeError, match="1 acceptance protocol"):
        run(engine, "0050_acceptance_protocols", "downgrade")
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM acceptance_protocols"))
    run(engine, "0050_acceptance_protocols", "downgrade")
    assert "acceptance_protocols" not in inspect(engine).get_table_names() and "concealed_works_protocols" in inspect(engine).get_table_names()
    run(engine, "0050_acceptance_protocols", "upgrade")
