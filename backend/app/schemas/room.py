import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.domain.rules.room_geometry import calculate_room_geometry
from app.models.opening import OpeningType


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
    floor_area: Decimal | None = None
    ceiling_area: Decimal | None = None
    total_wall_area: Decimal | None = None
    wall_area_length: Decimal | None = None
    wall_area_width: Decimal | None = None
    perimeter: Decimal | None = None
    total_deduction_area: Decimal | None = None
    net_wall_area: Decimal | None = None
    wall_count: int | None = None
    window_reveal_total_length: Decimal | None = None
    window_reveal_total_area: Decimal | None = None
    door_reveal_total_length: Decimal | None = None
    door_reveal_total_area: Decimal | None = None
    reveal_total_length: Decimal | None = None
    reveal_total_area: Decimal | None = None


class OpeningGroupRead(BaseModel):
    """Read-only opening summary row (Stage 13F-PRE): active openings on
    active surfaces grouped by type + exact width + height, quantities summed."""

    opening_type: OpeningType
    width: Decimal
    height: Decimal
    quantity: int

    model_config = {"from_attributes": True}


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
    # Stage 13F-PRE: which openings stand behind the deduction/reveal figures.
    opening_groups: list[OpeningGroupRead] = Field(default_factory=list)

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


class ProjectSummaryRead(BaseModel):
    """Object-level aggregate (Stage 13F-PRE) over ACTIVE rooms only.

    Every area/length is the Decimal sum of the rooms' canonical
    `RoomCalculations` values (the same read model the room screen shows);
    nothing is recomputed. A metric is null when no active room provides it.
    Per room net = gross - deductions exactly, so the sums keep that identity.
    Reveal area is its own metric and never part of wall area.
    """

    room_count: int
    floor_area: Decimal | None = None
    ceiling_area: Decimal | None = None
    total_wall_area: Decimal | None = None
    total_deduction_area: Decimal | None = None
    net_wall_area: Decimal | None = None
    reveal_total_length: Decimal | None = None
    reveal_total_area: Decimal | None = None
    opening_groups: list[OpeningGroupRead] = Field(default_factory=list)
