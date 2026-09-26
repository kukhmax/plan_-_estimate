import { OpeningTypeValue } from './opening';

/** One grouped opening row (backend Decimal strings, exact grouping). */
export interface OpeningGroup {
  opening_type: OpeningTypeValue;
  width: string;
  height: string;
  quantity: number;
}

/** Object summary over active rooms (GET /projects/{id}/summary). Every
 * value is a backend Decimal sum of canonical room calculations. */
export interface ProjectSummary {
  room_count: number;
  floor_area: string | null;
  ceiling_area: string | null;
  total_wall_area: string | null;
  total_deduction_area: string | null;
  net_wall_area: string | null;
  reveal_total_length: string | null;
  reveal_total_area: string | null;
  opening_groups: OpeningGroup[];
}

export interface RoomCalculations {
  floor_area: string | number | null;
  ceiling_area: string | number | null;
  total_wall_area: string | number | null;
  wall_area_length: string | number | null;
  wall_area_width: string | number | null;
  perimeter: string | number | null;
  total_deduction_area: string | number | null;
  net_wall_area: string | number | null;
  wall_count?: number | null;
  window_reveal_total_length?: string | number | null;
  window_reveal_total_area?: string | number | null;
  door_reveal_total_length?: string | number | null;
  door_reveal_total_area?: string | number | null;
  reveal_total_length?: string | number | null;
  reveal_total_area?: string | number | null;
}

export interface RoomType {
  id: string;
  project_id: string;
  name: string;
  description: string | null;
  length?: string | number | null;
  width?: string | number | null;
  height?: string | number | null;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
  calculations?: RoomCalculations | null;
  /** Stage 13F-PRE: active openings on active surfaces, grouped server-side. */
  opening_groups?: OpeningGroup[];
}

export interface RoomListResponse {
  items: RoomType[];
  total: number;
}

export interface RoomCreatePayload {
  name: string;
  description?: string | null;
  length?: number | string | null;
  width?: number | string | null;
  height?: number | string | null;
}

export interface RoomUpdatePayload {
  name?: string;
  description?: string | null;
  length?: number | string | null;
  width?: number | string | null;
  height?: number | string | null;
}
