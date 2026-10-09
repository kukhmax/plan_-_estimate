"""Contract DTOs (Stage 16E.1): the contract of an object with the answers of the questionnaire."""

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ContractAnswersUpdate(BaseModel):
    """Only the answers that are sent change; `null` clears an answer (the default, if the catalogue has one, applies again)."""

    model_config = ConfigDict(extra="forbid")

    answers: dict[str, Any] = Field(min_length=1)


class ContractRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    version: int
    status: str
    answers: dict[str, Any]
    effective_answers: dict[str, Any]
    missing_required: list[str]
    questionnaire_version: int
    issued_at: datetime | None = None
    estimate_version: int | None = None  # the estimate that priced an issued contract
    signed_on: date | None = None
    created_at: datetime
    updated_at: datetime


class ContractSignRequest(BaseModel):
    """The day written under the signatures (on paper); the server refuses a day before the issue or in the future."""

    model_config = ConfigDict(extra="forbid")

    signed_on: date


class ContractListResponse(BaseModel):
    items: list[ContractRead]
    total: int


class GateBlockerRead(BaseModel):
    """One thing to fix before the contract can be issued: a stable code the screen has a sentence for, and its details."""

    code: str
    details: dict[str, Any] | None = None


class ContractGateRead(BaseModel):
    ready: bool
    blockers: list[GateBlockerRead]
