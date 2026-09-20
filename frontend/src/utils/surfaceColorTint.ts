/**
 * Deterministic, stable surface_id -> subtle-tint mapping (Stage 10G.2,
 * extracted in Stage 10G.4 so SurfaceList's per-WALL-card tinting reuses the
 * exact same algorithm as EstimateShell's drill-down cards instead of a
 * second, divergent implementation).
 *
 * Depends only on surface_id (never array index / sort position), so the
 * same surface always renders the same tint regardless of list order.
 * Colors are intentionally very light — this is navigation hierarchy, not
 * decoration. The palette uses only Tailwind classes already referenced
 * verbatim in source (no dynamically-generated class names Tailwind's
 * build-time scanner could miss).
 */
export interface SurfaceTint {
  bg: string;
  border: string;
}

const SURFACE_TINT_PALETTE: readonly SurfaceTint[] = [
  { bg: 'bg-blue-50', border: 'border-blue-100' },
  { bg: 'bg-emerald-50', border: 'border-emerald-100' },
  { bg: 'bg-amber-50', border: 'border-amber-100' },
  { bg: 'bg-rose-50', border: 'border-rose-100' },
  { bg: 'bg-violet-50', border: 'border-violet-100' },
  { bg: 'bg-teal-50', border: 'border-teal-100' },
];

const NEUTRAL_CARD_TINT: SurfaceTint = { bg: 'bg-white', border: 'border-slate-200' };

// FNV-1a 32-bit — cheap, stable, well-distributed for short UUID strings.
export function hashSurfaceId(surfaceId: string): number {
  let hash = 0x811c9dc5;
  for (let i = 0; i < surfaceId.length; i++) {
    hash ^= surfaceId.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return hash >>> 0;
}

export function surfaceCardTint(surfaceId: string | null): SurfaceTint {
  if (surfaceId === null) return NEUTRAL_CARD_TINT;
  return SURFACE_TINT_PALETTE[hashSurfaceId(surfaceId) % SURFACE_TINT_PALETTE.length];
}
