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

/**
 * A place known only by its stored name (the photos of the craftsman's page, UX walk: "Wall 1" was shown untranslated): the canonical names
 * of the walls, the floor and the ceiling in the language of the screen, any other name as it is.
 */
export function getPlaceDisplayName(name: string | null | undefined, labels: SurfaceDisplayLabels): string {
  const trimmed = (name ?? '').trim();
  if (GENERATED_WALL_NAME.test(trimmed)) return getSurfaceDisplayName({ name: trimmed, surface_type: 'WALL' }, labels);
  if (CANONICAL_FLOOR_NAMES.has(trimmed)) return labels.floor;
  if (CANONICAL_CEILING_NAMES.has(trimmed)) return labels.ceiling;
  return name ?? '';
}
