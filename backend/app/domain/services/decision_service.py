"""Protocols of information and decisions of an object (Stage 16I.1): open the draft, record the items and the decisions, abandon the
draft, freeze.

Every call is scoped to the owner's own project (`ProjectNotFoundError` otherwise). At most one draft exists per object (a partial unique
index). Only a draft may change; the people present are the active persons of the object; a risk may be put into an item only while it is
an active candidate of the object; the texts of a risk item are the built-in risk catalogue's (Polish), never the owner's.
"""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.documents.catalog import localize_risk_text
from app.domain.exceptions import DecisionNotEditableError, DecisionNotFoundError, ProjectNotFoundError
from app.domain.protocols import decision as D
from app.domain.protocols.sources import DecisionSources, load_decision_sources
from app.models.decision_protocol import DecisionProtocol, DecisionStatus
from app.models.project import Project
from app.models.project_representative import ProjectRepresentative
from app.schemas.decision import (
    DecisionBlockerRead, DecisionContractRead, DecisionItemRead, DecisionRead, DecisionRiskOptionRead, DecisionRoomRead,
)


def data_of(row: DecisionProtocol) -> dict[str, Any]:
    return {
        **D.empty_state(),
        "held_on": row.held_on, "held_time": row.held_time, "attendees": list(row.attendees or []), "items": [dict(i) for i in row.items or []],
        "understood": bool(row.understood), "signature_refused": bool(row.signature_refused), "notes": row.notes,
    }


def item_texts(item: dict[str, Any], sources: DecisionSources) -> dict[str, Any]:
    """What an item says, as printed and shown: a risk item speaks with the catalogue's Polish texts, an own item with the owner's."""
    risk = sources.risks.get(item.get("risk_id") or "") if item.get("source") == "RISK" else None
    if risk is not None:
        return {
            "room_id": risk.room_id, "room_name": risk.room_name, "severity": risk.severity, "blocks_finishing": risk.blocks_finishing,
            "title": localize_risk_text(risk.title_key), "state": localize_risk_text(risk.explanation_key),
            "recommendation": localize_risk_text(risk.communication_key), "consequence": localize_risk_text(risk.consequence_key), "price": None,
            "risk_active": True,
        }
    room_name = dict(sources.rooms).get(item.get("room_id") or "")
    return {
        "room_id": item.get("room_id"), "room_name": room_name, "severity": None, "blocks_finishing": False, "title": item.get("title") or "",
        "state": None, "recommendation": item.get("recommendation") or "", "consequence": item.get("consequence") or "", "price": item.get("price"),
        "risk_active": item.get("source") != "RISK",
    }


class DecisionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _ensure_project_owned(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        found = await self.db.execute(select(Project.id).where(Project.id == project_id, Project.owner_id == owner_id))
        if found.scalar_one_or_none() is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")

    async def _draft(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> DecisionProtocol | None:
        return (
            await self.db.execute(
                select(DecisionProtocol).where(
                    DecisionProtocol.project_id == project_id, DecisionProtocol.owner_id == owner_id,
                    DecisionProtocol.status == DecisionStatus.DRAFT.value,
                )
            )
        ).scalar_one_or_none()

    async def get(self, project_id: uuid.UUID, protocol_id: uuid.UUID, owner_id: uuid.UUID) -> DecisionProtocol:
        await self._ensure_project_owned(project_id, owner_id)
        row = (
            await self.db.execute(
                select(DecisionProtocol).where(
                    DecisionProtocol.id == protocol_id, DecisionProtocol.project_id == project_id, DecisionProtocol.owner_id == owner_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise DecisionNotFoundError(f"Protocol {protocol_id} not found")
        return row

    async def list(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> "list[DecisionProtocol]":
        await self._ensure_project_owned(project_id, owner_id)
        return list(
            (
                await self.db.execute(
                    select(DecisionProtocol)
                    .where(DecisionProtocol.project_id == project_id, DecisionProtocol.owner_id == owner_id)
                    .order_by(DecisionProtocol.sequence.desc())
                )
            ).scalars()
        )

    async def open_draft(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> tuple[DecisionProtocol, bool]:
        """The draft of the object and whether it was just created. A second call returns the same draft."""
        await self._ensure_project_owned(project_id, owner_id)
        existing = await self._draft(project_id, owner_id)
        if existing is not None:
            return existing, False
        last = (
            await self.db.execute(
                select(DecisionProtocol.sequence).where(DecisionProtocol.project_id == project_id).order_by(DecisionProtocol.sequence.desc()).limit(1)
            )
        ).scalar_one_or_none()
        row = DecisionProtocol(
            owner_id=owner_id, project_id=project_id, sequence=(last or 0) + 1, status=DecisionStatus.DRAFT.value,
            attendees=[], items=[], understood=False, signature_refused=False,
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

    async def update(self, project_id: uuid.UUID, protocol_id: uuid.UUID, owner_id: uuid.UUID, changes: dict[str, Any]) -> DecisionProtocol:
        row = await self.get(project_id, protocol_id, owner_id)
        if row.status != DecisionStatus.DRAFT.value:
            raise DecisionNotEditableError(f"protocol {protocol_id} is {row.status}: a changed protocol is a new one")
        sources = await load_decision_sources(self.db, owner_id, project_id)
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
        state = D.apply_changes(data_of(row), changes, risks=sources.risks, room_ids={r[0] for r in sources.rooms}, people=people)
        row.held_on, row.held_time, row.attendees, row.items = state["held_on"], state["held_time"], state["attendees"], state["items"]
        row.understood, row.signature_refused, row.notes = state["understood"], state["signature_refused"], state["notes"]
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def archive_draft(self, project_id: uuid.UUID, protocol_id: uuid.UUID, owner_id: uuid.UUID) -> DecisionProtocol:
        row = await self.get(project_id, protocol_id, owner_id)
        if row.status != DecisionStatus.DRAFT.value:
            raise DecisionNotEditableError(f"protocol {protocol_id} is {row.status}: only a draft can be abandoned")
        row.status = DecisionStatus.ARCHIVED.value
        await self.db.commit()
        await self.db.refresh(row)
        return row

    @staticmethod
    def blockers(data: dict[str, Any], sources: DecisionSources) -> "list[D.Blocker]":
        """What stands between this protocol and its issue: the executor profile, the customer, a contract to work under, then the
        protocol's own entries."""
        blockers = []
        if sources.base.executor is None:
            blockers.append(D.Blocker(D.EXECUTOR_PROFILE_REQUIRED))
        if sources.base.client is None:
            blockers.append(D.Blocker(D.CLIENT_REQUIRED))
        if sources.base.contract is None:
            blockers.append(D.Blocker(D.CONTRACT_REQUIRED))
        return blockers + D.evaluate(data, sources.risks)

    async def gate(self, project_id: uuid.UUID, protocol_id: uuid.UUID, owner_id: uuid.UUID) -> "tuple[DecisionProtocol, DecisionSources, list[D.Blocker]]":
        row = await self.get(project_id, protocol_id, owner_id)
        sources = await load_decision_sources(self.db, owner_id, project_id)
        return row, sources, self.blockers(data_of(row), sources)

    async def mark_issued(
        self, project_id: uuid.UUID, protocol_id: uuid.UUID, owner_id: uuid.UUID, *,
        issued_at: datetime, snapshot: dict[str, Any], document_html: str, contract_id: uuid.UUID | None, contract_version: int | None,
    ) -> DecisionProtocol:
        """Freeze a draft: the items with their decisions, the exact page and the contract."""
        row = await self.get(project_id, protocol_id, owner_id)
        if row.status != DecisionStatus.DRAFT.value:
            raise DecisionNotEditableError(f"protocol {protocol_id} is {row.status}: only a draft is issued")
        row.status = DecisionStatus.ISSUED.value
        row.issued_at, row.snapshot, row.document_html = issued_at, snapshot, document_html
        row.contract_id, row.contract_version = contract_id, contract_version
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def read(self, row: DecisionProtocol) -> DecisionRead:
        data = data_of(row)
        sources = await load_decision_sources(self.db, row.owner_id, row.project_id)
        used = {i.get("risk_id") for i in data["items"] if i.get("source") == "RISK"}
        contract = sources.base.contract
        return DecisionRead(
            id=row.id, project_id=row.project_id, sequence=row.sequence, status=row.status, held_on=row.held_on, held_time=row.held_time,
            attendees=data["attendees"], understood=data["understood"], signature_refused=data["signature_refused"], notes=row.notes,
            items=[
                DecisionItemRead(
                    id=i["id"], source=i["source"], risk_id=i.get("risk_id"), decision=i.get("decision"), executor_action=i.get("executor_action"),
                    order_ref=i.get("order_ref"), note=i.get("note"), **item_texts(i, sources),
                )
                for i in data["items"]
            ],
            risk_options=[
                DecisionRiskOptionRead(
                    id=r.id, room_id=r.room_id, room_name=r.room_name, severity=r.severity, blocks_finishing=r.blocks_finishing,
                    title=localize_risk_text(r.title_key), consequence=localize_risk_text(r.consequence_key), used=r.id in used,
                )
                for r in sources.risks.values()
            ],
            rooms=[DecisionRoomRead(id=room_id, name=name) for room_id, name in sources.rooms],
            blockers=[DecisionBlockerRead(code=b.code, details=b.details) for b in self.blockers(data, sources)],
            contract=DecisionContractRead(id=contract.id, version=contract.version, status=contract.status) if contract is not None else None,
            created_at=row.created_at, updated_at=row.updated_at,
        )
