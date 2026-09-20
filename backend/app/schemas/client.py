import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app.models.client import ClientType


def normalize_telegram_username(value: Optional[str]) -> Optional[str]:
    """Contact-field normalization only (Stage 10G.4) — never Telegram auth.

    Trims whitespace and a leading '@' (if any), then re-adds exactly one
    '@' for a non-empty value; empty/whitespace-only input becomes NULL.
    No Telegram network/API validation is performed.
    """
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    return f"@{trimmed.lstrip('@')}"


class ClientCreate(BaseModel):
    client_type: ClientType
    first_name: Optional[str] = Field(default=None, max_length=255)
    last_name: Optional[str] = Field(default=None, max_length=255)
    company_name: Optional[str] = Field(default=None, max_length=512)
    phone: Optional[str] = Field(default=None, max_length=50)
    email: Optional[str] = Field(default=None, max_length=255)
    nip: Optional[str] = Field(default=None, max_length=20)
    telegram_username: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = Field(default=None, max_length=4096)

    @model_validator(mode="after")
    def validate_client_type_fields(self) -> "ClientCreate":
        if self.client_type == ClientType.PRIVATE_PERSON:
            if not self.first_name and not self.last_name:
                raise ValueError(
                    "At least one of first_name or last_name is required for PRIVATE_PERSON"
                )
        elif self.client_type == ClientType.COMPANY:
            if not self.company_name:
                raise ValueError("company_name is required for COMPANY clients")
        return self

    @model_validator(mode="after")
    def normalize_telegram_username_field(self) -> "ClientCreate":
        self.telegram_username = normalize_telegram_username(self.telegram_username)
        return self


class ClientUpdate(BaseModel):
    client_type: Optional[ClientType] = None
    first_name: Optional[str] = Field(default=None, max_length=255)
    last_name: Optional[str] = Field(default=None, max_length=255)
    company_name: Optional[str] = Field(default=None, max_length=512)
    phone: Optional[str] = Field(default=None, max_length=50)
    email: Optional[str] = Field(default=None, max_length=255)
    nip: Optional[str] = Field(default=None, max_length=20)
    telegram_username: Optional[str] = Field(default=None, max_length=64)
    notes: Optional[str] = Field(default=None, max_length=4096)

    @model_validator(mode="after")
    def validate_client_type_fields(self) -> "ClientUpdate":
        # Only validate when client_type is explicitly provided in the update payload
        if self.client_type == ClientType.PRIVATE_PERSON:
            if not self.first_name and not self.last_name:
                raise ValueError(
                    "At least one of first_name or last_name is required for PRIVATE_PERSON"
                )
        elif self.client_type == ClientType.COMPANY:
            if not self.company_name:
                raise ValueError("company_name is required for COMPANY clients")
        return self

    @model_validator(mode="after")
    def normalize_telegram_username_field(self) -> "ClientUpdate":
        # Runs only on the value actually present; exclude_unset (applied by
        # the service) still distinguishes omission from an explicit clear —
        # normalizing an omitted field's default None is a harmless no-op.
        if "telegram_username" in self.model_fields_set:
            self.telegram_username = normalize_telegram_username(self.telegram_username)
        return self


class ClientRead(BaseModel):
    id: uuid.UUID
    owner_user_id: uuid.UUID
    client_type: ClientType
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    company_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    nip: Optional[str] = None
    telegram_username: Optional[str] = None
    notes: Optional[str] = None
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ClientListResponse(BaseModel):
    items: list[ClientRead]
    total: int
