"""Persons of an object: DTOs (Stage 16B.2). The content rules (phone, e-mail, blank name) are the schema's, so every refusal is
one 422 naming the field. PATCH changes only what is sent; an explicit null clears an optional field."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.rules.polish_identifiers import normalize_email, normalize_phone
from app.models.project_representative import RepresentativeSide


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(value.split()) or None


def _clean_phone(value: str | None) -> str | None:
    try:
        return normalize_phone(value)
    except ValueError:
        raise ValueError("phone must have at least 7 digits (e.g. +48 600 100 200)") from None


def _clean_email(value: str | None) -> str | None:
    try:
        return normalize_email(value)
    except ValueError:
        raise ValueError("email must look like name@example.pl") from None


class _Fields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("name", "role_title", check_fields=False, mode="after")
    @classmethod
    def _trim(cls, value: str | None, info) -> str | None:
        cleaned = _clean_text(value)
        if info.field_name == "name" and value is not None and cleaned is None:
            raise ValueError("name must not be empty")
        return cleaned

    @field_validator("phone", check_fields=False, mode="after")
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        return _clean_phone(value)

    @field_validator("email", check_fields=False, mode="after")
    @classmethod
    def _email(cls, value: str | None) -> str | None:
        return _clean_email(value)


class ProjectRepresentativeCreate(_Fields):
    side: RepresentativeSide
    name: str = Field(max_length=255)
    role_title: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=255)
    may_accept_and_sign: bool = False


class ProjectRepresentativeUpdate(_Fields):
    """Only the fields that are sent change. `side`, `name` and the mark can be changed but never cleared."""

    side: RepresentativeSide | None = None
    name: str | None = Field(default=None, max_length=255)
    role_title: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=255)
    may_accept_and_sign: bool | None = None

    @model_validator(mode="after")
    def _required_fields_are_not_cleared(self) -> "ProjectRepresentativeUpdate":
        for field in ("side", "name", "may_accept_and_sign"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} must not be null")
        return self


class ProjectRepresentativeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    project_id: uuid.UUID
    side: RepresentativeSide
    name: str
    role_title: str | None
    phone: str | None
    email: str | None
    may_accept_and_sign: bool
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class ProjectRepresentativeListResponse(BaseModel):
    items: list[ProjectRepresentativeRead]
    total: int
