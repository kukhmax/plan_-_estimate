"""Downtime episodes of an object (Stage 16I.3): open the episode, write the notice, issue it, write the protocol, issue it, abandon.

Every call is scoped to the owner's own project (`ProjectNotFoundError` otherwise). At most one episode is open (a draft or a noticed
one) per object (a partial unique index). The notice's entries change only while the episode is a draft, the protocol's only once the
notice is issued; a closed or abandoned episode does not change. The people present are the active persons of the object; the photos are
the object's own. The sum for readiness is derived from the frozen contract (domain/protocols/downtime.py), never stored as typed.
"""
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.contracts.catalog import load_contract_catalog
from app.domain.exceptions import DowntimeNotEditableError, DowntimeNotFoundError, ProjectNotFoundError
from app.domain.protocols import downtime as D
from app.domain.protocols.sources import DowntimeSources, load_downtime_sources
from app.models.contract import Contract
from app.models.downtime_episode import DowntimeEpisode, DowntimeStatus
from app.models.project import Project
from app.models.project_representative import ProjectRepresentative
from app.schemas.downtime import (
    DowntimeBlockerRead, DowntimeContractRead, DowntimeDayRead, DowntimePhotoRead, DowntimeRead, DowntimeRoomRead, DowntimeSettlementRead,
)

OPEN = (DowntimeStatus.DRAFT.value, DowntimeStatus.NOTICED.value)


def data_of(row: DowntimeEpisode) -> dict[str, Any]:
    return {
        **D.empty_state(),
        "cause_key": row.cause_key, "cause_note": row.cause_note, "room_ids": list(row.room_ids or []), "noticed_on": row.noticed_on,
        "noticed_time": row.noticed_time, "notice_channel": row.notice_channel, "photo_ids": list(row.photo_ids or []), "need_text": row.need_text,
        "need_by": row.need_by, "days": [dict(d) for d in row.days or []], "held_on": row.held_on, "held_time": row.held_time,
        "attendees": list(row.attendees or []), "signature_refused": bool(row.signature_refused), "deadline_note": row.deadline_note, "notes": row.notes,
    }


def cause_text(key: str | None) -> str | None:
    return next((c.text_pl for c in load_contract_catalog().downtime_causes.items if c.key == key), None)


def _money(value: Any) -> str | None:
    return None if value is None else f"{value:.2f}"


