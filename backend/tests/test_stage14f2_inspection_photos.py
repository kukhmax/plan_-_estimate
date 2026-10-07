"""Stage 14F.2 — INSPECTION / FINDING photo contexts in the media API.

Upload (multipart), attach-existing, list filters (inspection / question / finding / lineage), counts, detail and
ownership for photos taken as evidence of an inspection, one of its checklist questions, or one finding. WORK stays
unsupported (14H). No migration: the 0032 schema already carries the columns, CHECK branches and unique indexes.
"""

import uuid
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.main import app
from app.models.checklist import AnswerType, ChecklistQuestion
from app.models.inspection import InspectionFinding
from app.models.photo_asset import PhotoAsset
from app.models.photo_attachment import PhotoAttachment
from tests import test_stage14c4_photos_api as c4
from tests.test_estimates import _make_room
from tests.test_stage14c4_photos_api import call, form, path_for
from tests.test_work_recommendation_accept import _make_inspection, _make_template

api = c4.api  # shared fixture: uploads on, in-memory recording storage, two projects of the owner + a foreign project


@pytest.fixture
async def http(api):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {api.token}"
        yield client


@pytest.fixture
async def w(api):
    """Inspection data: an inspection of the owner's room with two questions, three findings (two rows of one lineage
    and one of another) — plus a second template's question, an inspection in the owner's OTHER project and a foreign one."""
    db = api.db
    template = await _make_template(db)
    other_template = await _make_template(db)
    q1 = ChecklistQuestion(template_id=template.id, position=1, key="q1", text_key="q.one", answer_type=AnswerType.BOOLEAN)
    q2 = ChecklistQuestion(template_id=template.id, position=2, key="q2", text_key="q.two", answer_type=AnswerType.BOOLEAN)
    foreign_q = ChecklistQuestion(
        template_id=other_template.id, position=1, key="fq", text_key="q.foreign", answer_type=AnswerType.BOOLEAN
    )
    db.add_all([q1, q2, foreign_q])
    await db.commit()
    inspection = await _make_inspection(db, api.room, template.id)
    lineage, other_lineage = uuid.uuid4(), uuid.uuid4()
    old_row = InspectionFinding(inspection_id=inspection.id, question_id=q1.id, finding_key="CRACK", lineage_id=lineage, is_active=False)
    new_row = InspectionFinding(inspection_id=inspection.id, question_id=q1.id, finding_key="CRACK", lineage_id=lineage)
    other = InspectionFinding(inspection_id=inspection.id, question_id=q2.id, finding_key="MOLD", lineage_id=other_lineage)
    db.add_all([old_row, new_row, other])
    room2 = await _make_room(db, api.project2)
    inspection2 = await _make_inspection(db, room2.id, template.id)
    finding2 = InspectionFinding(inspection_id=inspection2.id, finding_key="CRACK")
    foreign_inspection = await _make_inspection(db, api.foreign_room, template.id)
    foreign_finding = InspectionFinding(inspection_id=foreign_inspection.id, finding_key="CRACK")
    db.add_all([finding2, foreign_finding])
    await db.commit()
    return SimpleNamespace(
        inspection=inspection.id, q1=q1.id, q2=q2.id, foreign_q=foreign_q.id, lineage=lineage, other_lineage=other_lineage,
        old_row=old_row.id, new_row=new_row.id, other=other.id,
        inspection2=inspection2.id, finding2=finding2.id, foreign_inspection=foreign_inspection.id,
        foreign_finding=foreign_finding.id, foreign_lineage=foreign_finding.lineage_id,
    )


async def up(a, *, context, target=None, extra=(), project=None, token=None):
    if target is None and context != "ROOM":
        target = {"PROJECT": ("caption", ""), "SURFACE": ("surface_id", str(a.surface)), "OPENING": ("opening_id", str(a.opening))}[context]
    return await call(path_for(project or a.project), token=token or a.token, body=form(a, context=context, target=target, extra=extra))


async def upload_ok(a, **kw) -> dict:
    c = await up(a, **kw)
    assert c.status == 201, c.body
    return c.json()


def code(c) -> str:
    return c.json()["detail"]["code"]


async def totals(db) -> tuple[int, int]:
    return await c4.counts(db)


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


