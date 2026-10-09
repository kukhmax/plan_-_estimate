"""Contract DTOs (Stage 16E.1): the contract of an object with the answers of the questionnaire."""

import uuid
from datetime import datetime
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
    created_at: datetime
    updated_at: datetime


class ContractListResponse(BaseModel):
    items: list[ContractRead]
    total: int
