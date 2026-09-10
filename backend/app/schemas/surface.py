import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.domain.rules.room_geometry import calculate_surface_gross_area
from app.models.surface import SurfaceType


class SurfaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    surface_type: SurfaceType
    description: str | None = Field(default=None, max_length=4096)
    width: Decimal | None = Field(
        default=None,
        gt=0,
        decimal_places=3,
        max_digits=10,
        description="Surface width in meters",
    )
    height: Decimal | None = Field(
        default=None,
        gt=0,
        decimal_places=3,
        max_digits=10,
        description="Surface height in meters",
    )


class SurfaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    surface_type: SurfaceType | None = None
    description: str | None = Field(default=None, max_length=4096)
    width: Decimal | None = Field(
        default=None,
        gt=0,
        decimal_places=3,
        max_digits=10,
        description="Surface width in meters",
    )
    height: Decimal | None = Field(
        default=None,
        gt=0,
        decimal_places=3,
        max_digits=10,
        description="Surface height in meters",
    )

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
    width: Decimal | None = None
    height: Decimal | None = None
    gross_area: Decimal | None = None
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def compute_gross_area(self) -> "SurfaceRead":
        if self.gross_area is None and self.width is not None and self.height is not None:
            self.gross_area = calculate_surface_gross_area(
                self.surface_type,
                self.width,
                self.height,
            )
        return self


class SurfaceListResponse(BaseModel):
    items: list[SurfaceRead]
    total: int
