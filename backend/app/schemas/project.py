import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.project import ProjectStatus


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    address: str = Field(min_length=1, max_length=512)
    city: str = Field(min_length=1, max_length=255)
    postal_code: str = Field(min_length=1, max_length=20)
    description: str | None = Field(default=None, max_length=4096)
    status: ProjectStatus = ProjectStatus.PLANNING


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    address: str | None = Field(default=None, min_length=1, max_length=512)
    city: str | None = Field(default=None, min_length=1, max_length=255)
    postal_code: str | None = Field(default=None, min_length=1, max_length=20)
    description: str | None = Field(default=None, max_length=4096)
    status: ProjectStatus | None = None

    @model_validator(mode="after")
    def validate_required_fields(self) -> "ProjectUpdate":
        for field_name in ("name", "address", "city", "postal_code", "status"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class ProjectRead(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    address: str
    city: str
    postal_code: str
    description: str | None = None
    status: ProjectStatus
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectListResponse(BaseModel):
    items: list[ProjectRead]
    total: int
