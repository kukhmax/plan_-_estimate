import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.domain.rules.room_geometry import calculate_opening_area
from app.models.opening import OpeningType


class OpeningCreate(BaseModel):
    opening_type: OpeningType
    name: str | None = Field(default=None, max_length=255)
    width: Decimal = Field(
        gt=0,
        decimal_places=3,
        max_digits=10,
        description="Opening width in meters",
    )
    height: Decimal = Field(
        gt=0,
        decimal_places=3,
        max_digits=10,
        description="Opening height in meters",
    )
    quantity: int = Field(
        default=1,
        ge=1,
        description="Quantity of identical openings",
    )
    description: str | None = Field(default=None, max_length=4096)


class OpeningUpdate(BaseModel):
    opening_type: OpeningType | None = None
    name: str | None = Field(default=None, max_length=255)
    width: Decimal | None = Field(
        default=None,
        gt=0,
        decimal_places=3,
        max_digits=10,
        description="Opening width in meters",
    )
    height: Decimal | None = Field(
        default=None,
        gt=0,
        decimal_places=3,
        max_digits=10,
        description="Opening height in meters",
    )
    quantity: int | None = Field(
        default=None,
        ge=1,
        description="Quantity of identical openings",
    )
    description: str | None = Field(default=None, max_length=4096)

    @model_validator(mode="after")
    def validate_not_null_fields(self) -> "OpeningUpdate":
        for field_name in ("opening_type", "width", "height", "quantity"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class OpeningRead(BaseModel):
    id: uuid.UUID
    surface_id: uuid.UUID
    opening_type: OpeningType
    name: str | None = None
    width: Decimal
    height: Decimal
    quantity: int
    single_area: Decimal | None = None
    total_area: Decimal | None = None
    description: str | None = None
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def compute_areas(self) -> "OpeningRead":
        if self.width is not None and self.height is not None and self.quantity is not None:
            res = calculate_opening_area(self.width, self.height, self.quantity)
            if res is not None:
                if self.single_area is None:
                    self.single_area = res.single_area
                if self.total_area is None:
                    self.total_area = res.total_area
        return self


class OpeningListResponse(BaseModel):
    items: list[OpeningRead]
    total: int
