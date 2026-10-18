"""AC-6 -- the archived contracts and protocols on the archive page and their final deletion (HTTP over the real routes)."""
import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.core.database import get_db
from app.core.security import create_access_token
from app.domain.services.archived_document_service import KINDS
from app.main import app
from app.models.acceptance_protocol import AcceptanceProtocol
from app.models.concealed_works_protocol import ConcealedWorksProtocol
from app.models.contract import Contract
from app.models.decision_protocol import DecisionProtocol
from app.models.downtime_episode import DowntimeEpisode
from app.models.handover_protocol import HandoverProtocol
from app.models.issued_document import IssuedDocument
from app.models.project import Project
from tests.test_stage14c4_photos_api import _make_project, _make_user

NOW = datetime.now(UTC)


@pytest.fixture
async def world(db_session):
    me = await _make_user(db_session, 7601)
    other = await _make_user(db_session, 7602)
    project = await _make_project(db_session, me.id, name="Mieszkanie Kowalskich")
    project2 = await _make_project(db_session, me.id, name="Dom pod lasem")
    foreign = await _make_project(db_session, other.id, name="Obcy")

    async def override_db():
        yield db_session

    app.dependency_overrides[get_db] = override_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.headers["Authorization"] = f"Bearer {create_access_token(me.id)}"
        yield SimpleNamespace(
            db=db_session, http=client, me=me.id, other=other.id, project=project.id, project2=project2.id, foreign=foreign.id,
            other_token=create_access_token(other.id),
        )
    app.dependency_overrides.clear()


async def add(db, model, owner, project, *, status="ARCHIVED", ordinal=1, issued=False, **extra):
    """One record of any of the six kinds; an issued one carries what the database demands of an issued record."""
    fields = dict(owner_id=owner, project_id=project, status=status, **extra)
    if model is Contract:
        fields.update(version=ordinal, questionnaire_version=1, answers={})
    else:
        fields.update(sequence=ordinal)
    if issued:
        if model is DowntimeEpisode:
            fields.update(notice_issued_at=NOW, notice_number="PRZ/2026/1", notice_snapshot={}, notice_html="<p>x</p>")
            if status == "CLOSED":
                fields.update(protocol_issued_at=NOW, protocol_snapshot={}, protocol_html="<p>x</p>")
        else:
            fields.update(issued_at=NOW, snapshot={}, document_html="<p>x</p>")
    row = model(**fields)
    db.add(row)
    await db.commit()
    return row.id


MODELS = {
    "CONTRACT": Contract, "HANDOVER": HandoverProtocol, "CONCEALED": ConcealedWorksProtocol,
    "ACCEPTANCE": AcceptanceProtocol, "DECISION": DecisionProtocol, "DOWNTIME": DowntimeEpisode,
}


async def journal(db, owner, project, kind, source, number, seq=1):
    row = IssuedDocument(
        owner_id=owner, project_id=project, kind=kind, source_id=source, title="t", number=number, project_seq=seq,
        template_version="1", status="SENT", issued_at=NOW,
    )
    db.add(row)
    await db.commit()


async def left(db, model) -> int:
    return int((await db.execute(select(func.count()).select_from(model))).scalar_one())


def test_the_kinds_of_the_archive_are_the_six_records():
    assert set(KINDS) == set(MODELS)


# ------------------------------------------------------------------ the list

async def test_the_list_holds_all_six_kinds_with_the_object_and_the_number(world):
    ids = {}
    for kind, model in MODELS.items():
        ids[kind] = await add(world.db, model, world.me, world.project, ordinal=2, issued=(kind != "HANDOVER"))
    await journal(world.db, world.me, world.project, "CONTRACT", ids["CONTRACT"], "UM/2026/5")
    body = (await world.http.get("/api/archive/documents")).json()
    assert body["total"] == 6 and len(body["items"]) == 6
    by_kind = {item["kind"]: item for item in body["items"]}
    assert set(by_kind) == set(MODELS)
    assert all(item["project_name"] == "Mieszkanie Kowalskich" and item["ordinal"] == 2 for item in body["items"])
    assert by_kind["CONTRACT"]["number"] == "UM/2026/5" and by_kind["CONTRACT"]["issued_at"] is not None
    assert by_kind["DOWNTIME"]["number"] == "PRZ/2026/1"
    assert by_kind["HANDOVER"]["number"] is None and by_kind["HANDOVER"]["issued_at"] is None  # a draft that was archived
    assert all(item["archived_at"] for item in body["items"])


