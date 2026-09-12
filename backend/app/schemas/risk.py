import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.risk import RiskSeverity


class RiskEvaluateRequest(BaseModel):
    """Request body for an idempotent risk evaluation of one inspection."""

    inspection_id: uuid.UUID


class RiskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    room_id: uuid.UUID
    inspection_id: uuid.UUID
    risk_code: str
    rule_code: str
    rule_version: int
    severity: RiskSeverity
    title_key: str
    explanation_key: str
    consequence_key: str
    mitigation_key: str
    communication_key: str
    warranty_exclusion_candidate: bool
    blocks_finishing: bool
    source_signature: str
    is_active: bool
    resolved_at: datetime | None
    position: int | None
    created_at: datetime
    updated_at: datetime


class RiskSourceFindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    finding_id: uuid.UUID | None
    finding_key_snapshot: str
    value_snapshot: dict | None
    position: int | None


class RiskDetailRead(RiskRead):
    source_findings: list[RiskSourceFindingRead] = []


class RiskListResponse(BaseModel):
    items: list[RiskRead]
    total: int


class RiskDetailResponse(BaseModel):
    items: list[RiskDetailRead]
    total: int
