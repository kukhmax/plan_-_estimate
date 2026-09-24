import { OrderedPriceItemSelection, PlannedWorkCoefficientOptionRead, SurfacePriceItemSummaryRead } from './workPlan';

// Stage 10G.4 — Opening reveal work planning (Stage 10E contract). The
// backend reuses the exact same SurfacePriceItemSummaryRead shape as the
// Surface Work Plan for price_item, so the UI gets a consistent Price Book
// representation across both.
export interface RevealWorkItemRead {
  id: string;
  position: number;
  price_item_id: string;
  price_item: SurfacePriceItemSummaryRead;
  coefficient_options?: PlannedWorkCoefficientOptionRead[];
}

export interface RevealWorkListResponse {
  opening_id: string;
  items: RevealWorkItemRead[];
}

// PUT is a full replacement of the ordered list — duplicates allowed, empty
// list clears all works (equivalent to DELETE), per the existing backend
// contract (OpeningRevealWorkService.set_works).
// Stage 12D/12F: accepts either price_item_ids or planned_works (with coefficients).
export interface RevealWorkSetPayload {
  price_item_ids?: string[];
  planned_works?: OrderedPriceItemSelection[];
}

// Stage 10G.4 — result of atomically copying a source opening's reveal work
// selection to every other reveal-enabled, non-archived opening in the room.
// Only the ordered PriceItem selection is copied; target geometry/quantities
// stay entirely their own and backend-authoritative.
export interface RevealWorkApplyResult {
  source_opening_id: string;
  target_count: number;
  target_opening_ids: string[];
}
