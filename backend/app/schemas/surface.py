import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

from app.domain.rules.room_geometry import (
    calculate_surface_gross_area,
    calculate_wall_net_area,
)
from app.models.surface import SurfaceType
from app.schemas.client_id import ClientId


class SurfaceCreate(BaseModel):
    id: ClientId
    name: str = Field(min_length=1, max_length=255)
    surface_type: SurfaceType
    description: str | None = Field(default=None, max_length=4096)
    position: int | None = Field(
        default=None,
        ge=0,
        description="Sequential position of the surface within the room",
    )
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
    position: int | None = Field(
        default=None,
        ge=0,
        description="Sequential position of the surface within the room",
    )
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


class SurfacePartRead(BaseModel):
    """One part of a merged wall: the size of a wall that was joined into it (the first part is the wall's own size)."""

    id: uuid.UUID
    source_surface_id: uuid.UUID | None = None
    position: int
    width: Decimal
    height: Decimal

    model_config = {"from_attributes": True}


class SurfaceMergeRequest(BaseModel):
    """The walls to join, in the order they were chosen: the first one stays (it keeps the plan), the others are archived into it."""

    surface_ids: list[uuid.UUID] = Field(min_length=2, max_length=12)


class SurfacePartUpdate(BaseModel):
    width: Decimal = Field(gt=0, decimal_places=3, max_digits=10)
    height: Decimal = Field(gt=0, decimal_places=3, max_digits=10)


class SurfaceRead(BaseModel):
    id: uuid.UUID
    room_id: uuid.UUID
    name: str
    surface_type: SurfaceType
    description: str | None = None
    position: int | None = None
    width: Decimal | None = None
    height: Decimal | None = None
    gross_area: Decimal | None = None
    deduction_area: Decimal | None = None
    net_area: Decimal | None = None
    # Usability U-7: how many works the saved plan of the surface holds (filled by the list; 0 elsewhere and for a surface with no plan).
    planned_work_count: int = 0
    # Merged walls: the parts of a merged wall (empty for an ordinary wall; its `gross_area` is their sum) and, for a wall that was joined
    # into another one, that merged wall.
    parts: list[SurfacePartRead] = []
    merged_into_id: uuid.UUID | None = None
    is_archived: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def compute_areas(self) -> "SurfaceRead":
        if self.gross_area is None and self.width is not None and self.height is not None:
            self.gross_area = calculate_surface_gross_area(
                self.surface_type,
                self.width,
                self.height,
            )
        if self.surface_type == SurfaceType.WALL:
            if self.gross_area is not None:
                if self.deduction_area is None:
                    self.deduction_area = Decimal("0.000")
                if self.net_area is None:
                    self.net_area = calculate_wall_net_area(
                        self.gross_area,
                        self.deduction_area,
                    )
            else:
                self.net_area = None
        else:
            self.deduction_area = None
            self.net_area = None
        return self


class SurfaceListResponse(BaseModel):
    items: list[SurfaceRead]
    total: int
