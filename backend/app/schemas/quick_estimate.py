"""Quick estimate API schemas (V2-4; docs/V2_4_PLAN_RU.md)."""
import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.domain.data.quick_estimate_data import MAX_DIMENSION_M, MAX_ROOMS
from app.models.checklist import QualityLevel, Substrate
from app.schemas.price import PriceItemRead


class QuickWorkRead(BaseModel):
    code: str
    ceiling_code: str
    default_on: bool


class QuickEstimateOptions(BaseModel):
    """What the screen offers: the works (in order) with the price rows behind them, the substrates and the defaults."""

    works: list[QuickWorkRead]
    items: list[PriceItemRead]
    substrates: list[Substrate]
    default_substrate: Substrate
    default_quality: QualityLevel


class QuickRoom(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    length: Decimal = Field(gt=0, le=MAX_DIMENSION_M, decimal_places=3, max_digits=10)
    width: Decimal = Field(gt=0, le=MAX_DIMENSION_M, decimal_places=3, max_digits=10)
    height: Decimal = Field(gt=0, le=MAX_DIMENSION_M, decimal_places=3, max_digits=10)

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value


class QuickEstimateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_id: uuid.UUID | None = None
    client_name: str | None = Field(default=None, max_length=255)
    client_phone: str | None = Field(default=None, max_length=50)
    address: str = Field(min_length=1, max_length=512)
    city: str = Field(min_length=1, max_length=255)
    rooms: list[QuickRoom] = Field(min_length=1, max_length=MAX_ROOMS)
    work_codes: list[str] = Field(min_length=1, max_length=20)
    include_ceiling: bool = False
    substrate: Substrate
    quality_target: QualityLevel

    @model_validator(mode="after")
    def _client_given(self) -> "QuickEstimateCreate":
        if self.client_id is None and not (self.client_name or "").strip():
            raise ValueError("a client is needed: an existing one or a name")
        return self


class QuickEstimateResult(BaseModel):
    project_id: uuid.UUID
    client_id: uuid.UUID
    estimate_id: uuid.UUID
    rooms: int
    lines: int
    unpriced_lines: int
    total: Decimal | None
