"""Stage 14H.5 — `inspection_surfaces` in GET /photos/counts: the photos that live only in the inspections of a surface.

Inspection, question and finding photos are kept out of the site photo lists (and out of `surfaces`, `rooms`, `room_totals`) on
purpose, so the "inspect the wall / floor / ceiling" button needs a number of its own: for every surface, the photos of ALL
its inspections (inspection-level, question-level and the findings of those inspections). A room-level inspection (no
surface) is not counted here. Same visibility rules as every other count (active attachment of a READY, non-archived asset,
full ownership chain).
"""

import uuid
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.checklist import AnswerType, ChecklistQuestion, Substrate
from app.models.inspection import Inspection, InspectionFinding, InspectionStatus
from tests import test_stage14c4_photos_api as c4
from tests.test_planned_work_coefficient_assignments import _make_room, _make_surface
from tests.test_stage14c4_photos_api import call, form, path_for
from tests.test_work_recommendation_accept import _make_template

api = c4.api


@pytest.fixture
async def http(api):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {api.token}"
        yield client


async def make_inspection(db, room_id, template_id, surface_id=None) -> Inspection:
    inspection = Inspection(
        room_id=room_id, surface_id=surface_id, template_id=template_id, substrate=Substrate.CONCRETE,
        status=InspectionStatus.COMPLETED,
    )
    db.add(inspection)
    await db.commit()
    return inspection


@pytest.fixture
async def w(api):
    """Surface A: two inspections (one with a question and a finding). Surface B: one inspection. A room-level inspection
    (no surface). An inspection of the owner's OTHER project and a foreign one."""
    db = api.db
    template = await _make_template(db)
    question = ChecklistQuestion(template_id=template.id, position=1, key="q1", text_key="q.one", answer_type=AnswerType.BOOLEAN)
    db.add(question)
    await db.commit()
    surface_b = await _make_surface(db, api.room, name="Ściana B")
    a1 = await make_inspection(db, api.room, template.id, api.surface)
    a2 = await make_inspection(db, api.room, template.id, api.surface)
    b1 = await make_inspection(db, api.room, template.id, surface_b.id)
    room_level = await make_inspection(db, api.room, template.id, None)
    finding_a1 = InspectionFinding(inspection_id=a1.id, question_id=question.id, finding_key="CRACK", lineage_id=uuid.uuid4())
    finding_b1 = InspectionFinding(inspection_id=b1.id, finding_key="MOLD", lineage_id=uuid.uuid4())
    finding_room = InspectionFinding(inspection_id=room_level.id, finding_key="DAMP", lineage_id=uuid.uuid4())
    db.add_all([finding_a1, finding_b1, finding_room])
    await db.commit()
    return SimpleNamespace(
        a1=a1.id, a2=a2.id, b1=b1.id, room_level=room_level.id, surface_a=api.surface, surface_b=surface_b.id,
        question=question.id, finding_a1=finding_a1.id, finding_b1=finding_b1.id, finding_room=finding_room.id,
        template=template.id,
    )


async def photo(api, *, context, inspection_id=None, finding_id=None, question_id=None):
    """Upload one photo to an inspection (inspection-level, or for a question) or to a finding."""
    if context == "FINDING":
        target, extra = ("finding_id", str(finding_id)), []
    else:
        target = ("inspection_id", str(inspection_id))
        extra = [("question_id", str(question_id))] if question_id else []
    c = await call(path_for(api.project), token=api.token, body=form(api, context=context, target=target, extra=extra))
    assert c.status == 201, c.body
    return c.json()["attachment"]["id"]


async def counts(http, api) -> dict:
    r = await http.get(f"{path_for(api.project)}/counts")
    assert r.status_code == 200, r.text
    return r.json()


async def test_a_project_without_inspection_photos_has_an_empty_map(http, api):
    assert (await counts(http, api))["inspection_surfaces"] == {}


