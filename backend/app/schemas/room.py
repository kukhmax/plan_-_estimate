import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.domain.rules.room_geometry import calculate_room_geometry


class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4096)
    length: Decimal | None = Field(
        default=None,
        gt=0,
        decimal_places=3,
        max_digits=10,
        description="Physical length in meters",
    )
    width: Decimal | None = Field(
        default=None,
        gt=0,
        decimal_places=3,
        max_digits=10,
        description="Physical width in meters",
    )
    height: Decimal | None = Field(
        default=None,
        gt=0,
        decimal_places=3,
        max_digits=10,
        description="Physical height in meters",
    )


class RoomUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=4096)
    length: Decimal | None = Field(
        default=None,
        gt=0,
        decimal_places=3,
        max_digits=10,
        description="Physical length in meters",
    )
    width: Decimal | None = Field(
        default=None,
        gt=0,
        decimal_places=3,
        max_digits=10,
        description="Physical width in meters",
    )
    height: Decimal | None = Field(
        default=None,
        gt=0,
        decimal_places=3,
        max_digits=10,
        description="Physical height in meters",
    )

    @model_validator(mode="after")
    def validate_name(self) -> "RoomUpdate":
        if "name" in self.model_fields_set and self.name is None:
            raise ValueError("name cannot be null")
        return self


class RoomCalculations(BaseModel):
    floor_area: Decimal
    ceiling_area: Decimal
    total_wall_area: Decimal
    wall_area_length: Decimal
    wall_area_width: Decimal
    perimeter: Decimal
    total_deduction_area: Decimal | None = None
    net_wall_area: Decimal | None = None


class RoomRead(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    name: str
    description: str | None = None
    length: Decimal | None = None
    width: Decimal | None = None
    height: Decimal | None = None
    is_archived: bool
    created_at: datetime
    updated_at: datetime
    calculations: RoomCalculations | None = None

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def compute_calculations(self) -> "RoomRead":
        if (
            self.calculations is None
            and self.length is not None
            and self.width is not None
            and self.height is not None
        ):
            geom = calculate_room_geometry(self.length, self.width, self.height)
            if geom is not None:
                self.calculations = RoomCalculations(
                    floor_area=geom.floor_area,
                    ceiling_area=geom.ceiling_area,
                    total_wall_area=geom.total_wall_area,
                    wall_area_length=geom.wall_area_length,
                    wall_area_width=geom.wall_area_width,
                    perimeter=geom.perimeter,
                    total_deduction_area=Decimal("0.000"),
                    net_wall_area=geom.total_wall_area,
                )
        return self


class RoomListResponse(BaseModel):
    items: list[RoomRead]
    total: int
