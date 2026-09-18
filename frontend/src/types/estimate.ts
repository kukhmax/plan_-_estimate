export type EstimateStatusValue = 'DRAFT' | 'FINAL' | 'ACCEPTED' | 'ARCHIVED';
export type LineOriginValue = 'PLANNED_WORK' | 'MANUAL';
export type QuantitySourceValue = 'SURFACE_NET_AREA' | 'REVEAL_LENGTH' | 'REVEAL_AREA' | 'MANUAL';

export interface EstimateSummaryRead {
  id: string;
  project_id: string;
  version: number;
  status: EstimateStatusValue;
  name: string | null;
  total: string | null;
  currency: string;
  created_at: string;
  updated_at: string;
}

export interface EstimateListResponse {
  items: EstimateSummaryRead[];
  total: number;
}

export interface EstimateLineRead {
  id: string;
  estimate_id: string;
  origin: LineOriginValue;
  position: number;
  description: string;
  item_code: string | null;
  unit: string;
  scope: string;
  currency: string;
  source_quantity: string | null;
  quantity: string;
  quantity_source: QuantitySourceValue;
  quantity_overridden: boolean;
  unit_price: string | null;
  price_override: boolean;
  amount: string | null;
  price_item_id: string | null;
  plan_id: string | null;
  planned_work_id: string | null;
  surface_id: string | null;
  room_id: string | null;
  opening_id: string | null;
  // Presentation metadata resolved live at read time — optional AND nullable:
  // some response-construction paths may omit these keys entirely rather
  // than send an explicit null, so callers must not assume `!== null` alone
  // rules out `undefined`.
  room_name?: string | null;
  surface_name?: string | null;
  surface_type_value?: string | null;
  opening_name?: string | null;
  opening_type_value?: string | null;
}

export interface EstimateRead extends EstimateSummaryRead {
  lines: EstimateLineRead[];
}

// PATCH body for a DRAFT line (Stage 10E contract). Every field is optional —
// an omitted key means "leave unchanged". `unit_price: null` is a distinct,
// meaningful operation (marks the line Do ustalenia / price_override=true);
// `quantity: null` must never be sent (rejected by the backend — NOT NULL).
// `reset_quantity_override`/`reset_price_override` must not be combined with
// a simultaneous `quantity`/`unit_price` assignment on the same field.
export interface EstimateLineUpdatePayload {
  quantity?: string;
  unit_price?: string | null;
  reset_price_override?: boolean;
  reset_quantity_override?: boolean;
}

// Stage 10G.3B — regeneration preview/confirm (Stage 10E contract). Both
// regenerate-preview and regenerate return this same shape; preview never
// mutates the estimate, regenerate applies it in-place.
export type LineChangeTypeValue = 'ADDED' | 'REMOVED' | 'UPDATED';

export interface LineChangeEntry {
  change_type: LineChangeTypeValue;
  estimate_line_id: string | null;
  planned_work_id: string;
  surface_id: string | null;
  opening_id: string | null;
  item_code: string | null;
  description: string;
  unit: string;
  old_source_quantity: string | null;
  new_source_quantity: string | null;
  old_unit_price: string | null;
  new_unit_price: string | null;
  quantity_overridden: boolean;
  price_override: boolean;
  // Stage 10G.3B provenance follow-up — resolved live from current DB
  // records, analogous to EstimateLineRead's presentation fields. Optional
  // AND nullable: some response-construction paths may omit these keys
  // entirely rather than send an explicit null (10G.2 crash-regression
  // protection), and a REMOVED entry's referenced Surface/Opening may no
  // longer exist, in which case the field is null rather than fabricated.
  room_name?: string | null;
  surface_name?: string | null;
  surface_type_value?: string | null;
  opening_name?: string | null;
  opening_type_value?: string | null;
}

export interface RegenerationPreviewResponse {
  added: number;
  removed: number;
  updated: number;
  preserved_manual: number;
  changes: LineChangeEntry[];
}

// Stage 10G.3C — POST body for a MANUAL EstimateLine (Stage 10E contract).
// scope/unit are plain strings here (matching EstimateLineRead), but the UI
// only ever offers PriceScopeValue/PriceUnitValue options; LABOR_AND_MATERIAL
// is never offered — the backend rejects it for MANUAL lines (no PriceBook
// source to split into labor/material components). currency is optional and,
// when sent, must match the estimate's own currency (Stage 10E contract) —
// callers always send the estimate's authoritative currency, never a
// user-editable value.
export interface ManualLineCreatePayload {
  description: string;
  scope: string;
  unit: string;
  quantity: string;
  unit_price?: string | null;
  currency?: string;
}
