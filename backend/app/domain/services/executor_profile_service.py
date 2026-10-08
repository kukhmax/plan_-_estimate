"""Executor profile (Stage 15C): read and save the owner's own profile. One row per owner; a save creates or replaces it."""

import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import ExecutorProfileValidationError
from app.domain.rules import polish_identifiers as ids
from app.models.executor_profile import ExecutorProfile
from app.schemas.executor_profile import ExecutorProfileWrite

_NORMALIZERS = {
    "nip": ids.normalize_nip,
    "postal_code": ids.normalize_postal_code,
    "phone": ids.normalize_phone,
    "email": ids.normalize_email,
    "bank_account": ids.normalize_bank_account,
}


def _clean_text(value: str | None) -> str | None:
    """Trimmed, inner whitespace collapsed; blank means "not given"."""
    if value is None:
        return None
    text = " ".join(value.split())
    return text or None


def validate_profile(payload: ExecutorProfileWrite) -> dict[str, str | None]:
    """The canonical values to store, or `ExecutorProfileValidationError` with every wrong field."""
    values: dict[str, str | None] = {}
    errors: dict[str, str] = {}
    name = _clean_text(payload.name)
    if name is None:
        errors["name"] = "NAME_REQUIRED"
    values["name"] = name
    for field in ("street", "city"):
        values[field] = _clean_text(getattr(payload, field))
    for field, normalize in _NORMALIZERS.items():
        try:
            values[field] = normalize(getattr(payload, field))
        except ValueError as exc:
            errors[field] = str(exc)
    if errors:
        raise ExecutorProfileValidationError(errors)
    return values


class ExecutorProfileService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, owner_id: uuid.UUID) -> ExecutorProfile | None:
        stmt = select(ExecutorProfile).where(ExecutorProfile.owner_id == owner_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def save(self, owner_id: uuid.UUID, payload: ExecutorProfileWrite) -> ExecutorProfile:
        values = validate_profile(payload)
        profile = await self.get(owner_id)
        if profile is None:
            profile = ExecutorProfile(owner_id=owner_id, **values)
            self.db.add(profile)
        else:
            self._apply(profile, values)
        try:
            await self.db.commit()
        except IntegrityError:
            # Two first saves at once: the unique owner_id let only one in; the other one replaces it.
            await self.db.rollback()
            profile = await self.get(owner_id)
            if profile is None:
                raise
            self._apply(profile, values)
            await self.db.commit()
        await self.db.refresh(profile)
        return profile

    @staticmethod
    def _apply(profile: ExecutorProfile, values: dict[str, str | None]) -> None:
        for field, value in values.items():
            setattr(profile, field, value)
