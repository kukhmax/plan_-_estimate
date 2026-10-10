"""Protocols of concealed works of an object (Stage 16G): open the draft, record what was accepted, abandon the draft, freeze.

Every call is scoped to the owner's own project (`ProjectNotFoundError` otherwise). At most one draft exists per object (a partial
unique index). Only a draft may change; the people present are the active persons of the same object; the surface is a surface of
the object; the evidence is the photos of the category HIDDEN_WORK of that surface.
"""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.contracts.catalog import load_contract_catalog
from app.domain.exceptions import ConcealedNotEditableError, ConcealedNotFoundError, ProjectNotFoundError
from app.domain.protocols.concealed import (
    CLIENT_REQUIRED, CONTRACT_REQUIRED, EXECUTOR_PROFILE_REQUIRED, Blocker, apply_changes, empty_state, evaluate,
)
from app.domain.protocols.sources import ConcealedSources, load_concealed_sources
from app.models.concealed_works_protocol import ConcealedStatus, ConcealedWorksProtocol
from app.models.project import Project
from app.models.project_representative import ProjectRepresentative
from app.schemas.concealed import (
    ConcealedBlockerRead, ConcealedContractRead, ConcealedPhotoRead, ConcealedRead, ConcealedSurfaceRead,
)


def data_of(row: ConcealedWorksProtocol) -> dict[str, Any]:
    return {
        **empty_state(),
        "held_on": row.held_on, "held_time": row.held_time, "customer_absent": bool(row.customer_absent), "notified_on": row.notified_on,
        "attendees": list(row.attendees or []), "surface_id": str(row.surface_id) if row.surface_id else None, "work_kind": row.work_kind,
        "work_note": row.work_note, "material": row.material, "batch": row.batch, "photo_ids": list(row.photo_ids or []),
        "result": row.result, "remarks": row.remarks, "cover_consent": row.cover_consent,
    }