class DowntimeService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _ensure_project_owned(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        found = await self.db.execute(select(Project.id).where(Project.id == project_id, Project.owner_id == owner_id))
        if found.scalar_one_or_none() is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")

    async def _open(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> DowntimeEpisode | None:
        return (
            await self.db.execute(
                select(DowntimeEpisode).where(
                    DowntimeEpisode.project_id == project_id, DowntimeEpisode.owner_id == owner_id, DowntimeEpisode.status.in_(OPEN)
                )
            )
        ).scalar_one_or_none()

    async def get(self, project_id: uuid.UUID, episode_id: uuid.UUID, owner_id: uuid.UUID) -> DowntimeEpisode:
        await self._ensure_project_owned(project_id, owner_id)
        row = (
            await self.db.execute(
                select(DowntimeEpisode).where(
                    DowntimeEpisode.id == episode_id, DowntimeEpisode.project_id == project_id, DowntimeEpisode.owner_id == owner_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise DowntimeNotFoundError(f"Downtime {episode_id} not found")
        return row

    async def list(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> "list[DowntimeEpisode]":
        await self._ensure_project_owned(project_id, owner_id)
        return list(
            (
                await self.db.execute(
                    select(DowntimeEpisode)
                    .where(DowntimeEpisode.project_id == project_id, DowntimeEpisode.owner_id == owner_id)
                    .order_by(DowntimeEpisode.sequence.desc())
                )
            ).scalars()
        )

    async def open_episode(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> tuple[DowntimeEpisode, bool]:
        """The open episode of the object and whether it was just created. A second call returns the same episode."""
        await self._ensure_project_owned(project_id, owner_id)
        existing = await self._open(project_id, owner_id)
        if existing is not None:
            return existing, False
        last = (
            await self.db.execute(
                select(DowntimeEpisode.sequence).where(DowntimeEpisode.project_id == project_id).order_by(DowntimeEpisode.sequence.desc()).limit(1)
            )
        ).scalar_one_or_none()
        row = DowntimeEpisode(
            owner_id=owner_id, project_id=project_id, sequence=(last or 0) + 1, status=DowntimeStatus.DRAFT.value,
            room_ids=[], photo_ids=[], days=[], attendees=[], signature_refused=False,
        )
        self.db.add(row)
        try:
            await self.db.commit()
        except IntegrityError:  # two requests opened the episode at the same moment: take the one that won
            await self.db.rollback()
            existing = await self._open(project_id, owner_id)
            if existing is None:
                raise
            return existing, False
        await self.db.refresh(row)
        return row, True

    async def update(self, project_id: uuid.UUID, episode_id: uuid.UUID, owner_id: uuid.UUID, changes: dict[str, Any]) -> DowntimeEpisode:
        row = await self.get(project_id, episode_id, owner_id)
        if row.status not in OPEN:
            raise DowntimeNotEditableError(f"episode {episode_id} is {row.status}: a changed one is a new episode")
        sources = await load_downtime_sources(self.db, owner_id, project_id)
        people = {
            str(p.id): (p.name, p.role_title)
            for p in (
                await self.db.execute(
                    select(ProjectRepresentative).where(
                        ProjectRepresentative.project_id == project_id, ProjectRepresentative.owner_id == owner_id,
                        ProjectRepresentative.is_archived.is_(False),
                    )
                )
            ).scalars()
        }
        state = D.apply_changes(
            data_of(row), changes, status=row.status, room_ids={r[0] for r in sources.rooms},
            photos_of=lambda rooms: {p.id for p in sources.allowed(rooms)}, people=people, catalog=load_contract_catalog(),
        )
        for name in (*D.NOTICE_FIELDS, *D.PROTOCOL_FIELDS):
            setattr(row, name, state[name])
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def archive(self, project_id: uuid.UUID, episode_id: uuid.UUID, owner_id: uuid.UUID) -> DowntimeEpisode:
        """Abandon an open episode (the obstacle went away): an issued notice stays in the journal as it was sent."""
        row = await self.get(project_id, episode_id, owner_id)
        if row.status not in OPEN:
            raise DowntimeNotEditableError(f"episode {episode_id} is {row.status}: only an open episode can be abandoned")
        row.status = DowntimeStatus.ARCHIVED.value
        await self.db.commit()
        await self.db.refresh(row)
        return row

    @staticmethod
    def blockers(row: DowntimeEpisode, data: dict[str, Any], sources: DowntimeSources) -> "list[D.Blocker]":
        """What stands between the next document of the episode and its issue: the executor profile, the customer, a contract to work
        under, then the document's own entries (the notice's while a draft, the protocol's once noticed)."""
        if row.status not in OPEN:
            return []
        blockers = []
        if sources.base.executor is None:
            blockers.append(D.Blocker(D.EXECUTOR_PROFILE_REQUIRED))
        if sources.base.client is None:
            blockers.append(D.Blocker(D.CLIENT_REQUIRED))
        if sources.base.contract is None:
            blockers.append(D.Blocker(D.CONTRACT_REQUIRED))
        return blockers + (D.evaluate_notice(data) if row.status == DowntimeStatus.DRAFT.value else D.evaluate_protocol(data))

    async def gate(self, project_id: uuid.UUID, episode_id: uuid.UUID, owner_id: uuid.UUID) -> "tuple[DowntimeEpisode, DowntimeSources, list[D.Blocker]]":
        row = await self.get(project_id, episode_id, owner_id)
        sources = await load_downtime_sources(self.db, owner_id, project_id)
        return row, sources, self.blockers(row, data_of(row), sources)

    async def mark_noticed(
        self, project_id: uuid.UUID, episode_id: uuid.UUID, owner_id: uuid.UUID, *,
        issued_at: datetime, number: str, snapshot: dict[str, Any], document_html: str, contract_id: uuid.UUID | None, contract_version: int | None,
    ) -> DowntimeEpisode:
        """Freeze the notice: what was said, the exact page and the contract it was written under."""
        row = await self.get(project_id, episode_id, owner_id)
        if row.status != DowntimeStatus.DRAFT.value:
            raise DowntimeNotEditableError(f"episode {episode_id} is {row.status}: only a draft notice is issued")
        row.status = DowntimeStatus.NOTICED.value
        row.notice_issued_at, row.notice_number, row.notice_snapshot, row.notice_html = issued_at, number, snapshot, document_html
        row.contract_id, row.contract_version = contract_id, contract_version
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def mark_closed(
        self, project_id: uuid.UUID, episode_id: uuid.UUID, owner_id: uuid.UUID, *,
        issued_at: datetime, snapshot: dict[str, Any], document_html: str,
    ) -> DowntimeEpisode:
        """Freeze the protocol: the days, the sum for readiness, the people present and the exact page."""
        row = await self.get(project_id, episode_id, owner_id)
        if row.status != DowntimeStatus.NOTICED.value:
            raise DowntimeNotEditableError(f"episode {episode_id} is {row.status}: only a noticed episode gets its protocol")
        row.status = DowntimeStatus.CLOSED.value
        row.protocol_issued_at, row.protocol_snapshot, row.protocol_html = issued_at, snapshot, document_html
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def contract_snapshot(self, row: DowntimeEpisode, sources: DowntimeSources) -> dict[str, Any] | None:
        """The frozen conditions the sum for readiness follows: those of the contract the notice was written under, else of the latest
        issued or signed one."""
        contract = sources.base.contract
        if row.contract_id is not None and (contract is None or contract.id != row.contract_id):
            contract = await self.db.get(Contract, row.contract_id)
        return contract.snapshot if contract is not None else None

    async def read(self, row: DowntimeEpisode) -> DowntimeRead:
        data = data_of(row)
        sources = await load_downtime_sources(self.db, row.owner_id, row.project_id)
        contract = sources.base.contract
        s = D.settlement(data["days"], await self.contract_snapshot(row, sources))

        def photo(p) -> DowntimePhotoRead:
            return DowntimePhotoRead(id=p.id, caption=p.caption, captured_at=p.captured_at, room_name=p.room_name)

        return DowntimeRead(
            id=row.id, project_id=row.project_id, sequence=row.sequence, status=row.status, cause_key=row.cause_key, cause_text=cause_text(row.cause_key),
            cause_note=row.cause_note, room_ids=data["room_ids"], noticed_on=row.noticed_on, noticed_time=row.noticed_time, notice_channel=row.notice_channel,
            photo_ids=data["photo_ids"], need_text=row.need_text, need_by=row.need_by,
            days=[DowntimeDayRead(date=d["date"], weekday=date.fromisoformat(d["date"]).weekday(), other_work=bool(d.get("other_work")), note=d.get("note")) for d in data["days"]],
            held_on=row.held_on, held_time=row.held_time, attendees=data["attendees"], signature_refused=data["signature_refused"],
            deadline_note=row.deadline_note, notes=row.notes, notice_number=row.notice_number, notice_issued_at=row.notice_issued_at,
            protocol_issued_at=row.protocol_issued_at,
            photos=[photo(sources.photos[i]) for i in data["photo_ids"] if i in sources.photos],
            photo_options=[photo(p) for p in sources.allowed(data["room_ids"])] if row.status == DowntimeStatus.DRAFT.value else [],
            rooms=[DowntimeRoomRead(id=room_id, name=name) for room_id, name in sources.rooms],
            settlement=DowntimeSettlementRead(
                listed=s["listed"], chargeable=s["chargeable"], rate=_money(s["rate"]), amount=_money(s["amount"]), cap=_money(s["cap"]),
                capped=s["capped"], payable=_money(s["payable"]), limit_days=s["limit_days"], limit_exceeded=s["limit_exceeded"],
            ),
            blockers=[DowntimeBlockerRead(code=b.code, details=b.details) for b in self.blockers(row, data, sources)],
            contract=DowntimeContractRead(id=contract.id, version=contract.version, status=contract.status) if contract is not None else None,
            created_at=row.created_at, updated_at=row.updated_at,
        )
