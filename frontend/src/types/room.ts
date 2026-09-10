export interface RoomCalculations {
  floor_area: string | number;
  ceiling_area: string | number;
  total_wall_area: string | number;
  wall_area_length: string | number;
  wall_area_width: string | number;
  perimeter: string | number;
  total_deduction_area: string | number | null;
  net_wall_area: string | number | null;
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
