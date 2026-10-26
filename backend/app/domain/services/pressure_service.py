"""Protocols of a pressure test of an object (V2-12b): open the draft, record the test, abandon the draft, freeze.

The same shape as the protocols of concealed works: every call is scoped to the owner's own project (`ProjectNotFoundError` otherwise); at most one draft exists per object (a
partial unique index); only a draft may change; the people present are the active persons of the same object; the evidence is a photo of the object that is not archived.
"""
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import PressureNotEditableError, PressureNotFoundError, ProjectNotFoundError
from app.domain.protocols.pressure import (
    CLIENT_REQUIRED, EXECUTOR_PROFILE_REQUIRED, Blocker, apply_changes, empty_state, evaluate,
)
from app.domain.protocols.sources import PressureSources, load_pressure_sources
from app.models.pressure_test_protocol import PressureStatus, PressureTestProtocol
from app.models.project import Project
from app.models.project_representative import ProjectRepresentative
from app.schemas.pressure import PressureBlockerRead, PressurePhotoRead, PressureRead


def data_of(row: PressureTestProtocol) -> dict[str, Any]:
    return {
        **empty_state(),
        "held_on": row.held_on, "held_time": row.held_time, "customer_absent": bool(row.customer_absent), "notified_on": row.notified_on,
        "attendees": list(row.attendees or []), "system": row.system, "section": row.section, "medium": row.medium,
        "test_pressure_bar": row.test_pressure_bar, "duration_min": row.duration_min, "pressure_drop_bar": row.pressure_drop_bar,
        "photo_ids": list(row.photo_ids or []), "result": row.result, "remarks": row.remarks,
    }


