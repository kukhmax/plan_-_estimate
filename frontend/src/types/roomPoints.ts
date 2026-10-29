/** The points and routes of a room (V2-10); mirrors backend `schemas/room_point.py`. A quantity arrives as a string with two places. */
import type { PriceCategoryValue, PriceUnitValue } from './priceItem';

export interface PointItem {
  id: string;
  code: string;
  name_key: string | null;
  display_name: string | null;
  category: PriceCategoryValue;
  unit: PriceUnitValue;
  price: string | null;
  is_archived: boolean;
}

export interface RoomPoint {
  id: string;
  room_id: string;
  quantity: string;
  note: string | null;
  item: PointItem;
  /** 'TRADE_LINK': carried over from a craftsman's answer; null: typed by the owner. */
  source?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PointFields {
  price_item_id: string;
  quantity: string;
  note: string | null;
}

export interface AddToEstimateResult {
  added: number;
  already: number;
  skipped: Array<{ point_id: string; code: string }>;
}

export interface PointsPackResult {
  created: number;
  existing: number;
}

export const MAX_POINT_NOTE_LENGTH = 500;
