"""The open page for the electrician and the plumber (V2-14): find the link by its secret, build the white-listed page, keep what the craftsman writes, record what he sends.

The only door is the secret of the link. Nothing here takes an owner or an object id from the request: both come from the link row. The key of the owner is put in force after the
link is found, so the encrypted words of the object can be read and written. A craftsman writes the answers of one room at a time; they replace the earlier answers of that room.
"""
import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import client_link as links
from app.domain import trade_link as texts
from app.domain.calendar.messages import language_of_telegram
from app.domain.rules import trade_checklist as rules
from app.domain.services.calendar_service import CalendarService
from app.domain.services.client_link_service import aware
from app.domain.services.data_key_service import DataKeyService
from app.domain.services.media_storage import MediaStorage
from app.domain.services.room_service import RoomService
from app.domain.services.trade_link_service import own_of, typical_in_order
from app.domain.services.trade_media_service import TradeMedia, TradeMediaService
from app.models.executor_profile import ExecutorProfile
from app.models.project import Project
from app.models.trade_link import TradeAnswer, TradeLink, TradeSubmission
from app.models.user import User
from app.schemas.room import RoomRead
from app.schemas.trade_link import (
    PortalContractor,
    PortalLinkInfo,
    PortalRoom,
    PortalTradePage,
    PositionRead,
)

logger = logging.getLogger(__name__)