class ConcealedService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _ensure_project_owned(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        found = await self.db.execute(select(Project.id).where(Project.id == project_id, Project.owner_id == owner_id))
        if found.scalar_one_or_none() is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")

    async def _draft(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> ConcealedWorksProtocol | None:
        return (
            await self.db.execute(
                select(ConcealedWorksProtocol).where(
                    ConcealedWorksProtocol.project_id == project_id, ConcealedWorksProtocol.owner_id == owner_id,
                    ConcealedWorksProtocol.status == ConcealedStatus.DRAFT.value,
                )
            )
        ).scalar_one_or_none()

    async def get(self, project_id: uuid.UUID, protocol_id: uuid.UUID, owner_id: uuid.UUID) -> ConcealedWorksProtocol:
        await self._ensure_project_owned(project_id, owner_id)
        row = (
            await self.db.execute(
                select(ConcealedWorksProtocol).where(
                    ConcealedWorksProtocol.id == protocol_id, ConcealedWorksProtocol.project_id == project_id,
                    ConcealedWorksProtocol.owner_id == owner_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise ConcealedNotFoundError(f"Protocol {protocol_id} not found")
        return row

    async def list(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> "list[ConcealedWorksProtocol]":
        await self._ensure_project_owned(project_id, owner_id)
        return list(
            (
                await self.db.execute(
                    select(ConcealedWorksProtocol)
                    .where(ConcealedWorksProtocol.project_id == project_id, ConcealedWorksProtocol.owner_id == owner_id)
                    .order_by(ConcealedWorksProtocol.sequence.desc())
                )
            ).scalars()
        )

    async def open_draft(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> tuple[ConcealedWorksProtocol, bool]:
        """The draft of the object and whether it was just created. A second call returns the same draft."""
        await self._ensure_project_owned(project_id, owner_id)
        existing = await self._draft(project_id, owner_id)
        if existing is not None:
            return existing, False
        last = (
            await self.db.execute(
                select(ConcealedWorksProtocol.sequence)
                .where(ConcealedWorksProtocol.project_id == project_id).order_by(ConcealedWorksProtocol.sequence.desc()).limit(1)
            )
        ).scalar_one_or_none()
        row = ConcealedWorksProtocol(
            owner_id=owner_id, project_id=project_id, sequence=(last or 0) + 1, status=ConcealedStatus.DRAFT.value,
            customer_absent=False, attendees=[], photo_ids=[],
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

    async def update(self, project_id: uuid.UUID, protocol_id: uuid.UUID, owner_id: uuid.UUID, changes: dict[str, Any]) -> ConcealedWorksProtocol:
        row = await self.get(project_id, protocol_id, owner_id)
        if row.status != ConcealedStatus.DRAFT.value:
            raise ConcealedNotEditableError(f"protocol {protocol_id} is {row.status}: a changed protocol is a new one")
        sources = await load_concealed_sources(self.db, owner_id, project_id)
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
        state = apply_changes(
            data_of(row), changes,
            surface_ids={sid for sid, s in sources.surfaces.items() if not s.archived},
            photos_of=lambda sid: {p.id for p in sources.photos.get(sid, [])},
            people=people, catalog=load_contract_catalog(),
        )
        row.held_on, row.held_time, row.customer_absent, row.notified_on = state["held_on"], state["held_time"], state["customer_absent"], state["notified_on"]
        row.attendees = state["attendees"]
        row.surface_id = uuid.UUID(state["surface_id"]) if state["surface_id"] else None
        row.work_kind, row.work_note, row.material, row.batch = state["work_kind"], state["work_note"], state["material"], state["batch"]
        row.photo_ids, row.result, row.remarks, row.cover_consent = state["photo_ids"], state["result"], state["remarks"], state["cover_consent"]
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def archive_draft(self, project_id: uuid.UUID, protocol_id: uuid.UUID, owner_id: uuid.UUID) -> ConcealedWorksProtocol:
        row = await self.get(project_id, protocol_id, owner_id)
        if row.status != ConcealedStatus.DRAFT.value:
            raise ConcealedNotEditableError(f"protocol {protocol_id} is {row.status}: only a draft can be abandoned")
        row.status = ConcealedStatus.ARCHIVED.value
        await self.db.commit()
        await self.db.refresh(row)
        return row

    @staticmethod
    def blockers(data: dict[str, Any], sources: ConcealedSources) -> "list[Blocker]":
        """What stands between this protocol and its issue: the executor profile, the customer, a contract to work under, then the
        protocol's own entries."""
        blockers = []
        if sources.base.executor is None:
            blockers.append(Blocker(EXECUTOR_PROFILE_REQUIRED))
        if sources.base.client is None:
            blockers.append(Blocker(CLIENT_REQUIRED))
        if sources.base.contract is None:
            blockers.append(Blocker(CONTRACT_REQUIRED))
        return blockers + evaluate(data)

    async def gate(self, project_id: uuid.UUID, protocol_id: uuid.UUID, owner_id: uuid.UUID) -> "tuple[ConcealedWorksProtocol, ConcealedSources, list[Blocker]]":
        row = await self.get(project_id, protocol_id, owner_id)
        sources = await load_concealed_sources(self.db, owner_id, project_id)
        return row, sources, self.blockers(data_of(row), sources)

    async def mark_issued(
        self, project_id: uuid.UUID, protocol_id: uuid.UUID, owner_id: uuid.UUID, *,
        issued_at: datetime, snapshot: dict[str, Any], document_html: str, contract_id: uuid.UUID | None, contract_version: int | None,
    ) -> ConcealedWorksProtocol:
        """Freeze a draft: what was accepted, the exact page and the contract it was made under."""
        row = await self.get(project_id, protocol_id, owner_id)
        if row.status != ConcealedStatus.DRAFT.value:
            raise ConcealedNotEditableError(f"protocol {protocol_id} is {row.status}: only a draft is issued")
        row.status = ConcealedStatus.ISSUED.value
        row.issued_at, row.snapshot, row.document_html = issued_at, snapshot, document_html
        row.contract_id, row.contract_version = contract_id, contract_version
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def read(self, row: ConcealedWorksProtocol) -> ConcealedRead:
        data = data_of(row)
        sources = await load_concealed_sources(self.db, row.owner_id, row.project_id)
        surface = sources.surfaces.get(data["surface_id"]) if data["surface_id"] else None
        contract = sources.base.contract
        return ConcealedRead(
            id=row.id, project_id=row.project_id, sequence=row.sequence, status=row.status, held_on=row.held_on, held_time=row.held_time,
            customer_absent=data["customer_absent"], notified_on=row.notified_on, attendees=data["attendees"],
            surface=ConcealedSurfaceRead(id=surface.id, name=surface.name, room_id=surface.room_id, room_name=surface.room_name) if surface else None,
            work_kind=row.work_kind, work_note=row.work_note, material=row.material, batch=row.batch, photo_ids=data["photo_ids"],
            result=row.result, remarks=row.remarks, cover_consent=row.cover_consent,
            photo_options=[
                ConcealedPhotoRead(id=p.id, caption=p.caption, captured_at=p.captured_at)
                for p in (sources.photos.get(data["surface_id"], []) if data["surface_id"] else [])
            ],
            blockers=[ConcealedBlockerRead(code=b.code, details=b.details) for b in self.blockers(data, sources)],
            contract=ConcealedContractRead(id=contract.id, version=contract.version, status=contract.status) if contract else None,
            created_at=row.created_at, updated_at=row.updated_at,
        )
