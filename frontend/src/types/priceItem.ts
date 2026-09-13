import { QualityLevelValue } from './checklist';

export type PriceCategoryValue =
  | 'PREPARATION'
  | 'SKIM_COAT'
  | 'PLASTER'
  | 'DRYWALL'
  | 'PAINTING'
  | 'GLASS_FIBER'
  | 'MICROCEMENT'
  | 'DECORATIVE'
  | 'REVEAL'
  | 'MATERIAL'
  | 'OTHER';

export type PriceUnitValue = 'M2' | 'LM' | 'PCS' | 'HOUR' | 'DAY' | 'FLAT';

export type PriceScopeValue = 'LABOR' | 'MATERIAL' | 'LABOR_AND_MATERIAL';

export const PRICE_CATEGORIES: readonly PriceCategoryValue[] = [
  'PREPARATION',
  'SKIM_COAT',
  'PLASTER',
  'DRYWALL',
  'PAINTING',
  'GLASS_FIBER',
  'MICROCEMENT',
  'DECORATIVE',
  'REVEAL',
  'MATERIAL',
  'OTHER',
];

export const PRICE_UNITS: readonly PriceUnitValue[] = [
  'M2',
  'LM',
  'PCS',
  'HOUR',
  'DAY',
  'FLAT',
];

export const PRICE_SCOPES: readonly PriceScopeValue[] = [
  'LABOR',
  'MATERIAL',
  'LABOR_AND_MATERIAL',
];

export const PRICE_QUALITY_LEVELS: readonly QualityLevelValue[] = [
  'S1',
  'S2',
  'S3',
  'S4',
  'Q1',
  'Q2',
  'Q3',
  'Q4',
];

/** Money arrives from the backend as a Decimal serialized to a JSON string
 * (never a float). It is formatted on the client without float arithmetic. */
export interface PriceItem {
  id: string;
  code: string;
  name_key: string | null;
  display_name: string | null;
  category: PriceCategoryValue;
  unit: PriceUnitValue;
  price: string;
  currency: string;
  price_scope: PriceScopeValue;
  quality_level: QualityLevelValue | null;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface PriceItemListResponse {
  items: PriceItem[];
  total: number;
}

export interface PriceItemListParams {
  archived?: 'active' | 'archived' | 'all';
  category?: PriceCategoryValue;
  search?: string;
}

export interface PriceItemCreatePayload {
  display_name: string;
  category: PriceCategoryValue;
  unit: PriceUnitValue;
  price: string;
  price_scope: PriceScopeValue;
  quality_level: QualityLevelValue | null;
}

export interface PriceItemUpdatePayload {
  display_name?: string;
  category?: PriceCategoryValue;
  unit?: PriceUnitValue;
  price?: string;
  price_scope?: PriceScopeValue;
  quality_level?: QualityLevelValue | null;
}