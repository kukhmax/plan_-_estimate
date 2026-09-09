import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app.models.client import ClientType


class ClientCreate(BaseModel):
    client_type: ClientType
    first_name: Optional[str] = Field(default=None, max_length=255)
    last_name: Optional[str] = Field(default=None, max_length=255)
    company_name: Optional[str] = Field(default=None, max_length=512)
    phone: Optional[str] = Field(default=None, max_length=50)
    email: Optional[str] = Field(default=None, max_length=255)
    nip: Optional[str] = Field(default=None, max_length=20)
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


class ClientUpdate(BaseModel):
    client_type: Optional[ClientType] = None
    first_name: Optional[str] = Field(default=None, max_length=255)
    last_name: Optional[str] = Field(default=None, max_length=255)
    company_name: Optional[str] = Field(default=None, max_length=512)
    phone: Optional[str] = Field(default=None, max_length=50)
    email: Optional[str] = Field(default=None, max_length=255)
    nip: Optional[str] = Field(default=None, max_length=20)
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
    notes: Optional[str] = None
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ClientListResponse(BaseModel):
    items: list[ClientRead]
    total: int
