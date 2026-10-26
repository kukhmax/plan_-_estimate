"""Pressure test protocol DTOs (V2-12b). The pressures go out as strings with two places, like every quantity of the application."""

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.payment import Out

# a number is checked by the domain rules (a sentence for each refusal), so the schema takes it as it comes: a number or the text typed
Number = int | float | str | None


class PressureUpdate(BaseModel):
    """Only the fields that are sent change; `null` clears one. The content of a field is checked by the domain rules, which name the field they refuse."""

    model_config = ConfigDict(extra="forbid")

    held_on: date | None = None
    held_time: str | None = None
    customer_absent: bool | None = None
    notified_on: date | None = None
    attendees: list[dict[str, Any]] | None = None
    system: str | None = None
    section: str | None = None
    medium: str | None = None
    test_pressure_bar: Number = None
    duration_min: int | None = None
    pressure_drop_bar: Number = None
    photo_ids: list[str] | None = None
    result: str | None = None
    remarks: str | None = None


class PressureBlockerRead(BaseModel):
    code: str
    details: dict[str, Any] | None = None


class PressurePhotoRead(BaseModel):
    id: str
    caption: str | None
    place: str | None
    captured_at: datetime | None
    created_at: datetime


class PressureRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    sequence: int
    status: str
    held_on: date | None
    held_time: str | None
    customer_absent: bool
    notified_on: date | None
    attendees: list[dict[str, Any]]
    system: str | None
    section: str | None
    medium: str | None
    test_pressure_bar: Out | None
    duration_min: int | None
    pressure_drop_bar: Out | None
    photo_ids: list[str]
    result: str | None
    remarks: str | None
    photo_options: list[PressurePhotoRead]  # the photos of the object that may be the picture of the manometer
    blockers: list[PressureBlockerRead]
    created_at: datetime
    updated_at: datetime


class PressureListResponse(BaseModel):
    items: list[PressureRead]
    total: int
