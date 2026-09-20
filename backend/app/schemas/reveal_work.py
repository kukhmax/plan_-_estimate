"""Opening reveal work plan schemas (Stage 10E).

Reuses SurfacePriceItemSummaryRead from work_plan so the UI gets a consistent
Price Book representation across surface and reveal work lists.
"""
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.work_plan import SurfacePriceItemSummaryRead


class RevealWorkItemRead(BaseModel):
    id: uuid.UUID
    position: int
    price_item_id: uuid.UUID
    price_item: SurfacePriceItemSummaryRead

    model_config = ConfigDict(from_attributes=True)


class RevealWorkListResponse(BaseModel):
    opening_id: uuid.UUID
    items: list[RevealWorkItemRead]


class RevealWorkSetRequest(BaseModel):
    """Ordered list of PriceItem IDs to set as the opening's reveal works.

    Duplicates are allowed (e.g. two-coat rows of the same item).
    Empty list clears all works — equivalent to DELETE.
    """
    price_item_ids: list[uuid.UUID] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class RevealWorkApplyResult(BaseModel):
    """Result of atomically copying a source opening's reveal work selection
    to every other reveal-enabled, non-archived opening in the same room
    (Stage 10G.4). Only the ordered PriceItem selection was copied — target
    geometry/quantities remain entirely their own and backend-authoritative.
    """
    source_opening_id: uuid.UUID
    target_count: int
    target_opening_ids: list[uuid.UUID]
