"""Opening reveal work plan schemas (Stage 10E).

Reuses SurfacePriceItemSummaryRead from work_plan so the UI gets a consistent
Price Book representation across surface and reveal work lists.
"""
import uuid

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.work_plan import (
    OrderedPriceItemSelection,
    PlannedWorkCoefficientOptionRead,
    SurfacePriceItemSummaryRead,
)


class RevealWorkItemRead(BaseModel):
    id: uuid.UUID
    position: int
    price_item_id: uuid.UUID
    price_item: SurfacePriceItemSummaryRead
    coefficient_options: list[PlannedWorkCoefficientOptionRead] = Field(
        default_factory=list
    )

    model_config = ConfigDict(from_attributes=True)


class RevealWorkListResponse(BaseModel):
    opening_id: uuid.UUID
    items: list[RevealWorkItemRead]


class RevealWorkSetRequest(BaseModel):
    """Ordered list of PriceItem IDs to set as the opening's reveal works.

    Duplicates are allowed (e.g. two-coat rows of the same item).
    Empty list clears all works — equivalent to DELETE.

    ``planned_works`` (Stage 12D) is the optional, richer replacement that
    additionally carries each occurrence's coefficient selection, reusing
    the exact same `OrderedPriceItemSelection` shape as the Surface Work
    Plan contract. A request provides EITHER field, never both non-empty at
    once. Every existing client sends only ``price_item_ids`` and MUST keep
    working unchanged.
    """
    price_item_ids: list[uuid.UUID] = Field(default_factory=list)
    planned_works: list[OrderedPriceItemSelection] | None = None

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def _check_exclusive_selection(self) -> "RevealWorkSetRequest":
        if self.planned_works is not None and self.price_item_ids:
            raise ValueError(
                "provide either price_item_ids (legacy) or planned_works "
                "(supports coefficients), not both"
            )
        return self


class RevealWorkApplyResult(BaseModel):
    """Result of atomically copying a source opening's reveal work selection
    to every other reveal-enabled, non-archived opening in the same room
    (Stage 10G.4). Only the ordered PriceItem selection was copied — target
    geometry/quantities remain entirely their own and backend-authoritative.
    """
    source_opening_id: uuid.UUID
    target_count: int
    target_opening_ids: list[uuid.UUID]
