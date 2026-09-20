import { SurfaceTypeValue } from '../types/surface';

/**
 * Deterministic, type-only card tint for FLOOR/CEILING (Stage 10G.4 mobile
 * navigation polish, refined in a follow-up round).
 *
 * WALL cards now use the per-surface-id deterministic hash tint instead
 * (see `surfaceColorTint.ts`, extracted from the existing Stage 10G.2
 * Estimate drill-down helper) so individual walls are distinguishable from
 * each other, not just from floors/ceilings. FLOOR and CEILING keep a
 * single stable semantic color each — canonical planes never render inside
 * SurfaceList's own WALL card list (AreaSegmentList is their sole
 * representation), so there is no risk of two different floors/ceilings
 * needing to be told apart the way walls do.
 *
 * `badge` is a single neutral style (white pill, slate text) — it needs to
 * stay legible against whichever `bg` a card actually has, and WALL cards no
 * longer share one fixed background, so per-type badge coloring was dropped.
 */
export interface SurfaceTypeTint {
  bg: string;
  border: string;
  badge: string;
}

const NEUTRAL_BADGE = 'bg-white text-slate-700';

const SURFACE_TYPE_TINT: Record<SurfaceTypeValue, SurfaceTypeTint> = {
  // Unused for card backgrounds now (WALL uses the per-id hash tint) but
  // kept as a sane fallback in case this helper is ever reused for WALL.
  WALL: { bg: 'bg-blue-50', border: 'border-blue-100', badge: NEUTRAL_BADGE },
  // Warm/sand tint.
  FLOOR: { bg: 'bg-orange-50', border: 'border-orange-100', badge: NEUTRAL_BADGE },
  // Cool gray-blue tint.
  CEILING: { bg: 'bg-slate-100', border: 'border-slate-300', badge: NEUTRAL_BADGE },
  OTHER: { bg: 'bg-white', border: 'border-slate-200', badge: NEUTRAL_BADGE },
};

export function surfaceTypeTint(surfaceType: SurfaceTypeValue): SurfaceTypeTint {
  return SURFACE_TYPE_TINT[surfaceType] ?? SURFACE_TYPE_TINT.OTHER;
}
