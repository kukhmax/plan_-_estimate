"""The link for the electrician and the plumber, the owner's side (V2-14): thin routes over `TradeLinkService`."""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import get_current_user, get_trade_link_service
from app.domain import client_link as links
from app.domain.exceptions import ProjectNotFoundError
from app.domain.rules import trade_checklist as rules
from app.domain.services.trade_link_service import TradeLinkService
from app.models.user import User
from app.schemas.trade_link import (
    TradeAnswersResponse,
    TradeLinkCreate,
    TradeLinkCreated,
    TradeLinkNote,
    TradeLinkRead,
    TradeLinksResponse,
)

router = APIRouter()

BASE = "/projects/{project_id}/trade-links"
FAILURES = (ProjectNotFoundError, rules.TradeChecklistError, links.ClientLinkNotFoundError)


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, rules.TradeChecklistError):
        code = status.HTTP_409_CONFLICT if exc.code == "LINK_BUSY" else status.HTTP_422_UNPROCESSABLE_ENTITY
        return HTTPException(code, detail={"code": exc.code, "message": str(exc), "field": exc.field})
    if isinstance(exc, links.ClientLinkNotFoundError):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail={"code": "NOT_FOUND", "message": str(exc)})
    return HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")


@router.get(BASE, response_model=TradeLinksResponse, summary="The links for the electrician and the plumber: terms, when opened, how much was answered")
async def link_statuses(
    project_id: uuid.UUID, current_user: User = Depends(get_current_user), service: TradeLinkService = Depends(get_trade_link_service)
) -> TradeLinksResponse:
    try:
        current = await service.status(current_user.id, project_id)
        now = datetime.now(UTC)
        reads: dict[str, TradeLinkRead | None] = {t: (await service.read_of(link, now=now) if link else None) for t, link in current.items()}
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return TradeLinksResponse(electric=reads["ELECTRIC"], plumbing=reads["PLUMBING"])


@router.post(BASE + "/{trade}", response_model=TradeLinkCreated, status_code=status.HTTP_201_CREATED, summary="Make a new link for the trade (the earlier one stops working); the secret is shown once")
async def create_link(
    project_id: uuid.UUID,
    trade: str,
    payload: TradeLinkCreate,
    current_user: User = Depends(get_current_user),
    service: TradeLinkService = Depends(get_trade_link_service),
) -> TradeLinkCreated:
    try:
        link, token = await service.create(current_user.id, project_id, trade, payload.language, payload.note)
        read = await service.read_of(link)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return TradeLinkCreated(link=read, token=token)


@router.patch(BASE + "/{trade}", response_model=TradeLinkRead, summary="Change the owner's word to the craftsman")
async def change_note(
    project_id: uuid.UUID,
    trade: str,
    payload: TradeLinkNote,
    current_user: User = Depends(get_current_user),
    service: TradeLinkService = Depends(get_trade_link_service),
) -> TradeLinkRead:
    try:
        link = await service.set_note(current_user.id, project_id, trade, payload.note)
        return await service.read_of(link)
    except FAILURES as exc:
        raise _http_error(exc) from exc


@router.post(BASE + "/{trade}/extend", response_model=TradeLinkRead, summary="Thirty more days from today")
async def extend_link(
    project_id: uuid.UUID, trade: str, current_user: User = Depends(get_current_user), service: TradeLinkService = Depends(get_trade_link_service)
) -> TradeLinkRead:
    try:
        link = await service.extend(current_user.id, project_id, trade)
        return await service.read_of(link)
    except FAILURES as exc:
        raise _http_error(exc) from exc


@router.delete(BASE + "/{trade}", status_code=status.HTTP_204_NO_CONTENT, summary="Revoke the link: it stops working at once (the answers stay)")
async def revoke_link(
    project_id: uuid.UUID, trade: str, current_user: User = Depends(get_current_user), service: TradeLinkService = Depends(get_trade_link_service)
) -> Response:
    try:
        await service.revoke(current_user.id, project_id, trade)
    except FAILURES as exc:
        raise _http_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(BASE + "/{trade}/answers", response_model=TradeAnswersResponse, summary="What the craftsman wrote, by room, and the journal of what he sent")
async def read_answers(
    project_id: uuid.UUID, trade: str, current_user: User = Depends(get_current_user), service: TradeLinkService = Depends(get_trade_link_service)
) -> TradeAnswersResponse:
    try:
        return await service.answers(current_user.id, project_id, trade)
    except FAILURES as exc:
        raise _http_error(exc) from exc
