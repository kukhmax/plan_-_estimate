"""Pydantic schemas for Stage 11B.2 recommendation materialization/lifecycle.

Read schemas map from ORM attributes. `current_price_item` is a read-time-only
PriceBook resolution preview computed by the service/endpoint and attached as
a transient attribute — it is never persisted and never touches
`resolved_price_item_id`, which stays reserved as the Stage 11C acceptance
snapshot. `None` means the semantic `recommended_work_code` does not
currently resolve to any owner PriceItem; a non-null value with
`is_archived=True` means it resolves but cannot be newly accepted per Stage
10's existing archived-item rule. Market/reference prices are never
substituted here or anywhere else.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.work_recommendation import (
    WorkRecommendationStatus,
    WorkRecommendationTargetKind,
    WorkRecommendationTriggerType,
)
from app.schemas.work_plan import SurfacePriceItemSummaryRead


class WorkRecommendationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    trigger_type: WorkRecommendationTriggerType
    trigger_code: str
    source_signature: str
    inspection_id: uuid.UUID
    room_id: uuid.UUID
    surface_id: uuid.UUID | None
    target_kind: WorkRecommendationTargetKind
    recommended_work_code: str
    status: WorkRecommendationStatus
    is_active: bool
    resolved_at: datetime | None
    accepted_at: datetime | None
    dismissed_at: datetime | None
    resolved_price_item_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
    current_price_item: SurfacePriceItemSummaryRead | None = None


class WorkRecommendationListResponse(BaseModel):
    items: list[WorkRecommendationRead]
    total: int


class WorkRecommendationEvaluateResponse(BaseModel):
    """Result of one explicit room-wide reconciliation pass.

    `items`/`total` are the room's full current ACTIVE set after
    reconciliation (mirrors RiskDetailResponse's own evaluate-response shape),
    not just the rows touched this call.
    """

    created: int
    reactivated: int
    unchanged: int
    resolved: int
    items: list[WorkRecommendationRead]
    total: int
