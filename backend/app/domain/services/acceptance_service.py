"""Acceptance protocols of an object (Stage 16H.1): open the draft, record the assessment, abandon the draft, freeze.

Every call is scoped to the owner's own project (`ProjectNotFoundError` otherwise). At most one draft exists per object (a partial
unique index). Only a draft may change; the people present are the active persons of the object; the rooms and surfaces are the
object's own; a remark may point at the photos of defects of its surface. The **result is derived** (domain/protocols/acceptance.py)
and shown by the read model, never stored as typed.
"""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.contracts.catalog import load_contract_catalog
from app.domain.exceptions import AcceptanceNotEditableError, AcceptanceNotFoundError, ProjectNotFoundError
from app.domain.protocols import acceptance as A
from app.domain.protocols.sources import AcceptanceSources, load_acceptance_sources
from app.models.acceptance_protocol import AcceptanceProtocol, AcceptanceStatus
from app.models.project import Project
from app.models.project_representative import ProjectRepresentative
from app.schemas.acceptance import (
    AcceptanceBlockerRead, AcceptanceConditionRead, AcceptanceContractRead, AcceptancePhotoRead, AcceptanceRead, AcceptanceRemarkRead,
    AcceptanceRoomRead, AcceptanceSurfaceRead, AcceptanceWorkRead,
)


def data_of(row: AcceptanceProtocol) -> dict[str, Any]:
    return {
        **A.empty_state(),
        "held_on": row.held_on, "held_time": row.held_time, "customer_absent": bool(row.customer_absent), "notified_on": row.notified_on,
        "renotified_on": row.renotified_on, "attendees": list(row.attendees or []), "room_ids": list(row.room_ids or []),
        "conditions_note": row.conditions_note, "instrument_keys": list(row.instrument_keys or []), "surfaces": dict(row.surfaces or {}),
        "batches": row.batches, "instructions_given": bool(row.instructions_given), "amount_due": row.amount_due,
        "amount_retained": row.amount_retained, "notes": row.notes,
    }


