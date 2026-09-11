export type RoomMeasurementMode = 'RECTANGLE' | 'CUSTOM';

interface InferredRoomShape {
  length?: unknown;
  width?: unknown;
  height?: unknown;
}

const STORAGE_PREFIX = 'plan-estimate:room-measurement-mode:';

export function loadRoomMeasurementMode(roomId: string): RoomMeasurementMode | null {
  try {
    const raw = localStorage.getItem(STORAGE_PREFIX + roomId);
    if (raw === 'CUSTOM') return 'CUSTOM';
    if (raw === 'RECTANGLE') return 'RECTANGLE';
    return null;
  } catch {
    // Storage unavailable: fall back to data inference.
    return null;
  }
}

export function saveRoomMeasurementMode(roomId: string, mode: RoomMeasurementMode): void {
  try {
    localStorage.setItem(STORAGE_PREFIX + roomId, mode);
  } catch {
    // Storage unavailable (private mode): mode stays session-only.
  }
}

// Custom rooms created in 5D.1A.1 store a default wall height but never length/width,
// so a room with height but no length/width is safely distinguishable from an
// unmeasured rectangle room (all null).
export function inferRoomMeasurementMode(room: InferredRoomShape): RoomMeasurementMode {
  const hasLengthWidth = room.length != null && room.width != null;
  if (!hasLengthWidth && room.height != null) return 'CUSTOM';
  return 'RECTANGLE';
}

export function resolveRoomMeasurementMode(
  roomId: string,
  room: InferredRoomShape,
): RoomMeasurementMode {
  return loadRoomMeasurementMode(roomId) ?? inferRoomMeasurementMode(room);
}
