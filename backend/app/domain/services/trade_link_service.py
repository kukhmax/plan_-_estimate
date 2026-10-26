"""The link for the electrician and the plumber, the owner's side (V2-14): make, extend, revoke a link, write the word to the craftsman, read the answers and the journal.

Every call is owner-scoped. The secret is made here and handed back once; only its SHA-256 is stored. Services commit internally.
"""
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import client_link as links
from app.domain.exceptions import ProjectNotFoundError
from app.domain.rules import trade_checklist as rules
from app.domain.services.client_link_service import aware
from app.domain.services.room_service import RoomService
from app.models.project import Project
from app.models.trade_link import TradeAnswer, TradeLink, TradeSubmission
from app.schemas.trade_link import (
    OwnerRoomAnswers,
    OwnRead,
    PositionRead,
    SubmissionRead,
    TradeAnswersResponse,
    TradeLinkRead,
    TypicalRead,
)


def typical_of(rows: list[TradeAnswer]) -> list[TypicalRead]:
    return [TypicalRead(key=r.position_key or "", unit=r.unit, quantity=r.quantity, note=r.note) for r in rows if r.position_key is not None]


def own_of(rows: list[TradeAnswer]) -> list[OwnRead]:
    ordered = sorted((r for r in rows if r.custom_name is not None), key=lambda r: (aware(r.created_at), str(r.id)))
    return [OwnRead(name=r.custom_name or "", quantity=r.quantity or 0, unit=r.unit, note=r.note) for r in ordered]


def typical_in_order(trade: str, rows: list[TradeAnswer]) -> list[TypicalRead]:
    order = {p.key: i for i, p in enumerate(rules.positions_of(trade))}
    return sorted(typical_of(rows), key=lambda t: order.get(t.key, 99))


