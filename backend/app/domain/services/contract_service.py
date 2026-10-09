"""Contracts of an object (Stage 16E.1): open the draft, answer the questionnaire, abandon the draft.

Every call is scoped to the owner's own project (`ProjectNotFoundError` otherwise). At most one draft exists per object (a partial
unique index): opening the draft twice returns the same one. Only a draft may change; the persons an answer names must be active
persons of the same object who are marked "may accept the work and sign the protocols".
"""
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.contracts.answers import effective_answers, merge_answers, missing_required
from app.domain.contracts.gate import Blocker, GateData, evaluate_gate, load_gate_data
from app.domain.contracts.catalog import load_contract_catalog
from app.domain.documents.formatting import local_datetime
from app.domain.exceptions import ContractNotEditableError, ContractNotFoundError, ContractSignError, ProjectNotFoundError
from app.models.estimate import Estimate, EstimateStatus
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
        issued_at=row.issued_at,
        estimate_version=row.estimate_version,
        signed_on=row.signed_on,
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
        previous = (
            await self.db.execute(
                select(Contract).where(Contract.project_id == project_id, Contract.owner_id == owner_id).order_by(Contract.version.desc()).limit(1)
            )
        ).scalar_one_or_none()
        row = Contract(
            owner_id=owner_id,
            project_id=project_id,
            version=1 if previous is None else previous.version + 1,
            status=ContractStatus.DRAFT.value,
            answers=dict(previous.answers or {}) if previous is not None else {},  # a new version starts from the last one's answers
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

    async def gate(self, project_id: uuid.UUID, contract_id: uuid.UUID, owner_id: uuid.UUID) -> "tuple[Contract, GateData, list[Blocker]]":
        """What stands between this contract and its issue, with the data the document would be built from."""
        row = await self.get(project_id, contract_id, owner_id)
        data = await load_gate_data(self.db, owner_id, project_id)
        return row, data, evaluate_gate(effective_answers(row.answers or {}, load_contract_catalog()), data)

    async def mark_issued(
        self,
        project_id: uuid.UUID,
        contract_id: uuid.UUID,
        owner_id: uuid.UUID,
        *,
        issued_at: datetime,
        snapshot: dict[str, Any],
        document_html: str,
        estimate_id: uuid.UUID | None,
        estimate_version: int | None,
    ) -> Contract:
        """Freeze a draft: its conditions, its page and the estimate it priced. An earlier issued (not signed) version of the
        same object is superseded and archived; a draft is the only state that can be issued."""
        row = await self.get(project_id, contract_id, owner_id)
        if row.status != ContractStatus.DRAFT.value:
            raise ContractNotEditableError(f"contract {contract_id} is {row.status}: only a draft is issued")
        for older in (
            await self.db.execute(
                select(Contract).where(
                    Contract.project_id == project_id, Contract.owner_id == owner_id, Contract.status == ContractStatus.ISSUED.value
                )
            )
        ).scalars():
            older.status = ContractStatus.ARCHIVED.value
        row.status = ContractStatus.ISSUED.value
        row.issued_at = issued_at
        row.snapshot = snapshot
        row.document_html = document_html
        row.estimate_id = estimate_id
        row.estimate_version = estimate_version
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def sign(
        self, project_id: uuid.UUID, contract_id: uuid.UUID, owner_id: uuid.UUID, signed_on: date, *, today: date | None = None
    ) -> Contract:
        """An issued contract was signed on paper: it becomes SIGNED and the estimate that priced it becomes ACCEPTED, in one
        transaction. The conditions stay exactly as issued; nothing is regenerated."""
        row = await self.get(project_id, contract_id, owner_id)
        if row.status != ContractStatus.ISSUED.value:
            raise ContractNotEditableError(f"contract {contract_id} is {row.status}: only an issued contract is signed")
        today = today or local_datetime(datetime.now(UTC)).date()
        if signed_on > today:
            raise ContractSignError("SIGNED_ON_IN_FUTURE")
        if row.issued_at is not None and signed_on < local_datetime(row.issued_at).date():
            raise ContractSignError("SIGNED_ON_BEFORE_ISSUE")
        estimate = (
            await self.db.execute(
                select(Estimate).where(Estimate.id == row.estimate_id, Estimate.project_id == project_id, Estimate.owner_id == owner_id)
            )
        ).scalar_one_or_none() if row.estimate_id is not None else None
        if estimate is None or estimate.status not in (EstimateStatus.FINAL, EstimateStatus.ACCEPTED):
            raise ContractSignError("ESTIMATE_CHANGED")
        signed = (
            await self.db.execute(
                select(Contract.id).where(
                    Contract.project_id == project_id, Contract.owner_id == owner_id, Contract.status == ContractStatus.SIGNED.value
                )
            )
        ).scalar_one_or_none()
        if signed is not None:
            raise ContractSignError("ALREADY_SIGNED")
        estimate.status = EstimateStatus.ACCEPTED
        row.status = ContractStatus.SIGNED.value
        row.signed_on = signed_on
        try:
            await self.db.commit()
        except IntegrityError:  # two requests signed at once: the unique index let one through
            await self.db.rollback()
            raise ContractSignError("ALREADY_SIGNED") from None
        await self.db.refresh(row)
        return row

    async def close(self, project_id: uuid.UUID, contract_id: uuid.UUID, owner_id: uuid.UUID) -> Contract:
        """An issued contract that was not signed, or a signed one that ended, goes to the archive. The estimate stays as it is."""
        row = await self.get(project_id, contract_id, owner_id)
        if row.status not in (ContractStatus.ISSUED.value, ContractStatus.SIGNED.value):
            raise ContractNotEditableError(f"contract {contract_id} is {row.status}: only an issued or signed contract is closed")
        row.status = ContractStatus.ARCHIVED.value
        await self.db.commit()
        await self.db.refresh(row)
        return row
