"""Stage 16K.5 — the journal of issued documents of ALL objects of the owner: `GET /api/documents` (read only)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient

from app.domain.services.issued_document_service import PENDING_TTL
from app.models.issued_document import IssuedDocument
from app.models.project import Project
from tests.test_clients import OTHER_USER, VALID_USER, auth_header, get_token
from tests.test_stage15d_estimate_document import seed as seed_owner

OWNER_TG, STRANGER_TG = VALID_USER["id"], OTHER_USER["id"]


def now() -> datetime:
    # read when a test runs, not when the file is imported: a full run takes longer than the time a stale attempt waits
    return datetime.now(UTC)


READ_FIELDS = {"id", "project_id", "kind", "source_id", "source_version", "title", "number", "project_seq", "template_version",
               "status", "error_code", "scope", "pages", "byte_size", "issued_at", "sent_at", "project_name"}


def row(owner, project, seq, *, kind="ESTIMATE", status="SENT", issued_at=None, number=None):
    return IssuedDocument(
        owner_id=owner.id, project_id=project.id, kind=kind, title=f"Dokument {seq}", number=number or f"KOSZ/{project.id.hex[:6]}/{seq}",
        project_seq=seq, template_version="1", status=status, pages=2, byte_size=1000, issued_at=issued_at or now() - timedelta(hours=seq),
        sent_at=(issued_at or now()) if status == "SENT" else None,
    )


async def login(client: AsyncClient, user=VALID_USER) -> dict:
    return auth_header(await get_token(client, user))


async def test_it_needs_a_token(async_client: AsyncClient):
    assert (await async_client.get("/api/documents")).status_code == 401


async def test_it_lists_the_documents_of_every_object_newest_first_with_the_name_of_the_object(async_client: AsyncClient, db_session):
    owner, first, _ = await seed_owner(db_session, telegram_id=OWNER_TG)
    second = Project(owner_id=owner.id, name="Dom pod Krakowem", address="ul. Leśna 2", city="Kraków", postal_code="30-001")
    db_session.add(second)
    await db_session.flush()
    db_session.add_all([
        row(owner, first, 1, issued_at=now() - timedelta(hours=5)),
        row(owner, second, 1, kind="CONTRACT", issued_at=now() - timedelta(hours=1)),
        row(owner, first, 2, kind="PHOTO_REPORT", issued_at=now() - timedelta(hours=3)),
    ])
    await db_session.commit()
    body = (await async_client.get("/api/documents", headers=await login(async_client))).json()
    assert body["total"] == 3
    assert [(item["project_name"], item["kind"]) for item in body["items"]] == [
        ("Dom pod Krakowem", "CONTRACT"), ("Mokotów", "PHOTO_REPORT"), ("Mokotów", "ESTIMATE"),
    ]
    assert set(body["items"][0]) == READ_FIELDS  # the row of the journal of an object and the name of the object, nothing more


async def test_another_owners_documents_never_appear(async_client: AsyncClient, db_session):
    owner, mine, _ = await seed_owner(db_session, telegram_id=OWNER_TG)
    stranger, theirs, _ = await seed_owner(db_session, telegram_id=STRANGER_TG)
    db_session.add_all([row(owner, mine, 1), row(stranger, theirs, 1, number="KOSZ/OTHER/1"), row(stranger, theirs, 2, number="KOSZ/OTHER/2")])
    await db_session.commit()
    body = (await async_client.get("/api/documents", headers=await login(async_client))).json()
    assert body["total"] == 1
    assert [item["project_id"] for item in body["items"]] == [str(mine.id)]
    assert "KOSZ/OTHER" not in str(body)


async def test_the_documents_of_an_archived_object_stay_in_the_journal(async_client: AsyncClient, db_session):
    owner, project, _ = await seed_owner(db_session, telegram_id=OWNER_TG)
    db_session.add(row(owner, project, 1))
    project.is_archived = True
    await db_session.commit()
    body = (await async_client.get("/api/documents", headers=await login(async_client))).json()
    assert body["total"] == 1 and body["items"][0]["project_name"] == "Mokotów"


async def test_a_page_is_cut_by_limit_and_offset_and_the_total_counts_everything(async_client: AsyncClient, db_session):
    owner, project, _ = await seed_owner(db_session, telegram_id=OWNER_TG)
    db_session.add_all([row(owner, project, seq) for seq in range(1, 6)])  # seq 1 is the newest
    await db_session.commit()
    headers = await login(async_client)
    page = (await async_client.get("/api/documents?limit=2&offset=1", headers=headers)).json()
    assert page["total"] == 5
    assert [item["project_seq"] for item in page["items"]] == [2, 3]
    assert (await async_client.get("/api/documents?limit=2&offset=4", headers=headers)).json()["items"][0]["project_seq"] == 5
    assert (await async_client.get("/api/documents?offset=9", headers=headers)).json() == {"items": [], "total": 5}


@pytest.mark.parametrize("query", ["limit=0", "limit=201", "limit=x", "offset=-1"])
async def test_a_wrong_page_is_a_plain_422(async_client: AsyncClient, db_session, query):
    headers = await login(async_client)
    assert (await async_client.get(f"/api/documents?{query}", headers=headers)).status_code == 422


async def test_an_attempt_left_pending_ends_as_failed_like_in_the_journal_of_an_object(async_client: AsyncClient, db_session):
    owner, project, _ = await seed_owner(db_session, telegram_id=OWNER_TG)
    db_session.add_all([
        row(owner, project, 1, status="PENDING", issued_at=now() - PENDING_TTL - timedelta(minutes=5)),
        row(owner, project, 2, status="PENDING", issued_at=now() - timedelta(minutes=1)),
    ])
    await db_session.commit()
    items = (await async_client.get("/api/documents", headers=await login(async_client))).json()["items"]
    by_seq = {item["project_seq"]: item for item in items}
    assert by_seq[1]["status"] == "FAILED" and by_seq[1]["error_code"] == "INTERRUPTED"
    assert by_seq[2]["status"] == "PENDING"


async def test_it_is_read_only(async_client: AsyncClient, db_session):
    headers = await login(async_client)
    for method in ("POST", "PUT", "PATCH", "DELETE"):
        assert (await async_client.request(method, "/api/documents", headers=headers)).status_code == 405


async def test_the_route_does_not_swallow_the_documents_of_one_object(async_client: AsyncClient, db_session):
    owner, project, _ = await seed_owner(db_session, telegram_id=OWNER_TG)
    db_session.add(row(owner, project, 1))
    await db_session.commit()
    headers = await login(async_client)
    one = (await async_client.get(f"/api/projects/{project.id}/documents", headers=headers)).json()
    assert one["total"] == 1 and "project_name" not in one["items"][0]
    assert (await async_client.get(f"/api/projects/{uuid.uuid4()}/documents", headers=headers)).status_code == 404
