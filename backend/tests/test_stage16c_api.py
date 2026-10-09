"""Stage 16C — the technological card over HTTP: issue, preview, the fixed error envelopes and owner isolation."""
import uuid

from httpx import AsyncClient

from app.api.deps import get_document_issuer
from app.main import app
from tests.test_clients import OTHER_USER, VALID_USER
from tests.test_stage15e_photo_report import seed as seed_photos
from tests.test_stage15f2_api import login, use_issuer  # noqa: F401  (a fixture)
from tests.test_stage15f2_issuing import Delivery, issuer
from tests.test_stage16c_tech_card import plan, price_item

OWNER_TG, STRANGER_TG = VALID_USER["id"], OTHER_USER["id"]


async def prepared(db, telegram_id=OWNER_TG, *, quality=True):
    w = await seed_photos(db, telegram_id=telegram_id)
    item = await price_item(db, w.owner.id, "PREP_PROT", "pricebook.seed.prep_prot")
    from app.models.checklist import QualityLevel

    await plan(db, w.wall, [item], quality=QualityLevel.S2 if quality else None)
    return w


async def test_the_card_needs_a_token(async_client: AsyncClient, use_issuer):  # noqa: F811
    use_issuer(issuer())
    pid = uuid.uuid4()
    assert (await async_client.post(f"/api/projects/{pid}/documents", json={"kind": "TECH_CARD"})).status_code == 401
    assert (await async_client.post(f"/api/projects/{pid}/documents/tech-card/preview")).status_code == 401


async def test_the_card_takes_no_other_fields(async_client: AsyncClient, use_issuer):  # noqa: F811
    run = use_issuer(issuer())
    headers = await login(async_client)
    for body in ({"kind": "TECH_CARD", "estimate_id": str(uuid.uuid4())}, {"kind": "TECH_CARD", "room_ids": [str(uuid.uuid4())]},
                 {"kind": "TECH_CARD", "include_project_photos": True}, {"kind": "TECH_CARD", "owner_id": str(uuid.uuid4())}):
        assert (await async_client.post(f"/api/projects/{uuid.uuid4()}/documents", json=body, headers=headers)).status_code == 422
    assert run.active == 0


async def test_issuing_returns_202_then_the_journal_shows_the_card_sent(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await prepared(db_session)
    project_id = str(w.project.id)
    sender = Delivery()
    run = use_issuer(issuer(delivery=sender))
    headers = await login(async_client)
    response = await async_client.post(f"/api/projects/{project_id}/documents", json={"kind": "TECH_CARD"}, headers=headers)
    assert response.status_code == 202, response.text
    row = response.json()
    assert row["kind"] == "TECH_CARD" and row["status"] == "PENDING" and row["number"].startswith("KART/") and row["source_id"] is None
    await run.drain()
    shown = await async_client.get(f"/api/projects/{project_id}/documents/{row['id']}", headers=headers)
    assert shown.json()["status"] == "SENT" and len(sender.sent) == 1
    listed = await async_client.get(f"/api/projects/{project_id}/documents", headers=headers)
    assert [d["kind"] for d in listed.json()["items"]] == ["TECH_CARD"]


async def test_an_incomplete_card_is_a_422_with_the_list_and_takes_no_number(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await prepared(db_session, quality=False)
    project_id = str(w.project.id)
    run = use_issuer(issuer())
    headers = await login(async_client)
    response = await async_client.post(f"/api/projects/{project_id}/documents", json={"kind": "TECH_CARD"}, headers=headers)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "TECH_CARD_INCOMPLETE"
    assert detail["details"]["items"] == [{"room": "Salon", "surface": "Ściana A", "surface_type": "WALL", "missing": ["QUALITY_TARGET"]}]
    assert (await async_client.get(f"/api/projects/{project_id}/documents", headers=headers)).json()["total"] == 0 and run.active == 0


async def test_an_object_with_no_plans_is_a_422_empty(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await seed_photos(db_session, telegram_id=OWNER_TG)
    use_issuer(issuer())
    headers = await login(async_client)
    response = await async_client.post(f"/api/projects/{w.project.id}/documents", json={"kind": "TECH_CARD"}, headers=headers)
    assert (response.status_code, response.json()["detail"]["code"]) == (422, "TECH_CARD_EMPTY")


async def test_the_preview_is_a_200_that_sends_to_the_chat_and_leaves_no_row(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await seed_photos(db_session, telegram_id=OWNER_TG)  # nothing planned: the working version is still made
    project_id = str(w.project.id)
    sender = Delivery()
    use_issuer(issuer(delivery=sender))
    headers = await login(async_client)
    response = await async_client.post(f"/api/projects/{project_id}/documents/tech-card/preview", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sent"] is True and body["pages"] >= 1 and len(sender.sent) == 1
    assert (await async_client.get(f"/api/projects/{project_id}/documents", headers=headers)).json()["total"] == 0


async def test_a_stranger_gets_404_for_both_actions_and_nothing_is_sent(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await prepared(db_session, telegram_id=STRANGER_TG)
    project_id = str(w.project.id)
    sender = Delivery()
    run = use_issuer(issuer(delivery=sender))
    headers = await login(async_client)  # a different user from the owner of the project
    for response in (
        await async_client.post(f"/api/projects/{project_id}/documents", json={"kind": "TECH_CARD"}, headers=headers),
        await async_client.post(f"/api/projects/{project_id}/documents/tech-card/preview", headers=headers),
    ):
        assert response.status_code == 404 and response.json()["detail"]["code"] == "PROJECT_NOT_FOUND"
    assert sender.sent == [] and run.active == 0


def test_the_override_is_removed():
    assert get_document_issuer not in app.dependency_overrides
