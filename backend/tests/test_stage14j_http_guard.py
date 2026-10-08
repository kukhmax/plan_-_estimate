"""Stage 14J.3 — ownership / information-leak guard over every photo route, including the ones added after 14C.6B.

1. The set of photo operations of the running application equals the explicit list below: a new photo route cannot appear
   without its probe being written here.
2. Without a token every photo route answers 401; with a project of ANOTHER owner every project-scoped photo route answers
   the same 404 PROJECT_NOT_FOUND as for a project that does not exist.
3. Markers (14G), the counts (14E / 14F / 14H) and the evidence contexts INSPECTION / FINDING / WORK (14F / 14H): another
   owner's / another project's / pending / archived / invented ids give the fixed envelope, never an internal value, never
   another owner's marker text, and the SAME answer for an existing foreign id as for an invented one (nothing to enumerate).
"""

import uuid
from types import SimpleNamespace

import pytest

from app.main import app
from app.models.checklist import AnswerType, ChecklistQuestion, ChecklistTemplate, Substrate
from app.models.inspection import Inspection, InspectionFinding, InspectionStatus
from app.models.photo_annotation import PhotoAnnotation
from app.models.photo_asset import PhotoAsset, PhotoAssetStatus
from app.models.photo_attachment import PhotoAttachment, PhotoAttachmentContext, PhotoCategory
from tests import test_stage14c5_photos_api as c5
from tests.test_planned_work_coefficient_assignments import _make_surface
from tests.test_stage14b4_photo_asset import raw_asset

api, http = c5.api, c5.http

# Every photo operation of the application. A new route must be added here WITH a probe below.
PHOTO_OPERATIONS = {
    ("GET", "/api/photo-storage"),
    ("PATCH", "/api/projects/{project_id}/photo-attachments/{attachment_id}"),
    ("GET", "/api/projects/{project_id}/photo-attachments/{attachment_id}/annotations"),
    ("POST", "/api/projects/{project_id}/photo-attachments/{attachment_id}/annotations"),
    ("DELETE", "/api/projects/{project_id}/photo-attachments/{attachment_id}/annotations/{annotation_id}"),
    ("PATCH", "/api/projects/{project_id}/photo-attachments/{attachment_id}/annotations/{annotation_id}"),
    ("POST", "/api/projects/{project_id}/photo-attachments/{attachment_id}/archive"),
    ("POST", "/api/projects/{project_id}/photo-attachments/{attachment_id}/restore"),
    ("GET", "/api/projects/{project_id}/photos"),
    ("POST", "/api/projects/{project_id}/photos"),
    ("GET", "/api/projects/{project_id}/photo-report/summary"),  # Stage 15F: counts for the document screen
    ("GET", "/api/projects/{project_id}/photos/counts"),
    ("GET", "/api/projects/{project_id}/photos/{asset_id}"),
    ("POST", "/api/projects/{project_id}/photos/{asset_id}/archive"),
    ("POST", "/api/projects/{project_id}/photos/{asset_id}/attachments"),
    ("POST", "/api/projects/{project_id}/photos/{asset_id}/restore"),
}
# Project-scoped operations whose body is validated BEFORE the project (multipart upload): covered by the 14C.4 upload tests.
BODY_FIRST = {("POST", "/api/projects/{project_id}/photos")}
SECRET_LABEL = "TAJNE-OBCY-ZNACZNIK"


def live_operations() -> set[tuple[str, str]]:
    found = set()
    for path, operations in app.openapi()["paths"].items():
        if "photo" in path:
            found |= {(method.upper(), path) for method in operations}
    return found


def concrete(path: str, **ids) -> str:
    values = {"project_id": uuid.uuid4(), "attachment_id": uuid.uuid4(), "annotation_id": uuid.uuid4(),
              "asset_id": uuid.uuid4(), **ids}
    return path.format(**values)


