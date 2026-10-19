import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AccessEntryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    telegram_user_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    status: Literal["PENDING", "ACTIVE", "BLOCKED"]
    is_admin: bool
    created_at: datetime
    decided_at: datetime | None = None


class AccessSettingsRead(BaseModel):
    closed: bool
    contact: str


class AccessOverview(BaseModel):
    settings: AccessSettingsRead
    entries: list[AccessEntryRead]


class AccessDecision(BaseModel):
    status: Literal["ACTIVE", "BLOCKED"]


class AccessSettingsUpdate(BaseModel):
    closed: bool | None = None
    contact: str | None = Field(default=None, max_length=300)
