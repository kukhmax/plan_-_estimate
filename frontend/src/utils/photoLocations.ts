import { fetchOpenings } from '../api/openings';
import { fetchRooms } from '../api/rooms';
import { fetchSurfaces } from '../api/surfaces';
import { OpeningTypeValue } from '../types/opening';
import { PhotoAttachmentRead, PhotoCounts } from '../types/photo';
import { SurfaceTypeValue } from '../types/surface';
import { SurfaceDisplayLabels, getSurfaceDisplayName } from './surfaceDisplayName';

// Names for the location path of the PROJECT-wide photo list (owner clarification C-2 / C-3). A photo stores only its
// leaf target id, and the numbering such as "Ściana 1" exists only in the frontend, so the names come from the
// structure lists of the object. They are loaded lazily when the project-wide section opens and only as deep as the
// photos need: surfaces when some surface / opening has a photo, openings when some opening has one.

export interface PhotoLocationData {
  rooms: Record<string, string>;
  surfaces: Record<string, { roomId: string; name: string; surfaceType: SurfaceTypeValue }>;
  openings: Record<string, { surfaceId: string; roomId: string; type: OpeningTypeValue; name: string | null }>;
  /** False when a request failed: the unresolved parts of a path show a dash instead of a name. */
  complete: boolean;
}

export const EMPTY_LOCATIONS: PhotoLocationData = { rooms: {}, surfaces: {}, openings: {}, complete: false };

const OPENING_CONCURRENCY = 6;

async function inChunks<T, R>(items: readonly T[], size: number, run: (item: T) => Promise<R>): Promise<R[]> {
  const results: R[] = [];
  for (let start = 0; start < items.length; start += size) {
    results.push(...(await Promise.all(items.slice(start, start + size).map(run))));
  }
  return results;
}

export async function loadPhotoLocations(projectId: string, counts: PhotoCounts): Promise<PhotoLocationData> {
  const data: PhotoLocationData = { rooms: {}, surfaces: {}, openings: {}, complete: true };
  const needSurfaces = Object.keys(counts.surfaces).length > 0 || Object.keys(counts.openings).length > 0;
  const needOpenings = Object.keys(counts.openings).length > 0;

  let rooms;
  try {
    rooms = (await fetchRooms(projectId, true)).items;
  } catch {
    return { ...data, complete: false };
  }
  for (const room of rooms) data.rooms[room.id] = room.name;
  if (!needSurfaces) return data;

  const surfaceLists = await Promise.all(
    rooms.map(async (room) => {
      try {
        return (await fetchSurfaces(projectId, room.id, true)).items;
      } catch {
        data.complete = false;
        return [];
      }
    }),
  );
  for (const list of surfaceLists) {
    for (const surface of list) {
      data.surfaces[surface.id] = { roomId: surface.room_id, name: surface.name, surfaceType: surface.surface_type };
    }
  }
  if (!needOpenings) return data;

  // Openings only exist on walls.
  const walls = surfaceLists.flat().filter((surface) => surface.surface_type === 'WALL');
  await inChunks(walls, OPENING_CONCURRENCY, async (wall) => {
    try {
      const response = await fetchOpenings(projectId, wall.room_id, wall.id, true);
      for (const opening of response.items) {
        data.openings[opening.id] = {
          surfaceId: wall.id,
          roomId: wall.room_id,
          type: opening.opening_type,
          name: opening.name,
        };
      }
    } catch {
      data.complete = false;
    }
  });
  return data;
}

export interface PhotoLocationLabels extends SurfaceDisplayLabels {
  door: string;
  window: string;
  other: string;
}

/** Path segments (room → surface → opening) of an attachment; an unresolved name is undefined. */
export function resolveLocationSegments(
  attachment: Pick<PhotoAttachmentRead, 'context' | 'room_id' | 'surface_id' | 'opening_id'>,
  data: PhotoLocationData,
  labels: PhotoLocationLabels,
): Array<string | undefined> {
  const surfaceName = (surfaceId: string): string | undefined => {
    const surface = data.surfaces[surfaceId];
    return surface ? getSurfaceDisplayName({ name: surface.name, surface_type: surface.surfaceType }, labels) : undefined;
  };
  switch (attachment.context) {
    case 'ROOM':
      return [attachment.room_id ? data.rooms[attachment.room_id] : undefined];
    case 'SURFACE': {
      const surface = attachment.surface_id ? data.surfaces[attachment.surface_id] : undefined;
      return [surface ? data.rooms[surface.roomId] : undefined, attachment.surface_id ? surfaceName(attachment.surface_id) : undefined];
    }
    case 'OPENING': {
      const opening = attachment.opening_id ? data.openings[attachment.opening_id] : undefined;
      const typeLabel = opening ? (opening.type === 'DOOR' ? labels.door : opening.type === 'WINDOW' ? labels.window : labels.other) : undefined;
      return [
        opening ? data.rooms[opening.roomId] : undefined,
        opening ? surfaceName(opening.surfaceId) : undefined,
        typeLabel ? `${typeLabel}${opening?.name ? ` (${opening.name})` : ''}` : undefined,
      ];
    }
    default:
      return [];
  }
}
