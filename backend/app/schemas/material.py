"""The norms and the calculations of materials (V2-11, V2-12). Quantities go out as strings with two places (`schemas/payment.py`); a norm as a plain number without needless zeros."""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer, model_validator

from app.schemas.payment import Out
from app.schemas.room_point import PointItemRead


def _plain(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return text


Plain = Annotated[Decimal, PlainSerializer(_plain, return_type=str, when_used="json")]
Area = Annotated[Decimal, Field(gt=0, le=100000, max_digits=10, decimal_places=2)]
Centimetres = Annotated[Decimal, Field(gt=0, le=1000, max_digits=7, decimal_places=1)]
Millimetres = Annotated[Decimal, Field(gt=0, le=100, max_digits=6, decimal_places=1)]
Metres = Annotated[Decimal, Field(gt=0, le=100000, max_digits=9, decimal_places=2)]


class TileParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    area_m2: Area
    length_cm: Centimetres
    width_cm: Centimetres
    thickness_mm: Millimetres = Decimal(8)
    joint_mm: Millimetres = Decimal(3)
    layout: Literal["STRAIGHT", "DIAGONAL"] = "STRAIGHT"
    waterproof: bool = False
    waterproof_area_m2: Area | None = None
    tape_m: Metres | None = None


class DrywallParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["WALL", "CEILING"]
    area_m2: Area
    layers: Literal[1, 2] = 1
    height_m: Metres | None = None
    perimeter_m: Metres | None = None

    @model_validator(mode="after")
    def _needs(self) -> "DrywallParams":
        if self.kind == "WALL" and self.height_m is None:
            raise ValueError("a wall needs its height")
        if self.kind == "CEILING" and self.perimeter_m is None:
            raise ValueError("a ceiling needs its perimeter")
        return self


Count = Annotated[int, Field(ge=0, le=500)]


class ElectricParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sockets: Count = 0
    switches: Count = 0
    lights: Count = 0
    circuits: Annotated[int, Field(ge=0, le=100)] = 0
    route_m: Metres | None = None

    @model_validator(mode="after")
    def _needs(self) -> "ElectricParams":
        if self.sockets + self.switches + self.lights == 0 and self.route_m is None and self.circuits == 0:
            raise ValueError("an electrical calculation needs at least one point, circuit or route")
        return self


class PlumbingParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    water_points: Count = 0
    drain_points: Count = 0
    manifold_outlets: Annotated[int, Field(ge=0, le=50)] = 0
    pipe_m: Metres | None = None

    @model_validator(mode="after")
    def _needs(self) -> "PlumbingParams":
        if self.water_points + self.drain_points + self.manifold_outlets == 0 and self.pipe_m is None:
            raise ValueError("a plumbing calculation needs at least one point, outlet or pipe")
        return self


class TileCalcCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package: Literal["TILE"]
    title: str | None = Field(default=None, max_length=120)
    params: TileParams


class DrywallCalcCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package: Literal["DRYWALL"]
    title: str | None = Field(default=None, max_length=120)
    params: DrywallParams


class ElectricCalcCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package: Literal["ELECTRIC"]
    title: str | None = Field(default=None, max_length=120)
    params: ElectricParams


class PlumbingCalcCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    package: Literal["PLUMBING"]
    title: str | None = Field(default=None, max_length=120)
    params: PlumbingParams


CalcCreate = Annotated[TileCalcCreate | DrywallCalcCreate | ElectricCalcCreate | PlumbingCalcCreate, Field(discriminator="package")]
PackageName = Literal["TILE", "DRYWALL", "ELECTRIC", "PLUMBING"]


class CalcUpdate(BaseModel):
    """Only what is sent changes; the data of a calculation is replaced whole (the package stays); `title: null` clears the title."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=120)
    params: dict | None = None


class MaterialRead(BaseModel):
    code: str
    name: str
    quantity: Out  # the exact need in `unit_text`
    unit_text: str
    pack_size: Plain | None
    packs: int | None
    pieces: int | None = None
    billing_unit: str
    billing_quantity: Out


class CalcRead(BaseModel):
    id: uuid.UUID
    room_id: uuid.UUID
    package: PackageName
    title: str | None
    params: dict
    materials: list[MaterialRead]
    created_at: datetime
    updated_at: datetime


class CalcsResponse(BaseModel):
    items: list[CalcRead]


class TotalRead(MaterialRead):
    package: PackageName
    price_item_id: uuid.UUID | None
    unit_price: Out | None
    amount: Out | None  # the packs by the price of the linked item; none without a price


class StatementCalc(CalcRead):
    room_name: str


class StatementResponse(BaseModel):
    calcs: list[StatementCalc]
    totals: list[TotalRead]
    amount: Out | None  # the sum of the priced materials
    unpriced: int  # the materials without a price (not linked, or the item has no price)


class NormRead(BaseModel):
    id: uuid.UUID
    code: str
    package: PackageName
    kind: Literal["PARAM", "MATERIAL"]
    name: str
    default_name: str
    unit_text: str
    value: Plain | None
    default_value: Plain | None
    minimum: Plain | None
    maximum: Plain | None
    billing_unit: str | None
    price_item: PointItemRead | None


class NormsResponse(BaseModel):
    items: list[NormRead]


class NormUpdate(BaseModel):
    """A number: `value`; a material: `name` and `price_item_id` (null unties the item); `reset: true` returns the starting value / name and unties the item."""

    model_config = ConfigDict(extra="forbid")

    value: Decimal | None = Field(default=None, max_digits=12, decimal_places=3)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    price_item_id: uuid.UUID | None = None
    reset: bool = False


class AddMaterialsResponse(BaseModel):
    added: int
    already: int
    skipped: list[str]  # the codes of the materials whose item has gone (archived, another unit)


class RouteTotalsResponse(BaseModel):
    """The routes (metres) the owner listed in a room as points and routes, by trade: they are offered to the calculations of the room."""

    electrical_m: Out
    plumbing_m: Out
