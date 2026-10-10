"""Acceptance protocol DTOs (Stage 16H)."""

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator


class AcceptanceUpdate(BaseModel):
    """Only the fields that are sent change; `null` clears one. The content of a field is checked by the domain rules, which name the
    field they refuse."""

    model_config = ConfigDict(extra="forbid")

    held_on: date | None = None
    held_time: str | None = None
    customer_absent: bool | None = None
    notified_on: date | None = None
    renotified_on: date | None = None
    attendees: list[dict[str, Any]] | None = None
    room_ids: list[str] | None = None
    conditions_note: str | None = None
    instrument_keys: list[str] | None = None
    surfaces: dict[str, Any] | None = None
    batches: str | None = None
    instructions_given: bool | None = None
    amount_due: str | None = None
    amount_retained: str | None = None
    notes: str | None = None

    @field_validator("surfaces")
    @classmethod
    def _deadlines_as_dates(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        """JSON carries a deadline as text; the rules take a date. Anything that is not a valid ISO date stays as it is and the rules
        refuse it by name."""
        for entry in (value or {}).values():
            remarks = entry.get("remarks") if isinstance(entry, dict) else None
            for remark in (remarks.values() if isinstance(remarks, dict) else ()):
                if isinstance(remark, dict) and isinstance(remark.get("deadline"), str):
                    try:
                        remark["deadline"] = date.fromisoformat(remark["deadline"])
                    except ValueError:
                        pass
        return value


class AcceptanceBlockerRead(BaseModel):
    code: str
    details: dict[str, Any] | None = None


class AcceptanceContractRead(BaseModel):
    id: uuid.UUID
    version: int
    status: str


class AcceptanceWorkRead(BaseModel):
    name: str
    status: str


class AcceptanceRemarkRead(BaseModel):
    id: str
    place: str
    description: str
    classification: str
    deadline: date | None
    photo_ids: list[str]


class AcceptancePhotoRead(BaseModel):
    id: str
    caption: str | None
    captured_at: datetime | None


class AcceptanceSurfaceRead(BaseModel):
    id: str
    name: str
    surface_type: str
    room_id: str
    room_name: str
    quality_target: str | None
    works: list[AcceptanceWorkRead]
    incomplete: int  # the planned works that are not completed
    assessed: bool
    remarks: list[AcceptanceRemarkRead]
    result: str  # derived: ACCEPTED / ACCEPTED_WITH_REMARKS / NOT_ACCEPTED
    photo_options: list[AcceptancePhotoRead]  # the photos of defects of this surface that a remark may point at


class AcceptanceRoomRead(BaseModel):
    id: str
    name: str
    surfaces: int  # surfaces with planned works


class AcceptanceConditionRead(BaseModel):
    key: str
    lighting: str
    requires_agreement: bool
    text_pl: str


class AcceptanceRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    sequence: int
    status: str
    held_on: date | None
    held_time: str | None
    customer_absent: bool
    notified_on: date | None
    renotified_on: date | None
    attendees: list[dict[str, Any]]
    room_ids: list[str]
    conditions_note: str | None
    instrument_keys: list[str]
    batches: str | None
    instructions_given: bool
    amount_due: str | None
    amount_retained: str | None
    notes: str | None
    scope_kind: str | None  # PARTIAL / FINAL, derived from the rooms in scope
    result: str | None  # derived from the surfaces in scope
    rooms: list[AcceptanceRoomRead]  # the rooms that have planned works: what may be put in scope
    surfaces: list[AcceptanceSurfaceRead]  # the surfaces with planned works of the rooms in scope
    conditions: list[AcceptanceConditionRead]  # the conditions of the assessment of the standards in scope
    blockers: list[AcceptanceBlockerRead]
    contract: AcceptanceContractRead | None
    created_at: datetime
    updated_at: datetime


class AcceptanceListResponse(BaseModel):
    items: list[AcceptanceRead]
    total: int
