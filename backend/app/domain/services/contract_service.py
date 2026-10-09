"""Contracts of an object (Stage 16E.1): open the draft, answer the questionnaire, abandon the draft.

Every call is scoped to the owner's own project (`ProjectNotFoundError` otherwise). At most one draft exists per object (a partial
unique index): opening the draft twice returns the same one. Only a draft may change; the persons an answer names must be active
persons of the same object who are marked "may accept the work and sign the protocols".
"""
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.contracts.answers import effective_answers, merge_answers, missing_required
from app.domain.contracts.catalog import load_contract_catalog
from app.domain.exceptions import ContractNotEditableError, ContractNotFoundError, ProjectNotFoundError
from app.models.contract import Contract, ContractStatus
from app.models.project import Project
from app.models.project_representative import ProjectRepresentative
from app.schemas.contract import ContractRead


def contract_read(row: Contract) -> ContractRead:
    catalog = load_contract_catalog()
    return ContractRead(
        id=row.id,
        project_id=row.project_id,
        version=row.version,
        status=row.status,
        answers=row.answers or {},
        effective_answers=effective_answers(row.answers or {}, catalog),
        missing_required=missing_required(row.answers or {}, catalog),
        questionnaire_version=row.questionnaire_version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


class ContractService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _ensure_project_owned(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> None:
        found = await self.db.execute(select(Project.id).where(Project.id == project_id, Project.owner_id == owner_id))
        if found.scalar_one_or_none() is None:
            raise ProjectNotFoundError(f"Project {project_id} not found")

    async def _draft(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> Contract | None:
        return (
            await self.db.execute(
                select(Contract).where(
                    Contract.project_id == project_id, Contract.owner_id == owner_id, Contract.status == ContractStatus.DRAFT.value
                )
            )
        ).scalar_one_or_none()

    async def get(self, project_id: uuid.UUID, contract_id: uuid.UUID, owner_id: uuid.UUID) -> Contract:
        await self._ensure_project_owned(project_id, owner_id)
        row = (
            await self.db.execute(
                select(Contract).where(Contract.id == contract_id, Contract.project_id == project_id, Contract.owner_id == owner_id)
            )
        ).scalar_one_or_none()
        if row is None:
            raise ContractNotFoundError(f"Contract {contract_id} not found")
        return row

    async def list(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> list[Contract]:
        await self._ensure_project_owned(project_id, owner_id)
        return list(
            (
                await self.db.execute(
                    select(Contract).where(Contract.project_id == project_id, Contract.owner_id == owner_id).order_by(Contract.version.desc())
                )
            ).scalars()
        )

    async def open_draft(self, project_id: uuid.UUID, owner_id: uuid.UUID) -> tuple[Contract, bool]:
        """The draft of the object and whether it was just created. A second call returns the same draft."""
        await self._ensure_project_owned(project_id, owner_id)
        existing = await self._draft(project_id, owner_id)
        if existing is not None:
            return existing, False
        last = (await self.db.execute(select(func.max(Contract.version)).where(Contract.project_id == project_id))).scalar_one_or_none()
        row = Contract(
            owner_id=owner_id,
            project_id=project_id,
            version=1 if last is None else last + 1,
            status=ContractStatus.DRAFT.value,
            answers={},
            questionnaire_version=load_contract_catalog().questionnaire.version,
        )
        self.db.add(row)
        try:
            await self.db.commit()
        except IntegrityError:  # two requests opened the draft at the same moment: the other one won, take its draft
            await self.db.rollback()
            existing = await self._draft(project_id, owner_id)
            if existing is None:
                raise
            return existing, False
        await self.db.refresh(row)
        return row, True

    async def update_answers(
        self, project_id: uuid.UUID, contract_id: uuid.UUID, owner_id: uuid.UUID, changes: dict[str, Any]
    ) -> Contract:
        row = await self.get(project_id, contract_id, owner_id)
        if row.status != ContractStatus.DRAFT.value:
            raise ContractNotEditableError(f"contract {contract_id} is {row.status}: a changed contract is a new version")
        people = (
            await self.db.execute(
                select(ProjectRepresentative.id, ProjectRepresentative.may_accept_and_sign).where(
                    ProjectRepresentative.project_id == project_id,
                    ProjectRepresentative.owner_id == owner_id,
                    ProjectRepresentative.is_archived.is_(False),
                )
            )
        ).all()
        row.answers = merge_answers(
            row.answers or {},
            changes,
            person_ids={str(person_id) for person_id, _ in people},
            authorised_ids={str(person_id) for person_id, authorised in people if authorised},
            catalog=load_contract_catalog(),
        )
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def archive_draft(self, project_id: uuid.UUID, contract_id: uuid.UUID, owner_id: uuid.UUID) -> Contract:
        row = await self.get(project_id, contract_id, owner_id)
        if row.status != ContractStatus.DRAFT.value:
            raise ContractNotEditableError(f"contract {contract_id} is {row.status}: only a draft can be abandoned")
        row.status = ContractStatus.ARCHIVED.value
        await self.db.commit()
        await self.db.refresh(row)
        return row
