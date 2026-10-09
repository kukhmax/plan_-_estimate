"""Handover protocol DTOs (Stage 16F.1)."""

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class HandoverUpdate(BaseModel):
    """Only the fields that are sent change; `null` clears one. Rooms and requirements are merged entry by entry (a room's entry
    set to `null` is removed); the content of an entry is checked by the domain rules, which name the field they refuse."""

    model_config = ConfigDict(extra="forbid")

    held_on: date | None = None
    held_time: str | None = None
    attendees: list[dict[str, Any]] | None = None
    meters: str | None = None
    notes: str | None = None
    rooms: dict[str, Any] | None = None


class HandoverBlockerRead(BaseModel):
    code: str
    details: dict[str, Any] | None = None


class HandoverContractRead(BaseModel):
    id: uuid.UUID
    version: int
    status: str


class HandoverRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    sequence: int
    status: str
    held_on: date | None
    held_time: str | None
    attendees: list[dict[str, Any]]
    rooms: dict[str, Any]
    meters: str | None
    notes: str | None
    suggested: dict[str, str | None]  # per room in the protocol: the best decision the findings allow
    blockers: list[HandoverBlockerRead]  # what is still missing before the protocol can be issued
    contract: HandoverContractRead | None  # the contract whose requirements apply: the latest issued or signed one
    required_values: dict[str, Any]  # that contract's numbers for the premises (annex 4), shown next to what was found
    created_at: datetime
    updated_at: datetime


class HandoverListResponse(BaseModel):
    items: list[HandoverRead]
    total: int
