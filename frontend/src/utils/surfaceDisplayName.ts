import { SurfaceTypeValue } from '../types/surface';

export interface SurfaceDisplayLabels {
  wall: string;
  floor: string;
  ceiling: string;
}

/** Presentation-metadata callers (e.g. estimate line provenance) may have a
 * surface name that is absent (null) or omitted entirely (undefined) at
 * runtime; `SurfaceType.name` itself stays required for callers backed by a
 * real persisted Surface record. */
export interface SurfaceNameInput {
  name: string | null | undefined;
  surface_type: SurfaceTypeValue | string | null | undefined;
}

const GENERATED_WALL_NAME = /^(?:Wall|Ściana|Стена)\s+([1-9]\d*)$/;
const CANONICAL_FLOOR_NAMES = new Set(['Floor', 'Podłoga', 'Пол']);
const CANONICAL_CEILING_NAMES = new Set(['Ceiling', 'Sufit', 'Потолок']);

export function getSurfaceDisplayName(
  surface: SurfaceNameInput,
  labels: SurfaceDisplayLabels,
): string {
  const rawName = surface.name ?? '';
  const normalizedName = rawName.trim();

  if (surface.surface_type === 'WALL') {
    const match = GENERATED_WALL_NAME.exec(normalizedName);
    return match ? `${labels.wall} ${match[1]}` : rawName;
  }

  if (surface.surface_type === 'FLOOR' && CANONICAL_FLOOR_NAMES.has(normalizedName)) {
    return labels.floor;
  }

  if (surface.surface_type === 'CEILING' && CANONICAL_CEILING_NAMES.has(normalizedName)) {
    return labels.ceiling;
  }

  return rawName;
}
