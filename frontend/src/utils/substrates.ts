import type { SubstrateValue } from '../types/checklist';
import type { SurfaceTypeValue } from '../types/surface';

/** The substrates of a wall or a ceiling (the first six; they carry a quality scale S / Q, PAINTED and OTHER an optional one). */
export const WALL_SUBSTRATES: readonly SubstrateValue[] = [
  'CONCRETE',
  'GYPSUM_PLASTER',
  'CEMENT_LIME_PLASTER',
  'GYPSUM_BOARD',
  'PAINTED',
  'OTHER',
];

/** The substrates of a floor (UX walk B4): screed, old tile and wooden boards are floor-only and take no quality target; no old paint on a floor (owner 2026-10-30). */
export const FLOOR_SUBSTRATES: readonly SubstrateValue[] = ['SCREED', 'CONCRETE', 'OLD_TILE', 'WOOD_BOARDS', 'OTHER'];

/** Every substrate, for the places that list them all (an inspection of any kind, in the order of the lists). */
export const ALL_SUBSTRATES: readonly SubstrateValue[] = [...WALL_SUBSTRATES, 'SCREED', 'OLD_TILE', 'WOOD_BOARDS'];

/** Substrates that no quality target (S1-S4 / Q1-Q4) is agreed for; mirrors the backend `NO_SCALE_SUBSTRATES`. */
const NO_SCALE: readonly SubstrateValue[] = ['SCREED', 'OLD_TILE', 'WOOD_BOARDS'];

export function hasNoQualityScale(substrate: SubstrateValue | ''): boolean {
  return substrate !== '' && NO_SCALE.includes(substrate);
}

/** The substrates a surface offers: a floor its own, a wall or a ceiling theirs. */
export function substratesFor(surfaceType: SurfaceTypeValue | undefined | null): readonly SubstrateValue[] {
  return surfaceType === 'FLOOR' ? FLOOR_SUBSTRATES : WALL_SUBSTRATES;
}
