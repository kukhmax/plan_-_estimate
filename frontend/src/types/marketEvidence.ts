import { PriceUnitValue } from './priceItem';

/** Controlled SourceType values emitted by the 9E.6A backend (mirror of
 * backend.app.models.market_evidence.SourceType). */
export type MarketSourceType =
  | 'CONTRACTOR_PRICE_LIST'
  | 'MARKETPLACE'
  | 'MANUFACTURER'
  | 'MATERIAL_STORE'
  | 'INDUSTRY_ARTICLE'
  | 'OWN_PRICE'
  | 'OTHER';

/** One observed quote backing a market reference. Exactly one evidence mode is
 * populated: SINGLE (quoted_price_single), RANGE (quoted_price_min/max), or
 * QUALITATIVE (note only). Money fields arrive as Decimal JSON strings. */
export interface PriceSource {
  id: string;
  source_name: string;
  source_type: MarketSourceType;
  source_url: string | null;
  source_region: string | null;
  quoted_price_min: string | null;
  quoted_price_max: string | null;
  quoted_price_single: string | null;
  quoted_unit: PriceUnitValue | null;
  note: string | null;
  checked_at: string;
}

/** Market evidence for one PriceItem in one region (read-only supporting data;
 * never the owner's working PriceItem.price). */
export interface PriceMarketReference {
  id: string;
  region: string;
  unit: PriceUnitValue;
  currency: string;
  market_min: string;
  market_max: string;
  reference_price: string | null;
  methodology_note: string | null;
  checked_at: string;
  sources: PriceSource[];
}

export interface PriceMarketReferenceListResponse {
  items: PriceMarketReference[];
  total: number;
}