async def test_upload_inspection_level_photo(api, w):
    body = await upload_ok(api, context="INSPECTION", target=("inspection_id", str(w.inspection)))
    attachment = body["attachment"]
    assert attachment["context"] == "INSPECTION"
    assert attachment["inspection_id"] == str(w.inspection)
    assert attachment["question_id"] is None and attachment["finding_id"] is None
    assert attachment["room_id"] is None and attachment["surface_id"] is None and attachment["opening_id"] is None


async def test_upload_question_level_photo_uses_the_eighth_scalar_field(api, w):
    body = await upload_ok(
        api, context="INSPECTION", target=("inspection_id", str(w.inspection)),
        extra=[("question_id", str(w.q1)), ("category", "DEFECT"), ("caption", "pęknięcie"), ("include_in_report", "true"), ("source", "CAMERA")],
    )
    attachment = body["attachment"]
    assert attachment["question_id"] == str(w.q1) and attachment["inspection_id"] == str(w.inspection)
    assert attachment["category"] == "DEFECT" and attachment["include_in_report"] is True
    assert body["asset"]["capture_source"] == "CAMERA"


async def test_upload_finding_photo(api, w):
    body = await upload_ok(api, context="FINDING", target=("finding_id", str(w.new_row)), extra=[("category", "DEFECT")])
    attachment = body["attachment"]
    assert attachment["context"] == "FINDING" and attachment["finding_id"] == str(w.new_row)
    assert attachment["inspection_id"] is None and attachment["question_id"] is None


async def test_nine_scalar_fields_are_still_refused(api, w):
    c = await up(
        api, context="INSPECTION", target=("inspection_id", str(w.inspection)),
        extra=[("question_id", str(w.q1)), ("category", "DEFECT"), ("caption", "x"), ("include_in_report", "true"),
               ("source", "CAMERA"), ("room_id", str(api.room))],
    )
    assert c.status == 422 and code(c) == "PHOTO_UPLOAD_MALFORMED"


@pytest.mark.parametrize(
    ("label", "context", "target", "extra"),
    [
        ("inspection without id", "INSPECTION", ("caption", ""), []),
        ("question without inspection", "INSPECTION", ("question_id", "Q1"), []),
        ("finding without id", "FINDING", ("caption", ""), []),
        ("finding with inspection", "FINDING", ("finding_id", "F"), [("inspection_id", "I")]),
        ("finding with question", "FINDING", ("finding_id", "F"), [("question_id", "Q1")]),
        ("room with question", "ROOM", ("room_id", "ROOM"), [("question_id", "Q1")]),
        ("project with finding", "PROJECT", ("finding_id", "F"), []),
        ("inspection with finding", "INSPECTION", ("inspection_id", "I"), [("finding_id", "F")]),
    ],
)
async def test_wrong_target_shapes_are_refused_without_writes(api, w, label, context, target, extra):
    real = {"Q1": str(w.q1), "F": str(w.new_row), "I": str(w.inspection), "ROOM": str(api.room)}
    target = (target[0], real.get(target[1], target[1]))
    extra = [(name, real.get(value, value)) for name, value in extra]
    before = await totals(api.db)
    c = await up(api, context=context, target=target, extra=extra)
    assert c.status == 422, label
    assert code(c) in {"PHOTO_UPLOAD_MALFORMED", "PHOTO_ATTACHMENT_INVALID"}, label
    assert await totals(api.db) == before
    assert c4.temp_clean(api)


@pytest.mark.parametrize(
    ("label", "context", "target", "extra", "expected"),
    [
        ("inspection of another project of the owner", "INSPECTION", "inspection2", [], "INSPECTION_NOT_FOUND"),
        ("foreign inspection", "INSPECTION", "foreign_inspection", [], "INSPECTION_NOT_FOUND"),
        ("random inspection", "INSPECTION", None, [], "INSPECTION_NOT_FOUND"),
        ("question of another template", "INSPECTION", "inspection", [("question_id", "foreign_q")], "QUESTION_NOT_FOUND"),
        ("random question", "INSPECTION", "inspection", [("question_id", None)], "QUESTION_NOT_FOUND"),
        ("finding of another project of the owner", "FINDING", "finding2", [], "FINDING_NOT_FOUND"),
        ("foreign finding", "FINDING", "foreign_finding", [], "FINDING_NOT_FOUND"),
        ("random finding", "FINDING", None, [], "FINDING_NOT_FOUND"),
    ],
)
async def test_ownership_chain_is_enforced_with_one_not_found_per_kind(api, w, label, context, target, extra, expected):
    column = "inspection_id" if context == "INSPECTION" else "finding_id"
    value = str(getattr(w, target)) if target else str(uuid.uuid4())
    extras = [(name, str(getattr(w, v)) if v else str(uuid.uuid4())) for name, v in extra]
    before = await totals(api.db)
    c = await up(api, context=context, target=(column, value), extra=extras)
    assert c.status == 404 and code(c) == expected, (label, c.body)
    assert await totals(api.db) == before
    assert c4.temp_clean(api)