async def test_only_archived_records_of_objects_in_work_of_this_owner_are_listed(world):
    await add(world.db, Contract, world.me, world.project, status="DRAFT", ordinal=1)
    await add(world.db, Contract, world.me, world.project, status="ISSUED", ordinal=2, issued=True)
    await add(world.db, HandoverProtocol, world.other, world.foreign)
    hidden = await add(world.db, DecisionProtocol, world.me, world.project2)
    project = (await world.db.execute(select(Project).where(Project.id == world.project2))).scalar_one()
    project.is_archived = True
    await world.db.commit()
    assert hidden
    assert (await world.http.get("/api/archive/documents")).json() == {"items": [], "total": 0}


async def test_the_list_is_the_newest_first_and_cut_at_two_hundred_with_the_whole_total(world):
    for n in range(1, 204):
        await add(world.db, HandoverProtocol, world.me, world.project, ordinal=n)
    rows = (await world.db.execute(select(HandoverProtocol))).scalars().all()
    for i, row in enumerate(rows):
        row.updated_at = NOW - timedelta(minutes=i)
    await world.db.commit()
    body = (await world.http.get("/api/archive/documents")).json()
    assert len(body["items"]) == 200 and body["total"] == 203
    stamps = [item["archived_at"] for item in body["items"]]
    assert stamps == sorted(stamps, reverse=True)


async def test_the_routes_need_a_token(world):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as anonymous:
        some = uuid.uuid4()
        assert (await anonymous.get("/api/archive/documents")).status_code in (401, 403)
        assert (await anonymous.get(f"/api/archive/documents/CONTRACT/{some}/purge-preview")).status_code in (401, 403)
        assert (await anonymous.post(f"/api/archive/documents/CONTRACT/{some}/purge")).status_code in (401, 403)


# ------------------------------------------------------------------ preview and purge

@pytest.mark.parametrize("kind", list(MODELS))
async def test_an_archived_record_is_previewed_and_deleted_for_good(world, kind):
    model = MODELS[kind]
    keep = await add(world.db, model, world.me, world.project, ordinal=1)
    target = await add(world.db, model, world.me, world.project, ordinal=2, issued=True)
    preview = (await world.http.get(f"/api/archive/documents/{kind}/{target}/purge-preview")).json()
    assert preview["can_purge"] is True and preview["archived"] is True and preview["issued"] is True and preview["ordinal"] == 2
    assert (preview["journal_lines"], preview["dependents"]) == (0, 0)
    assert await left(world.db, model) == 2  # the preview deleted nothing
    done = await world.http.post(f"/api/archive/documents/{kind}/{target}/purge")
    assert done.status_code == 200 and done.json() == {"purged": True}
    remaining = (await world.db.execute(select(model.id))).scalars().all()
    assert remaining == [keep]


async def test_the_journal_lines_stay_and_are_counted_in_the_preview(world):
    target = await add(world.db, Contract, world.me, world.project, issued=True)
    await journal(world.db, world.me, world.project, "CONTRACT", target, "UM/2026/1")
    preview = (await world.http.get(f"/api/archive/documents/CONTRACT/{target}/purge-preview")).json()
    assert preview["journal_lines"] == 1
    assert (await world.http.post(f"/api/archive/documents/CONTRACT/{target}/purge")).status_code == 200
    assert await left(world.db, IssuedDocument) == 1


