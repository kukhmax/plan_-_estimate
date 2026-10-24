"""The link for the client, the owner's side (V2-8): thin routes over `ClientLinkService`."""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import get_client_link_service, get_current_user
from app.domain import client_link as rules
from app.domain.exceptions import ProjectNotFoundError
from app.domain.services.client_link_service import ClientLinkService, aware
from app.models.client_link import ClientLink
from app.models.user import User
from app.schemas.client_link import (
    ClientConsentRead,
    ClientJournal,
    ClientLinkCreate,
    ClientLinkIssued,
    ClientLinkRead,
    ClientLinkStatus,
    ClientProposalCreate,
    ClientProposalList,
    ClientProposalRead,
)

router = APIRouter()

BASE = "/projects/{project_id}"
FAILURES = (ProjectNotFoundError, rules.ClientLinkError, rules.ClientLinkNotFoundError)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, rules.ClientLinkError):
        code = status.HTTP_409_CONFLICT if exc.code in ("LINK_BUSY", "PROPOSAL_BUSY", "PROPOSAL_NOT_OPEN") else status.HTTP_422_UNPROCESSABLE_ENTITY
        return HTTPException(code, detail={"code": exc.code, "message": str(exc), "field": exc.field})
    if isinstance(exc, rules.ClientLinkNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "NOT_FOUND", "message": str(exc)})
    return HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")


def _read(link: ClientLink) -> ClientLinkRead:
    out = ClientLinkRead.model_validate(link)
    out.expired = aware(link.expires_at) <= datetime.now(UTC)
    return out


@router.get(BASE + "/client-link", response_model=ClientLinkStatus, summary="The link for the client: its term and when it was last opened")
async def link_status(
    project_id: uuid.UUID, current_user: User = Depends(get_current_user), service: ClientLinkService = Depends(get_client_link_service)
) -> ClientLinkStatus:
    try:
        link = await service.status(current_user.id, project_id)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return ClientLinkStatus(link=_read(link) if link else None)


@router.post(BASE + "/client-link", response_model=ClientLinkIssued, status_code=status.HTTP_201_CREATED, summary="Make a new link (the earlier one stops working); the secret is shown once")
async def create_link(
    project_id: uuid.UUID,
    payload: ClientLinkCreate,
    current_user: User = Depends(get_current_user),
    service: ClientLinkService = Depends(get_client_link_service),
) -> ClientLinkIssued:
    try:
        link, token = await service.create(current_user.id, project_id, payload.language)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return ClientLinkIssued(link=_read(link), token=token)


@router.post(BASE + "/client-link/extend", response_model=ClientLinkStatus, summary="Thirty more days from today")
async def extend_link(
    project_id: uuid.UUID, current_user: User = Depends(get_current_user), service: ClientLinkService = Depends(get_client_link_service)
) -> ClientLinkStatus:
    try:
        link = await service.extend(current_user.id, project_id)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return ClientLinkStatus(link=_read(link))


@router.delete(BASE + "/client-link", status_code=status.HTTP_204_NO_CONTENT, summary="Revoke the link: it stops working at once")
async def revoke_link(
    project_id: uuid.UUID, current_user: User = Depends(get_current_user), service: ClientLinkService = Depends(get_client_link_service)
) -> Response:
    try:
        await service.revoke(current_user.id, project_id)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(BASE + "/client-proposals", response_model=ClientProposalList, summary="The proposals of extra work, the newest first")
async def list_proposals(
    project_id: uuid.UUID, current_user: User = Depends(get_current_user), service: ClientLinkService = Depends(get_client_link_service)
) -> ClientProposalList:
    try:
        rows = await service.list_proposals(current_user.id, project_id)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return ClientProposalList(items=[ClientProposalRead.model_validate(r) for r in rows], max_proposals=rules.MAX_PROPOSALS)


@router.post(BASE + "/client-proposals", response_model=ClientProposalRead, status_code=status.HTTP_201_CREATED, summary="Write a proposal of extra work for the client")
async def create_proposal(
    project_id: uuid.UUID,
    payload: ClientProposalCreate,
    current_user: User = Depends(get_current_user),
    service: ClientLinkService = Depends(get_client_link_service),
) -> ClientProposalRead:
    try:
        row = await service.create_proposal(
            current_user.id,
            project_id,
            title=payload.title,
            description=payload.description,
            amount=payload.amount,
            extra_days=payload.extra_days,
        )
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return ClientProposalRead.model_validate(row)


@router.post(BASE + "/client-proposals/{proposal_id}/withdraw", response_model=ClientProposalRead, summary="Withdraw an open proposal")
async def withdraw_proposal(
    project_id: uuid.UUID,
    proposal_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    service: ClientLinkService = Depends(get_client_link_service),
) -> ClientProposalRead:
    try:
        row = await service.withdraw_proposal(current_user.id, project_id, proposal_id)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return ClientProposalRead.model_validate(row)


@router.get(BASE + "/client-journal", response_model=ClientJournal, summary="The journal of consents of the client, the newest first")
async def journal(
    project_id: uuid.UUID, current_user: User = Depends(get_current_user), service: ClientLinkService = Depends(get_client_link_service)
) -> ClientJournal:
    try:
        rows = await service.journal(current_user.id, project_id)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return ClientJournal(items=[ClientConsentRead.model_validate(r) for r in rows])
