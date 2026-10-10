"""Decision protocol DTOs (Stage 16I)."""

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class DecisionUpdate(BaseModel):
    """Only the fields that are sent change; `null` clears one. The content of a field is checked by the domain rules, which name the
    field they refuse. `items` is {item_id: {fields} | null}."""

    model_config = ConfigDict(extra="forbid")

    held_on: date | None = None
    held_time: str | None = None
    attendees: list[dict[str, Any]] | None = None
    items: dict[str, Any] | None = None
    understood: bool | None = None
    signature_refused: bool | None = None
    notes: str | None = None


class DecisionBlockerRead(BaseModel):
    code: str
    details: dict[str, Any] | None = None


class DecisionContractRead(BaseModel):
    id: uuid.UUID
    version: int
    status: str


class DecisionItemRead(BaseModel):
    id: str
    source: str  # RISK / OWN
    risk_id: str | None
    room_id: str | None
    room_name: str | None
    severity: str | None  # of the risk
    blocks_finishing: bool
    title: str
    state: str | None  # what was found (the risk's explanation), none for the contractor's own item
    recommendation: str
    consequence: str
    price: str | None
    decision: str | None
    executor_action: str | None
    order_ref: str | None
    note: str | None
    risk_active: bool  # false when the risk of the item is no longer found


class DecisionRiskOptionRead(BaseModel):
    id: str
    room_id: str
    room_name: str
    severity: str
    blocks_finishing: bool
    title: str
    consequence: str
    used: bool  # already an item of this protocol


class DecisionRoomRead(BaseModel):
    id: str
    name: str


class DecisionRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    sequence: int
    status: str
    held_on: date | None
    held_time: str | None
    attendees: list[dict[str, Any]]
    understood: bool
    signature_refused: bool
    notes: str | None
    items: list[DecisionItemRead]
    risk_options: list[DecisionRiskOptionRead]  # the active risks that may be put into the protocol
    rooms: list[DecisionRoomRead]  # where a recommendation of the contractor's own may point
    blockers: list[DecisionBlockerRead]
    contract: DecisionContractRead | None
    created_at: datetime
    updated_at: datetime


class DecisionListResponse(BaseModel):
    items: list[DecisionRead]
    total: int