def test_the_photo_routes_are_exactly_the_probed_ones():
    live = live_operations()
    assert live - PHOTO_OPERATIONS == set(), f"new photo route without a probe: {sorted(live - PHOTO_OPERATIONS)}"
    assert PHOTO_OPERATIONS - live == set(), f"probed route that no longer exists: {sorted(PHOTO_OPERATIONS - live)}"


async def test_no_token_means_401_on_every_photo_route(api):
    async with c5.AsyncClient(transport=c5.ASGITransport(app=c5.app), base_url="http://t") as anonymous:
        failures = []
        for method, path in sorted(PHOTO_OPERATIONS):
            response = await anonymous.request(method, concrete(path), json={} if method in ("POST", "PATCH") else None)
            if response.status_code != 401:
                failures.append(f"{method} {path}: {response.status_code}")
        assert failures == []


async def test_a_project_of_another_owner_looks_exactly_like_a_missing_project(api, http):
    failures = []
    for method, path in sorted(PHOTO_OPERATIONS - BODY_FIRST):
        if "{project_id}" not in path:
            continue
        body = {"context": "PROJECT"} if method == "POST" and path.endswith("/attachments") else (
            {"x": 0.5, "y": 0.5} if method == "POST" else (
                ({"label": "x"} if path.endswith("{annotation_id}") else {"caption": "x"}) if method == "PATCH" else None))
        foreign = await http.request(method, concrete(path, project_id=api.foreign_project), json=body)
        missing = await http.request(method, concrete(path), json=body)
        if (foreign.status_code, foreign.content) != (missing.status_code, missing.content) or foreign.status_code != 404:
            failures.append(f"{method} {path}: foreign {foreign.status_code} {foreign.text[:80]} / missing {missing.status_code}")
        elif foreign.json()["detail"]["code"] != "PROJECT_NOT_FOUND":
            failures.append(f"{method} {path}: code {foreign.json()['detail']['code']}")
    assert failures == []


# ---------------------------------------------------------------------------
# The world: own photo with a marker, a foreign photo with a marker, pending / archived, foreign evidence targets
# ---------------------------------------------------------------------------


@pytest.fixture
async def world(api, http):
    db = api.db
    own = await c5.upload(api)
    own2 = await c5.upload(api)
    other_project = await c5.upload(api, context="PROJECT", project=api.project2, target=("caption", ""))
    foreign = await c5.upload(api, context="PROJECT", project=api.foreign_project, token=api.other_token, target=("caption", ""))
    marker = await http.post(f"/api/projects/{api.project}/photo-attachments/{own['attachment']['id']}/annotations",
                             json={"x": 0.3, "y": 0.4, "label": "moj"})
    assert marker.status_code == 201, marker.text
    marker2 = await http.post(f"/api/projects/{api.project}/photo-attachments/{own2['attachment']['id']}/annotations",
                              json={"x": 0.6, "y": 0.6})
    assert marker2.status_code == 201, marker2.text
    foreign_marker = PhotoAnnotation(attachment_id=uuid.UUID(foreign["attachment"]["id"]), x=0.5, y=0.5, position=0,
                                     label=SECRET_LABEL)
    pending_asset = raw_asset(SimpleNamespace(id=api.me), SimpleNamespace(id=api.project), status=PhotoAssetStatus.PENDING)
    db.add_all([foreign_marker, pending_asset])
    await db.flush()
    foreign_marker_id = str(foreign_marker.id)  # ids are read at once: later requests roll the shared session back
    pending_att = PhotoAttachment(asset_id=pending_asset.id, project_id=api.project, context=PhotoAttachmentContext.PROJECT,
                                  category=PhotoCategory.GENERAL)
    db.add(pending_att)
    await db.commit()
    pending_att_id = str(pending_att.id)
    # archived own photo (attachment archived)
    archived = await c5.upload(api)
    archive = await http.post(f"/api/projects/{api.project}/photo-attachments/{archived['attachment']['id']}/archive")
    assert archive.status_code == 200, archive.text
    # foreign evidence targets: a surface, an inspection of the foreign room and one of its findings
    foreign_surface_id = str((await _make_surface(db, api.foreign_room, name="Obca ściana")).id)
    template = ChecklistTemplate(code=f"G14J_{uuid.uuid4().hex[:8]}", version=1, substrate=Substrate.CONCRETE, title_key="t")
    db.add(template)
    await db.flush()
    question = ChecklistQuestion(template_id=template.id, position=1, key="q", text_key="q", answer_type=AnswerType.BOOLEAN)
    inspection = Inspection(room_id=api.foreign_room, template_id=template.id, substrate=Substrate.CONCRETE,
                            status=InspectionStatus.COMPLETED)
    db.add_all([question, inspection])
    await db.flush()
    finding = InspectionFinding(inspection_id=inspection.id, finding_key="CRACK", lineage_id=uuid.uuid4(), is_active=True,
                                position=1)
    db.add(finding)
    await db.commit()
    ids = SimpleNamespace(question=str(question.id), inspection=str(inspection.id), finding=str(finding.id))
    return SimpleNamespace(
        own=own, own2=own2, other_project=other_project, foreign=foreign, archived=archived,
        marker=marker.json()["id"], marker2=marker2.json()["id"], foreign_marker=foreign_marker_id,
        pending=pending_att_id, foreign_surface=foreign_surface_id, foreign_inspection=ids.inspection,
        foreign_finding=ids.finding, question=ids.question,
    )