@pytest.mark.parametrize("kind", list(MODELS))
async def test_a_record_that_is_not_archived_is_refused(world, kind):
    target = await add(world.db, MODELS[kind], world.me, world.project, status="DRAFT")
    preview = (await world.http.get(f"/api/archive/documents/{kind}/{target}/purge-preview")).json()
    assert preview["archived"] is False and preview["can_purge"] is False
    refused = await world.http.post(f"/api/archive/documents/{kind}/{target}/purge")
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "DOCUMENT_RECORD_NOT_ARCHIVED"
    assert await left(world.db, MODELS[kind]) == 1


async def test_a_contract_with_protocols_that_are_not_archived_cannot_be_deleted(world):
    contract = await add(world.db, Contract, world.me, world.project, issued=True)
    await add(world.db, HandoverProtocol, world.me, world.project, status="DRAFT", contract_id=contract)
    await add(world.db, DowntimeEpisode, world.me, world.project, status="CLOSED", issued=True, contract_id=contract)
    await add(world.db, DecisionProtocol, world.me, world.project, status="ARCHIVED", contract_id=contract)  # does not hold it
    preview = (await world.http.get(f"/api/archive/documents/CONTRACT/{contract}/purge-preview")).json()
    assert preview["dependents"] == 2 and preview["can_purge"] is False
    refused = await world.http.post(f"/api/archive/documents/CONTRACT/{contract}/purge")
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "DOCUMENT_RECORD_IN_USE"
    assert await left(world.db, Contract) == 1


async def test_a_contract_goes_when_only_archived_protocols_refer_to_it(world):
    contract = await add(world.db, Contract, world.me, world.project, issued=True)
    protocol = await add(world.db, AcceptanceProtocol, world.me, world.project, contract_id=contract)
    assert (await world.http.post(f"/api/archive/documents/CONTRACT/{contract}/purge")).status_code == 200
    assert await left(world.db, Contract) == 0 and await left(world.db, AcceptanceProtocol) == 1
    assert protocol


async def test_a_record_of_another_owner_or_an_unknown_one_is_not_found(world):
    foreign = await add(world.db, Contract, world.other, world.foreign)
    for target in (foreign, uuid.uuid4()):
        for call in (world.http.get(f"/api/archive/documents/CONTRACT/{target}/purge-preview"), world.http.post(f"/api/archive/documents/CONTRACT/{target}/purge")):
            r = await call
            assert r.status_code == 404 and r.json()["detail"]["code"] == "DOCUMENT_RECORD_NOT_FOUND"
    assert await left(world.db, Contract) == 1
    wrong_kind = await world.http.get(f"/api/archive/documents/INVOICE/{foreign}/purge-preview")
    assert wrong_kind.status_code == 422


async def test_a_record_cannot_be_deleted_under_another_kind(world):
    contract = await add(world.db, Contract, world.me, world.project)
    r = await world.http.post(f"/api/archive/documents/HANDOVER/{contract}/purge")
    assert r.status_code == 404
    assert await left(world.db, Contract) == 1


async def test_the_cut_at_two_hundred_holds_across_the_kinds_and_the_total_is_whole(world):
    for n in range(1, 121):
        await add(world.db, HandoverProtocol, world.me, world.project, ordinal=n)
        await add(world.db, DecisionProtocol, world.me, world.project, ordinal=n)
    body = (await world.http.get("/api/archive/documents")).json()
    assert len(body["items"]) == 200 and body["total"] == 240


async def test_only_the_journal_lines_of_this_kind_of_record_are_counted(world):
    target = await add(world.db, Contract, world.me, world.project, issued=True)
    await journal(world.db, world.me, world.project, "CONTRACT", target, "UM/2026/1")
    await journal(world.db, world.me, world.project, "ESTIMATE", target, "KO/2026/1", seq=2)  # another document with the same source id
    preview = (await world.http.get(f"/api/archive/documents/CONTRACT/{target}/purge-preview")).json()
    assert preview["journal_lines"] == 1


async def test_a_draft_that_was_archived_is_previewed_as_never_issued(world):
    target = await add(world.db, HandoverProtocol, world.me, world.project)
    preview = (await world.http.get(f"/api/archive/documents/HANDOVER/{target}/purge-preview")).json()
    assert preview["issued"] is False and preview["can_purge"] is True
