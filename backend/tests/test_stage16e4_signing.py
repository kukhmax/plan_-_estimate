"""Stage 16E.4: an issued contract is signed on paper -> SIGNED, its estimate -> ACCEPTED; closing; the database rules."""
import uuid
from datetime import UTC, date, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.exc import IntegrityError

from app.domain.exceptions import ContractNotEditableError, ContractSignError, ProjectNotFoundError
from app.domain.services.contract_service import ContractService, contract_read
from app.models.contract import Contract, ContractStatus
from app.models.estimate import Estimate, EstimateStatus
from tests.test_stage15f2_api import use_issuer  # noqa: F401  (a fixture)
from tests.test_stage15f2_issuing import Delivery, issuer, user_of
from tests.test_stage16e2_contract import (
    CONTRACT, OWNER_TG, STRANGER_TG, contract_engine, load_migration, login, ready, run, url,
)

TODAY = date(2026, 10, 20)


async def issued(db, telegram_id):
    """A world whose contract has been issued by the real issuer (frozen at the day the tests run)."""
    w = await ready(db, telegram_id=telegram_id)
    owner_id, project_id, contract_id = w.owner.id, w.project.id, w.contract.id
    run_ = issuer(delivery=Delivery())
    await run_.start_contract(db, await user_of(db, owner_id), project_id, contract_id)
    await run_.drain()
    return w, owner_id, project_id, contract_id


def service(db):
    return ContractService(db)


async def estimate_of(db, project_id=None):
    query = select(Estimate) if project_id is None else select(Estimate).where(Estimate.project_id == project_id)
    return (await db.execute(query)).scalar_one()


async def test_signing_makes_the_contract_signed_and_its_estimate_accepted_in_one_step(db_session):
    w, owner_id, project_id, contract_id = await issued(db_session, 9901)
    issued_day = (await service(db_session).get(project_id, contract_id, owner_id)).issued_at.date()
    row = await service(db_session).sign(project_id, contract_id, owner_id, issued_day, today=issued_day)
    assert (row.status, row.signed_on) == ("SIGNED", issued_day)
    assert (await estimate_of(db_session)).status is EstimateStatus.ACCEPTED
    read = contract_read(row)
    assert read.signed_on == issued_day and read.estimate_version == 1 and read.issued_at is not None
    frozen = row.document_html
    assert "SIGNED" == row.status and frozen  # the page and the snapshot are still the issued ones


async def test_only_an_issued_contract_is_signed(db_session):
    w = await ready(db_session, telegram_id=9902)
    with pytest.raises(ContractNotEditableError):  # a draft
        await service(db_session).sign(w.project.id, w.contract.id, w.owner.id, TODAY, today=TODAY)
    w2, owner_id, project_id, contract_id = await issued(db_session, 9903)
    day = (await service(db_session).get(project_id, contract_id, owner_id)).issued_at.date()
    await service(db_session).sign(project_id, contract_id, owner_id, day, today=day)
    with pytest.raises(ContractNotEditableError):  # already signed
        await service(db_session).sign(project_id, contract_id, owner_id, day, today=day)


async def test_the_day_of_signing_is_not_in_the_future_and_not_before_the_issue(db_session):
    _, owner_id, project_id, contract_id = await issued(db_session, 9904)
    issued_day = (await service(db_session).get(project_id, contract_id, owner_id)).issued_at.date()
    with pytest.raises(ContractSignError) as future:
        await service(db_session).sign(project_id, contract_id, owner_id, date(issued_day.year + 1, 1, 1), today=issued_day)
    assert future.value.reason == "SIGNED_ON_IN_FUTURE"
    with pytest.raises(ContractSignError) as early:
        await service(db_session).sign(project_id, contract_id, owner_id, date(2000, 1, 1), today=issued_day)
    assert early.value.reason == "SIGNED_ON_BEFORE_ISSUE"
    row = await service(db_session).get(project_id, contract_id, owner_id)
    assert row.status == "ISSUED" and (await estimate_of(db_session)).status is EstimateStatus.FINAL  # nothing changed


@pytest.mark.parametrize("status", [EstimateStatus.DRAFT, EstimateStatus.ARCHIVED])
async def test_a_changed_estimate_refuses_the_signing_and_changes_nothing(db_session, status):
    _, owner_id, project_id, contract_id = await issued(db_session, 9905 + (status is EstimateStatus.ARCHIVED))
    day = (await service(db_session).get(project_id, contract_id, owner_id)).issued_at.date()
    (await estimate_of(db_session)).status = status
    await db_session.commit()
    with pytest.raises(ContractSignError) as refused:
        await service(db_session).sign(project_id, contract_id, owner_id, day, today=day)
    assert refused.value.reason == "ESTIMATE_CHANGED"
    assert (await service(db_session).get(project_id, contract_id, owner_id)).status == "ISSUED"


