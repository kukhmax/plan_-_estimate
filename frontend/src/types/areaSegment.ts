export type AreaPlane = 'FLOOR' | 'CEILING';
export type AreaOperation = 'ADD' | 'SUBTRACT';

export interface AreaSegmentType {
  id: string;
  room_id: string;
  /** Canonical plane Surface.id (Stage 10C.1A); mirrors backend AreaSegmentRead. */
  surface_id?: string | null;
  plane: AreaPlane;
  operation: AreaOperation;
  width: string | number;
  height: string | number;
  position: number | null;
  label: string | null;
  area: string | number | null;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface PlaneAreaSummary {
  base_area: string | number | null;
  adjustment_area: string | number;
  net_area: string | number;
}

export interface AreaSegmentListResponse {
  items: AreaSegmentType[];
  total: number;
  planes?: Record<AreaPlane, PlaneAreaSummary>;
}

export interface AreaSegmentCreatePayload {
  plane: AreaPlane;
  operation: AreaOperation;
  width: number | string;
  height: number | string;
  position?: number | null;
  label?: string | null;
}

export interface AreaSegmentUpdatePayload {
  operation?: AreaOperation;
  width?: number | string;
  height?: number | string;
  position?: number | null;
  label?: string | null;
}