async def test_another_owner_cannot_use_my_inspection_or_finding(api, w):
    for context, column, value in (("INSPECTION", "inspection_id", w.inspection), ("FINDING", "finding_id", w.new_row)):
        c = await up(api, context=context, target=(column, str(value)), project=api.foreign_project, token=api.other_token)
        assert c.status == 404, context
        c = await up(api, context=context, target=(column, str(value)), token=api.other_token)
        assert c.status == 404 and code(c) == "PROJECT_NOT_FOUND", context


# ---------------------------------------------------------------------------
# Attach an existing photo
# ---------------------------------------------------------------------------


async def test_attach_existing_photo_to_inspection_question_and_finding(api, http, w):
    first = await upload_ok(api, context="ROOM")
    asset_id = first["asset"]["id"]
    url = f"{path_for(api.project)}/{asset_id}/attachments"
    r = await http.post(url, json={"context": "INSPECTION", "inspection_id": str(w.inspection)})
    assert r.status_code == 201 and r.json()["question_id"] is None
    r = await http.post(url, json={"context": "INSPECTION", "inspection_id": str(w.inspection), "question_id": str(w.q1)})
    assert r.status_code == 201 and r.json()["question_id"] == str(w.q1)  # inspection- and question-level coexist
    r = await http.post(url, json={"context": "INSPECTION", "inspection_id": str(w.inspection), "question_id": str(w.q2)})
    assert r.status_code == 201  # another question of the same inspection
    r = await http.post(url, json={"context": "FINDING", "finding_id": str(w.new_row), "category": "DEFECT"})
    assert r.status_code == 201 and r.json()["finding_id"] == str(w.new_row)
    detail = await http.get(f"{path_for(api.project)}/{asset_id}")
    assert {a["context"] for a in detail.json()["attachments"]} == {"ROOM", "INSPECTION", "FINDING"}


@pytest.mark.parametrize(
    "payload",
    [
        lambda w: {"context": "INSPECTION", "inspection_id": str(w.inspection)},
        lambda w: {"context": "INSPECTION", "inspection_id": str(w.inspection), "question_id": str(w.q1)},
        lambda w: {"context": "FINDING", "finding_id": str(w.new_row)},
    ],
)
async def test_the_same_target_twice_is_a_duplicate_but_archive_frees_it(api, http, w, payload):
    asset_id = (await upload_ok(api, context="ROOM"))["asset"]["id"]
    url = f"{path_for(api.project)}/{asset_id}/attachments"
    first = await http.post(url, json=payload(w))
    assert first.status_code == 201
    again = await http.post(url, json=payload(w))
    assert again.status_code == 409 and again.json()["detail"]["code"] == "PHOTO_ATTACHMENT_DUPLICATE"
    archived = await http.post(f"/api/projects/{api.project}/photo-attachments/{first.json()['id']}/archive")
    assert archived.status_code == 200
    third = await http.post(url, json=payload(w))
    assert third.status_code == 201  # an archived duplicate does not block a new active one