async def test_a_second_contract_of_the_object_cannot_be_signed_while_one_is_signed_but_can_after_it_is_closed(db_session):
    _, owner_id, project_id, first = await issued(db_session, 9907)
    svc = service(db_session)
    day = (await svc.get(project_id, first, owner_id)).issued_at.date()
    await svc.sign(project_id, first, owner_id, day, today=day)
    # a new version issued by hand-made rows (the issue itself is tested elsewhere): same object, issued, same estimate
    base = await svc.get(project_id, first, owner_id)
    second = Contract(owner_id=owner_id, project_id=project_id, version=2, status="ISSUED", answers={}, questionnaire_version=2,
                      issued_at=base.issued_at, snapshot={}, document_html="<html></html>", estimate_id=base.estimate_id, estimate_version=1)
    db_session.add(second)
    await db_session.commit()
    with pytest.raises(ContractSignError) as refused:
        await svc.sign(project_id, second.id, owner_id, day, today=day)
    assert refused.value.reason == "ALREADY_SIGNED"
    closed = await svc.close(project_id, first, owner_id)
    assert closed.status == "ARCHIVED" and (await estimate_of(db_session)).status is EstimateStatus.ACCEPTED  # the estimate stays
    signed = await svc.sign(project_id, second.id, owner_id, day, today=day)
    assert signed.status == "SIGNED"


async def test_closing_takes_an_issued_or_a_signed_contract_to_the_archive_and_nothing_else(db_session):
    w = await ready(db_session, telegram_id=9908)
    with pytest.raises(ContractNotEditableError):  # a draft is abandoned, not closed
        await service(db_session).close(w.project.id, w.contract.id, w.owner.id)
    _, owner_id, project_id, contract_id = await issued(db_session, 9909)
    closed = await service(db_session).close(project_id, contract_id, owner_id)
    assert closed.status == "ARCHIVED" and (await estimate_of(db_session, project_id)).status is EstimateStatus.FINAL
    with pytest.raises(ContractNotEditableError):
        await service(db_session).close(project_id, contract_id, owner_id)


async def test_a_foreign_contract_is_not_found(db_session):
    _, owner_id, project_id, contract_id = await issued(db_session, 9910)
    stranger = await ready(db_session, telegram_id=9911)
    with pytest.raises(ProjectNotFoundError):
        await service(db_session).sign(project_id, contract_id, stranger.owner.id, TODAY, today=TODAY)
    with pytest.raises(ProjectNotFoundError):
        await service(db_session).close(project_id, contract_id, stranger.owner.id)


# --- HTTP ------------------------------------------------------------------------------------------------------------------------


