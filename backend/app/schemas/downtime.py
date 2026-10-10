"""Downtime episode DTOs (Stage 16I.3)."""

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class DowntimeUpdate(BaseModel):
    """Only the fields that are sent change; `null` clears one. The notice's entries change while the episode is a draft, the protocol's
    once the notice is issued; the content of a field is checked by the domain rules, which name the field they refuse. `days` is
    {"YYYY-MM-DD": {"other_work": bool, "note": text} | null}."""

    model_config = ConfigDict(extra="forbid")

    cause_key: str | None = None
    cause_note: str | None = None
    room_ids: list[str] | None = None
    noticed_on: date | None = None
    noticed_time: str | None = None
    notice_channel: str | None = None
    photo_ids: list[str] | None = None
    need_text: str | None = None
    need_by: date | None = None
    days: dict[str, Any] | None = None
    held_on: date | None = None
    held_time: str | None = None
    attendees: list[dict[str, Any]] | None = None
    signature_refused: bool | None = None
    deadline_note: str | None = None
    notes: str | None = None


class DowntimeBlockerRead(BaseModel):
    code: str
    details: dict[str, Any] | None = None


class DowntimeContractRead(BaseModel):
    id: uuid.UUID
    version: int
    status: str


class DowntimePhotoRead(BaseModel):
    id: str
    caption: str | None
    captured_at: datetime | None
    room_name: str | None


class DowntimeDayRead(BaseModel):
    date: date
    weekday: int  # 0 = Monday
    other_work: bool
    note: str | None


class DowntimeSettlementRead(BaseModel):
    listed: int  # the days of the protocol
    chargeable: int  # the days without other work
    rate: str | None  # per day, from the contract
    amount: str | None  # rate x chargeable days
    cap: str | None  # the contract's cap, from the estimated remuneration
    capped: bool
    payable: str | None  # the amount, not more than the cap
    limit_days: int | None
    limit_exceeded: bool


class DowntimeRoomRead(BaseModel):
    id: str
    name: str


class DowntimeRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    sequence: int
    status: str  # DRAFT / NOTICED / CLOSED / ARCHIVED
    cause_key: str | None
    cause_text: str | None  # the catalogue's Polish name of the cause
    cause_note: str | None
    room_ids: list[str]
    noticed_on: date | None
    noticed_time: str | None
    notice_channel: str | None
    photo_ids: list[str]
    need_text: str | None
    need_by: date | None
    days: list[DowntimeDayRead]
    held_on: date | None
    held_time: str | None
    attendees: list[dict[str, Any]]
    signature_refused: bool
    deadline_note: str | None
    notes: str | None
    notice_number: str | None
    notice_issued_at: datetime | None
    protocol_issued_at: datetime | None
    photos: list[DowntimePhotoRead]  # the chosen photos
    photo_options: list[DowntimePhotoRead]  # what may be chosen (while a draft)
    rooms: list[DowntimeRoomRead]
    settlement: DowntimeSettlementRead
    blockers: list[DowntimeBlockerRead]  # of the document that is next to be issued
    contract: DowntimeContractRead | None
    created_at: datetime
    updated_at: datetime


class DowntimeListResponse(BaseModel):
    items: list[DowntimeRead]
    total: int