class TradeLinkService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _ensure_project(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> None:
        found = (await self.db.execute(select(Project.id).where(Project.id == project_id, Project.owner_id == owner_id))).scalar_one_or_none()
        if found is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")

    async def _current(self, owner_id: uuid.UUID, project_id: uuid.UUID, trade: str) -> TradeLink | None:
        return (
            await self.db.execute(
                select(TradeLink).where(
                    TradeLink.project_id == project_id, TradeLink.owner_id == owner_id, TradeLink.trade == trade, TradeLink.revoked_at.is_(None)
                )
            )
        ).scalar_one_or_none()

    async def read_of(self, link: TradeLink, *, now: datetime | None = None) -> TradeLinkRead:
        now = now or datetime.now(UTC)
        answers = (
            await self.db.execute(
                select(func.count()).select_from(TradeAnswer).where(TradeAnswer.project_id == link.project_id, TradeAnswer.trade == link.trade)
            )
        ).scalar_one()
        count, last = (
            await self.db.execute(
                select(func.count(), func.max(TradeSubmission.created_at)).where(
                    TradeSubmission.project_id == link.project_id, TradeSubmission.trade == link.trade
                )
            )
        ).one()
        return TradeLinkRead(
            trade=link.trade,  # type: ignore[arg-type]
            language=link.language,
            owner_note=link.owner_note,
            created_at=link.created_at,
            expires_at=link.expires_at,
            last_viewed_at=link.last_viewed_at,
            view_count=link.view_count or 0,
            expired=aware(link.expires_at) <= now,
            answers_count=answers,
            submissions_count=count,
            last_submitted_at=last,
        )

    # -- the links --------------------------------------------------------------------------------------------------------------

    async def status(self, owner_id: uuid.UUID, project_id: uuid.UUID) -> dict[str, TradeLink | None]:
        await self._ensure_project(owner_id, project_id)
        return {trade: await self._current(owner_id, project_id, trade) for trade in rules.TRADES}

    async def create(
        self, owner_id: uuid.UUID, project_id: uuid.UUID, trade: str, language: str | None, note: str | None, *, now: datetime | None = None
    ) -> tuple[TradeLink, str]:
        """A new link for the trade; the earlier one of the same trade stops working (the answers stay). Returns the row and the secret (shown once)."""
        trade = rules.clean_trade(trade)
        owner_note = rules.clean_owner_note(note)
        await self._ensure_project(owner_id, project_id)
        now = now or datetime.now(UTC)
        old = await self._current(owner_id, project_id, trade)
        if old is not None:
            old.revoked_at = now
            await self.db.flush()  # the unique index of the unrevoked link must see the old one gone
        token = links.new_token()
        link = TradeLink(
            owner_id=owner_id,
            project_id=project_id,
            trade=trade,
            token_hash=links.hash_token(token),
            language=links.clean_language(language),
            owner_note=owner_note,
            created_at=now,
            expires_at=now + links.LINK_TERM,
            view_count=0,
        )
        self.db.add(link)
        try:
            await self.db.commit()
        except IntegrityError:
            await self.db.rollback()
            raise rules.TradeChecklistError("LINK_BUSY", "the link is being made by another request") from None
        await self.db.refresh(link)
        return link, token

    async def _link(self, owner_id: uuid.UUID, project_id: uuid.UUID, trade: str) -> TradeLink:
        trade = rules.clean_trade(trade)
        await self._ensure_project(owner_id, project_id)
        link = await self._current(owner_id, project_id, trade)
        if link is None:
            raise links.ClientLinkNotFoundError("no link")
        return link

    async def extend(self, owner_id: uuid.UUID, project_id: uuid.UUID, trade: str, *, now: datetime | None = None) -> TradeLink:
        """Thirty more days counted from today (an expired link comes back to life; a revoked one does not)."""
        link = await self._link(owner_id, project_id, trade)
        now = now or datetime.now(UTC)
        link.expires_at = max(aware(link.expires_at), now + links.LINK_TERM)
        await self.db.commit()
        await self.db.refresh(link)
        return link

    async def revoke(self, owner_id: uuid.UUID, project_id: uuid.UUID, trade: str, *, now: datetime | None = None) -> None:
        link = await self._link(owner_id, project_id, trade)
        link.revoked_at = now or datetime.now(UTC)
        await self.db.commit()

    async def set_note(self, owner_id: uuid.UUID, project_id: uuid.UUID, trade: str, note: str | None) -> TradeLink:
        owner_note = rules.clean_owner_note(note)
        link = await self._link(owner_id, project_id, trade)
        link.owner_note = owner_note
        await self.db.commit()
        await self.db.refresh(link)
        return link

    # -- the answers ------------------------------------------------------------------------------------------------------------

    async def answers(self, owner_id: uuid.UUID, project_id: uuid.UUID, trade: str) -> TradeAnswersResponse:
        """What the craftsman wrote, by room (the rooms of the object that are not archived), and the journal of his submissions, the newest first."""
        trade = rules.clean_trade(trade)
        await self._ensure_project(owner_id, project_id)
        rooms, _total = await RoomService(self.db).list_rooms(project_id, owner_id)
        rows = list(
            (
                await self.db.execute(
                    select(TradeAnswer).where(TradeAnswer.project_id == project_id, TradeAnswer.owner_id == owner_id, TradeAnswer.trade == trade)
                )
            ).scalars()
        )
        by_room: dict[uuid.UUID, list[TradeAnswer]] = {}
        for row in rows:
            by_room.setdefault(row.room_id, []).append(row)
        out: list[OwnerRoomAnswers] = []
        for room in rooms:
            mine = by_room.get(room.id, [])
            updated = max((aware(r.updated_at) for r in mine), default=None)
            out.append(OwnerRoomAnswers(room_id=room.id, room_name=room.name, typical=typical_in_order(trade, mine), own=own_of(mine), updated_at=updated))
        journal = list(
            (
                await self.db.execute(
                    select(TradeSubmission)
                    .where(TradeSubmission.project_id == project_id, TradeSubmission.owner_id == owner_id, TradeSubmission.trade == trade)
                    .order_by(TradeSubmission.created_at.desc(), TradeSubmission.id.desc())
                )
            ).scalars()
        )
        return TradeAnswersResponse(
            trade=trade,  # type: ignore[arg-type]
            positions=[PositionRead(key=p.key, unit=p.unit) for p in rules.positions_of(trade)],  # type: ignore[arg-type]
            rooms=out,
            submissions=[SubmissionRead(id=s.id, master_name=s.master_name, answers_count=s.answers_count, created_at=s.created_at) for s in journal],
        )
