import type { UnpricedWork } from '../types/document';
import type { InspectionTarget } from '../types/inspection';

/** The carrier of the inspection that holds a recommendation: its wall, else its FLOOR / CEILING plane, else the room. */
export function inspectionTargetOf(work: Pick<UnpricedWork, 'inspection_surface_id' | 'inspection_plane'>): InspectionTarget {
  if (work.inspection_surface_id) return { kind: 'surface', surfaceId: work.inspection_surface_id };
  if (work.inspection_plane) return { kind: 'plane', plane: work.inspection_plane };
  return { kind: 'room' };
}
