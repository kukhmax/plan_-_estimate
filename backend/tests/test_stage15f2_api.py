"""Stage 15F.2 — the documents HTTP API: tokens, the fixed error envelopes, owner isolation, what a response may show."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.api.deps import get_document_issuer
from app.domain.exceptions import (
    DocumentChatUnavailableError,
    DocumentDeliveryDisabledError,
    DocumentDeliveryRejectedError,
    DocumentDeliveryUnavailableError,
    DocumentRenderBusyError,
    DocumentRenderTimeoutError,
    DocumentTooLargeError,
)
from app.main import app
from app.models.estimate import Estimate, EstimateStatus
from tests.test_clients import OTHER_USER, VALID_USER, auth_header, get_token
from tests.test_stage15d_estimate_document import seed as seed_estimate
from tests.test_stage15e_photo_report import seed as seed_photos
from tests.test_stage15f2_issuing import Delivery, StubRenderer, issuer

OWNER_TG, STRANGER_TG = VALID_USER["id"], OTHER_USER["id"]
READ_FIELDS = {"id", "project_id", "kind", "source_id", "source_version", "title", "number", "project_seq", "template_version",
               "status", "error_code", "scope", "pages", "byte_size", "issued_at", "sent_at"}


@pytest.fixture
def use_issuer():
    def install(run):
        app.dependency_overrides[get_document_issuer] = lambda: run
        return run

    yield install
    app.dependency_overrides.pop(get_document_issuer, None)


async def login(client: AsyncClient, user=VALID_USER) -> dict:
    return auth_header(await get_token(client, user))


# --- tokens and shapes --------------------------------------------------------------------------------------------------------


async def test_every_route_needs_a_token(async_client: AsyncClient, use_issuer):
    use_issuer(issuer())
    pid, eid, did = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    calls = [
        ("POST", f"/api/projects/{pid}/documents", {"kind": "PHOTO_REPORT"}),
        ("GET", f"/api/projects/{pid}/documents", None),
        ("GET", f"/api/projects/{pid}/documents/{did}", None),
        ("GET", f"/api/projects/{pid}/photo-report/summary", None),
        ("POST", f"/api/projects/{pid}/estimates/{eid}/preview-pdf", None),
    ]
    for method, path, body in calls:
        response = await async_client.request(method, path, json=body)
        assert response.status_code == 401, (method, path)


@pytest.mark.parametrize(
    "body",
    [{}, {"kind": "CONTRACT"}, {"kind": "ESTIMATE"}, {"kind": "ESTIMATE", "estimate_id": "not-a-uuid"},
     {"kind": "ESTIMATE", "estimate_id": str(uuid.uuid4()), "room_ids": [str(uuid.uuid4())]},
     {"kind": "ESTIMATE", "estimate_id": str(uuid.uuid4()), "include_project_photos": True},
     {"kind": "PHOTO_REPORT", "estimate_id": str(uuid.uuid4())}, {"kind": "PHOTO_REPORT", "room_ids": []},
     {"kind": "PHOTO_REPORT", "include_project_photos": True}, {"kind": "PHOTO_REPORT", "owner_id": str(uuid.uuid4())},
     {"kind": "PHOTO_REPORT", "room_ids": ["x"]}],
)
async def test_a_malformed_request_is_a_plain_422_and_starts_nothing(async_client: AsyncClient, use_issuer, body):
    run = use_issuer(issuer())
    headers = await login(async_client)
    assert (await async_client.post(f"/api/projects/{uuid.uuid4()}/documents", json=body, headers=headers)).status_code == 422
    assert run.active == 0


# --- an estimate ------------------------------------------------------------------------------------------------------------------


async def test_issuing_returns_202_with_the_pending_row_then_the_journal_shows_it_sent(async_client: AsyncClient, db_session, use_issuer):
    _owner, project, estimate = await seed_estimate(db_session, telegram_id=OWNER_TG)
    project_id, estimate_id = str(project.id), str(estimate.id)
    sender = Delivery()
    run = use_issuer(issuer(delivery=sender))
    headers = await login(async_client)
    response = await async_client.post(f"/api/projects/{project_id}/documents", json={"kind": "ESTIMATE", "estimate_id": estimate_id}, headers=headers)
    assert response.status_code == 202, response.text
    row = response.json()
    assert set(row) == READ_FIELDS
    assert (row["status"], row["kind"], row["number"], row["project_seq"], row["source_id"]) == (
        "PENDING", "ESTIMATE", "KOSZ/2026/10/08/1953", 1, estimate_id)
    assert row["pages"] is None and row["sent_at"] is None and row["error_code"] is None
    await run.drain()
    one = await async_client.get(f"/api/projects/{project_id}/documents/{row['id']}", headers=headers)
    assert one.status_code == 200 and one.json()["status"] == "SENT" and one.json()["pages"] == 1 and one.json()["byte_size"] > 0
    listed = await async_client.get(f"/api/projects/{project_id}/documents", headers=headers)
    assert listed.json()["total"] == 1 and listed.json()["items"][0]["id"] == row["id"] and len(sender.sent) == 1


async def test_a_second_tap_returns_the_same_row(async_client: AsyncClient, db_session, use_issuer):
    _owner, project, estimate = await seed_estimate(db_session, telegram_id=OWNER_TG)
    project_id, estimate_id = str(project.id), str(estimate.id)
    run = use_issuer(issuer())
    headers = await login(async_client)
    body = {"kind": "ESTIMATE", "estimate_id": estimate_id}
    first = await async_client.post(f"/api/projects/{project_id}/documents", json=body, headers=headers)
    second = await async_client.post(f"/api/projects/{project_id}/documents", json=body, headers=headers)
    assert first.status_code == second.status_code == 202 and first.json()["id"] == second.json()["id"]
    await run.drain()


async def test_what_is_wrong_is_answered_at_once_in_the_fixed_envelope(async_client: AsyncClient, db_session, use_issuer):
    _owner, project, estimate = await seed_estimate(db_session, telegram_id=OWNER_TG)
    project_id, estimate_id = str(project.id), estimate.id
    run = use_issuer(issuer())
    headers = await login(async_client)
    est = (await db_session.execute(select(Estimate).where(Estimate.id == estimate_id))).scalar_one()
    est.status = EstimateStatus.DRAFT
    await db_session.commit()
    draft = await async_client.post(f"/api/projects/{project_id}/documents", json={"kind": "ESTIMATE", "estimate_id": str(estimate_id)}, headers=headers)
    assert draft.status_code == 422 and draft.json()["detail"]["code"] == "ESTIMATE_NOT_FINAL"
    assert set(draft.json()["detail"]) == {"code", "message", "details"}
    missing = await async_client.post(f"/api/projects/{project_id}/documents", json={"kind": "ESTIMATE", "estimate_id": str(uuid.uuid4())}, headers=headers)
    assert missing.status_code == 404 and missing.json()["detail"]["code"] == "ESTIMATE_NOT_FOUND"
    unknown = await async_client.post(f"/api/projects/{uuid.uuid4()}/documents", json={"kind": "PHOTO_REPORT"}, headers=headers)
    assert unknown.status_code == 404 and unknown.json()["detail"]["code"] == "PROJECT_NOT_FOUND"
    assert run.active == 0
    listed = await async_client.get(f"/api/projects/{project_id}/documents", headers=headers)
    assert listed.json() == {"items": [], "total": 0}


async def test_another_owner_sees_nothing_and_cannot_issue_for_a_foreign_project(async_client: AsyncClient, db_session, use_issuer):
    _owner, project, estimate = await seed_estimate(db_session, telegram_id=OWNER_TG)
    _stranger, stranger_project, _ = await seed_estimate(db_session, telegram_id=STRANGER_TG)
    project_id, estimate_id, stranger_project_id = str(project.id), str(estimate.id), str(stranger_project.id)
    run = use_issuer(issuer())
    mine, theirs = await login(async_client), await login(async_client, OTHER_USER)
    issued = await async_client.post(f"/api/projects/{project_id}/documents", json={"kind": "ESTIMATE", "estimate_id": estimate_id}, headers=mine)
    document_id = issued.json()["id"]
    await run.drain()
    foreign_try = await async_client.post(f"/api/projects/{project_id}/documents", json={"kind": "ESTIMATE", "estimate_id": estimate_id}, headers=theirs)
    missing_try = await async_client.post(f"/api/projects/{uuid.uuid4()}/documents", json={"kind": "ESTIMATE", "estimate_id": estimate_id}, headers=theirs)
    assert foreign_try.status_code == missing_try.status_code == 404 and foreign_try.json() == missing_try.json()
    assert (await async_client.get(f"/api/projects/{project_id}/documents", headers=theirs)).status_code == 404
    assert (await async_client.get(f"/api/projects/{project_id}/documents/{document_id}", headers=theirs)).status_code == 404
    assert (await async_client.get(f"/api/projects/{stranger_project_id}/documents/{document_id}", headers=theirs)).status_code == 404
    assert (await async_client.get(f"/api/projects/{project_id}/photo-report/summary", headers=theirs)).status_code == 404
    assert (await async_client.post(f"/api/projects/{project_id}/estimates/{estimate_id}/preview-pdf", headers=theirs)).status_code == 404
    assert (await async_client.get(f"/api/projects/{stranger_project_id}/documents", headers=theirs)).json()["total"] == 0


async def test_a_full_queue_is_429_with_a_retry_hint(async_client: AsyncClient, db_session, use_issuer):
    _owner, project, estimate = await seed_estimate(db_session, telegram_id=OWNER_TG)
    project_id, estimate_id = str(project.id), str(estimate.id)
    run = use_issuer(issuer(max_active=1))
    headers = await login(async_client)
    body = {"kind": "ESTIMATE", "estimate_id": estimate_id}
    assert (await async_client.post(f"/api/projects/{project_id}/documents", json=body, headers=headers)).status_code == 202
    full = await async_client.post(f"/api/projects/{project_id}/documents", json=body, headers=headers)
    assert full.status_code == 429 and full.json()["detail"]["code"] == "DOCUMENT_QUEUE_FULL" and full.headers["retry-after"] == "10"
    await run.drain()


# --- the photo report ---------------------------------------------------------------------------------------------------------------


async def test_the_summary_and_the_limit_and_a_part_by_room(async_client: AsyncClient, db_session, use_issuer):
    w = await seed_photos(db_session, telegram_id=OWNER_TG)
    project_id, salon_id, kuchnia_id = str(w.project.id), str(w.salon.id), str(w.kuchnia.id)
    run = use_issuer(issuer(w.storage, max_photos=3))
    headers = await login(async_client)
    summary = await async_client.get(f"/api/projects/{project_id}/photo-report/summary", headers=headers)
    body = summary.json()
    assert summary.status_code == 200 and (body["photo_count"], body["project_photos"], body["limit"], body["over_limit"], body["has_content"]) == (5, 1, 3, True, True)
    assert [(r["room_id"], r["name"], r["photos"]) for r in body["rooms"]] == [(salon_id, "Salon", 3), (kuchnia_id, "Kuchnia", 1)]
    assert set(body["rooms"][0]) == {"room_id", "name", "photos", "has_inspection_content"}
    assert (body["recommended_count"], body["unpriced_works"]) == (0, [])
    over = await async_client.post(f"/api/projects/{project_id}/documents", json={"kind": "PHOTO_REPORT"}, headers=headers)
    assert over.status_code == 422 and over.json()["detail"]["code"] == "PHOTO_LIMIT_EXCEEDED"
    details = over.json()["detail"]["details"]
    assert (details["count"], details["limit"], details["project_photos"]) == (5, 3, 1)
    assert [(r["name"], r["count"]) for r in details["rooms"]] == [("Salon", 3), ("Kuchnia", 1)]
    part = await async_client.post(f"/api/projects/{project_id}/documents", json={"kind": "PHOTO_REPORT", "room_ids": [salon_id]}, headers=headers)
    assert part.status_code == 202 and part.json()["scope"] == {"room_ids": [salon_id], "include_project_photos": False}
    assert part.json()["title"] == "Raport fotograficzny (część: Salon)"
    await run.drain()


async def test_a_photo_report_without_the_profile_is_422(async_client: AsyncClient, db_session, use_issuer):
    w = await seed_photos(db_session, telegram_id=OWNER_TG, with_profile=False)
    project_id = str(w.project.id)
    use_issuer(issuer(w.storage))
    response = await async_client.post(f"/api/projects/{project_id}/documents", json={"kind": "PHOTO_REPORT"}, headers=await login(async_client))
    assert response.status_code == 422 and response.json()["detail"]["code"] == "EXECUTOR_PROFILE_REQUIRED"


# --- the preview --------------------------------------------------------------------------------------------------------------------


async def draft_world(db):
    _owner, project, estimate = await seed_estimate(db, telegram_id=OWNER_TG)
    project_id, estimate_id = str(project.id), estimate.id
    est = (await db.execute(select(Estimate).where(Estimate.id == estimate_id))).scalar_one()
    est.status = EstimateStatus.DRAFT
    await db.commit()
    return project_id, str(estimate_id)


async def test_a_draft_is_previewed_and_the_answer_says_so(async_client: AsyncClient, db_session, use_issuer):
    project_id, estimate_id = await draft_world(db_session)
    sender = Delivery()
    use_issuer(issuer(delivery=sender))
    response = await async_client.post(f"/api/projects/{project_id}/estimates/{estimate_id}/preview-pdf", headers=await login(async_client))
    assert response.status_code == 200 and response.json()["sent"] is True and response.json()["pages"] == 1
    assert len(sender.sent) == 1 and (await async_client.get(f"/api/projects/{project_id}/documents", headers=await login(async_client))).json()["total"] == 0


async def test_a_finished_estimate_is_not_previewed(async_client: AsyncClient, db_session, use_issuer):
    _owner, project, estimate = await seed_estimate(db_session, telegram_id=OWNER_TG)
    project_id, estimate_id = str(project.id), str(estimate.id)
    use_issuer(issuer())
    response = await async_client.post(f"/api/projects/{project_id}/estimates/{estimate_id}/preview-pdf", headers=await login(async_client))
    assert response.status_code == 422 and response.json()["detail"]["code"] == "PREVIEW_ONLY_FOR_DRAFT"


@pytest.mark.parametrize(
    ("renderer_error", "delivery_error", "http_status", "code"),
    [
        (None, DocumentChatUnavailableError("x"), 409, "TELEGRAM_CHAT_UNAVAILABLE"),
        (None, DocumentDeliveryUnavailableError("x"), 502, "TELEGRAM_UNAVAILABLE"),
        (None, DocumentDeliveryRejectedError("x"), 502, "TELEGRAM_REJECTED"),
        (None, DocumentDeliveryDisabledError("x"), 503, "DELIVERY_DISABLED"),
        (DocumentRenderBusyError("x"), None, 503, "DOCUMENT_RENDER_BUSY"),
        (DocumentRenderTimeoutError("x"), None, 504, "DOCUMENT_RENDER_TIMEOUT"),
        (DocumentTooLargeError("x"), None, 422, "DOCUMENT_TOO_LARGE"),
    ],
)
async def test_a_failing_preview_has_a_status_and_a_code_for_each_cause(async_client: AsyncClient, db_session, use_issuer, renderer_error, delivery_error, http_status, code):
    project_id, estimate_id = await draft_world(db_session)
    use_issuer(issuer(renderer=StubRenderer(renderer_error), delivery=Delivery(delivery_error)))
    response = await async_client.post(f"/api/projects/{project_id}/estimates/{estimate_id}/preview-pdf", headers=await login(async_client))
    assert response.status_code == http_status and response.json()["detail"]["code"] == code
    assert ("retry-after" in response.headers) == (http_status == 503)
