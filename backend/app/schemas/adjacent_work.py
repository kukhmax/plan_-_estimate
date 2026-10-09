"""Adjacent works of an object: DTOs (Stage 16D.1). PATCH changes only what is sent; an explicit null clears an optional field."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.adjacent_work import AdjacentWorkOrder


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(value.split()) or None


class _Fields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator(
        "work_name", "performer", "order_note", "responsibility_note", "coordination_note", check_fields=False, mode="after"
    )
    @classmethod
    def _trim(cls, value: str | None, info) -> str | None:
        cleaned = _clean(value)
        if info.field_name == "work_name" and value is not None and cleaned is None:
            raise ValueError("work_name must not be empty")
        return cleaned

    @field_validator("room_ids", check_fields=False, mode="after")
    @classmethod
    def _rooms(cls, value: list[uuid.UUID] | None) -> list[uuid.UUID] | None:
        if value is None:
            return None
        if not value:
            raise ValueError("room_ids must not be empty (use null for the whole object)")
        return list(dict.fromkeys(value))  # no room twice, the order is kept


class AdjacentWorkCreate(_Fields):
    work_name: str = Field(max_length=255)
    performer: str | None = Field(default=None, max_length=255)
    room_ids: list[uuid.UUID] | None = None
    period_from: date | None = None
    period_to: date | None = None
    order_relation: AdjacentWorkOrder
    order_note: str | None = Field(default=None, max_length=1000)
    responsibility_note: str | None = Field(default=None, max_length=1000)
    coordination_note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _period(self) -> "AdjacentWorkCreate":
        if self.period_from and self.period_to and self.period_to < self.period_from:
            raise ValueError("period_to must not be before period_from")
        return self


class AdjacentWorkUpdate(_Fields):
    """Only the fields that are sent change. `work_name` and `order_relation` can be changed but never cleared."""

    work_name: str | None = Field(default=None, max_length=255)
    performer: str | None = Field(default=None, max_length=255)
    room_ids: list[uuid.UUID] | None = None
    period_from: date | None = None
    period_to: date | None = None
    order_relation: AdjacentWorkOrder | None = None
    order_note: str | None = Field(default=None, max_length=1000)
    responsibility_note: str | None = Field(default=None, max_length=1000)
    coordination_note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _required_fields_are_not_cleared(self) -> "AdjacentWorkUpdate":
        for field in ("work_name", "order_relation"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} must not be null")
        if self.period_from and self.period_to and self.period_to < self.period_from:
            raise ValueError("period_to must not be before period_from")
        return self


class AdjacentWorkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    work_name: str
    performer: str | None
    room_ids: list[uuid.UUID] | None
    period_from: date | None
    period_to: date | None
    order_relation: AdjacentWorkOrder
    order_note: str | None
    responsibility_note: str | None
    coordination_note: str | None
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class AdjacentWorkListResponse(BaseModel):
    items: list[AdjacentWorkRead]
    total: int
