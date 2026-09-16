import { SurfaceType } from '../types/surface';

export interface SurfaceDisplayLabels {
  wall: string;
  floor: string;
  ceiling: string;
}

const GENERATED_WALL_NAME = /^(?:Wall|Ściana|Стена)\s+([1-9]\d*)$/;
const CANONICAL_FLOOR_NAMES = new Set(['Floor', 'Podłoga', 'Пол']);
const CANONICAL_CEILING_NAMES = new Set(['Ceiling', 'Sufit', 'Потолок']);

export function getSurfaceDisplayName(
  surface: Pick<SurfaceType, 'name' | 'surface_type'>,
  labels: SurfaceDisplayLabels,
): string {
  const normalizedName = surface.name.trim();

  if (surface.surface_type === 'WALL') {
    const match = GENERATED_WALL_NAME.exec(normalizedName);
    return match ? `${labels.wall} ${match[1]}` : surface.name;
  }

  if (surface.surface_type === 'FLOOR' && CANONICAL_FLOOR_NAMES.has(normalizedName)) {
    return labels.floor;
  }

  if (surface.surface_type === 'CEILING' && CANONICAL_CEILING_NAMES.has(normalizedName)) {
    return labels.ceiling;
  }

  return surface.name;
}
