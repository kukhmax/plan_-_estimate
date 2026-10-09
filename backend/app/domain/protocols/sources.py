"""What the handover protocol is built from besides its own entries (Stage 16F.2): the object, the customer, the executor, the rooms
and the contract whose requirements apply. Loaded once so the gate and the document see the same data."""
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import ProjectNotFoundError
from app.domain.services.executor_profile_service import ExecutorProfileService
from app.models.client import Client
from app.models.contract import Contract, ContractStatus
from app.models.executor_profile import ExecutorProfile
from app.models.issued_document import IssuedDocument, IssuedDocumentKind
from app.models.project import Project
from app.models.room import Room


@dataclass(slots=True)
class HandoverSources:
    project: Project
    client: Client | None
    executor: ExecutorProfile | None
    rooms: tuple[tuple[str, str, bool], ...]  # (id, name, archived) in the order they were added
    contract: Contract | None  # the latest issued or signed one
    contract_number: str | None  # its number in the journal of issued documents

    @property
    def required_values(self) -> dict:
        answers = ((self.contract.snapshot or {}).get("answers") or {}) if self.contract else {}
        return answers.get("premises_requirement_values") or {}


async def load_handover_sources(db: AsyncSession, owner_id: uuid.UUID, project_id: uuid.UUID) -> HandoverSources:
    """Raises ProjectNotFoundError for a project that is not this owner's (nothing else is read then)."""
    project = (await db.execute(select(Project).where(Project.id == project_id, Project.owner_id == owner_id))).scalar_one_or_none()
    if project is None:
        raise ProjectNotFoundError(f"Project {project_id} not found")
    client = (
        (await db.execute(select(Client).where(Client.id == project.client_id, Client.owner_user_id == owner_id))).scalar_one_or_none()
        if project.client_id is not None else None
    )
    executor = await ExecutorProfileService(db).get(owner_id)
    rooms = tuple(
        (str(room.id), room.name, bool(room.is_archived))
        for room in (await db.execute(select(Room).where(Room.project_id == project_id).order_by(Room.created_at, Room.id))).scalars()
    )
    contract = (
        await db.execute(
            select(Contract)
            .where(
                Contract.project_id == project_id, Contract.owner_id == owner_id,
                Contract.status.in_([ContractStatus.ISSUED.value, ContractStatus.SIGNED.value]),
            )
            .order_by(Contract.version.desc()).limit(1)
        )
    ).scalar_one_or_none()
    number = None
    if contract is not None:
        number = (
            await db.execute(
                select(IssuedDocument.number)
                .where(
                    IssuedDocument.owner_id == owner_id, IssuedDocument.kind == IssuedDocumentKind.CONTRACT.value,
                    IssuedDocument.source_id == contract.id,
                )
                .order_by(IssuedDocument.issued_at.desc()).limit(1)
            )
        ).scalar_one_or_none()
    return HandoverSources(project, client, executor, rooms, contract, number)
