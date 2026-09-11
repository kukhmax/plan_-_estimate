import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.area_segment import AreaPlane
from app.models.checklist import QualityLevel, Substrate
from app.models.inspection import InspectionStatus


class InspectionCreate(BaseModel):
    """Create an inspection targeting a substrate carrier.

    At most one of surface_id (a WALL surface) or plane (FLOOR/CEILING) may be
    set; neither set means a room-level inspection. Targeting both is invalid.
    """

    template_id: uuid.UUID
    substrate: Substrate
    quality_target: QualityLevel | None = None
    surface_id: uuid.UUID | None = None
    plane: AreaPlane | None = None
    notes: str | None = Field(default=None, max_length=4096)

    @model_validator(mode="after")
    def validate_target(self) -> "InspectionCreate":
        if self.surface_id is not None and self.plane is not None:
            raise ValueError("Inspection cannot target both a surface and a plane")
        return self


class InspectionUpdate(BaseModel):
    substrate: Substrate | None = None
    quality_target: QualityLevel | None = None
    notes: str | None = Field(default=None, max_length=4096)


class InspectionAnswerPayload(BaseModel):
    """A single answer to one template question.

    The populated field must match the question's answer_type; the service
    enforces this against the immutable template snapshot.
    """

    question_id: uuid.UUID
    value_bool: bool | None = None
    value_number: Decimal | None = Field(
        default=None,
        decimal_places=3,
        max_digits=10,
    )
    value_text: str | None = Field(default=None, max_length=4096)
    option_key: str | None = Field(default=None, max_length=120)
    option_keys: list[str] | None = None

    @model_validator(mode="after")
    def validate_choice_exclusive(self) -> "InspectionAnswerPayload":
        if self.option_key is not None and self.option_keys is not None:
            raise ValueError("Cannot set both option_key and option_keys")
        return self


class InspectionAnswersPut(BaseModel):
    answers: list[InspectionAnswerPayload]


class InspectionAnswerRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    question_id: uuid.UUID
    value_bool: bool | None = None
    value_number: Decimal | None = None
    value_text: str | None = None
    option_key: str | None = None
    option_keys: list[str] | None = None
    updated_at: datetime


class InspectionFindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    finding_key: str
    label_key: str | None = None
    value_snapshot: dict | None = None
    is_active: bool
    resolved_at: datetime | None = None
    position: int | None = None
    answer_id: uuid.UUID | None = None
    question_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class InspectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    room_id: uuid.UUID
    surface_id: uuid.UUID | None = None
    plane: AreaPlane | None = None
    template_id: uuid.UUID
    substrate: Substrate
    quality_target: QualityLevel | None = None
    status: InspectionStatus
    notes: str | None = None
    completed_at: datetime | None = None
    is_archived: bool
    created_at: datetime
    updated_at: datetime


class InspectionDetailRead(InspectionRead):
    answers: list[InspectionAnswerRead] = []


class InspectionFindingListResponse(BaseModel):
    items: list[InspectionFindingRead]
    total: int


class InspectionAnswerListResponse(BaseModel):
    items: list[InspectionAnswerRead]
    total: int


class InspectionListResponse(BaseModel):
    items: list[InspectionRead]
    total: int
