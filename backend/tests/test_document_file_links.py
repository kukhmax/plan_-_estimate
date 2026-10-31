"""Owner 2026-10-31: "Udostępnij / Pobierz PDF" in the application -- a five-minute signed link to the PDF, opened without the owner's token."""
import time
import uuid

import pytest
from httpx import AsyncClient

from app.domain.documents import file_links
from tests.test_stage15f2_api import draft_world, login, seed_estimate, use_issuer  # noqa: F401  (use_issuer is a fixture)
from tests.test_stage15f2_issuing import Delivery, issuer
from tests.test_clients import OTHER_USER

SECRET = "s" * 40


def test_a_ticket_is_signed_short_lived_and_cannot_be_changed():
    owner, project, target = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    token = file_links.make(file_links.DOCUMENT, owner, project, target, SECRET, now=1000)
    ticket = file_links.read(token, SECRET, now=1000 + file_links.TTL_SECONDS - 1)
    assert (ticket.kind, ticket.owner_id, ticket.project_id, ticket.target_id) == (file_links.DOCUMENT, owner, project, target)
    with pytest.raises(file_links.FileLinkError):
        file_links.read(token, SECRET, now=1000 + file_links.TTL_SECONDS + 1)  # expired
    with pytest.raises(file_links.FileLinkError):
        file_links.read(token, "x" * 40, now=1000)  # another secret
    body, signature = token.split(".")
    forged = file_links.make(file_links.DOCUMENT, uuid.uuid4(), project, target, "y" * 40, now=1000).split(".")[0]
    with pytest.raises(file_links.FileLinkError):
        file_links.read(f"{forged}.{signature}", SECRET, now=1000)  # another body under the old signature
    with pytest.raises(file_links.FileLinkError):
        file_links.read("garbage", SECRET)


async def test_an_issued_document_and_a_draft_estimate_are_opened_by_their_links(async_client: AsyncClient, db_session, use_issuer):
    _owner, project, estimate = await seed_estimate(db_session, telegram_id=__import__("tests.test_clients", fromlist=["x"]).VALID_USER["id"])
    project_id, estimate_id = str(project.id), str(estimate.id)
    run = use_issuer(issuer(delivery=Delivery()))
    headers = await login(async_client)
    row = (await async_client.post(f"/api/projects/{project_id}/documents", json={"kind": "ESTIMATE", "estimate_id": estimate_id}, headers=headers)).json()
    await run.drain()

    link = await async_client.post(f"/api/projects/{project_id}/documents/{row['id']}/file-link", headers=headers)
    assert link.status_code == 200, link.text
    assert link.json()["file_name"] == "KOSZ-2026-10-08-1953.pdf" and link.json()["url"].startswith("/api/public/files/")
    pdf = await async_client.get(link.json()["url"])  # no token: the link is the ticket
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF") and pdf.headers["content-type"] == "application/pdf"
    assert 'filename="KOSZ-2026-10-08-1953.pdf"' in pdf.headers["content-disposition"] and pdf.headers["cache-control"] == "no-store"
    assert (await async_client.get(link.json()["url"] + "x")).status_code == 404

    # a finished estimate has no working version; another owner gets nothing
    refused = await async_client.post(f"/api/projects/{project_id}/estimates/{estimate_id}/draft-file-link", headers=headers)
    assert refused.status_code == 422
    stranger = await login(async_client, OTHER_USER)
    assert (await async_client.post(f"/api/projects/{project_id}/documents/{row['id']}/file-link", headers=stranger)).status_code == 404
    assert (await async_client.post(f"/api/projects/{project_id}/documents/{row['id']}/file-link")).status_code == 401


async def test_a_draft_estimate_file(async_client: AsyncClient, db_session, use_issuer):
    project_id, estimate_id = await draft_world(db_session)
    use_issuer(issuer(delivery=Delivery()))
    headers = await login(async_client)
    link = await async_client.post(f"/api/projects/{project_id}/estimates/{estimate_id}/draft-file-link", headers=headers)
    assert link.status_code == 200 and link.json()["file_name"].startswith("Kosztorys-wersja-robocza-")
    pdf = await async_client.get(link.json()["url"])
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert time.time() > 0
