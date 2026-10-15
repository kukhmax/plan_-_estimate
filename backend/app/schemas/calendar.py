"""Calendar and reminders (Stage 18E): the agenda, the settings, the owner's own reminders, the planned dates."""
import uuid
from datetime import date, datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.work_execution import WorkExecutionStatus

Preset = Literal["BREAK_END", "WORK_DAY", "DAY_BEFORE", "IN_1H", "IN_3H", "TOMORROW", "CUSTOM"]


class AgendaItemRead(BaseModel):
    source: Literal["EVENT", "REMINDER"]
    kind: str
    key: str
    day: date
    on: date | None = None
    at: datetime | None = None
    ref: str = ""
    title_key: str | None = None
    title: str | None = None
    params: dict[str, str | int] = Field(default_factory=dict)
    sends: bool
    reminder_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    project_name: str | None = None
    room_id: uuid.UUID | None = None
    room_name: str | None = None
    surface_id: uuid.UUID | None = None
    surface_name: str | None = None
    occurrence_key: uuid.UUID | None = None


class AgendaWorkRead(BaseModel):
    occurrence_key: uuid.UUID
    planned_date: date
    status: WorkExecutionStatus
    wait_after_hours: int | None = None
    project_id: uuid.UUID
    project_name: str
    room_id: uuid.UUID
    room_name: str
    surface_id: uuid.UUID
    surface_name: str
    work_name_key: str | None = None
    work_display_name: str | None = None


class AgendaRead(BaseModel):
    today: date
    start: date
    end: date
    items: list[AgendaItemRead]
    works: list[AgendaWorkRead]
    overdue: list[AgendaWorkRead]


class KindSettingRead(BaseModel):
    kind: str
    default_push: bool
    sends: bool


class CalendarSettingsRead(BaseModel):
    timezone: str
    enabled: bool
    kind_overrides: dict[str, bool]
    quiet_from: time
    quiet_to: time
    digest_at: time
    language: Literal["pl", "ru"] | None = None
    kinds: list[KindSettingRead]
    timezones: list[str]


class CalendarSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timezone: str
    enabled: bool = True
    kind_overrides: dict[str, bool] = Field(default_factory=dict)
    quiet_from: time = time(21, 0)
    quiet_to: time = time(7, 0)
    digest_at: time = time(8, 0)
    language: str | None = None


class ReminderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preset: Preset
    title: str | None = Field(default=None, max_length=200)
    send_at: datetime | None = None  # CUSTOM: an aware instant (the API)...
    local_date: date | None = None  # ...or a day and a time of the day in the owner's zone (the screen): the server makes the instant
    local_time: time | None = None
    project_id: uuid.UUID | None = None
    room_id: uuid.UUID | None = None
    surface_id: uuid.UUID | None = None
    occurrence_key: uuid.UUID | None = None


class ReminderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID | None = None
    room_id: uuid.UUID | None = None
    surface_id: uuid.UUID | None = None
    occurrence_key: uuid.UUID | None = None
    origin: str
    kind: str
    title: str | None = None
    send_at: datetime
    status: str
    close_on_status: str | None = None


class ReminderListResponse(BaseModel):
    items: list[ReminderRead]
    total: int


class PlannedDateRead(BaseModel):
    occurrence_key: uuid.UUID
    planned_date: date


class ScheduleWarningRead(BaseModel):
    occurrence_key: uuid.UUID
    code: Literal["BEFORE_BREAK_END", "BEFORE_CONTRACT_START", "AFTER_CONTRACT_END"]
    date: date


class ScheduleRead(BaseModel):
    planned: list[PlannedDateRead]
    warnings: list[ScheduleWarningRead]
    window_start: date | None = None  # work_start_date of the contract
    window_end: date | None = None


class PlannedDateWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    planned_date: date | None = None  # None clears the date
    note: str | None = Field(default=None, max_length=255)


class ScheduleSuggestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: date
    room_id: uuid.UUID | None = None


class ScheduleApply(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dates: list[PlannedDateRead] = Field(max_length=500)
