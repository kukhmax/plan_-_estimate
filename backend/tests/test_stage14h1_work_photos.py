"""Stage 14H.1 — WORK (execution evidence) photo context in the media API.

Upload (multipart), attach-existing, list filters, counts, detail, archive / restore and ownership for photos of one
planned-work occurrence of a surface (surface + Stage 13 `occurrence_key`, with the operation snapshotted as
`price_item_id` by the server). Work-plan edits never touch photos: APPEND / apply-to-all never copy, REPLACE / removal never
delete (detached evidence stays listable and reportable), a re-added item is a new occurrence. A photo before the work
needs no execution row. No migration: the 0032 schema already carries the columns, CHECK branch and unique index.
"""

import uuid
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.domain.services.work_plan_service import SurfaceWorkPlanService
from app.main import app
from app.models.photo_attachment import PhotoAttachment
from app.models.price_item import PriceItem
from app.models.work_execution import SurfaceWorkExecution
from app.schemas.work_plan import OrderedPriceItemSelection
from tests import test_stage14c4_photos_api as c4
from tests.test_occurrence_key import _save
from tests.test_planned_work_coefficient_assignments import (
    _make_price_item,
    _make_room,
    _make_surface,
)
from tests.test_stage14c4_photos_api import call, form, path_for

Sel = OrderedPriceItemSelection
api = c4.api  # shared fixture: uploads on, in-memory recording storage, two projects of the owner + a foreign project


@pytest.fixture
async def http(api):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {api.token}"
        yield client


def _ids(**kw):
    return SimpleNamespace(**kw)


@pytest.fixture
async def w(api):
    """Work plans: surface 1 (three works: A, A, B), surface 2 of the same room (one work), a surface of the owner's OTHER
    project and a foreign surface — each with its own plan and keys."""
    db = api.db
    a = await _make_price_item(db, api.me, code="W14H_A")
    b = await _make_price_item(db, api.me, code="W14H_B")
    foreign_item = await _make_price_item(db, api.other, code="W14H_F")
    service = SurfaceWorkPlanService(db)
    owner, project, room = _ids(id=api.me), _ids(id=api.project), _ids(id=api.room)

    plan = await _save(service, owner, project, room, _ids(id=api.surface), [Sel(price_item_id=a.id), Sel(price_item_id=a.id), Sel(price_item_id=b.id)])
    keys = [x.occurrence_key for x in plan.planned_works]

    surface2 = await _make_surface(db, api.room, name="Ściana 2")
    plan2 = await _save(service, owner, project, room, _ids(id=surface2.id), [Sel(price_item_id=b.id)])

    room2 = await _make_room(db, api.project2)
    surface3 = await _make_surface(db, room2.id, name="Ściana innego obiektu")
    plan3 = await _save(service, owner, _ids(id=api.project2), _ids(id=room2.id), _ids(id=surface3.id), [Sel(price_item_id=a.id)])

    foreign_surface = await _make_surface(db, api.foreign_room, name="Obca ściana")
    plan4 = await _save(
        service, _ids(id=api.other), _ids(id=api.foreign_project), _ids(id=api.foreign_room), _ids(id=foreign_surface.id),
        [Sel(price_item_id=foreign_item.id)],
    )
    return SimpleNamespace(
        service=service, owner=owner, project=project, room=room, a=a.id, b=b.id,
        keys=keys, surface2=surface2.id, key2=plan2.planned_works[0].occurrence_key,
        surface3=surface3.id, key3=plan3.planned_works[0].occurrence_key, project2=api.project2,
        foreign_surface=foreign_surface.id, foreign_key=plan4.planned_works[0].occurrence_key,
    )


async def up(a, *, surface, key, extra=(), project=None, token=None, context="WORK"):
    target = ("surface_id", str(surface))
    fields = [("occurrence_key", str(key))] if key is not None else []
    return await call(
        path_for(project or a.project), token=token or a.token,
        body=form(a, context=context, target=target, extra=[*fields, *extra]),
    )