def secrets_of(db_rows) -> list[str]:
    found = [SECRET_LABEL]
    for asset in db_rows:
        found += [asset.sha256, asset.storage_key_original, asset.storage_key_display, asset.storage_key_thumbnail]
    return found


def marker_rows(a, w) -> list[tuple[str, str, str, dict | None, int, str | None]]:
    p, p2, fp = a.project, a.project2, a.foreign_project
    own_att, own2_att = w.own["attachment"]["id"], w.own2["attachment"]["id"]
    foreign_att, other_att = w.foreign["attachment"]["id"], w.other_project["attachment"]["id"]
    arch_att = w.archived["attachment"]["id"]
    rnd = str(uuid.uuid4())
    base = "photo-attachments"
    return [
        # (label, method, url, json body, status, code)
        ("markers of a foreign project", "GET", f"/api/projects/{fp}/{base}/{foreign_att}/annotations", None, 404, "PROJECT_NOT_FOUND"),
        ("create in a foreign project", "POST", f"/api/projects/{fp}/{base}/{foreign_att}/annotations", {"x": 0.1, "y": 0.1}, 404,
         "PROJECT_NOT_FOUND"),
        ("foreign attachment (list)", "GET", f"/api/projects/{p}/{base}/{foreign_att}/annotations", None, 404, "PHOTO_ATTACHMENT_NOT_FOUND"),
        ("foreign attachment (create)", "POST", f"/api/projects/{p}/{base}/{foreign_att}/annotations", {"x": 0.1, "y": 0.1}, 404,
         "PHOTO_ATTACHMENT_NOT_FOUND"),
        ("foreign marker (patch)", "PATCH", f"/api/projects/{p}/{base}/{foreign_att}/annotations/{w.foreign_marker}", {"label": "x"},
         404, "PHOTO_ATTACHMENT_NOT_FOUND"),
        ("foreign marker (delete)", "DELETE", f"/api/projects/{p}/{base}/{foreign_att}/annotations/{w.foreign_marker}", None, 404,
         "PHOTO_ATTACHMENT_NOT_FOUND"),
        ("foreign marker under my attachment (patch)", "PATCH", f"/api/projects/{p}/{base}/{own_att}/annotations/{w.foreign_marker}",
         {"label": "x"}, 404, "PHOTO_ANNOTATION_NOT_FOUND"),
        ("foreign marker under my attachment (delete)", "DELETE", f"/api/projects/{p}/{base}/{own_att}/annotations/{w.foreign_marker}",
         None, 404, "PHOTO_ANNOTATION_NOT_FOUND"),
        ("my marker under my OTHER attachment (patch)", "PATCH", f"/api/projects/{p}/{base}/{own2_att}/annotations/{w.marker}",
         {"label": "x"}, 404, "PHOTO_ANNOTATION_NOT_FOUND"),
        ("my marker under my OTHER attachment (delete)", "DELETE", f"/api/projects/{p}/{base}/{own2_att}/annotations/{w.marker}",
         None, 404, "PHOTO_ANNOTATION_NOT_FOUND"),
        ("random marker", "DELETE", f"/api/projects/{p}/{base}/{own_att}/annotations/{rnd}", None, 404, "PHOTO_ANNOTATION_NOT_FOUND"),
        ("random attachment", "GET", f"/api/projects/{p}/{base}/{rnd}/annotations", None, 404, "PHOTO_ATTACHMENT_NOT_FOUND"),
        ("my attachment of the other project", "GET", f"/api/projects/{p}/{base}/{other_att}/annotations", None, 404,
         "PHOTO_ATTACHMENT_NOT_FOUND"),
        ("my attachment, wrong project (create)", "POST", f"/api/projects/{p2}/{base}/{own_att}/annotations", {"x": 0.1, "y": 0.1},
         404, "PHOTO_ATTACHMENT_NOT_FOUND"),
        ("pending attachment (list)", "GET", f"/api/projects/{p}/{base}/{w.pending}/annotations", None, 404, "PHOTO_ATTACHMENT_NOT_FOUND"),
        ("pending attachment (create)", "POST", f"/api/projects/{p}/{base}/{w.pending}/annotations", {"x": 0.1, "y": 0.1}, 404,
         "PHOTO_ATTACHMENT_NOT_FOUND"),
        ("archived attachment (create)", "POST", f"/api/projects/{p}/{base}/{arch_att}/annotations", {"x": 0.1, "y": 0.1}, 409,
         "PHOTO_ANNOTATION_READ_ONLY"),
        ("malformed marker uuid", "DELETE", f"/api/projects/{p}/{base}/{own_att}/annotations/not-a-uuid", None, 422, None),
        ("malformed attachment uuid", "GET", f"/api/projects/{p}/{base}/not-a-uuid/annotations", None, 422, None),
        ("a marker moved by the client", "PATCH", f"/api/projects/{p}/{base}/{own_att}/annotations/{w.marker}", {"x": 0.9}, 422, None),
        ("a coordinate out of range", "POST", f"/api/projects/{p}/{base}/{own_att}/annotations", {"x": 1.5, "y": 0.1}, 422,
         "PHOTO_ANNOTATION_INVALID"),
        # evidence contexts: another owner's inspection / finding / surface
        ("foreign inspection (list)", "GET", f"/api/projects/{p}/photos?context=INSPECTION&inspection_id={w.foreign_inspection}", None,
         404, None),
        ("foreign inspection question (list)", "GET",
         f"/api/projects/{p}/photos?context=INSPECTION&inspection_id={w.foreign_inspection}&question_id={w.question}", None, 404, None),
        ("foreign finding (list)", "GET", f"/api/projects/{p}/photos?context=FINDING&finding_id={w.foreign_finding}", None, 404, None),
        ("foreign surface (WORK list)", "GET",
         f"/api/projects/{p}/photos?context=WORK&surface_id={w.foreign_surface}", None, 404, None),
        ("foreign inspection (attach)", "POST", f"/api/projects/{p}/photos/{w.own['asset']['id']}/attachments",
         {"context": "INSPECTION", "inspection_id": w.foreign_inspection}, 404, None),
        ("foreign finding (attach)", "POST", f"/api/projects/{p}/photos/{w.own['asset']['id']}/attachments",
         {"context": "FINDING", "finding_id": w.foreign_finding}, 404, None),
        ("foreign surface (WORK attach)", "POST", f"/api/projects/{p}/photos/{w.own['asset']['id']}/attachments",
         {"context": "WORK", "surface_id": w.foreign_surface, "occurrence_key": str(uuid.uuid4())}, 404, None),
        ("foreign lineage (list)", "GET", f"/api/projects/{p}/photos?lineage={uuid.uuid4()}", None, 404, None),
    ]


