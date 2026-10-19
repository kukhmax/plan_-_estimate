import { apiRequest } from './http';
import { QualityLevelValue, SubstrateValue } from '../types/checklist';
import { SurfaceTypeValue } from '../types/surface';

// The archived inspections (Badania podłoża) of all objects in work (archive cleanup AC-7); restoring uses the route of the inspection,
// deleting for good the purge routes (`structurePurge.ts`).

export interface ArchivedInspectionItem {
  id: string;
  status: 'DRAFT' | 'COMPLETED';
  substrate: SubstrateValue;
  quality_target: QualityLevelValue | null;
  /** FLOOR / CEILING when it targets one; null with no surface = the room itself. */
  plane: 'FLOOR' | 'CEILING' | null;
  created_at: string;
  completed_at: string | null;
  room_id: string;
  room_name: string;
  surface_id: string | null;
  surface_name: string | null;
  surface_type: SurfaceTypeValue | null;
  project_id: string;
  project_name: string;
}

export interface ArchivedInspections {
  items: ArchivedInspectionItem[];
  /** The list holds the first 200; the total is whole. */
  total: number;
}

export function fetchArchivedInspections(): Promise<ArchivedInspections> {
  return apiRequest<ArchivedInspections>('/api/archive/inspections');
}
