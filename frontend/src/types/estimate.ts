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
}

export interface EstimateRead extends EstimateSummaryRead {
  lines: EstimateLineRead[];
}
