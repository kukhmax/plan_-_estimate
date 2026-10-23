export type SurfaceTypeValue = 'WALL' | 'CEILING' | 'FLOOR' | 'OTHER';

export interface SurfaceType {
  id: string;
  room_id: string;
  name: string;
  surface_type: SurfaceTypeValue;
  description: string | null;
  position?: number | null;
  width?: string | number | null;
  height?: string | number | null;
  gross_area?: string | number | null;
  deduction_area?: string | number | null;
  net_area?: string | number | null;
  /** How many works the saved plan of the surface holds (usability U-7; the list fills it). */
  planned_work_count?: number;
  /** Merged walls: the parts of a merged wall (the area is their sum); empty for an ordinary wall. */
  parts?: SurfacePart[];
  /** A wall that was joined into another one: that merged wall. */
  merged_into_id?: string | null;
  is_archived: boolean;
  /** Made on the phone and not yet accepted by the server (Stage 19E): the screens mark it. */
  _pending?: boolean;
  created_at: string;
  updated_at: string;
}

export interface SurfaceListResponse {
  items: SurfaceType[];
  total: number;
}

export interface SurfaceCreatePayload {
  name: string;
  surface_type: SurfaceTypeValue;
  description?: string | null;
  position?: number | null;
  width?: number | string | null;
  height?: number | string | null;
}

export interface SurfaceUpdatePayload {
  name?: string;
  surface_type?: SurfaceTypeValue;
  description?: string | null;
  position?: number | null;
  width?: number | string | null;
  height?: number | string | null;
}

/** One part of a merged wall: the size of a wall that was joined into it (the first part is the wall's own size). */
export interface SurfacePart {
  id: string;
  source_surface_id: string | null;
  position: number;
  width: string | number;
  height: string | number;
}
