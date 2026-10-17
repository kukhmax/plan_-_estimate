import { apiRequest } from './http';

// The final deletion of an archived room or surface (archive cleanup AC-4b): the server counts what goes and what holds it.

export interface StructurePurgePreview {
  kind: 'ROOM' | 'SURFACE';
  target_id: string;
  name: string;
  archived: boolean;
  can_purge: boolean;
  /** Surfaces of a room (0 for a surface). */
  surfaces: number;
  openings: number;
  inspections: number;
  photos: number;
  /** File sets (original, display, thumbnail) that leave the storage: those no other photo still uses. */
  photo_files: number;
  bytes: number;
  annotations: number;
  /** Lines of the estimates that name it: they stay as a record and lose the link. */
  estimate_lines: number;
  may_be_in_backups: boolean;
  /** `kind` is a kind of document that is not archived and still points to it: CONCEALED_WORKS | ACCEPTANCE | DOWNTIME | ADJACENT_WORK. */
  blockers: Array<{ kind: string; protocol_id: string; status: string }>;
}

export interface StructurePurgeResult {
  purged: boolean;
  photo_files: number;
  /** File sets still to be removed from the storage: a retry finishes them. */
  storage_pending: number;
}

const roomPath = (projectId: string, roomId: string) => `/api/projects/${projectId}/rooms/${roomId}`;
const surfacePath = (projectId: string, roomId: string, surfaceId: string) => `${roomPath(projectId, roomId)}/surfaces/${surfaceId}`;

export function fetchRoomPurgePreview(projectId: string, roomId: string): Promise<StructurePurgePreview> {
  return apiRequest(`${roomPath(projectId, roomId)}/purge-preview`);
}

export function purgeRoom(projectId: string, roomId: string): Promise<StructurePurgeResult> {
  return apiRequest(`${roomPath(projectId, roomId)}/purge`, { method: 'POST' });
}

export function fetchSurfacePurgePreview(projectId: string, roomId: string, surfaceId: string): Promise<StructurePurgePreview> {
  return apiRequest(`${surfacePath(projectId, roomId, surfaceId)}/purge-preview`);
}

export function purgeSurface(projectId: string, roomId: string, surfaceId: string): Promise<StructurePurgeResult> {
  return apiRequest(`${surfacePath(projectId, roomId, surfaceId)}/purge`, { method: 'POST' });
}
