import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.checklist import QualityLevel, Substrate
from app.models.communication import CommunicationCategory
from app.models.risk import RiskSeverity
from app.schemas.risk import RiskSourceFindingRead


class CommunicationApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    inspection_id: uuid.UUID
    phrase_code: str
    phrase_version: int
    category: CommunicationCategory
    priority: int
    phrase_key: str
    why_key: str | None
    seed_key: str | None
    source_kind: str
    source_signature: str
    is_active: bool
    resolved_at: datetime | None
    position: int | None
    created_at: datetime
    updated_at: datetime


class CommunicationApplicationListResponse(BaseModel):
    items: list[CommunicationApplicationRead]
    total: int


class CommunicationRiskSource(BaseModel):
    kind: Literal["RISK"] = "RISK"
    risk_id: uuid.UUID | None
    risk_code: str | None
    severity: RiskSeverity | None
    risk_is_active: bool | None
    source_findings: list[RiskSourceFindingRead] = []


class CommunicationFindingSnapshot(BaseModel):
    finding_id: uuid.UUID
    label_key: str | None
    value_snapshot: dict | None
    is_active: bool
    position: int | None


class CommunicationFindingSource(BaseModel):
    kind: Literal["FINDING"] = "FINDING"
    finding_key: str
    findings: list[CommunicationFindingSnapshot] = []


class CommunicationQualitySource(BaseModel):
    kind: Literal["QUALITY"] = "QUALITY"
    substrate: Substrate | None
    quality_level: QualityLevel | None


CommunicationSource = Annotated[
    CommunicationRiskSource
    | CommunicationFindingSource
    | CommunicationQualitySource,
    Field(discriminator="kind"),
]


class CommunicationApplicationDetailRead(CommunicationApplicationRead):
    source: CommunicationSource