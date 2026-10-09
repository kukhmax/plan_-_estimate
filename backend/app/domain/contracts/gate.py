"""The gate of the contract (Stage 16E.2): what must be true before a contract is issued, checked deterministically.

The chain "technological card -> production plan -> estimate -> contract" is only as good as its data, so a contract is refused
(with the list of what to fix, never a vague error) while any of these holds:

* the executor profile is not filled in;
* the object has no client, or the client has no address (street, postal code, city -- 16B.1);
* a REQUIRED answer of the questionnaire is missing, or a person chosen to accept the work has since been archived or lost the
  authority to accept and sign;
* no surface has planned works, or a surface with works lacks its agreed standard or a finished inspection (the same rule as the
  numbered technological card, which is an annex of the contract);
* the object has no estimate, or its current estimate is not FINAL (the price of the contract is that estimate's, without VAT).

The annexes (technological card, production plan, requirements for the premises, regulation of acceptance) are part of the same
issue, so they need no separate issuing; they are built from the same data that the gate has just checked.
"""

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.contracts.answers import missing_required
from app.domain.contracts.catalog import load_contract_catalog
from app.domain.documents.production_plan_document import load_adjacent_works
from app.domain.documents.tech_card_document import RoomSource, TechCardDocumentService, missing_for_issue
from app.domain.services.executor_profile_service import ExecutorProfileService
from app.models.adjacent_work import AdjacentWork
from app.models.client import Client
from app.models.estimate import Estimate, EstimateStatus
from app.models.executor_profile import ExecutorProfile
from app.models.project import Project
from app.models.project_representative import ProjectRepresentative

EXECUTOR_PROFILE_REQUIRED = "EXECUTOR_PROFILE_REQUIRED"
CLIENT_REQUIRED = "CLIENT_REQUIRED"
CLIENT_ADDRESS_INCOMPLETE = "CLIENT_ADDRESS_INCOMPLETE"
ANSWERS_MISSING = "ANSWERS_MISSING"
PERSON_NOT_AUTHORISED = "PERSON_NOT_AUTHORISED"
NO_PLANNED_WORKS = "NO_PLANNED_WORKS"
SURFACE_INCOMPLETE = "SURFACE_INCOMPLETE"
ESTIMATE_REQUIRED = "ESTIMATE_REQUIRED"
ESTIMATE_NOT_FINAL = "ESTIMATE_NOT_FINAL"


@dataclass(frozen=True, slots=True)
class Blocker:
    code: str
    details: dict[str, Any] | None = None


@dataclass(slots=True)
class GateData:
    """Everything the gate looks at, loaded once; the document is built from the same data."""

    project: Project
    client: Client | None
    executor: ExecutorProfile | None
    rooms: tuple[RoomSource, ...]
    adjacent: tuple[AdjacentWork, ...]
    people: list[ProjectRepresentative]
    estimate: Estimate | None
    blockers: list[Blocker] = field(default_factory=list)


async def load_gate_data(db: AsyncSession, owner_id: uuid.UUID, project_id: uuid.UUID) -> GateData:
    """Raises ProjectNotFoundError for a project that is not this owner's (nothing else is read then)."""
    project, client, rooms = await TechCardDocumentService(db).sources(owner_id, project_id)
    executor = await ExecutorProfileService(db).get(owner_id)
    adjacent = await load_adjacent_works(db, owner_id, project_id)
    people = list(
        (
            await db.execute(
                select(ProjectRepresentative)
                .where(
                    ProjectRepresentative.project_id == project_id,
                    ProjectRepresentative.owner_id == owner_id,
                    ProjectRepresentative.is_archived.is_(False),
                )
                .order_by(ProjectRepresentative.created_at, ProjectRepresentative.id)
            )
        ).scalars()
    )
    estimate = (
        await db.execute(
            select(Estimate)
            .where(Estimate.project_id == project_id, Estimate.owner_id == owner_id, Estimate.status != EstimateStatus.ARCHIVED)
            .order_by(Estimate.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return GateData(project, client, executor, rooms, adjacent, people, estimate)


def evaluate_gate(answers: dict[str, Any], data: GateData) -> list[Blocker]:
    """The blockers, in the order the owner would fix them; an empty list means the contract may be issued."""
    blockers: list[Blocker] = []
    if data.executor is None:
        blockers.append(Blocker(EXECUTOR_PROFILE_REQUIRED))
    if data.client is None:
        blockers.append(Blocker(CLIENT_REQUIRED))
    else:
        absent = [name for name in ("street", "postal_code", "city") if not (getattr(data.client, name) or "").strip()]
        if absent:
            blockers.append(Blocker(CLIENT_ADDRESS_INCOMPLETE, {"missing": absent}))
    catalog = load_contract_catalog()
    keys = missing_required(answers, catalog)
    if keys:
        blockers.append(Blocker(ANSWERS_MISSING, {"keys": keys}))
    authorised = {str(p.id) for p in data.people if p.may_accept_and_sign}
    gone = [pid for pid in answers.get("who_accepts") or [] if pid not in authorised]
    if gone:
        blockers.append(Blocker(PERSON_NOT_AUTHORISED, {"ids": gone}))
    planned = [(room, surface) for room in data.rooms for surface in room.surfaces if surface.works]
    if not planned:
        blockers.append(Blocker(NO_PLANNED_WORKS))
    else:
        items = [
            {"room": room.name, "surface": surface.name, "surface_type": surface.surface_type, "missing": list(missing_for_issue(surface))}
            for room, surface in planned
            if missing_for_issue(surface)
        ]
        if items:
            blockers.append(Blocker(SURFACE_INCOMPLETE, {"items": items}))
    if data.estimate is None:
        blockers.append(Blocker(ESTIMATE_REQUIRED))
    elif data.estimate.status not in (EstimateStatus.FINAL, EstimateStatus.ACCEPTED):
        blockers.append(Blocker(ESTIMATE_NOT_FINAL, {"status": data.estimate.status.value, "version": data.estimate.version}))
    return blockers

