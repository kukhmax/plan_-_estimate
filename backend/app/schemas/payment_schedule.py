"""The payment schedule, the work hours and the margin of an object (V2-9). Money goes out as a string with two places (`schemas/payment.py`)."""
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.payment import Money, Out

Percent = Annotated[Decimal, Field(gt=0, le=100, max_digits=5, decimal_places=2)]
Hours = Annotated[Decimal, Field(gt=0, le=24, max_digits=4, decimal_places=2)]
Rate = Annotated[Decimal, Field(gt=0, max_digits=8, decimal_places=2)]
StageState = Literal["PAID", "PARTIAL", "OVERDUE", "OPEN"]


class StageCreate(BaseModel):
    """A line of the schedule: a title and either a share of the agreed amount or a fixed amount."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    percent: Percent | None = None
    amount: Money | None = None
    due_on: date | None = None

    @model_validator(mode="after")
    def _one_of(self) -> "StageCreate":
        if (self.percent is None) == (self.amount is None):
            raise ValueError("give either percent or amount")
        return self


class StageUpdate(BaseModel):
    """Only what is sent changes; giving the percent drops a fixed amount and the other way round; `due_on: null` clears the day."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=255)
    percent: Percent | None = None
    amount: Money | None = None
    due_on: date | None = None

    @model_validator(mode="after")
    def _not_both(self) -> "StageUpdate":
        if self.percent is not None and self.amount is not None:
            raise ValueError("give either percent or amount")
        return self


class StageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    percent: Out | None
    amount_fixed: Out | None = None  # the fixed amount the owner typed (null for a share)
    due_on: date | None
    amount: Out | None = None  # what the stage is worth: the fixed amount, or the share of the agreed amount (null while there is none)
    received: Out
    remaining: Out | None = None
    state: StageState
    created_at: datetime
    updated_at: datetime


class ScheduleSummaryRead(BaseModel):
    agreed: Out | None
    stages_total: Out
    unpriced: int
    difference: Out | None
    received: Out
    to_receive: Out | None


class ScheduleResponse(BaseModel):
    items: list[StageRead]
    summary: ScheduleSummaryRead


class HourCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    worked_on: date
    hours: Hours
    note: str | None = Field(default=None, max_length=1000)


class HourUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    worked_on: date | None = None
    hours: Hours | None = None
    note: str | None = Field(default=None, max_length=1000)


class HourRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    worked_on: date
    hours: Out
    note: str | None
    created_at: datetime
    updated_at: datetime


class HoursResponse(BaseModel):
    items: list[HourRead]
    total_hours: Out
    hourly_rate: Out | None  # the rate of the executor profile (the log shows what the hours are worth when it is set)


class MarginRead(BaseModel):
    basis: Out | None
    basis_source: Literal["AGREED", "ESTIMATE"] | None
    expenses: Out
    hours: Out
    hourly_rate: Out | None
    labor_cost: Out | None
    labor_included: bool
    margin: Out | None
    percent: Out | None
    per_hour: Out | None
