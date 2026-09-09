export type SurfaceTypeValue = 'WALL' | 'CEILING' | 'FLOOR' | 'OTHER';

export interface SurfaceType {
  id: string;
  room_id: string;
  name: string;
  surface_type: SurfaceTypeValue;
  description: string | null;
  is_archived: boolean;
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
}

export interface SurfaceUpdatePayload {
  name?: string;
  surface_type?: SurfaceTypeValue;
  description?: string | null;
}