class AcceptanceService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _ensure_project_owned(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        found = await self.db.execute(select(Project.id).where(Project.id == project_id, Project.owner_id == owner_id))
        if found.scalar_one_or_none() is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")

    async def _draft(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> AcceptanceProtocol | None:
        return (
            await self.db.execute(
                select(AcceptanceProtocol).where(
                    AcceptanceProtocol.project_id == project_id, AcceptanceProtocol.owner_id == owner_id,
                    AcceptanceProtocol.status == AcceptanceStatus.DRAFT.value,
                )
            )
        ).scalar_one_or_none()

    async def get(self, project_id: uuid.UUID, protocol_id: uuid.UUID, owner_id: uuid.UUID) -> AcceptanceProtocol:
        await self._ensure_project_owned(project_id, owner_id)
        row = (
            await self.db.execute(
                select(AcceptanceProtocol).where(
                    AcceptanceProtocol.id == protocol_id, AcceptanceProtocol.project_id == project_id, AcceptanceProtocol.owner_id == owner_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise AcceptanceNotFoundError(f"Protocol {protocol_id} not found")
        return row

    async def list(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> "list[AcceptanceProtocol]":
        await self._ensure_project_owned(project_id, owner_id)
        return list(
            (
                await self.db.execute(
                    select(AcceptanceProtocol)
                    .where(AcceptanceProtocol.project_id == project_id, AcceptanceProtocol.owner_id == owner_id)
                    .order_by(AcceptanceProtocol.sequence.desc())
                )
            ).scalars()
        )

    async def open_draft(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> tuple[AcceptanceProtocol, bool]:
        """The draft of the object and whether it was just created. A second call returns the same draft."""
        await self._ensure_project_owned(project_id, owner_id)
        existing = await self._draft(project_id, owner_id)
        if existing is not None:
            return existing, False
        last = (
            await self.db.execute(
                select(AcceptanceProtocol.sequence).where(AcceptanceProtocol.project_id == project_id).order_by(AcceptanceProtocol.sequence.desc()).limit(1)
            )
        ).scalar_one_or_none()
        row = AcceptanceProtocol(
            owner_id=owner_id, project_id=project_id, sequence=(last or 0) + 1, status=AcceptanceStatus.DRAFT.value,
            customer_absent=False, attendees=[], room_ids=[], instrument_keys=[], surfaces={}, instructions_given=False,
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

    async def update(self, project_id: uuid.UUID, protocol_id: uuid.UUID, owner_id: uuid.UUID, changes: dict[str, Any]) -> AcceptanceProtocol:
        row = await self.get(project_id, protocol_id, owner_id)
        if row.status != AcceptanceStatus.DRAFT.value:
            raise AcceptanceNotEditableError(f"protocol {protocol_id} is {row.status}: a changed protocol is a new one")
        sources = await load_acceptance_sources(self.db, owner_id, project_id)
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
        state = A.apply_changes(
            data_of(row), changes,
            room_ids={r[0] for r in sources.rooms}, surface_ids={sid for sid, f in sources.facts.items() if f.works},
            defect_photos_of=lambda sid: {p.id for p in sources.defect_photos.get(sid, [])},
            people=people, catalog=load_contract_catalog(),
        )
        row.held_on, row.held_time, row.customer_absent = state["held_on"], state["held_time"], state["customer_absent"]
        row.notified_on, row.renotified_on, row.attendees = state["notified_on"], state["renotified_on"], state["attendees"]
        row.room_ids, row.conditions_note, row.instrument_keys = state["room_ids"], state["conditions_note"], state["instrument_keys"]
        row.surfaces, row.batches, row.instructions_given = state["surfaces"], state["batches"], state["instructions_given"]
        row.amount_due, row.amount_retained, row.notes = state["amount_due"], state["amount_retained"], state["notes"]
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def archive_draft(self, project_id: uuid.UUID, protocol_id: uuid.UUID, owner_id: uuid.UUID) -> AcceptanceProtocol:
        row = await self.get(project_id, protocol_id, owner_id)
        if row.status != AcceptanceStatus.DRAFT.value:
            raise AcceptanceNotEditableError(f"protocol {protocol_id} is {row.status}: only a draft can be abandoned")
        row.status = AcceptanceStatus.ARCHIVED.value
        await self.db.commit()
        await self.db.refresh(row)
        return row

    @staticmethod
    def blockers(data: dict[str, Any], sources: AcceptanceSources) -> "list[A.Blocker]":
        """What stands between this protocol and its issue: the executor profile, the customer, a contract to work under, then the
        protocol's own entries."""
        blockers = []
        if sources.base.executor is None:
            blockers.append(A.Blocker(A.EXECUTOR_PROFILE_REQUIRED))
        if sources.base.client is None:
            blockers.append(A.Blocker(A.CLIENT_REQUIRED))
        if sources.base.contract is None:
            blockers.append(A.Blocker(A.CONTRACT_REQUIRED))
        return blockers + A.evaluate(data, sources.facts, load_contract_catalog())

    async def gate(self, project_id: uuid.UUID, protocol_id: uuid.UUID, owner_id: uuid.UUID) -> "tuple[AcceptanceProtocol, AcceptanceSources, list[A.Blocker]]":
        row = await self.get(project_id, protocol_id, owner_id)
        sources = await load_acceptance_sources(self.db, owner_id, project_id)
        return row, sources, self.blockers(data_of(row), sources)

    async def mark_issued(
        self, project_id: uuid.UUID, protocol_id: uuid.UUID, owner_id: uuid.UUID, *,
        issued_at: datetime, snapshot: dict[str, Any], document_html: str, contract_id: uuid.UUID | None, contract_version: int | None,
    ) -> AcceptanceProtocol:
        """Freeze a draft: the assessment, the exact page and the contract it was made under."""
        row = await self.get(project_id, protocol_id, owner_id)
        if row.status != AcceptanceStatus.DRAFT.value:
            raise AcceptanceNotEditableError(f"protocol {protocol_id} is {row.status}: only a draft is issued")
        row.status = AcceptanceStatus.ISSUED.value
        row.issued_at, row.snapshot, row.document_html = issued_at, snapshot, document_html
        row.contract_id, row.contract_version = contract_id, contract_version
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def read(self, row: AcceptanceProtocol) -> AcceptanceRead:
        data = data_of(row)
        catalog = load_contract_catalog()
        sources = await load_acceptance_sources(self.db, row.owner_id, row.project_id)
        scope = A.surfaces_in_scope(data, sources.facts)
        views = []
        for facts in scope:
            entry = data["surfaces"].get(facts.id) or {}
            views.append(AcceptanceSurfaceRead(
                id=facts.id, name=facts.name, surface_type=facts.surface_type, room_id=facts.room_id, room_name=facts.room_name,
                quality_target=facts.quality_target, works=[AcceptanceWorkRead(name=w.name, status=w.status) for w in facts.works],
                incomplete=len(facts.incomplete), assessed=bool(entry.get("assessed")),
                remarks=[
                    AcceptanceRemarkRead(id=rid, place=r["place"], description=r["description"], classification=r["classification"],
                                         deadline=r.get("deadline"), photo_ids=list(r.get("photo_ids") or []))
                    for rid, r in (entry.get("remarks") or {}).items()
                ],
                result=A.surface_result(facts, entry),
                photo_options=[AcceptancePhotoRead(id=p.id, caption=p.caption, captured_at=p.captured_at) for p in sources.defect_photos.get(facts.id, [])],
            ))
        contract = sources.base.contract
        return AcceptanceRead(
            id=row.id, project_id=row.project_id, sequence=row.sequence, status=row.status, held_on=row.held_on, held_time=row.held_time,
            customer_absent=data["customer_absent"], notified_on=row.notified_on, renotified_on=row.renotified_on, attendees=data["attendees"],
            room_ids=data["room_ids"], conditions_note=row.conditions_note, instrument_keys=data["instrument_keys"], batches=row.batches,
            instructions_given=data["instructions_given"], amount_due=row.amount_due, amount_retained=row.amount_retained, notes=row.notes,
            scope_kind=A.scope_kind(data, sources.facts), result=A.overall_result([v.result for v in views]),
            rooms=[AcceptanceRoomRead(id=r[0], name=r[1], surfaces=r[2]) for r in sources.rooms],
            surfaces=views,
            conditions=[AcceptanceConditionRead(**c) for c in A.conditions(data, sources.facts, catalog)],
            blockers=[AcceptanceBlockerRead(code=b.code, details=b.details) for b in self.blockers(data, sources)],
            contract=AcceptanceContractRead(id=contract.id, version=contract.version, status=contract.status) if contract else None,
            created_at=row.created_at, updated_at=row.updated_at,
        )
