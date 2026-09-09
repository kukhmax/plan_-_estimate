import uuid
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.models.surface import SurfaceType


class SurfaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    surface_type: SurfaceType
    description: str | None = Field(default=None, max_length=4096)


class SurfaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    surface_type: SurfaceType | None = None
    description: str | None = Field(default=None, max_length=4096)

    @model_validator(mode="after")
    def validate_required_fields(self) -> "SurfaceUpdate":
        for field_name in ("name", "surface_type"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class SurfaceRead(BaseModel):
    id: uuid.UUID
    room_id: uuid.UUID
    name: str
    surface_type: SurfaceType
    description: str | None = None
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SurfaceListResponse(BaseModel):
    items: list[SurfaceRead]
    total: int