async def test_the_routes_sign_and_close_with_their_refusals(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    w = await ready(db_session, telegram_id=OWNER_TG)
    project_id, contract_id = str(w.project.id), str(w.contract.id)
    run_ = use_issuer(issuer(delivery=Delivery()))
    headers = await login(async_client)
    assert (await async_client.post(url(project_id, f"/{contract_id}/sign"), json={"signed_on": "2026-10-10"})).status_code == 401
    draft = await async_client.post(url(project_id, f"/{contract_id}/sign"), json={"signed_on": "2026-10-10"}, headers=headers)
    assert draft.status_code == 409 and draft.json()["detail"]["code"] == "CONTRACT_NOT_EDITABLE"
    assert (await async_client.post(url(project_id, f"/{contract_id}/issue"), headers=headers)).status_code == 202
    await run_.drain()
    for body in ({}, {"signed_on": "10.10.2026"}, {"signed_on": "2026-10-10", "x": 1}):
        assert (await async_client.post(url(project_id, f"/{contract_id}/sign"), json=body, headers=headers)).status_code == 422
    future = await async_client.post(url(project_id, f"/{contract_id}/sign"), json={"signed_on": "2999-01-01"}, headers=headers)
    assert future.status_code == 422 and future.json()["detail"] == {
        "code": "CONTRACT_SIGN_REFUSED", "message": "the contract cannot be signed: SIGNED_ON_IN_FUTURE", "details": {"reason": "SIGNED_ON_IN_FUTURE"}}
    early = await async_client.post(url(project_id, f"/{contract_id}/sign"), json={"signed_on": "2000-01-01"}, headers=headers)
    assert early.json()["detail"]["details"]["reason"] == "SIGNED_ON_BEFORE_ISSUE"
    today = datetime.now(UTC).date().isoformat()
    ok = await async_client.post(url(project_id, f"/{contract_id}/sign"), json={"signed_on": today}, headers=headers)
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "SIGNED" and ok.json()["signed_on"] == today and ok.json()["estimate_version"] == 1
    closed = await async_client.post(url(project_id, f"/{contract_id}/close"), headers=headers)
    assert closed.status_code == 200 and closed.json()["status"] == "ARCHIVED"
    assert (await async_client.post(url(project_id, f"/{contract_id}/close"), headers=headers)).status_code == 409


async def test_a_stranger_gets_404_on_sign_and_close(async_client: AsyncClient, db_session, use_issuer):  # noqa: F811
    mine = await ready(db_session, telegram_id=OWNER_TG)
    theirs = await ready(db_session, telegram_id=STRANGER_TG)
    use_issuer(issuer(delivery=Delivery()))
    headers = await login(async_client)
    for tail, body in (("sign", {"signed_on": "2026-10-10"}), ("close", None)):
        response = await async_client.post(url(theirs.project.id, f"/{theirs.contract.id}/{tail}"), json=body, headers=headers)
        assert response.status_code == 404
    unknown = await async_client.post(url(mine.project.id, f"/{uuid.uuid4()}/close"), headers=headers)
    assert unknown.status_code == 404


# --- migration -------------------------------------------------------------------------------------------------------------------


def test_revision_chain_and_length():
    module = load_migration("0046_contract_signed")
    assert module.revision == "0046_contract_signed" and module.down_revision == "0045_contract_issue" and len(module.revision) <= 32


def engine_0046():
    engine = contract_engine()
    run(engine, "0045_contract_issue", "upgrade")
    run(engine, "0046_contract_signed", "upgrade")
    return engine


FROZEN = {"issued": "2026-10-10", "snapshot": "{}", "html": "<html></html>"}
SIGNED = CONTRACT.replace("issued_at, snapshot", "signed_on, issued_at, snapshot").replace(":issued, :snapshot", ":signed, :issued, :snapshot")


def test_the_database_refuses_a_signed_contract_without_its_day_and_a_second_signed_contract_of_an_object():
    engine = engine_0046()
    with engine.begin() as conn:
        conn.execute(text(SIGNED), {"id": "a", "version": 1, "status": "SIGNED", "signed": "2026-10-11", **FROZEN})
        conn.execute(text(SIGNED), {"id": "b", "version": 2, "status": "ISSUED", "signed": None, **FROZEN})
        conn.execute(text(SIGNED), {"id": "c", "version": 3, "status": "ARCHIVED", "signed": "2026-10-12", **FROZEN})  # a closed signed one
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text(SIGNED), {"id": "d", "version": 4, "status": "SIGNED", "signed": None, **FROZEN})
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(text(SIGNED), {"id": "e", "version": 5, "status": "SIGNED", "signed": "2026-10-13", **FROZEN})


def test_downgrade_refuses_while_a_day_of_signing_exists_even_on_an_archived_contract_and_then_restores_the_old_shape():
    engine = engine_0046()
    with engine.begin() as conn:
        conn.execute(text(SIGNED), {"id": "a", "version": 1, "status": "SIGNED", "signed": "2026-10-11", **FROZEN})
    with pytest.raises(RuntimeError, match="1 contract.s. carry a day of signing"):
        run(engine, "0046_contract_signed", "downgrade")
    with engine.begin() as conn:
        conn.execute(text("UPDATE contracts SET status = 'ARCHIVED'"))  # closed, but the evidence of the day stays
    with pytest.raises(RuntimeError, match="day of signing"):
        run(engine, "0046_contract_signed", "downgrade")
    with engine.begin() as conn:
        conn.execute(text("UPDATE contracts SET signed_on = NULL"))
    run(engine, "0046_contract_signed", "downgrade")
    insp = inspect(engine)
    assert "signed_on" not in {c["name"] for c in insp.get_columns("contracts")}
    assert "uq_contracts_one_signed" not in {i["name"] for i in insp.get_indexes("contracts")}
    run(engine, "0046_contract_signed", "upgrade")  # up again
    assert "signed_on" in {c["name"] for c in inspect(engine).get_columns("contracts")}