async def upload_ok(a, **kw) -> dict:
    c = await up(a, **kw)
    assert c.status == 201, c.body
    return c.json()


def code(c) -> str:
    return c.json()["detail"]["code"]


async def execution_rows(db) -> int:
    return (await db.execute(select(func.count()).select_from(SurfaceWorkExecution))).scalar_one()


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


async def test_upload_work_photo_snapshots_the_operation_of_the_occurrence(api, w):
    body = await upload_ok(api, surface=api.surface, key=w.keys[0], extra=[("category", "BEFORE"), ("source", "CAMERA")])
    attachment = body["attachment"]
    assert attachment["context"] == "WORK"
    assert attachment["surface_id"] == str(api.surface) and attachment["occurrence_key"] == str(w.keys[0])
    assert attachment["price_item_id"] == str(w.a)
    assert attachment["category"] == "BEFORE"
    for other in ("room_id", "opening_id", "inspection_id", "question_id", "finding_id"):
        assert attachment[other] is None
    assert body["asset"]["capture_source"] == "CAMERA"


async def test_each_occurrence_snapshots_its_own_operation(api, w):
    first = await upload_ok(api, surface=api.surface, key=w.keys[1])
    third = await upload_ok(api, surface=api.surface, key=w.keys[2])
    assert first["attachment"]["price_item_id"] == str(w.a)
    assert third["attachment"]["price_item_id"] == str(w.b)


async def test_a_photo_before_the_work_needs_no_execution_row(api, w):
    before = await execution_rows(api.db)
    body = await upload_ok(api, surface=api.surface, key=w.keys[0], extra=[("category", "BEFORE")])
    assert body["attachment"]["category"] == "BEFORE"
    assert await execution_rows(api.db) == before == 0  # execution rows are lazy; photographing never creates one


async def test_the_client_cannot_name_the_operation(api, w):
    c = await up(api, surface=api.surface, key=w.keys[0], extra=[("price_item_id", str(w.b))])
    assert c.status == 422 and code(c) == "PHOTO_UPLOAD_MALFORMED"
    assert await c4.counts(api.db) == (0, 0) and c4.temp_clean(api)


def test_the_scalar_field_limit_stays_eight_and_the_largest_work_form_fills_it():
    # Contract §29: WORK needs no new limit. A ninth valid field cannot exist, so the constant itself is the contract.
    from app.api.v1.endpoints import photos

    largest_work_form = {
        "upload_id", "context", "surface_id", "occurrence_key", "category", "caption", "include_in_report", "source",
    }
    assert photos.MAX_FIELDS == 8
    assert len(largest_work_form) == photos.MAX_FIELDS and largest_work_form <= photos.SCALAR_FIELDS


async def test_a_work_form_with_every_optional_field_fits_the_eight_field_limit(api, w):
    body = await upload_ok(
        api, surface=api.surface, key=w.keys[0],
        extra=[("category", "BEFORE"), ("caption", "przed pracą"), ("include_in_report", "true"), ("source", "CAMERA")],
    )  # upload_id, context, surface_id, occurrence_key, category, caption, include_in_report, source = 8 fields
    assert body["attachment"]["caption"] == "przed pracą" and body["attachment"]["include_in_report"] is True


async def test_a_ninth_scalar_field_is_refused(api, w):
    c = await up(
        api, surface=api.surface, key=w.keys[0],
        extra=[("category", "BEFORE"), ("caption", "x"), ("include_in_report", "true"), ("source", "CAMERA"),
               ("room_id", str(api.room))],
    )
    assert c.status == 422 and code(c) == "PHOTO_UPLOAD_MALFORMED"
    assert await c4.counts(api.db) == (0, 0)