class TradePortalService:
    def __init__(self, db: AsyncSession, secret: str, web_app_url: str = "", storage: MediaStorage | None = None) -> None:
        self.db = db
        self.secret = secret
        self.web_app_url = web_app_url
        self.storage = storage  # V2-14b: signs the links of the photos; None = no photos on the page

    # -- the door ---------------------------------------------------------------------------------------------------------------

    async def resolve(self, token: str | None, *, now: datetime | None = None) -> TradeLink:
        """The link of a secret. Unknown: not found (always the same answer); revoked or expired: inactive."""
        if not links.looks_like_token(token):
            raise links.ClientLinkNotFoundError("no link")
        link = (await self.db.execute(select(TradeLink).where(TradeLink.token_hash == links.hash_token(token or "")))).scalar_one_or_none()
        if link is None:
            raise links.ClientLinkNotFoundError("no link")
        now = now or datetime.now(UTC)
        if link.revoked_at is not None or aware(link.expires_at) <= now:
            raise links.LinkInactiveError("inactive")
        await DataKeyService(self.db).put_in_force(link.owner_id)
        return link

    # -- the page ---------------------------------------------------------------------------------------------------------------

    async def _contractor(self, owner_id: uuid.UUID) -> PortalContractor:
        profile = (await self.db.execute(select(ExecutorProfile).where(ExecutorProfile.owner_id == owner_id))).scalar_one_or_none()
        if profile is not None:
            return PortalContractor(name=profile.name, phone=profile.phone, email=profile.email, city=profile.city)
        user = (await self.db.execute(select(User).where(User.id == owner_id))).scalar_one_or_none()
        name = " ".join(part for part in (user.first_name, user.last_name) if part) if user is not None else ""
        return PortalContractor(name=name or None)

    async def _answers(self, link: TradeLink) -> dict[uuid.UUID, list[TradeAnswer]]:
        rows = (
            await self.db.execute(
                select(TradeAnswer).where(TradeAnswer.project_id == link.project_id, TradeAnswer.owner_id == link.owner_id, TradeAnswer.trade == link.trade)
            )
        ).scalars()
        by_room: dict[uuid.UUID, list[TradeAnswer]] = {}
        for row in rows:
            by_room.setdefault(row.room_id, []).append(row)
        return by_room

    async def _media(self, link: TradeLink) -> TradeMedia:
        """The photos of the rooms; whatever goes wrong with them the page of the craftsman still opens (and the failure is logged, without any name or address)."""
        try:
            return await TradeMediaService(self.db, self.storage).for_trade(link.owner_id, link.project_id, link.trade)
        except Exception:
            logger.exception("the photos of a craftsman's page could not be made")
            return TradeMedia()

    async def page(self, link: TradeLink, lang: str | None, *, now: datetime | None = None, touch: bool = False) -> PortalTradePage:
        lang = links.clean_language(lang or link.language)
        now = now or datetime.now(UTC)
        project = (await self.db.execute(select(Project).where(Project.id == link.project_id, Project.owner_id == link.owner_id))).scalar_one()
        if touch:
            link.last_viewed_at = now
            link.view_count = (link.view_count or 0) + 1
            await self.db.commit()
            await self.db.refresh(link)
        rooms, _total = await RoomService(self.db).list_rooms(link.project_id, link.owner_id)
        by_room = await self._answers(link)
        media = await self._media(link)
        portal_rooms: list[PortalRoom] = []
        for room in rooms:
            read = RoomRead.model_validate(room)
            calc = read.calculations
            mine = by_room.get(room.id, [])
            portal_rooms.append(
                PortalRoom(
                    id=read.id,
                    name=read.name,
                    length=read.length,
                    width=read.width,
                    height=read.height,
                    floor_area=calc.floor_area if calc else None,
                    perimeter=calc.perimeter if calc else None,
                    typical=typical_in_order(link.trade, mine),
                    own=own_of(mine),
                    photos=media.rooms[room.id].photos if room.id in media.rooms else [],
                    route_map=media.rooms[room.id].route_map if room.id in media.rooms else [],
                )
            )
        count, last = (
            await self.db.execute(
                select(func.count(), func.max(TradeSubmission.created_at)).where(
                    TradeSubmission.project_id == link.project_id, TradeSubmission.trade == link.trade
                )
            )
        ).one()
        return PortalTradePage(
            link=PortalLinkInfo(expires_at=link.expires_at, language=link.language),
            lang=lang,
            trade=link.trade,  # type: ignore[arg-type]
            contractor=await self._contractor(link.owner_id),
            project_name=project.name,
            owner_note=link.owner_note,
            positions=[PositionRead(key=p.key, unit=p.unit) for p in rules.positions_of(link.trade)],  # type: ignore[arg-type]
            rooms=portal_rooms,
            submissions_count=count,
            last_submitted_at=last,
            photos_expire_at=media.expires_at,
        )

    # -- the answers ------------------------------------------------------------------------------------------------------------

    async def save_room(
        self, link: TradeLink, room_id: uuid.UUID, typical: list[dict] | None, own: list[dict] | None, *, now: datetime | None = None
    ) -> None:
        """Replace what the craftsman wrote for one room. The room must be a room of this object that is not archived; wrong entries change nothing."""
        now = now or datetime.now(UTC)
        rooms, _total = await RoomService(self.db).list_rooms(link.project_id, link.owner_id)
        if room_id not in {room.id for room in rooms}:
            raise links.ClientLinkNotFoundError("no such room")
        clean_typical, clean_own = rules.clean_room_answers(link.trade, typical, own)
        await self.db.execute(
            delete(TradeAnswer).where(
                TradeAnswer.project_id == link.project_id, TradeAnswer.owner_id == link.owner_id, TradeAnswer.trade == link.trade, TradeAnswer.room_id == room_id
            )
        )
        await self.db.flush()
        for a in clean_typical:
            self.db.add(
                TradeAnswer(
                    owner_id=link.owner_id, project_id=link.project_id, trade=link.trade, room_id=room_id, position_key=a.key,
                    quantity=a.quantity, unit=a.unit, note=a.note, created_at=now, updated_at=now,
                )
            )
        for index, o in enumerate(clean_own):
            at = now.replace(microsecond=min(now.microsecond + index, 999999))  # keeps the order the craftsman wrote them in
            self.db.add(
                TradeAnswer(
                    owner_id=link.owner_id, project_id=link.project_id, trade=link.trade, room_id=room_id, custom_name=o.name,
                    quantity=o.quantity, unit=o.unit, note=o.note, created_at=at, updated_at=now,
                )
            )
        await self.db.commit()

    # -- the submission ---------------------------------------------------------------------------------------------------------

    async def submit(self, link: TradeLink, master_name: str, *, ip: str, agent: str, now: datetime | None = None) -> TradeSubmission:
        """The craftsman says he is done: one row in the journal with a hash of what he wrote. Nothing written, nothing to send."""
        now = now or datetime.now(UTC)
        name = links.clean_name(master_name)
        rows = list(
            (
                await self.db.execute(
                    select(TradeAnswer).where(TradeAnswer.project_id == link.project_id, TradeAnswer.owner_id == link.owner_id, TradeAnswer.trade == link.trade)
                )
            ).scalars()
        )
        if not rows:
            raise rules.TradeChecklistError("NOTHING_TO_SEND", "write at least one answer first")
        digest = rules.answers_hash(
            [(str(r.room_id), r.position_key or r.custom_name or "", r.unit, str(r.quantity if r.quantity is not None else ""), r.note or "") for r in rows]
        )
        row = TradeSubmission(
            owner_id=link.owner_id,
            project_id=link.project_id,
            link_id=link.id,
            trade=link.trade,
            master_name=name,
            answers_hash=digest,
            answers_count=len(rows),
            ip_hash=links.hash_value(self.secret, ip),
            agent_hash=links.hash_value(self.secret, agent[:300]),
            created_at=now,
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def owner_notice(self, link: TradeLink, submission: TradeSubmission) -> links.OwnerNotice | None:
        """The message to the owner's Telegram chat about a submission just recorded: in the language the owner chose for the messages of the calendar (else that of their
        Telegram), with a button that opens the object. None when the owner has no Telegram chat (signs in with a password)."""
        user = (await self.db.execute(select(User).where(User.id == link.owner_id))).scalar_one_or_none()
        if user is None or user.telegram_user_id <= 0:
            return None
        prefs = await CalendarService(self.db).prefs(link.owner_id)
        lang = links.clean_language(prefs.language or language_of_telegram(user.language_code))
        project = (await self.db.execute(select(Project).where(Project.id == link.project_id, Project.owner_id == link.owner_id))).scalar_one()
        text = texts.notice_text(lang, trade=texts.trade_name(link.trade, lang), master=submission.master_name, project=project.name, count=submission.answers_count)
        return links.OwnerNotice(
            chat_id=user.telegram_user_id,
            text=text,
            open_url=links.project_open_url(self.web_app_url, link.project_id),
            button_text=links.texts()["notice_button"][lang],
        )
