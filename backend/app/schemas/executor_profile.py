"""Executor profile DTOs (Stage 15C). PUT replaces the whole profile: an omitted optional field is cleared."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ExecutorProfileWrite(BaseModel):
    """Types and lengths only; the content rules (NIP checksum, postal code, e-mail, ...) are the service's, so every
    refusal comes back in one fixed envelope with a code per field."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=255)
    nip: str | None = Field(default=None, max_length=32)
    street: str | None = Field(default=None, max_length=255)
    postal_code: str | None = Field(default=None, max_length=16)
    city: str | None = Field(default=None, max_length=128)
    phone: str | None = Field(default=None, max_length=50)
    email: str | None = Field(default=None, max_length=255)
    bank_account: str | None = Field(default=None, max_length=64)


class ExecutorProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    nip: str | None
    street: str | None
    postal_code: str | None
    city: str | None
    phone: str | None
    email: str | None
    bank_account: str | None
    created_at: datetime
    updated_at: datetime


class ExecutorProfileResponse(BaseModel):
    """`profile` is null until the owner has filled the profile in."""

    profile: ExecutorProfileRead | None
