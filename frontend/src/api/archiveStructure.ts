import { apiRequest } from './http';
import { SurfaceTypeValue } from '../types/surface';

// The archived rooms and surfaces of all objects in work (archive cleanup AC-4a); restoring uses the routes of the room / surface.

export interface ArchivedRoomItem {
  id: string;
  name: string;
  project_id: string;
  project_name: string;
}

export interface ArchivedSurfaceItem {
  id: string;
  name: string;
  surface_type: SurfaceTypeValue;
  room_id: string;
  room_name: string;
  project_id: string;
  project_name: string;
}

export interface ArchivedStructure {
  rooms: ArchivedRoomItem[];
  surfaces: ArchivedSurfaceItem[];
  /** The lists hold the first 200; the totals are whole. */
  rooms_total: number;
  surfaces_total: number;
}

export function fetchArchivedStructure(): Promise<ArchivedStructure> {
  return apiRequest<ArchivedStructure>('/api/archive/structure');
}
