"""The owner's standard terms of a contract ("Moje standardowe warunki umowy", UX walk B2): read and replace them.

Only the keys of `STANDARD_TERM_KEYS` are admitted, and every answer is checked and normalised exactly like an answer of the
contract's questionnaire (`merge_answers`), so a term carried into a draft is always a valid answer there.
"""
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.contracts.answers import UNKNOWN_QUESTION, merge_answers
from app.domain.contracts.catalog import load_contract_catalog
from app.domain.contracts.prefill import STANDARD_TERM_KEYS
from app.domain.exceptions import ContractAnswerInvalidError
from app.models.owner_contract_terms import OwnerContractTerms


class ContractTermsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _row(self, owner_id: uuid.UUID) -> OwnerContractTerms | None:
        return (await self.db.execute(select(OwnerContractTerms).where(OwnerContractTerms.owner_id == owner_id))).scalar_one_or_none()

    async def get(self, owner_id: uuid.UUID) -> dict[str, Any]:
        row = await self._row(owner_id)
        return {key: value for key, value in (row.answers or {}).items() if key in STANDARD_TERM_KEYS} if row else {}

    async def save(self, owner_id: uuid.UUID, answers: dict[str, Any]) -> dict[str, Any]:
        """Replace the terms with `answers` (a missing or null key is no term). Nothing is stored when one answer is refused."""
        for key in answers:
            if key not in STANDARD_TERM_KEYS:
                raise ContractAnswerInvalidError(key, UNKNOWN_QUESTION)
        normalised = merge_answers({}, answers, person_ids=set(), authorised_ids=set(), catalog=load_contract_catalog())
        row = await self._row(owner_id)
        if row is None:
            row = OwnerContractTerms(owner_id=owner_id, answers=normalised)
            self.db.add(row)
        else:
            row.answers = normalised
        await self.db.commit()
        return normalised
