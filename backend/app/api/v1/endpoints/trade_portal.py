"""The open page for the electrician and the plumber (V2-14): `/api/public/trade`. No login: the secret of the link, sent in the header `X-Trade-Link`, is the only door.

Built like the open page of the client (`client_portal.py`): the secret travels in a header and not in the path, every answer says `no-store` and `noindex`, an unknown secret always gets
the same 404, a revoked or expired one 410, requests are counted per address (in memory) and too many bad secrets from one address close the door for a while.
"""
import logging
import uuid

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
)

from app.api.deps import get_message_sender, get_trade_portal_service
from app.api.v1.endpoints.client_portal import SECURITY_HEADERS, client_ip
from app.core.rate_limit import SlidingWindowLimiter
from app.domain import client_link as links
from app.domain.exceptions import MessageDeliveryDisabledError, MessageDeliveryError
from app.domain.rules import trade_checklist as rules
from app.domain.services.trade_portal_service import TradePortalService
from app.models.trade_link import TradeLink
from app.schemas.trade_link import PortalRoomWrite, PortalSubmit, PortalTradePage

logger = logging.getLogger(__name__)


async def _secure_headers(response: Response) -> None:
    response.headers.update(SECURITY_HEADERS)


router = APIRouter(prefix="/public/trade", dependencies=[Depends(_secure_headers)])

page_limiter = SlidingWindowLimiter(limit=120, window_seconds=60)
action_limiter = SlidingWindowLimiter(limit=60, window_seconds=60)
miss_limiter = SlidingWindowLimiter(limit=20, window_seconds=300)


def reset_limits() -> None:
    for limiter in (page_limiter, action_limiter, miss_limiter):
        limiter.reset()


def _error(code_: int, code: str, message: str, headers: dict[str, str] | None = None) -> HTTPException:
    return HTTPException(code_, detail={"code": code, "message": message}, headers={**SECURITY_HEADERS, **(headers or {})})


def _limited(limiter: SlidingWindowLimiter, key: str) -> None:
    if not limiter.allow(key):
        raise _error(429, "RATE_LIMITED", "too many requests", {"Retry-After": str(limiter.retry_after(key))})


async def _door(request: Request, service: TradePortalService, token: str | None, limiter: SlidingWindowLimiter) -> TradeLink:
    ip = client_ip(request)
    if miss_limiter.retry_after(ip) > 0:
        raise _error(429, "RATE_LIMITED", "too many requests", {"Retry-After": str(miss_limiter.retry_after(ip))})
    _limited(limiter, ip)
    try:
        return await service.resolve(token)
    except links.ClientLinkNotFoundError:
        miss_limiter.allow(ip)
        raise _error(404, "NOT_FOUND", "the link does not exist") from None
    except links.LinkInactiveError:
        raise _error(410, "LINK_INACTIVE", "the link is no longer active") from None


async def _tell_owner(sender, notice: links.OwnerNotice) -> None:
    """Send the message to the owner after the answer to the craftsman has gone. A failure never reaches the craftsman (the submission is recorded); it is logged without the text or the chat."""
    try:
        await sender.send_message(notice.chat_id, notice.text, open_url=notice.open_url, button_text=notice.button_text)
    except MessageDeliveryDisabledError:
        logger.info("a craftsman sent his answer; messages to the owner are switched off")
    except MessageDeliveryError as exc:
        logger.warning("a craftsman sent his answer; the owner was not told: %s", type(exc).__name__)


def _failure(exc: Exception) -> HTTPException:
    if isinstance(exc, (rules.TradeChecklistError, links.ClientLinkError)):
        return _error(422, exc.code, str(exc))
    return _error(404, "NOT_FOUND", "not found")


@router.get("", response_model=PortalTradePage, summary="The page of the craftsman: the rooms with their sizes, the checklist, his answers")
async def read_page(
    request: Request,
    lang: str | None = Query(default=None, max_length=5),
    x_trade_link: str | None = Header(default=None, max_length=100),
    service: TradePortalService = Depends(get_trade_portal_service),
) -> PortalTradePage:
    link = await _door(request, service, x_trade_link, page_limiter)
    return await service.page(link, lang, touch=True)


@router.put("/rooms/{room_id}", response_model=PortalTradePage, summary="The craftsman writes the answers of one room (they replace the earlier ones of the room)")
async def save_room(
    room_id: uuid.UUID,
    payload: PortalRoomWrite,
    request: Request,
    lang: str | None = Query(default=None, max_length=5),
    x_trade_link: str | None = Header(default=None, max_length=100),
    service: TradePortalService = Depends(get_trade_portal_service),
) -> PortalTradePage:
    link = await _door(request, service, x_trade_link, action_limiter)
    try:
        await service.save_room(link, room_id, [t.model_dump() for t in payload.typical], [o.model_dump() for o in payload.own])
    except (rules.TradeChecklistError, links.ClientLinkNotFoundError) as exc:
        raise _failure(exc) from exc
    return await service.page(link, lang)


@router.post("/submit", response_model=PortalTradePage, summary="The craftsman sends his answer: a row in the journal and a message to the owner")
async def submit(
    payload: PortalSubmit,
    request: Request,
    tasks: BackgroundTasks,
    lang: str | None = Query(default=None, max_length=5),
    x_trade_link: str | None = Header(default=None, max_length=100),
    service: TradePortalService = Depends(get_trade_portal_service),
    sender=Depends(get_message_sender),
) -> PortalTradePage:
    link = await _door(request, service, x_trade_link, action_limiter)
    try:
        submission = await service.submit(link, payload.master_name, ip=client_ip(request), agent=request.headers.get("user-agent", ""))
    except (rules.TradeChecklistError, links.ClientLinkError) as exc:
        raise _failure(exc) from exc
    try:
        notice = await service.owner_notice(link, submission)
    except Exception:
        logger.exception("a craftsman sent his answer; the message to the owner could not be put together")
        notice = None
    if notice is not None:
        tasks.add_task(_tell_owner, sender, notice)
    return await service.page(link, lang)