async def test_attach_to_work_is_still_unsupported_and_extra_fields_are_rejected(api, http, w):
    asset_id = (await upload_ok(api, context="ROOM"))["asset"]["id"]
    url = f"{path_for(api.project)}/{asset_id}/attachments"
    r = await http.post(url, json={"context": "WORK"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "PHOTO_CONTEXT_NOT_SUPPORTED"
    r = await http.post(url, json={"context": "FINDING", "finding_id": str(w.new_row), "occurrence_key": str(uuid.uuid4())})
    assert r.status_code == 422  # still extra="forbid"
    r = await http.post(url, json={"context": "FINDING", "finding_id": str(w.foreign_finding)})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "FINDING_NOT_FOUND"


async def test_the_attachment_target_cannot_be_changed_by_patch(api, http, w):
    made = await upload_ok(api, context="INSPECTION", target=("inspection_id", str(w.inspection)))
    attachment_id = made["attachment"]["id"]
    for field, value in (("inspection_id", str(w.inspection)), ("question_id", str(w.q1)), ("finding_id", str(w.new_row)), ("context", "FINDING")):
        r = await http.patch(f"/api/projects/{api.project}/photo-attachments/{attachment_id}", json={field: value})
        assert r.status_code == 422, field


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


async def evidence(api, w) -> SimpleNamespace:
    """insp = inspection-level, qa/qb = question-level, f_old / f_new = finding rows of ONE lineage, f_other = other lineage."""
    return SimpleNamespace(
        insp=(await upload_ok(api, context="INSPECTION", target=("inspection_id", str(w.inspection))))["attachment"]["id"],
        qa=(await upload_ok(api, context="INSPECTION", target=("inspection_id", str(w.inspection)), extra=[("question_id", str(w.q1))]))["attachment"]["id"],
        qb=(await upload_ok(api, context="INSPECTION", target=("inspection_id", str(w.inspection)), extra=[("question_id", str(w.q2))]))["attachment"]["id"],
        f_old=(await upload_ok(api, context="FINDING", target=("finding_id", str(w.old_row))))["attachment"]["id"],
        f_new=(await upload_ok(api, context="FINDING", target=("finding_id", str(w.new_row))))["attachment"]["id"],
        f_other=(await upload_ok(api, context="FINDING", target=("finding_id", str(w.other))))["attachment"]["id"],
        room=(await upload_ok(api, context="ROOM"))["attachment"]["id"],
    )


def ids(r) -> list[str]:
    assert r.status_code == 200, r.text
    return [i["attachment"]["id"] for i in r.json()["items"]]


async def test_list_by_inspection_question_finding(api, http, w):
    e = await evidence(api, w)
    base = path_for(api.project)
    assert sorted(ids(await http.get(base, params={"context": "INSPECTION", "inspection_id": str(w.inspection)}))) == sorted([e.insp, e.qa, e.qb])
    assert sorted(ids(await http.get(base, params={"context": "INSPECTION", "inspection_id": str(w.inspection), "question_id": str(w.q1)}))) == sorted([e.qa])
    assert sorted(ids(await http.get(base, params={"context": "FINDING", "finding_id": str(w.new_row)}))) == sorted([e.f_new])
    assert sorted(ids(await http.get(base, params={"context": "FINDING", "finding_id": str(w.old_row)}))) == sorted([e.f_old])
    assert sorted(ids(await http.get(base, params={"context": "ROOM", "room_id": str(api.room)}))) == sorted([e.room])  # untouched


async def test_list_by_lineage_returns_the_photos_of_every_row_of_the_lineage(api, http, w):
    e = await evidence(api, w)
    base = path_for(api.project)
    assert sorted(ids(await http.get(base, params={"lineage": str(w.lineage)}))) == sorted([e.f_old, e.f_new])
    assert sorted(ids(await http.get(base, params={"lineage": str(w.other_lineage)}))) == sorted([e.f_other])
    # the category / report filters still apply, and an archived photo moves to the archive view
    await http.post(f"/api/projects/{api.project}/photo-attachments/{e.f_old}/archive")
    assert sorted(ids(await http.get(base, params={"lineage": str(w.lineage)}))) == sorted([e.f_new])
    assert sorted(ids(await http.get(base, params={"lineage": str(w.lineage), "archived": "true"}))) == sorted([e.f_old])
    assert sorted(ids(await http.get(base, params={"lineage": str(w.lineage), "category": "DEFECT"}))) == sorted([])


async def test_lineage_of_another_project_or_owner_or_nothing_is_a_plain_not_found(api, http, w):
    base = path_for(api.project)
    for lineage in (w.foreign_lineage, uuid.uuid4()):
        r = await http.get(base, params={"lineage": str(lineage)})
        assert r.status_code == 404 and r.json()["detail"]["code"] == "FINDING_NOT_FOUND"
    # the owner's finding of another project is not a lineage of THIS project either
    other_lineage = (await api.db.get(InspectionFinding, w.finding2)).lineage_id
    r = await http.get(base, params={"lineage": str(other_lineage)})
    assert r.status_code == 404
    # a stranger gets the project's own not-found
    r = await http.get(base, params={"lineage": str(w.lineage)}, headers={"Authorization": f"Bearer {api.other_token}"})
    assert r.status_code == 404 and r.json()["detail"]["code"] == "PROJECT_NOT_FOUND"


@pytest.mark.parametrize(
    "params",
    [
        lambda w, api: {"lineage": str(w.lineage), "context": "FINDING"},
        lambda w, api: {"lineage": str(w.lineage), "finding_id": str(w.new_row)},
        lambda w, api: {"lineage": str(w.lineage), "in_room_id": str(api.room)},
        lambda w, api: {"inspection_id": str(w.inspection)},  # an id needs its context
        lambda w, api: {"question_id": str(w.q1)},
        lambda w, api: {"finding_id": str(w.new_row)},
        lambda w, api: {"context": "INSPECTION"},  # the context needs its id
        lambda w, api: {"context": "FINDING"},
        lambda w, api: {"context": "FINDING", "finding_id": str(w.new_row), "inspection_id": str(w.inspection)},
        lambda w, api: {"context": "INSPECTION", "inspection_id": str(w.inspection), "finding_id": str(w.new_row)},
        lambda w, api: {"in_room_id": str(api.room), "inspection_id": str(w.inspection)},
        lambda w, api: {"context": "ROOM", "room_id": str(api.room), "question_id": str(w.q1)},
    ],
)
async def test_invalid_filter_combinations_are_422(api, http, w, params):
    r = await http.get(path_for(api.project), params=params(w, api))
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["code"] == "PHOTO_ATTACHMENT_INVALID"


async def test_list_filters_enforce_the_ownership_chain(api, http, w):
    base = path_for(api.project)
    for params, expected in (
        ({"context": "INSPECTION", "inspection_id": str(w.foreign_inspection)}, "INSPECTION_NOT_FOUND"),
        ({"context": "INSPECTION", "inspection_id": str(w.inspection2)}, "INSPECTION_NOT_FOUND"),
        ({"context": "INSPECTION", "inspection_id": str(w.inspection), "question_id": str(w.foreign_q)}, "QUESTION_NOT_FOUND"),
        ({"context": "FINDING", "finding_id": str(w.foreign_finding)}, "FINDING_NOT_FOUND"),
    ):
        r = await http.get(base, params=params)
        assert r.status_code == 404 and r.json()["detail"]["code"] == expected, params


async def test_pagination_cursor_is_bound_to_the_lineage_filter(api, http, w):
    e = await evidence(api, w)
    base = path_for(api.project)
    first = await http.get(base, params={"lineage": str(w.lineage), "limit": 1})
    assert len(ids(first)) == 1 and first.json()["next_cursor"]
    second = await http.get(base, params={"lineage": str(w.lineage), "limit": 1, "cursor": first.json()["next_cursor"]})
    assert len(ids(second)) == 1 and second.json()["next_cursor"] is None
    assert sorted(ids(first) + ids(second)) == sorted([e.f_old, e.f_new])  # both rows of the lineage, each exactly once
    wrong = await http.get(base, params={"lineage": str(w.other_lineage), "limit": 1, "cursor": first.json()["next_cursor"]})
    assert wrong.status_code == 422 and wrong.json()["detail"]["code"] == "PHOTO_CURSOR_INVALID"
    wrong = await http.get(base, params={"context": "FINDING", "finding_id": str(w.old_row), "limit": 1, "cursor": first.json()["next_cursor"]})
    assert wrong.status_code == 422


# ---------------------------------------------------------------------------
# Counts and detail
# ---------------------------------------------------------------------------


async def test_counts_report_inspection_finding_and_lineage_photos_apart_from_room_totals(api, http, w):
    e = await evidence(api, w)
    await upload_ok(api, context="FINDING", target=("finding_id", str(w.new_row)))  # a second photo on the same row
    r = await http.get(f"{path_for(api.project)}/counts")
    assert r.status_code == 200
    data = r.json()
    assert data["inspections"] == {str(w.inspection): 3}  # inspection-level + two question-level
    assert data["findings"] == {str(w.old_row): 1, str(w.new_row): 2, str(w.other): 1}
    assert data["lineages"] == {str(w.lineage): 3, str(w.other_lineage): 1}  # both rows of the lineage added up
    assert data["rooms"] == {str(api.room): 1} and data["room_totals"] == {str(api.room): 1}  # only the ROOM photo
    # archived photos are not counted, empty targets are absent
    await http.post(f"/api/projects/{api.project}/photo-attachments/{e.qb}/archive")
    await http.post(f"/api/projects/{api.project}/photo-attachments/{e.f_other}/archive")
    data = (await http.get(f"{path_for(api.project)}/counts")).json()
    assert data["inspections"] == {str(w.inspection): 2}
    assert str(w.other) not in data["findings"] and str(w.other_lineage) not in data["lineages"]


async def test_counts_of_a_project_without_evidence_have_empty_maps(api, http):
    data = (await http.get(f"{path_for(api.project)}/counts")).json()
    assert data["inspections"] == {} and data["findings"] == {} and data["lineages"] == {} and data["questions"] == {}


async def test_detail_and_list_items_carry_the_new_target_fields(api, http, w):
    made = await upload_ok(api, context="INSPECTION", target=("inspection_id", str(w.inspection)), extra=[("question_id", str(w.q2))])
    detail = (await http.get(f"{path_for(api.project)}/{made['asset']['id']}")).json()
    assert detail["attachments"][0]["inspection_id"] == str(w.inspection) and detail["attachments"][0]["question_id"] == str(w.q2)
    item = (await http.get(path_for(api.project), params={"context": "INSPECTION", "inspection_id": str(w.inspection)})).json()["items"][0]
    assert item["attachment"]["finding_id"] is None


async def test_deleting_nothing_changes_for_existing_contexts(api, http, w):
    """The four 14C contexts keep their shape: the new columns are simply null."""
    made = [await upload_ok(api, context=c) for c in ("PROJECT", "ROOM", "SURFACE", "OPENING")]
    for body in made:
        attachment = body["attachment"]
        assert attachment["inspection_id"] is None and attachment["question_id"] is None and attachment["finding_id"] is None
    assert (await api.db.execute(select(func.count()).select_from(PhotoAsset))).scalar_one() == 4


# ---------------------------------------------------------------------------
# 14F.3: per-question counts and the site-only list
# ---------------------------------------------------------------------------


async def test_counts_split_question_level_photos_per_inspection_and_question(api, http, w):
    await evidence(api, w)  # inspection-level x1, question q1 x1, question q2 x1
    await upload_ok(api, context="INSPECTION", target=("inspection_id", str(w.inspection)), extra=[("question_id", str(w.q1))])
    data = (await http.get(f"{path_for(api.project)}/counts")).json()
    assert data["questions"] == {str(w.inspection): {str(w.q1): 2, str(w.q2): 1}}  # the inspection-level photo is in no question
    assert data["inspections"] == {str(w.inspection): 4}
    # archived question-level photos leave the map, and an emptied inspection disappears from it
    attachments = (await http.get(path_for(api.project), params={"context": "INSPECTION", "inspection_id": str(w.inspection), "question_id": str(w.q2)})).json()["items"]
    await http.post(f"/api/projects/{api.project}/photo-attachments/{attachments[0]['attachment']['id']}/archive")
    data = (await http.get(f"{path_for(api.project)}/counts")).json()
    assert data["questions"] == {str(w.inspection): {str(w.q1): 2}}


async def test_site_only_list_leaves_out_inspection_evidence(api, http, w):
    e = await evidence(api, w)
    base = path_for(api.project)
    everything = ids(await http.get(base))
    assert e.insp in everything and e.f_new in everything and e.room in everything  # the unfiltered list is still complete
    site = ids(await http.get(base, params={"site_only": "true"}))
    assert site == [e.room]
    assert ids(await http.get(base, params={"site_only": "true", "archived": "true"})) == []
    assert ids(await http.get(base, params={"site_only": "true", "category": "GENERAL"})) == [e.room]


@pytest.mark.parametrize(
    "extra",
    [
        lambda w, api: {"context": "ROOM", "room_id": str(api.room)},
        lambda w, api: {"in_room_id": str(api.room)},
        lambda w, api: {"lineage": str(w.lineage)},
        lambda w, api: {"inspection_id": str(w.inspection)},
    ],
)
async def test_site_only_cannot_be_combined_with_targets(api, http, w, extra):
    r = await http.get(path_for(api.project), params={"site_only": "true", **extra(w, api)})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "PHOTO_ATTACHMENT_INVALID"


async def test_site_only_cursor_is_bound_to_the_filter(api, http, w):
    await evidence(api, w)
    await upload_ok(api, context="ROOM")
    base = path_for(api.project)
    first = await http.get(base, params={"site_only": "true", "limit": 1})
    assert first.json()["next_cursor"]
    again = await http.get(base, params={"limit": 1, "cursor": first.json()["next_cursor"]})  # same cursor, no site_only
    assert again.status_code == 422 and again.json()["detail"]["code"] == "PHOTO_CURSOR_INVALID"
