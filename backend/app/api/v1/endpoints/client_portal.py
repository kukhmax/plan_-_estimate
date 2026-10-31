"""The open page for the client (V2-8): `/api/public/client`. No login: the secret of the link, sent in the header `X-Client-Link`, is the only door.

The secret travels in a header and not in the path so that no access log, referrer or link preview ever holds it (the address the client opens keeps
it after the `#`, which a browser never sends). Every answer says `no-store` and `noindex`. An unknown secret always gets the same 404; a revoked or
expired one gets 410. Requests are counted per address (in memory); too many bad secrets from one address close the door for a while.
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

from app.api.deps import get_client_portal_service, get_message_sender, get_photo_runtime
from app.core.rate_limit import SlidingWindowLimiter
from app.domain import client_link as rules
from app.domain.exceptions import MessageDeliveryDisabledError, MessageDeliveryError
from app.domain.services.client_portal_service import ClientPortalService
from app.domain.services.client_why_service import ClientWhyService
from app.models.client_link import ClientLink
from app.schemas.client_portal import (
    PortalWhy,
    PortalWhyPhoto,
    PortalWhyReason,
    PortalWhyRoom,
    PortalDecideEstimate,
    PortalDecideProposal,
    PortalPage,
)

logger = logging.getLogger(__name__)

SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "X-Robots-Tag": "noindex, nofollow",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
}



async def _secure_headers(response: Response) -> None:
    response.headers.update(SECURITY_HEADERS)


router = APIRouter(prefix="/public/client", dependencies=[Depends(_secure_headers)])

page_limiter = SlidingWindowLimiter(limit=120, window_seconds=60)
action_limiter = SlidingWindowLimiter(limit=20, window_seconds=60)
miss_limiter = SlidingWindowLimiter(limit=20, window_seconds=300)


def reset_limits() -> None:
    for limiter in (page_limiter, action_limiter, miss_limiter):
        limiter.reset()


def client_ip(request: Request) -> str:
    """The address the client came from: the header of the edge (Cloudflare), else the first of the forwarded chain, else the socket."""
    for name in ("cf-connecting-ip", "x-forwarded-for"):
        value = request.headers.get(name)
        if value:
            return value.split(",")[0].strip()[:64]
    return request.client.host if request.client else "unknown"


def _error(code_: int, code: str, message: str, headers: dict[str, str] | None = None) -> HTTPException:
    return HTTPException(code_, detail={"code": code, "message": message}, headers={**SECURITY_HEADERS, **(headers or {})})


def _limited(limiter: SlidingWindowLimiter, key: str) -> None:
    if not limiter.allow(key):
        raise _error(429, "RATE_LIMITED", "too many requests", {"Retry-After": str(limiter.retry_after(key))})


async def _door(request: Request, service: ClientPortalService, token: str | None, limiter: SlidingWindowLimiter) -> ClientLink:
    ip = client_ip(request)
    if miss_limiter.retry_after(ip) > 0:
        raise _error(429, "RATE_LIMITED", "too many requests", {"Retry-After": str(miss_limiter.retry_after(ip))})
    _limited(limiter, ip)
    try:
        return await service.resolve(token)
    except rules.ClientLinkNotFoundError:
        miss_limiter.allow(ip)
        raise _error(404, "NOT_FOUND", "the link does not exist") from None
    except rules.LinkInactiveError:
        raise _error(410, "LINK_INACTIVE", "the link is no longer active") from None


async def _tell_owner(sender, notice: rules.OwnerNotice) -> None:
    """Send the message to the owner after the answer to the client has gone. A failure never reaches the client (the consent is already recorded);
    it is logged without the text or the chat."""
    try:
        await sender.send_message(notice.chat_id, notice.text, open_url=notice.open_url, button_text=notice.button_text)
    except MessageDeliveryDisabledError:
        logger.info("a client decided; messages to the owner are switched off")
    except MessageDeliveryError as exc:
        logger.warning("a client decided; the owner was not told: %s", type(exc).__name__)


async def _notice_after(service: ClientPortalService, link: ClientLink, consent, tasks: BackgroundTasks, sender) -> None:
    try:
        notice = await service.owner_notice(link, consent)
    except Exception:
        logger.exception("a client decided; the message to the owner could not be put together")
        return
    if notice is not None:
        tasks.add_task(_tell_owner, sender, notice)


_STATUS = {
    "AGREE_REQUIRED": 422,
    "NAME_REQUIRED": 422,
    "NAME_TOO_LONG": 422,
    "COMMENT_TOO_LONG": 422,
    "COMMENT_ONLY_ON_DECLINE": 422,
    "ESTIMATE_ALREADY_APPROVED": 409,
    "ESTIMATE_CHANGED": 409,
    "PROPOSAL_CHANGED": 409,
    "ALREADY_DECIDED": 409,
}


def _failure(exc: Exception) -> HTTPException:
    if isinstance(exc, rules.ClientLinkError):
        return _error(_STATUS.get(exc.code, 422), exc.code, str(exc))
    return _error(404, "NOT_FOUND", "not found")


@router.get("", response_model=PortalPage, summary="The page of the client: the estimate, the proposals, what was decided")
async def read_page(
    request: Request,
    lang: str | None = Query(default=None, max_length=5),
    x_client_link: str | None = Header(default=None, max_length=100),
    service: ClientPortalService = Depends(get_client_portal_service),
) -> PortalPage:
    link = await _door(request, service, x_client_link, page_limiter)
    page = await service.page(link, lang, touch=True)
    return page


@router.get("/why", response_model=PortalWhy, summary="Why these works: the standard of each room and the reasons from the inspections, with photos")
async def read_why(
    request: Request,
    x_client_link: str | None = Header(default=None, max_length=100),
    service: ClientPortalService = Depends(get_client_portal_service),
    runtime=Depends(get_photo_runtime),
) -> PortalWhy:
    link = await _door(request, service, x_client_link, page_limiter)
    rooms = await ClientWhyService(service.db, runtime.storage).why(link.owner_id, link.project_id)
    return PortalWhy(
        rooms=[
            PortalWhyRoom(
                room_name=room.room_name,
                quality_target=room.quality_target,
                reasons=[
                    PortalWhyReason(
                        surface_name=r.surface_name, work_name_key=r.work_name_key, work_name=r.work_name, reason_key=r.reason_key, inspected_on=r.inspected_on,
                        photos=[PortalWhyPhoto(thumb_url=p.thumb_url, url=p.url, width=p.width, height=p.height) for p in r.photos],
                    )
                    for r in room.reasons
                ],
            )
            for room in rooms
        ]
    )


@router.post("/estimate/decide", response_model=PortalPage, summary="The client approves or declines the estimate")
async def decide_estimate(
    payload: PortalDecideEstimate,
    request: Request,
    tasks: BackgroundTasks,
    lang: str | None = Query(default=None, max_length=5),
    x_client_link: str | None = Header(default=None, max_length=100),
    service: ClientPortalService = Depends(get_client_portal_service),
    sender=Depends(get_message_sender),
) -> PortalPage:
    link = await _door(request, service, x_client_link, action_limiter)
    try:
        consent = await service.decide_estimate(
            link,
            estimate_id=payload.estimate_id,
            version=payload.version,
            seen_hash=payload.hash,
            decision=payload.decision,
            signer_name=payload.signer_name,
            agree=payload.agree,
            comment=payload.comment,
            ip=client_ip(request),
            agent=request.headers.get("user-agent", ""),
        )
    except (rules.ClientLinkError, rules.ClientLinkNotFoundError) as exc:
        raise _failure(exc) from exc
    await _notice_after(service, link, consent, tasks, sender)
    return await service.page(link, lang)


@router.post("/proposals/{proposal_id}/decide", response_model=PortalPage, summary="The client agrees to or declines a proposal of extra work")
async def decide_proposal(
    proposal_id: uuid.UUID,
    payload: PortalDecideProposal,
    request: Request,
    tasks: BackgroundTasks,
    lang: str | None = Query(default=None, max_length=5),
    x_client_link: str | None = Header(default=None, max_length=100),
    service: ClientPortalService = Depends(get_client_portal_service),
    sender=Depends(get_message_sender),
) -> PortalPage:
    link = await _door(request, service, x_client_link, action_limiter)
    try:
        consent = await service.decide_proposal(
            link,
            proposal_id,
            decision=payload.decision,
            seen_hash=payload.hash,
            signer_name=payload.signer_name,
            agree=payload.agree,
            comment=payload.comment,
            ip=client_ip(request),
            agent=request.headers.get("user-agent", ""),
        )
    except (rules.ClientLinkError, rules.ClientLinkNotFoundError) as exc:
        raise _failure(exc) from exc
    await _notice_after(service, link, consent, tasks, sender)
    return await service.page(link, lang)