class PressureService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _ensure_project_owned(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        found = await self.db.execute(select(Project.id).where(Project.id == project_id, Project.owner_id == owner_id))
        if found.scalar_one_or_none() is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")

    async def _draft(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> PressureTestProtocol | None:
        return (
            await self.db.execute(
                select(PressureTestProtocol).where(
                    PressureTestProtocol.project_id == project_id, PressureTestProtocol.owner_id == owner_id,
                    PressureTestProtocol.status == PressureStatus.DRAFT.value,
                )
            )
        ).scalar_one_or_none()

    async def get(self, project_id: uuid.UUID, protocol_id: uuid.UUID, owner_id: uuid.UUID) -> PressureTestProtocol:
        await self._ensure_project_owned(project_id, owner_id)
        row = (
            await self.db.execute(
                select(PressureTestProtocol).where(
                    PressureTestProtocol.id == protocol_id, PressureTestProtocol.project_id == project_id, PressureTestProtocol.owner_id == owner_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise PressureNotFoundError(f"Protocol {protocol_id} not found")
        return row

    async def list(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> "list[PressureTestProtocol]":
        """The drafts and the issued protocols of the object, newest first (an abandoned draft is not listed)."""
        await self._ensure_project_owned(project_id, owner_id)
        return list(
            (
                await self.db.execute(
                    select(PressureTestProtocol)
                    .where(
                        PressureTestProtocol.project_id == project_id, PressureTestProtocol.owner_id == owner_id,
                        PressureTestProtocol.status != PressureStatus.ARCHIVED.value,
                    )
                    .order_by(PressureTestProtocol.sequence.desc())
                )
            ).scalars()
        )

    async def open_draft(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> tuple[PressureTestProtocol, bool]:
        """The draft of the object and whether it was just created. A second call returns the same draft."""
        await self._ensure_project_owned(project_id, owner_id)
        existing = await self._draft(project_id, owner_id)
        if existing is not None:
            return existing, False
        last = (
            await self.db.execute(
                select(PressureTestProtocol.sequence).where(PressureTestProtocol.project_id == project_id).order_by(PressureTestProtocol.sequence.desc()).limit(1)
            )
        ).scalar_one_or_none()
        row = PressureTestProtocol(
            owner_id=owner_id, project_id=project_id, sequence=(last or 0) + 1, status=PressureStatus.DRAFT.value,
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

    async def update(self, project_id: uuid.UUID, protocol_id: uuid.UUID, owner_id: uuid.UUID, changes: dict[str, Any]) -> PressureTestProtocol:
        row = await self.get(project_id, protocol_id, owner_id)
        if row.status != PressureStatus.DRAFT.value:
            raise PressureNotEditableError(f"protocol {protocol_id} is {row.status}: a changed protocol is a new one")
        sources = await load_pressure_sources(self.db, owner_id, project_id)
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
        state = apply_changes(data_of(row), changes, photo_ids=set(sources.photos), people=people)
        row.held_on, row.held_time, row.customer_absent, row.notified_on = state["held_on"], state["held_time"], state["customer_absent"], state["notified_on"]
        row.attendees = state["attendees"]
        row.system, row.section, row.medium = state["system"], state["section"], state["medium"]
        row.test_pressure_bar, row.duration_min, row.pressure_drop_bar = state["test_pressure_bar"], state["duration_min"], state["pressure_drop_bar"]
        row.photo_ids, row.result, row.remarks = state["photo_ids"], state["result"], state["remarks"]
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def archive_draft(self, project_id: uuid.UUID, protocol_id: uuid.UUID, owner_id: uuid.UUID) -> PressureTestProtocol:
        row = await self.get(project_id, protocol_id, owner_id)
        if row.status != PressureStatus.DRAFT.value:
            raise PressureNotEditableError(f"protocol {protocol_id} is {row.status}: only a draft can be abandoned")
        row.status = PressureStatus.ARCHIVED.value
        await self.db.commit()
        await self.db.refresh(row)
        return row

    @staticmethod
    def blockers(data: dict[str, Any], sources: PressureSources) -> "list[Blocker]":
        """What stands between this protocol and its issue: the executor profile and the customer (the signature lines), then the protocol's own entries."""
        blockers = []
        if sources.base.executor is None:
            blockers.append(Blocker(EXECUTOR_PROFILE_REQUIRED))
        if sources.base.client is None:
            blockers.append(Blocker(CLIENT_REQUIRED))
        return blockers + evaluate(data)

    async def gate(self, project_id: uuid.UUID, protocol_id: uuid.UUID, owner_id: uuid.UUID) -> "tuple[PressureTestProtocol, PressureSources, list[Blocker]]":
        row = await self.get(project_id, protocol_id, owner_id)
        sources = await load_pressure_sources(self.db, owner_id, project_id)
        return row, sources, self.blockers(data_of(row), sources)

    async def mark_issued(
        self, project_id: uuid.UUID, protocol_id: uuid.UUID, owner_id: uuid.UUID, *, issued_at: datetime, snapshot: dict[str, Any], document_html: str,
    ) -> PressureTestProtocol:
        """Freeze a draft: what was tested and the exact page."""
        row = await self.get(project_id, protocol_id, owner_id)
        if row.status != PressureStatus.DRAFT.value:
            raise PressureNotEditableError(f"protocol {protocol_id} is {row.status}: only a draft is issued")
        row.status = PressureStatus.ISSUED.value
        row.issued_at, row.snapshot, row.document_html = issued_at, snapshot, document_html
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def read(self, row: PressureTestProtocol) -> PressureRead:
        data = data_of(row)
        sources = await load_pressure_sources(self.db, row.owner_id, row.project_id)
        return PressureRead(
            id=row.id, project_id=row.project_id, sequence=row.sequence, status=row.status, held_on=row.held_on, held_time=row.held_time,
            customer_absent=data["customer_absent"], notified_on=row.notified_on, attendees=data["attendees"], system=row.system, section=row.section,
            medium=row.medium, test_pressure_bar=row.test_pressure_bar, duration_min=row.duration_min, pressure_drop_bar=row.pressure_drop_bar,
            photo_ids=data["photo_ids"], result=row.result, remarks=row.remarks,
            photo_options=[PressurePhotoRead(id=p.id, caption=p.caption, place=p.place, captured_at=p.captured_at, created_at=p.created_at) for p in sources.photos.values()],
            blockers=[PressureBlockerRead(code=b.code, details=b.details) for b in self.blockers(data, sources)],
            created_at=row.created_at, updated_at=row.updated_at,
        )
