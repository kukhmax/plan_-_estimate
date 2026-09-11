import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.domain.rules.room_geometry import calculate_segment_area
from app.models.area_segment import AreaOperation, AreaPlane


class AreaSegmentCreate(BaseModel):
    plane: AreaPlane
    operation: AreaOperation
    width: Decimal = Field(
        gt=0,
        decimal_places=3,
        max_digits=10,
        description="Segment width in meters",
    )
    height: Decimal = Field(
        gt=0,
        decimal_places=3,
        max_digits=10,
        description="Segment height in meters",
    )
    position: int | None = Field(
        default=None,
        ge=0,
        description="Sequential position of the segment within the plane",
    )
    label: str | None = Field(default=None, max_length=255)


class AreaSegmentUpdate(BaseModel):
    operation: AreaOperation | None = None
    width: Decimal | None = Field(
        default=None,
        gt=0,
        decimal_places=3,
        max_digits=10,
        description="Segment width in meters",
    )
    height: Decimal | None = Field(
        default=None,
        gt=0,
        decimal_places=3,
        max_digits=10,
        description="Segment height in meters",
    )
    position: int | None = Field(
        default=None,
        ge=0,
        description="Sequential position of the segment within the plane",
    )
    label: str | None = Field(default=None, max_length=255)

    @model_validator(mode="after")
    def validate_not_null_fields(self) -> "AreaSegmentUpdate":
        for field_name in ("operation", "width", "height"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class AreaSegmentRead(BaseModel):
    id: uuid.UUID
    room_id: uuid.UUID
    plane: AreaPlane
    operation: AreaOperation
    width: Decimal
    height: Decimal
    position: int | None = None
    label: str | None = None
    area: Decimal | None = None
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def compute_area(self) -> "AreaSegmentRead":
        if self.area is None:
            self.area = calculate_segment_area(self.width, self.height)
        return self


class AreaSegmentListResponse(BaseModel):
    items: list[AreaSegmentRead]
    total: int
