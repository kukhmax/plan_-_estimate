"""Concealed works protocol DTOs (Stage 16G)."""

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class ConcealedUpdate(BaseModel):
    """Only the fields that are sent change; `null` clears one. The content of a field is checked by the domain rules, which name the
    field they refuse."""

    model_config = ConfigDict(extra="forbid")

    held_on: date | None = None
    held_time: str | None = None
    customer_absent: bool | None = None
    notified_on: date | None = None
    attendees: list[dict[str, Any]] | None = None
    surface_id: str | None = None
    work_kind: str | None = None
    work_note: str | None = None
    material: str | None = None
    batch: str | None = None
    photo_ids: list[str] | None = None
    result: str | None = None
    remarks: str | None = None
    cover_consent: str | None = None


class ConcealedBlockerRead(BaseModel):
    code: str
    details: dict[str, Any] | None = None


class ConcealedContractRead(BaseModel):
    id: uuid.UUID
    version: int
    status: str


class ConcealedSurfaceRead(BaseModel):
    id: str
    name: str
    room_id: str
    room_name: str


class ConcealedPhotoRead(BaseModel):
    id: str
    caption: str | None
    captured_at: datetime | None


class ConcealedRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    sequence: int
    status: str
    held_on: date | None
    held_time: str | None
    customer_absent: bool
    notified_on: date | None
    attendees: list[dict[str, Any]]
    surface: ConcealedSurfaceRead | None
    work_kind: str | None
    work_note: str | None
    material: str | None
    batch: str | None
    photo_ids: list[str]
    result: str | None
    remarks: str | None
    cover_consent: str | None
    photo_options: list[ConcealedPhotoRead]  # the evidence photos that exist for the chosen surface
    blockers: list[ConcealedBlockerRead]
    contract: ConcealedContractRead | None
    created_at: datetime
    updated_at: datetime


class ConcealedListResponse(BaseModel):
    items: list[ConcealedRead]
    total: int
