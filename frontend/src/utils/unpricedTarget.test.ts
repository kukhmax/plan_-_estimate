import { describe, expect, it } from 'vitest';
import { inspectionTargetOf } from './unpricedTarget';

describe('inspectionTargetOf (Stage 15H.1)', () => {
  it('leads to the wall, the plane or the room that carries the inspection', () => {
    expect(inspectionTargetOf({ inspection_surface_id: 's1', inspection_plane: null })).toEqual({ kind: 'surface', surfaceId: 's1' });
    expect(inspectionTargetOf({ inspection_surface_id: null, inspection_plane: 'CEILING' })).toEqual({ kind: 'plane', plane: 'CEILING' });
    expect(inspectionTargetOf({ inspection_surface_id: null, inspection_plane: 'FLOOR' })).toEqual({ kind: 'plane', plane: 'FLOOR' });
    expect(inspectionTargetOf({ inspection_surface_id: null, inspection_plane: null })).toEqual({ kind: 'room' });
  });
});
