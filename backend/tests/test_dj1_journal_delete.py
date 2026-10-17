"""Journal of the sent documents, DJ-1 -- deleting one row of the journal (HTTP over the real routes).

A row of the journal says that a document went to the chat under a number; no file is kept, so deleting a row removes only that line:
the document it recorded stays where it is. A row whose attempt is still running is not deleted.
"""
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.models.estimate import Estimate
from app.models.issued_document import IssuedDocument, IssuedDocumentKind, IssuedDocumentStatus
from tests.test_clients import OTHER_USER, VALID_USER
from tests.test_stage15e_photo_report import seed
from tests.test_stage15f2_api import login, use_issuer  # noqa: F401  (a fixture)
from tests.test_stage15f2_issuing import issuer

OWNER_TG = VALID_USER["id"]
NOW = datetime.now(UTC)


async def row(db, w, *, status="SENT", kind="PHOTO_REPORT", seq=1, number=None, issued_at=None, project=None, owner=None) -> IssuedDocument:
    document = IssuedDocument(
        owner_id=owner or w.owner.id, project_id=project or w.project.id, kind=kind, title="Dokument", number=number or f"DOC/{seq}-{uuid.uuid4().hex[:6]}",
        project_seq=seq, template_version="1", status=status, issued_at=issued_at or NOW, pages=1, byte_size=1000,
    )
    db.add(document)
    await db.commit()
    return document


async def count(db) -> int:
    return (await db.execute(select(func.count()).select_from(IssuedDocument))).scalar_one()


def url(w, document) -> str:
    return f"/api/projects/{w.project.id}/documents/{document.id}"


@pytest.mark.parametrize("status", ["SENT", "FAILED"])
async def test_a_sent_or_failed_row_is_deleted_and_the_others_stay(async_client: AsyncClient, db_session, use_issuer, status):  # noqa: F811
    w = await seed(db_session, telegram_id=OWNER_TG)
    use_issuer(issuer())
    headers = await login(async_client)
    gone = await row(db_session, w, status=status, seq=1)
    kept = await row(db_session, w, seq=2)
    response = await async_client.delete(url(w, gone), headers=headers)
    assert response.status_code == 204 and response.content == b""
    assert (await db_session.execute(select(IssuedDocument.id))).scalars().all() == [kept.id]
    listed = await async_client.get(f"/api/projects/{w.project.id}/documents", headers=headers)
    assert [d["id"] for d in listed.json()["items"]] == [str(kept.id)]
    everything = await async_client.get("/api/documents", headers=headers)
    assert [d["id"] for d in everything.json()["items"]] == [str(kept.id)] and everything.json()["total"] == 1
    assert (await async_client.get(url(w, gone), headers=headers)).status_code == 404  # it is gone
    assert (await async_client.delete(url(w, gone), headers=headers)).status_code == 404  # twice is not a success


async def test_every_kind_of_row_can_be_deleted(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await seed(db_session, telegram_id=OWNER_TG)
    use_issuer(issuer())
    headers = await login(async_client)
    rows = [await row(db_session, w, kind=kind.value, seq=index + 1) for index, kind in enumerate(IssuedDocumentKind)]
    for document in rows:
        assert (await async_client.delete(url(w, document), headers=headers)).status_code == 204, document.kind
    assert await count(db_session) == 0


async def test_a_running_attempt_is_not_deleted_and_says_so(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await seed(db_session, telegram_id=OWNER_TG)
    use_issuer(issuer())
    headers = await login(async_client)
    running = await row(db_session, w, status="PENDING", issued_at=datetime.now(UTC))
    response = await async_client.delete(url(w, running), headers=headers)
    assert response.status_code == 409 and response.json()["detail"]["code"] == "DOCUMENT_IN_PROGRESS"
    assert await count(db_session) == 1


async def test_an_attempt_left_pending_long_ago_has_ended_and_can_be_deleted(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await seed(db_session, telegram_id=OWNER_TG)
    use_issuer(issuer())
    headers = await login(async_client)
    stale = await row(db_session, w, status="PENDING", issued_at=datetime.now(UTC) - timedelta(hours=3))
    assert (await async_client.delete(url(w, stale), headers=headers)).status_code == 204
    assert await count(db_session) == 0


async def test_another_owner_another_object_or_nothing_is_a_404_and_nothing_is_deleted(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await seed(db_session, telegram_id=OWNER_TG)
    other = await seed(db_session, telegram_id=OTHER_USER["id"])
    use_issuer(issuer())
    mine = await row(db_session, w)
    theirs = await row(db_session, other)
    stranger = await login(async_client, OTHER_USER)
    assert (await async_client.delete(url(w, mine), headers=stranger)).status_code == 404  # my row, their token
    owner = await login(async_client)
    assert (await async_client.delete(f"/api/projects/{other.project.id}/documents/{theirs.id}", headers=owner)).status_code == 404  # their row, my token
    assert (await async_client.delete(f"/api/projects/{other.project.id}/documents/{mine.id}", headers=owner)).status_code == 404  # my row on the wrong object
    assert (await async_client.delete(f"/api/projects/{w.project.id}/documents/{uuid.uuid4()}", headers=owner)).status_code == 404
    assert await count(db_session) == 2


async def test_the_route_needs_a_token(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await seed(db_session, telegram_id=OWNER_TG)
    use_issuer(issuer())
    mine = await row(db_session, w)
    assert (await async_client.delete(url(w, mine))).status_code in (401, 403)
    assert await count(db_session) == 1


async def test_deleting_a_row_leaves_the_document_it_recorded_and_the_numbers_of_the_rest(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await seed(db_session, telegram_id=OWNER_TG)
    use_issuer(issuer())
    headers = await login(async_client)
    first = await row(db_session, w, seq=1, number="KOSZ/2026/10/18/1000")
    second = await row(db_session, w, seq=2, number="KOSZ/2026/10/18/1001")
    estimates_before = (await db_session.execute(select(func.count()).select_from(Estimate))).scalar_one()
    assert (await async_client.delete(url(w, first), headers=headers)).status_code == 204
    left = (await db_session.execute(select(IssuedDocument))).scalars().all()
    assert [(d.number, d.project_seq) for d in left] == [("KOSZ/2026/10/18/1001", 2)]  # the other row keeps its number and its running number
    assert (await db_session.execute(select(func.count()).select_from(Estimate))).scalar_one() == estimates_before
    assert second.id == left[0].id


async def test_a_row_of_an_archived_object_can_be_deleted_from_the_journal_of_all_objects(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await seed(db_session, telegram_id=OWNER_TG)
    use_issuer(issuer())
    headers = await login(async_client)
    document = await row(db_session, w)
    w.project.is_archived = True
    await db_session.commit()
    shown = await async_client.get("/api/documents", headers=headers)
    assert shown.json()["total"] == 1  # an archived object's documents stay in the journal
    assert (await async_client.delete(url(w, document), headers=headers)).status_code == 204
    assert (await async_client.get("/api/documents", headers=headers)).json()["total"] == 0


def test_the_status_words_are_the_ones_the_rule_knows():
    assert {s.value for s in IssuedDocumentStatus} == {"PENDING", "SENT", "FAILED"}