async def test_markers_counts_and_evidence_contexts_leak_nothing(api, http, world):
    db_assets = list((await api.db.execute(PhotoAsset.__table__.select())).all())
    secrets = secrets_of(db_assets)
    failures = []
    for label, method, url, body, status, code in marker_rows(api, world):
        response = await http.request(method, url, json=body)
        if response.status_code != status:
            failures.append(f"{label}: {response.status_code} != {status} ({response.text[:140]})")
            continue
        detail = response.json().get("detail")
        if code is not None and (not isinstance(detail, dict) or detail.get("code") != code):
            failures.append(f"{label}: detail {detail}")
        if any(secret in response.text for secret in secrets) or "Traceback" in response.text or "botocore" in response.text:
            failures.append(f"{label}: leaked an internal value or another owner's marker")
    assert failures == []


async def test_a_foreign_id_is_indistinguishable_from_an_invented_one(api, http, world):
    p = api.project
    own_att = world.own["attachment"]["id"]
    pairs = [
        ("marker list", "GET", f"/api/projects/{p}/photo-attachments/{{}}/annotations", None, world.foreign["attachment"]["id"]),
        ("marker create", "POST", f"/api/projects/{p}/photo-attachments/{{}}/annotations", {"x": 0.2, "y": 0.2},
         world.foreign["attachment"]["id"]),
        ("marker patch", "PATCH", f"/api/projects/{p}/photo-attachments/{own_att}/annotations/{{}}", {"label": "x"}, world.foreign_marker),
        ("marker delete", "DELETE", f"/api/projects/{p}/photo-attachments/{own_att}/annotations/{{}}", None, world.foreign_marker),
        ("inspection list", "GET", f"/api/projects/{p}/photos?context=INSPECTION&inspection_id={{}}", None, world.foreign_inspection),
        ("finding list", "GET", f"/api/projects/{p}/photos?context=FINDING&finding_id={{}}", None, world.foreign_finding),
        ("work list", "GET", f"/api/projects/{p}/photos?context=WORK&surface_id={{}}", None, world.foreign_surface),
    ]
    for label, method, template, body, foreign_id in pairs:
        existing = await http.request(method, template.format(foreign_id), json=body)
        invented = await http.request(method, template.format(uuid.uuid4()), json=body)
        assert (existing.status_code, existing.content) == (invented.status_code, invented.content), label


async def test_counts_belong_to_the_project_and_the_owner_only(api, http, world):
    own = await http.get(f"/api/projects/{api.project}/photos/counts")
    assert own.status_code == 200
    data = own.json()
    other_project = await http.get(f"/api/projects/{api.project2}/photos/counts")
    assert other_project.status_code == 200
    # this project's counts hold only this project's photos: the other project's PROJECT photo is not in `project`
    assert data["project"] == 0 and other_project.json()["project"] == 1
    foreign = await http.get(f"/api/projects/{api.foreign_project}/photos/counts")
    assert foreign.status_code == 404 and foreign.json()["detail"]["code"] == "PROJECT_NOT_FOUND"
    for text in (own.text, other_project.text, foreign.text):
        assert SECRET_LABEL not in text and world.foreign["attachment"]["id"] not in text
    # two active ROOM photos (the archived one and the pending one are not counted); markers change no count
    assert sum(data["rooms"].values()) == 2 and data["project"] == 0
