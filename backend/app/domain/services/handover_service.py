"""Handover protocols of an object (Stage 16F.1): open the draft, record what was found, abandon the draft.

Every call is scoped to the owner's own project (`ProjectNotFoundError` otherwise). At most one draft exists per object (a partial
unique index). Only a draft may change; the people present are the active persons of the same object; the rooms are the rooms of
the object. The requirements to meet are those of the latest issued or signed contract (its frozen answers), shown beside the
findings; the protocol never invents a number.
"""
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.contracts.catalog import load_contract_catalog
from app.domain.exceptions import HandoverNotEditableError, HandoverNotFoundError, ProjectNotFoundError
from app.domain.protocols.handover import apply_changes, evaluate, suggested_decision
from app.models.contract import Contract, ContractStatus
from app.models.handover_protocol import HandoverProtocol, HandoverStatus
from app.models.project import Project
from app.models.project_representative import ProjectRepresentative
from app.models.room import Room
from app.schemas.handover import HandoverBlockerRead, HandoverContractRead, HandoverRead


def _data(row: HandoverProtocol) -> dict[str, Any]:
    return {
        "held_on": row.held_on, "held_time": row.held_time, "attendees": list(row.attendees or []),
        "rooms": dict(row.rooms or {}), "meters": row.meters, "notes": row.notes,
    }


class HandoverService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _ensure_project_owned(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        found = await self.db.execute(select(Project.id).where(Project.id == project_id, Project.owner_id == owner_id))
        if found.scalar_one_or_none() is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")

    async def _draft(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> HandoverProtocol | None:
        return (
            await self.db.execute(
                select(HandoverProtocol).where(
                    HandoverProtocol.project_id == project_id, HandoverProtocol.owner_id == owner_id,
                    HandoverProtocol.status == HandoverStatus.DRAFT.value,
                )
            )
        ).scalar_one_or_none()

    async def get(self, project_id: uuid.UUID, handover_id: uuid.UUID, owner_id: uuid.UUID) -> HandoverProtocol:
        await self._ensure_project_owned(project_id, owner_id)
        row = (
            await self.db.execute(
                select(HandoverProtocol).where(
                    HandoverProtocol.id == handover_id, HandoverProtocol.project_id == project_id, HandoverProtocol.owner_id == owner_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise HandoverNotFoundError(f"Handover protocol {handover_id} not found")
        return row

    async def list(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> "list[HandoverProtocol]":
        await self._ensure_project_owned(project_id, owner_id)
        return list(
            (
                await self.db.execute(
                    select(HandoverProtocol)
                    .where(HandoverProtocol.project_id == project_id, HandoverProtocol.owner_id == owner_id)
                    .order_by(HandoverProtocol.sequence.desc())
                )
            ).scalars()
        )

    async def open_draft(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> tuple[HandoverProtocol, bool]:
        """The draft of the object and whether it was just created. A second call returns the same draft."""
        await self._ensure_project_owned(project_id, owner_id)
        existing = await self._draft(project_id, owner_id)
        if existing is not None:
            return existing, False
        last = (
            await self.db.execute(
                select(HandoverProtocol.sequence)
                .where(HandoverProtocol.project_id == project_id).order_by(HandoverProtocol.sequence.desc()).limit(1)
            )
        ).scalar_one_or_none()
        row = HandoverProtocol(
            owner_id=owner_id, project_id=project_id, sequence=(last or 0) + 1, status=HandoverStatus.DRAFT.value,
            attendees=[], rooms={},
        )
        self.db.add(row)
        try:
            await self.db.commit()
        except IntegrityError:  # two requests opened the draft at the same moment: take the one that won
            await self.db.rollback()
            existing = await self._draft(project_id, owner_id)
            if existing is None:
                raise
            return existing, False
        await self.db.refresh(row)
        return row, True

    async def update(self, project_id: uuid.UUID, handover_id: uuid.UUID, owner_id: uuid.UUID, changes: dict[str, Any]) -> HandoverProtocol:
        row = await self.get(project_id, handover_id, owner_id)
        if row.status != HandoverStatus.DRAFT.value:
            raise HandoverNotEditableError(f"handover protocol {handover_id} is {row.status}: a changed protocol is a new one")
        room_ids = {str(r) for r in (await self.db.execute(select(Room.id).where(Room.project_id == project_id))).scalars()}
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
        state = apply_changes(_data(row), changes, room_ids=room_ids, people=people, catalog=load_contract_catalog())
        row.held_on, row.held_time = state.get("held_on"), state.get("held_time")
        row.attendees, row.rooms = state["attendees"], state["rooms"]
        row.meters, row.notes = state.get("meters"), state.get("notes")
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def archive_draft(self, project_id: uuid.UUID, handover_id: uuid.UUID, owner_id: uuid.UUID) -> HandoverProtocol:
        row = await self.get(project_id, handover_id, owner_id)
        if row.status != HandoverStatus.DRAFT.value:
            raise HandoverNotEditableError(f"handover protocol {handover_id} is {row.status}: only a draft can be abandoned")
        row.status = HandoverStatus.ARCHIVED.value
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def reference_contract(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> Contract | None:
        """The contract whose requirements apply: the latest issued or signed one."""
        return (
            await self.db.execute(
                select(Contract)
                .where(
                    Contract.project_id == project_id, Contract.owner_id == owner_id,
                    Contract.status.in_([ContractStatus.ISSUED.value, ContractStatus.SIGNED.value]),
                )
                .order_by(Contract.version.desc()).limit(1)
            )
        ).scalar_one_or_none()

    async def read(self, row: HandoverProtocol) -> HandoverRead:
        catalog = load_contract_catalog()
        data = _data(row)
        contract = await self.reference_contract(row.project_id, row.owner_id)
        required = ((contract.snapshot or {}).get("answers") or {}).get("premises_requirement_values") or {} if contract else {}
        return HandoverRead(
            id=row.id, project_id=row.project_id, sequence=row.sequence, status=row.status, held_on=row.held_on, held_time=row.held_time,
            attendees=data["attendees"], rooms=data["rooms"], meters=row.meters, notes=row.notes,
            suggested={rid: suggested_decision(room.get("requirements") or {}, catalog) for rid, room in data["rooms"].items()},
            blockers=[HandoverBlockerRead(code=b.code, details=b.details) for b in evaluate(data, catalog)],
            contract=HandoverContractRead(id=contract.id, version=contract.version, status=contract.status) if contract else None,
            required_values=required, created_at=row.created_at, updated_at=row.updated_at,
        )
