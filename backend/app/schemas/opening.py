import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.domain.rules.room_geometry import calculate_opening_area, calculate_reveal
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
    reveal_enabled: bool = Field(default=False)
    reveal_depth: Decimal | None = Field(
        default=None,
        gt=0,
        decimal_places=3,
        max_digits=10,
        description="Reveal depth in meters",
    )
    reveal_left: bool = Field(default=True)
    reveal_right: bool = Field(default=True)
    reveal_top: bool = Field(default=True)
    reveal_bottom: bool = Field(default=False)

    @model_validator(mode="after")
    def validate_reveal(self) -> "OpeningCreate":
        if self.reveal_enabled:
            if self.opening_type == OpeningType.OTHER:
                raise ValueError(
                    "Reveal calculation is only available for WINDOW and DOOR openings"
                )
            if self.reveal_depth is None:
                raise ValueError("reveal_depth is required when reveal_enabled is True")
        return self


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
    reveal_enabled: bool | None = None
    reveal_depth: Decimal | None = Field(
        default=None,
        gt=0,
        decimal_places=3,
        max_digits=10,
        description="Reveal depth in meters",
    )
    reveal_left: bool | None = None
    reveal_right: bool | None = None
    reveal_top: bool | None = None
    reveal_bottom: bool | None = None

    @model_validator(mode="after")
    def validate_not_null_fields(self) -> "OpeningUpdate":
        for field_name in ("opening_type", "width", "height", "quantity"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        for bool_field in ("reveal_enabled", "reveal_left", "reveal_right", "reveal_top", "reveal_bottom"):
            if bool_field in self.model_fields_set and getattr(self, bool_field) is None:
                raise ValueError(f"{bool_field} cannot be null")
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
    reveal_enabled: bool = False
    reveal_depth: Decimal | None = None
    reveal_left: bool = True
    reveal_right: bool = True
    reveal_top: bool = True
    reveal_bottom: bool = False
    reveal_single_length: Decimal | None = None
    reveal_single_area: Decimal | None = None
    reveal_total_length: Decimal | None = None
    reveal_total_area: Decimal | None = None
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def compute_derived(self) -> "OpeningRead":
        if self.width is not None and self.height is not None and self.quantity is not None:
            area_res = calculate_opening_area(self.width, self.height, self.quantity)
            if area_res is not None:
                if self.single_area is None:
                    self.single_area = area_res.single_area
                if self.total_area is None:
                    self.total_area = area_res.total_area

        if (
            self.reveal_enabled
            and self.reveal_depth is not None
            and self.width is not None
            and self.height is not None
            and self.quantity is not None
        ):
            rev = calculate_reveal(
                self.width,
                self.height,
                self.reveal_depth,
                self.reveal_left,
                self.reveal_right,
                self.reveal_top,
                self.reveal_bottom,
                self.quantity,
            )
            if rev is not None:
                self.reveal_single_length = rev.single_length
                self.reveal_single_area = rev.single_area
                self.reveal_total_length = rev.total_length
                self.reveal_total_area = rev.total_area

        return self


class OpeningListResponse(BaseModel):
    items: list[OpeningRead]
    total: int