@pytest.mark.parametrize(
    ("label", "context", "target", "extra"),
    [
        ("work without surface", "WORK", ("caption", ""), [("occurrence_key", "K")]),
        ("work without key", "WORK", ("surface_id", "S"), []),
        ("work with room", "WORK", ("surface_id", "S"), [("occurrence_key", "K"), ("room_id", "ROOM")]),
        ("work with opening", "WORK", ("surface_id", "S"), [("occurrence_key", "K"), ("opening_id", "OPENING")]),
        ("key that is not a uuid", "WORK", ("surface_id", "S"), [("occurrence_key", "not-a-uuid")]),
        ("key on a surface photo", "SURFACE", ("surface_id", "S"), [("occurrence_key", "K")]),
        ("key on a room photo", "ROOM", ("room_id", "ROOM"), [("occurrence_key", "K")]),
        ("key on a project photo", "PROJECT", ("caption", ""), [("occurrence_key", "K")]),
    ],
)
async def test_upload_shape_errors_are_malformed_and_write_nothing(api, w, label, context, target, extra):
    def fill(value):
        return {"S": str(api.surface), "K": str(w.keys[0]), "ROOM": str(api.room), "OPENING": str(api.opening)}.get(value, value)

    c = await call(
        path_for(api.project), token=api.token,
        body=form(api, context=context, target=(target[0], fill(target[1])), extra=[(n, fill(v)) for n, v in extra]),
    )
    assert c.status == 422 and code(c) == "PHOTO_UPLOAD_MALFORMED", (label, c.body)
    assert await c4.counts(api.db) == (0, 0) and c4.temp_clean(api) and api.runtime.admission.in_use == 0


@pytest.mark.parametrize(
    "case",
    ["invented key", "key of another surface of the room", "key of the owner's other project", "foreign key"],
)
async def test_a_key_that_is_not_current_for_this_surface_is_409_and_nothing_is_stored(api, w, case):
    key = {
        "invented key": uuid.uuid4(),
        "key of another surface of the room": w.key2,
        "key of the owner's other project": w.key3,
        "foreign key": w.foreign_key,
    }[case]
    c = await up(api, surface=api.surface, key=key)
    assert c.status == 409 and code(c) == "WORK_OCCURRENCE_NOT_CURRENT", c.body
    assert await c4.counts(api.db) == (0, 0) and c4.temp_clean(api) and api.runtime.admission.in_use == 0
    assert not api.storage.puts  # refused before any object was written


@pytest.mark.parametrize("case", ["random", "surface of the owner's other project", "foreign surface"])
async def test_surfaces_outside_the_project_are_404(api, w, case):
    surface = {"random": uuid.uuid4(), "surface of the owner's other project": w.surface3, "foreign surface": w.foreign_surface}[case]
    c = await up(api, surface=surface, key=w.keys[0])
    assert c.status == 404 and code(c) == "SURFACE_NOT_FOUND"
    assert await c4.counts(api.db) == (0, 0)


async def test_another_user_cannot_photograph_my_work(api, w):
    c = await up(api, surface=api.surface, key=w.keys[0], token=api.other_token)
    assert c.status == 404 and code(c) == "PROJECT_NOT_FOUND"
    assert await c4.counts(api.db) == (0, 0)


async def test_the_service_refuses_a_target_that_already_names_the_operation(api, w):
    # The operation is always resolved from the plan: a caller cannot pre-set it on an incoming target.
    from app.domain.exceptions import PhotoAttachmentValidationError
    from app.domain.services.photo_attachment_service import (
        AttachmentTarget,
        PhotoAttachmentService,
    )
    from app.models.photo_attachment import PhotoAttachmentContext

    service = PhotoAttachmentService(api.db)
    target = AttachmentTarget(context=PhotoAttachmentContext.WORK, surface_id=api.surface, occurrence_key=w.keys[0])
    resolved = await service.validate_target(api.me, api.project, target)
    assert resolved.price_item_id == w.a and target.price_item_id is None
    with pytest.raises(PhotoAttachmentValidationError):
        await service.validate_target(api.me, api.project, AttachmentTarget(
            context=PhotoAttachmentContext.WORK, surface_id=api.surface, occurrence_key=w.keys[0], price_item_id=w.b))