async def test_inspection_question_and_finding_photos_of_a_surface_add_up_across_its_inspections(http, api, w):
    await photo(api, context="INSPECTION", inspection_id=w.a1)
    await photo(api, context="INSPECTION", inspection_id=w.a1, question_id=w.question)
    await photo(api, context="FINDING", finding_id=w.finding_a1)
    await photo(api, context="INSPECTION", inspection_id=w.a2)
    await photo(api, context="INSPECTION", inspection_id=w.b1)
    await photo(api, context="FINDING", finding_id=w.finding_b1)
    data = await counts(http, api)
    assert data["inspection_surfaces"] == {str(w.surface_a): 4, str(w.surface_b): 2}


async def test_a_room_level_inspection_is_not_counted_on_any_surface(http, api, w):
    await photo(api, context="INSPECTION", inspection_id=w.room_level)
    await photo(api, context="FINDING", finding_id=w.finding_room)
    data = await counts(http, api)
    assert data["inspection_surfaces"] == {}
    assert data["inspections"] == {str(w.room_level): 1}  # the per-inspection map still has it


async def test_the_new_map_does_not_leak_into_the_site_counts(http, api, w):
    await photo(api, context="INSPECTION", inspection_id=w.a1)
    await photo(api, context="FINDING", finding_id=w.finding_a1)
    data = await counts(http, api)
    assert data["surfaces"] == {} and data["rooms"] == {} and data["room_totals"] == {} and data["project"] == 0
    assert data["work_surfaces"] == {}


async def test_a_site_photo_of_the_surface_is_not_an_inspection_photo(http, api, w):
    c = await call(path_for(api.project), token=api.token, body=form(api, context="SURFACE", target=("surface_id", str(api.surface))))
    assert c.status == 201, c.body
    data = await counts(http, api)
    assert data["surfaces"] == {str(api.surface): 1}
    assert data["inspection_surfaces"] == {}


async def test_archived_attachments_are_not_counted_and_come_back_when_restored(http, api, w):
    first = await photo(api, context="INSPECTION", inspection_id=w.a1)
    await photo(api, context="FINDING", finding_id=w.finding_a1)
    base = f"/api/projects/{api.project}/photo-attachments/{first}"
    assert (await http.post(f"{base}/archive")).status_code == 200
    assert (await counts(http, api))["inspection_surfaces"] == {str(w.surface_a): 1}
    assert (await http.post(f"{base}/restore")).status_code == 200
    assert (await counts(http, api))["inspection_surfaces"] == {str(w.surface_a): 2}


async def test_the_last_photo_removes_the_surface_from_the_map(http, api, w):
    only = await photo(api, context="INSPECTION", inspection_id=w.b1)
    assert (await counts(http, api))["inspection_surfaces"] == {str(w.surface_b): 1}
    await http.post(f"/api/projects/{api.project}/photo-attachments/{only}/archive")
    assert (await counts(http, api))["inspection_surfaces"] == {}


async def test_another_project_and_another_owner_never_contribute(http, api, w):
    db = api.db
    foreign_surface = await _make_surface(db, api.foreign_room, name="Obca")
    await make_inspection(db, api.foreign_room, w.template, foreign_surface.id)
    other_room = await _make_room(db, api.project2)
    other_surface = await _make_surface(db, other_room.id, name="Druga ściana")
    await make_inspection(db, other_room.id, w.template, other_surface.id)
    await photo(api, context="INSPECTION", inspection_id=w.a1)
    data = await counts(http, api)
    assert data["inspection_surfaces"] == {str(w.surface_a): 1}
    assert (await http.get(f"{path_for(api.foreign_project)}/counts")).status_code == 404  # not this owner's project


async def test_the_response_declares_the_field_for_every_project(http, api):
    data = await counts(http, api)
    assert "inspection_surfaces" in data and isinstance(data["inspection_surfaces"], dict)


def test_the_field_is_required_in_the_published_contract():
    schema = app.openapi()["components"]["schemas"]["PhotoCountsResponse"]
    assert "inspection_surfaces" in schema["required"]