async def test_the_same_bytes_with_the_same_upload_id_are_idempotent(api, w):
    upload_id = str(uuid.uuid4())
    def body():
        return form(api, upload_id=upload_id, context="WORK", target=("surface_id", str(api.surface)),
                    extra=[("occurrence_key", str(w.keys[0]))])

    first = await call(path_for(api.project), token=api.token, body=body())
    second = await call(path_for(api.project), token=api.token, body=body())
    assert first.status == 201 and second.status in (200, 201)
    assert await c4.counts(api.db) == (1, 1)


# ---------------------------------------------------------------------------
# Attach an existing asset
# ---------------------------------------------------------------------------


def attach_url(a, asset_id) -> str:
    return f"{path_for(a.project)}/{asset_id}/attachments"


async def test_attach_existing_asset_to_a_work(api, http, w):
    asset_id = (await upload_ok(api, surface=api.surface, key=w.keys[0], context="WORK"))["asset"]["id"]
    r = await http.post(attach_url(api, asset_id), json={"context": "WORK", "surface_id": str(api.surface), "occurrence_key": str(w.keys[2]),
                                                          "category": "AFTER"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["occurrence_key"] == str(w.keys[2]) and body["price_item_id"] == str(w.b) and body["category"] == "AFTER"


async def test_attach_does_not_accept_a_client_price_item(api, http, w):
    asset_id = (await upload_ok(api, surface=api.surface, key=w.keys[0]))["asset"]["id"]
    r = await http.post(attach_url(api, asset_id), json={"context": "WORK", "surface_id": str(api.surface),
                                                          "occurrence_key": str(w.keys[1]), "price_item_id": str(w.b)})
    assert r.status_code == 422  # extra="forbid": the operation is always taken from the plan


async def test_attach_rejections(api, http, w):
    asset_id = (await upload_ok(api, surface=api.surface, key=w.keys[0]))["asset"]["id"]
    url = attach_url(api, asset_id)
    r = await http.post(url, json={"context": "WORK", "surface_id": str(api.surface), "occurrence_key": str(uuid.uuid4())})
    assert r.status_code == 409 and code(r) == "WORK_OCCURRENCE_NOT_CURRENT"
    r = await http.post(url, json={"context": "WORK", "surface_id": str(api.surface), "occurrence_key": str(w.foreign_key)})
    assert r.status_code == 409 and code(r) == "WORK_OCCURRENCE_NOT_CURRENT"
    r = await http.post(url, json={"context": "WORK", "surface_id": str(w.foreign_surface), "occurrence_key": str(w.foreign_key)})
    assert r.status_code == 404 and code(r) == "SURFACE_NOT_FOUND"
    r = await http.post(url, json={"context": "WORK", "surface_id": str(api.surface)})
    assert r.status_code == 422 and code(r) == "PHOTO_ATTACHMENT_INVALID"
    r = await http.post(url, json={"context": "WORK", "occurrence_key": str(w.keys[1])})
    assert r.status_code == 422 and code(r) == "PHOTO_ATTACHMENT_INVALID"
    r = await http.post(url, json={"context": "SURFACE", "surface_id": str(api.surface), "occurrence_key": str(w.keys[1])})
    assert r.status_code == 422 and code(r) == "PHOTO_ATTACHMENT_INVALID"  # a key belongs to WORK only
    assert await c4.counts(api.db) == (1, 1)


async def test_duplicates_archive_frees_and_restore_refuses_a_duplicate(api, http, w):
    made = await upload_ok(api, surface=api.surface, key=w.keys[0])
    asset_id = made["asset"]["id"]
    payload = {"context": "WORK", "surface_id": str(api.surface), "occurrence_key": str(w.keys[0])}
    r = await http.post(attach_url(api, asset_id), json=payload)
    assert r.status_code == 409 and code(r) == "PHOTO_ATTACHMENT_DUPLICATE"
    r = await http.post(attach_url(api, asset_id), json={**payload, "occurrence_key": str(w.keys[1])})
    assert r.status_code == 201  # the same asset on ANOTHER occurrence of the surface is a different attachment
    att = made["attachment"]["id"]
    r = await http.post(f"{path_for(api.project).replace('/photos', '')}/photo-attachments/{att}/archive")
    assert r.status_code == 200
    r = await http.post(attach_url(api, asset_id), json=payload)
    assert r.status_code == 201  # the archived duplicate does not block a new active one
    r = await http.post(f"{path_for(api.project).replace('/photos', '')}/photo-attachments/{att}/restore")
    assert r.status_code == 409 and code(r) == "PHOTO_ATTACHMENT_DUPLICATE"


# ---------------------------------------------------------------------------
# Reads: list, counts, detail
# ---------------------------------------------------------------------------


def ids_of(response) -> list[str]:
    return [item["attachment"]["id"] for item in response.json()["items"]]


async def test_list_a_surfaces_work_photos_and_one_occurrence(api, http, w):
    p0 = (await upload_ok(api, surface=api.surface, key=w.keys[0]))["attachment"]["id"]
    p1 = (await upload_ok(api, surface=api.surface, key=w.keys[1]))["attachment"]["id"]
    p1b = (await upload_ok(api, surface=api.surface, key=w.keys[1]))["attachment"]["id"]
    other_surface = (await upload_ok(api, surface=w.surface2, key=w.key2))["attachment"]["id"]
    url = path_for(api.project)
    whole = await http.get(url, params={"context": "WORK", "surface_id": str(api.surface)})
    assert whole.status_code == 200 and set(ids_of(whole)) == {p0, p1, p1b}
    one = await http.get(url, params={"context": "WORK", "surface_id": str(api.surface), "occurrence_key": str(w.keys[1])})
    assert set(ids_of(one)) == {p1, p1b}
    other = await http.get(url, params={"context": "WORK", "surface_id": str(w.surface2)})
    assert ids_of(other) == [other_surface]
    item = whole.json()["items"][0]["attachment"]
    assert item["occurrence_key"] and item["price_item_id"]


async def test_work_photos_stay_out_of_every_site_list(api, http, w):
    work = (await upload_ok(api, surface=api.surface, key=w.keys[0]))["attachment"]["id"]
    site = (await upload_ok(api, context="SURFACE", surface=api.surface, key=None))["attachment"]["id"]
    url = path_for(api.project)
    surface_list = await http.get(url, params={"context": "SURFACE", "surface_id": str(api.surface)})
    assert ids_of(surface_list) == [site]
    assert ids_of(await http.get(url, params={"site_only": "true"})) == [site]
    assert ids_of(await http.get(url, params={"in_room_id": str(api.room)})) == [site]
    everything = await http.get(url)
    assert set(ids_of(everything)) == {work, site}  # the unfiltered list still shows all of the project's photos


@pytest.mark.parametrize(
    ("params", "status", "expected"),
    [
        ({"context": "WORK"}, 422, "PHOTO_ATTACHMENT_INVALID"),
        ({"context": "WORK", "surface_id": "S", "room_id": "ROOM"}, 422, "PHOTO_ATTACHMENT_INVALID"),
        ({"context": "WORK", "surface_id": "S", "opening_id": "OPENING"}, 422, "PHOTO_ATTACHMENT_INVALID"),
        ({"occurrence_key": "K"}, 422, "PHOTO_ATTACHMENT_INVALID"),
        ({"context": "SURFACE", "surface_id": "S", "occurrence_key": "K"}, 422, "PHOTO_ATTACHMENT_INVALID"),
        ({"site_only": "true", "occurrence_key": "K"}, 422, "PHOTO_ATTACHMENT_INVALID"),
        ({"context": "WORK", "surface_id": "RANDOM"}, 404, "SURFACE_NOT_FOUND"),
        ({"context": "WORK", "surface_id": "FOREIGN"}, 404, "SURFACE_NOT_FOUND"),
        ({"context": "WORK", "surface_id": "OTHERPROJECT"}, 404, "SURFACE_NOT_FOUND"),
    ],
)
async def test_list_filter_errors(api, http, w, params, status, expected):
    fill = {"S": str(api.surface), "ROOM": str(api.room), "OPENING": str(api.opening), "K": str(w.keys[0]),
            "RANDOM": str(uuid.uuid4()), "FOREIGN": str(w.foreign_surface), "OTHERPROJECT": str(w.surface3)}
    r = await http.get(path_for(api.project), params={k: fill.get(v, v) for k, v in params.items()})
    assert r.status_code == status and code(r) == expected


async def test_an_unknown_key_lists_nothing_and_never_leaks(api, http, w):
    await upload_ok(api, surface=api.surface, key=w.keys[0])
    r = await http.get(path_for(api.project), params={"context": "WORK", "surface_id": str(api.surface),
                                                      "occurrence_key": str(w.foreign_key)})
    assert r.status_code == 200 and r.json()["items"] == []


async def test_cursor_is_bound_to_the_occurrence_filter(api, http, w):
    for _ in range(3):
        await upload_ok(api, surface=api.surface, key=w.keys[1])
    await upload_ok(api, surface=api.surface, key=w.keys[0])
    url = path_for(api.project)
    first = await http.get(url, params={"context": "WORK", "surface_id": str(api.surface), "occurrence_key": str(w.keys[1]), "limit": 2})
    assert first.status_code == 200 and len(first.json()["items"]) == 2 and first.json()["next_cursor"]
    rest = await http.get(url, params={"context": "WORK", "surface_id": str(api.surface), "occurrence_key": str(w.keys[1]),
                                       "limit": 2, "cursor": first.json()["next_cursor"]})
    assert rest.status_code == 200 and len(rest.json()["items"]) == 1
    assert set(ids_of(first)).isdisjoint(ids_of(rest))
    wrong = await http.get(url, params={"context": "WORK", "surface_id": str(api.surface), "occurrence_key": str(w.keys[0]),
                                        "limit": 2, "cursor": first.json()["next_cursor"]})
    assert wrong.status_code == 422 and code(wrong) == "PHOTO_CURSOR_INVALID"


async def test_counts_keep_execution_evidence_apart_from_site_photos(api, http, w):
    await upload_ok(api, surface=api.surface, key=w.keys[0])
    await upload_ok(api, surface=api.surface, key=w.keys[1])
    await upload_ok(api, surface=api.surface, key=w.keys[1])
    await upload_ok(api, surface=w.surface2, key=w.key2)
    await upload_ok(api, context="SURFACE", surface=api.surface, key=None)
    data = (await http.get(f"{path_for(api.project)}/counts")).json()
    assert data["works"] == {str(w.keys[0]): 1, str(w.keys[1]): 2, str(w.key2): 1}
    assert data["work_surfaces"] == {str(api.surface): 3, str(w.surface2): 1}
    assert data["surfaces"] == {str(api.surface): 1}  # only the site photo
    assert data["room_totals"] == {str(api.room): 1}  # execution evidence never enters the room totals
    assert data["rooms"] == {} and data["project"] == 0


async def test_counts_are_empty_without_work_photos(api, http, w):
    data = (await http.get(f"{path_for(api.project)}/counts")).json()
    assert data["works"] == {} and data["work_surfaces"] == {}


async def test_detail_exposes_the_occurrence_and_the_operation(api, http, w):
    made = await upload_ok(api, surface=api.surface, key=w.keys[2])
    r = await http.get(f"{path_for(api.project)}/{made['asset']['id']}")
    assert r.status_code == 200
    attachment = r.json()["attachments"][0]
    assert attachment["context"] == "WORK" and attachment["occurrence_key"] == str(w.keys[2])
    assert attachment["price_item_id"] == str(w.b)


async def test_metadata_patch_keeps_the_target(api, http, w):
    made = await upload_ok(api, surface=api.surface, key=w.keys[0], extra=[("category", "BEFORE")])
    att = made["attachment"]["id"]
    root = path_for(api.project).replace("/photos", "")
    r = await http.patch(f"{root}/photo-attachments/{att}", json={"category": "IN_PROGRESS", "caption": "w trakcie"})
    assert r.status_code == 200
    body = r.json()
    assert body["category"] == "IN_PROGRESS" and body["caption"] == "w trakcie"
    assert body["occurrence_key"] == str(w.keys[0]) and body["price_item_id"] == str(w.a)
    r = await http.patch(f"{root}/photo-attachments/{att}", json={"occurrence_key": str(w.keys[1])})
    assert r.status_code == 422  # the target is immutable


# ---------------------------------------------------------------------------
# Work-plan edits never touch the photos (architecture §7)
# ---------------------------------------------------------------------------


async def photos_of(http, api, surface, key=None) -> set[str]:
    params = {"context": "WORK", "surface_id": str(surface)}
    if key is not None:
        params["occurrence_key"] = str(key)
    return set(ids_of(await http.get(path_for(api.project), params=params)))


async def resave(w, api, selection):
    return await _save(w.service, w.owner, w.project, w.room, _ids(id=api.surface), selection)


async def test_a_full_replace_save_that_keeps_the_keys_keeps_the_photos(api, http, w):
    photo = (await upload_ok(api, surface=api.surface, key=w.keys[0]))["attachment"]["id"]
    before = (await http.get(f"{path_for(api.project)}/counts")).json()["works"]
    plan = await resave(w, api, [
        Sel(price_item_id=w.a, occurrence_key=w.keys[0]), Sel(price_item_id=w.a, occurrence_key=w.keys[1]),
        Sel(price_item_id=w.b, occurrence_key=w.keys[2]),
    ])
    assert [x.occurrence_key for x in plan.planned_works] == w.keys  # the rows were rebuilt, the identities were not
    assert await photos_of(http, api, api.surface, w.keys[0]) == {photo}
    assert (await http.get(f"{path_for(api.project)}/counts")).json()["works"] == before


async def test_append_does_not_copy_and_the_new_work_starts_without_photos(api, http, w):
    photo = (await upload_ok(api, surface=api.surface, key=w.keys[0]))["attachment"]["id"]
    locked = await w.service.lock_plan(api.surface)
    appended = await w.service.append_one_planned_work_no_commit(locked, await api.db.get(PriceItem, w.a))
    await api.db.commit()
    assert appended.occurrence_key not in w.keys
    assert await photos_of(http, api, api.surface, appended.occurrence_key) == set()
    assert await photos_of(http, api, api.surface, w.keys[0]) == {photo}


async def test_apply_to_all_never_copies_photos(api, http, w):
    photo = (await upload_ok(api, surface=api.surface, key=w.keys[0]))["attachment"]["id"]
    wall_b = await _make_surface(api.db, api.room, name="Ściana B")
    await w.service.apply_to_room_walls(api.project, api.room, api.surface, api.me)
    new_plan = await api.db.execute(
        select(PhotoAttachment.id).where(PhotoAttachment.surface_id == wall_b.id)
    )
    assert new_plan.first() is None
    assert await photos_of(http, api, wall_b.id) == set()
    assert await photos_of(http, api, api.surface, w.keys[0]) == {photo}


async def test_replace_and_removal_keep_the_photos_as_detached_evidence(api, http, w):
    photo = (await upload_ok(api, surface=api.surface, key=w.keys[0], extra=[("category", "BEFORE")]))["attachment"]["id"]
    # REPLACE: the first work is dropped and a different item takes its place; the key leaves the plan.
    await resave(w, api, [Sel(price_item_id=w.b), Sel(price_item_id=w.a, occurrence_key=w.keys[1]), Sel(price_item_id=w.b, occurrence_key=w.keys[2])])
    assert w.keys[0] not in {x.occurrence_key for x in (await w.service.get_work_plan(api.project, api.room, api.surface, api.me)).planned_works}
    # the evidence is still listed, counted and labelled with the operation that was planned when it was taken ...
    assert await photos_of(http, api, api.surface, w.keys[0]) == {photo}
    counts = (await http.get(f"{path_for(api.project)}/counts")).json()
    assert counts["works"][str(w.keys[0])] == 1 and counts["work_surfaces"][str(api.surface)] == 1
    detail = (await http.get(f"{path_for(api.project)}/{(await http.get(path_for(api.project))).json()['items'][0]['asset']['id']}")).json()
    assert detail["attachments"][0]["price_item_id"] == str(w.a)
    # ... but no NEW photo can be attached to a work that is no longer in the plan.
    c = await up(api, surface=api.surface, key=w.keys[0])
    assert c.status == 409 and code(c) == "WORK_OCCURRENCE_NOT_CURRENT"


async def test_a_readded_item_is_a_new_occurrence_without_the_old_photos(api, http, w):
    photo = (await upload_ok(api, surface=api.surface, key=w.keys[0]))["attachment"]["id"]
    await resave(w, api, [Sel(price_item_id=w.a, occurrence_key=w.keys[1]), Sel(price_item_id=w.b, occurrence_key=w.keys[2])])
    readded = await resave(w, api, [
        Sel(price_item_id=w.a, occurrence_key=w.keys[1]), Sel(price_item_id=w.b, occurrence_key=w.keys[2]), Sel(price_item_id=w.a),
    ])
    new_key = readded.planned_works[-1].occurrence_key
    assert new_key not in w.keys
    assert await photos_of(http, api, api.surface, new_key) == set()  # matching is by key only: nothing is inherited
    assert await photos_of(http, api, api.surface, w.keys[0]) == {photo}  # the old evidence stays with the old key


async def test_detached_evidence_can_be_archived_and_restored(api, http, w):
    made = await upload_ok(api, surface=api.surface, key=w.keys[0])
    att = made["attachment"]["id"]
    await resave(w, api, [Sel(price_item_id=w.a, occurrence_key=w.keys[1]), Sel(price_item_id=w.b, occurrence_key=w.keys[2])])
    root = path_for(api.project).replace("/photos", "")
    assert (await http.post(f"{root}/photo-attachments/{att}/archive")).status_code == 200
    assert await photos_of(http, api, api.surface, w.keys[0]) == set()
    assert (await http.get(f"{path_for(api.project)}/counts")).json()["works"] == {}
    assert (await http.post(f"{root}/photo-attachments/{att}/restore")).status_code == 200  # evidence needs no current key
    assert await photos_of(http, api, api.surface, w.keys[0]) == {att}


# ---------------------------------------------------------------------------
# Other contexts are unchanged
# ---------------------------------------------------------------------------


async def test_the_four_site_contexts_still_work_as_before(api, http, w):
    surface_photo = await upload_ok(api, context="SURFACE", surface=api.surface, key=None)
    assert surface_photo["attachment"]["occurrence_key"] is None and surface_photo["attachment"]["price_item_id"] is None
    data = (await http.get(f"{path_for(api.project)}/counts")).json()
    assert data["surfaces"] == {str(api.surface): 1} and data["works"] == {} and data["work_surfaces"] == {}
